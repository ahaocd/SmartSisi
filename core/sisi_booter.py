# TTS 事件共享机制
_tts_event_subscribers = []
_tts_event_broadcast_enabled = False

def subscribe_tts_event(callback):
    """
    订阅 TTS 事件。
    
    Args:
        callback: 回调函数，签名应为 callback(text, audio_file)
    
    Returns:
        bool: 是否订阅成功
    """
    global _tts_event_subscribers
    if callback not in _tts_event_subscribers:
        _tts_event_subscribers.append(callback)
        return True
    return False
    
def unsubscribe_tts_event(callback):
    """
    取消订阅 TTS 事件。
    
    Args:
        callback: 原已订阅的回调函数
        
    Returns:
        bool: 是否取消成功
    """
    global _tts_event_subscribers
    if callback in _tts_event_subscribers:
        _tts_event_subscribers.remove(callback)
        return True
    return False
    
def notify_tts_event(text, audio_file):
    """
    通知所有 TTS 订阅者。
    
    Args:
        text: TTS 文本
        audio_file: 生成的音频文件路径
        
    Returns:
        int: 成功通知的订阅者数量
    """
    global _tts_event_subscribers
    if not _tts_event_broadcast_enabled:
        return 0
    count = 0
    for callback in _tts_event_subscribers:
        try:
            callback(text, audio_file)
            count += 1
        except Exception as e:
            print(f"TTS事件通知异常: {str(e)}")
    return count

# 核心启动模块
import os
import time
import re
import threading
import copy
import pyaudio
import socket
import sys
import asyncio
import requests
from core.interact import Interact
from core.recorder import Recorder
from scheduler.thread_manager import MyThread
from utils import util, config_util, stream_util
from core.wsa_server import MyServer
from core import wsa_server
from core import socket_bridge_service
from core.transport_topology import load_transport_topology
from core.transport_control_lane import get_transport_control_coordinator
# agent_service 已移除，相关定时器逻辑已禁用
import subprocess
from core import shared_state
import random
from pathlib import Path

# 延迟导入 sisi_core，避免循环依赖
def get_sisi_core():
    from core import sisi_core
    return sisi_core

def _get_cache_root():
    try:
        config_util.load_config()
    except Exception:
        pass
    cache_root = getattr(config_util, "cache_root", None)
    if cache_root:
        return cache_root
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache_data")

def _is_enabled_flag(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")

def get_device_transport_ports():
    topology = load_transport_topology()
    return topology.device_tcp_port, topology.device_ws_port, topology.device_tcp_target_port


def _is_tcp_reachable(host, port, timeout_sec=0.25):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_sec):
            return True
    except Exception:
        return False


def _is_thread_alive(thread_obj):
    try:
        return bool(thread_obj is not None and thread_obj.is_alive())
    except Exception:
        return False


def _is_socket_open(socket_obj):
    try:
        return bool(socket_obj is not None and socket_obj.fileno() >= 0)
    except Exception:
        return False


def _is_listener_ready(thread_obj, socket_obj):
    return bool(_is_thread_alive(thread_obj) and _is_socket_open(socket_obj))


def _is_bridge_service_ready(service_obj, thread_obj):
    if not _is_thread_alive(thread_obj):
        return False
    try:
        return bool(service_obj is not None and getattr(service_obj, "running", False))
    except Exception:
        return False


def _select_ws_bridge_target_port(configured_target_port, fallback_port):
    if configured_target_port <= 0:
        raise RuntimeError("ws bridge target port is invalid")
    if fallback_port <= 0:
        raise RuntimeError("ws bridge fallback port is invalid")
    if configured_target_port == fallback_port:
        return configured_target_port
    if _is_tcp_reachable("127.0.0.1", configured_target_port):
        return configured_target_port
    util.log(
        1,
        f"[transport] ws bridge target {configured_target_port} is unavailable, fallback to {fallback_port}",
    )
    return fallback_port


class AppLayerGatewayService:
    def __init__(
        self,
        *,
        host,
        port,
        media_backend,
        control_backend,
        access_token,
        max_message_bytes,
    ):
        self.host = host
        self.port = int(port)
        self.media_backend = media_backend
        self.control_backend = control_backend
        self.access_token = access_token
        self.max_message_bytes = int(max_message_bytes)
        self.loop = None
        self.server = None

    def start_service(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            from gateway.app.ws_gateway_server import WsGatewayServer

            self.server = WsGatewayServer(
                host=self.host,
                port=self.port,
                media_backend_url=self.media_backend,
                control_backend_url=self.control_backend,
                access_token=self.access_token,
                max_message_bytes=self.max_message_bytes,
            )
            self.loop.run_until_complete(self.server.run_forever())
        except Exception as e:
            util.log(2, f"[gateway] app-layer front door stopped with error: {str(e)}")
        finally:
            try:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            self.server = None
            self.loop.close()
            self.loop = None

    def stop_service(self):
        if self.loop is None or not self.loop.is_running() or self.server is None:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self.server.shutdown(), self.loop)
            future.result(timeout=5)
        except Exception as e:
            util.log(2, f"[gateway] app-layer front door stop failed: {str(e)}")

# 全局变量声明
sisiCore = None
sisi_core = None  # compatibility alias used by existing modules
recorderListener: Recorder = None
__running = False
deviceSocketServer = None
deviceSocketThread = None
DeviceInputListenerDict = {}
controlSocketServer = None
ControlInputListenerDict = {}
ngrok = None
socket_service_instance = None
socket_bridge_service_Thread = None
control_socket_service_instance = None
app_gateway_service_instance = None
app_gateway_service_thread = None
control_socket_bridge_service_thread = None
controlSocketThread = None
transport_health_monitor_thread = None
transport_health_monitor_stop_event = None
active_transport_topology = None
_transport_runtime_lock = threading.Lock()
_transport_runtime_state = {
    "running": False,
    "topology": {},
    "services": {},
    "health": {},
    "degrade": {},
    "updated_ts_ms": 0,
}


