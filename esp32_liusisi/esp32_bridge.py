#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ESP32 S3桥接模块 - 专门用于连接ESP32 S3设备
作者: sisi liu
日期: 2025-04-05

说明:
- 此模块启动WebSocket服务器(端口8000)，专门用于ESP32 S3设备连接
- 完全独立于9001端口(WebSocket)/10001端口(TCP)桥接系统
- 通过主程序(main.py)启动时会自动加载此模块
- 新增 mDNS 服务广播功能，使设备能自动发现服务器 IP
"""

import os
import sys
import time
import socket
import threading
import importlib
import asyncio
import traceback
from functools import wraps
from zeroconf import ServiceInfo, Zeroconf

# 设置导入路径
DIR_PATH = os.path.dirname(os.path.realpath(__file__))
SISI_ROOT = os.path.abspath(os.path.join(DIR_PATH, ".."))
if SISI_ROOT not in sys.path:
    sys.path.append(SISI_ROOT)

# 延迟导入核心模块，避免循环依赖
core_modules = {
    "wsa_server": None,
    "sisi_core": None,
    "recorder": None
}

# 适配器实例
adapter_instance = None
adapter_thread = None
is_initialized = False
is_running = False

# mDNS "战场雷达" 相关全局变量
zeroconf_instance = None
mdns_thread = None
mdns_running = False


# 日志函数
def log(level, msg):
    try:
        from utils import util
        util.log(level, f"[ESP32桥接] {msg}")
    except ImportError:
        print(f"[ESP32桥接] {msg}")

def get_local_ip():
    """获取本机局域网IP地址 - 优先返回热点IP"""
    
    # 方法1：检查Windows移动热点IP（192.168.137.1）
    try:
        import subprocess
        result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                # 查找移动热点适配器
                if '移动热点' in line or 'Mobile Hotspot' in line or '本地连接' in line:
                    # 在接下来的几行中查找IP地址
                    for j in range(i+1, min(i+10, len(lines))):
                        if 'IPv4' in lines[j] and '192.168.137.' in lines[j]:
                            ip = lines[j].split(':')[-1].strip()
                            log(1, f"✅ 检测到Windows热点IP: {ip}")
                            return ip
    except Exception as e:
        log(2, f"⚠️ Windows热点IP检测失败: {e}")
    
    # 方法2：尝试连接iPhone热点网关来获取本机IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 尝试连接iPhone热点网关
        s.connect(('172.20.10.1', 1))
        ip = s.getsockname()[0]
        if ip.startswith('172.20.10.'):
            log(1, f"✅ 检测到iPhone热点IP: {ip}")
            return ip
        else:
            log(1, f"🔍 获取到IP: {ip} (可能非iPhone热点)")
            # 继续检查其他可能性
    except Exception as e:
        log(2, f"⚠️ 连接iPhone热点网关失败: {e}")
    finally:
        s.close()
    
    # 方法3：尝试连接通用网关
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 连接到一个不存在但能触发路由选择的地址
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        # 过滤掉明显错误的IP
        if (not ip.startswith('127.') and 
            not ip.startswith('169.254.') and
            not ip.startswith('0.') and
            ip != ''):
            log(1, f"🔍 通用方法获取IP: {ip}")
            return ip
    except Exception as e:
        log(2, f"⚠️ 通用IP检测失败: {e}")
    finally:
        s.close()
    
    # 方法4：Windows特定方法
    try:
        import subprocess
        result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                if 'iPhone' in line or 'Wi-Fi' in line:
                    # 在接下来的几行中查找IP地址
                    for j in range(i+1, min(i+10, len(lines))):
                        if 'IPv4' in lines[j] and '172.20.10.' in lines[j]:
                            ip = lines[j].split(':')[-1].strip()
                            log(1, f"✅ Windows ipconfig检测到iPhone热点IP: {ip}")
                            return ip
                        elif 'IPv4' in lines[j]:
                            ip = lines[j].split(':')[-1].strip()
                            if (not ip.startswith('127.') and 
                                not ip.startswith('169.254.')):
                                log(1, f"🔍 Windows ipconfig获取IP: {ip}")
                                return ip
    except Exception as e:
        log(2, f"⚠️ Windows ipconfig方法失败: {e}")
    
    # 最后的fallback - 返回热点默认IP
    log(2, f"❌ 所有IP检测方法都失败，使用热点默认IP")
    return '192.168.137.1'

def mdns_broadcast_task(port):
    """mDNS广播任务，在独立线程中运行"""
    global zeroconf_instance, mdns_running
    
    try:
        ip_address = get_local_ip()
        service_name = "_sisi-bridge._tcp.local."
        server_name = f"{socket.gethostname().split('.')[0]}.local."

        log(1, f"准备启动mDNS灯塔: 服务名={service_name}, 地址={ip_address}:{port}, 主机名={server_name}")

        info = ServiceInfo(
            service_name,
            f"sisi-bridge.{service_name}",
            addresses=[socket.inet_aton(ip_address)],
            port=port,
            server=server_name,
        )
        
        zeroconf_instance = Zeroconf()
        zeroconf_instance.register_service(info)
        log(1, f"mDNS灯塔已启动，Sisi主机现在可以被自动发现了！")

        while mdns_running:
            time.sleep(1)
        
        log(1, "正在关闭mDNS灯塔...")
        zeroconf_instance.unregister_service(info)
        zeroconf_instance.close()
        log(1, "mDNS灯塔已安全关闭。")

    except Exception as e:
        log(2, f"mDNS灯塔任务异常: {e}")
        traceback.print_exc()


def safe_import_modules():
    """安全地导入核心模块，不会因为导入失败而中断程序"""
    global core_modules

    modules_to_import = {
        "wsa_server": "core.wsa_server",
        "sisi_core": "core.sisi_core",
        "recorder": "core.recorder"
    }

    for key, module_path in modules_to_import.items():
        try:
            core_modules[key] = importlib.import_module(module_path)
            log(1, f"成功导入模块: {module_path}")
        except Exception as e:
            log(2, f"导入模块失败: {module_path} - {str(e)}")
            core_modules[key] = None

def get_safe_web_instance():
    """安全地获取WebSocket实例，避免NoneType错误"""
    global core_modules

    if core_modules["wsa_server"] is None:
        try:
            # 尝试再次导入wsa_server模块
            core_modules["wsa_server"] = importlib.import_module("core.wsa_server")
            log(1, "重新导入wsa_server模块成功")
        except Exception as e:
            log(2, f"重新导入wsa_server模块失败: {str(e)}")
            return None

    try:
        # 获取web实例
        web_instance = core_modules["wsa_server"].get_web_instance()

        # 验证web实例
        if web_instance is None:
            log(2, "获取Web实例返回None")
            return None

        # 验证web实例是否有必要的方法
        required_methods = ['is_connected', 'add_cmd']
        for method in required_methods:
            if not hasattr(web_instance, method):
                log(2, f"Web实例缺少必要的方法: {method}")
                return None

        return web_instance
    except Exception as e:
        log(2, f"获取Web实例异常: {str(e)}")
        return None

def get_web_instance():
    """获取WebSocket实例的兼容包装"""
    try:
        if core_modules["wsa_server"] is None:
            core_modules["wsa_server"] = importlib.import_module("core.wsa_server")
        return core_modules["wsa_server"].get_web_instance()
    except Exception as e:
        log(2, f"获取Web实例异常: {str(e)}")
        return None

def get_sisi_instance():
    """安全地获取SmartSisi实例"""
    global core_modules

    if core_modules["sisi_core"] is None:
        try:
            # 尝试再次导入sisi_core模块
            core_modules["sisi_core"] = importlib.import_module("core.sisi_core")
            log(1, "重新导入sisi_core模块成功")
        except Exception as e:
            log(2, f"重新导入sisi_core模块失败: {str(e)}")
            return None

    try:
        # 尝试从sisi_booter获取已有实例
        try:
            import sys
            if 'sisi_booter' in sys.modules:
                import sisi_booter
                booter_instance = getattr(sisi_booter, 'sisi_core', None) or getattr(sisi_booter, 'sisiCore', None)
                if booter_instance:
                    log(1, "使用sisi_booter中的SmartSisi实例")
                    return booter_instance
        except Exception as e:
            log(2, f"从sisi_booter获取SmartSisi实例失败: {str(e)}")

        # 尝试从core.sisi_booter获取已有实例
        try:
            from core import sisi_booter as core_sisi_booter
            core_booter_instance = getattr(core_sisi_booter, 'sisi_core', None) or getattr(core_sisi_booter, 'sisiCore', None)
            if core_booter_instance:
                log(1, "使用core.sisi_booter中的SmartSisi实例")
                return core_booter_instance
        except Exception as e:
            log(2, f"从core.sisi_booter获取SmartSisi实例失败: {str(e)}")

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
                log(1, "使用全局中转站中的SmartSisi实例")
                return transit.sisi_core
        except Exception as e:
            log(2, f"从全局中转站获取SmartSisi实例失败: {str(e)}")

        # 如果都没有，才创建新实例
        from core.sisi_core import SisiCore
        log(2, "警告：创建新的SmartSisi实例，这可能导致多实例问题")
        sisi_instance = SisiCore()

        # 验证实例是否有效
        if sisi_instance is None:
            log(2, "创建SmartSisi实例返回None")
            return None

        # 验证是否有必要的方法 - 仅检查on_interact方法
        if not hasattr(sisi_instance, 'on_interact'):
            log(2, f"SmartSisi实例缺少必要的方法: on_interact")
            return None

        return sisi_instance
    except Exception as e:
        log(2, f"获取SmartSisi实例异常: {str(e)}")
        return None

def retry_until_success(max_attempts=10, retry_delay=1):
    """装饰器：重试直到成功或达到最大尝试次数"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            last_error = None

            while attempts < max_attempts:
                try:
                    result = func(*args, **kwargs)
                    if result:
                        return result
                except Exception as e:
                    last_error = e

                attempts += 1
                log(1, f"尝试 {attempts}/{max_attempts} 失败，等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)

            log(2, f"达到最大尝试次数 ({max_attempts})，最后错误: {last_error}")
            return None
        return wrapper
    return decorator

@retry_until_success(max_attempts=5, retry_delay=2)
def wait_for_core_initialized():
    """等待SmartSisi核心初始化完成"""
    # 导入核心模块
    safe_import_modules()

    # 检查WebSocket实例
    web_instance = get_web_instance()
    if web_instance is None:
        log(1, "WebSocket实例未初始化，等待...")
        return False

    # 检查SmartSisi实例
    sisi_instance = get_sisi_instance()
    if sisi_instance is None:
        log(1, "SmartSisi实例未初始化，等待...")
        return False

    log(1, "SmartSisi核心已初始化，继续...")
    return True

def initialize_adapter():
    """初始化ESP32适配器 - 简化版，不创建SmartSisi实例"""
    global adapter_instance, is_initialized

    try:
        # 确保当前目录在导入路径中
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.append(current_dir)

        # 导入适配器模块
        try:
            # 🔥 修复：导入importlib.util模块
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "sisi_adapter",
                os.path.join(current_dir, "sisi.adapter.py")
            )
            if not spec:
                log(2, f"无法获取模块规格: {os.path.join(current_dir, 'sisi.adapter.py')}")
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules["sisi_adapter"] = module
            spec.loader.exec_module(module)

            # 获取适配器类
            adapter_class = module.SisiDeviceAdapter

            # 创建适配器实例 - 使用8000端口（与ESP32 S3兼容）
            adapter_instance = adapter_class(port=8000)

            # 同步到sisi.adapter.py的全局实例，确保TTS检测能找到
            module._ADAPTER_INSTANCE = adapter_instance

            # 初始化完成
            is_initialized = True
            log(1, "ESP32适配器初始化成功 (端口8000)，准备接收ESP32 S3连接")
            return True
        except Exception as e:
            log(2, f"从文件导入适配器失败: {str(e)}")
            traceback.print_exc()
            return False
    except Exception as e:
        log(2, f"初始化ESP32适配器失败: {str(e)}")
        traceback.print_exc()
        return False

