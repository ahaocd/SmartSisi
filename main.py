#入口文件main
import os
import sys
import json
import pygame
import threading
import importlib
import warnings
warnings.filterwarnings("ignore")

# Ensure UTF-8 output to avoid garbled logs on Windows consoles
try:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 🔧 配置系统日志，禁用调试信息泄露
try:
    from config.logging_config import configure_system_logging, setup_sisi_logging
    configure_system_logging()
    setup_sisi_logging()
except ImportError:
    print("⚠️ 日志配置模块未找到，使用默认配置")

# ===== 修复Windows平台的asyncio事件循环关闭错误 =====
import asyncio
import platform
if platform.system() == 'Windows':
    # 针对Windows平台的ProactorEventLoop关闭错误进行修复
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 修复Windows下的_ProactorBasePipeTransport.__del__错误
    import sys
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8:
        # Python 3.8及以上版本的修复方法
        try:
            from functools import wraps
            import inspect
            
            # 获取原始的__del__方法
            original_proactor_del = asyncio.proactor_events._ProactorBasePipeTransport.__del__
            
            # 创建安全的__del__包装器
            @wraps(original_proactor_del)
            def __del__(self):
                try:
                    original_proactor_del(self)
                except (RuntimeError, AttributeError, ImportError):
                    # 忽略事件循环关闭错误
                    pass
            
            # 替换原始的__del__方法
            asyncio.proactor_events._ProactorBasePipeTransport.__del__ = __del__
            
        except (ImportError, AttributeError):
            # 如果上述方法失败，不进行修改
            pass

# 初始化pygame音频系统，若WASAPI失败则回退到 DirectSound 或 Dummy 驱动
try:
    pygame.mixer.init()
except pygame.error as e:
    try:
        import os
        # 尝试切换到 DirectSound 驱动
        os.environ["SDL_AUDIODRIVER"] = "directsound"
        pygame.mixer.init()
    except pygame.error:
        # 最后降级到无声驱动，保证程序能继续启动
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        try:
            pygame.mixer.init()
            print("[警告] 未能初始化真实音频设备，已使用 dummy 音频驱动，程序继续运行但无声音输出")
        except pygame.error:
            print("[错误] 无法初始化任何音频驱动: " + str(e))
            # 程序仍继续运行，后续模块需判断 mixer.get_init()

from datetime import datetime
from utils.util import log
from utils import config_util as cfg
from gui import flask_server

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

os.environ['PATH'] += os.pathsep + os.path.join(os.getcwd(), "test", "ovr_lipsync", "ffmpeg", "bin")
import time
import psutil
import re
import argparse
from utils import config_util, util
from asr import ali_nls
from core import wsa_server
from gui import flask_server
from gui.window import MainWindow
# 🚨 content_db已删除，使用Mem0记忆系统
from core import sisi_booter
from scheduler.thread_manager import MyThread
from core.interact import Interact
import signal
import subprocess

# ============== 全局变量定义 ==============
esp32_server = None  # ESP32服务器全局实例
recorderListener = None  # RecorderListener实例

# ESP32服务器函数
def init_esp32_server():
    """初始化ESP32服务器 - 已禁用，使用sisi_booter中的DeviceInputListener处理ESP32连接"""
    global esp32_server
    try:
        # 检查配置但不启动服务
        esp32_config = config_util.config.get("esp32_server", {})
        util.log(1, "ESP32服务器已禁用，使用DeviceInputListener处理ESP32连接 (端口: 10001)")
        
        # 修改配置确保禁用
        if "enabled" in esp32_config:
            esp32_config["enabled"] = False
            config_util.config["esp32_server"] = esp32_config
            config_util.save_config(config_util.config)
    except Exception as e:
        util.log(1, f"ESP32服务器配置更新失败: {str(e)}")

def get_esp32_server_instance():
    """获取ESP32服务器实例"""
    return esp32_server

#载入配置
cfg.load_config()