def _set_transport_runtime_state(**kwargs):
    with _transport_runtime_lock:
        _transport_runtime_state.update(kwargs)
        _transport_runtime_state["updated_ts_ms"] = int(time.time() * 1000)


def get_transport_runtime_status():
    with _transport_runtime_lock:
        snapshot = copy.deepcopy(_transport_runtime_state)
    try:
        snapshot["control_lane"] = get_transport_control_coordinator().snapshot()
    except Exception:
        snapshot["control_lane"] = {}
    return snapshot


# 运行状态
def is_running():
    return __running

# 录制本地麦克风音频输入并传给阿里云
class RecorderListener(Recorder):

    def __init__(self, device, fei):
        self.__device = device
        self.__FORMAT = pyaudio.paInt16
        self.__running = False
        self.username = 'User'
        # 这两个参数会在 get_stream 中根据当前设备信息更新
        self.channels = None
        self.sample_rate = None
        super().__init__(fei)

    def on_speaking(self, text):
        if len(text) > 1:
            try:
                from core.interact import Interact
                import time

                # 获取最新音频文件路径并输出调试信息
                audio_path = getattr(self, 'latest_audio_file', None)
                print(f"[本地录音] self.latest_audio_file: {audio_path}")

                if not audio_path:
                    # 查找最新的临时音频文件
                    import glob
                    import os
                    cache_root = _get_cache_root()
                    temp_audio_files = glob.glob(os.path.join(cache_root, "tmp*.wav"))
                    if temp_audio_files:
                        audio_path = max(temp_audio_files, key=os.path.getmtime)
                        print(f"[本地录音] 使用最新临时文件: {audio_path}")
                    else:
                        audio_path = os.path.join(cache_root, "input.wav")
                        print(f"[本地录音] 使用默认文件: {audio_path}")
                else:
                    print(f"[本地录音] 使用 latest_audio_file: {audio_path}")

                # 获取 ASR 服务的音频上下文数据
                audio_context = {}
                if hasattr(self, '_Recorder__aLiNls') and self._Recorder__aLiNls:
                    # 从 ASR 实例获取音频上下文数据
                    if hasattr(self._Recorder__aLiNls, 'get_audio_context'):
                        audio_context = self._Recorder__aLiNls.get_audio_context() or {}
                        if audio_context:
                            print(f"[local-input] ASR audio_context items={len(audio_context)}")
                        else:
                            print("[local-input] ASR audio_context empty")
                    else:
                        print("[本地录音] ASR 实例缺少 get_audio_context 方法")
                else:
                    print("[local-input] ASR instance unavailable")

                # 不再直接发送消息到 WebUI，统一交给 SmartSisi 核心处理
                # 直接构造 Interact 并由 Sisi 核心统一处理消息显示
                interact = Interact("socket", 1, {
                    'user': self.username,
                    'msg': text,
                    'audio_path': audio_path,
                    'audio_context': audio_context  # 传递音频上下文数据
                })

                # 同时设置 interact 对象的音频属性
                interact.audio_file = audio_path

                self._Recorder__sisi.on_interact(interact)
            except Exception as e:
                print(f"处理识别结果异常: {str(e)}")

    def get_stream(self):
        try:
            while True:
                config_util.load_config()
                source_cfg = config_util.config.get('source', {}) if isinstance(config_util.config, dict) else {}
                record_cfg = source_cfg.get('record', {}) if isinstance(source_cfg.get('record', {}), dict) else {}
                input_mode = str(source_cfg.get('input_mode', 'device_only') or 'device_only').strip().lower()
                local_capture_enabled = _is_enabled_flag(record_cfg.get('enabled', False)) and input_mode != 'device_only'
                if local_capture_enabled:
                    break
                time.sleep(0.1)

            util.log(1, "等待音频系统稳定后初始化麦克风...")
            time.sleep(3)

            self.paudio = pyaudio.PyAudio()
            default_device = self.paudio.get_default_input_device_info()
            max_input_channels = max(1, int(default_device.get('maxInputChannels', 1)))
            preferred_channels = max(1, min(max_input_channels, 2))
            preferred_rate = int(self.sample_rate or 16000)
            default_rate = int(default_device.get('defaultSampleRate', preferred_rate) or preferred_rate)

            util.printInfo(
                1,
                "系统",
                f"默认麦克风信息 - 默认采样率: {default_rate}Hz, 最大声道数: {max_input_channels}, 首选采样率: {preferred_rate}Hz",
            )

            candidate_channels = []
            for channel in (preferred_channels, 1):
                if 1 <= int(channel) <= max_input_channels and int(channel) not in candidate_channels:
                    candidate_channels.append(int(channel))

            candidate_rates = []
            for rate in (preferred_rate, default_rate, 16000, 44100, 48000):
                rate_int = int(rate)
                if rate_int > 0 and rate_int not in candidate_rates:
                    candidate_rates.append(rate_int)

            open_errors = []
            selected = None
            for channel in candidate_channels:
                for rate in candidate_rates:
                    try:
                        self.stream = self.paudio.open(
                            format=self.__FORMAT,
                            channels=channel,
                            rate=rate,
                            input=True,
                            frames_per_buffer=1024,
                        )
                        selected = (channel, rate)
                        break
                    except Exception as open_err:
                        open_errors.append((channel, rate, str(open_err)))
                if selected is not None:
                    break

            if selected is None:
                last_error = open_errors[-1][2] if open_errors else "unknown"
                raise RuntimeError(f"all microphone open attempts failed: {last_error}")

            self.channels, self.sample_rate = selected
            util.log(1, f"麦克风初始化成功: 采样率={self.sample_rate}Hz, 声道数={self.channels}")

            self.__running = True
            MyThread(target=self.__pyaudio_clear).start()
        except Exception as e:
            util.log(1, f"打开麦克风时出错: {str(e)}")
            util.printInfo(1, self.username, "请检查录音设备是否有误，再重新启动!")
            time.sleep(10)
        return self.stream

    def __pyaudio_clear(self):
        try:
            while self.__running:
                time.sleep(30)
        except Exception as e:
            util.log(1, f"音频清理线程出错: {str(e)}")
        finally:
            if hasattr(self, 'stream') and self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except Exception as e:
                    util.log(1, f"关闭音频流时出错: {str(e)}")

    def stop(self):
        super().stop()
        self.__running = False
        time.sleep(0.1)
        try:
            while self.is_reading:
                time.sleep(0.1)
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
                self.paudio.terminate()
        except Exception as e:
            print(e)
            util.log(1, "请检查设备是否有误，再重新启动!")

    def is_remote(self):
        return False

