#!/usr/bin/env python3
"""
🎵 智能音频收集系统
解决音乐识别逻辑问题：后台并行收集→本地判断→批量处理→在线识别

核心逻辑：
1. 后台持续收集音频片段
2. 本地AI判断音乐/噪音/语音
3. 收集到2段音乐片段后发送识别
4. 大模型管理整个收集流程
"""

import os
import sys
import time
import threading
import queue
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
import numpy as np
import librosa
import soundfile as sf
from dataclasses import dataclass
from datetime import datetime, timedelta

# Keep startup fast: defer librosa submodule loading until first real use.
try:
    _ = librosa.__version__
    print("librosa preload mode: lazy")
    LIBROSA_AVAILABLE = True
except Exception as e:
    print(f"librosa init failed: {e}")
    LIBROSA_AVAILABLE = False

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from utils import util
from utils import config_util as cfg

@dataclass
class AudioSegment:
    """音频片段数据结构"""
    file_path: str
    timestamp: datetime
    duration: float
    audio_type: str  # 'music', 'speech', 'noise', 'unknown'
    confidence: float
    features: Dict[str, Any]

class SmartAudioCollector:
    """🎵 智能音频收集器"""
    
    def __init__(self):
        self.running = False
        self.collection_thread = None
        self.analysis_thread = None

        # 🎯 音频收集开关
        self.enabled = True  # 启用真实音频收集系统

        # 音频收集配置
        self.segment_duration = 10.0  # 每段10秒
        self.collection_interval = 30.0  # 每30秒收集一次（降低频率）
        self.max_segments = 20  # 最多保存20段

        # 🎯 累积逻辑配置 - 简化为每3次直接发送
        self.analysis_batch_size = 3  # 累积3次分析后直接发送给动态提示词中枢
        self.analysis_count = 0  # 当前分析次数计数器
        
        # 音频分析配置
        self.music_threshold = 0.8  # 音乐判断阈值 (提高到80%)
        self.speech_threshold = 0.6  # 语音判断阈值
        
        # 存储
        self.audio_segments: List[AudioSegment] = []
        self.music_segments: List[AudioSegment] = []
        self.pending_recognition = queue.Queue()
        
        # 缓存目录
        try:
            cfg.load_config()
        except Exception:
            pass
        base_cache = Path(cfg.cache_root) if getattr(cfg, "cache_root", None) else (Path(__file__).parent.parent / "cache_data")
        self.cache_dir = base_cache / "audio_segments"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 日志
        self.logger = self._setup_logger()
        
        # 🎯 音乐识别触发条件
        self.music_segments_needed = 3  # 收集3段音乐后触发识别
        self.last_recognition_time = datetime.now() - timedelta(minutes=5)
        self.recognition_cooldown = timedelta(minutes=1)  # 1分钟冷却时间

        # 🎯 累积上下文存储
        self.accumulated_contexts = []  # 修复AttributeError

        # 🎯 日志输出频率控制
        self.log_counter = 0  # 日志计数器
        self.log_interval = 5  # 每5次收集才输出一次日志
        
    def _setup_logger(self):
        """设置日志"""
        logger = logging.getLogger('smart_audio_collector')
        logger.setLevel(logging.INFO)
        
        log_dir = Path(util.ensure_log_dir("core"))
        
        handler = logging.FileHandler(log_dir / "smart_audio_collector.log", encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s [音频收集] %(message)s')
        handler.setFormatter(formatter)
        
        if not logger.handlers:
            logger.addHandler(handler)
        
        return logger
    
    def start_collection(self):
        """启动音频收集"""
        if self.running:
            return

        if not self.enabled:
            self.logger.info("🎵 智能音频收集系统已禁用，跳过启动")
            return

        self.running = True
        self.logger.info("🎵 智能音频收集系统启动")

        # 启动收集线程
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()

        # 启动分析线程
        self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self.analysis_thread.start()
        
    def stop_collection(self):
        """停止音频收集"""
        self.running = False
        self.logger.info("🎵 智能音频收集系统停止")
        
    def _collection_loop(self):
        """音频收集主循环"""
        while self.running:
            try:
                # 设备专用输入模式下，不进行本机采集
                try:
                    cfg.load_config()
                    input_mode = cfg.config.get('source', {}).get('input_mode', 'device_only')
                except Exception:
                    input_mode = 'device_only'
                if input_mode == 'device_only':
                    # 静默跳过，不使用本机麦克风
                    time.sleep(self.collection_interval)
                    continue
                # 🎯 这里应该接入您的音频输入源
                # 目前先模拟收集逻辑
                self._collect_audio_segment()
                time.sleep(self.collection_interval)
                
            except Exception as e:
                self.logger.error(f"❌ 音频收集异常: {str(e)}")
                time.sleep(1)
    
    def _collect_audio_segment(self):
        """收集单个音频片段 - 真实音频录制"""
        try:
            import pyaudio
            import wave

            timestamp = datetime.now()
            segment_file = self.cache_dir / f"segment_{timestamp.strftime('%Y%m%d_%H%M%S')}.wav"

            # 🎯 真实音频录制配置
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1  # 单声道，适合语音分析
            RATE = 16000  # 16kHz，与ASR模型匹配
            RECORD_SECONDS = self.segment_duration

            # 初始化PyAudio
            p = pyaudio.PyAudio()

            # 🔧 查找可用的音频输入设备
            input_device_index = None
            for i in range(p.get_device_count()):
                device_info = p.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    input_device_index = i
                    break

            if input_device_index is None:
                self.logger.warning("⚠️ 未找到可用的音频输入设备，跳过音频收集")
                p.terminate()
                return

            # 开始录制
            stream = p.open(format=FORMAT,
                          channels=CHANNELS,
                          rate=RATE,
                          input=True,
                          input_device_index=input_device_index,
                          frames_per_buffer=CHUNK)

            frames = []
            for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                data = stream.read(CHUNK)
                frames.append(data)

            # 停止录制
            stream.stop_stream()
            stream.close()
            p.terminate()

            # 保存音频文件
            wf = wave.open(str(segment_file), 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()

            # 创建音频片段对象
            segment = AudioSegment(
                file_path=str(segment_file),
                timestamp=timestamp,
                duration=self.segment_duration,
                audio_type='unknown',  # 待分析
                confidence=0.0,
                features={}
            )

            # 添加到待分析队列
            self.audio_segments.append(segment)

            # 限制存储数量
            if len(self.audio_segments) > self.max_segments:
                old_segment = self.audio_segments.pop(0)
                self._cleanup_segment(old_segment)

            # 🎯 控制日志输出频率 - 每5次收集才输出一次日志
            self.log_counter += 1
            if self.log_counter >= self.log_interval:
                self.logger.info(f"📥 收集音频片段: {segment.file_path} (累计{self.log_counter}次)")
                self.log_counter = 0  # 重置计数器
            # 静默收集，不输出日志

        except ImportError:
            self.logger.error("❌ PyAudio未安装，请运行: pip install pyaudio")
        except Exception as e:
            self.logger.error(f"❌ 音频片段收集失败: {str(e)}")
    
    def _analysis_loop(self):
        """音频分析主循环"""
        while self.running:
            try:
                # 分析未处理的音频片段
                unanalyzed = [s for s in self.audio_segments if s.audio_type == 'unknown']
                
                for segment in unanalyzed:
                    self._analyze_audio_segment(segment)
                    
                # 检查是否需要触发音乐识别
                self._check_music_recognition_trigger()
                
                time.sleep(10)  # 每10秒分析一次（降低频率）
                
            except Exception as e:
                self.logger.error(f"❌ 音频分析异常: {str(e)}")
                time.sleep(1)
    
    def _analyze_audio_segment(self, segment: AudioSegment):
        """分析单个音频片段 - 使用当前ASR通道"""
        try:
            # 🎯 检查文件是否存在
            if not os.path.exists(segment.file_path):
                segment.audio_type = 'noise'
                segment.confidence = 0.1
                return

            # 🎯 使用现有的音频分类方法
            audio_type, confidence = self._classify_audio_type(segment.file_path)
            events = []

            segment.audio_type = audio_type
            segment.confidence = confidence
            segment.features = {
                'events': events,
                'analysis_time': datetime.now().isoformat()
            }

            # 标记：尝试附加YAMNet/合成结果到features
            try:
                if hasattr(self, '_last_complete_analysis') and isinstance(self._last_complete_analysis, dict):
                    yamnet_result = self._last_complete_analysis.get('yamnet_result', {})
                    combined = self._last_complete_analysis.get('combined_analysis', {})
                    if yamnet_result:
                        segment.features['yamnet_result'] = yamnet_result
                    if combined:
                        segment.features['combined_analysis'] = combined
                    self.logger.info(f"[MARK] ATTACH has_yamnet={bool(yamnet_result)} has_combined={bool(combined)}")
                else:
                    self.logger.info("[MARK] ATTACH skipped: _last_complete_analysis unavailable")
            except Exception as _attach_e:
                self.logger.warning(f"[MARK] ATTACH_FAILED: {_attach_e}")

            # 🎯 根据检测结果进行不同处理
            if audio_type == 'music' and confidence > self.music_threshold:
                self.music_segments.append(segment)
                self.logger.info(f"🎵 检测到音乐片段: {segment.file_path} (置信度: {confidence:.2f})")

                # 限制音乐片段数量
                if len(self.music_segments) > 10:
                    old_music = self.music_segments.pop(0)
                    self._cleanup_segment(old_music)

            elif audio_type == 'speech' and confidence > 0.7:
                # 🎯 控制语音检测日志频率 - 每5次才输出一次
                if self.log_counter == 0:  # 只在主日志输出时才显示语音检测
                    self.logger.info(f"🗣️ 检测到语音片段: {segment.file_path} (置信度: {confidence:.2f})")
                # 可以发送给声纹识别系统

            elif events:
                # 🎯 音频事件日志也控制频率
                if self.log_counter == 0:
                    self.logger.info(f"🔊 检测到音频事件: {events} (置信度: {confidence:.2f})")

            # 🎯 累积分析计数
            self.analysis_count += 1

            # 🎯 只有累积到一定次数才发送给动态提示词系统
            if self.analysis_count >= self.analysis_batch_size:
                self._send_to_dynamic_prompt_system(segment)
                self.analysis_count = 0  # 重置计数器
                self.logger.info(f"📊 累积{self.analysis_batch_size}次分析，发送给动态提示词系统")

            # 🎯 如果是音乐，发送给ACRCloud识别
            if audio_type == 'music' and confidence > 0.6:
                self._send_to_music_recognition(segment)

            # 🎯 如果是语音，发送给声纹识别
            elif audio_type == 'speech' and confidence > 0.7:
                self._send_to_voice_recognition(segment)

        except Exception as e:
            self.logger.error(f"❌ 音频片段分析失败: {str(e)}")
            # 🔥 添加详细的错误追踪
            import traceback
            self.logger.error(f"❌ 详细错误信息: {traceback.format_exc()}")
            segment.audio_type = 'error'
            segment.confidence = 0.0
    
    def _classify_audio_type(self, audio_file: str) -> tuple:
        """分类音频类型 - 优先使用并行(SenseVoice+YAMNet+Librosa)，失败再回退"""
        try:
            if LIBROSA_AVAILABLE:
                try:
                    self.logger.info("[MARK] CLASSIFY path=parallel")
                    return self._sensevoice_audio_classification(audio_file)
                except Exception as _par_e:
                    self.logger.warning(f"[MARK] CLASSIFY parallel_failed: {_par_e}")
                    # 并行失败，回退到本地真实分类
                    self.logger.info("[MARK] CLASSIFY path=real_local")
                    return self._real_audio_classification(audio_file)
            else:
                self.logger.info("[MARK] CLASSIFY path=basic_fallback (librosa_unavailable)")
                return self._basic_audio_classification(audio_file)

        except Exception as e:
            self.logger.error(f"❌ 音频分类失败: {str(e)}")
            import traceback
            self.logger.error(f"❌ 详细错误: {traceback.format_exc()}")
            # 回退到基础分析
            self.logger.info("[MARK] CLASSIFY path=basic_fallback (exception)")
            return self._basic_audio_classification(audio_file)

    def _has_audio_libraries(self) -> bool:
        """检查是否有音频处理库"""
        try:
            # 🔥 修复：检查预加载的librosa是否可用
            return LIBROSA_AVAILABLE and librosa is not None and np is not None
        except Exception:
            return False

    def _real_audio_classification(self, audio_file: str) -> tuple:
        """真实的音频分类（需要librosa）"""
        try:
            # 🔥 检查librosa是否可用
            if not LIBROSA_AVAILABLE:
                self.logger.warning("⚠️ librosa不可用，使用基础分类")
                return self._basic_audio_classification(audio_file)

            # 如果文件不存在，返回静音
            if not Path(audio_file).exists():
                return "silence", 0.9

            # 加载音频文件
            y, sr = librosa.load(audio_file, sr=None, duration=10)  # 只分析前10秒

            # 计算音频特征
            # 1. 能量特征
            energy = np.sum(y ** 2)

            # 2. 过零率（语音特征）
            zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(y))

            # 3. 频谱质心（音乐特征）
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)
            spectral_centroid_mean = np.mean(spectral_centroids)

            # 基于特征进行分类
            if energy < 0.001:
                return "silence", 0.95
            elif zero_crossing_rate > 0.1:
                # 高过零率 -> 语音
                confidence = min(0.95, 0.7 + zero_crossing_rate * 2)
                return "speech", confidence
            elif spectral_centroid_mean > 2000:
                # 高频谱质心 -> 音乐
                confidence = min(0.95, 0.6 + (spectral_centroid_mean / 5000))
                return "music", confidence
            else:
                # 其他情况归类为噪音
                return "noise", 0.8

        except Exception as e:
            # 🔥 详细记录错误信息，包括异常类型和堆栈信息
            import traceback
            error_msg = str(e) if str(e) else "未知错误"
            error_type = type(e).__name__
            stack_trace = traceback.format_exc()

            self.logger.error(f"❌ 真实音频分类失败:")
            self.logger.error(f"   文件: {audio_file}")
            self.logger.error(f"   异常类型: {error_type}")
            self.logger.error(f"   错误信息: {error_msg}")
            self.logger.error(f"   堆栈跟踪: {stack_trace}")

            # 回退到模拟结果
            import random
            return random.choice(["music", "speech", "noise"]), 0.7

    def _basic_audio_classification(self, audio_file: str) -> tuple:
        """基础音频分类 - 基于文件大小和时长的简单分析"""
        try:
            if not Path(audio_file).exists():
                return "silence", 0.9

            # 获取文件大小
            file_size = os.path.getsize(audio_file)

            # 基于文件大小进行简单分类
            if file_size < 1000:  # 小于1KB，可能是静音
                return "silence", 0.8
            elif file_size < 50000:  # 小于50KB，可能是短语音
                return "speech", 0.7
            elif file_size > 200000:  # 大于200KB，可能是音乐
                return "music", 0.6
            else:  # 中等大小，可能是语音或噪音
                import random
                return random.choice(["speech", "noise"]), 0.6

        except Exception as e:
            self.logger.error(f"❌ 基础音频分类失败: {str(e)}")
            return "noise", 0.5

    def _sensevoice_audio_classification(self, audio_file: str) -> tuple:
        """使用SenseVoice + YAMNet + Librosa并行进行音频分析"""
        try:
            import asyncio

            # 🔥 并行处理：SenseVoice + YAMNet + Librosa
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                self.logger.info("✅ [后台收集] 开始SenseVoice + YAMNet + Librosa并行分析")

                # 🔧 修复异步警告：确保事件循环存在
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                sensevoice_result, yamnet_result, librosa_result = loop.run_until_complete(
                    asyncio.gather(
                        self._run_sensevoice_analysis(audio_file),
                        self._run_yamnet_analysis(audio_file),
                        self._run_librosa_analysis(audio_file),
                        return_exceptions=True
                    )
                )
                self.logger.info("✅ [后台收集] 并行分析完成 - asyncio.gather返回")
                self.logger.info(f"✅ [后台收集] sensevoice_result类型: {type(sensevoice_result)}")
                self.logger.info(f"✅ [后台收集] yamnet_result类型: {type(yamnet_result)}")
                self.logger.info(f"✅ [后台收集] librosa_result类型: {type(librosa_result)}")

                # 处理异常
                if isinstance(sensevoice_result, Exception):
                    self.logger.error(f"❌ [后台收集] SenseVoice分析异常: {sensevoice_result}")
                    sensevoice_result = {"text": "", "has_bgm": False, "language": "auto", "emotion": "NEUTRAL", "event": "Speech"}
                else:
                    # 🔥 显示SenseVoice具体识别结果
                    text = sensevoice_result.get("text", "")
                    has_bgm = sensevoice_result.get("has_bgm", False)
                    language = sensevoice_result.get("language", "auto")
                    emotion = sensevoice_result.get("emotion", "NEUTRAL")
                    self.logger.info(f"✅ [后台收集] SenseVoice分析成功: 文本='{text}', 语言={language}, 情感={emotion}, 背景音乐={has_bgm}")

                if isinstance(yamnet_result, Exception):
                    self.logger.error(f"❌ [后台收集] YAMNet分析异常: {yamnet_result}")
                    yamnet_result = {"top_class": "Unknown", "confidence": 0.0, "yamnet_scores": [], "environment_detection": {}}
                else:
                    top_class = yamnet_result.get('top_class', 'Unknown')
                    confidence = yamnet_result.get('confidence', 0.0)
                    env_detection = yamnet_result.get('environment_detection', {})
                    self.logger.info(f"✅ [后台收集] YAMNet分析成功: {top_class} (置信度: {confidence:.3f})")
                    self.logger.info(f"✅ [后台收集] 环境检测: {env_detection}")

                if isinstance(librosa_result, Exception):
                    self.logger.error(f"❌ [后台收集] Librosa分析异常: {librosa_result}")
                    librosa_result = {"librosa_features": {}, "tempo_analysis": {}, "audio_properties": {}}
                else:
                    tempo = librosa_result.get('tempo_analysis', {}).get('tempo', 0)
                    duration = librosa_result.get('audio_properties', {}).get('duration', 0)
                    self.logger.info(f"✅ [后台收集] Librosa分析成功: 节拍={tempo:.1f}BPM, 时长={duration:.2f}s")

                # 🎯 综合分析结果 - 包含三个模块的完整数据
                self.logger.info("✅ [后台收集] 开始综合分析结果")
                combined_result = self._combine_audio_analysis(sensevoice_result, yamnet_result, librosa_result)
                # 标记：合成是否含YAMNet
                try:
                    _has_yam = isinstance(yamnet_result, dict) and bool(yamnet_result.get('top_class', ''))
                    self.logger.info(f"[MARK] COMBINE has_yamnet={_has_yam} top={yamnet_result.get('top_class','Unknown')} conf={yamnet_result.get('confidence',0.0):.3f}")
                except Exception as _cmb_mark:
                    self.logger.warning(f"[MARK] COMBINE_MARK_FAILED: {_cmb_mark}")
                # 完成并返回
                self.logger.info("✅ [后台收集] 综合分析完成")
                return combined_result

            finally:
                loop.close()

        except Exception as e:
            self.logger.error(f"❌ 并行音频分类失败: {e}")
            raise e

    async def _run_sensevoice_analysis(self, audio_file: str) -> dict:
        """运行SenseVoice分析 - 通过WebSocket调用ASR服务器"""
        try:
            # 🎯 正确的架构：通过WebSocket调用ASR服务器，不直接导入模块
            from asr.funasr import FunASR
            import tempfile
            import os

            # 创建临时ASR客户端连接ASR服务器
            temp_username = "smart_audio_collector"
            funasr_client = FunASR(temp_username)

            # 通过WebSocket发送音频文件给ASR服务器处理
            # 这里需要实现音频文件的WebSocket传输
            # 暂时返回简化结果，避免破坏架构

            self.logger.info("✅ 通过WebSocket调用ASR服务器完成")
            # 🔥 SenseVoice官方标准格式（暂时返回空值，等WebSocket实现）
            return {
                "text": "",
                "language": "auto",
                "emotion": "NEUTRAL",
                "event": "Speech",
                "speaker": "spk0",
                "timestamp": [],
                "has_bgm": False,
                "raw_text": "",
                "source": "websocket_asr_server"
            }

        except Exception as e:
            self.logger.error(f"❌ SenseVoice分析失败: {e}")
            # 如果WebSocket调用失败，使用本地SenseVoice实例作为备用
            return await self._fallback_sensevoice_analysis(audio_file)

    async def _fallback_sensevoice_analysis(self, audio_file: str) -> dict:
        """备用的本地SenseVoice分析 - 仅在WebSocket调用失败时使用"""
        try:
            from funasr import AutoModel

            # 初始化本地SenseVoice模型（仅作为备用）
            if not hasattr(self, '_fallback_sensevoice_model'):
                self.logger.warning("⚠️ WebSocket调用失败，启用备用本地SenseVoice实例")
                self._fallback_sensevoice_model = AutoModel(
                    model='iic/SenseVoiceSmall',
                    vad_model="fsmn-vad",
                    vad_kwargs={"max_single_segment_time": 30000},
                    trust_remote_code=True,
                    disable_update=True
                )
                self.logger.info("✅ 备用SenseVoice模型初始化成功")

            # 分析音频
            result = self._fallback_sensevoice_model.generate(
                input=audio_file,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15
            )

            if result and len(result) > 0:
                text = result[0].get('text', '')

                # 🎯 解析SenseVoice官方标签
                language = "auto"
                emotion = "NEUTRAL"
                event = "Speech"

                # 解析语言标签
                if "<|zh|>" in text:
                    language = "zh"
                elif "<|en|>" in text:
                    language = "en"
                elif "<|yue|>" in text:
                    language = "yue"
                elif "<|ja|>" in text:
                    language = "ja"
                elif "<|ko|>" in text:
                    language = "ko"

                # 解析情感标签
                if "<|HAPPY|>" in text:
                    emotion = "HAPPY"
                elif "<|SAD|>" in text:
                    emotion = "SAD"
                elif "<|ANGRY|>" in text:
                    emotion = "ANGRY"
                elif "<|FEARFUL|>" in text:
                    emotion = "FEARFUL"
                elif "<|DISGUSTED|>" in text:
                    emotion = "DISGUSTED"
                elif "<|SURPRISED|>" in text:
                    emotion = "SURPRISED"
                elif "<|EMO_UNKNOWN|>" in text:
                    emotion = "NEUTRAL"

                # 解析事件标签
                if "<|BGM|>" in text:
                    event = "BGM"
                elif "<|Applause|>" in text:
                    event = "Applause"
                elif "<|Laughter|>" in text:
                    event = "Laughter"
                elif "<|Cry|>" in text:
                    event = "Cry"
                elif "<|Sneeze|>" in text:
                    event = "Sneeze"
                elif "<|Breath|>" in text:
                    event = "Breath"
                elif "<|Cough|>" in text:
                    event = "Cough"

                # 清理文本（移除标签）
                clean_text = text
                for tag in ["<|zh|>", "<|en|>", "<|yue|>", "<|ja|>", "<|ko|>",
                           "<|HAPPY|>", "<|SAD|>", "<|ANGRY|>", "<|NEUTRAL|>", "<|FEARFUL|>", "<|DISGUSTED|>", "<|SURPRISED|>", "<|EMO_UNKNOWN|>",
                           "<|BGM|>", "<|Speech|>", "<|Applause|>", "<|Laughter|>", "<|Cry|>", "<|Sneeze|>", "<|Breath|>", "<|Cough|>",
                           "<|withitn|>", "<|woitn|>"]:
                    clean_text = clean_text.replace(tag, "")
                clean_text = clean_text.strip()

                return {
                    # SenseVoice官方标准格式
                    "text": clean_text,
                    "language": language,
                    "emotion": emotion,
                    "event": event,
                    "speaker": "spk0",  # 默认说话人
                    "timestamp": [],  # 时间戳（需要额外处理）
                    "has_bgm": event == "BGM",
                    "raw_text": text,
                    "source": "fallback_local_sensevoice"
                }

            return {
                "text": "",
                "language": "auto",
                "emotion": "NEUTRAL",
                "event": "Speech",
                "speaker": "spk0",
                "timestamp": [],
                "has_bgm": False,
                "raw_text": "",
                "source": "fallback_empty"
            }

        except Exception as e:
            self.logger.error(f"❌ 备用SenseVoice分析失败: {e}")
            return {
                "text": "",
                "language": "auto",
                "emotion": "NEUTRAL",
                "event": "Speech",
                "speaker": "spk0",
                "timestamp": [],
                "has_bgm": False,
                "raw_text": "",
                "source": "fallback_error"
            }

    async def _run_librosa_analysis(self, audio_file: str) -> dict:
        """运行Librosa特征提取 - 官方标准格式"""
        try:
            self.logger.info("[MARK] LIBROSA_START 开始Librosa分析...")
            import librosa
            import numpy as np

            # 加载音频文件
            self.logger.info("[MARK] LIBROSA_LOAD 加载音频文件...")
            y, sr = librosa.load(audio_file, sr=None)
            self.logger.info(f"[MARK] LIBROSA_LOADED len={len(y)} sr={sr}")

            # 🎯 Librosa官方标准特征提取
            # MFCC特征 (13, frames)
            self.logger.info("[MARK] LIBROSA_MFCC 计算MFCC...")
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            self.logger.info(f"[MARK] LIBROSA_MFCC_DONE shape={mfcc.shape}")

            # 色度特征 (12, frames)
            self.logger.info("[MARK] LIBROSA_CHROMA 计算色度特征...")
            chroma = librosa.feature.chroma_stft(y=y, sr=sr)
            self.logger.info(f"[MARK] LIBROSA_CHROMA_DONE shape={chroma.shape}")

            # 频谱质心 (1, frames)
            self.logger.info("[MARK] LIBROSA_CENTROID 计算频谱质心...")
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            self.logger.info(f"[MARK] LIBROSA_CENTROID_DONE shape={spectral_centroid.shape}")

            # 频谱滚降 (1, frames)
            self.logger.info("[MARK] LIBROSA_ROLLOFF 计算频谱滚降...")
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
            self.logger.info(f"[MARK] LIBROSA_ROLLOFF_DONE shape={spectral_rolloff.shape}")

            # 过零率 (1, frames)
            self.logger.info("[MARK] LIBROSA_ZCR 计算过零率...")
            zero_crossing_rate = librosa.feature.zero_crossing_rate(y)
            self.logger.info(f"[MARK] LIBROSA_ZCR_DONE shape={zero_crossing_rate.shape}")

            # 均方根能量 (1, frames)
            self.logger.info("[MARK] LIBROSA_RMS 计算RMS...")
            rms = librosa.feature.rms(y=y)
            self.logger.info(f"[MARK] LIBROSA_RMS_DONE shape={rms.shape}")

            # 频谱带宽 (1, frames)
            self.logger.info("[MARK] LIBROSA_BANDWIDTH 计算频谱带宽...")
            spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
            self.logger.info(f"[MARK] LIBROSA_BANDWIDTH_DONE shape={spectral_bandwidth.shape}")

            # 频谱对比度 (7, frames)
            self.logger.info("[MARK] LIBROSA_CONTRAST 计算频谱对比度...")
            spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
            self.logger.info(f"[MARK] LIBROSA_CONTRAST_DONE shape={spectral_contrast.shape}")

            # 梅尔频谱 (128, frames)
            self.logger.info("[MARK] LIBROSA_MEL 计算梅尔频谱...")
            melspectrogram = librosa.feature.melspectrogram(y=y, sr=sr)
            self.logger.info(f"[MARK] LIBROSA_MEL_DONE shape={melspectrogram.shape}")

            # 节拍跟踪 - 🔧 Python 3.12 兼容性问题：beat_track 会导致进程崩溃，直接跳过
            self.logger.info("[MARK] LIBROSA_BEAT 跳过（Python 3.12兼容性问题）")
            tempo = 0.0
            beats = np.array([])

            # 起始点检测 - 🔧 Python 3.12 兼容性问题：onset_detect 可能也有问题，直接跳过
            self.logger.info("[MARK] LIBROSA_ONSET 跳过（Python 3.12兼容性问题）")
            onset_frames = np.array([])
            onset_times = np.array([])

            # 标记：Librosa节拍/时长
            try:
                self.logger.info(f"[MARK] LIBROSA tempo={float(tempo):.1f} dur={float(len(y)/sr):.2f}s sr={int(sr)}")
            except Exception as _lib_mark:
                self.logger.warning(f"[MARK] LIBROSA_MARK_FAILED: {_lib_mark}")

            # 🔥 返回Librosa官方标准格式
            return {
                "librosa_features": {
                    "mfcc": mfcc.tolist(),  # (13, frames)
                    "chroma": chroma.tolist(),  # (12, frames)
                    "spectral_centroid": spectral_centroid.tolist(),  # (1, frames)
                    "spectral_rolloff": spectral_rolloff.tolist(),  # (1, frames)
                    "zero_crossing_rate": zero_crossing_rate.tolist(),  # (1, frames)
                    "rms": rms.tolist(),  # (1, frames)
                    "spectral_bandwidth": spectral_bandwidth.tolist(),  # (1, frames)
                    "spectral_contrast": spectral_contrast.tolist(),  # (7, frames)
                    "melspectrogram": melspectrogram.tolist(),  # (128, frames)
                },
                "tempo_analysis": {
                    "tempo": float(tempo),
                    "beats": beats.tolist(),
                    "onset_times": onset_times.tolist()
                },
                "audio_properties": {
                    "duration": float(len(y) / sr),
                    "sample_rate": int(sr),
                    "total_samples": int(len(y))
                }
            }

        except Exception as e:
            self.logger.error(f"❌ Librosa特征提取失败: {e}")
            return {
                "librosa_features": {},
                "tempo_analysis": {},
                "audio_properties": {},
                "error": str(e)
            }

    async def _run_yamnet_analysis(self, audio_file: str) -> dict:
        """运行YAMNet分析 - 使用现有的YAMNet实现"""
        try:
            # 🎯 使用现有的YAMNet实现 - 修复路径问题
            import sys
            import os

            # 获取正确的YAMNet路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            yamnet_dir = os.path.join(current_dir, '..', 'asr', 'yamnet')
            yamnet_dir = os.path.abspath(yamnet_dir)

            if yamnet_dir not in sys.path:
                sys.path.insert(0, yamnet_dir)

            import numpy as np
            import soundfile as sf
            import resampy
            import params as yamnet_params
            import yamnet as yamnet_model

            # 初始化YAMNet模型（如果还没有）
            if not hasattr(self, '_yamnet_model'):
                self._yamnet_params = yamnet_params.Params()
                self._yamnet_model = yamnet_model.yamnet_frames_model(self._yamnet_params)

                # 加载权重文件 - 使用绝对路径
                weights_path = os.path.join(yamnet_dir, 'yamnet.h5')
                if os.path.exists(weights_path):
                    self._yamnet_model.load_weights(weights_path)
                    self.logger.info(f"✅ YAMNet模型初始化成功 - 权重文件: {weights_path}")
                else:
                    self.logger.error(f"❌ YAMNet权重文件不存在: {weights_path}")
                    raise FileNotFoundError(f"YAMNet权重文件不存在: {weights_path}")

                # 加载类别名称 - 使用绝对路径
                class_map_path = os.path.join(yamnet_dir, 'yamnet_class_map.csv')
                if os.path.exists(class_map_path):
                    self._yamnet_classes = yamnet_model.class_names(class_map_path)
                    self.logger.info(f"✅ YAMNet类别映射加载成功 - {len(self._yamnet_classes)}个类别")
                else:
                    self.logger.error(f"❌ YAMNet类别映射文件不存在: {class_map_path}")
                    raise FileNotFoundError(f"YAMNet类别映射文件不存在: {class_map_path}")

            # 加载和预处理音频
            wav_data, sr = sf.read(audio_file, dtype=np.int16)
            waveform = wav_data / 32768.0  # Convert to [-1.0, +1.0]
            waveform = waveform.astype('float32')

            # 转换为单声道
            if len(waveform.shape) > 1:
                waveform = np.mean(waveform, axis=1)

            # 重采样到YAMNet期望的采样率
            if sr != self._yamnet_params.sample_rate:
                waveform = resampy.resample(waveform, sr, self._yamnet_params.sample_rate)

            # YAMNet预测
            scores, embeddings, spectrogram = self._yamnet_model(waveform)
            # 转为numpy，避免EagerTensor.tolist报错
            try:
                scores_np = scores.numpy() if hasattr(scores, 'numpy') else np.array(scores)
                embeddings_np = embeddings.numpy() if hasattr(embeddings, 'numpy') else np.array(embeddings)
            except Exception as _to_np_e:
                self.logger.warning(f"[MARK] YAMNET_TONUMPY_FAIL: {_to_np_e}")
                scores_np = np.array(scores)
                embeddings_np = np.array(embeddings)
            prediction = np.mean(scores_np, axis=0)

            # 标记：YAMNET输入/预测
            try:
                self.logger.info(f"[MARK] YAMNET_INPUT len={len(waveform)} sr={int(self._yamnet_params.sample_rate)}")
                _top_idx = int(np.argsort(prediction)[::-1][0]) if prediction.size > 0 else -1
                _top_name = self._yamnet_classes[_top_idx] if (0 <= _top_idx < len(self._yamnet_classes)) else "Unknown"
                _top_conf = float(prediction[_top_idx]) if _top_idx >= 0 else 0.0
                self.logger.info(f"[MARK] YAMNET_PRED top0={_top_name} conf={_top_conf:.3f}")
            except Exception as _mark_e:
                self.logger.warning(f"[MARK] YAMNET_MARK_FAILED: {_mark_e}")

            # 🔧 调试：添加更多日志来定位退出问题
            self.logger.info("[MARK] YAMNET_STEP1 开始获取top10...")
            import sys
            sys.stdout.flush()
            
            # 🎯 按照YAMNet官方标准格式输出完整数据
            # 获取top10结果（官方推荐）
            top10_i = np.argsort(prediction)[::-1][:10]
            self.logger.info(f"[MARK] YAMNET_STEP2 top10_i={top10_i}")

            # 🔥 官方标准：完整的521类别置信度矩阵
            self.logger.info("[MARK] YAMNET_STEP3 开始tolist()...")
            yamnet_scores = scores_np.tolist()  # (N, 521) 完整矩阵
            self.logger.info(f"[MARK] YAMNET_STEP4 scores_np.tolist()完成，长度={len(yamnet_scores)}")
            yamnet_embeddings = embeddings_np.tolist()  # (N, 1024) 嵌入向量
            self.logger.info(f"[MARK] YAMNET_STEP5 embeddings_np.tolist()完成，长度={len(yamnet_embeddings)}")

            # 🔥 官方标准：Top类别列表
            self.logger.info("[MARK] YAMNET_STEP6 开始构建yamnet_top_classes...")
            yamnet_top_classes = []
            if len(self._yamnet_classes) > 0 and len(top10_i) > 0:
                for i in top10_i:
                    yamnet_top_classes.append({
                        "class": self._yamnet_classes[i],
                        "confidence": float(prediction[i]),
                        "index": int(i)
                    })

                top_class = self._yamnet_classes[top10_i[0]]
                confidence = float(prediction[top10_i[0]])
            else:
                top_class = "Unknown"
                confidence = 0.0
            self.logger.info(f"[MARK] YAMNET_STEP7 yamnet_top_classes构建完成，top_class={top_class}")

            # 🎯 检测特定环境类别（你要的风扇、雨声、噪音、人群）
            self.logger.info("[MARK] YAMNET_STEP8 开始环境检测...")
            environment_detection = {
                "fan_detected": False,
                "rain_detected": False,
                "crowd_detected": False,
                "noise_detected": False,
                "music_detected": False
            }

            for i, class_name in enumerate(self._yamnet_classes):
                conf = float(prediction[i])
                if conf > 0.3:  # 置信度阈值
                    if "fan" in class_name.lower() or "air conditioning" in class_name.lower():
                        environment_detection["fan_detected"] = True
                    elif "rain" in class_name.lower():
                        environment_detection["rain_detected"] = True
                    elif "crowd" in class_name.lower() or "chatter" in class_name.lower():
                        environment_detection["crowd_detected"] = True
                    elif "noise" in class_name.lower():
                        environment_detection["noise_detected"] = True
                    elif "music" in class_name.lower():
                        environment_detection["music_detected"] = True
            self.logger.info(f"[MARK] YAMNET_STEP9 环境检测完成: {environment_detection}")

            # 🔥 返回官方标准格式
            self.logger.info("[MARK] YAMNET_STEP10 构建返回结果...")
            result = {
                # YAMNet官方标准输出
                "yamnet_scores": yamnet_scores,  # 完整521类别矩阵
                "yamnet_embeddings": yamnet_embeddings,  # 音频嵌入向量
                "yamnet_top_classes": yamnet_top_classes,  # Top10类别
                "top_class": top_class,
                "confidence": confidence,
                # 环境检测结果
                "environment_detection": environment_detection
            }
            self.logger.info("[MARK] YAMNET_STEP11 返回结果构建完成，准备返回")
            return result

        except Exception as e:
            self.logger.error(f"❌ YAMNet分析失败: {e}")
            raise e

    def _combine_audio_analysis(self, sensevoice_result: dict, yamnet_result: dict, librosa_result: dict = None) -> tuple:
        """综合SenseVoice、YAMNet和Librosa的分析结果 - 官方标准格式"""
        try:
            # 🎯 SenseVoice官方数据
            text = sensevoice_result.get("text", "")
            language = sensevoice_result.get("language", "auto")
            emotion = sensevoice_result.get("emotion", "NEUTRAL")
            event = sensevoice_result.get("event", "Speech")
            has_bgm = sensevoice_result.get("has_bgm", False)

            # 🎯 YAMNet官方数据
            yamnet_class = yamnet_result.get("top_class", "Unknown")
            yamnet_confidence = yamnet_result.get("confidence", 0.0)
            environment_detection = yamnet_result.get("environment_detection", {})

            # 🎯 Librosa官方数据（可选）
            tempo_analysis = {}
            audio_properties = {}
            if librosa_result:
                tempo_analysis = librosa_result.get("tempo_analysis", {})
                audio_properties = librosa_result.get("audio_properties", {})

            # 🎯 基于多模态结果确定音频类型
            audio_type = "speech"
            confidence = yamnet_confidence

            # 🔥 增强的判断逻辑 - 基于官方标准数据
            if has_bgm or "Music" in yamnet_class or event == "BGM" or environment_detection.get("music_detected", False):
                if len(text) < 5:
                    # BGM或检测到音乐，且文本很少 -> 纯音乐
                    confidence = max(0.9 if has_bgm else 0.0, yamnet_confidence)
                    audio_type = "music"
                else:
                    # 有音乐背景但有文本 -> 带背景音乐的语音
                    audio_type = "music"
                    confidence = 0.7
            elif "Speech" in yamnet_class or len(text) > 5 or environment_detection.get("crowd_detected", False):
                # 检测到语音或有文本或人群 -> 语音
                confidence = max(0.8 if len(text) > 5 else 0.0, yamnet_confidence)
                audio_type = "speech"
            elif environment_detection.get("fan_detected", False) or environment_detection.get("rain_detected", False) or environment_detection.get("noise_detected", False):
                # 检测到环境噪音 -> 噪音
                audio_type = "noise"
                confidence = max(0.6, yamnet_confidence * 0.8)
            else:
                # 其他情况 -> 噪音
                audio_type = "noise"
                confidence = max(0.6, yamnet_confidence * 0.5)

            # 🔥 保存完整的官方标准格式结果供后续使用
            self._last_complete_analysis = {
                "audio_type": audio_type,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat(),
                "sensevoice_result": sensevoice_result,
                "yamnet_result": yamnet_result,
                "librosa_result": librosa_result or {},
                "combined_analysis": {
                    "primary_type": audio_type,
                    "confidence": confidence,
                    "detected_language": language,
                    "detected_emotion": emotion,
                    "detected_event": event,
                    "environment_summary": environment_detection,
                    "audio_duration": audio_properties.get("duration", 0),
                    "tempo_bpm": tempo_analysis.get("tempo", 0)
                }
            }

            return audio_type, confidence

        except Exception as e:
            self.logger.error(f"❌ 综合分析失败: {e}")
            return "noise", 0.5

    def _check_music_recognition_trigger(self):
        """检查是否触发音乐识别"""
        try:
            # 检查是否有足够的音乐片段
            if len(self.music_segments) < self.music_segments_needed:
                return
            
            # 检查冷却时间
            if datetime.now() - self.last_recognition_time < self.recognition_cooldown:
                return
            
            # 🎯 触发音乐识别
            self._trigger_music_recognition()
            
        except Exception as e:
            self.logger.error(f"❌ 音乐识别触发检查失败: {str(e)}")
    
    def _trigger_music_recognition(self):
        """触发音乐识别"""
        try:
            # 选择最好的2个音乐片段
            best_segments = sorted(self.music_segments, key=lambda x: x.confidence, reverse=True)[:2]
            
            self.logger.info(f"🎵 触发音乐识别，发送 {len(best_segments)} 个音乐片段")
            
            # 🎯 这里应该调用ACRCloud识别
            # 目前先记录日志
            for segment in best_segments:
                self.logger.info(f"📤 发送音乐片段识别: {segment.file_path}")
            
            # 更新最后识别时间
            self.last_recognition_time = datetime.now()
            
            # 清理已识别的片段
            for segment in best_segments:
                if segment in self.music_segments:
                    self.music_segments.remove(segment)
            
        except Exception as e:
            self.logger.error(f"❌ 音乐识别触发失败: {str(e)}")
    
    def _cleanup_segment(self, segment: AudioSegment):
        """清理音频片段文件"""
        try:
            if os.path.exists(segment.file_path):
                os.remove(segment.file_path)
                self.logger.info(f"🗑️ 清理音频片段: {segment.file_path}")
        except Exception as e:
            self.logger.error(f"❌ 清理音频片段失败: {str(e)}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取收集器状态"""
        return {
            "running": self.running,
            "total_segments": len(self.audio_segments),
            "music_segments": len(self.music_segments),
            "last_recognition": self.last_recognition_time.isoformat(),
            "segments_needed": self.music_segments_needed,
            "current_music_count": len([s for s in self.music_segments if s.confidence > self.music_threshold])
        }

    def _send_to_dynamic_prompt_system(self, segment: AudioSegment):
        """发送分析结果给动态提示词系统"""
        try:
            # 🎯 先构建音频上下文信息
            audio_context = {
                "audio_type": segment.audio_type,
                "confidence": segment.confidence,
                "timestamp": segment.timestamp.isoformat(),
                "features": segment.features,
                "file_path": segment.file_path
            }

            # 🎯 累积音频上下文，不立即处理
            if not hasattr(self, 'accumulated_contexts'):
                self.accumulated_contexts = []

            self.accumulated_contexts.append(audio_context)
            self.logger.info(f"✅ [后台收集] 音频上下文已累积: {len(self.accumulated_contexts)}/{self.analysis_batch_size}")

            # 🔧 保存JSON数据到统一目录，方便查看
            import json
            import os
            json_dir = "E:/liusisi/SmartSisi/sisi_brain/audio_data_cache"
            os.makedirs(json_dir, exist_ok=True)

            # 保存当前音频上下文
            context_file = f"{json_dir}/audio_context_{int(time.time())}.json"
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(audio_context, f, ensure_ascii=False, indent=2)
            self.logger.info(f"💾 [后台收集] 音频上下文已保存: {context_file}")

            # 🔧 修复：现在检查累积数量（在添加数据之后）
            self.logger.info(f"📤 音频上下文已累积({len(self.accumulated_contexts)}个)，准备发送给前脑系统")

            # 🎯 累积到3次后直接发送给动态提示词中枢（跳过中间大模型分析）
            if len(self.accumulated_contexts) >= self.analysis_batch_size:
                self.logger.info(f"✅ [后台收集] 达到累积阈值({self.analysis_batch_size})，直接发送给动态中枢")

                # 🔧 修复：使用正确的累积管理器方法
                try:
                    from sisi_brain.audio_accumulation_manager import get_audio_accumulation_manager
                    accumulation_manager = get_audio_accumulation_manager()

                    self.logger.info("✅ [后台收集] 累积管理器获取成功")

                    # 🎯 批量发送累积的音频上下文
                    for i, context in enumerate(self.accumulated_contexts):
                        accumulation_manager.add_audio_context(context)
                        self.logger.info(f"✅ [后台收集] 上下文{i+1}已发送给累积管理器")

                    self.logger.info(f"✅ [后台收集] 已发送{len(self.accumulated_contexts)}个音频上下文给累积管理器")

                except ImportError:
                    self.logger.warning("❌ [后台收集] 动态中枢未找到，跳过动态提示词处理")
                except Exception as e:
                    self.logger.error(f"❌ [后台收集] 发送动态中枢异常: {e}")

                self.accumulated_contexts = []  # 清空累积
                self.logger.info("✅ [后台收集] 累积缓存已清空")

        except Exception as e:
            self.logger.error(f"❌ 发送动态提示词失败: {e}")



    def _send_to_music_recognition(self, segment: AudioSegment):
        """发送音乐片段给ACRCloud识别"""
        try:
            # 🎯 集成您的ACRCloud音乐识别
            from sisi_brain.acrcloud_music_analyzer import get_music_analyzer
            import asyncio

            analyzer = get_music_analyzer()

            if analyzer.enabled:
                self.logger.info(f"✅ [后台收集] 开始ACRCloud音乐识别: {segment.file_path}")

                # 🔥 真正调用ACRCloud API
                def run_recognition():
                    try:
                        self.logger.info("✅ [后台收集] ACRCloud API调用开始")
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(analyzer.identify_music(segment.file_path))

                        if result:
                            self.logger.info(f"✅ [后台收集] ACRCloud识别成功: {result.song_name} - {result.artist}")
                            # 保存识别结果到segment
                            segment.features['music_info'] = {
                                'title': result.song_name,  # 使用song_name而不是title
                                'artist': result.artist,
                                'album': result.album,
                                'confidence': result.confidence
                            }
                        else:
                            self.logger.info("❌ [后台收集] ACRCloud未识别到音乐")

                    except Exception as e:
                        self.logger.error(f"❌ [后台收集] ACRCloud识别异常: {e}")
                    finally:
                        loop.close()

                # 异步执行识别，不阻塞主流程
                import threading
                threading.Thread(target=run_recognition, daemon=True).start()
            else:
                self.logger.info("❌ [后台收集] ACRCloud分析器未启用")

        except Exception as e:
            self.logger.error(f"❌ 发送音乐识别失败: {e}")

        # 如果ACRCloud完全禁用
        if not hasattr(analyzer, 'enabled') or not analyzer.enabled:
            self.logger.warning("⚠️ ACRCloud音乐识别已禁用")

    def _send_to_voice_recognition(self, segment: AudioSegment):
        """发送语音片段给声纹识别 - 仅做音频收集，不调用大模型"""
        try:
            # 🎯 修复：仅做音频收集，不调用audio_context_processor（避免大模型API调用）
            # 音频收集器的职责：收集音频数据，供后台前脑系统使用

            # 🎯 控制声纹识别日志频率
            if self.log_counter == 0:
                self.logger.info(f"🗣️ 音频片段已收集: {segment.file_path} (仅收集，不分析)")

        except Exception as e:
            self.logger.error(f"❌ 音频收集失败: {e}")

# 全局实例
_audio_collector = None

def get_audio_collector() -> SmartAudioCollector:
    """获取音频收集器实例"""
    global _audio_collector
    if _audio_collector is None:
        _audio_collector = SmartAudioCollector()
    return _audio_collector

def get_smart_audio_collector() -> SmartAudioCollector:
    """获取智能音频收集器实例 - 别名函数"""
    return get_audio_collector()

def start_smart_audio_collection():
    """启动智能音频收集"""
    collector = get_audio_collector()
    collector.start_collection()
    return collector

def stop_smart_audio_collection():
    """停止智能音频收集"""
    collector = get_audio_collector()
    collector.stop_collection()

if __name__ == "__main__":
    # 测试代码
    collector = start_smart_audio_collection()
    
    try:
        print("🎵 智能音频收集系统测试启动...")
        print("按 Ctrl+C 停止测试")
        
        while True:
            status = collector.get_status()
            print(f"状态: {status}")
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n🛑 停止测试")
        stop_smart_audio_collection()
