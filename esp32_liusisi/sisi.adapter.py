#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# sisi.adapter.py - ESP32 SiSi设备适配器
# 作者: sisi liu
# 日期: 2025-04-05
# 最近更新: 2025-05-09

import os
import sys
import json
import time
import asyncio
import traceback
import logging
import uuid
import functools
import threading
import importlib
import io
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Tuple, Union

# 确保当前目录在路径中，以便导入opus_helper
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 导入自定义工具
try:
    from opus_helper import OpusConvertor
    opus_helper_available = True
except ImportError:
    opus_helper_available = False
    print("警告: 无法导入opus_helper模块，将使用兼容模式")

import time
import traceback
import asyncio
import websockets
import uuid
import threading
import zipfile
import wave
import struct
import logging
import queue
from queue import Queue
import base64
import ctypes
import tempfile
import re
import glob
from datetime import datetime
from functools import partial
from typing import Dict, List, Optional, Any, Tuple, Union, Callable
from pathlib import Path
import importlib.util
import subprocess
try:
    from utils import config_util as cfg
except Exception:
    cfg = None

def _get_cache_root(fallback_root: str) -> str:
    if cfg:
        try:
            cfg.load_config()
        except Exception:
            pass
        cache_root = getattr(cfg, "cache_root", None)
        if cache_root:
            return cache_root
    return fallback_root


def _resolve_sisi_booter_module():
    """Resolve sisi_booter module from core first, then top-level fallback."""
    try:
        from core import sisi_booter as booter
        return booter
    except Exception:
        pass

    try:
        import sisi_booter as booter
        return booter
    except Exception:
        return None

# 🎵 导入S3CAM显示发送器
try:
    from oled_display_sender import S3CAMDisplaySender, SisiS3CAMIntegration
    s3cam_display_available = True
    print("✅ S3CAM显示发送器模块导入成功")
except ImportError as e:
    s3cam_display_available = False
    print(f"⚠️  S3CAM显示发送器模块导入失败: {e}")

# 直接导入sisi_audio_output模块，确保与TTS模块使用相同的类
try:
    from esp32_liusisi.sisi_audio_output import AudioOutputManager, AudioState
    print("✅ 成功导入AudioOutputManager和AudioState")
except ImportError as e:
    print(f"❌ 导入AudioOutputManager失败: {e}")
    # 创建临时类作为后备
    class AudioOutputManager:
        pass
    
    class AudioState:
        IDLE = "idle"
        PLAYING = "playing"
        PAUSED = "paused"
        ERROR = "error"

# 设置UTF-8编码环境
if sys.platform.startswith('win'):
    try:
        # Windows平台需要设置控制台编码为UTF-8
        ctypes.windll.kernel32.SetConsoleCP(65001)
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception as e:
        print(f"设置控制台编码失败: {e}")

# 确保能够访问上层目录
DIR_PATH = os.path.dirname(os.path.realpath(__file__))
ROOT_PATH = os.path.abspath(os.path.join(DIR_PATH, ".."))
sys.path.append(ROOT_PATH)

# 引入SISI框架模块
try:
    from core.recorder import Recorder
except ImportError as e:
    print(f"导入SmartSisi录音组件失败，请确认当前目录:{DIR_PATH}, 错误: {e}")
    try:
        # 尝试从相对路径导入
        sys.path.append("../")
        from core.recorder import Recorder
    except ImportError:
        print(f"尝试从相对路径导入录音组件也失败，ESP32将无法与语音识别集成")
        Recorder = type('DummyRecorder', (), {})  # 创建一个空的Recorder类

# 安全导入core.wsa_server模块
try:
    from core import wsa_server as core_wsa_server
except ImportError as e:
    print(f"导入SmartSisi WebUI接口失败: {e}，ESP32将无法与WebUI集成")
    core_wsa_server = None

# sisi_device_adapter.py
# ESP32 SiSi设备适配器 - 基于SiSi协议
# 作者: sisi liu
# 日期: 2025-04-02

import asyncio
import websockets
import json
import uuid
import os
import sys
import time
import threading
import traceback
import tempfile
import subprocess
import socket
import io
import numpy as np
import struct
import importlib
from multiprocessing import Queue
import wave

# 导入统一的音频工具
from utils.stream_util import AudioManagerUtil, StreamCache

# 使用统一的音频标记帧常量
AUDIO_START_MARKER = AudioManagerUtil.AUDIO_START_MARKER
AUDIO_END_MARKER = AudioManagerUtil.AUDIO_END_MARKER
HEARTBEAT_MARKER = AudioManagerUtil.HEARTBEAT_MARKER

# 🔥 修复：移除重复的pygame初始化，避免参数冲突导致顿挫
# pygame.mixer已在main.py中正确初始化，不需要重复初始化

# 设置opus.dll库路径
def setup_opus_dll():
    """设置OPUS库文件路径"""
    try:
        # 获取当前文件所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 构建opus.dll路径
        opus_dll_path = os.path.join(current_dir, "libs", "windows", "opus.dll")

        if os.path.exists(opus_dll_path):
            # 添加到环境变量PATH - 修复关键错误：sep改为pathsep
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + os.path.dirname(opus_dll_path)

            # 使用ctypes预加载库文件
            import ctypes
            try:
                ctypes.CDLL(opus_dll_path)
                print(f"OPUS库文件已加载: {opus_dll_path}")
                return True
            except Exception as e:
                print(f"加载OPUS库文件失败: {e}")
        else:
            print(f"OPUS库文件不存在: {opus_dll_path}")

        return False
    except Exception as e:
        print(f"设置OPUS库文件路径时出错: {e}")
        return False

# 尝试设置opus.dll
setup_opus_dll()

# 确保能访问SmartSisi核心模块
current_dir = os.path.dirname(os.path.abspath(__file__))
sisi_root = os.path.dirname(current_dir)
if sisi_root not in sys.path:
    sys.path.append(sisi_root)
import SmartSisi

if sisi_root not in sys.path:
    sys.path.append(sisi_root)
import SmartSisi




# 设置工作目录到Sisi根目录，确保能找到配置文件
os.chdir(sisi_root)
print(f"设置工作目录: {os.getcwd()}")
print(f"检查配置文件存在: {os.path.exists('config.json')}")

try:
    # 导入SmartSisi相关模块
    from utils import util, config_util
    from scheduler.thread_manager import MyThread
    from core import sisi_core
    from core.recorder import Recorder

    # 尝试导入OPUS库 - 添加更健壮的错误处理
    opuslib = None
    opus_import_error = None
    try:
        # 先尝试导入opuslib_next
        import opuslib_next as opuslib
        print("已加载OPUS库: opuslib_next")
    except Exception as e:
        opus_import_error = str(e)
        try:
            # 再尝试导入opuslib
            import opuslib
            print("已加载OPUS库: opuslib")
        except Exception as e2:
            opus_import_error += f"\n以及: {str(e2)}"
            print("注意: 未能加载OPUS库，将使用备选方案处理音频。")
            print(f"OPUS库错误详情: {opus_import_error}")
            print("Windows系统请安装：pip install opuslib-wheel")
            print("Linux系统请先安装：sudo apt-get install libopus-dev")
            opuslib = None
except ImportError as e:
    print(f"无法导入SmartSisi模块: {e}")
    print("请确保当前目录结构正确")
    sys.exit(1)

# 定义延迟导入Recorder类的函数
def _delayed_import_recorder():
    """延迟导入Recorder类，确保SISI子系统正确加载"""
    try:
        from core.recorder import Recorder
        return Recorder
    except ImportError as e:
        print(f"导入SmartSisi录音组件失败: {e}")
        return None

# 添加全局变量用于保存适配器实例
_ADAPTER_INSTANCE = None

def get_adapter_instance():
    """获取当前适配器实例"""
    global _ADAPTER_INSTANCE
    return _ADAPTER_INSTANCE