# 远程设备音频输入监听


class DeviceInputListener(Recorder):
    def __init__(self, deviceConnector, fei):
        super().__init__(fei)
        self.__running = True
        self.streamCache = None
        self.username = 'User'
        self.isOutput = True
        self.deviceConnector = deviceConnector
        self._control_start = b"<control>"
        self._control_end = b"</control>"
        self._pending_data = bytearray()
        self._max_pending_bytes = 64 * 1024
        self._control_coordinator = get_transport_control_coordinator()
        self.thread = MyThread(target=self.run)
        self.thread.start()  # 启动远程音频输入设备监听线程

    def run(self):
        # 启动缓存流
        self.streamCache = stream_util.StreamCache(1024 * 1024 * 20)
        while self.__running:
            try:
                data = b""
                while self.deviceConnector:
                    data = self.deviceConnector.recv(2048)
                    if not data:
                        break
                    self._consume_device_data(data)
                    time.sleep(0.005)
                # self.streamCache.clear()

            except Exception as err:
                pass
            time.sleep(1)

    def _consume_non_control_chunk(self, chunk):
        if not chunk:
            return
        try:
            if b"<username>" in chunk:
                data_str = chunk.decode("utf-8", errors="ignore")
                match = re.search(r"<username>(.*?)</username>", data_str)
                if match:
                    self.username = match.group(1)
                    return
            if b"<output>" in chunk:
                data_str = chunk.decode("utf-8", errors="ignore")
                match = re.search(r"<output>(.*?)</output>", data_str)
                if match:
                    self.isOutput = (match.group(1) == "True")
                    return
        except Exception:
            pass
        self.streamCache.write(chunk)

    def _handle_control_message(self, payload_text):
        global active_transport_topology
        if active_transport_topology is not None and bool(getattr(active_transport_topology, "control_lane_enabled", False)):
            util.log(1, "[transport][control_rx] ignore mixed_audio control payload because dedicated control lane is enabled")
            return
        self._control_coordinator.handle_control_payload(payload_text, source_lane="mixed_audio")

    def _consume_device_data(self, data):
        self._pending_data.extend(data)

        while True:
            start_idx = self._pending_data.find(self._control_start)
            if start_idx < 0:
                keep = max(0, len(self._control_start) - 1)
                if len(self._pending_data) <= keep:
                    return
                flush_len = len(self._pending_data) - keep
                chunk = bytes(self._pending_data[:flush_len])
                del self._pending_data[:flush_len]
                self._consume_non_control_chunk(chunk)
                return

            if start_idx > 0:
                chunk = bytes(self._pending_data[:start_idx])
                del self._pending_data[:start_idx]
                self._consume_non_control_chunk(chunk)
                continue

            end_idx = self._pending_data.find(self._control_end, len(self._control_start))
            if end_idx < 0:
                if len(self._pending_data) > self._max_pending_bytes:
                    util.log(2, "[transport][control_rx] pending buffer overflow, flush as audio path")
                    chunk = bytes(self._pending_data)
                    self._pending_data.clear()
                    self._consume_non_control_chunk(chunk)
                return

            payload_bytes = bytes(self._pending_data[len(self._control_start):end_idx])
            del self._pending_data[:end_idx + len(self._control_end)]

            payload_text = payload_bytes.decode("utf-8", errors="ignore").strip()
            if payload_text:
                self._handle_control_message(payload_text)

    def on_speaking(self, text):
        global sisiCore
        if len(text) > 1:
            # 补全音频路径，避免语音识别时 audio_path 为空
            audio_path = getattr(self, 'latest_audio_file', None)
            if not audio_path:
                # 查找最新的临时音频文件
                import glob
                import os

                cache_root = _get_cache_root()
                temp_audio_files = glob.glob(os.path.join(cache_root, "tmp*.wav"))
                if temp_audio_files:
                    audio_path = max(temp_audio_files, key=os.path.getmtime)
                else:
                    audio_path = os.path.join(cache_root, "input.wav")

            # 获取 ASR 服务的音频上下文数据
            audio_context = {}
            if hasattr(self, '_Recorder__aLiNls') and self._Recorder__aLiNls:
                if hasattr(self._Recorder__aLiNls, 'get_audio_context'):
                    audio_context = self._Recorder__aLiNls.get_audio_context() or {}
                    if audio_context:
                        print(f"[remote-input] ASR audio_context items={len(audio_context)}")
                    else:
                        print("[remote-input] ASR audio_context empty")

            interact = Interact("socket", 1, {
                "user": self.username,
                "msg": text,
                "socket": self.deviceConnector,
                "audio_path": audio_path,  # 传递音频路径
                "audio_context": audio_context,  # 传递音频上下文数据
            })

            # 同时设置 interact 对象的音频属性
            util.printInfo(3, "(" + self.username + ")远程音频输入", '{}'.format(interact.data["msg"]), time.time())
            interact.audio_file = audio_path
            sisiCore.on_interact(interact)

    # recorder 会等待 stream 不为空后再开始读取
    def get_stream(self):
        while self.__running and (not self.deviceConnector or self.streamCache is None):
            time.sleep(1)
        if not self.__running:
            return None
        return self.streamCache

    def stop(self):
        super().stop()
        self.__running = False

    def is_remote(self):
        return True


