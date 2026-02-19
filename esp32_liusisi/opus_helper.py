#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# opus_helper.py - 解决ESP32音频兼容性问题
# 作者: 修改于 2025-5-09

import os
import time
import asyncio
import logging
import tempfile
import sys
import io
import numpy as np
from typing import Tuple, List, Optional

# 添加opus.dll路径
current_dir = os.path.dirname(os.path.abspath(__file__))
opus_dll_path = os.path.join(current_dir, 'libs', 'windows')
if os.path.exists(opus_dll_path):
    os.environ['PATH'] = opus_dll_path + os.pathsep + os.environ.get('PATH', '')
    sys.path.insert(0, opus_dll_path)
    print(f"已添加Opus库路径: {opus_dll_path}")

# 尝试导入pydub
try:
    from pydub import AudioSegment
except ImportError:
    print("警告: pydub库未安装，请运行: pip install pydub")
    print("继续使用内置音频处理...")
    AudioSegment = None

# 尝试导入opuslib_next，如果失败则使用简单实现
try:
    import opuslib_next
    OPUS_AVAILABLE = True
    OPUS_APPLICATION_AUDIO = opuslib_next.APPLICATION_AUDIO
    print("已成功加载opuslib_next库")
except Exception as e:
    print(f"警告: 无法加载opuslib_next库: {str(e)}")
    opuslib_next = None
    # 尝试导入标准opuslib作为后备
    try:
        import opuslib
        OPUS_AVAILABLE = True
        # opuslib中可能使用不同的常量名
        OPUS_APPLICATION_AUDIO = getattr(opuslib, 'APPLICATION_AUDIO', 2048)  # 默认值2048
        print("已成功加载标准opuslib库作为替代")
    except Exception as e:
        print(f"警告: 无法加载opuslib库: {str(e)}")
        print("将使用备用音频处理方法...")
        opuslib = None
        OPUS_APPLICATION_AUDIO = 2048  # 默认值
        OPUS_AVAILABLE = False

logger = logging.getLogger("OpusHelper")