#是否为普通模式（桌面模式）
if cfg.config.get("start_mode") == 'common':
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import QApplication

#音频清理
def __clear_samples(clear_all=False):
    if not os.path.exists("./samples"):
        os.makedirs("./samples")
    current_time = time.time()
    for file_name in os.listdir('./samples'):
        file_path = os.path.join('./samples', file_name)
        try:
            # 清理普通音频文件（非开场白缓存）
            if file_name.startswith('sample-') and not file_name.endswith('_opening.wav'):
                if clear_all or current_time - os.path.getmtime(file_path) > 7 * 24 * 3600:
                    os.remove(file_path)
            # 清理过期的开场白缓存（7天）
            elif file_name.startswith('opening_'):
                if current_time - os.path.getmtime(file_path) > 7 * 24 * 3600:
                    os.remove(file_path)
        except Exception as e:
            util.log(1, f"清理音频文件失败: {str(e)}")

#日志文件清理
def __clear_logs(clear_all=False):
    import time
    current_time = time.time()
    
    log_root = util.LOGS_DIR
    if not os.path.exists(log_root):
        os.makedirs(log_root)
    for root, _, files in os.walk(log_root):
        for file_name in files:
            if not file_name.endswith('.log'):
                continue
            file_path = os.path.join(root, file_name)
            try:
                if clear_all or current_time - os.path.getmtime(file_path) > 7 * 24 * 3600:
                    os.remove(file_path)
            except Exception as e:
                util.log(1, f"清理日志文件失败: {str(e)}")

#缓存文件清理
def __clear_cache(clear_all=False):
    import time
    current_time = time.time()
    cache_root = cfg.cache_root or "./cache_data"
    if not os.path.exists(cache_root):
        os.makedirs(cache_root)
    opus_cache_dir = os.path.join(cache_root, "music_cache", "opus_music")
    for root, _, files in os.walk(cache_root):
        for file_name in files:
            if file_name.lower() in ("readme.md", ".gitkeep", "input.wav"):
                continue
            if file_name.lower() in ("high_quality_voice.wav", "id1.wav"):
                continue
            if os.path.sep + "speaker_profiles" + os.path.sep in (root + os.path.sep):
                continue
            if opus_cache_dir and (root + os.path.sep).startswith(opus_cache_dir + os.path.sep):
                continue
            if file_name.lower().endswith(".opus_cache"):
                continue
            file_path = os.path.join(root, file_name)
            try:
                if clear_all or current_time - os.path.getmtime(file_path) > 7 * 24 * 3600:
                    os.remove(file_path)
            except Exception as e:
                util.log(1, f"清理缓存文件失败: {str(e)}")

def __start_periodic_cache_cleanup():
    """周期性清理缓存（只在系统空闲时执行）"""
    import threading
    import time

    def periodic_cleanup():
        while True:
            try:
                time.sleep(3600)  # 1小时一次
                if __is_system_idle():
                    __clear_cache(clear_all=False)
            except Exception as e:
                util.log(1, f"缓存周期清理异常: {str(e)}")

    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()

# ???????????
def __is_system_idle():
    try:
        from core import shared_state
        with shared_state.auto_play_lock:
            is_auto_playing = bool(shared_state.is_auto_playing)
    except Exception:
        is_auto_playing = False

    chatting = False
    speaking_flag = False
    try:
        from core import sisi_booter
        fei = getattr(sisi_booter, "sisi_core", None)
        if fei:
            chatting = bool(getattr(fei, "chatting", False))
            speaking_flag = bool(getattr(fei, "speaking", False))
    except Exception:
        pass

    return not (is_auto_playing or chatting or speaking_flag)