class ControlInputListener:
    def __init__(self, deviceConnector):
        self.__running = True
        self.deviceConnector = deviceConnector
        self._pending_data = bytearray()
        self._pending_text = bytearray()
        self._control_start = b"<control>"
        self._control_end = b"</control>"
        self._max_pending_bytes = 32 * 1024
        self._control_coordinator = get_transport_control_coordinator()
        self.thread = MyThread(target=self.run)
        self.thread.start()

    def stop(self):
        self.__running = False
        try:
            self.deviceConnector.close()
        except Exception:
            pass

    def run(self):
        while self.__running:
            try:
                data = self.deviceConnector.recv(2048)
                if not data:
                    break
                self._consume_control_data(data)
            except Exception:
                break
        self.__running = False

    def _emit_control_payload(self, payload_text):
        payload = str(payload_text or "").strip()
        if not payload:
            return
        self._control_coordinator.handle_control_payload(payload, source_lane="control_lane")

    def _consume_text_lines(self, chunk: bytes):
        if not chunk:
            return
        self._pending_text.extend(chunk)
        while True:
            line_idx = self._pending_text.find(b"\n")
            if line_idx < 0:
                break
            line = bytes(self._pending_text[:line_idx])
            del self._pending_text[: line_idx + 1]
            text = line.decode("utf-8", errors="ignore").strip()
            if text:
                self._emit_control_payload(text)
        if len(self._pending_text) > 2048:
            text = self._pending_text.decode("utf-8", errors="ignore").strip()
            self._pending_text.clear()
            if text:
                self._emit_control_payload(text)

    def _consume_control_data(self, data: bytes):
        self._pending_data.extend(data)

        while True:
            start_idx = self._pending_data.find(self._control_start)
            if start_idx < 0:
                keep = max(0, len(self._control_start) - 1)
                if len(self._pending_data) <= keep:
                    return
                flush_len = len(self._pending_data) - keep
                chunk = bytes(self._pending_data[:flush_len])
                del self._pending_data[:flush_len]
                self._consume_text_lines(chunk)
                return

            if start_idx > 0:
                chunk = bytes(self._pending_data[:start_idx])
                del self._pending_data[:start_idx]
                self._consume_text_lines(chunk)
                continue

            end_idx = self._pending_data.find(self._control_end, len(self._control_start))
            if end_idx < 0:
                if len(self._pending_data) > self._max_pending_bytes:
                    util.log(2, "[transport][control_lane] pending buffer overflow, flush text buffer")
                    chunk = bytes(self._pending_data)
                    self._pending_data.clear()
                    self._consume_text_lines(chunk)
                return

            payload_bytes = bytes(self._pending_data[len(self._control_start):end_idx])
            del self._pending_data[:end_idx + len(self._control_end)]
            payload_text = payload_bytes.decode("utf-8", errors="ignore").strip()
            if payload_text:
                self._emit_control_payload(payload_text)


# 安全获取 WebSocket 实例，避免 NoneType 错误
def safe_get_web_instance():
    """安全地获取 WebSocket 实例，避免 NoneType 错误"""
    try:
        web_instance = wsa_server.get_web_instance()
        if web_instance is None:
            return None

        # 校验 web 实例是否具备关键方法
        required_methods = ['is_connected', 'add_cmd']
        for method in required_methods:
            if not hasattr(web_instance, method):
                return None

        return web_instance
    except Exception as e:
        util.log(2, f"获取 WebSocket 实例失败: {str(e)}")
        return None


def _pick_active_recorder_for_wake():
    global recorderListener
    global DeviceInputListenerDict

    try:
        if DeviceInputListenerDict:
            for listener in reversed(list(DeviceInputListenerDict.values())):
                if listener is not None:
                    return listener
    except Exception:
        pass

    if recorderListener is not None:
        return recorderListener
    return None


def _handle_external_wake_hit(*, fields, source_lane):
    recorder = _pick_active_recorder_for_wake()
    if recorder is None:
        util.log(
            1,
            f"[wake_session] action=ignore_external_wake reason=no_active_recorder lane={source_lane}",
        )
        return False

    source = str(fields.get("source", "device_kws")).strip() or "device_kws"
    keyword = str(fields.get("keyword", fields.get("wake_word", ""))).strip()
    confidence = str(fields.get("confidence", "")).strip()
    try:
        return bool(
            recorder.apply_external_wake_hit(
                source=source,
                keyword=keyword,
                confidence=confidence,
            )
        )
    except Exception as e:
        util.log(
            2,
            f"[wake_session] action=external_wake_failed lane={source_lane} source={source} error={str(e)}",
        )
        return False


# 修改 device_socket_keep_alive 函数，使用安全获取函数
def device_socket_keep_alive():
    global DeviceInputListenerDict
    while __running:
        delkey = None
        for key, value in DeviceInputListenerDict.items():
            try:
                value.deviceConnector.send(b'\xf0\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8')  # 发送心跳包
                web_instance = safe_get_web_instance()
                if web_instance and web_instance.is_connected(value.username):
                    web_instance.add_cmd({"remote_audio_connect": True, "Username": value.username})
            except Exception:
                util.printInfo(1, value.username, f"远程音频输入输出设备已断开: {key}")
                value.stop()
                delkey = key
                break
        if delkey:
            value = DeviceInputListenerDict.pop(delkey)
            web_instance = safe_get_web_instance()
            if web_instance and web_instance.is_connected(value.username):
                web_instance.add_cmd({"remote_audio_connect": False, "Username": value.username})
        time.sleep(10)


# 远程音频连接服务
def accept_audio_device_output_connect():
    global deviceSocketServer
    global __running
    global DeviceInputListenerDict

    try:
        # 9001 端口(WebSocket)桥接到 10001 端口(TCP)服务
        # 该服务是 WebSocket-TCP 桥接系统，与 ESP32 S3 的 8000 端口完全独立
        audio_device_port, _, _ = get_device_transport_ports()

        deviceSocketServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        deviceSocketServer.bind(("0.0.0.0", audio_device_port))
        deviceSocketServer.listen(1)
        util.log(1, f"[transport] device TCP listener started on {audio_device_port}")

        MyThread(target=device_socket_keep_alive).start()  # 启动心跳包检测

        while __running:
            try:
                deviceConnector, addr = deviceSocketServer.accept()
                deviceInputListener = DeviceInputListener(deviceConnector, sisiCore)
                deviceInputListener.start()
                if addr:
                    listener_key = f"{addr[0]}:{addr[1]}"
                    DeviceInputListenerDict[listener_key] = deviceInputListener
                    util.log(1, f"远程音频设备已连接: {addr}")
            except Exception as e:
                if __running:
                    util.log(1, f"音频设备连接异常: {str(e)}")
                time.sleep(1)
    except OSError as e:
        if e.errno == 10048:
            util.log(1, f"端口{audio_device_port}已被占用，远程音频设备服务启动失败")
        else:
            util.log(1, f"远程音频设备服务启动失败: {str(e)}")
    except Exception as e:
        util.log(1, f"远程音频设备服务启动失败: {str(e)}")


