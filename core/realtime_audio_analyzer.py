#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于GitHub最新项目的实时音频分析器
参考：aiXander/Realtime_PyAudio_FFT (2024)
功能：一边播放音乐一边实时分析频谱并发送到ESP32
"""

import numpy as np
import threading
import time
import wave
import os
from typing import List, Optional, Callable
import logging

# 音频库检测
try:
    import librosa
    LIBROSA_AVAILABLE = True
    print("✅ librosa可用 - 使用专业音频分析")
except ImportError:
    LIBROSA_AVAILABLE = False
    print("⚠️ librosa未安装 - 使用基础分析")

class RealtimeAudioAnalyzer:
    """
    基于2024年最新GitHub项目的实时音频分析器
    特点：一边播放一边分析，真正的实时处理
    """
    
    def __init__(self, sample_rate: int = 22050, chunk_size: int = 1024):
        """
        初始化实时音频分析器
        
        Args:
            sample_rate: 采样率
            chunk_size: 每次分析的音频块大小
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.n_fft = 2048  # FFT窗口大小
        
        # 音频数据
        self.audio_data = None
        self.audio_duration = 0.0
        self.total_frames = 0
        
        # 实时分析状态
        self.is_analyzing = False
        self.analysis_thread = None
        self.stop_event = threading.Event()
        
        # 播放同步
        self.start_time = None
        self.current_position = 0
        
        # 回调和数据
        self.spectrum_callback = None
        self.latest_spectrum_data = None
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
    def load_audio_file(self, file_path: str) -> bool:
        """
        加载音频文件
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            bool: 加载成功返回True
        """
        try:
            self.logger.info(f"🎵 加载音频文件: {file_path}")
            
            if not os.path.exists(file_path):
                self.logger.error(f"❌ 文件不存在: {file_path}")
                return False
            
            # 优先使用librosa
            if LIBROSA_AVAILABLE:
                try:
                    self.audio_data, _ = librosa.load(
                        file_path, 
                        sr=self.sample_rate,
                        mono=True
                    )
                    self.total_frames = len(self.audio_data)
                    self.audio_duration = self.total_frames / self.sample_rate
                    self.logger.info(f"✅ librosa加载成功: {self.total_frames} 帧, {self.audio_duration:.2f} 秒")
                    return True
                except Exception as e:
                    self.logger.warning(f"⚠️ librosa加载失败: {e}，尝试wave方法")
            
            # 备选：使用wave库
            if file_path.lower().endswith('.wav'):
                try:
                    with wave.open(file_path, 'rb') as wav_file:
                        frames = wav_file.readframes(-1)
                        sample_rate = wav_file.getframerate()
                        
                        # 转换为float32
                        if wav_file.getsampwidth() == 2:  # 16-bit
                            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                        else:
                            audio_data = np.frombuffer(frames, dtype=np.float32)
                        
                        # 重采样到目标采样率
                        if sample_rate != self.sample_rate:
                            step = sample_rate / self.sample_rate
                            indices = np.arange(0, len(audio_data), step).astype(int)
                            audio_data = audio_data[indices]
                        
                        self.audio_data = audio_data
                        self.total_frames = len(self.audio_data)
                        self.audio_duration = self.total_frames / self.sample_rate
                        
                        self.logger.info(f"✅ wave加载成功: {self.total_frames} 帧, {self.audio_duration:.2f} 秒")
                        return True
                        
                except Exception as e:
                    self.logger.error(f"❌ wave加载失败: {e}")
            
            return False
            
        except Exception as e:
            self.logger.error(f"❌ 音频文件加载失败: {e}")
            return False
    
    def set_spectrum_callback(self, callback: Callable[[List[int]], None]):
        """设置频谱数据回调函数"""
        self.spectrum_callback = callback
    
    def start_realtime_analysis(self, update_interval: float = 0.1) -> bool:
        """
        启动实时音频分析
        
        Args:
            update_interval: 更新间隔（秒）
            
        Returns:
            bool: 启动成功返回True
        """
        if self.audio_data is None:
            self.logger.error("❌ 请先加载音频文件")
            return False
            
        if self.is_analyzing:
            self.logger.warning("⚠️ 分析已在进行中")
            return False
        
        self.stop_event.clear()
        self.is_analyzing = True
        self.start_time = time.time()
        self.current_position = 0
        
        # 启动实时分析线程
        self.analysis_thread = threading.Thread(
            target=self._realtime_analysis_loop,
            args=(update_interval,),
            daemon=True
        )
        self.analysis_thread.start()
        
        self.logger.info(f"🚀 实时分析已启动，更新间隔: {update_interval}秒")
        return True
    
    def _realtime_analysis_loop(self, update_interval: float):
        """
        实时分析循环 - 基于播放时间同步分析
        """
        try:
            while self.is_analyzing and not self.stop_event.is_set():
                # 计算当前播放时间
                current_time = time.time() - self.start_time
                
                # 计算对应的音频位置
                audio_position = int(current_time * self.sample_rate)
                
                if audio_position >= self.total_frames:
                    # 音频播放完毕
                    self.logger.info("🎵 音频分析完成")
                    break
                
                # 提取当前时间的音频块
                start_pos = max(0, audio_position - self.chunk_size // 2)
                end_pos = min(start_pos + self.n_fft, self.total_frames)
                
                if end_pos - start_pos < self.chunk_size:
                    # 数据不够，填充零
                    audio_chunk = np.zeros(self.n_fft)
                    chunk_size = end_pos - start_pos
                    if chunk_size > 0:
                        audio_chunk[:chunk_size] = self.audio_data[start_pos:end_pos]
                else:
                    audio_chunk = self.audio_data[start_pos:end_pos]
                
                # 分析频谱
                spectrum_data = self._analyze_spectrum(audio_chunk)
                
                # 存储最新数据
                self.latest_spectrum_data = spectrum_data
                
                # 调用回调函数
                if self.spectrum_callback:
                    self.spectrum_callback(spectrum_data)
                
                # 等待下一次更新
                time.sleep(update_interval)
                
        except Exception as e:
            self.logger.error(f"❌ 实时分析循环错误: {e}")
        finally:
            self.is_analyzing = False
    
    def _analyze_spectrum(self, audio_chunk: np.ndarray) -> List[int]:
        """
        分析音频频谱 - 基于GitHub最新项目的方法
        
        Args:
            audio_chunk: 音频数据块
            
        Returns:
            List[int]: 8个频段的强度值 (0-255)
        """
        try:
            # 应用窗函数
            windowed = audio_chunk * np.hanning(len(audio_chunk))
            
            # FFT变换
            fft_data = np.fft.fft(windowed)
            
            # 计算幅度谱
            magnitude = np.abs(fft_data[:len(fft_data)//2])
            
            # 定义8个频段（基于音乐频率分布）
            freq_bins = len(magnitude)
            nyquist = self.sample_rate / 2
            
            # 频段范围（Hz）
            freq_ranges = [
                (20, 250),      # 低频：鼓、贝斯
                (250, 500),     # 中低频：男声、低音乐器
                (500, 1000),    # 中频：人声主要区域
                (1000, 2000),   # 中高频：人声高音、乐器
                (2000, 4000),   # 高频：乐器高音、和声
                (4000, 8000),   # 超高频：细节、空气感
                (8000, 16000),  # 极高频：空气感、细节
                (16000, 22000)  # 超极高频：空气感
            ]
            
            spectrum_8bands = []
            
            for low_freq, high_freq in freq_ranges:
                # 计算频段对应的FFT bin范围
                low_bin = int(low_freq * freq_bins / nyquist)
                high_bin = int(high_freq * freq_bins / nyquist)
                
                # 确保bin范围有效
                low_bin = max(0, low_bin)
                high_bin = min(freq_bins - 1, high_bin)
                
                if high_bin > low_bin:
                    # 计算该频段的平均能量
                    band_energy = np.mean(magnitude[low_bin:high_bin])
                else:
                    band_energy = 0
                
                spectrum_8bands.append(band_energy)
            
            # 🔥 修复：使用dancyPi的自适应增益算法，不用dB！
            if max(spectrum_8bands) > 0:
                spectrum_8bands = np.array(spectrum_8bands, dtype=float)

                # 🎵 步骤1：初始化自适应增益滤波器
                if not hasattr(self, 'gain_filter'):
                    # 创建ExpFilter类
                    class ExpFilter:
                        def __init__(self, val=0.01, alpha_decay=0.01, alpha_rise=0.99):
                            self.alpha_decay = alpha_decay
                            self.alpha_rise = alpha_rise
                            self.value = val

                        def update(self, value):
                            alpha = self.alpha_rise if value > self.value else self.alpha_decay
                            self.value = alpha * value + (1.0 - alpha) * self.value
                            return self.value

                    self.gain_filter = ExpFilter(val=0.01, alpha_decay=0.01, alpha_rise=0.99)

                # 🎵 步骤2：自适应增益归一化（dancyPi算法）
                # 计算当前最大能量
                current_max = np.max(spectrum_8bands)

                # 更新增益滤波器
                self.gain_filter.update(current_max)

                # 归一化：除以滤波后的增益值
                if self.gain_filter.value > 1e-10:
                    spectrum_8bands = spectrum_8bands / self.gain_filter.value
                else:
                    spectrum_8bands = spectrum_8bands * 0  # 避免除零

                # 🎵 步骤3：缩放到0-255范围
                spectrum_8bands = spectrum_8bands * 255.0

                # 🎵 步骤4：限制范围并应用噪声门限
                spectrum_8bands = np.clip(spectrum_8bands, 0, 255)

                # 简单噪声门限：低于10的值设为0
                spectrum_8bands = np.where(spectrum_8bands < 10, 0, spectrum_8bands)

                spectrum_8bands = spectrum_8bands.astype(int)
            else:
                spectrum_8bands = [0] * 8  # 静音时完全关闭
            
            # 转换为整数列表
            result = [int(val) for val in spectrum_8bands]
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ 频谱分析失败: {e}")
            # 返回默认值
            return [128, 120, 110, 100, 90, 80, 70, 60]
    
    def stop_analysis(self):
        """停止实时分析"""
        if not self.is_analyzing:
            return
            
        self.logger.info("🛑 停止实时音频分析")
        self.stop_event.set()
        self.is_analyzing = False
        
        # 等待线程结束
        if self.analysis_thread and self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=1.0)
            
        self.logger.info("✅ 实时音频分析已停止")
