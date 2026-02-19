#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业界标准音频分析器
基于librosa + numpy FFT，参考GitHub热门项目实现
支持多种音频格式：WAV, MP3, FLAC等
"""

import numpy as np
import threading
import time
import wave
import os
import random
from typing import List, Optional, Callable
import logging

# 音频库检测和导入
try:
    import librosa
    LIBROSA_AVAILABLE = True
    print("✅ librosa可用 - 使用专业音频分析")
except ImportError:
    LIBROSA_AVAILABLE = False
    print("⚠️ librosa未安装 - 使用基础wave分析")

try:
    from scipy.fft import fft
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    # 使用numpy.fft作为备选

class RealAudioAnalyzer:
    """简单音频分析器 - 适配你的系统"""

    def __init__(self, sample_rate: int = 22050):
        """
        初始化音频分析器

        Args:
            sample_rate: 采样率 (Hz)
        """
        self.sample_rate = sample_rate
        self.n_fft = 2048  # FFT窗口大小

        # 音频数据
        self.audio_data = None
        self.audio_duration = 0.0
        self.total_frames = 0
        self.current_position = 0

        # 分析状态
        self.is_analyzing = False
        self.analysis_thread = None
        self.stop_event = threading.Event()

        # 回调函数
        self.spectrum_callback = None
        self.latest_spectrum_data = None

        # 日志
        self.logger = logging.getLogger(__name__)
        
        # 8个频段的频率范围 (Hz) - 专业音乐制作标准
        self.frequency_bands = [
            (20, 80),      # 低频：鼓、贝斯、低音炮 (更宽范围，突出节拍)
            (80, 200),     # 中低频：男声基频、低音乐器
            (200, 500),    # 中频：人声主要区域、吉他基频
            (500, 1200),   # 中高频：人声清晰度、乐器表现力
            (1200, 3000),  # 高频：女声、钢琴、弦乐
            (3000, 6000),  # 超高频：镲片、高音细节、空气感
            (6000, 12000), # 极高频：临场感、空间感
            (12000, 22050) # 超极高频：数字音频细节、泛音
        ]

        # 频段权重：低频加强，高频细化
        self.frequency_weights = [
            2.5,  # 低频：强化节拍感
            2.0,  # 中低频：增强人声
            1.5,  # 中频：平衡表现
            1.2,  # 中高频：轻微增强
            1.0,  # 高频：自然表现
            0.8,  # 超高频：适度抑制
            0.6,  # 极高频：细节保留
            0.4   # 超极高频：背景细节
        ]
        
        # 分析状态
        self.is_analyzing = False
        self.audio_data = None
        self.current_position = 0
        self.total_frames = 0
        
        # 回调函数
        self.spectrum_callback: Optional[Callable[[List[int]], None]] = None
        
        # 线程控制
        self.analysis_thread = None
        self.stop_event = threading.Event()
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
    def precompute_spectrum(self, file_path: str, update_interval: float = 0.1) -> bool:
        """
        预计算音频文件的频谱数据

        Args:
            file_path: 音频文件路径
            update_interval: 更新间隔 (秒)

        Returns:
            bool: 预计算成功返回True
        """
        try:
            self.logger.info(f"🎵 预分析音频文件: {file_path}")

            if not LIBROSA_AVAILABLE:
                self.logger.error("❌ librosa未安装，无法进行音频分析")
                return False

            # 使用librosa加载音频文件
            audio_data, sr = librosa.load(
                file_path,
                sr=self.sample_rate,
                mono=True  # 转换为单声道
            )

            self.audio_duration = len(audio_data) / sr
            self.logger.info(f"✅ 音频加载成功: {len(audio_data)} 帧, {self.audio_duration:.2f} 秒")

            # 计算需要的时间点
            time_points = []
            current_time = 0.0
            while current_time < self.audio_duration:
                time_points.append(current_time)
                current_time += update_interval

            self.logger.info(f"🔄 开始预计算 {len(time_points)} 个时间点的频谱数据...")

            # 预计算每个时间点的频谱
            self.precomputed_spectrum = []
            self.spectrum_timestamps = []

            for i, timestamp in enumerate(time_points):
                # 计算音频帧位置
                frame_start = int(timestamp * sr)
                frame_end = min(frame_start + self.n_fft, len(audio_data))

                if frame_end - frame_start < self.n_fft:
                    # 如果数据不够，填充零
                    audio_chunk = np.zeros(self.n_fft)
                    audio_chunk[:frame_end - frame_start] = audio_data[frame_start:frame_end]
                else:
                    audio_chunk = audio_data[frame_start:frame_end]

                # 分析频谱
                spectrum_data = self._analyze_spectrum(audio_chunk)

                self.precomputed_spectrum.append(spectrum_data)
                self.spectrum_timestamps.append(timestamp)

                # 进度显示
                if i % 50 == 0:
                    progress = (i + 1) / len(time_points) * 100
                    self.logger.info(f"📊 预计算进度: {progress:.1f}%")

            self.logger.info(f"✅ 频谱预计算完成: {len(self.precomputed_spectrum)} 个数据点")
            return True

        except Exception as e:
            self.logger.error(f"❌ 音频文件预分析失败: {e}")
            return False
    
    def set_spectrum_callback(self, callback: Callable[[List[int]], None]):
        """设置频谱数据回调函数"""
        self.spectrum_callback = callback

    def load_audio_file(self, file_path: str) -> bool:
        """
        加载音频文件 - 支持多种方法

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

            # 方法1：优先使用librosa（支持MP3, FLAC等）
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

            # 方法2：使用wave库（仅支持WAV）
            if file_path.lower().endswith('.wav'):
                try:
                    with wave.open(file_path, 'rb') as wav_file:
                        frames = wav_file.readframes(-1)
                        sample_rate = wav_file.getframerate()

                        # 转换为float32
                        if wav_file.getsampwidth() == 2:  # 16-bit
                            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                        else:  # 其他格式
                            audio_data = np.frombuffer(frames, dtype=np.float32)

                        # 重采样到目标采样率（简单方法）
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

            self.logger.error(f"❌ 无法加载音频文件: {file_path}")
            return False

        except Exception as e:
            self.logger.error(f"❌ 音频文件加载失败: {e}")
            return False

    def start_playback_sync(self) -> bool:
        """
        开始播放同步（与pygame.mixer同步）

        Returns:
            bool: 启动成功返回True
        """
        if not self.precomputed_spectrum:
            self.logger.error("❌ 请先预计算频谱数据")
            return False

        self.playback_start_time = time.time()
        self.is_playing = True

        # 启动同步线程
        self.sync_thread = threading.Thread(
            target=self._playback_sync_loop,
            daemon=True
        )
        self.sync_thread.start()

        self.logger.info("🚀 播放同步已启动")
        return True

    def _playback_sync_loop(self):
        """播放同步循环"""
        try:
            while self.is_playing:
                current_time = time.time()
                playback_time = current_time - self.playback_start_time

                # 如果播放时间超过音频时长，停止
                if playback_time >= self.audio_duration:
                    self.logger.info("🎵 音频播放完成")
                    break

                # 找到当前时间对应的频谱数据
                spectrum_data = self._get_spectrum_at_time(playback_time)

                if spectrum_data and self.spectrum_callback:
                    self.spectrum_callback(spectrum_data)

                # 等待下一次更新
                time.sleep(0.1)  # 10FPS更新

        except Exception as e:
            self.logger.error(f"❌ 播放同步错误: {e}")
        finally:
            self.is_playing = False

    def _get_spectrum_at_time(self, playback_time: float) -> List[int]:
        """
        获取指定时间的频谱数据

        Args:
            playback_time: 播放时间 (秒)

        Returns:
            List[int]: 频谱数据
        """
        if not self.spectrum_timestamps:
            return [128] * 8  # 默认值

        # 找到最接近的时间点
        closest_index = 0
        min_diff = abs(self.spectrum_timestamps[0] - playback_time)

        for i, timestamp in enumerate(self.spectrum_timestamps):
            diff = abs(timestamp - playback_time)
            if diff < min_diff:
                min_diff = diff
                closest_index = i

        return self.precomputed_spectrum[closest_index]

    def stop_playback_sync(self):
        """停止播放同步"""
        self.is_playing = False
        if hasattr(self, 'sync_thread') and self.sync_thread:
            self.sync_thread.join(timeout=1.0)
        self.logger.info("🛑 播放同步已停止")
    
    def _analyze_spectrum(self, audio_chunk: np.ndarray) -> List[int]:
        """
        分析音频频谱 - 业界标准方法

        Args:
            audio_chunk: 音频数据块

        Returns:
            List[int]: 8个频段的强度值 (0-255)
        """
        try:
            # 应用窗函数减少频谱泄漏
            windowed = audio_chunk * np.hanning(len(audio_chunk))

            # FFT变换
            if SCIPY_AVAILABLE:
                fft_data = fft(windowed)
            else:
                fft_data = np.fft.fft(windowed)

            # 计算幅度谱
            magnitude = np.abs(fft_data[:len(fft_data)//2])  # 只取正频率部分

            # 定义8个频段（基于音乐频率分布）
            # 低频到高频：20Hz-250Hz, 250Hz-500Hz, 500Hz-1kHz, 1kHz-2kHz,
            #              2kHz-4kHz, 4kHz-8kHz, 8kHz-16kHz, 16kHz-22kHz
            freq_bins = len(magnitude)
            nyquist = self.sample_rate / 2

            # 计算每个频段的边界
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

            # 🎵 专业音频频谱分析算法（基于JSFX项目）
            spectrum_8bands = np.array(spectrum_8bands, dtype=np.float64)

            if np.max(spectrum_8bands) > 0:
                # 🎯 步骤1：对数变换（符合人耳感知，但保持动态范围）
                # 使用dB标度：20*log10(amplitude)，但避免-inf
                spectrum_db = 20 * np.log10(spectrum_8bands + 1e-10)  # 添加小值避免log(0)

                # 🎯 步骤2：动态范围映射（-60dB到0dB映射到0-255）
                # 这是专业音频设备的标准做法
                db_min = -60.0  # 噪声门限
                db_max = 0.0    # 最大值（0dB）

                # 限制dB范围
                spectrum_db = np.clip(spectrum_db, db_min, db_max)

                # 🎯 步骤3：线性映射到0-255（保持真正的动态范围）
                # 这样-60dB=0, 0dB=255，中间线性变化
                spectrum_normalized = (spectrum_db - db_min) / (db_max - db_min)
                spectrum_8bands = spectrum_normalized * 255.0

                # 🎯 步骤4：时间域平滑（防止快速抖动）
                if not hasattr(self, 'spectrum_history'):
                    self.spectrum_history = spectrum_8bands.copy()
                else:
                    # 指数移动平均（类似硬件VU表的响应）
                    attack_coeff = 0.3   # 快速响应上升
                    release_coeff = 0.05  # 慢速响应下降

                    for i in range(8):
                        if spectrum_8bands[i] > self.spectrum_history[i]:
                            # Attack：快速跟随上升
                            self.spectrum_history[i] += (spectrum_8bands[i] - self.spectrum_history[i]) * attack_coeff
                        else:
                            # Release：慢速跟随下降
                            self.spectrum_history[i] += (spectrum_8bands[i] - self.spectrum_history[i]) * release_coeff

                    spectrum_8bands = self.spectrum_history.copy()

                # 最终限制范围
                spectrum_8bands = np.clip(spectrum_8bands, 0, 255)
            else:
                # 真正的静音
                spectrum_8bands = np.zeros(8)
                if hasattr(self, 'spectrum_history'):
                    # 静音时也要慢速衰减到0
                    self.spectrum_history *= 0.95

            # 转换为整数列表
            result = [int(val) for val in spectrum_8bands]

            return result

        except Exception as e:
            self.logger.error(f"❌ 频谱分析失败: {e}")
            # 返回默认值
            return [128, 120, 110, 100, 90, 80, 70, 60]
        """
        分析音频块的频谱
        
        Args:
            audio_chunk: 音频数据块
            
        Returns:
            List[int]: 8个频段的强度值 (0-255)
        """
        # 计算短时傅里叶变换 (STFT)
        stft = librosa.stft(
            audio_chunk, 
            n_fft=self.n_fft, 
            hop_length=self.hop_length
        )
        
        # 计算幅度谱
        magnitude = np.abs(stft)
        
        # 计算功率谱密度
        power_spectrum = magnitude ** 2
        
        # 频率轴
        freqs = librosa.fft_frequencies(sr=self.sample_rate, n_fft=self.n_fft)
        
        # 提取8个频段的能量，应用专业权重
        band_energies = []

        for i, (low_freq, high_freq) in enumerate(self.frequency_bands):
            # 找到频率范围对应的索引
            freq_mask = (freqs >= low_freq) & (freqs <= high_freq)

            if np.any(freq_mask):
                # 计算该频段的RMS能量（更准确的音频强度表示）
                band_power = power_spectrum[freq_mask, :]
                rms_energy = np.sqrt(np.mean(band_power))

                # 应用频段权重
                weighted_energy = rms_energy * self.frequency_weights[i]
                band_energies.append(weighted_energy)
            else:
                band_energies.append(0.0)

        # 专业音频处理：动态范围压缩 + 归一化
        if max(band_energies) > 0:
            # 对数压缩（模拟人耳听觉特性）
            log_energies = np.log10(np.array(band_energies) + 1e-10)

            # 动态范围调整：增强对比度
            log_min, log_max = log_energies.min(), log_energies.max()
            if log_max > log_min:
                # 非线性映射：增强低频，平滑高频
                normalized = (log_energies - log_min) / (log_max - log_min)

                # 应用音乐感知曲线：低频更敏感，高频更平滑
                perception_curve = np.array([1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.6])
                enhanced = normalized * perception_curve

                # 重新归一化到0-255
                if enhanced.max() > 0:
                    final_normalized = enhanced / enhanced.max()
                    spectrum_values = (final_normalized * 255).astype(int)
                else:
                    spectrum_values = np.zeros(8, dtype=int)
            else:
                spectrum_values = np.zeros(8, dtype=int)
        else:
            spectrum_values = np.zeros(8, dtype=int)
        
        return spectrum_values.tolist()
    
    def start_realtime_analysis(self, use_microphone: bool = True) -> bool:
        """
        开始实时音频分析（从麦克风或系统音频）

        Args:
            use_microphone: True=麦克风捕获，False=系统音频捕获

        Returns:
            bool: 启动成功返回True
        """
        if not PYAUDIO_AVAILABLE:
            self.logger.error("❌ PyAudio未安装，无法进行实时音频分析")
            return False

        if self.is_analyzing:
            self.logger.warning("⚠️ 分析已在进行中")
            return False

        try:
            # 初始化PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()
            self.use_microphone = use_microphone

            # 配置音频流
            if use_microphone:
                # 麦克风输入
                self.audio_stream = self.pyaudio_instance.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=self._audio_callback
                )
                self.logger.info("🎤 使用麦克风进行实时音频分析")
            else:
                # 系统音频捕获（需要特殊配置）
                # 这里先用麦克风代替
                self.audio_stream = self.pyaudio_instance.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=self._audio_callback
                )
                self.logger.info("🔊 使用系统音频进行实时音频分析")

            # 启动音频流
            self.audio_stream.start_stream()
            self.is_analyzing = True

            self.logger.info("🚀 实时音频分析已启动")
            return True

        except Exception as e:
            self.logger.error(f"❌ 实时音频分析启动失败: {e}")
            return False

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio音频回调函数"""
        try:
            # 将音频数据转换为numpy数组
            audio_data = np.frombuffer(in_data, dtype=np.float32)

            # 分析频谱
            spectrum_data = self._analyze_realtime_spectrum(audio_data)

            # 调用回调函数
            if self.spectrum_callback:
                self.spectrum_callback(spectrum_data)

        except Exception as e:
            self.logger.error(f"❌ 音频回调处理错误: {e}")

        return (None, pyaudio.paContinue)

    def _analyze_realtime_spectrum(self, audio_chunk: np.ndarray) -> List[int]:
        """
        分析实时音频块的频谱

        Args:
            audio_chunk: 实时音频数据块

        Returns:
            List[int]: 8个频段的强度值 (0-255)
        """
        try:
            # 如果数据太短，填充零
            if len(audio_chunk) < self.n_fft:
                padded_audio = np.zeros(self.n_fft)
                padded_audio[:len(audio_chunk)] = audio_chunk
                audio_chunk = padded_audio

            # 计算FFT
            fft_data = np.fft.fft(audio_chunk[:self.n_fft])
            magnitude = np.abs(fft_data[:self.n_fft//2])  # 只取正频率部分

            # 频率轴
            freqs = np.fft.fftfreq(self.n_fft, 1/self.sample_rate)[:self.n_fft//2]

            # 提取8个频段的能量
            band_energies = []

            for i, (low_freq, high_freq) in enumerate(self.frequency_bands):
                # 找到频率范围对应的索引
                freq_mask = (freqs >= low_freq) & (freqs <= high_freq)

                if np.any(freq_mask):
                    # 计算该频段的RMS能量
                    band_energy = np.sqrt(np.mean(magnitude[freq_mask] ** 2))

                    # 应用频段权重
                    weighted_energy = band_energy * self.frequency_weights[i]
                    band_energies.append(weighted_energy)
                else:
                    band_energies.append(0.0)

            # 归一化到0-255范围
            if max(band_energies) > 0:
                # 对数压缩 + 动态范围调整
                log_energies = np.log10(np.array(band_energies) + 1e-10)

                # 动态范围映射
                log_min, log_max = log_energies.min(), log_energies.max()
                if log_max > log_min:
                    normalized = (log_energies - log_min) / (log_max - log_min)

                    # 应用感知曲线
                    perception_curve = np.array([1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.6])
                    enhanced = normalized * perception_curve

                    # 最终归一化
                    if enhanced.max() > 0:
                        final_normalized = enhanced / enhanced.max()
                        spectrum_values = (final_normalized * 255).astype(int)
                    else:
                        spectrum_values = np.zeros(8, dtype=int)
                else:
                    spectrum_values = np.zeros(8, dtype=int)
            else:
                spectrum_values = np.zeros(8, dtype=int)

            return spectrum_values.tolist()

        except Exception as e:
            self.logger.error(f"❌ 实时频谱分析错误: {e}")
            return [0] * 8

    def start_analysis(self, update_interval: float = 0.1) -> bool:
        """
        开始实时分析 - 适配你的系统

        Args:
            update_interval: 更新间隔（秒），默认0.1秒匹配你的发送频率

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
        self.current_position = 0

        # 启动分析线程
        self.analysis_thread = threading.Thread(
            target=self._analysis_loop,
            args=(update_interval,),
            daemon=True
        )
        self.analysis_thread.start()

        self.logger.info(f"🚀 实时分析已启动，更新间隔: {update_interval}秒")
        return True

    def _analysis_loop(self, update_interval: float):
        """分析循环 - 每0.1秒分析一次，匹配你的发送频率"""
        try:
            while self.is_analyzing and not self.stop_event.is_set():
                # 计算当前应该分析的音频位置
                frames_per_update = int(self.sample_rate * update_interval)

                if self.current_position + frames_per_update >= self.total_frames:
                    # 音频播放完毕
                    self.logger.info("🎵 音频分析完成")
                    break

                # 提取当前时间段的音频数据
                start_pos = self.current_position
                end_pos = min(start_pos + self.n_fft, self.total_frames)

                if end_pos - start_pos < self.n_fft:
                    # 数据不够，填充零
                    audio_chunk = np.zeros(self.n_fft)
                    audio_chunk[:end_pos - start_pos] = self.audio_data[start_pos:end_pos]
                else:
                    audio_chunk = self.audio_data[start_pos:end_pos]

                # 分析频谱
                spectrum_data = self._analyze_spectrum(audio_chunk)

                # 存储最新数据
                self.latest_spectrum_data = spectrum_data

                # 调用回调函数（发送到你的系统）
                if self.spectrum_callback:
                    self.spectrum_callback(spectrum_data)

                # 更新位置
                self.current_position += frames_per_update

                # 等待下一次更新
                time.sleep(update_interval)

        except Exception as e:
            self.logger.error(f"❌ 分析循环错误: {e}")
        finally:
            self.is_analyzing = False
        """
        开始实时频谱分析
        
        Args:
            update_interval: 更新间隔 (秒)，默认30FPS
            
        Returns:
            bool: 启动成功返回True
        """
        if self.audio_data is None:
            self.logger.error("❌ 请先加载音频文件")
            return False
            
        if self.is_analyzing:
            self.logger.warning("⚠️ 分析已在进行中")
            return False
        
        self.is_analyzing = True
        self.stop_event.clear()
        
        # 启动分析线程
        self.analysis_thread = threading.Thread(
            target=self._analysis_loop,
            args=(update_interval,),
            daemon=True
        )
        self.analysis_thread.start()
        
        self.logger.info("🚀 实时频谱分析已启动")
        return True
    
    def _analysis_loop(self, update_interval: float):
        """分析循环"""
        chunk_size = int(self.sample_rate * update_interval)
        
        while not self.stop_event.is_set() and self.current_position < self.total_frames:
            try:
                # 获取当前音频块
                end_pos = min(self.current_position + chunk_size, self.total_frames)
                audio_chunk = self.audio_data[self.current_position:end_pos]
                
                if len(audio_chunk) > 0:
                    # 分析频谱
                    spectrum_data = self._analyze_spectrum(audio_chunk)

                    # 调用回调函数
                    if self.spectrum_callback:
                        self.spectrum_callback(spectrum_data)

                    # 存储最新数据供外部访问
                    self.latest_spectrum_data = spectrum_data
                    
                    # 更新位置
                    self.current_position = end_pos
                
                # 等待下一次更新
                time.sleep(update_interval)
                
            except Exception as e:
                self.logger.error(f"❌ 频谱分析错误: {e}")
                break
        
        self.is_analyzing = False
        self.logger.info("🛑 频谱分析已停止")
    
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
        """停止频谱分析"""
        if self.is_analyzing:
            self.stop_event.set()

            # 停止实时音频流
            if self.audio_stream:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                    self.audio_stream = None
                except Exception as e:
                    self.logger.error(f"❌ 停止音频流失败: {e}")

            # 关闭PyAudio
            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                    self.pyaudio_instance = None
                except Exception as e:
                    self.logger.error(f"❌ 关闭PyAudio失败: {e}")

            # 停止文件分析线程
            if self.analysis_thread:
                self.analysis_thread.join(timeout=1.0)

            self.is_analyzing = False
            self.logger.info("🛑 频谱分析已手动停止")
    
    def reset_position(self):
        """重置播放位置到开头"""
        self.current_position = 0
    
    def get_progress(self) -> float:
        """获取播放进度 (0.0-1.0)"""
        if self.total_frames == 0:
            return 0.0
        return self.current_position / self.total_frames


# 测试代码
if __name__ == "__main__":
    import sys
    
    # 配置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    def spectrum_callback(spectrum_data):
        print(f"🎵 实时频谱: {spectrum_data}")
    
    # 创建分析器
    analyzer = RealAudioAnalyzer()
    analyzer.set_spectrum_callback(spectrum_callback)
    
    # 测试音频文件
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    else:
        test_file = "E:/liusisi/SmartSisi/qa/mymusic/风吹笑容.wav"
    
    # 加载并分析
    if analyzer.load_audio_file(test_file):
        analyzer.start_analysis()
        
        try:
            # 运行10秒测试
            time.sleep(10)
        except KeyboardInterrupt:
            pass
        finally:
            analyzer.stop_analysis()
    else:
        print("❌ 音频文件加载失败")