def accept_control_lane_connect():
    global controlSocketServer
    global __running
    global ControlInputListenerDict
    global active_transport_topology

    try:
        control_port = 9004
        if active_transport_topology is not None:
            control_port = int(active_transport_topology.control_tcp_port)
        controlSocketServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        controlSocketServer.bind(("0.0.0.0", control_port))
        controlSocketServer.listen(4)
        util.log(1, f"[transport] control TCP listener started on {control_port}")

        while __running:
            try:
                deviceConnector, addr = controlSocketServer.accept()
                control_listener = ControlInputListener(deviceConnector)
                if addr:
                    listener_key = f"{addr[0]}:{addr[1]}"
                    ControlInputListenerDict[listener_key] = control_listener
                    util.log(1, f"[transport] control lane connected: {addr}")
            except Exception as e:
                if __running:
                    util.log(2, f"[transport] control lane accept failed: {str(e)}")
                time.sleep(0.3)
    except OSError as e:
        if e.errno == 10048:
            util.log(2, f"[transport] control lane port {control_port} is already in use")
        else:
            util.log(2, f"[transport] control lane server failed: {str(e)}")
    except Exception as e:
        util.log(2, f"[transport] control lane server failed: {str(e)}")


def _transport_health_monitor_loop(topology):
    global __running
    global transport_health_monitor_stop_event
    global socket_service_instance
    global control_socket_service_instance
    global app_gateway_service_thread
    global control_socket_bridge_service_thread
    global socket_bridge_service_Thread
    global deviceSocketThread
    global controlSocketThread
    global deviceSocketServer
    global controlSocketServer
    interval_ms = max(500, int(getattr(topology, "health_probe_interval_ms", 5000)))
    interval_sec = max(0.5, interval_ms / 1000.0)
    while __running:
        if transport_health_monitor_stop_event is not None and transport_health_monitor_stop_event.is_set():
            break
        health = {
            "media_tcp_ready": _is_listener_ready(deviceSocketThread, deviceSocketServer),
            "media_ws_ready": _is_bridge_service_ready(socket_service_instance, socket_bridge_service_Thread),
            "control_tcp_ready": False,
            "control_ws_ready": False,
            "gateway_ready": False,
        }
        if topology.control_lane_enabled:
            health["control_tcp_ready"] = _is_listener_ready(controlSocketThread, controlSocketServer)
            health["control_ws_ready"] = _is_bridge_service_ready(
                control_socket_service_instance,
                control_socket_bridge_service_thread,
            )
        if topology.gateway_enabled:
            health["gateway_ready"] = _is_thread_alive(app_gateway_service_thread)
        degraded = {
            "control_lane_degraded": bool(topology.control_lane_enabled and not health["control_ws_ready"]),
            "gateway_degraded": bool(topology.gateway_enabled and not health["gateway_ready"]),
            "reason": "",
        }
        if degraded["control_lane_degraded"]:
            degraded["reason"] = "control_lane_unavailable"
        elif degraded["gateway_degraded"]:
            degraded["reason"] = "gateway_front_door_unavailable"
        _set_transport_runtime_state(health=health, degrade=degraded)
        time.sleep(interval_sec)


# 删除冲突的旧自动播放函数实现，使用 core/sisi_core 中的完整实现


# 停止服务
def stop():
    global sisiCore
    global sisi_core
    global recorderListener
    global __running
    global DeviceInputListenerDict
    global ControlInputListenerDict
    global ngrok
    global deviceSocketThread
    global socket_service_instance
    global socket_bridge_service_Thread
    global control_socket_service_instance
    global app_gateway_service_instance
    global app_gateway_service_thread
    global control_socket_bridge_service_thread
    global controlSocketThread
    global transport_health_monitor_thread
    global transport_health_monitor_stop_event
    global active_transport_topology
    global deviceSocketServer
    global controlSocketServer

    if os.name == 'nt':
        util.log(1, '正在停止启动脚本管理的进程...')
        startup_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shell', 'run_startup.py')
        if os.path.exists(startup_script):
            from shell.run_startup import stop_all_processes
            stop_all_processes()

    util.log(1, '正在关闭服务...')
    __running = False
    try:
        get_transport_control_coordinator().set_wake_hit_handler(None)
    except Exception:
        pass
    if transport_health_monitor_stop_event is not None:
        transport_health_monitor_stop_event.set()
        transport_health_monitor_stop_event = None
    if transport_health_monitor_thread is not None:
        try:
            transport_health_monitor_thread.join(timeout=1.5)
        except Exception:
            pass
        transport_health_monitor_thread = None
    if recorderListener is not None:
        util.log(1, "正在关闭录音服务...")
        recorderListener.stop()
        time.sleep(0.1)

    util.log(1, "正在关闭远程音频输入输出服务...")
    try:
        if len(DeviceInputListenerDict) > 0:
            for key in list(DeviceInputListenerDict.keys()):
                value = DeviceInputListenerDict.pop(key)
                value.stop()
        if len(ControlInputListenerDict) > 0:
            for key in list(ControlInputListenerDict.keys()):
                value = ControlInputListenerDict.pop(key)
                value.stop()
        if deviceSocketServer is not None:
            deviceSocketServer.close()
            deviceSocketServer = None
        if controlSocketServer is not None:
            controlSocketServer.close()
            controlSocketServer = None
        if socket_service_instance is not None:
            socket_service_instance.stop_server()
            socket_service_instance = None
            socket_bridge_service.remove_instance("media")
        if socket_bridge_service_Thread is not None:
            try:
                socket_bridge_service_Thread.join(timeout=1.5)
            except Exception:
                pass
            socket_bridge_service_Thread = None
        if control_socket_service_instance is not None:
            control_socket_service_instance.stop_server()
            control_socket_service_instance = None
            socket_bridge_service.remove_instance("control")
        if app_gateway_service_instance is not None:
            app_gateway_service_instance.stop_service()
            app_gateway_service_instance = None
        if app_gateway_service_thread is not None:
            try:
                app_gateway_service_thread.join(timeout=1.5)
            except Exception:
                pass
            app_gateway_service_thread = None
        if control_socket_bridge_service_thread is not None:
            try:
                control_socket_bridge_service_thread.join(timeout=1.5)
            except Exception:
                pass
            control_socket_bridge_service_thread = None
        if controlSocketThread is not None:
            try:
                controlSocketThread.join(timeout=1.5)
            except Exception:
                pass
            controlSocketThread = None
        if deviceSocketThread is not None:
            try:
                deviceSocketThread.join(timeout=1.5)
            except Exception:
                pass
            deviceSocketThread = None
    except Exception:
        pass

    if config_util.key_chat_module == "agent":
        util.log(1, "⚠️ agent服务已禁用，跳过关闭")

    util.log(1, "正在关闭核心服务...")
    if sisiCore is not None:
        sisiCore.stop()
    sisiCore = None
    sisi_core = None
    active_transport_topology = None
    _set_transport_runtime_state(
        running=False,
        services={},
        health={},
        degrade={"reason": "stopped"},
    )
    util.log(1, '服务已关闭')


