import os
import json
import requests
import re
import time
import asyncio
import threading
from utils import util, config_util as cfg
from utils.pc_audio_stream import get_pc_stream

# 导入统一的音频工具
from utils.stream_util import AudioManagerUtil

def _write_pcm_to_pc_stream(pcm_data, sample_rate, channels, sample_width, frames_per_buffer=1024):
    if not pcm_data:
        return
    get_pc_stream().write_pcm(
        pcm_data,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        frames_per_buffer=frames_per_buffer,
    )

# 流式OPUS TTS引擎（可选，静默降级）
try:
    from .streaming_opus_tts import StreamingOpusTTS
    STREAMING_OPUS_AVAILABLE = True
except ImportError:
    STREAMING_OPUS_AVAILABLE = False

class SiliconFlowTTS:
    def __init__(self):
        self.api_key = cfg.siliconflow_api_key
        self.model = cfg.siliconflow_model
        self.voice_type = getattr(cfg, 'siliconflow_voice_type', None) or getattr(cfg, 'sisi_voice_uri', None)
        base_url = getattr(cfg, 'siliconflow_base_url', None)
        if base_url is None:
            base_url = "https://api.siliconflow.cn/v1"
        else:
            base_url = str(base_url).strip()
            if not base_url or base_url.lower() in ("none", "null", "nil"):
                base_url = "https://api.siliconflow.cn/v1"
        self.base_url = base_url
        self.__history_data = []

        # 🚀 初始化流式OPUS TTS引擎
        self.streaming_opus_tts = None
        if STREAMING_OPUS_AVAILABLE and self.api_key and self.voice_type:
            try:
                self.streaming_opus_tts = StreamingOpusTTS(
                    api_key=self.api_key,
                    voice_uri=self.voice_type,
                    debug=False
                )
                util.log(1, "[TTS] 流式OPUS TTS引擎初始化成功")
            except Exception as e:
                util.log(2, f"[TTS] 流式OPUS TTS引擎初始化失败: {e}")
                self.streaming_opus_tts = None

    def connect(self):
        """连接服务"""
        if not self.api_key or not self.model or not self.voice_type:
            util.log(1, "[x] liusisi配置缺失，请检查system.conf中的siliconflow相关配置")
            return False
        util.log(1, "liusisi已连接")
        return True

    def _check_esp32_connection(self) -> bool:
        """检查ESP32设备是否连接"""
        try:
            # 检查ESP32是否连接
            import sys
            esp32_connected = False

            if 'esp32_liusisi.esp32_bridge' in sys.modules:
                esp32_bridge = sys.modules['esp32_liusisi.esp32_bridge']
                adapter = getattr(esp32_bridge, 'adapter_instance', None)

                if adapter and hasattr(adapter, 'clients') and adapter.clients:
                    # 检查是否有连接的设备
                    connected_devices = 0
                    for client_id in adapter.clients:
                        websocket = adapter.clients.get(client_id)
                        if websocket and not websocket.closed:
                            connected_devices += 1

                    if connected_devices > 0:
                        esp32_connected = True
                        util.log(1, f"[TTS] 检测到{connected_devices}个ESP32设备连接，使用并行模式")
                    else:
                        util.log(1, f"[TTS] ESP32适配器无有效设备连接，使用PC模式")
                else:
                    util.log(1, f"[TTS] ESP32适配器无设备连接，使用PC模式")
            else:
                util.log(1, f"[TTS] ESP32桥接模块未加载，使用PC模式")

            return esp32_connected

        except Exception as e:
            util.log(2, f"[TTS] 检查ESP32连接失败: {e}")
            return False

    # 🔥 删除_try_direct_esp32_streaming方法，避免重复播放
    # 所有音频统一通过ESP32适配器处理

    # 🔥 删除_stream_wav_to_esp32_direct方法，避免重复播放

    # 🔥 删除_send_opus_to_esp32_direct方法，避免重复播放

    def _send_music_file_direct(self, music_file_path: str) -> bool:
        """直发音乐文件到ESP32设备"""
        try:
            util.log(1, f"[TTS] 🎵 开始直发音乐文件: {music_file_path}")

            # 获取ESP32适配器
            import importlib.util
            import os
            adapter_path = os.path.join(os.path.dirname(__file__), '..', 'esp32_liusisi', 'sisi.adapter.py')
            spec = importlib.util.spec_from_file_location("sisi_adapter", adapter_path)
            sisi_adapter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sisi_adapter)
            adapter = sisi_adapter.get_adapter_instance()

            if not adapter or not adapter.clients:
                util.log(2, f"[TTS] 音乐直发：无可用ESP32设备")
                return False

            # 转换音乐文件为OPUS帧
            try:
                from esp32_liusisi.opus_helper import OpusConvertor
                # 🔥 修复：使用单例模式，避免重复初始化编码器
                if not hasattr(self, '_opus_converter'):
                    self._opus_converter = OpusConvertor()
                opus_helper = self._opus_converter
                opus_frames, duration = opus_helper.audio_to_opus_frames(music_file_path)
            except ImportError:
                util.log(2, f"[TTS] OpusHelper导入失败")
                return False

            if not opus_frames:
                util.log(2, f"[TTS] 音乐文件OPUS转换失败")
                return False

            util.log(1, f"[TTS] 音乐文件OPUS转换完成: {len(opus_frames)}帧")

            # 直发到ESP32设备
            music_name = os.path.splitext(os.path.basename(music_file_path))[0]
            success = self._send_opus_to_esp32_direct(opus_frames, f"🎵 {music_name}", adapter)

            if success:
                util.log(1, f"[TTS] ✅ 音乐文件直发成功")
                return True
            else:
                util.log(2, f"[TTS] ❌ 音乐文件直发失败")
                return False

        except Exception as e:
            util.log(2, f"[TTS] 音乐文件直发异常: {e}")
            return False

    def _get_esp32_adapter(self):
        """获取ESP32适配器实例"""
        try:
            # 方法1：从sisi_booter模块获取
            try:
                from core import sisi_booter
                if hasattr(sisi_booter, 'esp32_adapter') and sisi_booter.esp32_adapter:
                    adapter = sisi_booter.esp32_adapter
                    if hasattr(adapter, 'clients'):
                        util.log(1, f"[TTS] 从sisi_booter获取到ESP32适配器")
                        return adapter
            except Exception as e:
                util.log(2, f"[TTS] 从sisi_booter获取适配器失败: {e}")

            # 方法2：从已加载的sisi_adapter模块获取
            try:
                import sys
                if 'sisi_adapter' in sys.modules:
                    sisi_adapter_module = sys.modules['sisi_adapter']
                    if hasattr(sisi_adapter_module, 'get_adapter_instance'):
                        adapter = sisi_adapter_module.get_adapter_instance()
                        if adapter and hasattr(adapter, 'clients'):
                            util.log(1, f"[TTS] 从sisi_adapter模块获取到ESP32适配器")
                            return adapter
                    elif hasattr(sisi_adapter_module, '_ADAPTER_INSTANCE') and sisi_adapter_module._ADAPTER_INSTANCE:
                        adapter = sisi_adapter_module._ADAPTER_INSTANCE
                        if hasattr(adapter, 'clients'):
                            util.log(1, f"[TTS] 从sisi_adapter全局实例获取到ESP32适配器")
                            return adapter
            except Exception as e:
                util.log(2, f"[TTS] 从sisi_adapter模块获取适配器失败: {e}")

            # 方法3：从已加载的模块中查找适配器实例
            try:
                import sys
                for module_name, module in sys.modules.items():
                    if 'sisi' in module_name.lower() and 'adapter' in module_name.lower():
                        if hasattr(module, '_ADAPTER_INSTANCE') and module._ADAPTER_INSTANCE:
                            adapter = module._ADAPTER_INSTANCE
                            if hasattr(adapter, 'clients'):
                                util.log(1, f"[TTS] 从模块 {module_name} 获取到ESP32适配器")
                                return adapter
            except Exception as e:
                util.log(2, f"[TTS] 从已加载模块获取适配器失败: {e}")

            util.log(2, f"[TTS] 未找到ESP32适配器实例")
            return None
        except Exception as e:
            util.log(2, f"[TTS] 获取ESP32适配器异常: {e}")
            return None

    def _stream_to_esp32_devices(self, params, esp32_adapter):
        """设备优先流式播放：实时发送TTS流到ESP32设备"""
        try:
            util.log(1, f"[TTS] 🚀 开始设备优先流式播放")

            # 发送TTS请求
            response = self.__send_request("audio/speech", params, timeout=30)
            if not response:
                util.log(2, f"[TTS] 流式TTS请求失败")
                return None

            # 🔥 关键修复：使用流式PCM编码，保持编码器状态
            # 重置编码器状态以确保新会话干净
            opus_helper.reset_encoder()

            # 🔥 设备优先流式播放：边接收边转换边发送
            util.log(1, f"[TTS] 🚀 开始设备优先流式播放（持久编码器模式）...")

            # 通知设备开始播放
            self._notify_devices_tts_start(esp32_adapter)

            try:
                # 收集所有PCM数据
                complete_pcm = bytearray()
                chunk_count = 0
                sent_frames = []

                # 流式接收并实时处理
                for chunk in response.iter_content(chunk_size=3200):  # 精确匹配100ms PCM数据
                    if chunk:
                        chunk_count += 1

                        # 🔥 关键：直接处理PCM数据流，保持编码器连续性
                        # 假设siliconflow返回的是16kHz PCM数据
                        pcm_data = chunk

                        # 如果是WAV格式，需要跳过44字节头部（只在第一个chunk）
                        if chunk_count == 1 and len(chunk) > 44:
                            # 检查WAV头部标志
                            if chunk[:4] == b'RIFF' and chunk[8:12] == b'WAVE':
                                util.log(1, f"[TTS] 检测到WAV头部，跳过44字节")
                                pcm_data = chunk[44:]
                            else:
                                pcm_data = chunk

                        # 使用流式编码（保持编码器状态）
                        opus_frames = opus_helper.encode_pcm_stream(pcm_data, end_of_stream=False)

                        # 立即发送新生成的OPUS帧
                        if opus_frames:
                            self._send_opus_frames_async(opus_frames, esp32_adapter)
                            sent_frames.extend(opus_frames)
                            util.log(1, f"[TTS] 实时发送 {len(opus_frames)} OPUS帧 (chunk #{chunk_count})")

                        # 累积PCM数据用于保存文件
                        complete_pcm.extend(pcm_data)

                # 处理最后的剩余数据
                util.log(1, f"[TTS] 流式接收完成，总计 {chunk_count} 个chunk，{len(complete_pcm)} 字节PCM")

                # 刷新编码器缓冲区，处理剩余数据
                final_frames = opus_helper.encode_pcm_stream(b'', end_of_stream=True)
                if final_frames:
                    self._send_opus_frames_async(final_frames, esp32_adapter)
                    sent_frames.extend(final_frames)
                    util.log(1, f"[TTS] 发送最后 {len(final_frames)} OPUS帧")

                # 通知设备播放结束
                self._notify_devices_tts_stop(esp32_adapter)

                # 保存完整音频文件（可选）
                if complete_pcm:
                    import wave
                    final_wav_path = os.path.join("samples", f"output_{int(time.time())}.wav")
                    with wave.open(final_wav_path, 'wb') as wav_file:
                        wav_file.setnchannels(1)  # 单声道
                        wav_file.setsampwidth(2)  # 16bit
                        wav_file.setframerate(16000)  # 16000Hz
                        wav_file.writeframes(bytes(complete_pcm))

                    util.log(1, f"[TTS] ✅ 流式播放完成: 总计 {len(sent_frames)} 帧, 文件保存到: {final_wav_path}")
                    return final_wav_path
                else:
                    util.log(1, f"[TTS] ✅ 流式播放完成: 总计 {len(sent_frames)} 帧")
                    return "STREAMING_COMPLETED"

            except Exception as stream_error:
                util.log(2, f"[TTS] 流式处理异常: {stream_error}")
                # 通知设备停止播放
                self._notify_devices_tts_stop(esp32_adapter)
                return None

        except Exception as e:
            util.log(2, f"[TTS] 设备优先流式播放异常: {e}")
            return None

    def _send_opus_frames_async(self, opus_frames, esp32_adapter):
        """统一通路：不再直接写socket，交由AudioOutputManager/适配器处理"""
        try:
            # 将帧交给音频管理器，由适配器的 data_callback 统一入队发送
            from esp32_liusisi.sisi_audio_output import AudioOutputManager
            audio_manager = AudioOutputManager.get_instance()
            if not audio_manager:
                util.log(2, f"[TTS] 未找到音频输出管理器实例，跳过直发")
                return
            # 合并为连续PCM转发由现有流式路径处理；此处不再单独直发OPUS帧
            util.log(1, f"[TTS] 统一通路已启用：跳过直发OPUS帧，交由适配器发送")
        except Exception as e:
            util.log(2, f"[TTS] 统一通路转交失败: {e}")

    def _notify_devices_tts_start(self, esp32_adapter):
        """统一通路：开始/停止控制交由适配器自身，不在TTS层直发"""
        util.log(1, "[TTS] 统一通路：跳过TTS start直发，由适配器统一控制")



    def _notify_devices_tts_stop(self, esp32_adapter):
        """统一通路：开始/停止控制交由适配器自身，不在TTS层直发"""
        util.log(1, "[TTS] 统一通路：跳过TTS stop直发，由适配器统一控制")

    def _real_streaming_playback(self, params, esp32_adapter):
        """🔥 真正流式播放：直接转发WAV流到音频管理器"""
        try:
            util.log(1, f"[TTS] 🚀 开始真正流式播放（完整转发）")

            # 使用WAV格式
            stream_params = params.copy()
            stream_params['response_format'] = 'wav'
            stream_params['sample_rate'] = 16000  # 改为16kHz采样率，与设备端配置保持一致

            # 发送流式请求
            response = self.__send_request("audio/speech", stream_params, timeout=30)
            if not response:
                util.log(2, f"[TTS] 流式请求失败")
                return None

            # 获取音频管理器
            audio_manager = None
            try:
                from esp32_liusisi.sisi_audio_output import AudioOutputManager
                audio_manager = AudioOutputManager.get_instance()
                if not audio_manager:
                    util.log(2, f"[TTS] 未找到音频输出管理器实例")
                    return None
            except Exception as e:
                util.log(2, f"[TTS] 获取音频管理器失败: {e}")
                return None

            # 核心修复：直接转发所有数据，让音频管理器处理
            priority = 5
            chunk_count = 0
            total_bytes = 0
            wav_header_processed = False  # 标记是否已处理WAV头部
            header_buffer = bytearray()  # 用于累积头部数据

            util.log(1, f"[TTS] 🌊 开始转发WAV流")

            # 改进：使用更小的块大小以提高实时性
            for network_chunk in response.iter_content(chunk_size=1024):  # 改为1024字节块大小
                if not network_chunk:
                    continue

                chunk_count += 1
                total_bytes += len(network_chunk)

                # 🔥 修复：正确处理WAV数据流
                if not wav_header_processed:
                    # 累积数据以检测WAV头部
                    header_buffer.extend(network_chunk)
                    
                    # 检查是否有完整的WAV头部（至少44字节）
                    if len(header_buffer) >= 44:
                        # 检查是否包含WAV头部（RIFF标记）
                        if header_buffer[:4] == b'RIFF' and header_buffer[8:12] == b'WAVE':
                            # 找到WAV头部，跳过44字节
                            pcm_data = header_buffer[44:]
                            wav_header_processed = True
                            util.log(1, f"[TTS] 检测到WAV头部，已跳过44字节头部，PCM数据大小: {len(pcm_data)} 字节")
                            
                            # 发送PCM数据（如果有）
                            if len(pcm_data) > 0:
                                audio_manager.add_stream_chunk(bytes(pcm_data), priority, is_final=False)
                        else:
                            # 不是WAV格式，发送所有累积数据
                            util.log(1, f"[TTS] 未检测到WAV格式，发送原始数据: {len(header_buffer)} 字节")
                            audio_manager.add_stream_chunk(bytes(header_buffer), priority, is_final=False)
                            wav_header_processed = True
                            
                        # 清空缓冲区
                        header_buffer.clear()
                    elif chunk_count > 20:  # 如果累积了太多数据仍未找到头部
                        # 可能不是WAV格式，发送所有累积数据
                        util.log(1, f"[TTS] 未找到WAV头部，发送累积数据: {len(header_buffer)} 字节")
                        audio_manager.add_stream_chunk(bytes(header_buffer), priority, is_final=False)
                        wav_header_processed = True
                        header_buffer.clear()
                    # 否则继续累积数据以检测头部
                else:
                    # 已处理头部，直接发送后续数据（PCM数据）
                    audio_manager.add_stream_chunk(network_chunk, priority, is_final=False)

                if chunk_count == 1:
                    util.log(1, f"[TTS] 🎵 开始转发数据")
                elif chunk_count % 20 == 0:  # 每20块记录一次
                    util.log(1, f"[TTS] ✅ 已转发 {chunk_count} 块，共 {total_bytes} 字节")

            # 发送结束标记
            if chunk_count > 0:
                audio_manager.add_stream_chunk(b'', priority, is_final=True)
                util.log(1, f"[TTS] 🏁 转发完成：{chunk_count} 块，{total_bytes} 字节")

            util.log(1, f"[TTS] ✅ 流式播放完成")
            return "STREAMING_COMPLETED"
        except Exception as e:
            util.log(2, f"[TTS] 流式播放异常: {e}")
            return None

    def __get_history(self, voice_name, style, text):
        """获取历史合成记录"""
        for data in self.__history_data:
            if data[0] == voice_name and data[1] == style and data[2] == text:
                return data[3]
        return None

    def __get_emotion_params(self, text):
        """根据文本中的表情符号获取语音参数"""
        params = {
            "speed": 1.0,
            "gain": 0.0
        }
        
        # 简单的表情映射,使用更温和的参数
        if "😠" in text:  # 生气
            params.update({
                "speed": 0.8,  # 稍快
                "gain": 5   # 稍大声
            })
        elif "⚡" in text:  # 快速
            params.update({
                "speed": 1.2,  # 快速
                "gain": 0.0   # 正常音量
            })
        elif "🐌" in text:  # 慢速
            params.update({
                "speed": 0.9,  # 稍慢
                "gain": 0.0   # 正常音量
            })
        elif "🤫" in text:  # 悄悄话
            params.update({
                "speed": 1.5, # 接近正常
                "gain": -5  # 稍小声
            })
            
        return params

    def _extract_text_and_params(self, text, style=None):
        """提取文本和参数，复用现有逻辑"""
        # 检查并处理元组类型的输入
        if isinstance(text, tuple) and len(text) >= 2:
            extracted_text = text[0]
            tuple_style = text[1] if len(text) > 1 else None
            final_style = tuple_style or style
        else:
            extracted_text = str(text)
            final_style = style

        # 处理风格参数
        speed = 1.0
        gain = -5

        if final_style:
            if final_style == "fast":
                speed = 1.3
            elif final_style == "slow":
                speed = 0.8
            elif final_style == "gentle":
                gain = -8
            elif final_style == "excited":
                speed = 1.2
                gain = -3

        return extracted_text, speed, gain

    def to_sample(self, text, style=None, pc_stream_sink=None, skip_effects=False):
        """
        将文本转换为语音并保存为音频文件

        Args:
            text: 文本内容或(文本,风格)元组
            style: 语音风格，可选

        Returns:
            str: 生成的音频文件路径，如果失败则返回None
        """
        print(f"[TTS] to_sample输入文本: {text}")
        print(f"[TTS] to_sample输入style: {style}")

        try:
            util.log(1, f"[TTS-Silicon] 开始处理语音合成请求...")



            # 检查并处理元组类型的输入
            if isinstance(text, tuple):
                util.log(1, f"[TTS-Silicon] 处理元组类型输入: {text[0][:30] if text and len(text) > 0 else '空'}")
                # 提取元组中的文本部分
                orig_text = text[0] if text and len(text) > 0 else ""
                text = orig_text
            
            # 确保text是字符串类型
            if not isinstance(text, str):
                text = str(text) if text is not None else ""
                util.log(1, f"[TTS-Silicon] 将非字符串输入转换为字符串: {text[:30]}")
            
            # 处理style参数2025年3.26使用
            speed = 1  # 默认速度
            gain = -2  # 默认增益
            
            if style == "angry":
                speed = 0.9  # 愤怒语气略快
                gain = -1     # 音量增强
                print(f"[TTS] 检测到angry风格，设置speed={speed}, gain={gain}")
            elif style == "whisper":
                speed = 0.9  # 低语语气略慢
                gain = -8    # 音量降低
                print(f"[TTS] 检测到whisper风格，设置speed={speed}, gain={gain}")
            elif style == "gentle":
                speed = 1  # 温柔语气正常速度
                gain = -2    # 正常音量
                print(f"[TTS] 检测到gentle风格，设置speed={speed}, gain={gain}")
            else:
                print(f"[TTS] 未检测到特定风格，使用默认参数speed={speed}, gain={gain}")

            # Android remote playback path: clamp gain to reduce speaker clipping risk.
            # Keep local PC playback unchanged.
            try:
                from utils.android_output_hub import get_android_output_hub

                if get_android_output_hub().has_output_device() and gain > -5:
                    util.log(1, f"[TTS] remote output detected, clamp gain {gain} -> -5")
                    gain = -5
            except Exception:
                pass
            
            # 2025.3.26 特殊标记处理逻辑 - 处理[laughter]和[breath]标记
            extracted_text = text  # 默认使用原始文本
            
            # 使用正则表达式检测标记，同时支持有空格和无空格的格式
            has_laughter = re.search(r'\[\s*laughter\s*\]', text) is not None
            has_breath = re.search(r'\[\s*breath\s*\]', text) is not None
            
            if has_laughter or has_breath:
                # 备份原始文本
                original_text = text
                
                # 根据标记选择合适的提示前缀
                if has_laughter and has_breath:
                    prefix = "Can you add laughter and breathing sounds?"
                elif has_laughter:
                    prefix = "Can you add laughter?"
                elif has_breath:
                    prefix = "Can you add breathing sounds?"
                
                # 添加前缀和分隔符
                extracted_text = f"{prefix} <|endofprompt|>{original_text}"
                print(f"[TTS] 检测到特殊标记，添加提示前缀: {prefix}")
                util.log(1, f"[TTS] 添加特殊标记处理: {prefix}")
            
            # 初始化默认参数
            
            # 处理可能是JSON的情况
            if isinstance(text, str) and "{" in text and "}" in text:
                # 移除解析日志，减少输出
                
                try:
                    # 1. 尝试标准JSON解析
                    clean_text = text.strip()
                    json_data = json.loads(clean_text)
                    
                    # 提取文本内容
                    if "text" in json_data:
                        extracted_text = json_data["text"]
                    
                    # 提取其他参数
                    if "tone" in json_data:
                        tone = json_data.get("tone")
                        if tone == "angry":
                            speed = 0.8
                            gain = 0.0  # 愤怒音量调整为0.0
                        elif tone == "gentle":
                            if "小声" in extracted_text or "悄悄" in extracted_text or "🤫" in extracted_text:
                                speed = 0.9
                                gain = -5.0  # 悄悄话音量调整为-5.0
                    
                    # 直接提取速度和音量
                    if "speed" in json_data:
                        speed = float(json_data["speed"])
                    if "gain" in json_data:
                        gain = float(json_data["gain"])
                    
                except json.JSONDecodeError as e:
                    util.log(1, f"[TTS] 标准JSON解析失败: {str(e)}, 尝试正则表达式提取")
                    
                    # 2. 尝试使用多种正则表达式提取文本
                    # 提取引号中的文本，处理各种格式的引号
                    patterns = [
                        r'"text"\s*[:：]\s*"([^"]+)"',  # 标准格式
                        r'"text"\s*[:：]\s*"([^"]*)"',  # 空文本
                        r'"text"[:：]\s*[""]([^""]+)[""]',  # 中文引号
                        r'"text"\s*[:：]\s*[""]([^"]*)[""]',  # 中文引号包围空文本
                        r'text"?\s*[:：]\s*"([^"]+)"',  # 少引号格式
                        r'"?text"?\s*[:：]\s*"?([^",\n}{]+)',  # 宽松匹配
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            extracted_text = match.group(1)
                            util.log(1, f"[TTS] 使用正则表达式提取到文本: {extracted_text}")
                            break
                    
                    # 3. 根据文本内容判断情绪并设置参数
                    if extracted_text:
                        if "😠" in text or "angry" in text.lower() or "愤怒" in text:
                            speed = 0.8
                            gain = 0.0  # 愤怒音量调整为0.0
                        elif "🤫" in text or "悄悄" in text or "小声" in text or "gentle" in text.lower():
                            speed = 0.9
                            gain = -5.0  # 悄悄话音量调整为-5.0
            
            # 如果无法提取文本，使用原始输入
            if not extracted_text:
                extracted_text = text
                util.log(1, f"[TTS] 未能提取有效文本，使用原始输入")
                
            # 确保extracted_text是字符串类型
            if isinstance(extracted_text, tuple):
                # 如果是元组，提取第一个元素作为文本
                extracted_text = extracted_text[0] if len(extracted_text) > 0 else ""
                util.log(1, f"[TTS] 处理元组类型的输入，提取文本: {extracted_text[:30]}...")
            
            # 将非字符串类型转换为字符串
            extracted_text = str(extracted_text) if extracted_text is not None else ""

            # 🔥 重要：仅检测是否需要音效分块。{}触发已由Core统一入口处理，避免重复。
            should_use_chunked = False
            if not skip_effects:
                try:
                    from utils.emotion_trigger import should_use_chunked_processing
                    should_use_chunked = should_use_chunked_processing(extracted_text)
                except Exception as e:
                    util.log(2, f"[TTS] 分块处理检测失败: {str(e)}")

            if should_use_chunked:
                util.log(1, "[TTS] 检测到需要音效分块，切换 OPUS 插入流程")
                return self.process_with_opus_insertion(extracted_text, style=style)

            # 进一步清理文本 - 移除JSON相关字符和格式
            if extracted_text.startswith('{') and '}' in extracted_text:
                # 这可能仍然是JSON格式，需要进一步提取
                util.log(1, f"[TTS] 警告：提取的文本仍然是JSON格式，尝试进一步清理")

                # 移除所有JSON符号和引号
                cleaned_text = re.sub(r'[{}\[\]",:]', ' ', extracted_text)
                # 移除多余空格
                cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

                if cleaned_text:
                    extracted_text = cleaned_text
                    util.log(1, f"[TTS] 清理后的文本: {extracted_text}")

            # 移除Markdown格式和特殊标记
            extracted_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', extracted_text)  # 去除加粗标记
            extracted_text = re.sub(r'#+ ', '', extracted_text)  # 去除标题标记

            # 去除音乐指令和其他方括号标记 - TTS不读出
            extracted_text = re.sub(r'\[MUSIC:[^\]]*\]', '', extracted_text)  # 去除音乐指令
            extracted_text = re.sub(r'\[[^\]]*\]', '', extracted_text)  # 去除其他方括号标记
            extracted_text = re.sub(r'\s+', ' ', extracted_text).strip()  # 清理多余空格
            
            # 确保文本不为空
            if not extracted_text or extracted_text.strip() == "":
                util.log(1, "[TTS] 警告: 提取的文本为空，使用默认文本")
                extracted_text = "我没有理解你的意思，请再说一次。"
            
            # 添加必要的标点
            if not extracted_text.endswith(('.', '。', '!', '！', '?', '？')):
                extracted_text += '...'
            
            # 构建请求参数
            params = {
                "model": self.model,
                "voice": self.voice_type,
                "input": extracted_text,  # 使用处理后的文本
                "response_format": "wav",  # 🔥 使用WAV格式，避免OPUS 48000Hz限制
                "sample_rate": 16000,     # 🔥 改为16000Hz，与设备端配置保持一致
                "stream": True,  # 开启流式合成
                "speed": speed,
                "gain": gain
            }
            
            # 记录最终发送的文本
            print(f"[TTS] 最终发送的文本: {extracted_text[:100]}...")
            util.log(1, f"[TTS] 最终请求参数: speed={speed}, gain={gain}")

            # 设备优先流式播放：统一OPUS单通路（下线WAV直转发）
            try:
                util.log(1, f"[TTS] 🎯 设备优先流式播放模式（OPUS单通路）")

                # 检查是否有ESP32设备连接
                esp32_adapter = self._get_esp32_adapter()
                if esp32_adapter and esp32_adapter.clients:
                    util.log(1, f"[TTS] 检测到 {len(esp32_adapter.clients)} 个ESP32设备，走OPUS编码实时发送")

                    # 统一：拉取音频流（wav），转PCM→统一队列（由AudioOutputManager内部做OPUS与BP3）
                    response = self.__send_request("audio/speech", params, timeout=30)
                    if not response:
                        util.log(2, f"[TTS] 流式请求失败")
                        return None

                    import struct
                    import audioop

                    def _parse_wav_header(data: bytes):
                        if len(data) < 44 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
                            return None
                        fmt_pos = data.find(b'fmt ')
                        if fmt_pos == -1:
                            return None
                        fmt_size = struct.unpack('<I', data[fmt_pos+4:fmt_pos+8])[0]
                        fmt_data = data[fmt_pos+8:fmt_pos+8+fmt_size]
                        if len(fmt_data) < 16:
                            return None
                        audio_format, channels, sample_rate, byte_rate, block_align, bits_per_sample = struct.unpack('<HHIIHH', fmt_data[:16])
                        data_pos = data.find(b'data')
                        if data_pos == -1:
                            return None
                        audio_data_start = data_pos + 8
                        return {
                            'channels': channels,
                            'sample_rate': sample_rate,
                            'bits_per_sample': bits_per_sample,
                            'block_align': block_align,
                            'audio_data_start': audio_data_start
                        }

                    from esp32_liusisi.sisi_audio_output import AudioOutputManager
                    aom = AudioOutputManager.get_instance()
                    if not aom:
                        util.log(2, f"[TTS] 未找到AudioOutputManager实例")
                        return None

                    header_buf = bytearray()
                    wav_header = None
                    in_channels = None
                    in_rate = None
                    in_width = None
                    pcm_pending = bytearray()
                    ratecv_state = None

                    def _push_pcm(pcm_bytes: bytes, is_final: bool = False):
                        nonlocal pcm_pending, ratecv_state, in_channels, in_width, in_rate
                        if not pcm_bytes and not is_final:
                            return
                        pcm_pending.extend(pcm_bytes)
                        if in_channels and in_width and in_rate:
                            frame_size_in = in_channels * in_width
                            process_len = (len(pcm_pending) // frame_size_in) * frame_size_in
                            if process_len > 0:
                                to_process = bytes(pcm_pending[:process_len])
                                pcm_pending = pcm_pending[process_len:]

                                data_conv = to_process
                                # 声道转单声道
                                if in_channels == 2:
                                    try:
                                        data_conv = audioop.tomono(data_conv, in_width, 0.5, 0.5)
                                    except Exception:
                                        step = in_channels * in_width
                                        data_conv = b''.join([to_process[i:i+in_width] for i in range(0, len(to_process), step)])
                                elif in_channels != 1:
                                    step = in_channels * in_width
                                    data_conv = b''.join([to_process[i:i+in_width] for i in range(0, len(to_process), step)])

                                # 位宽转16bit
                                if in_width != 2:
                                    try:
                                        data_conv = audioop.lin2lin(data_conv, in_width, 2)
                                    except Exception:
                                        data_conv = b''

                                # 采样率转16k
                                if in_rate != 16000 and data_conv:
                                    try:
                                        data_conv, ratecv_state = audioop.ratecv(data_conv, 2, 1, in_rate, 16000, ratecv_state)
                                    except Exception:
                                        data_conv = b''

                                if data_conv:
                                    aom.add_stream_chunk(data_conv, priority=5, is_final=False)

                        if is_final:
                            # flush余量
                            if in_channels and in_width and in_rate and len(pcm_pending) > 0:
                                frame_size_in2 = in_channels * in_width
                                tail_len = (len(pcm_pending) // frame_size_in2) * frame_size_in2
                                if tail_len > 0:
                                    tail = bytes(pcm_pending[:tail_len])
                                    pcm_pending = pcm_pending[tail_len:]
                                    try:
                                        data_conv = tail
                                        if in_channels == 2:
                                            data_conv = audioop.tomono(data_conv, in_width, 0.5, 0.5)
                                        elif in_channels != 1:
                                            step = in_channels * in_width
                                            data_conv = b''.join([tail[i:i+in_width] for i in range(0, len(tail), step)])
                                        if in_width != 2:
                                            data_conv = audioop.lin2lin(data_conv, in_width, 2)
                                        if in_rate != 16000:
                                            data_conv, ratecv_state = audioop.ratecv(data_conv, 2, 1, in_rate, 16000, ratecv_state)
                                        if data_conv:
                                            aom.add_stream_chunk(data_conv, priority=5, is_final=False)
                                    except Exception:
                                        pass
                            aom.add_stream_chunk(b'', priority=5, is_final=True)

                    # 流式读取并逐块送入统一队列
                    chunk_count = 0
                    for net_chunk in response.iter_content(chunk_size=2048):
                        if not net_chunk:
                            continue
                        chunk_count += 1
                        if not wav_header:
                            header_buf.extend(net_chunk)
                            if len(header_buf) >= 44 and header_buf[:4] == b'RIFF' and header_buf[8:12] == b'WAVE':
                                info = _parse_wav_header(bytes(header_buf))
                                if info:
                                    in_channels = info['channels']
                                    in_rate = info['sample_rate']
                                    in_width = max(1, info['bits_per_sample'] // 8)
                                    # 首批去头后的PCM
                                    if len(header_buf) > info['audio_data_start']:
                                        pcm_part = bytes(header_buf[info['audio_data_start']:])
                                        if pcm_part:
                                            _push_pcm(pcm_part, is_final=False)
                                    header_buf.clear()
                                    wav_header = info
                                continue
                            elif len(header_buf) >= 44:
                                # 非标准头，按原始PCM处理，默认参数
                                if in_channels is None:
                                    in_channels = 1
                                    in_rate = 16000
                                    in_width = 2
                                _push_pcm(bytes(header_buf), is_final=False)
                                header_buf.clear()
                                wav_header = {'channels': in_channels, 'sample_rate': in_rate, 'bits_per_sample': in_width*8, 'audio_data_start': 0}
                                continue
                            else:
                                continue
                        else:
                            _push_pcm(net_chunk, is_final=False)

                    # 结束
                    _push_pcm(b'', is_final=True)

                    util.log(1, f"[TTS] ✅ OPUS单通路流式播放完成")
                    return "STREAMING_COMPLETED"
                else:
                    util.log(1, f"[TTS] 无ESP32设备连接，使用PC播放模式")

                # 🔄 PC播放模式（无设备时的备用方案）
                max_retries = 3
                retry_count = 0

                pc_queue = None
                if pc_stream_sink is None:
                    try:
                        from utils.pc_stream_queue import get_pc_stream_queue
                        pc_queue = get_pc_stream_queue()
                        pc_stream_sink = pc_queue.enqueue_stream(label="tts")
                    except Exception:
                        pc_stream_sink = None
                use_pc_queue = pc_stream_sink is not None

                while retry_count < max_retries:
                    try:
                        # 使用统一的请求方法
                        response = self.__send_request(
                            "audio/speech",
                            params,
                            timeout=30  # 增加超时时间，确保大文本也能处理
                        )

                        if not response:
                            retry_count += 1
                            util.log(1, f"[TTS] API请求失败 - 重试 {retry_count}/{max_retries}")
                            time.sleep(1)  # 等待1秒后重试
                            continue

                        # 确保流式参数被正确设置
                        if not response.headers.get('Transfer-Encoding') == 'chunked':
                            util.log(1, f"[TTS] 警告：非流式响应，可能会导致大文本处理超时")
                        
                        # 🔥 2025-08-15 修复：实现真正的并行流式TTS
                        output_file = os.path.join("samples", f"output_{int(time.time())}.wav")
                        os.makedirs("samples", exist_ok=True)

                        # 🔥 初始化PC实时播放处理
                        # 初始化 PC 实时播放缓冲
                        complete_audio = b""
                        pc_audio_buffer = b""
                        chunk_count = 0
                        header_parsed = False
                        pcm_cfg = None

                        # 增量重采样到 PC 输出
                        import audioop
                        ratecv_state = None
                        pcm_pending = bytearray()

                        def _convert_pcm_chunk(raw, cfg):
                            nonlocal ratecv_state
                            if not raw or not cfg:
                                return b''
                            sample_rate, channels, sample_width = cfg
                            data_conv = raw
                            if channels == 2:
                                data_conv = audioop.tomono(data_conv, sample_width, 0.5, 0.5)
                            elif channels != 1:
                                step = channels * sample_width
                                data_conv = b''.join([data_conv[i:i+sample_width] for i in range(0, len(data_conv), step)])
                            if sample_width != 2:
                                try:
                                    data_conv = audioop.lin2lin(data_conv, sample_width, 2)
                                except Exception:
                                    data_conv = b''
                            if sample_rate != 16000 and data_conv:
                                try:
                                    data_conv, ratecv_state = audioop.ratecv(data_conv, 2, 1, sample_rate, 16000, ratecv_state)
                                except Exception:
                                    data_conv = b''
                            return data_conv

                        def _push_converted(data_conv):
                            if not data_conv:
                                return
                            pcm_pending.extend(data_conv)
                            while len(pcm_pending) >= 1024:
                                chunk_out = bytes(pcm_pending[:1024])
                                del pcm_pending[:1024]
                                if use_pc_queue:
                                    pc_stream_sink.push(chunk_out)
                                else:
                                    _write_pcm_to_pc_stream(
                                        chunk_out,
                                        sample_rate=16000,
                                        channels=1,
                                        sample_width=2,
                                    )

                        for chunk in response.iter_content(chunk_size=1024):  # 1KB 分块读取
                            if not chunk:
                                continue
                            complete_audio += chunk
                            pc_audio_buffer += chunk
                            chunk_count += 1

                            if not header_parsed and len(pc_audio_buffer) >= 44:
                                try:
                                    sample_rate = int.from_bytes(pc_audio_buffer[24:28], 'little')
                                    channels = int.from_bytes(pc_audio_buffer[22:24], 'little')
                                    sample_width = int.from_bytes(pc_audio_buffer[34:36], 'little') // 8
                                    header_parsed = True
                                    pcm_cfg = (sample_rate, channels, sample_width)
                                    util.log(1, f"[TTS] 2025-08-15 ✅ PC音频流参数: {sample_rate}Hz, {channels}ch")

                                    audio_data_start = pc_audio_buffer[44:]
                                    if audio_data_start:
                                        data_conv = _convert_pcm_chunk(audio_data_start, pcm_cfg)
                                        _push_converted(data_conv)
                                    pc_audio_buffer = b''
                                except Exception as e:
                                    util.log(2, f"[TTS] 2025-08-15 WAV头解析失败: {str(e)}")

                            if header_parsed and pcm_cfg and len(pc_audio_buffer) >= 1024:
                                try:
                                    data_conv = _convert_pcm_chunk(pc_audio_buffer[:1024], pcm_cfg)
                                    _push_converted(data_conv)
                                    pc_audio_buffer = pc_audio_buffer[1024:]
                                except Exception as e:
                                    util.log(2, f"[TTS] 2025-08-15 PC流处理失败: {str(e)}")

                        if header_parsed and pcm_cfg and pc_audio_buffer:
                            try:
                                data_conv = _convert_pcm_chunk(pc_audio_buffer, pcm_cfg)
                                _push_converted(data_conv)
                                util.log(1, "[TTS] 2025-08-15 ✅ PC尾包已处理")
                            except Exception as e:
                                util.log(2, f"[TTS] 2025-08-15 PC尾包处理失败: {str(e)}")

                        if pcm_pending:
                            if use_pc_queue:
                                pc_stream_sink.push(bytes(pcm_pending))
                            else:
                                _write_pcm_to_pc_stream(
                                    bytes(pcm_pending),
                                    sample_rate=16000,
                                    channels=1,
                                    sample_width=2,
                                )
                            pcm_pending = bytearray()

                        if use_pc_queue:
                            try:
                                pc_stream_sink.finish()
                            except Exception:
                                pass

                        with open(output_file, "wb") as f:
                            f.write(complete_audio)
                            f.flush()
                            os.fsync(f.fileno())
                        
                        # 验证文件是否成功创建并可访问
                        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                            util.log(1, f"[TTS] 🔊 并行TTS完成: {output_file}")
                            util.log(1, f"[TTS] 📊 处理统计: {chunk_count}块, 总大小: {len(complete_audio)}字节")

                            # 转换为绝对路径，确保其他模块能正确访问
                            abs_output_file = os.path.abspath(output_file)

                            # ✅ 并行处理完成，PC实时播放+文件保存（设备播放统一由播放队列线程处理）
                            util.log(1, f"[TTS] ✅ 并行处理完成，PC实时播放+文件保存")
                            return abs_output_file
                        else:
                            util.log(1, f"[TTS] ❌ 音频文件创建失败或为空: {output_file}")
                            return None
                        
                    except Exception as e:
                        retry_count += 1
                        util.log(1, f"[TTS] 请求异常，重试 {retry_count}/{max_retries}: {str(e)}")
                        if retry_count >= max_retries:
                            util.log(1, f"[TTS] 重试{max_retries}次后仍失败")
                            return None
                        time.sleep(1)
                
                # 如果所有重试都失败
                if retry_count >= max_retries:
                    util.log(1, f"[TTS] 达到最大重试次数，请求失败")
                    return None
                
            except Exception as e:
                util.log(1, f"[TTS] 未预期的异常: {str(e)}")
                import traceback
                util.log(1, f"[TTS] 异常堆栈: {traceback.format_exc()}")
                return None

        except Exception as e:
            util.log(1, f"[TTS] 处理语音合成请求时发生错误: {str(e)}")
            print(f"[TTS] 错误: {str(e)}")
            return None

    def __send_request(self, endpoint, params, timeout=60):
        """发送请求到SiliconFlow API"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 处理代理配置
        proxies = None
        if hasattr(cfg, 'proxy_config') and cfg.proxy_config:
            if cfg.proxy_config.startswith('http'):
                proxies = {
                    "http": cfg.proxy_config,
                    "https": cfg.proxy_config
                }
                util.log(1, f"[TTS] 使用代理: {cfg.proxy_config}")
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=params,
                proxies=proxies,
                timeout=timeout,
                stream=True
            )
            
            # 错误处理
            if response.status_code != 200:
                if response.status_code == 401:
                    util.log(1, f"[错误] API认证失败: 无效的token，请检查system.conf中的siliconflow_api_key是否正确")
                else:
                    util.log(1, f"[错误] API请求失败: {response.status_code} - {response.text}")
                return None
                
            return response
        except requests.exceptions.RequestException as e:
            util.log(1, f"[错误] 请求异常: {str(e)}")
            return None

    def close(self):
        """关闭连接"""
        pass

    def generate_opening_audio(self, text):
        """生成开场白音频并缓存"""
        util.log(1, f"准备生成开场白音频: {text}")
        file_url = f'./samples/sample-opening_{hash(text)}_opening.wav'
        
        # 检查缓存
        if os.path.exists(file_url):
            util.log(1, f"找到缓存的开场白音频: {file_url}")
            return file_url

        # 生成音频
        return self.to_sample(text, style="opening")

    def process_text_with_sound_effects(self, text, **kwargs):
        """
        处理带有音效标记的文本，支持在TTS中插入音效

        Args:
            text: 带有音效标记的文本，如"前面{南无阿弥陀佛_电音DJ音效}后面"
            **kwargs: TTS合成参数

        Returns:
            list: 音频文件列表，按顺序播放 [(类型, 文件路径), ...]
        """
        import re
        from utils.emotion_trigger import EMOTION_TRIGGER_MAP

        # 音效标记正则表达式
        effect_pattern = re.compile(r'(\{([A-Za-z0-9_\u4e00-\u9fff]+)\})')

        # 分割文本
        audio_files = []
        last_end = 0

        for match in effect_pattern.finditer(text):
            # 处理音效前的文本
            if match.start() > last_end:
                text_before = text[last_end:match.start()].strip()
                if text_before:
                    # TTS合成
                    tts_file = self.to_sample(text_before, **kwargs)
                    if tts_file:
                        audio_files.append(("tts", tts_file))

            # 处理音效
            effect_name = match.group(2)  # 提取音效名称
            effect_config = EMOTION_TRIGGER_MAP.get(effect_name)

            if effect_config and effect_config.get("type") == "sound_effect":
                audio_file = effect_config.get("audio_file")
                if audio_file:
                    # 构建完整路径
                    import os
                    if not os.path.isabs(audio_file):
                        audio_file = os.path.abspath(audio_file)

                    if os.path.exists(audio_file):
                        audio_files.append(("effect", audio_file))
                        util.log(1, f"[TTS分块] ✅ 添加音效: {effect_name}")
                    else:
                        util.log(2, f"[TTS分块] ❌ 音效文件不存在: {audio_file}")

            last_end = match.end()

        # 处理最后一段文本
        if last_end < len(text):
            text_after = text[last_end:].strip()
            if text_after:
                tts_file = self.to_sample(text_after, **kwargs)
                if tts_file:
                    audio_files.append(("tts", tts_file))

        util.log(1, f"[TTS分块] 处理完成，共{len(audio_files)}个音频片段")
        return audio_files

    def process_with_opus_insertion(self, text, **kwargs):
        """
        使用OPUS帧插入方式处理音效 - 真正的中间插入

        Args:
            text: 带有音效标记的文本
            **kwargs: TTS合成参数

        Returns:
            str: 合并后的音频文件路径
        """
        import re
        from utils.emotion_trigger import EMOTION_TRIGGER_MAP

        util.log(1, f"[OPUS插入] 开始处理: {text}")

        # 🔥 修复1：更精确的文本清理和位置映射
        effect_pattern = re.compile(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}')
        effects = []

        # 建立原文本到清理文本的位置映射
        clean_text = ""
        char_mapping = []  # 记录清理文本中每个字符在原文本中的位置

        last_pos = 0
        for match in effect_pattern.finditer(text):
            effect_name = match.group(1)
            effect_config = EMOTION_TRIGGER_MAP.get(effect_name)

            # 支持音效和音乐播放两种类型
            if effect_config and effect_config.get("type") in ["sound_effect", "music_play"]:
                # 添加标记前的文本
                before_text = text[last_pos:match.start()]
                clean_text += before_text

                # 记录字符映射
                for i, char in enumerate(before_text):
                    char_mapping.append(last_pos + i)

                # 🔥 修复：更精确的插入位置计算
                # 基于前面文本的字符数，而不是总长度比例
                insert_position_in_clean = len(clean_text)

                # 验证音效文件存在性
                effect_file = effect_config.get("audio_file")
                if effect_file and not os.path.isabs(effect_file):
                    effect_file = os.path.abspath(effect_file)

                if effect_file and os.path.exists(effect_file):
                    effects.append({
                        'name': effect_name,
                        'file': effect_file,
                        'insert_position_in_clean': insert_position_in_clean,
                        'type': effect_config.get("type"),
                        'before_text_length': len(before_text)  # 新增：前面文本长度
                    })
                    util.log(1, f"[OPUS插入] ✅ 音效文件验证通过: {effect_name} -> {effect_file}")
                else:
                    util.log(2, f"[OPUS插入] ❌ 音效文件不存在: {effect_name} -> {effect_file}")

                last_pos = match.end()

        # 添加最后一段文本
        if last_pos < len(text):
            remaining_text = text[last_pos:]
            clean_text += remaining_text
            for i, char in enumerate(remaining_text):
                char_mapping.append(last_pos + i)

        # 🔥 修复2：确保清理文本完全去除标记
        # 再次清理可能遗漏的标记
        clean_text = re.sub(r'\{[A-Za-z0-9_\u4e00-\u9fff]+\}', '', clean_text)

        util.log(1, f"[OPUS插入] 清理后文本: {clean_text}")
        util.log(1, f"[OPUS插入] 检测到{len(effects)}个插入点")

        # 2. TTS合成清理后的文本
        main_audio = self.to_sample(clean_text, **kwargs)

        if not main_audio:
            util.log(2, f"[OPUS插入] TTS合成失败")
            return None

        # 🔥 修复：流式TTS完成后，不支持OPUS插入，改为异步播放音乐
        if main_audio == "STREAMING_COMPLETED":
            util.log(1, f"[OPUS插入] 流式TTS已完成，音乐将在TTS后异步播放")
            # 触发音乐异步播放 - 等待AudioManager空闲后播放
            def wait_and_play_music():
                try:
                    from esp32_liusisi.sisi_audio_output import AudioOutputManager
                    import time
                    
                    aom = AudioOutputManager.get_instance()
                    if not aom:
                        util.log(2, "[OPUS插入] AudioManager不可用，跳过音乐播放")
                        return
                    
                    # 等待AudioManager空闲（最多等10秒）
                    max_wait = 10
                    waited = 0
                    while waited < max_wait:
                        if aom.is_idle():
                            util.log(1, f"[OPUS插入] AudioManager已空闲，开始播放音乐")
                            break
                        time.sleep(0.1)
                        waited += 0.1
                    
                    if waited >= max_wait:
                        util.log(2, f"[OPUS插入] 等待AudioManager空闲超时，跳过音乐播放")
                        return
                    
                    # 播放音乐
                    for effect in effects:
                        effect_name = effect['name']
                        util.log(1, f"[OPUS插入] 触发音乐播放: {effect_name}")
                        from utils.emotion_trigger import _execute_music_play, EMOTION_TRIGGER_MAP
                        if effect_name in EMOTION_TRIGGER_MAP:
                            trigger_config = EMOTION_TRIGGER_MAP[effect_name]
                            _execute_music_play(effect_name, trigger_config)
                            # 等待当前音乐播放完成
                            aom.wait_until_idle(timeout=15.0)
                
                except Exception as e:
                    util.log(2, f"[OPUS插入] 音乐播放异常: {e}")
            
            import threading
            threading.Thread(target=wait_and_play_music, daemon=True).start()
            return main_audio

        if not effects:
            return main_audio

        # 3. OPUS帧级插入（这里返回原音频，实际插入在播放时处理）
        util.log(1, f"[OPUS插入] 检测到{len(effects)}个音效插入点")

        # 4. 实现真正的OPUS帧插入
        try:
            # 导入OPUS转换器
            from esp32_liusisi.opus_helper import OpusConvertor
            opus_helper = OpusConvertor()

            # 转换主音频为OPUS帧
            main_frames, duration = opus_helper.audio_to_opus_frames(main_audio)
            if not main_frames:
                util.log(2, f"[OPUS插入] 主音频转换失败")
                return main_audio

            util.log(1, f"[OPUS插入] 主音频转换成功: {len(main_frames)}帧, 时长{duration:.2f}秒")

            # 计算插入位置并插入音效帧
            final_frames = main_frames.copy()

            for effect in effects:
                effect_file = effect['file']
                if not effect_file or not os.path.exists(os.path.abspath(effect_file)):
                    continue

                # 转换音效为OPUS帧
                effect_frames, effect_duration = opus_helper.audio_to_opus_frames(os.path.abspath(effect_file))
                if not effect_frames:
                    continue

                # 🔥 修复3：更精确的插入位置计算
                # 基于前面文本的实际长度，而不是比例
                before_text_length = effect.get('before_text_length', 0)
                clean_text_length = len(clean_text)

                if clean_text_length > 0 and before_text_length >= 0:
                    # 使用前面文本的实际比例
                    position_ratio = before_text_length / clean_text_length
                    insert_frame_pos = int(len(main_frames) * position_ratio)

                    # 确保插入位置在有效范围内
                    insert_frame_pos = max(0, min(insert_frame_pos, len(main_frames)))
                else:
                    insert_frame_pos = 0

                util.log(1, f"[OPUS插入] {effect['name']}: 前文长度={before_text_length}, 总长度={clean_text_length}, 比例={position_ratio:.2f}, 帧位置={insert_frame_pos}/{len(main_frames)}")

                # 插入音效帧
                final_frames = (final_frames[:insert_frame_pos] +
                              effect_frames +
                              final_frames[insert_frame_pos:])

                util.log(1, f"[OPUS插入] 在第{insert_frame_pos}帧插入音效: {effect['name']}")

            # 🔧 正确策略：不保存音频文件，直接缓存OPUS帧供发送端使用
            merged_audio_path = main_audio.replace('.wav', '_with_effects.wav')

            # 将合并后的OPUS帧缓存，供ESP32发送端直接使用
            if not hasattr(self, '_opus_frames_cache'):
                self._opus_frames_cache = {}
            self._opus_frames_cache[merged_audio_path] = final_frames

            # 🔥 修复：生成实际的音频文件而不是标记文件
            try:
                # 简单方案：复制原音频文件作为合并文件（音效通过OPUS帧发送）
                import shutil
                shutil.copy2(main_audio, merged_audio_path)
                util.log(1, f"[OPUS插入] 已生成合并音频文件: {merged_audio_path}")
                util.log(1, f"[OPUS插入] OPUS帧已缓存: {len(final_frames)}帧")
            except Exception as e:
                util.log(2, f"[OPUS插入] 生成音频文件失败: {str(e)}")
                return main_audio

            util.log(1, f"[OPUS插入] 合并完成: {len(final_frames)}帧，已缓存供直接发送")
            return merged_audio_path

        except Exception as e:
            util.log(2, f"[OPUS插入] 处理失败: {str(e)}")
            return main_audio


# 为了与现有接口保持一致，添加Speech类作为SiliconFlowTTS的别名
class Speech(SiliconFlowTTS):
    """Speech类作为SiliconFlowTTS的别名，保持与其他TTS模块接口一致"""
    pass


if __name__ == "__main__":
    # 测试代码
    tts = SiliconFlowTTS()
    print("SiliconFlowTTS class defined successfully")
