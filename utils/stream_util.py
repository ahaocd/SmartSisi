from io import BytesIO
import threading
import functools
import queue
import time
from typing import Optional, List

def synchronized(func):
  @functools.wraps(func)
  def wrapper(self, *args, **kwargs):
    with self.lock:
      return func(self, *args, **kwargs)
  return wrapper

class StreamCache:
    def __init__(self, maxbytes):
        self.lock = threading.Lock()
        self.bytesio = BytesIO()
        self.writeSeek = 0
        self.readSeek = 0
        self.maxbytes = maxbytes
        self.idle = 0
        
    @synchronized
    def write(self, bs):
        # print("写:{},{}".format(len(bs),bs), end=' ')
        if self.idle >= self.maxbytes:
            print("缓存区不够用")
        self.bytesio.seek(self.writeSeek)
        if self.writeSeek + len(bs) <= self.maxbytes:
            self.bytesio.write(bs)
        else:
            self.bytesio.write(bs[0:self.maxbytes - self.writeSeek])
            self.bytesio.seek(0)
            self.bytesio.write(bs[self.maxbytes - self.writeSeek:])
        self.idle += len(bs)
        self.writeSeek = self.bytesio.tell()
        if self.writeSeek >= self.maxbytes - 1:
            self.writeSeek = 0

    
    @synchronized
    def read(self, length, exception_on_overflow = False):
        if self.idle < length:
            return None
        # print("读:{}".format(length), end=' ')
        self.bytesio.seek(self.readSeek)
        if self.readSeek + length <= self.maxbytes:
            bs = self.bytesio.read(length)
        else:
            bs = self.bytesio.read(self.maxbytes - self.readSeek)
            self.bytesio.seek(0)
            bs.append(self.bytesio.read(self.readSeek + length - self.maxbytes))

        self.idle -= length
        self.readSeek = self.bytesio.tell()
        if self.readSeek >= self.maxbytes - 1:
           self.readSeek = 0
        return bs

    @synchronized
    def clear(self):
        self.bytesio = BytesIO()
        self.writeSeek = 0
        self.readSeek = 0
        self.idle = 0

# 添加统一的音频流处理工具
class AudioManagerUtil:
    """音频管理工具类 - 提供统一的音频处理功能"""
    
    # 音频参数配置
    SAMPLE_RATE = 16000  # 采样率
    FRAME_DURATION = 60  # 帧时长(ms)
    FRAME_SIZE = 960     # 帧大小(samples)
    PRE_BUFFER_FRAMES = 3  # 预缓冲帧数
    
    # 音频标记帧常量
    AUDIO_START_MARKER = bytes([0x01, 0x00, 0x00, 0x00]) + bytes([0x00] * 28)  # 音频开始标记 (32字节)
    AUDIO_END_MARKER = bytes([0x02, 0x00, 0x00, 0x00]) + bytes([0x00] * 28)    # 音频结束标记 (32字节)
    HEARTBEAT_MARKER = bytes([0x03, 0x00, 0x00, 0x00]) + bytes([0x00] * 28)    # 心跳标记 (32字节)
    
    @staticmethod
    def split_audio_to_frames(audio_data: bytes) -> List[bytes]:
        """将音频数据分割为帧
        Args:
            audio_data: 音频数据
        Returns:
            List[bytes]: 音频帧列表
        """
        frames = []
        for i in range(0, len(audio_data), AudioManagerUtil.FRAME_SIZE):
            frame = audio_data[i:i+AudioManagerUtil.FRAME_SIZE]
            if frame:
                frames.append(frame)
        return frames
    
    @staticmethod
    def add_markers_to_frames(frames: List[bytes]) -> List[bytes]:
        """为音频帧添加开始和结束标记
        Args:
            frames: 音频帧列表
        Returns:
            List[bytes]: 添加标记后的音频帧列表
        """
        if not frames:
            return []
        
        # 添加开始标记
        result = [AudioManagerUtil.AUDIO_START_MARKER]
        
        # 添加预缓冲帧
        pre_buffer_count = min(AudioManagerUtil.PRE_BUFFER_FRAMES, len(frames))
        result.extend(frames[:pre_buffer_count])
        
        # 添加剩余帧
        result.extend(frames[pre_buffer_count:])
        
        # 添加结束标记
        result.append(AudioManagerUtil.AUDIO_END_MARKER)
        
        return result
    
    @staticmethod
    def convert_to_opus_frames(audio_file: str) -> Optional[List[bytes]]:
        """将音频文件转换为OPUS帧（保持与xiaozhi-server一致的实现）
        Args:
            audio_file: 音频文件路径
        Returns:
            List[bytes]: OPUS帧列表或None
        """
        try:
            # 检查文件是否存在
            import os
            if not os.path.exists(audio_file):
                print(f"[音频工具] 音频文件不存在: {audio_file}")
                return None
            
            # 🔥 直接使用xiaozhi-server风格的实现
            try:
                from core.utils.util import audio_to_data
                opus_frames = audio_to_data(audio_file, is_opus=True)
                return opus_frames
            except ImportError:
                # 备用方案：使用本地opus_helper
                try:
                    from esp32_liusisi.opus_helper import OpusConvertor
                    # 🔥 修复：创建单例OpusConvertor实例，避免重复初始化
                    if not hasattr(AudioManagerUtil, '_opus_converter'):
                        AudioManagerUtil._opus_converter = OpusConvertor()
                    opus_helper = AudioManagerUtil._opus_converter
                    opus_frames, duration = opus_helper.audio_to_opus_frames(audio_file)
                    return opus_frames
                except ImportError:
                    print("[音频工具] OpusConvertor不可用，使用备用方案")
                    # 备用方案：直接读取文件
                    with open(audio_file, 'rb') as f:
                        audio_data = f.read()
                    return [audio_data]
        except Exception as e:
            print(f"[音频工具] 音频转换失败: {e}")
            return None

if __name__ == '__main__':
    streamCache = StreamCache(5)
    streamCache.write(b'\x01\x02')
    streamCache.write(b'\x03\x04\x00')
    print(streamCache.read(2))
    print(streamCache.read(3))
    streamCache.write(b'\x05\x06')
    print(streamCache.read(2))
    print(streamCache.read(2))
    print(streamCache.read(3))