class OpusConvertor:
    """Opus音频转换工具，专为ESP32优化 - 基于sisi-esp32-server项目实现"""

    # 导入统一的音频参数配置
    from utils.stream_util import AudioManagerUtil
    SAMPLE_RATE = AudioManagerUtil.SAMPLE_RATE
    FRAME_DURATION = AudioManagerUtil.FRAME_DURATION
    CHANNELS = 1        # 🔥 修复：改回单声道，用户要求

    def __init__(self, debug: bool = False):
        """初始化Opus转换器
        Args:
            debug: 是否启用调试模式
        """
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        # 检查库可用性和版本
        if OPUS_AVAILABLE:
            if opuslib_next:
                lib_name = "opuslib_next"
                lib_version = getattr(opuslib_next, "__version__", "未知")
            else:
                lib_name = "opuslib"
                lib_version = getattr(opuslib, "__version__", "未知")
            if self.debug:
                logger.info(f"使用 {lib_name} 库, 版本: {lib_version}")
                logger.info(f"音频参数: 采样率={self.SAMPLE_RATE}Hz, 通道={self.CHANNELS}, 帧时长={self.FRAME_DURATION}ms")
        else:
            logger.warning("Opus库不可用，将使用简单实现")

        # 检查pydub是否可用
        if AudioSegment:
            try:
                # 验证pydub可用
                dummy = AudioSegment.silent(duration=100)
                if self.debug:
                    logger.debug("pydub库初始化成功")
            except Exception as e:
                logger.error(f"pydub库不可用: {str(e)}")
                logger.error("请安装必要库: pip install pydub")

        # 🔥 关键修复：创建持久的OPUS编码器实例（像xiaozhi那样）
        self.encoder = None
        self.pcm_buffer = bytearray()  # PCM缓冲区，用于流式处理
        self._init_encoder()

    def get_device_info(self, websocket):
        """获取WebSocket连接对应的设备信息"""
        # 通过websocket对象查找对应的client_id
        try:
            # 尝试从全局适配器实例获取设备信息
            from .sisi.adapter import get_adapter_instance
            adapter = get_adapter_instance()
            if adapter:
                # 通过websocket对象查找对应的client_id
                for client_id, ws in adapter.clients.items():
                    if ws == websocket:
                        return adapter.devices.get(client_id, {})
        except Exception as e:
            logger.debug(f"获取设备信息失败: {e}")
        return None

    def _init_encoder(self):
        """初始化持久的OPUS编码器"""
        if OPUS_AVAILABLE:
            try:
                if opuslib_next:
                    self.encoder = opuslib_next.Encoder(self.SAMPLE_RATE, self.CHANNELS, opuslib_next.APPLICATION_AUDIO)
                    # 🔥 减少重复初始化日志输出，只在调试模式下输出
                    if self.debug:
                        logger.info("🔥 创建持久的opuslib_next编码器")
                else:
                    self.encoder = opuslib.Encoder(self.SAMPLE_RATE, self.CHANNELS, OPUS_APPLICATION_AUDIO)
                    # 🔥 减少重复初始化日志输出，只在调试模式下输出
                    if self.debug:
                        logger.info("🔥 创建持久的opuslib编码器")

                # 设置编码参数
                if hasattr(self.encoder, 'bitrate'):
                    self.encoder.bitrate = 24000  # 24kbps
                if hasattr(self.encoder, 'complexity'):
                    self.encoder.complexity = 10  # 最高质量

                # 🔥 减少重复初始化日志输出，只在调试模式下输出
                if self.debug:
                    logger.info("✅ 持久编码器初始化成功")
            except Exception as e:
                logger.error(f"❌ 创建持久编码器失败: {e}")
                self.encoder = None

    def reset_encoder(self):
        """重置编码器状态（用于新的TTS会话）"""
        if self.encoder and hasattr(self.encoder, 'reset_state'):
            try:
                self.encoder.reset_state()
                self.pcm_buffer.clear()
                if self.debug:
                    logger.info("🔄 编码器状态已重置")
            except Exception as e:
                logger.warning(f"重置编码器失败，重新创建: {e}")
                self._init_encoder()
        else:
            # 如果没有reset_state方法，重新创建编码器
            self._init_encoder()
        self.pcm_buffer.clear()

    def _encode_with_recovery(self, frame_data, frame_size):
        """🔥 新增：带错误恢复的编码方法"""
        try:
            # 🔥 关键修复：将字节数据转换为numpy int16数组
            import numpy as np
            # frame_data是字节，需要转换为int16数组
            pcm_array = np.frombuffer(frame_data, dtype=np.int16)

            # 尝试使用现有编码器编码
            opus_frame = self.encoder.encode(pcm_array.tobytes(), frame_size)
            return opus_frame
        except Exception as e:
            logger.warning(f"编码失败: {e}，尝试恢复...")
            # 重置编码器状态
            self.reset_encoder()
            # 再次尝试编码
            try:
                if self.encoder:
                    opus_frame = self.encoder.encode(frame_data, frame_size)
                    logger.info("编码器恢复成功")
                    return opus_frame
                else:
                    logger.error("编码器恢复失败")
                    return None
            except Exception as e2:
                logger.error(f"编码器恢复后仍然失败: {e2}")
                return None

    def encode_pcm_to_opus_stream(self, pcm_data: bytes, end_of_stream: bool = False, callback=None) -> list:
        """🔥 新增：流式编码PCM数据为OPUS（保持编码器状态）
        参考xiaozhi-server的实现方式，直接处理PCM流

        Args:
            pcm_data: PCM字节数据
            end_of_stream: 是否为流的结束
            callback: OPUS帧回调函数

        Returns:
            list: OPUS帧列表（如果没有callback）
        """
        if not self.encoder:
            logger.error("编码器未初始化")
            return [] if not callback else None

        opus_frames = [] if not callback else None

        # 将新数据添加到缓冲区
        self.pcm_buffer.extend(pcm_data)

        # 🔥 添加调试日志
        if self.debug:
            logger.info(f"PCM缓冲区: 新增{len(pcm_data)}字节, 总计{len(self.pcm_buffer)}字节")

        # 计算帧大小（字节）
        frame_size = int(self.SAMPLE_RATE * self.FRAME_DURATION / 1000)  # 960 samples
        frame_size_bytes = frame_size * 2  # 16-bit = 2 bytes

        # 处理所有完整帧
        # 使用实例级自增帧号，便于跨帧统计
        if not hasattr(self, '_global_frame_count'):
            self._global_frame_count = 0
        while len(self.pcm_buffer) >= frame_size_bytes:
            # 提取一帧
            frame_data = bytes(self.pcm_buffer[:frame_size_bytes])
            del self.pcm_buffer[:frame_size_bytes]
            self._global_frame_count += 1

            # 🔥 使用带错误恢复的编码方法
            opus_frame = self._encode_with_recovery(frame_data, frame_size)
            if opus_frame:
                # 🔥 记录前几帧的详细信息
                if self._global_frame_count <= 3 or (self.debug and self._global_frame_count % 10 == 0):
                    logger.info(f"编码帧 #{self._global_frame_count}: PCM {frame_size_bytes}字节 -> OPUS {len(opus_frame)}字节")
                if callback:
                    callback(opus_frame)
                else:
                    opus_frames.append(opus_frame)
            else:
                logger.error("编码失败，跳过当前帧")

        # 如果是流结束且还有剩余数据，进行填充并编码
        if end_of_stream and len(self.pcm_buffer) > 0:
            remaining = bytes(self.pcm_buffer)
            # 填充到完整帧
            padding_needed = frame_size_bytes - len(remaining)
            frame_data = remaining + b'\x00' * padding_needed

            # 🔥 使用带错误恢复的编码方法
            opus_frame = self._encode_with_recovery(frame_data, frame_size)
            if opus_frame:
                if callback:
                    callback(opus_frame)
                else:
                    opus_frames.append(opus_frame)
            else:
                logger.error("编码最后一帧失败")

            # 清空缓冲区
            self.pcm_buffer.clear()

        return opus_frames if not callback else None

    def audio_to_opus_frames(self, audio_file: str) -> Tuple[List[bytes], float]:
        """将音频文件转换为opus帧列表 - 使用持久编码器

        Args:
            audio_file: 音频文件路径

        Returns:
            (opus_frames, duration): opus帧列表和音频时长(秒)
        """
        try:
            # 检查文件
            if not os.path.exists(audio_file):
                logger.error(f"文件不存在: {audio_file}")
                return [], 0.0

            # 检查文件大小
            file_size = os.path.getsize(audio_file)
            if file_size < 100:  # 太小的文件可能是空的或损坏的
                logger.error(f"文件太小，可能是空文件: {audio_file} ({file_size} 字节)")
                return [], 0.0

            logger.debug(f"处理音频文件: {audio_file}, 大小: {file_size} 字节")

            # 根据库可用性选择适当的方法
            if OPUS_AVAILABLE and AudioSegment:
                return self._convert_using_opuslib(audio_file)
            else:
                return self._convert_simple(audio_file)

        except Exception as e:
            logger.error(f"音频转换异常: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return [], 0.0

    def _convert_using_opuslib(self, audio_file: str) -> Tuple[List[bytes], float]:
        """使用opuslib库的转换方法，使用持久编码器"""
        try:
            # 获取文件后缀名
            file_type = os.path.splitext(audio_file)[1]
            if file_type:
                file_type = file_type.lstrip('.')

            # 读取音频文件
            logger.debug(f"从文件读取音频: {audio_file} (格式: {file_type or 'auto'})")
            try:
                audio = AudioSegment.from_file(audio_file, format=file_type, parameters=["-nostdin"])
            except Exception as e:
                logger.warning(f"按指定格式读取失败: {str(e)}")
                # 尝试使用wav格式强制读取
                logger.info(f"尝试以wav格式读取文件...")
                audio = AudioSegment.from_file(audio_file, format="wav", parameters=["-nostdin"])

            # 转换为单声道/16kHz采样率/16位小端编码（确保与编码器匹配）
            audio = audio.set_channels(self.CHANNELS).set_frame_rate(self.SAMPLE_RATE).set_sample_width(2)

            # 音频时长(秒)
            duration = len(audio) / 1000.0
            logger.debug(f"音频处理后: {duration:.2f}秒, {self.CHANNELS}通道, {self.SAMPLE_RATE}Hz采样率")

            # 获取原始PCM数据（16位小端）
            raw_data = audio.raw_data

            # 🔥 关键修复：使用持久编码器，而不是每次创建新的
            if not self.encoder:
                logger.error("持久编码器未初始化")
                self._init_encoder()
                if not self.encoder:
                    return [], 0.0

            logger.debug("使用持久编码器进行转换...")

            # 编码参数
            frame_size = int(self.SAMPLE_RATE * self.FRAME_DURATION / 1000)  # 960 samples/frame (60ms)

            # 分帧编码
            opus_frames = []
            total_frames = len(raw_data) // (frame_size * 2)  # 16bit=2bytes/sample

            logger.debug(f"开始编码 {total_frames} 帧...")

            # 按帧处理所有音频数据（包括最后一帧可能补零）
            for i in range(0, len(raw_data), frame_size * 2):  # 16bit=2bytes/sample
                # 获取当前帧的二进制数据
                chunk = raw_data[i:i + frame_size * 2]

                # 如果最后一帧不足，补零
                if len(chunk) < frame_size * 2:
                    chunk = chunk + b'\x00' * (frame_size * 2 - len(chunk))

                try:
                    # 转换为numpy数组处理
                    np_frame = np.frombuffer(chunk, dtype=np.int16)

                    # 编码Opus数据 - 使用持久编码器
                    opus_data = self.encoder.encode(np_frame.tobytes(), frame_size)
                    opus_frames.append(opus_data)

                    # 记录帧信息
                    if self.debug and (i == 0 or i == len(raw_data) - frame_size * 2 or i % (5 * frame_size * 2) == 0):
                        frame_num = i // (frame_size * 2)
                        logger.debug(f"帧 {frame_num}/{total_frames}: PCM={len(chunk)}字节 -> Opus={len(opus_data)}字节")

                except Exception as e:
                    logger.warning(f"编码帧 {i//(frame_size*2)} 失败: {str(e)}")

            logger.info(f"转换成功: {len(opus_frames)} 帧, 时长:{duration:.2f}秒")
            return opus_frames, duration

        except Exception as e:
            logger.error(f"音频转换失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return [], 0.0

    def _convert_simple(self, audio_file: str) -> Tuple[List[bytes], float]:
        """简单实现：直接按固定大小分块读取文件作为帧
        当opuslib不可用时使用这个备用方法
        """
        try:
            # 读取整个文件
            with open(audio_file, 'rb') as f:
                file_data = f.read()

            # 估算时长(假设24000Hz, 16位, 单声道)
            duration = len(file_data) / (self.SAMPLE_RATE * 2 * self.CHANNELS)
            logger.info(f"文件大小: {len(file_data)} 字节, 估算时长: {duration:.2f}秒")

            # 计算帧大小
            frame_size = int(self.SAMPLE_RATE * self.FRAME_DURATION / 1000) * 2
            logger.debug(f"使用简单实现，每帧大小: {frame_size}字节")

            # 分帧处理
            frames = []
            for i in range(0, len(file_data), frame_size):
                chunk = file_data[i:i + frame_size]
                # 填充最后一帧
                if len(chunk) < frame_size:
                    chunk = chunk + b'\x00' * (frame_size - len(chunk))
                frames.append(chunk)

            logger.info(f"简单处理完成: {len(frames)}帧, 估计时长: {duration:.2f}秒")
            return frames, duration

        except Exception as e:
            logger.error(f"简单音频处理失败: {str(e)}")
            return [], 0.0

    async def play_opus_frames(self, websocket, frames: List[bytes],
                               pre_buffer: int = 2,  # 🔥 改为2帧预缓冲，平衡延迟和稳定性
                               max_retry: int = 3) -> bool:
        """播放opus帧到WebSocket连接，简化版，参考sisi-esp32-server实现

        Args:
            websocket: WebSocket连接对象
            frames: opus帧列表
            pre_buffer: 预缓冲的帧数量
            max_retry: 最大重试次数

        Returns:
            是否播放成功
        """
        if not frames:
            logger.warning("没有帧可播放")
            return False

        logger.info(f"开始播放 {len(frames)} 个Opus帧 (预缓冲: {pre_buffer})")

        try:
            # 流控参数
            frame_duration = self.FRAME_DURATION / 1000.0  # 帧时长(秒)
            start_time = time.perf_counter()
            play_position = 0
            
            # 添加发送统计信息
            sent_frames = 0
            total_bytes = 0

            # 预缓冲：快速发送前几帧（根据客户端版本封装头或裸帧）
            pre_buffer = min(pre_buffer, len(frames))
            for i in range(pre_buffer):
                try:
                    # 检查连接状态 - websockets 14.0+ 兼容
                    try:
                        from websockets.protocol import State
                        if websocket.state != State.OPEN:
                            logger.warning(f"WebSocket连接已断开，停止播放 (预缓冲阶段)")
                            return False
                    except (ImportError, AttributeError):
                        if hasattr(websocket, 'closed') and websocket.closed:
                            logger.warning(f"WebSocket连接已断开，停止播放 (预缓冲阶段)")
                            return False

                    # 统一协议：根据协议版本决定是否发送 BinaryProtocol3 头
                    device = self.get_device_info(websocket)
                    protocol_version = device.get("protocol_version", 3) if device else 3
                    
                    if protocol_version == 3:
                        # 发送带BP3头部的数据 - 使用大端字节序，与xiaozhi项目保持一致
                        header = bytes([0, 0]) + (len(frames[i]).to_bytes(2, 'big'))
                        await websocket.send(header + frames[i])
                    else:
                        # 发送裸帧数据
                        await websocket.send(frames[i])
                    logger.debug(f"预缓冲帧 {i+1}/{pre_buffer} 已发送")
                except Exception as e:
                    logger.error(f"发送帧失败: {str(e)}")
                    return False

            # 正常播放剩余帧
            for i, opus_packet in enumerate(frames[pre_buffer:], pre_buffer):
                # 检查连接状态 - websockets 14.0+ 兼容
                try:
                    from websockets.protocol import State
                    if websocket.state != State.OPEN:
                        logger.warning(f"WebSocket连接已断开，停止播放 (播放位置: {i}/{len(frames)})")
                        return False
                except (ImportError, AttributeError):
                    if hasattr(websocket, 'closed') and websocket.closed:
                        logger.warning(f"WebSocket连接已断开，停止播放 (播放位置: {i}/{len(frames)})")
                        return False

                # 计算预期发送时间
                expected_time = start_time + (play_position * frame_duration)
                current_time = time.perf_counter()
                delay = expected_time - current_time

                # 需要等待时执行等待
                if delay > 0:
                    await asyncio.sleep(delay)
                # 添加额外的微小延迟以确保设备有足够时间处理
                elif play_position > 0 and play_position % 10 == 0:  # 每10帧添加一次微小延迟
                    await asyncio.sleep(0.001)  # 1ms延迟

                # 再次检查连接状态（等待后可能已断开）- websockets 14.0+ 兼容
                try:
                    from websockets.protocol import State
                    if websocket.state != State.OPEN:
                        logger.warning(f"WebSocket连接在等待后断开，停止播放 (播放位置: {i}/{len(frames)})")
                        return False
                except (ImportError, AttributeError):
                    if hasattr(websocket, 'closed') and websocket.closed:
                        logger.warning(f"WebSocket连接在等待后断开，停止播放 (播放位置: {i}/{len(frames)})")
                        return False

                # 发送帧（根据客户端版本封装BP3或裸帧）
                try:
                    # 统一协议：根据协议版本决定是否发送 BinaryProtocol3 头
                    device = self.get_device_info(websocket)
                    protocol_version = device.get("protocol_version", 3) if device else 3
                    
                    if protocol_version == 3:
                        # 发送带BP3头部的数据 - 使用大端字节序，与xiaozhi项目保持一致
                        header = bytes([0, 0]) + (len(opus_packet).to_bytes(2, 'big'))
                        await websocket.send(header + opus_packet)
                    else:
                        # 发送裸帧数据
                        await websocket.send(opus_packet)
                    # 更新统计信息
                    sent_frames += 1
                    total_bytes += len(opus_packet)
                    
                    if i % 20 == 0:  # 每20帧记录一次
                        logger.debug(f"帧 {i}/{len(frames)} 已发送 (累计: {sent_frames}帧, {total_bytes}字节)")
                except Exception as e:
                    logger.error(f"发送帧失败: {str(e)}")
                    # 如果是连接断开相关的错误，直接返回
                    if "close frame" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                        logger.warning(f"检测到连接断开或超时，停止播放")
                        return False
                    # 其他错误继续尝试
                    # 添加错误计数，避免无限重试
                    if not hasattr(self, '_error_count'):
                        self._error_count = 0
                    self._error_count += 1
                    if self._error_count > 5:  # 最多允许5次错误
                        logger.error(f"错误次数过多 ({self._error_count})，停止播放")
                        return False

                # 更新播放位置
                play_position += 1

            # 播放完成
            logger.info(f"音频播放完成: {len(frames)}帧 (累计发送: {sent_frames}帧, {total_bytes}字节)")
            return True

        except Exception as e:
            logger.error(f"播放opus帧异常: {str(e)}")
            return False

# 简单测试
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    converter = OpusConvertor(debug=True)

    # 测试文件转换
    test_file = "samples/output_1.wav"  # 替换为实际文件
    if os.path.exists(test_file):
        frames, duration = converter.audio_to_opus_frames(test_file)
        print(f"转换完成: {len(frames)}帧, {duration}秒")

        # 打印每个帧的大小
        for i, frame in enumerate(frames[:5]):  # 只显示前5帧
            print(f"帧 {i}: {len(frame)} 字节")

        if len(frames) > 5:
            print(f"... 还有 {len(frames)-5} 帧")
    else:
        print(f"测试文件不存在: {test_file}")