class SisiDeviceAdapter:
    """SiSi设备适配器 - 专注于设备通信功能"""

    def __init__(self, host='0.0.0.0', port=10000):
        """初始化适配器
        Args:
            host: 监听地址
            port: 监听端口
        """
        # 基础配置
        self.host = host
        self.port = port
        self.running = True

        # 设备状态管理
        self.clients = {}  # WebSocket连接
        self.devices = {}  # 设备信息
        self.listeners = {}  # 音频监听器

        # 音频管理器 - 🔥 修复：使用lambda包装回调函数确保正确的参数传递
        self.audio_manager = AudioOutputManager(
            data_callback=lambda data: self.handle_audio_data(data),
            state_callback=lambda state: self.handle_state_change(state)
        )

        # 获取SmartSisi根目录
        self.sisi_root = str(Path(__file__).parent.parent)

        # 🔧 首先初始化logger，避免后续调用出错
        self.logger = logging.getLogger("SisiAdapter")
        # 确保日志传递到根logger，不添加重复handler
        self.logger.propagate = True
        self.logger.setLevel(logging.INFO)

        # 单实例/幂等保护
        self.server = None
        self.server_running = False
        self.monitor_thread_running = False
        self.hook_registered = False

        # 统一发送通路：每连接唯一发送队列与协程
        self._sender_queues = {}  # client_id -> asyncio.Queue[bytes]
        self._sender_tasks = {}   # client_id -> asyncio.Task
        self._frame_duration_ms = 60

        # 🎵 初始化S3CAM显示发送器
        self.s3cam_sender = None
        self.s3cam_integration = None
        if s3cam_display_available:
            try:
                # 使用电脑热点IP (CMCC-H4m3网段)
                self.s3cam_sender = S3CAMDisplaySender("192.168.1.1")
                self.s3cam_integration = SisiS3CAMIntegration("192.168.1.1")
                self.log(1, "✅ S3CAM显示发送器初始化成功")
            except Exception as e:
                self.log(2, f"⚠️  S3CAM显示发送器初始化失败: {e}")

        # 初始化SmartSisi核心实例
        self.sisi_core_instance = None
        self._init_sisi_core()

        # 订阅TTS事件
        try:
            booter = _resolve_sisi_booter_module()
            if booter and hasattr(booter, 'subscribe_tts_event'):
                booter.subscribe_tts_event(self._on_tts_event)
                self.log(1, "已订阅TTS事件")
        except Exception as e:
            self.log(2, f"订阅TTS事件失败: {str(e)}")

        self.logger.info("SiSi设备适配器初始化完成")

        # 保存到全局变量，使其他模块可以访问
        global _ADAPTER_INSTANCE
        _ADAPTER_INSTANCE = self

    def log(self, level, message):
        """记录日志的方法，统一日志格式
        Args:
            level: 日志级别，1=INFO, 2=WARNING, 3=ERROR
            message: 日志消息
        """
        if level == 1:
            self.logger.info(message)
        elif level == 2:
            self.logger.warning(message)
        elif level == 3:
            self.logger.error(message)
        else:
            self.logger.debug(message)

    def handle_audio_data(self, data):
        """处理音频数据回调 - 根据协议版本决定是否添加BP3头部"""
        try:
            # speaking期间屏蔽一切非音频文本发送
            # 此回调只处理音频二进制数据，文本控制统一从send_message(dict)走
            # 获取所有连接的客户端（不检查状态，避免时序问题）
            active_clients = list(self.clients.keys())
            if not active_clients:
                return

            # 🔥 关键修复：检查是否为标记帧（32字节的特殊数据包）
            if len(data) == 32:
                # 可能是标记帧，检查前4字节
                marker_type = data[:4]
                if marker_type == bytes([0x01, 0x00, 0x00, 0x00]):
                    # 音频开始标记，可以忽略或处理
                    self.log(1, "[Audio] 收到音频开始标记")
                    return
                elif marker_type == bytes([0x02, 0x00, 0x00, 0x00]):
                    # 音频结束标记，可以忽略或处理
                    self.log(1, "[Audio] 收到音频结束标记")
                    return
                elif marker_type == bytes([0x03, 0x00, 0x00, 0x00]):
                    # 心跳标记
                    self.log(1, "[Audio] 收到心跳标记")
                    return

            # 🔥 关键修复：data已经是OPUS帧，根据协议版本决定是否添加BP3头部
            # AudioManager已经完成了PCM到OPUS的转换
            opus_frame = data

            # 直接发送OPUS帧给所有客户端
            import asyncio as _asyncio
            import threading as _threading

            async def send_to_all():
                for client_id in list(active_clients):
                    ws = self.clients.get(client_id)
                    if not ws or getattr(ws, 'closed', False):
                        continue
                    
                    # 获取设备信息，确定协议版本
                    device = self.devices.get(client_id, {})
                    protocol_version = device.get("protocol_version", 3)  # 默认使用BP3
                    
                    try:
                        # 根据协议版本决定是否添加BP3头部
                        if protocol_version == 3:
                            # BP3协议封装 - 使用大端字节序，与xiaozhi项目保持一致
                            header = bytes([0, 0]) + len(opus_frame).to_bytes(2, 'big')
                            packet = header + opus_frame
                        else:
                            # 其他版本直接发送裸帧
                            packet = opus_frame
                            
                        await ws.send(packet)

                        # 调试日志和统计信息
                        if not hasattr(self, '_audio_send_count'):
                            self._audio_send_count = 0
                            self._audio_send_bytes = 0
                        self._audio_send_count += 1
                        self._audio_send_bytes += len(packet)
                        if self._audio_send_count <= 5 or self._audio_send_count % 50 == 0:
                            self.log(1, f"[Audio] 发送音频数据: {len(packet)}字节 -> {client_id[:8]} (协议版本: {protocol_version}, 累计: {self._audio_send_count}帧, {self._audio_send_bytes}字节)")
                    except Exception as e:
                        if self._audio_send_count <= 5:
                            self.log(2, f"发送音频失败: {e}")
                        # 添加错误恢复机制
                        if 'timeout' in str(e).lower() or 'closed' in str(e).lower():
                            self.log(2, f"检测到连接问题，尝试清理无效连接: {client_id[:8]}")
                            self._cleanup_client(client_id)
                            return

            def _run():
                loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(send_to_all())
                finally:
                    loop.close()

            t = _threading.Thread(target=_run, daemon=True)
            t.start()

        except Exception as e:
            self.log(2, f"处理音频数据异常: {str(e)}")
            traceback.print_exc()

    # 🔥 已删除第一个 handle_state_change 方法（重复定义，会被第1593行的第二个方法覆盖）
    # 所有修复已合并到第1593行开始的方法中

    def register_tts_hooks(self):
        """注册SmartSisi核心的TTS钩子"""
        try:
            if not self.sisi_core_instance:
                self.log(1, "无法获取SmartSisi核心实例，TTS钩子注册失败")
                return False

            core_instance = self.sisi_core_instance
            core_class = core_instance.__class__
            self.log(1, f"SmartSisi核心类名: {core_class.__name__}")

            # 检查可能的TTS方法名
            tts_methods = ['do_tts', 'tts', 'speak', 'text_to_speech']
            method_name = None

            for name in tts_methods:
                if hasattr(core_instance, name):
                    method_name = name
                    self.log(1, f"找到TTS方法: {method_name}")
                    break

            if not method_name:
                self.log(1, "未找到TTS方法")
                return False

            # 保存原始方法引用
            original_method = getattr(core_instance, method_name)
            self.log(1, f"原始TTS方法: {original_method}")

            # 检查是否已经被钩子替换
            if hasattr(original_method, '_is_esp32_hook'):
                self.log(1, "TTS方法已经被钩子替换，跳过重复注册")
                return True

            # 使用装饰器模式，保持原始方法签名
            import inspect
            import functools

            @functools.wraps(original_method)
            def tts_hook_fn(*args, **kwargs):
                """TTS钩子函数，将TTS结果直接发送到ESP32设备"""
                # 调用原始方法
                result = original_method(*args, **kwargs)

                return result

            # 标记钩子函数
            tts_hook_fn._is_esp32_hook = True

            # 替换原始方法
            setattr(core_instance, method_name, tts_hook_fn)
            self.log(1, f"成功注册TTS钩子: {method_name}")

            self.log(1, "已注册TTS回调钩子，启用直接内存传输")
            return True

        except Exception as e:
            self.log(2, f"注册TTS钩子失败: {str(e)}")
            traceback.print_exc()
            return False

    def _init_sisi_core(self):
        """初始化SmartSisi核心实例 - 修改为获取已有实例而不是创建新实例"""
        try:
            # 尝试从sisi_booter获取已有实例
            try:
                import sys
                if 'sisi_booter' in sys.modules:
                    booter = _resolve_sisi_booter_module()
                    if booter and hasattr(booter, 'sisi_core') and booter.sisi_core:
                        self.sisi_core_instance = booter.sisi_core
                        self.log(1, "使用sisi_booter中的SmartSisi实例")
                        return
            except Exception as e:
                self.log(2, f"从sisi_booter获取SmartSisi实例失败: {str(e)}")

            # 尝试从core.sisi_booter获取已有实例
            try:
                from core import sisi_booter as core_sisi_booter
                if hasattr(core_sisi_booter, 'sisi_core') and core_sisi_booter.sisi_core:
                    self.sisi_core_instance = core_sisi_booter.sisi_core
                    self.log(1, "使用core.sisi_booter中的SmartSisi实例")
                    return
            except Exception as e:
                self.log(2, f"从core.sisi_booter获取SmartSisi实例失败: {str(e)}")

            # 尝试从全局中转站获取
            try:
                # 确保llm在导入路径中
                import sys
                sisi_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                llm_path = os.path.join(sisi_root, "llm")
                if llm_path not in sys.path:
                    sys.path.append(llm_path)

                # 导入全局中转站
                from llm.transit_station import get_transit_station
                transit = get_transit_station()
                if transit and hasattr(transit, 'sisi_core') and transit.sisi_core:
                    self.sisi_core_instance = transit.sisi_core
                    self.log(1, "使用全局中转站中的SmartSisi实例")
                    return
            except Exception as e:
                self.log(2, f"从全局中转站获取SmartSisi实例失败: {str(e)}")

            # 如果都没有，才创建新实例
            from core.sisi_core import SisiCore
            self.sisi_core_instance = SisiCore()
            self.log(2, "警告：创建新的SmartSisi实例，这可能导致多实例问题")
        except Exception as e:
            self.log(1, f"初始化SmartSisi核心实例失败: {str(e)}")
            traceback.print_exc()

    def start(self):
        """在新线程中启动服务器（幂等）"""
        # 服务器已运行则不再重复启动
        if self.server_running or (self.server is not None):
            self.log(1, "检测到WebSocket服务已运行，复用现有实例")
        else:
            def run_server():
                asyncio.run(self.start_server())
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()

        # 启动连接监控线程（仅一次）
        if not self.monitor_thread_running:
            monitor_thread = threading.Thread(target=self.monitor_connections, daemon=True)
            monitor_thread.start()
            self.monitor_thread_running = True
            self.log(1, "已启动连接监控线程")
        else:
            self.log(1, "连接监控线程已在运行，跳过重复启动")

        # 注册TTS钩子，实现直接内存传输（仅一次）
        # 内部已包含详细日志，这里不重复打印
        self.register_tts_hooks()
        return True

    def stop(self):
        """停止适配器"""
        try:
            # 标记停止
            self.running = False

            # 等待服务器关闭
            if self.server:
                self.server.close()

            # 关闭所有连接
            for client_id, websocket in list(self.clients.items()):
                try:
                    websocket.close()
                except:
                    pass

            # 清空设备列表
            self.clients = {}
            self.devices = {}

            # 停止所有录音器
            for _, recorder in list(self.listeners.items()):
                if hasattr(recorder, 'stop'):
                    recorder.stop()
            self.listeners = {}

            # 恢复本地播放
            self.restore_local_playback()

            # 停止音频管理器
            if hasattr(self, 'audio_manager') and self.audio_manager:
                self.log(1, "停止音频管理器")
                self.audio_manager.stop()

            self.log(1, "适配器已停止")
            return True

        except Exception as e:
            self.log(2, f"停止适配器异常: {str(e)}")
            traceback.print_exc()
            return False

    async def _prepare_lyrics_data(self, music_file_path: str, text: str) -> Optional[Dict[str, Any]]:
        """
        准备歌词数据

        Args:
            music_file_path: 音乐文件路径
            text: 当前文本内容

        Returns:
            歌词数据字典或None
        """
        try:
            if not self.s3cam_sender:
                return None

            # 使用S3CAM发送器加载歌词
            lyrics = self.s3cam_sender.load_lyrics_from_file(music_file_path)

            if lyrics:
                return {
                    "lyrics": lyrics,
                    "music_file": music_file_path,
                    "text": text,
                    "timestamp": int(time.time() * 1000)
                }
            else:
                # 如果没有歌词文件，创建基于当前文本的简单歌词
                return {
                    "lyrics": [{"time": 0, "text": text}],
                    "music_file": music_file_path,
                    "text": text,
                    "timestamp": int(time.time() * 1000)
                }

        except Exception as e:
            self.log(2, f"准备歌词数据失败: {e}")
            return None

    async def _send_music_data_to_s3cam(self, music_file_path: str, lyrics_data: Optional[Dict[str, Any]]):
        """
        发送音乐数据到S3-CAM设备

        Args:
            music_file_path: 音乐文件路径
            lyrics_data: 歌词数据
        """
        try:
            if not self.s3cam_sender:
                self.log(2, "S3CAM发送器未初始化")
                return

            # 确定动画风格
            animation_style = "rockets"  # 默认火箭动画
            if "random_generation_music" in music_file_path:
                animation_style = "stars"  # AI生成音乐使用星空动画

            # 发送完整音乐数据
            success = self.s3cam_sender.send_complete_music_data(music_file_path, animation_style)

            if success:
                self.log(1, f"✅ 音乐数据发送到S3-CAM成功: {os.path.basename(music_file_path)}")

                # 发送SmartSisi交互日志
                if lyrics_data and self.s3cam_integration:
                    text = lyrics_data.get("text", "")
                    self.s3cam_integration.on_sisi_music_start(music_file_path, animation_style)
                    if text:
                        self.s3cam_integration.on_sisi_response(f"正在播放: {text}")
            else:
                self.log(2, f"❌ 音乐数据发送到S3-CAM失败")

        except Exception as e:
            self.log(2, f"发送音乐数据到S3-CAM异常: {e}")
            traceback.print_exc()

    async def start_server(self):
        """启动WebSocket服务器（幂等，端口占用容忍）"""
        try:
            # 已在运行则跳过
            if self.server_running or (self.server is not None):
                self.log(1, f"WebSocket服务已在运行: ws://{self.host}:{self.port}/sisi/v1/，跳过重复启动")
                return

            self.running = True
            self.log(1, f"准备启动WebSocket服务，使用端口: {self.port}")

            try:
                self.server = await websockets.serve(
                    self.handle_connection,
                    self.host,
                    self.port,
                    ping_interval=30
                )
                self.server_running = True
                self.log(1, f"SiSi协议服务器启动成功 - ws://{self.host}:{self.port}/sisi/v1/")
            except OSError as oe:
                if getattr(oe, 'errno', None) == 10048 or 'only one usage of each socket address' in str(oe).lower():
                    # 端口被占用，视为已有实例在运行
                    self.server_running = True
                    self.log(1, f"检测到端口已被占用，视为已有实例在运行: ws://{self.host}:{self.port}/sisi/v1/，复用现有服务")
                    return
                else:
                    raise

            # 不再重复获取SmartSisi核心实例，使用初始化时创建的实例
            if not self.sisi_core_instance:
                self.log(1, "警告: SmartSisi核心实例未初始化，某些功能可能受限")

            # 保持服务器运行
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            self.log(1, f"服务器启动失败: {str(e)}")
            traceback.print_exc()
        # 注意：不在这里关闭服务器，也不更改运行状态，避免正常复用路径被误判为关闭

    async def handle_connection(self, websocket):
        """处理WebSocket连接 - 兼容websockets 14.0+"""
        try:
            # 从websocket对象获取路径
            try:
                path = websocket.request.path
            except AttributeError:
                # 旧版本兼容
                path = getattr(websocket, 'path', '/sisi/v1/')
            
            self.log(1, f"处理新的WebSocket连接 - {path}")

            # 检查路径是否正确
            if not path.startswith("/sisi/v1/"):
                await websocket.close(1008, "不支持的路径")
                return

            # 获取请求头信息
            try:
                # 新版本websockets库的方式
                headers = dict(websocket.raw_request_headers)
            except AttributeError:
                try:
                    # 旧版本websockets库的方式
                    headers = dict(websocket.request_headers)
                except AttributeError:
                    try:
                        # 更早版本的尝试
                        headers = dict(websocket.request.headers)
                    except AttributeError:
                        # 如果无法获取头信息，使用空字典
                        self.log(2, "无法获取WebSocket请求头，使用空字典")
                        headers = {}

            # 获取设备ID和生成客户端ID
            device_id = headers.get("device-id", "unknown")
            client_id = str(uuid.uuid4())

            self.log(1, f"SiSi设备连接: {device_id}, 会话ID: {client_id}")

            # 统一协议：固定使用 BinaryProtocol v3，不再回退
            protocol_version = 3

            # 存储客户端信息
            self.clients[client_id] = websocket
            self.devices[client_id] = {
                "device_id": device_id,
                "device_type": "esp32s3",  # 修复：直接使用默认设备类型
                "client_id": client_id,
                "username": f"SiSi_{device_id[-6:]}",
                "connected_at": time.time(),
                "last_audio_time": time.time(),
                "state": "connecting",  # connecting, idle, listening, speaking
                "session_id": str(uuid.uuid4())[:8],  # 添加会话ID
                "protocol_version": protocol_version,
            }

            # 绑定固定版本到websocket实例（供底层发送判断，虽然已统一为v3）
            try:
                setattr(websocket, "_sisi_protocol_version", 3)
            except Exception:
                pass

            # 发送hello响应 - 这一步非常关键（回送协商后的协议版本）
            try:
                hello_response = {
                    "type": "hello",
                    "transport": "websocket",
                    "version": 3,
                    "audio_params": {
                        "sample_rate": 16000
                    }
                }
                await websocket.send(json.dumps(hello_response))
                self.log(1, f"向设备发送hello响应: {device_id}, 协议版本: {protocol_version}")
            except Exception as e:
                self.log(1, f"发送hello响应失败: {str(e)}")
                return

            # 创建设备录音器处理音频
            device_recorder = SisiDeviceRecorder(self, client_id)
            self.listeners[client_id] = device_recorder

            # 启动音频处理
            device_recorder.start()

            # 设置连接状态标志（不禁用本地播放）
            self._playback_disabled = True

            # 2. 重新注册文件监控，确保能捕获SISI音频
            # self.register_file_monitors()  # 2025.4.10日更换策略：从文件监控改为TTS回调，禁用文件监控
            self.log(1, "使用TTS回调代替文件监控")

            # 3. 设置设备为listening状态
            self.devices[client_id]["state"] = "listening"
            self.log(1, f"自动启动侦听模式: {device_id}")

            # 4. 发送显式listen start命令到设备
            try:
                listen_start_cmd = {
                    "type": "listen",
                    "state": "start",
                    "session_id": self.devices[client_id]["session_id"]
                }
                await websocket.send(json.dumps(listen_start_cmd))
                self.log(1, f"向设备发送listen start命令: {device_id}")
            except Exception as e:
                self.log(1, f"发送listen start命令失败: {str(e)}")

            # 向SISI通知用户已连接 - 使用安全的方式
            self._notify_webui({
                "panelMsg": f"[ESP32] {self.devices[client_id]['device_id']} 已连接",
                "Username": "Device"
            })

            # 启动保活线程
            async def keep_alive():
                while client_id in self.clients:
                    try:
                        # 每5秒发送一次保活消息
                        await asyncio.sleep(5)

                        # 检查最后活动时间，如果超过30秒没有音频数据，发送保活消息
                        if time.time() - self.devices[client_id]["last_audio_time"] > 30:
                            await websocket.send(json.dumps({
                                "type": "ping",
                                "timestamp": int(time.time() * 1000),
                                "session_id": self.devices[client_id]["session_id"]
                            }))
                            self.log(1, f"向设备发送保活消息: {device_id}")
                    except Exception:
                        break

            # 启动保活任务
            keep_alive_task = asyncio.create_task(keep_alive())

            # 初始化每连接唯一发送队列与协程
            try:
                if client_id not in self._sender_queues:
                    self._sender_queues[client_id] = asyncio.Queue(maxsize=512)
                if client_id not in self._sender_tasks:
                    self._sender_tasks[client_id] = asyncio.create_task(self._sender_loop(client_id))
                self.log(1, f"[Sender] 已初始化发送队列与协程: {client_id[:8]}")
            except Exception as e:
                self.log(2, f"[Sender] 初始化失败: {e}")

            try:
                # 保持连接直到关闭
                async for message in websocket:
                    if not self.running:
                        break
                    await self.process_message(client_id, message)
            except websockets.exceptions.ConnectionClosed:
                self.log(1, f"SiSi设备断开连接: {device_id}")
            except Exception as e:
                self.log(2, f"处理WebSocket连接异常: {str(e)}")
                traceback.print_exc()
            finally:
                # 取消保活任务
                keep_alive_task.cancel()

                # 清理资源
                # 停止并清理发送协程与队列
                try:
                    if client_id in self._sender_tasks:
                        try:
                            self._sender_tasks[client_id].cancel()
                        except Exception:
                            pass
                        del self._sender_tasks[client_id]
                    if client_id in self._sender_queues:
                        try:
                            while not self._sender_queues[client_id].empty():
                                self._sender_queues[client_id].get_nowait()
                        except Exception:
                            pass
                        del self._sender_queues[client_id]
                except Exception as e:
                    self.log(2, f"[Sender] 清理发送资源异常: {e}")
                if client_id in self.listeners:
                    self.listeners[client_id].stop()
                    del self.listeners[client_id]

                if client_id in self.clients:
                    del self.clients[client_id]

                if client_id in self.devices:
                    del self.devices[client_id]

                # 重置播放标志
                self._playback_disabled = False
                self.log(1, "ESP32设备已断开，重置播放标志")
        except Exception as e:
            self.log(2, f"处理WebSocket连接异常: {str(e)}")
            traceback.print_exc()

    async def process_message(self, client_id, message):
        """处理接收到的消息"""
        device = self.devices.get(client_id)
        listener = self.listeners.get(client_id)

        if not device or not listener:
            return

        if isinstance(message, str):
            # 处理JSON消息
            try:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "listen":
                    await self.handle_listen_message(client_id, data)
                elif msg_type == "abort":
                    await self.handle_abort_message(client_id, data)
                elif msg_type == "iot":
                    await self.handle_iot_message(client_id, data)
            except json.JSONDecodeError:
                self.log(1, f"无效的JSON消息: {message[:100]}...")
        elif isinstance(message, bytes):
            # 处理二进制数据
            device["last_audio_time"] = time.time()

            # 特殊处理1字节心跳包
            if len(message) == 1:
                # 每20秒记录一次心跳包，避免日志过多
                current_time = time.time()
                if not hasattr(self, '_last_heartbeat_log_time') or current_time - self._last_heartbeat_log_time > 20:
                    self.log(1, f"收到心跳包: {message.hex()}")
                    self._last_heartbeat_log_time = current_time
                return

            # 处理正常的音频数据
            # 🔥 添加调试日志：检查状态条件
            if not hasattr(self, '_audio_receive_count'):
                self._audio_receive_count = 0
            self._audio_receive_count += 1
            if self._audio_receive_count % 50 == 1:
                self.log(1, f"[🔍音频入口] 收到音频数据，设备状态={device['state']}, listener存在={listener is not None}")
            
            if device["state"] == "listening" and listener:
                # 发送聆听中状态到WebUI
                self._notify_webui({
                    "panelMsg": "聆听中...",
                    "agent_status": "listening",
                    'Username': device["username"],
                    'robot': 'http://127.0.0.1:5000/robot/Listening.jpg'
                })

                listener.process_audio_data(message)
            else:
                # 🔥 记录为什么不处理音频
                if self._audio_receive_count % 50 == 1:
                    self.log(2, f"[🔍音频入口] ❌ 音频未处理: 状态={device['state']}（需要listening）, listener={listener is not None}")

    async def handle_listen_message(self, client_id, data):
        """处理listen消息"""
        device = self.devices.get(client_id)
        if not device:
            return

        state = data.get("state")

        if state == "start":
            device["state"] = "listening"
            self.log(1, f"SiSi设备开始录音: {device['device_id']}")

            # 添加录音监听指示到UI
            self._notify_webui({
                "listening": True,
                "remote_audio": True,
                "Username": device["username"]
            })

        elif state == "stop":
            device["state"] = "idle"
            self.log(1, f"SiSi设备停止录音: {device['device_id']}")

            # 更新UI状态
            self._notify_webui({
                "listening": False,
                "remote_audio": True,
                "Username": device["username"]
            })

        elif state == "detect":
            # 唤醒词检测
            wake_word = data.get("text", "")
            self.log(1, f"SiSi设备检测到唤醒词: {wake_word}")

            # 触发SISI的唤醒逻辑 (两种方式)
            # 1. 通过sisi_core实例
            if self.sisi_core_instance:
                try:
                    # 检查是否有wake_up方法
                    if hasattr(self.sisi_core_instance, 'wake_up'):
                        self.sisi_core_instance.wake_up()
                    else:
                        self.log(2, "SmartSisi核心实例缺少wake_up方法")
                except Exception as e:
                    self.log(2, f"调用wake_up方法异常: {str(e)}")

            # 2. 直接创建交互对象
            try:
                from core.interact import Interact
                interact = Interact("mic", 1, {'user': device["username"], 'msg': wake_word})
                if self.sisi_core_instance and hasattr(self.sisi_core_instance, 'on_interact'):
                    self.sisi_core_instance.on_interact(interact)
            except Exception as e:
                self.log(2, f"创建交互对象异常: {str(e)}")

    async def handle_abort_message(self, client_id, data):
        """处理abort消息"""
        device = self.devices.get(client_id)
        if not device:
            return

        reason = data.get("reason", "")
        self.log(1, f"SiSi设备中止操作: {reason}")

        # 中止SISI当前的语音输出
        if not self.sisi_core_instance:
            return

        core = self.sisi_core_instance
        try:
            if hasattr(core, "stop_speaking"):
                core.stop_speaking()
            elif hasattr(core, "_stop_current_tasks"):
                self.log(1, "SisiCore缺少stop_speaking，回退到_stop_current_tasks")
                core._stop_current_tasks()
            else:
                self.log(2, "SisiCore缺少停止接口，回退为状态位清理")
                if hasattr(core, "speaking"):
                    core.speaking = False
                if hasattr(core, "chatting"):
                    core.chatting = False
        except Exception as e:
            self.log(2, f"处理abort消息失败: {str(e)}")

    async def handle_iot_message(self, client_id, data):
        """处理IOT消息 - 将来可以扩展为控制SISI或其他设备"""
        device = self.devices.get(client_id)
        if not device:
            return

        if "descriptors" in data:
            self.log(1, f"收到设备描述: {json.dumps(data['descriptors'])[:100]}...")

        elif "states" in data:
            self.log(1, f"收到设备状态: {json.dumps(data['states'])[:100]}...")

    async def send_message(self, client_id, message):
        """发送消息到客户端 - 🔥 增强连接稳定性"""
        if client_id not in self.clients:
            self.log(2, f"[🔍调试] 客户端 {client_id[:8]} 不在clients列表中！当前clients: {list(self.clients.keys())}")
            return False

        websocket = self.clients[client_id]
        device = self.devices.get(client_id, {})

        # 🔥 检查WebSocket连接状态
        if websocket is None:
            self.log(2, f"客户端 {client_id[:8]} WebSocket为None，移除无效连接")
            self._cleanup_client(client_id)
            return False

        # websockets 14.0+ 使用 state 属性检查连接状态
        try:
            from websockets.protocol import State
            if websocket.state != State.OPEN:
                self.log(2, f"客户端 {client_id[:8]} WebSocket已关闭，移除无效连接")
                self._cleanup_client(client_id)
                return False
        except (ImportError, AttributeError):
            # 兼容旧版本 websockets
            if hasattr(websocket, 'closed') and websocket.closed:
                self.log(2, f"客户端 {client_id[:8]} WebSocket已关闭，移除无效连接")
                self._cleanup_client(client_id)
                return False

        try:
            if isinstance(message, dict):
                # 特别记录listen消息的发送情况
                if message.get("type") == "listen":
                    formatted_msg = json.dumps(message)
                    self.log(1, f"ESP32命令发送确认: {formatted_msg} -> {client_id[:8]}")
                elif message.get("type") == "tts":
                    self.log(1, f"[🔍调试] 发送TTS命令到设备 {client_id[:8]}: {message}")
                await websocket.send(json.dumps(message))
            elif isinstance(message, str):
                # speaking期间屏蔽纯文本消息，避免与音频交错
                device = self.devices.get(client_id, {})
                if device.get("state") == "speaking":
                    self.log(1, f"[🔍调试] speaking中屏蔽文本消息 -> {client_id[:8]}")
                    return True
                # 非speaking状态可发（如hello/心跳等初始化阶段）
                self.log(1, f"[🔍调试] 发送文本消息到设备 {client_id[:8]}: {len(message)}字符")
                await websocket.send(message)
            elif isinstance(message, bytes):
                await websocket.send(message)
            return True
        except websockets.exceptions.ConnectionClosed:
            self.log(2, f"客户端 {client_id[:8]} 连接已关闭，移除无效连接")
            self._cleanup_client(client_id)
            return False
        except Exception as e:
            self.log(2, f"发送消息到客户端 {client_id[:8]} 失败: {str(e)}")
            # 如果是连接相关错误，清理客户端
            if 'socket' in str(e).lower() or 'connection' in str(e).lower() or 'nonetype' in str(e).lower():
                self.log(2, f"检测到连接错误，清理客户端 {client_id[:8]}")
                self._cleanup_client(client_id)
            return False

    def _cleanup_client(self, client_id):
        """清理无效的客户端连接"""
        try:
            # 清理listeners
            if client_id in self.listeners:
                try:
                    self.listeners[client_id].stop()
                except:
                    pass
                del self.listeners[client_id]

            # 清理clients
            if client_id in self.clients:
                del self.clients[client_id]

            # 清理devices
            if client_id in self.devices:
                device_id = self.devices[client_id].get("device_id", "unknown")
                del self.devices[client_id]
                self.log(1, f"已清理断开的设备: {device_id}")

            # 重置播放标志
            self._playback_disabled = False

        except Exception as e:
            self.log(2, f"清理客户端 {client_id[:8]} 时出错: {str(e)}")



    def notify_tts_event(self, text):
        """通知所有SiSi设备TTS事件"""
        try:
            if not self.clients:
                self.log(1, "没有设备连接")
                return

            # 记录详细日志
            self.log(1, f"收到TTS事件通知: 文本长度={len(text) if text else 0}, 文本前30字符={text[:30] if text else ''}...")

            # 检查是否有<answer>标签，如果有则提取内容
            import re
            processed_text = text
            answer_match = re.search(r'<answer>(.*?)</answer>', processed_text, flags=re.DOTALL)
            if answer_match:
                processed_text = answer_match.group(1).strip()
                self.log(1, f"从<answer>标签中提取文本: {processed_text[:30]}...")

            # 使用线程安全方式处理异步调用
            def send_tts_in_thread(text):
                try:
                    # 创建新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    # 在新的事件循环中执行异步操作
                    loop.run_until_complete(self.send_tts_messages(text))
                    loop.close()
                    self.log(1, f"已发送TTS消息: {text[:30]}...")
                except Exception as e:
                    self.log(2, f"线程内发送TTS消息失败: {str(e)}")
                    import traceback
                    traceback.print_exc()

            # 创建并启动线程
            thread = threading.Thread(target=send_tts_in_thread, args=(processed_text,))
            thread.daemon = True
            thread.start()
            self.log(1, "已创建TTS发送线程")
        except Exception as e:
            self.log(2, f"通知TTS事件失败: {str(e)}")
            import traceback
            traceback.print_exc()

    async def send_tts_messages(self, text):
        """发送TTS消息到所有设备"""
        if not text or not self.clients:
            return

        try:
            # 获取活跃设备数量
            device_count = len(self.clients)
            if device_count == 0:
                self.log(1, "没有设备连接")
                return

            # 0. 设置设备状态为speaking，这是关键步骤！
            for client_id, device in list(self.devices.items()):
                if client_id in self.clients:
                    try:
                        # 向所有设备发送tts start命令，切换状态
                        await self.send_message(client_id, {
                            "type": "tts",
                            "state": "start"
                        })
                        # 设置设备状态为speaking
                        self.devices[client_id]["state"] = "speaking"
                        self.log(1, f"已向设备 {client_id[:8]} 发送tts start命令")
                    except Exception as e:
                        self.log(2, f"设置设备 {client_id[:8]} 状态失败: {str(e)}")

            # 等待设备处理状态变化
            await asyncio.sleep(0.1)

            # 1. 查找和发送音频数据（如当前处于流式播放，跳过基于文件的发送以避免并发）
            samples_dir = os.path.join(self.sisi_root, "samples")
            latest_file = None
            latest_time = 0

            # 查找最近10秒内创建的output_*.wav文件 - 增加时间窗口以捕获Agent系统的输出
            current_time = time.time()
            if os.path.exists(samples_dir):
                for file in os.listdir(samples_dir):
                    if file.endswith(".wav"):  # 放宽文件名匹配条件，捕获所有WAV文件
                        file_path = os.path.join(samples_dir, file)
                        file_time = os.path.getmtime(file_path)
                        if current_time - file_time < 10 and file_time > latest_time:  # 增加时间窗口
                            latest_time = file_time
                            latest_file = file_path

            # 🎵 新增：检查是否为音乐文件，如果是则准备歌词数据
            lyrics_data = None
            # 检测音乐文件：不是TTS文件就是音乐文件
            is_music_file = latest_file and 'samples' not in latest_file

            if is_music_file:
                self.log(1, f"检测到音乐文件: {os.path.basename(latest_file)}")
                lyrics_data = await self._prepare_lyrics_data(latest_file, text)
                if lyrics_data:
                    self.log(1, f"已准备歌词数据: {len(lyrics_data.get('lyrics', []))} 行歌词")

                # 🎵 发送歌词和动画数据到S3-CAM设备
                if self.s3cam_sender:
                    try:
                        await self._send_music_data_to_s3cam(latest_file, lyrics_data)
                    except Exception as e:
                        self.log(2, f"发送音乐数据到S3-CAM失败: {e}")
            else:
                # 普通TTS回复，发送到SISIeyes显示
                self.log(1, f"🔍 调试信息: s3cam_integration={self.s3cam_integration is not None}, text='{text[:50] if text else 'None'}'")

                if self.s3cam_integration and text:
                    try:
                        self.log(1, f"📤 准备发送SmartSisi回复到SISIeyes: {text[:30]}...")
                        self.s3cam_integration.on_sisi_response(text)
                        self.log(1, f"✅ SmartSisi回复已发送到SISIeyes: {text[:30]}...")
                    except Exception as e:
                        self.log(2, f"❌ SmartSisi回复发送失败: {e}")
                elif not self.s3cam_integration:
                    self.log(2, "❌ s3cam_integration未初始化，无法发送SmartSisi回复")
                elif not text:
                    self.log(2, "❌ 文本为空，无法发送SmartSisi回复")

            # 查询流式状态
            try:
                from esp32_liusisi.sisi_audio_output import AudioOutputManager
                aom = AudioOutputManager.get_instance()
                if aom and aom.is_streaming():
                    self.log(1, f"[SisiAdapter] 检测到流式会话进行中，跳过基于文件的TTS发送")
                    latest_file = None
            except Exception:
                pass

            if latest_file and os.path.exists(latest_file) and os.path.getsize(latest_file) > 0:
                self.log(1, f"找到TTS音频文件: {os.path.basename(latest_file)}")
                # 转换为OPUS格式
                opus_frames = await self._convert_to_opus(latest_file)
                if opus_frames:
                    self.log(1, f"已转换音频文件为OPUS: {len(opus_frames)} 帧")

                    # 使用opus_convertor向每个设备发送音频帧
                    for client_id in list(self.clients.keys()):
                        try:
                            websocket = self.clients.get(client_id)
                            if websocket:
                                # 使用opus_convertor的方法播放帧
                                if hasattr(self, 'opus_convertor'):
                                    await self.opus_convertor.play_opus_frames(websocket, opus_frames, pre_buffer=2)  # 🔥 2帧预缓冲
                                    self.log(1, f"已向设备 {client_id[:8]} 发送音频帧")
                        except Exception as e:
                            self.log(2, f"发送音频帧到设备 {client_id[:8]} 失败: {str(e)}")

                    self.log(1, f"已发送TTS音频数据: {len(opus_frames)} 帧")
                else:
                    self.log(2, "音频转换失败")
            else:
                # 如果没有找到最新的音频文件，尝试查找所有可能的音频目录
                self.log(1, "在samples目录中未找到最新音频文件，尝试查找其他目录")

                # 检查多个可能的文件夹
                cache_root = _get_cache_root(os.path.join(self.sisi_root, "cache_data"))
                dirs_to_check = [
                    os.path.join(self.sisi_root, "samples"),
                    cache_root,
                    os.path.join(self.sisi_root, "output"),
                    os.path.join(self.sisi_root, "audio")
                ]

                for dir_path in dirs_to_check:
                    if not os.path.exists(dir_path):
                        continue

                    # 查找WAV文件
                    for pattern in ["*.wav", "*.mp3", "output_*.wav"]:
                        import glob
                        files = glob.glob(os.path.join(dir_path, pattern))
                        for file in files:
                            file_time = os.path.getmtime(file)
                            if current_time - file_time < 10 and file_time > latest_time:
                                latest_time = file_time
                                latest_file = file

                if latest_file:
                    self.log(1, f"在其他目录中找到音频文件: {os.path.basename(latest_file)}")
                    # 转换为OPUS格式
                    opus_frames = await self._convert_to_opus(latest_file)
                    if opus_frames:
                        self.log(1, f"已转换音频文件为OPUS: {len(opus_frames)} 帧")

                        # 使用opus_convertor向每个设备发送音频帧
                        for client_id in list(self.clients.keys()):
                            try:
                                websocket = self.clients.get(client_id)
                                if websocket:
                                    # 使用opus_convertor的方法播放帧
                                    if hasattr(self, 'opus_convertor'):
                                        await self.opus_convertor.play_opus_frames(websocket, opus_frames, pre_buffer=2)  # 🔥 2帧预缓冲
                                        self.log(1, f"已向设备 {client_id[:8]} 发送音频帧")
                            except Exception as e:
                                self.log(2, f"发送音频帧到设备 {client_id[:8]} 失败: {str(e)}")

                        self.log(1, f"已发送TTS音频数据: {len(opus_frames)} 帧")
                    else:
                        self.log(2, "音频转换失败")
                else:
                    self.log(2, "未找到有效的TTS音频文件")

            # 日志：准备发送结束命令前的状态确认
            self.log(1, "准备发送TTS结束命令")

            # 3. 发送TTS结束命令
            for client_id, device in list(self.devices.items()):
                if client_id in self.clients:
                    try:
                        # 向所有设备发送TTS stop命令
                        await self.send_message(client_id, {
                            "type": "tts",
                            "state": "stop"
                        })
                        # 设置设备状态
                        self.devices[client_id]["state"] = "idle"
                        self.log(1, f"已向设备 {client_id[:8]} 发送tts stop命令")
                    except Exception as e:
                        self.log(2, f"向设备 {client_id[:8]} 发送tts stop命令失败: {str(e)}")

            # 4. 标记完成
            self.log(1, "TTS消息发送完成")

        except Exception as e:
            self.log(2, f"发送TTS消息异常: {str(e)}")
            traceback.print_exc()

    async def _synthesize_audio(self, text):
        """使用TTS引擎直接合成音频数据，不经过文件系统"""
        try:
            # 这里使用临时内存缓冲区而非文件
            import io
            import wave
            import numpy as np
            from scipy.io import wavfile

            # 使用内置TTS引擎合成音频
            # 注意：实际实现取决于你使用的TTS引擎
            # 以下是一个示例，你需要根据实际情况调整
            if hasattr(self.sisi_core_instance, 'tts_engine'):
                # 如果SISI有tts_engine属性
                audio_data = self.sisi_core_instance.tts_engine.synthesize(text)

                # 转换为OPUS格式
                opus_data = await self._convert_audio_to_opus(audio_data)
                return opus_data
            else:
                self.log(2, "无法访问TTS引擎，使用备用方法")
                # 备用方法：如果无法直接访问TTS引擎
                # 寻找最新生成的音频文件
                audio_file = self._find_latest_audio()
                if audio_file:
                    # 转换为OPUS格式
                    opus_data = await self._convert_to_opus(audio_file)
                    return opus_data
                return None

        except Exception as e:
            self.log(2, f"音频合成异常: {str(e)}")
            traceback.print_exc()
            return None

    async def _convert_audio_to_opus(self, audio_data):
        """将内存中的音频数据转换为OPUS格式"""
        try:
            # 使用临时文件作为中转
            temp_wav = os.path.join(tempfile.gettempdir(), f"temp_tts_{int(time.time())}.wav")
            temp_opus = os.path.join(tempfile.gettempdir(), f"temp_tts_{int(time.time())}.opus")

            # 保存为临时WAV文件
            import numpy as np
            from scipy.io import wavfile

            # 假设audio_data是(采样率, 音频数据)格式
            if isinstance(audio_data, tuple) and len(audio_data) == 2:
                rate, data = audio_data
            else:
                # 如果不是元组，假设只是音频数据
                rate = 24000  # 采样率为24kHz
                data = audio_data

            wavfile.write(temp_wav, rate, data)

            # 转换为OPUS格式
            cmd = [
                "ffmpeg", "-y", "-i", temp_wav,
                "-c:a", "libopus", "-b:a", "32k",
                "-application", "voip", "-frame_duration", "60",
                temp_opus
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.log(2, f"转换OPUS失败: {stderr.decode()}")
                return None

            # 读取OPUS文件数据
            with open(temp_opus, "rb") as f:
                opus_data = f.read()

            # 清理临时文件
            try:
                os.remove(temp_wav)
                os.remove(temp_opus)
            except:
                pass

            return opus_data

        except Exception as e:
            self.log(2, f"转换音频异常: {str(e)}")
            traceback.print_exc()
            return None

    def disable_local_playback(self):
        """不再禁用本地播放，仅设置标志位"""
        self.log(1, "保留电脑端音频输出，只设置同步标志...")
        self._playback_disabled = True
        return True

    def restore_local_playback(self):
        """重置标志位"""
        self._playback_disabled = False
        self.log(1, "已重置播放标志")
        return True


    def handle_state_change(self, state):
        """处理状态变化回调 - 🔥 防止频繁触发问题（参考xiaozhi-server实现）"""
        try:
            # 🔥 关键修复：防止重复触发，使用状态锁
            if not hasattr(self, '_last_state_change'):
                self._last_state_change = None
                self._state_lock = False
                self._reset_threads = {}  # 记录正在运行的重置线程
            
            # 如果已经在处理状态变化，直接返回
            if self._state_lock:
                return
                
            # 如果状态没有变化，直接返回
            if self._last_state_change == state:
                return
            
            # 设置状态锁
            self._state_lock = True
            self._last_state_change = state
            
            try:
                # 🔥 添加状态变化冷却时间，避免过于频繁的状态切换
                if hasattr(self, '_last_state_change_time'):
                    elapsed = time.time() - self._last_state_change_time
                    # 🔥 增加冷却时间到2.0秒，确保设备端有足够时间处理状态变化
                    if elapsed < 2.0:
                        time.sleep(2.0 - elapsed)
                self._last_state_change_time = time.time()
                
                # 🔥 统一状态管理（参考xiaozhi-server）
                # 获取活跃设备
                for client_id, device in list(self.devices.items()):
                    if client_id in self.clients:
                        if state == AudioState.PLAYING:
                            # 仅在设备不是speaking状态时才设置
                            if device.get("state") != "speaking":
                                device["state"] = "speaking"
                                device["last_state_change"] = time.time()
                                self.log(1, f"[SisiAdapter] 设置设备 {client_id[:8]} 状态为 speaking (时间: {device['last_state_change']})")

                                # 同步到WebUI（10003）
                                self._notify_webui({
                                    "audio_event": "start",
                                    "audio_command": "start",
                                    "agent_status": "speaking"
                                })
                                
                                # 发送开始消息 - 🔥 修复：使用异步发送
                                session_id = device.get("session_id", "")
                                start_msg = json.dumps({
                                    "type": "tts",
                                    "state": "start",
                                    "session_id": session_id
                                })
                                # 🔥 关键修复：使用异步发送
                                import asyncio
                                import threading
                                def async_send_start():
                                    try:
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)
                                        loop.run_until_complete(self.send_message(client_id, start_msg))
                                        # 移除：避免发送会被设备端误解码的标记帧
                                        loop.close()
                                    except Exception:
                                        pass
                                thread = threading.Thread(target=async_send_start, daemon=True)
                                thread.start()

                        elif state == AudioState.IDLE:
                            # 🔥 关键修复：只有在设备是speaking状态时才重置
                            if device.get("state") == "speaking":
                                device["state"] = "idle"
                                self.log(1, f"[SisiAdapter] 设置设备 {client_id[:8]} 状态为 idle")

                                # 同步到WebUI（10003）
                                self._notify_webui({
                                    "audio_event": "complete",
                                    "audio_command": "stop",
                                    "agent_status": "idle",
                                    "audio_level": 0
                                })
                                
                                # 发送结束消息 - 🔥 修复：使用异步发送
                                session_id = device.get("session_id", "")
                                stop_msg = json.dumps({
                                    "type": "tts",
                                    "state": "stop",
                                    "session_id": session_id
                                })
                                # 🔥 关键修复：使用异步发送
                                import asyncio
                                import threading
                                def async_send_stop():
                                    try:
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)
                                        loop.run_until_complete(self.send_message(client_id, stop_msg))
                                        loop.close()
                                    except Exception:
                                        pass
                                thread = threading.Thread(target=async_send_stop, daemon=True)
                                thread.start()
                                
                                # 🔥 修复问题3：延迟恢复listening状态并发送命令（和第一个方法保持一致）
                                def delayed_reset():
                                    import time
                                    time.sleep(0.5)
                                    device["state"] = "listening"

                                    try:
                                        # 同步到WebUI（10003）
                                        self._notify_webui({
                                            "agent_status": "listening"
                                        })

                                        listen_start_cmd = {
                                            "type": "listen",
                                            "state": "start",
                                            "session_id": session_id
                                        }
                                        def async_send_listen():
                                            try:
                                                loop = asyncio.new_event_loop()
                                                asyncio.set_event_loop(loop)
                                                loop.run_until_complete(self.send_message(client_id, json.dumps(listen_start_cmd)))
                                                loop.close()
                                            except Exception as e:
                                                self.log(2, f"❌ 发送listen start失败: {e}")
                                        thread = threading.Thread(target=async_send_listen, daemon=True)
                                        thread.start()
                                        self.log(1, f"🎤 交互结束，重新启动侦听: {device.get('device_id', 'unknown')[:8]}")
                                    except Exception as e:
                                        self.log(2, f"❌ 重启侦听失败: {e}")
                                
                                reset_thread = threading.Thread(target=delayed_reset, daemon=True)
                                reset_thread.start()
            finally:
                # 释放状态锁
                self._state_lock = False

        except Exception as e:
            self.log(2, f"处理状态变化异常: {str(e)}")
            # 确保错误时也释放锁
            if hasattr(self, '_state_lock'):
                self._state_lock = False

    def _on_audio_play_start(self):
        """音频播放开始回调"""
        self.log(1, "音频播放开始")

        # 更新所有设备状态为speaking
        for client_id, device in list(self.devices.items()):
            device["state"] = "speaking"
            device["last_state_change"] = time.time()
            try:
                # 发送TTS开始消息
                def send_in_thread():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        # 发送sentence_start消息
                        loop.run_until_complete(self.send_message(client_id, {
                            "type": "tts",
                            "state": "sentence_start",
                            "session_id": device.get("session_id", "")
                        }))
                        loop.close()

                        # 调用SISI UI接口
                        username = device.get("username", "")
                        if username:
                            self._notify_webui({
                                "tts_start": True,
                                "Username": username
                            })
                    except Exception as e:
                        self.log(2, f"线程内发送TTS开始命令失败: {str(e)}")

                # 创建并启动线程
                thread = threading.Thread(target=send_in_thread)
                thread.daemon = True
                thread.start()

            except Exception as e:
                self.log(2, f"发送TTS开始消息失败: {str(e)}")

    def _on_audio_play_end(self):
        """音频播放结束回调"""
        self.log(1, "音频播放结束")

        # 恢复所有设备为listening状态
        for client_id, device in list(self.devices.items()):
            device["state"] = "listening"
            device["last_state_change"] = time.time()
            try:
                # 发送TTS结束消息
                def send_in_thread():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        # 发送sentence_end消息
                        loop.run_until_complete(self.send_message(client_id, {
                            "type": "tts",
                            "state": "sentence_end",
                            "session_id": device.get("session_id", "")
                        }))
                        # 发送stop消息
                        loop.run_until_complete(self.send_message(client_id, {
                            "type": "tts",
                            "state": "stop",
                            "session_id": device.get("session_id", "")
                        }))
                        loop.close()

                        # 通知SISI UI
                        username = device.get("username", "")
                        if username:
                            self._notify_webui({
                                "tts_end": True,
                                "Username": username
                            })
                    except Exception as e:
                        self.log(2, f"线程内发送TTS结束命令失败: {str(e)}")

                # 创建并启动线程
                thread = threading.Thread(target=send_in_thread)
                thread.daemon = True
                thread.start()

            except Exception as e:
                self.log(2, f"发送TTS结束消息失败: {str(e)}")

    def _on_audio_data(self, data):
        """音频数据回调 - 关闭直发PCM路径，统一走TTS->Opus->BP3发送"""
        return

    def monitor_connections(self):
        """
        通过异步方式监控设备连接与状态更新
        包括检测新设备、断线重连、心跳保持等
        """
        try:
            # 设备连接状态检测和处理
            time.sleep(0.5)  # 短暂延迟，等待连接初始化完成

            # 连接初始状态记录
            prev_client_count = len(self.clients)
            is_first_connect = prev_client_count == 0

            # 等待连接建立
            while self.running:
                # 更新当前客户端数
                current_client_count = len(self.clients)

                # 连接数变化，检查状态
                if current_client_count != prev_client_count:
                    self.log(1, f"ESP32设备连接状态变更: {prev_client_count} -> {current_client_count} 个连接")

                    # 无连接 -> 有连接：禁用本地播放
                    if prev_client_count == 0 and current_client_count > 0:
                        self.log(1, "ESP32设备已连接，开始接管音频播放")
                        self.disable_local_playback()

                        # 初始化每个设备的录音器
                        for client_id in list(self.clients.keys()):
                            if client_id not in self.listeners:
                                self.log(1, f"创建设备录音器: {client_id[:8]}")
                                device_recorder = SisiDeviceRecorder(self, client_id)
                                self.listeners[client_id] = device_recorder
                                device_recorder.start()

                # 检查设备状态是否正常，如果长时间没有状态变化，可能需要重置
                current_time = time.time()
                for client_id, device in list(self.devices.items()):
                    if 'last_state_change' in device:
                        time_since_last_change = current_time - device['last_state_change']
                        # 如果超过30秒没有状态变化，且设备处于speaking状态，可能需要重置
                        if time_since_last_change > 30 and device.get('state') == 'speaking':
                            self.log(1, f"设备 {client_id[:8]} 长时间处于speaking状态，尝试重置")
                            
                            # 🔥 修复：重置后直接恢复listening，不经过idle（避免状态机混乱）
                            def reset_to_listening():
                                try:
                                    import time
                                    # 1. 发送停止命令
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    loop.run_until_complete(self.send_message(client_id, {
                                        "type": "tts",
                                        "state": "stop",
                                        "session_id": device.get("session_id", "")
                                    }))
                                    
                                    # 2. 等待0.5秒确保停止
                                    time.sleep(0.5)
                                    
                                    # 3. 直接设置为listening并发送命令
                                    device["state"] = "listening"
                                    device["last_state_change"] = current_time
                                    
                                    listen_start_cmd = {
                                        "type": "listen",
                                        "state": "start",
                                        "session_id": device.get("session_id", "")
                                    }
                                    loop.run_until_complete(self.send_message(client_id, json.dumps(listen_start_cmd)))
                                    loop.close()
                                    
                                    self.log(1, f"✅ 设备 {client_id[:8]} 已重置并恢复listening")
                                except Exception as e:
                                    self.log(2, f"❌ 重置失败: {e}")
                            
                            thread = threading.Thread(target=reset_to_listening, daemon=True)
                            thread.start()

                        # 确保文件监控已启动
                        # self.register_file_monitors()  # 2025.4.10日更换策略：从文件监控改为TTS回调，禁用文件监控

                    # 有连接 -> 无连接：恢复本地播放
                    elif prev_client_count > 0 and current_client_count == 0:
                        self.log(1, "所有ESP32设备已断开，恢复本地播放")
                        self.restore_local_playback()

                    # 更新连接数
                    prev_client_count = current_client_count

                # 每5秒发送一次心跳
                time.sleep(5)

                # 向所有设备发送心跳
                for client_id in list(self.clients.keys()):
                    try:
                        # 使用线程安全的方式创建事件循环并发送消息
                        def send_in_thread():
                            try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                loop.run_until_complete(self.send_message(client_id, {
                                    "type": "heartbeat",
                                    "time": int(time.time() * 1000)
                                }))
                                loop.close()
                            except Exception as e:
                                self.log(2, f"向设备 {client_id[:8]} 发送心跳失败: {str(e)}")

                        # 创建并启动新线程
                        t = threading.Thread(target=send_in_thread)
                        t.daemon = True
                        t.start()
                    except Exception as e:
                        self.log(2, f"向设备 {client_id[:8]} 发送心跳失败: {str(e)}")

        except Exception as e:
            self.log(2, f"连接监控异常: {str(e)}")
            traceback.print_exc()

        self.log(1, "连接监控线程已退出")

    async def handle_websocket_audio_data(self, client_id, audio_data):
        """处理从设备收到的音频数据"""
        # 忽略太小的数据包
        if not audio_data or len(audio_data) < 10:
            return

        # 获取设备和录音器
        device = self.devices.get(client_id)
        listener = self.listeners.get(client_id)

        if not device or not listener:
            return

        # 更新最后活动时间
        device["last_audio_time"] = time.time()

        # 处理音频数据，这是关键
        if device["state"] == "listening" and listener:
            listener.process_audio_data(audio_data)

    def _notify_webui(self, cmd_data):
        """向SISI WebUI发送通知的辅助方法，避免重复代码"""
        try:
            from core import wsa_server
            web_instance = wsa_server.get_web_instance()
            if web_instance:
                web_instance.add_cmd(cmd_data)
            return True
        except Exception as e:
            self.log(2, f"通知SISI WebUI失败: {str(e)}")
            return False

    async def _sender_loop(self, client_id: str):
        """唯一发送协程：顺序从队列取包并发送，避免并发写socket"""
        try:
            q = self._sender_queues.get(client_id)
            ws = self.clients.get(client_id)
            if q is None or ws is None:
                return
            frame_interval = self._frame_duration_ms / 1000.0
            while client_id in self.clients and not getattr(ws, 'closed', False):
                try:
                    packet = await q.get()
                    await ws.send(packet)
                    # 节拍控制，避免突发
                    await asyncio.sleep(frame_interval)
                except Exception:
                    # 连接异常或发送失败，退出协程
                    break
        except Exception:
            pass

    def _find_latest_audio(self):
        """查找最新生成的音频文件，优先查找samples文件夹"""
        try:
            # 检查多个可能的文件夹
            cache_root = _get_cache_root(os.path.join(self.sisi_root, "cache_data"))
            dirs_to_check = [
                os.path.join(self.sisi_root, "samples"),
                cache_root,
                os.path.join(self.sisi_root, "output")
            ]

            latest_file = None
            latest_time = 0

            for dir_path in dirs_to_check:
                if not os.path.exists(dir_path):
                    continue

                # 查找WAV文件 - 扩展匹配模式包括所有可能的TTS输出文件
                for pattern in ["*.wav", "*.mp3", "output_*.wav", "auto_play_*.wav", "sample-*.wav"]:
                    files = glob.glob(os.path.join(dir_path, pattern))
                    for file in files:
                        file_time = os.path.getmtime(file)
                        if file_time > latest_time:
                            latest_time = file_time
                            latest_file = file

            if latest_file:
                self.log(1, f"找到最新音频文件: {os.path.basename(latest_file)}")
                return latest_file
            else:
                self.log(2, "未找到任何音频文件")
                return None

        except Exception as e:
            self.log(2, f"查找音频文件异常: {str(e)}")
            traceback.print_exc()
            return None

    async def send_to_all_devices(self, data):
        """向所有设备发送数据

        Args:
            data: 要发送的数据
        """
        try:
            # 获取所有设备列表
            devices = []
            for client_id, device in list(self.devices.items()):
                if client_id in self.clients:
                    devices.append(client_id)

            if not devices:
                self.log(1, "[🔍调试] 没有可用设备连接，无法发送音频数据")
                return

            self.log(1, f"[🔍调试] 准备向{len(devices)}个设备发送数据，设备列表: {[d[:8] for d in devices]}")

            # 向所有设备发送数据
            success_count = 0
            for client_id in devices:
                try:
                    result = await self.send_message(client_id, data)
                    if result:
                        success_count += 1
                    self.log(1, f"[🔍调试] 设备 {client_id[:8]} 发送结果: {'✅成功' if result else '❌失败'}")
                except Exception as e:
                    self.log(2, f"向设备 {client_id[:8]} 发送数据失败: {str(e)}")

            # 只对音频开始和结束标记以及音频统计信息输出日志
            # 避免每个音频帧都输出日志
            if len(data) == 4 or len(data) < 100:
                self.log(1, f"已向{len(devices)}个设备发送数据，长度: {len(data)} 字节，成功: {success_count}/{len(devices)}")

        except Exception as e:
            self.log(2, f"发送数据到所有设备失败: {str(e)}")
            traceback.print_exc()

    async def _convert_to_opus(self, audio_file):
        """将音频文件转换为opus格式的帧

        Args:
            audio_file: 音频文件路径

        Returns:
            opus_frames: opus帧列表或None
        """
        try:
            if not os.path.exists(audio_file):
                self.log(2, f"音频文件不存在: {audio_file}")
                return None

            # 使用OpusConvertor处理
            if not hasattr(self, 'opus_convertor'):
                # 修复: 使用固定的debug=False参数，而不是self.debug_mode
                self.opus_convertor = OpusConvertor(debug=False)

            opus_frames, duration = self.opus_convertor.audio_to_opus_frames(audio_file)

            if not opus_frames:
                self.log(2, f"无法转换音频文件: {audio_file}")
                return None

            self.log(1, f"音频转换成功: {len(opus_frames)}帧, {duration:.2f}秒")
            # 🔥 修复：保存音频时长用于后续等待计算
            self._last_audio_duration = duration
            return opus_frames

        except Exception as e:
            self.log(2, f"转换音频异常: {str(e)}")
            traceback.print_exc()
            return None

    def get_device_info(self, websocket):
        """获取WebSocket连接对应的设备信息"""
        # 通过websocket对象查找对应的client_id
        for client_id, ws in self.clients.items():
            if ws == websocket:
                return self.devices.get(client_id, {})
        return None

    def _on_tts_event(self, text, audio_path=None):
        """处理SmartSisi核心的TTS事件 - 🔥 优化版本，减少延迟"""
        if not audio_path:
            self.log(2, "TTS事件未提供audio_path，无法处理")
            return

        self.log(1, f"收到TTS事件: {text[:30]}...")
        self.log(1, f"使用TTS事件提供的音频路径: {audio_path}")

        # 🎯 **发送SmartSisi回复文本到SISIeyes显示屏**
        if self.s3cam_integration and text.strip():
            try:
                self.s3cam_integration.on_sisi_response(text)
                self.log(1, f"✅ 已发送SmartSisi回复到SISIeyes显示屏: {text[:30]}...")
            except Exception as e:
                self.log(2, f"❌ 发送SmartSisi回复到SISIeyes显示屏失败: {str(e)}")

        # 检查文件是否存在且有效
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            self.log(2, f"提供的音频文件无效或为空: {audio_path}")
            # 尝试从SmartSisi核心请求重新生成或查找
            if hasattr(self, 'sisi_core_instance') and self.sisi_core_instance:
                self.log(1, f"尝试请求SmartSisi核心重新处理文本: {text[:30]}...")
                # 注意：这里假设sisi_core_instance有一个合适的重新处理方法
                # 例如 self.sisi_core_instance.regenerate_tts(text)
                # 这需要根据SmartSisi核心的实际接口调整
                # 此处暂时只记录，不执行实际的重新生成调用
            return

        # 使用线程安全方式处理异步调用
        async def process_audio_file():
            try:
                # 详细记录：开始处理来自事件的音频文件
                self.log(1, f"[SisiAdapter-TTS-Event] 开始处理音频文件: {os.path.basename(audio_path)}")

                # 🔥 修复：在异步函数内部实时获取当前活跃的客户端，而不是在函数定义时固定
                active_clients = list(self.clients.keys()) # 实时获取当前活跃的客户端ID列表
                if not active_clients:
                    self.log(1, "[SisiAdapter-TTS-Event] 没有活跃的客户端连接，无法发送TTS。")
                    return

                # 🔧 新增：检查设备状态，如果正在播放则先停止
                for client_id in active_clients:
                    device = self.devices.get(client_id)
                    if device:
                        current_state = device.get("state", "idle")
                        if current_state == "speaking":
                            self.log(1, f"[SisiAdapter-TTS-Event] 设备 {client_id[:8]} 正在播放，先发送停止命令")
                            try:
                                # 1. 发送停止命令
                                await self.send_message(client_id, {"type": "tts", "state": "stop"})
                                await asyncio.sleep(0.2)  # 等待设备处理停止命令

                                # 2. 🔥 修复：不在这里恢复监听状态，避免与后续TTS start命令冲突
                                # 监听状态恢复将在TTS播放完成后进行
                                device["state"] = "idle"  # 设置为空闲状态，等待新TTS
                                self.log(1, f"[SisiAdapter-TTS-Event] 设备 {client_id[:8]} 已停止播放，等待新TTS")

                            except Exception as e:
                                self.log(2, f"[SisiAdapter-TTS-Event] 停止设备 {client_id[:8]} 播放失败: {str(e)}")

                # 🔥 并行设置所有设备为speaking状态，减少延迟
                start_tasks = []
                for client_id in active_clients:
                    device = self.devices.get(client_id)
                    if device:
                        async def send_start_command(cid, dev):
                            try:
                                await self.send_message(cid, {"type": "tts", "state": "start"})
                                dev["state"] = "speaking"
                                self.log(1, f"[SisiAdapter-TTS-Event] 已向设备 {cid[:8]} 发送 tts start 命令")
                            except Exception as e:
                                self.log(2, f"[SisiAdapter-TTS-Event] 设置设备 {cid[:8]} 状态为 speaking 失败: {str(e)}")

                        start_tasks.append(send_start_command(client_id, device))

                # 并行执行所有开始命令
                if start_tasks:
                    await asyncio.gather(*start_tasks, return_exceptions=True)

                # 🔥 减少等待时间，从100ms减少到30ms
                await asyncio.sleep(0.03) # 等待设备处理状态变化

                # 1. 检查是否有缓存的OPUS帧（音效插入的情况）
                cached_frames = None
                try:
                    # 检查TTS实例是否有缓存的OPUS帧
                    booter = _resolve_sisi_booter_module()
                    if (booter and hasattr(booter, 'sisi_core') and
                        hasattr(booter.sisi_core, 'sp') and
                        hasattr(booter.sisi_core.sp, '_opus_frames_cache')):
                        cached_frames = booter.sisi_core.sp._opus_frames_cache.get(audio_path)
                        if cached_frames:
                            self.log(1, f"[SisiAdapter-TTS-Event] 发现缓存的OPUS帧: {len(cached_frames)}帧")
                except Exception as e:
                    self.log(2, f"[SisiAdapter-TTS-Event] 检查OPUS帧缓存失败: {str(e)}")

                if cached_frames:
                    # 使用缓存的合并OPUS帧，直接发送
                    opus_frames = cached_frames
                    self.log(1, f"[SisiAdapter-TTS-Event] 使用缓存OPUS帧: {len(opus_frames)}帧")
                else:
                    # 正常转换音频文件
                    self.log(1, f"[SisiAdapter-TTS-Event] 准备转换音频文件 {os.path.basename(audio_path)} 为OPUS...")
                    opus_frames = await self._convert_to_opus(audio_path)

                if opus_frames:
                    self.log(1, f"[SisiAdapter-TTS-Event] 音频文件 {os.path.basename(audio_path)} 成功转换为OPUS: {len(opus_frames)} 帧")

                    # 2. 发送音频数据
                    frames_sent_to_any_device = False
                    for client_id in active_clients: # 使用获取时的客户端列表
                        websocket = self.clients.get(client_id) # 再次获取，确保仍然有效
                        if websocket:
                            try:
                                self.log(1, f"[SisiAdapter-TTS-Event] 准备向设备 {client_id[:8]} 发送 {len(opus_frames)} OPUS帧...")
                                if hasattr(self, 'opus_convertor') and hasattr(self.opus_convertor, 'play_opus_frames'):
                                    await self.opus_convertor.play_opus_frames(websocket, opus_frames, pre_buffer=2)  # 🔥 2帧预缓冲
                                    self.log(1, f"[SisiAdapter-TTS-Event] 成功向设备 {client_id[:8]} 发送了 {len(opus_frames)} OPUS帧。")
                                    frames_sent_to_any_device = True
                                else:
                                    self.log(2, f"[SisiAdapter-TTS-Event] OpusConvertor 或 play_opus_frames 方法不存在，无法发送给 {client_id[:8]}。")
                            except Exception as e:
                                self.log(2, f"[SisiAdapter-TTS-Event] 发送OPUS帧到设备 {client_id[:8]} 失败: {str(e)}")
                                import traceback
                                traceback.print_exc()
                        else:
                            self.log(1, f"[SisiAdapter-TTS-Event] 设备 {client_id[:8]} 的WebSocket连接在发送前已失效。")

                    if frames_sent_to_any_device:
                        self.log(1, f"[SisiAdapter-TTS-Event] 已完成向至少一个设备发送OPUS帧。")
                    else:
                        self.log(2, f"[SisiAdapter-TTS-Event] 未能向任何设备成功发送OPUS帧。")

                else:
                    self.log(2, f"[SisiAdapter-TTS-Event] 音频文件 {os.path.basename(audio_path)} 转换为OPUS失败，无帧生成。")

                # 3. 发送TTS结束命令
                self.log(1, "[SisiAdapter-TTS-Event] 准备发送TTS结束命令...")
                for client_id in active_clients: # 使用获取时的客户端列表
                    device = self.devices.get(client_id)
                    if device: # 确保设备信息仍然存在
                        try:
                            # 1. 发送TTS停止命令
                            await self.send_message(client_id, {"type": "tts", "state": "stop"})
                            self.log(1, f"[SisiAdapter-TTS-Event] 已向设备 {client_id[:8]} 发送 tts stop 命令。")

                            # 2. 🔥 修复：等待音频播放完成，根据音频时长计算等待时间
                            # 从OPUS转换结果获取音频时长，确保设备有足够时间播放
                            if hasattr(self, '_last_audio_duration') and self._last_audio_duration:
                                wait_time = max(self._last_audio_duration + 1.0, 2.0)  # 音频时长+1秒缓冲，最少2秒
                                self.log(1, f"[SisiAdapter-TTS-Event] 等待音频播放完成: {wait_time:.1f}秒")
                                await asyncio.sleep(wait_time)
                            else:
                                await asyncio.sleep(2.0)  # 默认等待2秒

                            # 3. 🔥 关键修复：主动发送监听开始命令，确保设备重新进入监听状态
                            await self.send_message(client_id, {
                                "type": "listen",
                                "state": "start",
                                "session_id": device.get("session_id", "")
                            })
                            device["state"] = "listening"  # 设置为监听状态而不是idle
                            self.log(1, f"[SisiAdapter-TTS-Event] 🎤 已向设备 {client_id[:8]} 发送监听开始命令，恢复ASR功能")

                        except Exception as e:
                            self.log(2, f"[SisiAdapter-TTS-Event] 设备 {client_id[:8]} 状态恢复失败: {str(e)}")

                self.log(1, "[SisiAdapter-TTS-Event] TTS事件处理流程结束。")

            except Exception as e:
                self.log(2, f"[SisiAdapter-TTS-Event] process_audio_file 内部发生严重错误: {str(e)}")
                import traceback
                traceback.print_exc()

        # 创建并启动线程来运行异步的 process_audio_file
        thread = threading.Thread(target=lambda: asyncio.run(process_audio_file()))
        thread.daemon = True
        thread.start()
        self.log(1, f"已为TTS事件 (路径: {os.path.basename(audio_path)}) 创建处理线程。")


