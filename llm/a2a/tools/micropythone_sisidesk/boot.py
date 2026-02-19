"""
boot.py - 极简启动程序 (v1.20.0内存优化)
只负责WiFi连接，删除所有重复代码，从686行减少到30行
"""
import time

def countdown_wifi_start(seconds=10):
    """WiFi启动倒计时"""
    for i in range(seconds, 0, -1):
        print(f"⏳ {i}秒后强制启动WiFi (Ctrl+C取消)")
        time.sleep(1)
    print("🚀 强制启动WiFi连接...")

# 使用wifi_simple模块的连接功能
try:
    from wifi_simple import connect_with_retry
    countdown_wifi_start(10)
    ip_address = connect_with_retry(max_retries=50)
    if ip_address:
        print(f"✅ WiFi系统就绪: {ip_address}")
        print("🚀 继续启动main.py...")
    else:
        print("❌ WiFi连接失败")
        print("💡 解决方案:")
        print("   1. 检查iPhone15热点是否开启")
        print("   2. 确认热点密码为: 88888888")
        print("   3. 使用5V独立供电而非USB供电")
        print("   4. 手动按RST按钮重启设备")
except Exception as e:
    print(f"❌ WiFi模块加载失败: {e}")