def __compress_temp_files(clear_all=False):
    import time
    from datetime import datetime
    import shutil
    import subprocess

    # ???????
    if not __is_system_idle():
        return

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        util.log(2, "? FFmpeg ????????? OPUS")
        return

    src_dir = cfg.cache_root or "./cache_data"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    archive_dir = os.path.join(base_dir, "asr", "archive")
    if not os.path.exists(src_dir):
        os.makedirs(src_dir)
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)

    if not clear_all:
        try:
            from core import sisi_booter
            fei = getattr(sisi_booter, "sisi_core", None)
            if fei:
                if getattr(fei, "speaking", False):
                    return
                if getattr(fei, "chatting", False):
                    return
                if hasattr(fei, "sound_query") and not fei.sound_query.empty():
                    return
        except Exception:
            pass

    current_time = time.time()
    min_age_sec = 0 if clear_all else 60  # ????????????

    compressed_count = 0
    errors = 0

    for file_name in os.listdir(src_dir):
        if not ((file_name.startswith("input_") or file_name.startswith("tmp")) and file_name.endswith(".wav")):
            continue
        file_path = os.path.join(src_dir, file_name)
        try:
            if current_time - os.path.getmtime(file_path) < min_age_sec:
                continue

            ts = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            out_name = f"asr_{ts}.opus"
            out_path = os.path.join(archive_dir, out_name)

            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                file_path,
                "-c:a",
                "libopus",
                "-b:a",
                "24k",
                "-vbr",
                "on",
                out_path
            ]
            subprocess.run(cmd, check=True)

            os.remove(file_path)  # ??? WAV
            compressed_count += 1
        except Exception:
            errors += 1

    if compressed_count > 0:
        util.log(1, f"? ??????: {compressed_count} ? (OPUS)")
    if errors > 0:
        util.log(2, f"? ??????: {errors} ?")
def __start_periodic_compress():
    """????????????????"""
    import threading
    import time

    def periodic_compress():
        while True:
            try:
                time.sleep(600)  # ?10??????
                __compress_temp_files(clear_all=False)
            except Exception as e:
                util.log(1, f"???????: {str(e)}")

    compress_thread = threading.Thread(target=periodic_compress, daemon=True)
    compress_thread.start()
    util.log(1, "? ?????????????????")

#ip替换
def replace_ip_in_file(file_path, new_ip):
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()
    content = re.sub(r"127\.0\.0\.1", new_ip, content)
    content = re.sub(r"localhost", new_ip, content)
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)           


def kill_process_by_port(port):
    for conn in psutil.net_connections(kind='inet'):
        if conn.laddr.port == port and conn.pid:
            try:
                proc = psutil.Process(conn.pid)
                proc.terminate()
                proc.wait()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass


#控制台输入监听
def console_listener():
    while True:
        try:
            text = input()
        except EOFError:
            util.log(1, "控制台已经关闭")
            break
        
        args = text.split(' ')

        if len(args) == 0 or len(args[0]) == 0:
            continue

        if args[0] == 'help':
            util.log(1, 'in <msg> \t通过控制台交互')
            util.log(1, 'restart \t重启服务')
            util.log(1, 'start \t\t启动服务')
            util.log(1, 'stop \t\t关闭服务')
            util.log(1, 'exit \t\t结束程序')
            # util.log(1, 'esp32 \t\t查看ESP32状态')

        elif args[0] == 'stop' and sisi_booter.is_running():
            sisi_booter.stop()
        
        elif args[0] == 'start' and not sisi_booter.is_running():
            sisi_booter.start()

        elif args[0] == 'restart' and sisi_booter.is_running():
            sisi_booter.stop()
            time.sleep(0.1)
            sisi_booter.start()
        
        elif args[0] == 'in' and sisi_booter.is_running():
            if len(args) == 1:
                util.log(1, '错误的参数！')
            msg = text[3:len(text)]
            util.printInfo(3, "控制台", '{}: {}'.format('控制台', msg))
            interact = Interact("console", 1, {'user': 'User', 'msg': msg})
            thr = MyThread(target=sisi_booter.sisi_core.on_interact, args=[interact])
            thr.start()

        elif args[0]=='exit':
            if  sisi_booter.is_running():
                sisi_booter.stop()
                time.sleep(0.1)
                util.log(1,'程序正在退出..')
            ports =[10001, 10002, 10003, 5000, 9001]
            for port in ports:
                kill_process_by_port(port)
            sys.exit(0)
        else:
            util.log(1, '未知命令！使用 \'help\' 获取帮助.')