class SisiDeviceRecorder:
    """ESP32设备录音适配器 - 使用组合而非继承"""

    def __init__(self, adapter, client_id):
        """初始化设备录音器
        Args:
            adapter: SisiDeviceAdapter实例
            client_id: 客户端ID
        """
        self.adapter = adapter
        self.client_id = client_id
        self.device_id = f"esp32_{client_id}"
        self.username = f"SiSi_{client_id[:8]}"
        self.running = True
        self.stream_cache = None
        self.recorder = None
        self.log = adapter.log
        self.static_frame_count = 0  # 静音帧计数
        self.energy_history = []  # 能量历史

        # 初始化语音检测相关属性
        self.is_speaking = False
        self.last_speech_time = time.time()
        self.complete_audio_buffer = b''
        self._is_processing_complete_audio = False
        self._audio_active = False

        # 修复：移除重复的pygame初始化，避免参数冲突导致顿挫
        # pygame.mixer已在main.py和util.py中正确初始化，不需要重复初始化

        # 初始化OPUS解码器
        self.opus_decoder = self._init_opus_decoder()

        # 使用适配器中的SmartSisi实例，避免重复创建
        sisi_instance = adapter.sisi_core_instance

        # 创建内部类DeviceRecorder，它继承了Recorder类
        class DeviceRecorder(Recorder):
            def __init__(self, username, sisi_instance):
                # 直接使用传入的SmartSisi实例，不再创建新实例
                try:
                    super().__init__(sisi_instance)  # 直接使用传入的SmartSisi实例
                except Exception as e_init:
                    print(f"Recorder初始化失败: {str(e_init)}")
                    raise

                self.username = username  # 覆盖默认User名
                # 🔥 修复：使用AudioPriorityQueue替换Queue()
                from utils.stream_sentence import AudioPriorityQueue
                self.audio_queue = AudioPriorityQueue()
                self.is_connected = True
                self.wakeup_matched = False
                self.is_awake = True
                # 修复：添加s3cam_integration属性
                self.s3cam_integration = getattr(adapter, 's3cam_integration', None)

                # 流缓存初始化确保有足够的数据可以被读取
                self.stream_cache = StreamCache(1024*1024*10)
                # 初始化预填充数据，否则SISI会等待它
                self.stream_cache.write(bytearray(b'\x00\x00' * 1024 * 4))

            def is_remote(self):
                """必须声明为远程设备"""
                return True

            def get_stream(self):
                """必须有效返回stream_cache"""
                return self.stream_cache

            def _notify_webui(self, cmd_data):
                """设备录音器的WebUI通知辅助方法"""
                try:
                    from core import wsa_server
                    web_instance = wsa_server.get_web_instance()
                    if web_instance:
                        web_instance.add_cmd(cmd_data)
                    return True
                except Exception as e:
                    print(f"通知SISI WebUI失败: {e}")
                    return False

            def on_speaking(self, text):
                """处理语音识别结果"""
                if len(text) > 1:
                    try:
                        # 1. 统一走Mem0记忆系统，不再引用已移除的 member_db
                        #    这里仅打印说明，避免 ImportError
                        username = "User"
                        uid = 1
                        print(f"[ESP32适配器] 🧠 用户输入已由Mem0记忆系统处理 (user={username}, uid={uid})")

                        # 🎵 发送用户消息到S3-CAM设备（后台异步，不阻塞主流程）
                        if self.s3cam_integration:
                            def send_to_s3cam_async():
                                try:
                                    self.s3cam_integration.on_sisi_user_message(text, username)
                                except Exception as e:
                                    self.log(2, f"发送用户消息到S3-CAM失败: {e}")
                            
                            import threading
                            threading.Thread(target=send_to_s3cam_async, daemon=True, name="S3CAM-Async").start()

                        # 2. 向WebUI发送用户消息 - 使用固定的UID=1和用户名="User"
                        self._notify_webui({
                            "panelReply": {
                                "content": text,
                                "username": username,  # 使用"User"
                                "uid": uid,            # 使用UID=1
                                "type": "member",
                                "id": int(time.time()),  # 使用时间戳作为ID
                                "timetext": time.strftime("%Y-%m-%d %H:%M:%S")
                            },
                            "Username": username  # 外部Username也使用"User"
                        })

                        # 🔥 已删除重复的S3-CAM调用（上面2269-2273行已经调用过了）

                        # 3. 向SISI发送交互请求
                        from core.interact import Interact
                        interact = Interact("mic", 1, {'user': username, 'msg': text})
                        self._Recorder__sisi.on_interact(interact)
                    except Exception as e:
                        print(f"处理识别结果异常: {str(e)}")
                        import traceback
                        print(traceback.format_exc())

        # 实例化Recorder - 只在SmartSisi实例存在时创建
        if sisi_instance:
            try:
                self.recorder = DeviceRecorder(self.username, sisi_instance)
            except Exception as e:
                self.log(2, f"创建DeviceRecorder失败: {str(e)}")
                self.recorder = None

    def start(self):
        """启动录音处理"""
        if self.recorder:
            # 在启动前，将原始数据标准写入缓存一次，确保起始数据格式正确
            sample_frame = bytearray(b'\x00\x00' * 1024 * 2)
            # 修正：使用recorder的stream_cache而不是self的
            self.recorder.stream_cache.write(sample_frame)

            # 启动录音处理器
            self.log(1, f"启动设备录音处理：{self.device_id}")
            self.log(1, f"[🔍调试] Recorder对象: {self.recorder}, 类型: {type(self.recorder)}")
            self.log(1, f"[🔍调试] Recorder.running: {getattr(self.recorder, 'running', 'N/A')}")
            self.recorder.start()
            self.log(1, f"[🔍调试] Recorder启动后状态: running={getattr(self.recorder, 'running', 'N/A')}")

            # 设置语音能量计数
            self.static_frame_count = 0
            self.energy_history = []

            return True
        else:
            self.log(2, f"❌ 无法启动录音处理: 录音器未初始化")
            return False

    def stop(self):
        """停止录音处理"""
        self.running = False
        if self.recorder:
            self.recorder.stop()  # 使用Recorder的stop方法
        self.stream_cache = None
        self.log(1, f"设备录音处理已停止: {self.device_id}")

    def process_audio_data(self, audio_data):
        """处理从ESP32接收到的音频数据"""
        try:
            # 🔥 添加调试日志：确认方法被调用
            if not hasattr(self, '_audio_data_count'):
                self._audio_data_count = 0
            self._audio_data_count += 1
            if self._audio_data_count % 50 == 1:  # 每50帧记录一次
                self.log(1, f"[🔍音频接收] process_audio_data被调用，已接收{self._audio_data_count}帧，recorder={self.recorder is not None}")
            
            # 检查recorder是否存在
            if not self.recorder:
                if self._audio_data_count % 50 == 1:
                    self.log(2, f"[🔍音频接收] ❌ recorder对象不存在，无法处理音频")
                return False
            
            # 基本检查
            if not audio_data or len(audio_data) < 10:
                return False

            # 确保OPUS解码器已初始化
            if self.opus_decoder is None:
                self.opus_decoder = self._init_opus_decoder()

            # 如果没有解码器，尝试直接使用PCM数据
            pcm_data = None

            # 使用OPUS解码或直接处理PCM数据
            if self.opus_decoder:
                # 使用OPUS解码器
                try:
                    pcm_data = self.opus_decoder.decode(audio_data, 960)
                except Exception:
                    # 解码失败，尝试作为PCM处理
                    if len(audio_data) % 2 != 0:
                        audio_data = audio_data[:-1]  # 确保是偶数长度
                    pcm_data = audio_data
            else:
                # 没有解码器，尝试直接使用PCM
                if len(audio_data) % 2 != 0:
                    audio_data = audio_data[:-1]  # 确保是偶数长度
                pcm_data = audio_data

            # 🔥 系统级回声消除：检查系统是否在播放TTS或音乐
            # 只检查实际的音频播放状态，不检查is_speaking（is_speaking用于暂停自动播放，不代表正在播放音频）
            try:
                from esp32_liusisi.sisi_audio_output import AudioOutputManager, AudioState
                
                # 检查音乐/音频播放状态
                aom = AudioOutputManager.get_instance()
                if aom and aom.is_streaming():
                    if self._audio_data_count % 100 == 1:
                        self.log(1, f"[系统回声消除] 系统正在播放音频(state={aom.state})，丢弃音频帧 #{self._audio_data_count}")
                    return False
                    
            except Exception as e:
                # 如果无法获取状态，继续处理（向后兼容）
                pass

            # 写入数据到Recorder流缓存
            if pcm_data and self.recorder and hasattr(self.recorder, 'stream_cache'):
                self.recorder.stream_cache.write(pcm_data)
                
                # 🔥 修复2：音频分叉 - 发送给前脑系统（和本机麦克风逻辑一致）
                if hasattr(self.recorder, '_send_to_background_brain'):
                    self.recorder._send_to_background_brain(pcm_data)
                    if not hasattr(self, '_brain_send_count'):
                        self._brain_send_count = 0
                    self._brain_send_count += 1
                    if self._brain_send_count % 100 == 1:
                        self.log(1, f"[前脑系统] 已发送{self._brain_send_count}帧音频到前脑后台")
                
                return True

        except Exception as e:
            # 只记录一次错误
            if not hasattr(self, '_pcm_error'):
                print(f"处理音频数据失败: {str(e)}")
                self._pcm_error = True

        return False

    def _update_audio_status(self, pcm_data):
        """更新音频状态"""
        try:
            if not pcm_data:
                return False

            # 设置音频活动标志
            self._audio_active = True
            return True
        except Exception as e:
            self.log(3, f"更新音频状态失败: {str(e)}")
            return False

    def _init_opus_decoder(self):
        """初始化Opus解码器"""
        try:
            import opuslib
            decoder = opuslib.Decoder(fs=16000, channels=1)
            return decoder
        except ImportError:
            try:
                import opuslib_next as opuslib
                decoder = opuslib.Decoder(fs=16000, channels=1)
                return decoder
            except ImportError:
                if not hasattr(SisiDeviceRecorder, '_opus_error'):
                    print("错误: 无法导入OPUS库，请安装: pip install opuslib-wheel")
                    SisiDeviceRecorder._opus_error = True
                return None