# 启动服务
def start():
    """启动 Sisi"""
    global __running, sisiCore, sisi_core, recorderListener, deviceSocketServer
    global deviceSocketThread
    global socket_service_instance, socket_bridge_service_Thread, control_socket_service_instance
    global app_gateway_service_instance, app_gateway_service_thread
    global control_socket_bridge_service_thread, controlSocketThread
    global transport_health_monitor_thread, transport_health_monitor_stop_event
    global active_transport_topology
    __running = True

    device = "default_input"

    from core.sisi_core import SisiCore
    sisiCore = SisiCore()
    sisi_core = sisiCore

    import core.sisi_core as sisi_core_module
    sisi_core_module._sisi_core_instance = sisiCore

    max_retries = 5
    retry_delay = 1
    registered = False

    import sys
    from pathlib import Path

    sisi_root = str(Path(__file__).resolve().parent.parent)
    if sisi_root not in sys.path:
        sys.path.insert(0, sisi_root)

    from llm.transit_station import get_transit_station
    transit = get_transit_station()
    util.log(1, f"[启动器] 获取全局中转站实例，会话ID: {transit.session_id}")

    for retry in range(max_retries):
        try:
            current_core = transit.sisi_core
            current_core_id = id(current_core) if current_core else None
            util.log(1, f"[启动器] 尝试注册SmartSisi核心 (重试 {retry + 1}/{max_retries}), 当前核心ID: {current_core_id}, 新核心ID: {id(sisiCore)}")

            transit.register_sisi_core(sisiCore)

            if transit.sisi_core is sisiCore:
                util.log(1, f"[启动器] SmartSisi核心成功注册到全局中转站 (会话ID: {transit.session_id})")
                registered = True

                try:
                    from llm.sisi_core_bridge import get_bridge
                    bridge = get_bridge()
                    bridge.register_sisi_core(sisiCore)
                    util.log(1, "[启动器] SmartSisi核心成功注册到SmartSisi核心桥接模块")
                except Exception as bridge_err:
                    util.log(2, f"[启动器] 注册SmartSisi核心到SmartSisi核心桥接模块异常: {str(bridge_err)}")

                try:
                    import json
                    from pathlib import Path

                    bridge_dir = Path(sisi_root) / "resources" / "bridge"
                    bridge_dir.mkdir(parents=True, exist_ok=True)

                    status_file = bridge_dir / "sisi_core_status.json"
                    status = {
                        "is_active": True,
                        "timestamp": time.time(),
                        "instance_id": str(id(sisiCore))
                    }

                    with open(status_file, "w", encoding="utf-8") as f:
                        json.dump(status, f, ensure_ascii=False, indent=2)

                    util.log(1, f"[启动器] SmartSisi核心状态已更新到文件 (核心ID: {id(sisiCore)})")
                except Exception as status_err:
                    util.log(2, f"[启动器] 更新SmartSisi核心状态文件异常: {str(status_err)}")
                break
            else:
                util.log(2, f"[启动器] SmartSisi核心注册验证失败，当前核心ID: {id(transit.sisi_core) if transit.sisi_core else None}")
        except Exception as e:
            util.log(2, f"[启动器] 注册SmartSisi核心到中转站异常: {str(e)}")

        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 8)

    if not registered:
        util.log(2, f"[startup] warning register_sisi_core failed after retries={max_retries}")

    config_util.load_config()
    source_cfg = config_util.config.get('source', {}) if isinstance(config_util.config, dict) else {}
    record_cfg = source_cfg.get('record', {}) if isinstance(source_cfg.get('record', {}), dict) else {}

    sisiCore.start()

    try:
        input_mode = str(source_cfg.get('input_mode', 'device_only') or 'device_only').strip().lower()
    except Exception:
        input_mode = 'device_only'

    if input_mode == 'device_only':
        util.log(1, '[input] device_only mode active; local recorder listener is not started')
    else:
        recorderListener = RecorderListener('device', sisiCore)
        recorderListener.start()
        if _is_enabled_flag(record_cfg.get('enabled', False)):
            util.log(1, '[input] local recorder listener started')
        else:
            util.log(1, '[input] local recorder listener started (waiting for record.enabled=true)')

    topology = load_transport_topology()
    active_transport_topology = topology
    control_coordinator = get_transport_control_coordinator()
    control_coordinator.set_wake_hit_handler(_handle_external_wake_hit)
    util.log(1, "[wake_session] external wake_hit handler bound")
    _set_transport_runtime_state(
        running=True,
        topology=topology.summary_fields(),
        services={},
        health={},
        degrade={"reason": ""},
    )
    device_tcp_port = topology.device_tcp_port
    device_ws_port = topology.device_ws_port
    target_tcp_port = topology.device_tcp_target_port
    ws_bridge_target_port = _select_ws_bridge_target_port(target_tcp_port, device_tcp_port)

    deviceSocketThread = MyThread(target=accept_audio_device_output_connect)
    deviceSocketThread.start()

    socket_service_instance = socket_bridge_service.new_instance(
        ws_port=device_ws_port,
        tcp_port=ws_bridge_target_port,
        instance_key="media",
    )
    socket_bridge_service_Thread = MyThread(
        target=socket_service_instance.start_service,
        kwargs={"port": device_ws_port, "tcp_port": ws_bridge_target_port},
    )
    socket_bridge_service_Thread.start()

    time.sleep(0.35)
    tcp_thread_alive = deviceSocketThread.is_alive()
    ws_thread_alive = socket_bridge_service_Thread.is_alive()
    tcp_listen_ready = _is_listener_ready(deviceSocketThread, deviceSocketServer)
    ws_listen_ready = _is_bridge_service_ready(socket_service_instance, socket_bridge_service_Thread)
    control_tcp_thread_alive = False
    control_ws_thread_alive = False
    control_tcp_ready = False
    control_ws_ready = False

    if topology.control_lane_enabled:
        controlSocketThread = MyThread(target=accept_control_lane_connect, name="transport_control_tcp")
        controlSocketThread.start()
        control_socket_service_instance = socket_bridge_service.new_instance(
            ws_port=topology.control_ws_port,
            tcp_port=topology.control_tcp_port,
            instance_key="control",
            text_message_suffix=b"\n",
        )
        control_socket_bridge_service_thread = MyThread(
            target=control_socket_service_instance.start_service,
            kwargs={"port": topology.control_ws_port, "tcp_port": topology.control_tcp_port},
            name="transport_control_ws_bridge",
        )
        control_socket_bridge_service_thread.start()
        time.sleep(0.25)
        control_tcp_thread_alive = controlSocketThread.is_alive()
        control_ws_thread_alive = control_socket_bridge_service_thread.is_alive()
        control_tcp_ready = _is_listener_ready(controlSocketThread, controlSocketServer)
        control_ws_ready = _is_bridge_service_ready(
            control_socket_service_instance,
            control_socket_bridge_service_thread,
        )
        if not control_tcp_thread_alive or not control_tcp_ready:
            util.log(
                2,
                f"[transport] control tcp listener may be unavailable port={topology.control_tcp_port} thread_alive={control_tcp_thread_alive} listen_ready={control_tcp_ready}",
            )
        if not control_ws_thread_alive or not control_ws_ready:
            util.log(
                2,
                f"[transport] control ws bridge may be unavailable port={topology.control_ws_port} thread_alive={control_ws_thread_alive} listen_ready={control_ws_ready}",
            )
    else:
        controlSocketThread = None
        control_socket_service_instance = None
        control_socket_bridge_service_thread = None
        util.log(1, "[transport] control lane disabled by config")

    if topology.control_lane_required and topology.control_lane_enabled and not control_ws_ready:
        _set_transport_runtime_state(degrade={"reason": "control_lane_required_unavailable"})
        raise RuntimeError("control lane required but unavailable")

    gateway_thread_alive = False
    gateway_ready = False
    gateway_port = topology.gateway_port
    gateway_media_backend = topology.resolved_gateway_media_backend()
    gateway_control_backend = topology.resolved_gateway_control_backend()

    if topology.gateway_enabled:
        app_gateway_service_instance = AppLayerGatewayService(
            host=topology.gateway_host,
            port=topology.gateway_port,
            media_backend=gateway_media_backend,
            control_backend=gateway_control_backend,
            access_token=topology.gateway_access_token,
            max_message_bytes=topology.gateway_max_message_bytes,
        )
        app_gateway_service_thread = MyThread(
            target=app_gateway_service_instance.start_service,
            name="app_gateway_front_door",
        )
        app_gateway_service_thread.start()
        time.sleep(0.2)
        gateway_thread_alive = app_gateway_service_thread.is_alive()
        gateway_ready = _is_thread_alive(app_gateway_service_thread)
        if not gateway_thread_alive or not gateway_ready:
            util.log(
                2,
                f"[gateway] front door may be unavailable host={topology.gateway_host} port={topology.gateway_port} thread_alive={gateway_thread_alive} listen_ready={gateway_ready}",
            )
        util.log(
            1,
            f"[gateway] front door enabled host={topology.gateway_host} port={topology.gateway_port} media_backend={gateway_media_backend} control_backend={gateway_control_backend} token_set={bool(topology.gateway_access_token)}",
        )
    else:
        app_gateway_service_instance = None
        app_gateway_service_thread = None
        util.log(1, "[gateway] front door disabled by config")

    if topology.gateway_enabled and not gateway_ready:
        _set_transport_runtime_state(degrade={"reason": "gateway_front_door_unavailable"})
        raise RuntimeError("gateway front door enabled but unavailable")

    if not tcp_thread_alive or not tcp_listen_ready:
        util.log(
            2,
            f"[transport] device tcp listener may be unavailable port={device_tcp_port} thread_alive={tcp_thread_alive} listen_ready={tcp_listen_ready}",
        )
    if not ws_thread_alive or not ws_listen_ready:
        util.log(
            2,
            f"[transport] ws bridge may be unavailable port={device_ws_port} thread_alive={ws_thread_alive} listen_ready={ws_listen_ready}",
        )

    services = {
        "media_tcp": {"thread_alive": bool(tcp_thread_alive), "ready": bool(tcp_listen_ready), "port": int(device_tcp_port)},
        "media_ws": {"thread_alive": bool(ws_thread_alive), "ready": bool(ws_listen_ready), "port": int(device_ws_port)},
        "control_tcp": {
            "enabled": bool(topology.control_lane_enabled),
            "thread_alive": bool(control_tcp_thread_alive),
            "ready": bool(control_tcp_ready),
            "port": int(topology.control_tcp_port),
        },
        "control_ws": {
            "enabled": bool(topology.control_lane_enabled),
            "thread_alive": bool(control_ws_thread_alive),
            "ready": bool(control_ws_ready),
            "port": int(topology.control_ws_port),
        },
        "gateway": {
            "enabled": bool(topology.gateway_enabled),
            "thread_alive": bool(gateway_thread_alive),
            "ready": bool(gateway_ready),
            "port": int(gateway_port),
            "control_backend": gateway_control_backend,
        },
    }
    health = {
        "media_tcp_ready": bool(tcp_listen_ready),
        "media_ws_ready": bool(ws_listen_ready),
        "control_tcp_ready": bool(control_tcp_ready),
        "control_ws_ready": bool(control_ws_ready),
        "gateway_ready": bool(gateway_ready),
    }
    degrade = {
        "control_lane_degraded": bool(topology.control_lane_enabled and not control_ws_ready),
        "gateway_degraded": bool(topology.gateway_enabled and not gateway_ready),
        "reason": "control_lane_unavailable" if (topology.control_lane_enabled and not control_ws_ready) else "",
    }
    _set_transport_runtime_state(services=services, health=health, degrade=degrade)

    util.log(
        1,
        f"[transport] network services status tcp_port={device_tcp_port} tcp_thread={tcp_thread_alive} tcp_ready={tcp_listen_ready} ws_port={device_ws_port} ws_thread={ws_thread_alive} ws_ready={ws_listen_ready} target_tcp={ws_bridge_target_port} control_ws_port={topology.control_ws_port} control_ws_thread={control_ws_thread_alive} control_ws_ready={control_ws_ready} gateway_enabled={topology.gateway_enabled} gateway_port={gateway_port} gateway_thread={gateway_thread_alive} gateway_ready={gateway_ready}",
    )

    transport_health_monitor_stop_event = threading.Event()
    transport_health_monitor_thread = MyThread(
        target=_transport_health_monitor_loop,
        args=(topology,),
        name="transport_health_monitor",
    )
    transport_health_monitor_thread.start()

    try:
        config_util.config['source']['automatic_player_status'] = True
        config_util.config['source']['automatic_player_url'] = 'http://127.0.0.1:6000'
        config_util.save_config(config_util.config)

        from core.sisi_core import start_auto_play_service
        auto_play_thread = MyThread(target=start_auto_play_service, daemon=False)
        auto_play_thread.start()
        util.log(1, "[auto_play] service started")
    except Exception as e:
        util.log(1, f"自动播放服务启动失败: {str(e)}")
        config_util.config['source']['automatic_player_status'] = False
        config_util.save_config(config_util.config)

    if config_util.key_chat_module == "agent":
        util.log(1, "⚠️ agent服务已禁用，跳过启动")

    try:
        esp32_bridge_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "esp32_liusisi",
            "esp32_bridge.py",
        )
        if os.path.exists(esp32_bridge_path):
            util.log(1, "检测到ESP32 S3专用模块，准备加载...")
            try:
                from esp32_liusisi import esp32_bridge  # noqa: F401

                util.log(1, "ESP32 S3适配器已加载，将在端口8000上启动WebSocket服务")
                _, device_ws_port, target_tcp_port = get_device_transport_ports()
                util.log(
                    1,
                    f"端口8000服务独立于设备桥接系统（ws={device_ws_port}/tcp={target_tcp_port}），仅用于ESP32 S3设备",
                )
            except Exception as e:
                util.log(2, f"ESP32 S3适配器加载失败: {str(e)}")
    except Exception as e:
        util.log(2, f"ESP32 S3适配器加载失败: {str(e)}")

    util.log(1, "SmartSisi service startup completed")

    try:
        from utils.emotion_trigger import preload_music_opus_cache
        priority_songs = ["乱世书", "叹云兮", "遇上你是我的缘", "九万字"]
        preload_music_opus_cache(song_names=priority_songs, background=True)
    except Exception as e:
        util.log(2, f"[startup] music preload failed: {str(e)}")

    util.log(
        1,
        f"[transport] android_connection_contract mode=android_initiates endpoint_device=ws://<host>:{topology.gateway_port}/device endpoint_control=ws://<host>:{topology.gateway_port}/control same_wifi_required=0",
    )

