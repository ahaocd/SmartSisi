import codecs
import os
import sys
import random
import time
import audioop
from datetime import datetime
from core import wsa_server
from scheduler.thread_manager import MyThread
from utils import config_util
from utils.pc_audio_stream import get_pc_stream
from colorama import Fore, Style

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(_BASE_DIR, "logs")
LOGS_FILE_URL = os.path.join(LOGS_DIR, "log-" + time.strftime("%Y%m%d%H%M%S") + ".log")

def ensure_log_dir(*parts):
    # 统一写入 logs 根目录，不再分子目录
    path = LOGS_DIR
    os.makedirs(path, exist_ok=True)
    return path

# 定义日志级别
LOG_LEVEL_ERROR = 3    # 错误信息
LOG_LEVEL_WARNING = 2  # 警告信息
LOG_LEVEL_INFO = 1     # 一般信息
LOG_LEVEL_DEBUG = 0    # 调试信息

# 获取配置的日志级别，默认为INFO
def get_log_level():
    try:
        return config_util.config.get("log_level", LOG_LEVEL_INFO)
    except:
        return LOG_LEVEL_INFO

def random_hex(length):
    result = hex(random.randint(0, 16 ** length)).replace('0x', '').lower()
    if len(result) < length:
        result = '0' * (length - len(result)) + result
    return result


def __write_to_file(text):
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR, exist_ok=True)
    file = codecs.open(LOGS_FILE_URL, 'a', 'utf-8')
    file.write(text + "\n")
    file.close()


def printInfo(level, sender, text, send_time=-1):
    # 检查日志级别，低于配置级别的日志不显示
    if level < get_log_level() and not (text.startswith('[错误]') or text.startswith('[警告]')):
        return
        
    if send_time < 0:
        send_time = time.time()
    dt = datetime.now()
    timestr = "[" + dt.strftime('%Y-%m-%d %H:%M:%S') + f".{int(send_time % 1 * 10)}" + "]"
    
    # 日志级别颜色
    level_colors = {
        0: Fore.WHITE,   # 调试
        1: Fore.GREEN,   # 信息
        2: Fore.YELLOW,  # 警告
        3: Fore.RED,     # 错误
    }
    
    color = level_colors.get(level, Fore.WHITE)
    msg = timestr + color + "[" + sender + "] " + text + Style.RESET_ALL
    print(msg)
    
    # 安全地访问WebSocket实例
    try:
        web_instance = wsa_server.get_web_instance()
        if web_instance and web_instance.is_connected(sender):
            msg = timestr + "[" + sender + "] " + text
            if sender == "系统":
                web_instance.add_cmd({"panelMsg": text})
            else:
                web_instance.add_cmd({"panelMsg": text, "Username" : sender})
    except (AttributeError, Exception) as e:
        # 在测试环境或WebSocket未初始化时可能发生，忽略此错误
        pass

    try:
        instance = wsa_server.get_instance()
        if instance and instance.is_connected(sender):
            content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': text}} if sender == "系统" else  {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': text}, "Username" : sender}
            instance.add_cmd(content)
    except (AttributeError, Exception) as e:
        # 在测试环境或WebSocket未初始化时可能发生，忽略此错误
        pass

    MyThread(target=__write_to_file, args=[msg]).start()


def log(level, text):
    try:
        # 对于错误和警告日志，强制提高级别确保显示
        if text.startswith('[错误]'):
            printInfo(LOG_LEVEL_ERROR, "系统", text)
        elif text.startswith('[警告]'):
            printInfo(LOG_LEVEL_WARNING, "系统", text)
        else:
            printInfo(level, "系统", text)
    except Exception as e:
        # 避免日志系统本身出错导致系统崩溃
        print(f"请检查参数是否有误: {str(e)}")
        import traceback
        traceback.print_exc()



def play_audio(file_path, emit_level=True):
    """
    Play WAV audio via persistent PC stream (no file playback fallback).
    """
    try:
        # Skip PC playback if ESP32 is connected
        try:
            from esp32_liusisi.sisi.adapter import get_adapter_instance
            adapter = get_adapter_instance()
            if adapter and len(adapter.clients) > 0:
                log(1, f"[TTS] ESP32 connected, skip PC playback: {file_path}")
                return True
        except Exception:
            pass

        if not os.path.exists(file_path):
            log(1, f"Audio file not found: {file_path}")
            return False

        import wave
        stream = get_pc_stream()
        with wave.open(file_path, 'rb') as wf:
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            max_amp = float(1 << (sample_width * 8 - 1)) if sample_width else 0.0
            level_interval = 0.03
            last_level_ts = 0.0
            while True:
                data = wf.readframes(1024)
                if not data:
                    break
                if emit_level and max_amp > 0:
                    try:
                        rms = audioop.rms(data, sample_width)
                        level = min(1.0, max(0.0, rms / max_amp))
                        now = time.time()
                        if now - last_level_ts >= level_interval:
                            web_instance = wsa_server.get_web_instance()
                            if web_instance:
                                web_instance.add_cmd({"audio_level": level})
                            last_level_ts = now
                    except Exception:
                        pass
                stream.write_pcm(
                    data,
                    sample_rate=sample_rate,
                    channels=channels,
                    sample_width=sample_width,
                )
        if emit_level:
            try:
                web_instance = wsa_server.get_web_instance()
                if web_instance:
                    web_instance.add_cmd({"audio_level": 0})
            except Exception:
                pass
        return True
    except Exception as e:
        log(1, f"Audio playback failed: {str(e)}")
        return False


class DisablePrint:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout
