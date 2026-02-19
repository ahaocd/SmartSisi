"""
思思桌面控制系统主程序
提供Web控制界面和电机控制功能
"""

import time
from machine import Pin
import config
from sisi_web import SisiWebServer

def start():
    """启动设备控制系统"""
    print("启动思思桌面控制系统...")

    try:
        # 确保电机处于停止状态
        motor_in1 = Pin(config.DC_MOTOR_IN1_PIN, Pin.OUT, value=0)  # 0=停止
        motor_in2 = Pin(config.DC_MOTOR_IN2_PIN, Pin.OUT, value=0)  # 0=停止

        print("硬件初始化完成")

    except Exception as e:
        print(f"硬件初始化失败: {e}")

    try:
        # 创建并启动思思坐台Web服务器 (拆分版本)
        print("正在启动思思坐台控制系统...")
        server = SisiWebServer()
        print("启动Web控制界面...")

        if server.start_web_server():
            print("✅ Web服务器启动成功")
            server.run_web_server()
        else:
            print("❌ Web服务器启动失败")

    except KeyboardInterrupt:
        print("程序被用户中断")
    except Exception as e:
        print(f"启动失败: {e}")
        print("尝试紧急模式启动...")
        # 紧急模式：启动简化HTTP服务
        try:
            print("启动紧急HTTP服务...")
            import simple_http
            simple_http.start_basic_server()
        except Exception as e2:
            print(f"紧急模式也失败: {e2}")
            print("系统完全无法启动，请检查:")
            print("1. MicroPython固件是否完整")
            print("2. 硬件连接是否正确")
            print("3. 内存是否充足")

# 主程序入口 - MicroPython会自动执行
print("=== ESP32-C3 main.py 启动 (USB优化版) ===")

# 检测并处理USB连接
def handle_usb_connection():
    """处理USB连接状态"""
    try:
        import sys
        import micropython

        # 检测USB连接
        if hasattr(sys, 'stdin') and hasattr(sys.stdin, 'buffer'):
            print("🔌 检测到USB连接，优化启动流程")

            # 禁用键盘中断，防止自动KeyboardInterrupt
            micropython.kbd_intr(-1)
            print("✅ 已禁用USB键盘中断")

            # 短暂延迟，让USB连接稳定
            time.sleep(0.5)

            return True
        else:
            print("🔋 检测到独立供电")
            return False

    except Exception as e:
        print(f"USB检测失败: {e}")
        return False

# 处理USB连接
usb_connected = handle_usb_connection()

# 检查boot.py是否已经启动了系统
try:
    import network
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        print("WiFi已连接，boot.py启动成功")
        print(f"当前IP: {wlan.ifconfig()[0]}")
        # 直接启动应用，不重复WiFi连接
        start()
    else:
        if usb_connected:
            print("USB连接模式：跳过WiFi自动连接，直接启动系统")
            print("💡 如需WiFi连接，请:")
            print("   1. 开启iPhone15热点")
            print("   2. 手动运行: import boot; boot.do_connect()")
            start()
        else:
            print("独立供电模式：启动WiFi自动连接")
            # 备用启动方案
            import boot
            boot.auto_start()
            start()
except Exception as e:
    print(f"检查WiFi状态失败: {e}")
    print("直接启动思思桌面控制系统...")
    start()