def _get_transit_and_register(retry_count=5):
    """Get global transit station and register SmartSisi core with retries."""
    for i in range(retry_count):
        try:
            from llm.transit_station import get_transit_station
            transit = get_transit_station()
            util.log(1, f"[startup] transit session={getattr(transit, 'session_id', 'unknown')}")

            if transit.sisi_core is not None and id(transit.sisi_core) == id(_SISI_INSTANCE):
                util.log(1, "[startup] SmartSisi already registered in transit")
                return transit

            sisi_core_id = id(_sisi_core) if '_sisi_core' in globals() and _sisi_core else None
            util.log(
                1,
                f"[startup] register SmartSisi retry={i+1}/{retry_count} current_core_id={sisi_core_id} new_core_id={id(_SISI_INSTANCE)}",
            )

            success = transit.register_sisi_core(_SISI_INSTANCE)
            if success and transit.sisi_core is not None and id(transit.sisi_core) == id(_SISI_INSTANCE):
                util.log(1, "[startup] SmartSisi registered in transit")
                return transit

            util.log(
                2,
                f"[startup] register SmartSisi failed has_core={transit.sisi_core is not None} core_id={id(transit.sisi_core) if transit.sisi_core else None}",
            )
        except Exception as e:
            util.log(2, f"[startup] register SmartSisi exception retry={i+1}/{retry_count}: {str(e)}")
        time.sleep(0.5)

    util.log(2, f"[startup] register SmartSisi failed after retries={retry_count}")
    return None

if __name__ == '__main__':
    ws_server = None
    sisiCore = None
    sisi_core = None
    recorderListener = None
    start()