def start_adapter():
    """启动ESP32适配器"""
    global adapter_instance, adapter_thread, is_initialized, mdns_running, mdns_thread

    if not is_initialized:
        if not initialize_adapter():
            log(2, "ESP32适配器初始化失败，无法启动")
            return False

    try:
        # 启动适配器
        adapter_thread = adapter_instance.start()
        log(1, "ESP32适配器已启动 (端口8000)，等待ESP32 S3设备连接")
        
        # 启动 mDNS "战场雷达" 灯塔
        mdns_running = True
        mdns_thread = threading.Thread(target=mdns_broadcast_task, args=(8000,), daemon=True)
        mdns_thread.start()
        
        return True
    except Exception as e:
        log(2, f"启动ESP32适配器失败: {str(e)}")
        traceback.print_exc()
        return False

def stop_adapter():
    """停止ESP32适配器"""
    global adapter_instance, is_initialized, mdns_running, mdns_thread

    if not is_initialized:
        return False

    try:
        # 停止 mDNS "战场雷达" 灯塔
        if mdns_running:
            mdns_running = False
            if mdns_thread:
                mdns_thread.join(timeout=2)
                log(1, "mDNS广播线程已停止")

        # 停止适配器
        adapter_instance.stop()
        log(1, "ESP32适配器已停止")
        return True
    except Exception as e:
        log(2, f"停止ESP32适配器失败: {str(e)}")
        traceback.print_exc()
        return False

