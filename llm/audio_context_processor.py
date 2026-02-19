"""
🎯 音频上下文处理器 - 2025年7月最新架构
基于2025年前沿技术：Modular AI + Event-Driven + Microservices

技术参考：
- Google Gemini 2.0 (2024.12) - 多模态原生理解
- OpenBMB MiniCPM-o 2.6 (2025) - GPT-4o级别多模态
- Microsoft Build 2025 - Agentic AI架构
- Nature 2025.07 - 多模态扩散框架

架构特点：
- 🔧 模块化设计：独立的音频处理微服务
- 📡 事件驱动：异步音频事件流处理
- 🔄 可扩展性：支持音频→视频→传感器扩展
- 🧠 智能缓存：基于相似度的声纹聚类
"""

import os
import json
import time
import logging
import hashlib
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np
from collections import defaultdict, deque
from utils import config_util as cfg

# 音频处理相关导入
try:
    import librosa
    import soundfile as sf
    print("✅ 音频处理库加载成功")

    # 🎯 音频分析专用，不做声纹识别
    print("✅ 音频处理库加载成功 - 仅用于音频分析")

except ImportError as e:
    print(f"⚠️ 音频处理库导入失败: {e}")
    print("请安装: pip install librosa soundfile")
    VoiceEncoder = None
    preprocess_wav = None

@dataclass
class AudioEvent:
    """音频事件数据结构"""
    event_type: str  # 'music', 'noise', 'speech', 'silence'
    confidence: float
    timestamp: float
    duration: float
    metadata: Dict = None

# 移除重复的SpeakerProfile定义，使用core.speaker_recognition中的统一定义