def main():
    """测试入口函数"""
    try:
        print("SiSi协议适配器启动中...")

        # 检查网络
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"本机名称: {hostname}")
        print(f"本机IP地址: {local_ip}")

        # 检查端口是否被占用
        port = 8000
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                s.listen(1)
                s.close()
            print(f"端口 {port} 可用")
        except OSError:
            print(f"警告: 端口 {port} 已被占用，请检查是否有其他程序正在使用")
            port = 8001
            print(f"尝试使用备用端口 {port}")

        # 创建适配器实例
        adapter = SisiDeviceAdapter(port=port)

        # 尝试注册TTS钩子
        print("正在注册TTS钩子...")
        tts_hook_success = adapter.register_tts_hooks()
        if not tts_hook_success:
            print("TTS钩子注册失败，继续启动但功能受限")

        # 将适配器实例添加到sisi_booter全局变量中，确保其他模块可以访问
        try:
            booter = _resolve_sisi_booter_module()
            if booter is not None:
                booter.esp32_adapter = adapter
            print("已将ESP32适配器实例添加到sisi_booter模块")
        except ImportError:
            print("无法导入sisi_booter模块，其他模块可能无法访问ESP32适配器")

        # 启动WebSocket服务器
        print(f"正在启动WebSocket服务器，监听端口: {port}...")
        server_thread = adapter.start()

        print(f"SiSi协议适配器已启动，监听地址: ws://0.0.0.0:{port}/sisi/v1/")
        print("本地网络地址: ws://" + local_ip + f":{port}/sisi/v1/")
        print("按Ctrl+C退出...")

        # 保持主线程运行
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("正在关闭服务...")
        adapter.stop()
    except Exception as e:
        print(f"启动失败: {str(e)}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