def get_device_status():
    """获取ESP32设备状态 - 用于打断系统状态检测"""
    global adapter_instance, is_initialized

    default_status = {
        "connected": False,
        "audio_playing": False,
        "display_active": False,
        "motor_running": False,
        "camera_working": False,
        "last_heartbeat": None,
        "error": None
    }

    if not is_initialized or not adapter_instance:
        default_status["error"] = "adapter_not_initialized"
        return default_status

    try:
        # 检查适配器是否有设备状态查询方法
        if hasattr(adapter_instance, 'get_device_status'):
            device_status = adapter_instance.get_device_status()
            if device_status:
                return device_status

        # 如果没有专门的状态查询方法，检查基本连接状态
        if hasattr(adapter_instance, 'is_connected'):
            default_status["connected"] = adapter_instance.is_connected()

        # 检查最后心跳时间
        if hasattr(adapter_instance, 'last_heartbeat'):
            default_status["last_heartbeat"] = adapter_instance.last_heartbeat

        return default_status

    except Exception as e:
        log(2, f"获取ESP32设备状态异常: {str(e)}")
        default_status["error"] = str(e)
        return default_status

def send_status_query():
    """向ESP32设备发送状态查询命令"""
    global adapter_instance, is_initialized

    if not is_initialized or not adapter_instance:
        log(2, "适配器未初始化，无法发送状态查询")
        return False

    try:
        # 如果适配器支持发送命令
        if hasattr(adapter_instance, 'send_command'):
            adapter_instance.send_command({
                "type": "status_query",
                "timestamp": time.time()
            })
            log(1, "已发送状态查询命令到ESP32设备")
            return True
        else:
            log(2, "适配器不支持发送命令功能")
            return False

    except Exception as e:
        log(2, f"发送状态查询异常: {str(e)}")
        return False

def delayed_start(delay=5):
    """延迟启动ESP32适配器"""
    def _delayed_start():
        log(1, f"等待 {delay} 秒后启动ESP32适配器...")
        time.sleep(delay)

        # 初始化适配器
        if initialize_adapter():
            # 启动适配器
            if start_adapter():
                log(1, f"ESP32适配器已在端口8000上启动，可以连接ESP32 S3设备")
            else:
                log(2, "ESP32适配器启动失败")
        else:
            log(2, "ESP32适配器初始化失败，无法启动")

    # 创建并启动线程
    thread = threading.Thread(target=_delayed_start, daemon=True)
    thread.start()
    return thread

# 当作为模块导入时自动执行
def auto_start():
    """当作为模块导入时自动执行"""
    log(1, "ESP32桥接模块被导入，准备自动启动...")
    delayed_start(delay=5)

# 当直接运行此文件时
if __name__ == "__main__":
    log(1, "ESP32桥接模块启动...")
    delayed_start(delay=3)

    # 保持主线程运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log(1, "接收到终止信号，停止适配器...")
        stop_adapter()
else:
    # 作为模块导入时，自动启动
    auto_start()