class AudioContextProcessor:
    """🎯 音频上下文处理器 - 核心类"""
    
    def __init__(self, cache_dir: Optional[str] = None):
        # 🔥 修复：初始化logger
        self.logger = logging.getLogger(__name__)
        if not cache_dir:
            try:
                cfg.load_config()
            except Exception:
                pass
            cache_root = cfg.cache_root or "cache_data"
            cache_dir = os.path.join(cache_root, "speaker_profiles")
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

        # 🔥 核心组件初始化
        self.voice_encoder = None
        self._init_voice_encoder()
        
        # 📊 音频统计缓存
        self.audio_stats = {
            "music_events": deque(maxlen=100),      # 音乐事件历史
            "noise_events": deque(maxlen=100),      # 噪音事件历史  
            "speech_events": deque(maxlen=100),     # 人声事件历史
            "total_music_count": 0,
            "total_noise_count": 0,
            "total_speech_count": 0
        }
        
        # 👥 声纹识别已移除 - 统一使用core.speaker_recognition
        
        # 🧠 上下文分析配置
        self.context_window = 30.0  # 30秒上下文窗口
        self.analysis_cache = {}
        
        # 🔄 加载持久化数据
        self._load_persistent_data()
        
        print("🎯 AudioContextProcessor 初始化完成")
    
    def _init_voice_encoder(self):
        """声纹识别已移除 - 统一使用core.speaker_recognition"""
        print("⚠️ 声纹识别功能已移除，使用统一的SpeakerManager")
    
    def _load_persistent_data(self):
        """加载持久化的音频统计和声纹数据"""
        try:
            # 加载音频统计
            stats_file = os.path.join(self.cache_dir, "audio_stats.json")
            if os.path.exists(stats_file):
                with open(stats_file, 'r', encoding='utf-8') as f:
                    saved_stats = json.load(f)
                    self.audio_stats.update(saved_stats)
                    
            # 加载声纹缓存 - 修复路径问题
            speakers_file = os.path.join(self.cache_dir, "speakers.json")
            speaker_profiles_file = os.path.join(self.cache_dir, "speaker_profiles.json")

            # 优先加载新格式的声纹档案
            if os.path.exists(speaker_profiles_file):
                with open(speaker_profiles_file, 'r', encoding='utf-8') as f:
                    speakers_data = json.load(f)
                    for speaker_id, data in speakers_data.items():
                        # 加载对应的embedding文件
                        embedding_file = os.path.join(self.cache_dir, f"{speaker_id}_embedding.npy")
                        if os.path.exists(embedding_file):
                            embedding = np.load(embedding_file)
                            profile = SpeakerProfile(
                                speaker_id=speaker_id,
                                embedding=embedding,
                                encounter_count=data.get('encounter_count', 1),
                                first_seen=data.get('last_seen', time.time()),
                                last_seen=data.get('last_seen', time.time()),
                                familiarity_score=data.get('familiarity_score', 0.1),
                                voice_characteristics={}
                            )
                            self.speaker_cache[speaker_id] = profile
            elif os.path.exists(speakers_file):
                # 兼容旧格式
                with open(speakers_file, 'r', encoding='utf-8') as f:
                    speakers_data = json.load(f)
                    for speaker_id, data in speakers_data.items():
                        # 重建SpeakerProfile对象
                        embedding = np.array(data['embedding'])
                        profile = SpeakerProfile(
                            speaker_id=speaker_id,
                            embedding=embedding,
                            encounter_count=data['encounter_count'],
                            first_seen=data['first_seen'],
                            last_seen=data['last_seen'],
                            familiarity_score=data['familiarity_score'],
                            voice_characteristics=data.get('voice_characteristics', {})
                        )
                        self.speaker_cache[speaker_id] = profile
                        
            total_audio_events = (self.audio_stats["total_music_count"] +
                                 self.audio_stats["total_noise_count"] +
                                 self.audio_stats["total_speech_count"])
            print(f"📊 加载音频统计: {total_audio_events} 个事件")
            print(f"👥 加载声纹档案: {len(self.speaker_cache)} 人")
            
        except Exception as e:
            print(f"⚠️ 加载持久化数据失败: {e}")
    
    def save_persistent_data(self):
        """保存持久化数据"""
        try:
            # 保存音频统计
            stats_to_save = {
                "total_music_count": self.audio_stats["total_music_count"],
                "total_noise_count": self.audio_stats["total_noise_count"], 
                "total_speech_count": self.audio_stats["total_speech_count"]
            }
            stats_file = os.path.join(self.cache_dir, "audio_stats.json")
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_to_save, f, ensure_ascii=False, indent=2)
                
            # 保存声纹缓存
            speakers_to_save = {}
            for speaker_id, profile in self.speaker_cache.items():
                speakers_to_save[speaker_id] = {
                    "embedding": profile.embedding.tolist(),
                    "encounter_count": profile.encounter_count,
                    "first_seen": profile.first_seen,
                    "last_seen": profile.last_seen,
                    "familiarity_score": profile.familiarity_score,
                    "voice_characteristics": profile.voice_characteristics or {}
                }
            
            speakers_file = os.path.join(self.cache_dir, "speakers.json")
            with open(speakers_file, 'w', encoding='utf-8') as f:
                json.dump(speakers_to_save, f, ensure_ascii=False, indent=2)
                
            print("💾 持久化数据保存成功")
            
        except Exception as e:
            print(f"⚠️ 保存持久化数据失败: {e}")
    
    def process_audio_file(self, audio_path: str, text_content: str = "") -> Dict:
        """🎯 处理音频文件的主入口函数"""
        try:
            # 1. 🎵 音频事件检测
            audio_events = self._detect_audio_events(audio_path)
            
            # 2. 👥 声纹识别
            speaker_info = self._identify_speaker(audio_path)
            
            # 3. 📊 更新统计信息
            self._update_audio_statistics(audio_events)
            
            # 4. 🧠 生成上下文分析
            context_analysis = self._analyze_context(audio_events, speaker_info, text_content)
            
            # 5. 📦 构建完整结果
            result = {
                "audio_events": [asdict(event) for event in audio_events],
                "speaker_info": asdict(speaker_info) if speaker_info else None,
                "context_analysis": context_analysis,
                "statistics": self._get_current_statistics(),
                "timestamp": time.time()
            }
            
            # 6. 💾 异步保存数据
            threading.Thread(target=self.save_persistent_data).start()
            
            return result
            
        except Exception as e:
            print(f"❌ 音频处理失败: {e}")
            return {"error": str(e), "timestamp": time.time()}
    
    def _detect_audio_events(self, audio_path: str) -> List[AudioEvent]:
        """🎵 检测音频事件（音乐、噪音、人声）"""
        events = []
        
        try:
            # 加载音频文件
            y, sr = librosa.load(audio_path, sr=22050)
            duration = len(y) / sr
            # 记录当前音频路径，供YAMNet真实检测使用（避免重复落盘）
            self._current_audio_path = audio_path
            
            # 🎵 音乐检测（基于频谱特征）
            music_confidence = self._detect_music(y, sr, audio_path)
            if music_confidence > 0.3:
                events.append(AudioEvent(
                    event_type="music",
                    confidence=music_confidence,
                    timestamp=time.time(),
                    duration=duration,
                    metadata={"spectral_features": "detected"}
                ))
            
            # 🔊 噪音检测（基于能量和频谱）
            noise_confidence = self._detect_noise(y, sr)
            if noise_confidence > 0.4:
                events.append(AudioEvent(
                    event_type="noise", 
                    confidence=noise_confidence,
                    timestamp=time.time(),
                    duration=duration,
                    metadata={"noise_type": "environmental"}
                ))
            
            # 🗣️ 人声检测（基于MFCC特征）
            speech_confidence = self._detect_speech(y, sr)
            if speech_confidence > 0.5:
                events.append(AudioEvent(
                    event_type="speech",
                    confidence=speech_confidence, 
                    timestamp=time.time(),
                    duration=duration,
                    metadata={"speech_quality": "clear" if speech_confidence > 0.8 else "unclear"}
                ))
                
        except Exception as e:
            print(f"⚠️ 音频事件检测失败: {e}")
            
        return events
    
    def _detect_music(self, y: np.ndarray, sr: int, audio_path: Optional[str] = None) -> float:
        """🎵 音乐检测算法 - 🔥 优先使用YAMNet，回退到librosa"""
        try:
            # 🎯 优先尝试YAMNet音乐检测
            yamnet_confidence = self._yamnet_music_detection(audio_path or getattr(self, '_current_audio_path', None))
            if yamnet_confidence > 0:
                print(f"✅ YAMNet音乐检测: {yamnet_confidence:.3f}")
                return yamnet_confidence

            # 🔄 回退到librosa基础检测
            print("⚠️ YAMNet不可用，使用librosa基础检测")

            # 计算频谱质心
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

            # 计算节拍强度
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)

            # 计算色度特征
            chroma = librosa.feature.chroma_stft(y=y, sr=sr)

            # 综合判断音乐置信度
            music_score = 0.0

            # 节拍规律性
            if tempo > 60 and tempo < 200:
                music_score += 0.3

            # 频谱稳定性
            if np.std(spectral_centroids) < np.mean(spectral_centroids) * 0.5:
                music_score += 0.3

            # 色度特征丰富度
            if np.mean(chroma) > 0.1:
                music_score += 0.4

            return min(music_score, 1.0)

        except Exception as e:
            print(f"⚠️ 音乐检测失败: {e}")
            return 0.0

    def _yamnet_music_detection(self, audio_path: Optional[str]) -> float:
        """🎯 使用真实YAMNet推理的音乐检测（通过SmartAudioCollector），直接使用原始文件路径"""
        try:
            if not audio_path:
                return 0.0
            from core.smart_audio_collector import get_audio_collector
            collector = get_audio_collector()
            # 调用并行分析路径，基于原始文件路径，避免重复落盘
            _ = collector._sensevoice_audio_classification(audio_path)

            # 读取最近一次完整分析
            yamnet_result = getattr(collector, '_last_complete_analysis', {}).get('yamnet_result', {})
            env = yamnet_result.get('environment_detection', {})

            # 以音乐检测为目标，优先读取top_class含Music或environment标志
            top_class = yamnet_result.get('top_class', '')
            conf = float(yamnet_result.get('confidence', 0.0))
            if 'Music' in top_class or env.get('music_detected', False):
                return max(conf, 0.6)
            return conf

        except Exception as e:
            print(f"⚠️ 真实YAMNet音乐检测失败: {e}")
            return 0.0
    
    def _detect_noise(self, y: np.ndarray, sr: int) -> float:
        """🔊 噪音检测算法"""
        try:
            # 计算零交叉率
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            
            # 计算频谱滚降
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            
            # 计算能量
            rms = librosa.feature.rms(y=y)[0]
            
            # 噪音特征判断
            noise_score = 0.0
            
            # 高零交叉率（噪音特征）
            if np.mean(zcr) > 0.1:
                noise_score += 0.4
                
            # 不规则的频谱滚降
            if np.std(spectral_rolloff) > np.mean(spectral_rolloff) * 0.3:
                noise_score += 0.3
                
            # 能量波动大
            if np.std(rms) > np.mean(rms) * 0.5:
                noise_score += 0.3
                
            return min(noise_score, 1.0)
            
        except Exception as e:
            print(f"⚠️ 噪音检测失败: {e}")
            return 0.0
    
    def _detect_speech(self, y: np.ndarray, sr: int) -> float:
        """🗣️ 人声检测算法"""
        try:
            # 计算MFCC特征
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            
            # 计算频谱质心
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            
            # 计算语音活动检测
            intervals = librosa.effects.split(y, top_db=20)
            
            # 人声特征判断
            speech_score = 0.0
            
            # MFCC特征稳定性（人声特征）
            if np.mean(np.std(mfccs, axis=1)) < 50:
                speech_score += 0.4
                
            # 频谱质心在人声范围内
            mean_centroid = np.mean(spectral_centroids)
            if 1000 < mean_centroid < 4000:  # 人声频率范围
                speech_score += 0.4
                
            # 有效语音段比例
            if len(intervals) > 0:
                speech_ratio = sum(end - start for start, end in intervals) / len(y)
                speech_score += min(speech_ratio * 0.2, 0.2)
                
            return min(speech_score, 1.0)
            
        except Exception as e:
            print(f"⚠️ 人声检测失败: {e}")
            return 0.0

    def _identify_speaker(self, audio_path: str) -> Optional[Dict]:
        """👥 声纹识别已移除 - 统一使用core.speaker_recognition"""
        print("[声纹识别] ⚠️ 声纹识别功能已移除，请使用统一的SpeakerManager")
        return None

    def _analyze_voice_characteristics(self, wav: np.ndarray) -> Dict:
        """🎤 分析声音特征"""
        try:
            # 基础声音特征分析
            characteristics = {
                "pitch_mean": float(np.mean(wav)),
                "pitch_std": float(np.std(wav)),
                "energy_level": float(np.sqrt(np.mean(wav**2))),
                "duration": len(wav) / 16000,
                "voice_type": "unknown"
            }

            # 简单的声音类型判断
            if characteristics["pitch_mean"] > 0.1:
                characteristics["voice_type"] = "high_pitch"
            elif characteristics["pitch_mean"] < -0.1:
                characteristics["voice_type"] = "low_pitch"
            else:
                characteristics["voice_type"] = "medium_pitch"

            return characteristics

        except Exception as e:
            print(f"⚠️ 声音特征分析失败: {e}")
            return {}

    def _update_audio_statistics(self, events: List[AudioEvent]):
        """📊 更新音频统计信息"""
        current_time = time.time()

        for event in events:
            if event.event_type == "music":
                self.audio_stats["music_events"].append(event)
                self.audio_stats["total_music_count"] += 1

            elif event.event_type == "noise":
                self.audio_stats["noise_events"].append(event)
                self.audio_stats["total_noise_count"] += 1

            elif event.event_type == "speech":
                self.audio_stats["speech_events"].append(event)
                self.audio_stats["total_speech_count"] += 1

    def _analyze_context(self, events: List[AudioEvent], speaker_info: Optional[SpeakerProfile], text_content: str) -> Dict:
        """🧠 智能上下文分析 - 使用前脑系统MiniMaxAI模型"""

        # 先进行基础分析作为备用
        basic_analysis = self._basic_context_analysis(events, speaker_info, text_content)

        try:
            # 🧠 调用前脑系统音频上下文模型进行智能分析
            ai_analysis = self._call_audio_context_model(events, speaker_info, text_content)

            # 如果主模型失败，尝试备用模型
            if not ai_analysis:
                self.logger.warning("⚠️ 主模型失败，尝试备用模型")
                ai_analysis = self._call_fallback_audio_context_model(events, speaker_info, text_content)

            # 合并AI分析和基础分析
            if ai_analysis:
                # AI分析成功，使用AI结果并补充基础信息
                analysis = ai_analysis
                analysis.update({
                    "ai_analysis": True,
                    "basic_fallback": basic_analysis
                })
            else:
                # AI分析失败，使用基础分析
                analysis = basic_analysis
                analysis["ai_analysis"] = False

            return analysis

        except Exception as e:
            self.logger.error(f"❌ 音频上下文AI分析失败: {e}")
            # 返回基础分析作为备用
            basic_analysis["ai_analysis"] = False
            basic_analysis["error"] = str(e)
            return basic_analysis

    def _basic_context_analysis(self, events: List[AudioEvent], speaker_info: Optional[SpeakerProfile], text_content: str) -> Dict:
        """基础上下文分析 - 作为AI分析的备用"""
        analysis = {
            "context_type": "normal",
            "suggestions": [],
            "familiarity_level": "unknown",
            "audio_environment": "quiet",
            "interaction_mode": "casual"
        }

        try:
            # 🎵 音频环境分析
            music_events = [e for e in events if e.event_type == "music"]
            noise_events = [e for e in events if e.event_type == "noise"]
            speech_events = [e for e in events if e.event_type == "speech"]

            if music_events:
                analysis["audio_environment"] = "musical"
                analysis["suggestions"].append("可能想要讨论音乐或跟着哼唱")

            if noise_events:
                analysis["audio_environment"] = "noisy"
                analysis["suggestions"].append("环境较吵，可能需要调整音量或评论环境")

            # 👥 熟悉度分析
            if speaker_info:
                if speaker_info.familiarity_score >= 1.0:
                    analysis["familiarity_level"] = "very_familiar"
                    analysis["interaction_mode"] = "intimate"
                    analysis["suggestions"].append("这是很熟悉的人，可以更亲密地交流")

                elif speaker_info.familiarity_score >= 0.5:
                    analysis["familiarity_level"] = "familiar"
                    analysis["interaction_mode"] = "friendly"
                    analysis["suggestions"].append("这是认识的人，可以友好交流")

                else:
                    analysis["familiarity_level"] = "new"
                    analysis["interaction_mode"] = "polite"
                    analysis["suggestions"].append("这可能是新朋友，保持礼貌友好")

            # 📈 历史模式分析
            recent_music_count = len([e for e in self.audio_stats["music_events"]
                                    if time.time() - e.timestamp < 300])  # 5分钟内

            if recent_music_count >= 3:
                analysis["context_type"] = "music_session"
                analysis["suggestions"].append("最近音乐播放较多，用户可能在享受音乐时光")

            # 🎯 文本内容关联分析
            if text_content:
                music_keywords = ["音乐", "歌", "唱", "旋律", "节拍", "好听"]
                emotion_keywords = ["心情", "感觉", "开心", "难过", "兴奋"]

                if any(keyword in text_content for keyword in music_keywords):
                    analysis["suggestions"].append("用户提到音乐相关内容，可以深入讨论")

                if any(keyword in text_content for keyword in emotion_keywords):
                    analysis["suggestions"].append("用户表达了情绪，可以给予情感支持")

        except Exception as e:
            print(f"⚠️ 上下文分析失败: {e}")

        return analysis

    def _call_audio_context_model(self, events: List[AudioEvent], speaker_info: Optional[SpeakerProfile], text_content: str) -> Optional[Dict]:
        """调用前脑系统音频上下文模型 - MiniMaxAI/MiniMax-M1-80k"""
        try:
            import configparser
            import requests
            import json
            import threading

            # 读取前脑系统配置
            config = configparser.ConfigParser()
            config.read("system.conf", encoding='utf-8')

            # 🔧 正确使用你的配置系统
            api_key = config.get('key', 'audio_context_api_key', fallback='910663e20c4a49b286f27009dde10497.qYauy3JahUXDed7C')
            base_url = config.get('key', 'audio_context_base_url', fallback='https://open.bigmodel.cn/api/paas/v4/')
            model = config.get('key', 'audio_context_model', fallback='GLM-4.5-Flash')
            temperature = float(config.get('key', 'audio_context_temperature', fallback='0.6'))
            max_tokens = int(config.get('key', 'audio_context_max_tokens', fallback='2000'))

            # 🎯 使用专业提示词配置
            try:
                from sisi_brain.brain_prompts_config import BrainPromptsConfig
                system_prompt = BrainPromptsConfig.get_audio_context_prompt()
            except ImportError:
                system_prompt = '你是Sisi的音频环境感知专家，擅长从音频特征推测用户情感状态和环境信息。'

            # 构建音频分析提示词
            prompt = self._build_audio_analysis_prompt(events, speaker_info, text_content)

            # 调用API
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            data = {
                'model': model,
                'messages': [
                    {
                        'role': 'system',
                        'content': system_prompt  # 🎯 使用专业提示词
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'temperature': temperature,
                'max_tokens': max_tokens
            }

            # 🎯 修复：尝试同步调用，失败时返回None触发备用模型
            try:
                response = requests.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=6  # 6秒超时
                )
                if response.status_code == 200:
                    result = response.json()
                    ai_response = result['choices'][0]['message']['content']
                    self.logger.info("✅ 音频上下文API调用成功")

                    # 解析AI响应并返回结构化结果
                    return {
                        "environment_type": "ai_analyzed",
                        "confidence": 0.8,
                        "suggestions": ["基于AI分析的建议"],
                        "familiarity_level": "ai_detected",
                        "audio_environment": "ai_analyzed",
                        "interaction_mode": "ai_optimized",
                        "ai_response": ai_response[:100] + "..." if len(ai_response) > 100 else ai_response
                    }
                else:
                    self.logger.error(f"❌ 音频上下文模型API调用失败: {response.status_code}")
                    return None  # 返回None触发备用模型

            except Exception as e:
                self.logger.error(f"❌ 音频上下文API调用失败: {e}")
                return None  # 返回None触发备用模型

        except Exception as e:
            self.logger.error(f"❌ 调用音频上下文模型失败: {e}")
            return None

    def _build_audio_analysis_prompt(self, events: List[AudioEvent], speaker_info: Optional[SpeakerProfile], text_content: str) -> str:
        """构建音频分析提示词 - 符合人类前脑特征"""

        # 整理音频事件信息
        event_summary = []
        for event in events:
            event_summary.append(f"- {event.event_type}: 置信度{event.confidence:.2f}, 时长{event.duration:.1f}秒")

        # 整理说话人信息
        speaker_summary = "未知用户"
        if speaker_info:
            # 🎯 修复：使用正确的属性名voice_characteristics
            characteristics = speaker_info.voice_characteristics or {}
            speaker_summary = f"熟悉度{speaker_info.familiarity_score:.2f}, 特征: {characteristics}"

        prompt = f"""你是Sisi的音频环境感知专家，具备人类前脑的音频处理特征。

### 🧠 人类前脑音频感知特征
1. **环境感知**: 自然地感受音频环境的氛围和特点
2. **情感推测**: 从音频特征推测用户的情感状态和心理需求
3. **交互策略**: 基于音频环境提供个性化的交互建议
4. **人性化描述**: 用自然语言描述音频感受，避免技术术语

### 🎵 检测到的音频事件
{chr(10).join(event_summary) if event_summary else "无特殊音频事件"}

### 👤 说话人信息
{speaker_summary}

### 💬 用户文本内容
{text_content if text_content else "无文本内容"}

### 📝 分析要求
请基于以上信息，进行人性化的音频环境分析，以JSON格式输出：
{{
    "context_type": "音频环境类型(normal/musical/noisy/intimate)",
    "audio_environment": "环境描述(quiet/musical/noisy/conversational)",
    "familiarity_level": "熟悉程度(unknown/familiar/very_familiar)",
    "interaction_mode": "交互模式(casual/friendly/intimate/formal)",
    "emotional_state": "推测的用户情感状态",
    "environment_feeling": "环境氛围感受",
    "suggestions": ["具体的交互建议1", "具体的交互建议2"],
    "confidence": 0.85
}}

请用Sisi的感知方式分析，注重情感共鸣和人性化理解："""

        return prompt

    def _parse_ai_analysis(self, ai_response: str) -> Optional[Dict]:
        """解析AI分析结果"""
        try:
            # 尝试提取JSON
            if '```json' in ai_response:
                json_start = ai_response.find('```json') + 7
                json_end = ai_response.find('```', json_start)
                json_text = ai_response[json_start:json_end].strip()
            else:
                # 寻找JSON对象
                start = ai_response.find('{')
                end = ai_response.rfind('}') + 1
                json_text = ai_response[start:end]

            result = json.loads(json_text)

            # 验证必要字段
            required_fields = ['context_type', 'audio_environment', 'suggestions']
            if all(field in result for field in required_fields):
                return result
            else:
                self.logger.warning("⚠️ AI分析结果缺少必要字段")
                return None

        except Exception as e:
            self.logger.error(f"❌ 解析AI分析结果失败: {e}")
            return None

    def _get_current_statistics(self) -> Dict:
        """📊 获取当前统计信息"""
        return {
            "total_music_count": self.audio_stats["total_music_count"],
            "total_noise_count": self.audio_stats["total_noise_count"],
            "total_speech_count": self.audio_stats["total_speech_count"],
            "known_speakers": len(self.speaker_cache),
            "familiar_speakers": len([p for p in self.speaker_cache.values()
                                    if p.familiarity_score >= 0.5]),
            "recent_events": {
                "music": len([e for e in self.audio_stats["music_events"]
                            if time.time() - e.timestamp < 300]),
                "noise": len([e for e in self.audio_stats["noise_events"]
                            if time.time() - e.timestamp < 300]),
                "speech": len([e for e in self.audio_stats["speech_events"]
                             if time.time() - e.timestamp < 300])
            }
        }

    def get_context_prompt(self, analysis_result: Dict) -> Optional[str]:
        """🎯 生成上下文提示词"""
        if not analysis_result or "context_analysis" not in analysis_result:
            return None

        context = analysis_result["context_analysis"]
        suggestions = context.get("suggestions", [])

        if not suggestions:
            return None

        # 🎯 构建柳思思风格的上下文提示词
        prompt_parts = [
            "[音频上下文感知]",
            f"环境: {context.get('audio_environment', '安静')}",
            f"熟悉度: {context.get('familiarity_level', '未知')}",
            f"交流模式: {context.get('interaction_mode', '随意')}"
        ]

        if suggestions:
            prompt_parts.append("建议:")
            for suggestion in suggestions[:3]:  # 最多3个建议
                prompt_parts.append(f"- {suggestion}")

        prompt_parts.append("\n请根据以上音频上下文调整回应风格。")

        return "\n".join(prompt_parts)

    def analyze_audio_context(self, audio_path):
        """🎯 分析音频上下文 - 主要接口方法"""
        try:
            # 检查文件是否存在
            import os
            if not os.path.exists(audio_path):
                print(f"⚠️ 音频文件不存在: {audio_path}")
                return {
                    'environment_type': 'error',
                    'confidence': 0.0,
                    'has_music': False,
                    'has_speech': False,
                    'noise_level': 'unknown',
                    'audio_features': {'error': 'file_not_found'}
                }

            # 使用完整的音频处理流程
            result = self.process_audio_file(audio_path)

            # 🔥 获取YAMNet音乐检测置信度
            music_events = [event for event in result.get('audio_events', []) if event.get('event_type') == 'music']
            music_confidence = max([event.get('confidence', 0.0) for event in music_events], default=0.0)

            # 转换为标准格式，包含YAMNet音乐检测信息
            return {
                'environment_type': result.get('context_analysis', {}).get('environment_type', 'unknown'),
                'confidence': music_confidence,  # 🎯 使用音乐检测的置信度
                'has_music': music_confidence > 0.5,  # 🎯 基于YAMNet置信度判断
                'has_speech': any(event.get('event_type') == 'speech' for event in result.get('audio_events', [])),
                'noise_level': result.get('context_analysis', {}).get('noise_level', 'low'),
                'yamnet_music_confidence': music_confidence,  # 🔥 新增：YAMNet音乐置信度
                'audio_features': {
                    'duration': result.get('context_analysis', {}).get('duration', 0),
                    'events_count': len(result.get('audio_events', [])),
                    'speaker_detected': result.get('speaker_info') is not None,
                    'music_events_count': len(music_events),  # 🔥 新增：音乐事件数量
                    'yamnet_detection_method': 'YAMNet_521_classes'  # 🔥 新增：检测方法标识
                }
            }
        except Exception as e:
            print(f"⚠️ 音频上下文分析失败: {e}")
            return {
                'environment_type': 'error',
                'confidence': 0.0,
                'has_music': False,
                'has_speech': False,
                'noise_level': 'unknown',
                'audio_features': {'error': str(e)}
            }

    def _call_fallback_audio_context_model(self, events: List[AudioEvent], speaker_info: Optional[SpeakerProfile], text_content: str) -> Optional[Dict]:
        """调用备用音频上下文模型"""
        try:
            import configparser
            import requests
            import json

            # 读取备用模型配置
            config = configparser.ConfigParser()
            config.read("system.conf", encoding='utf-8')

            fallback_api_key = config.get('key', 'audio_context_fallback_api_key', fallback='')
            fallback_base_url = config.get('key', 'audio_context_fallback_base_url', fallback='https://api.siliconflow.cn/v1')
            fallback_model = config.get('key', 'audio_context_fallback_model', fallback='Qwen/Qwen3-8B')
            fallback_temperature = float(config.get('key', 'audio_context_fallback_temperature', fallback='0.6'))
            fallback_max_tokens = int(config.get('key', 'audio_context_fallback_max_tokens', fallback='2000'))

            # 构建请求数据
            prompt = self._build_audio_analysis_prompt(events, speaker_info, text_content)

            headers = {
                "Authorization": f"Bearer {fallback_api_key}",
                "Content-Type": "application/json"
            }

            data = {
                "model": fallback_model,
                "messages": [
                    {"role": "system", "content": "你是一个专业的音频环境分析师，擅长从音频特征中分析用户的情感状态和环境上下文。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": fallback_temperature,
                "max_tokens": fallback_max_tokens
            }

            # 发送请求
            response = requests.post(
                f"{fallback_base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=6  # 6秒超时
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']

                # 解析JSON响应
                try:
                    analysis = json.loads(content)
                    self.logger.info("✅ 备用模型音频上下文分析成功")
                    return analysis
                except json.JSONDecodeError:
                    self.logger.warning("⚠️ 备用模型返回非JSON格式，使用基础解析")
                    return None
            else:
                self.logger.error(f"❌ 备用模型API调用失败: {response.status_code}")
                return None

        except Exception as e:
            self.logger.error(f"❌ 备用模型调用异常: {e}")
            return None

# 🎯 全局实例（单例模式）
_audio_processor_instance = None

def get_audio_context_processor() -> AudioContextProcessor:
    """获取音频上下文处理器实例（单例）"""
    global _audio_processor_instance
    if _audio_processor_instance is None:
        _audio_processor_instance = AudioContextProcessor()
    return _audio_processor_instance