def main():
    """主程序入口函数，负责启动各个服务"""
    # 加载配置
    cfg.load_config()
    
    # ======== 第一步：清理临时文件 ========
    __clear_samples()
    __clear_logs()
    __clear_cache()
    __compress_temp_files(clear_all=True)  # ???????

    # ======== 启动周期性清理任务 ========
    __start_periodic_compress()
    __start_periodic_cache_cleanup()

    # ======== 第二步：初始化统一记忆系统 ========
    # 🧠 使用Mem0记忆系统替代传统数据库
    contentdb = None
    # 🧠 content_db已删除，使用Mem0记忆系统，无需初始化
    print("[主程序] 🧠 使用Mem0记忆系统，跳过传统数据库初始化")
    
    # ======== 第三步：IP替换 ========
    # sisi_url 仅用于面板图片地址，不做前端静态替换

    # ======== 第四步：启动WebSocket服务器 ========
    # 数字人接口服务
    ws_server = wsa_server.new_instance(port=10002)
    ws_server.start_server()

    # UI数据接口服务
    web_ws_server = wsa_server.new_web_instance(port=10003)
    web_ws_server.start_server()
    
    # ======== 启动ESP32服务器 ========
    init_esp32_server()
    
    # ======== 第五步：启动其他服务 ========
    # 启动阿里云ASR（如果配置使用阿里云）
    if cfg.ASR_mode == "ali":
        ali_nls.start()

    # 添加对ESP32桥接模块的支持 - 延迟加载，SmartSisi核心启动后再初始化
    try:
        # 🔥 修复：确保使用正确的os模块，避免变量名冲突
        import os as os_module  # 使用别名避免后面局部导入的影响
        esp32_bridge_path = os_module.path.join(os_module.path.dirname(os_module.path.abspath(__file__)), "esp32_liusisi", "esp32_bridge.py")
        if os_module.path.exists(esp32_bridge_path):
            util.log(1, "检测到ESP32桥接模块，将在SmartSisi核心启动后自动加载")
    except Exception as e:
        util.log(2, f"检查ESP32桥接模块时出错: {str(e)}")

    # ======== 第六步：设置控制台监听 ========
    util.log(1, '注册命令...')
    MyThread(target=console_listener).start()
    util.log(1, 'restart \t重启服务')
    util.log(1, 'start \t\t启动服务')
    util.log(1, 'stop \t\t关闭服务')
    util.log(1, 'exit \t\t结束程序')
    # util.log(1, 'esp32 \t\t查看ESP32状态')
    util.log(1, '使用 \'help\' 获取帮助.')
    
    # ======== 第六步半：A2A服务器已禁用 ========
    util.log(1, "A2A服务器功能已禁用")

    # ======== 第七步：监控系统已禁用 ========
    util.log(1, "监控系统功能已禁用")

    # ======== 第七点五步：音频收集器已禁用 ========
    util.log(1, "智能音频收集系统功能已禁用")

    # ======== 第七点六步：前脑系统已禁用 ========
    util.log(1, "前脑系统异步处理器功能已禁用")

    # ======== 第八步：启动QwenCLI日志分析 ========
    # 🎯 使用合并后的QwenCLI分析器
    util.log(1, "🎯 正在启动QwenCLI日志分析...")
    try:
        # 导入合并后的QwenCLI分析器
        from evoliu.liuye_frontend.qwen_log_analyzer import run_startup_analysis

        # 在后台启动QwenCLI分析
        def start_qwen_analysis():
            try:
                util.log(1, "🚀 开始QwenCLI启动日志分析...")
                result = run_startup_analysis()
                if result.get("success"):
                    util.log(1, f"✅ QwenCLI日志分析完成！处理了{result.get('logs_analyzed', 0)}个日志")
                else:
                    util.log(2, f"❌ QwenCLI日志分析失败: {result.get('error', '未知错误')}")
            except Exception as qwen_e:
                util.log(2, f"❌ QwenCLI分析器启动失败: {qwen_e}")

        # 在独立线程启动，不阻塞主程序
        import threading
        qwen_thread = threading.Thread(target=start_qwen_analysis, daemon=True)
        qwen_thread.start()
        util.log(1, "🎯 QwenCLI日志分析已在后台启动")

    except Exception as e:
        util.log(2, f"❌ QwenCLI日志分析器加载失败: {e}")

    # ======== 第九步：按模式启动相应服务 ========
    if cfg.get_value("start_mode") == 'web':
        util.log(1, "请通过浏览器访问 http://127.0.0.1:5000/ 管理您的SmartSisi")
        # 先启动Sisi核心服务
        sisi_booter.start()

        # 🔥 启用音频分叉架构（后台前脑系统）
        try:
            if hasattr(sisi_booter, 'recorderListener') and sisi_booter.recorderListener:
                sisi_booter.recorderListener.enable_brain_background(True)
                util.log(1, "🧠 音频分叉架构已启用：主流程(实时交互) + 副流程(后台前脑)")
        except Exception as e:
            util.log(2, f"⚠️ 音频分叉架构启用失败: {e}")

        # Web模式下启动Flask服务器（阻塞式）
        try:
            util.log(1, "🌐 正在启动Flask Web服务器...")
            flask_server.run()
        except Exception as e:
            util.log(2, f"❌ Flask Web服务器启动失败: {e}")
            util.log(1, "🔄 切换到控制台模式继续运行...")
            # 保持程序运行
            while True:
                time.sleep(1)
    else:
        # 先启动Sisi核心服务
        sisi_booter.start()

        # 🔥 启用音频分叉架构（后台前脑系统）
        try:
            if hasattr(sisi_booter, 'recorderListener') and sisi_booter.recorderListener:
                sisi_booter.recorderListener.enable_brain_background(True)
                util.log(1, "🧠 音频分叉架构已启用：主流程(实时交互) + 副流程(后台前脑)")
        except Exception as e:
            util.log(2, f"⚠️ 音频分叉架构启用失败: {e}")

        # 非Web模式下在后台启动Flask服务器
        flask_server.start()

        # 普通模式下启动窗口
        if cfg.get_value("start_mode") == 'common':
            app = QApplication(sys.argv)
            app.setWindowIcon(QtGui.QIcon('icon.png'))
            win = MainWindow()
            time.sleep(1)
            win.show()
            app.exit(app.exec_())
        else:
            # 保持程序运行
            while True:
                time.sleep(1)


# ======== 确保模块导出必要的全局变量和函数 ========
# 导出函数，方便其他模块调用
__all__ = ['init_esp32_server', 'get_esp32_server_instance', 'esp32_server']

# 程序入口点
if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="SmartSisi启动器")
    parser.add_argument('command', nargs='?', default='', help="start")
    parsed_args = parser.parse_args()
    
    # 确保当前目录在导入路径中
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    print(f"[主程序] 当前工作目录: {os.getcwd()}")
    print(f"[主程序] 添加到导入路径: {os.path.dirname(os.path.abspath(__file__))}")
    
    # 启动主程序
    main()

    # 🔥 确保程序保持运行，不自动退出
    try:
        util.log(1, "🎯 SmartSisi启动完成，进入运行状态...")
        util.log(1, "💡 使用 Ctrl+C 退出程序")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        util.log(1, "👋 收到退出信号，正在关闭SmartSisi...")
        # 这里可以添加清理代码
        sys.exit(0)

    # 如果命令行参数是start，则自动启动Sisi服务
    if parsed_args.command.lower() == 'start':
        MyThread(target=sisi_booter.start).start()
