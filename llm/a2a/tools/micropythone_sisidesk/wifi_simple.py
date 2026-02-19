"""
ESP32-C3 WiFi连接 - 官方标准方法
基于MicroPython官方文档推荐的最简单可靠的WiFi连接方式
避免复杂配置导致的"Wifi Internal Error"
"""

import time
import network
import machine



def do_connect(ssid="iPhone15", password="88888888"):
    """官方推荐的WiFi连接方法 - 最简单可靠"""
    print(f"🔗 连接WiFi: {ssid}")
    

    
    try:
        # ESP32-C3修复方法
        wlan = network.WLAN(network.STA_IF)

        # 修复1: 先关闭再开启
        wlan.active(False)
        time.sleep(0.5)
        wlan.active(True)
        time.sleep(0.5)

        # 修复2: 禁用功率管理
        try:
            wlan.config(pm=wlan.PM_NONE)
            print("✅ 已禁用WiFi功率管理")
        except:
            print("⚠️ 功率管理设置失败")

        # 修复3: 降低发射功率
        try:
            wlan.config(txpower=14)
            print("✅ 已设置WiFi发射功率: 14dBm")
        except:
            print("⚠️ 发射功率设置失败")

        if not wlan.isconnected():
            print('📡 正在连接网络...')
            # 修复4: 只调用一次connect
            wlan.connect(ssid, password)

            # 等待连接
            timeout = 20
            while not wlan.isconnected() and timeout > 0:
                machine.idle()
                timeout -= 1
                if timeout % 5 == 0:
                    status = wlan.status()
                    print(f"⏳ 连接中... 状态:{status} ({20-timeout}/20)")
                time.sleep(1)
        
        if wlan.isconnected():
            # 设置固定IP地址，避免与其他设备冲突
            try:
                from config import FIXED_IP, SUBNET_MASK, GATEWAY, DNS_SERVER
                # 使用配置文件中的固定IP设置
                fixed_ip = FIXED_IP
                subnet = SUBNET_MASK
                gateway = GATEWAY
                dns = DNS_SERVER

                wlan.ifconfig((fixed_ip, subnet, gateway, dns))
                print(f"✅ 设置固定IP: {fixed_ip}")

                # 验证IP设置
                ip_config = wlan.ifconfig()
                ip = ip_config[0]
                print(f"🎉 WiFi连接成功!")
                print(f"📍 IP地址: {ip}")
                print(f"🌐 网关: {ip_config[2]}")
                print(f"🔒 使用固定IP，避免冲突")

                return ip

            except Exception as e:
                print(f"⚠️ 固定IP设置失败: {e}")
                # 回退到动态IP
                ip_config = wlan.ifconfig()
                ip = ip_config[0]
                print(f"🎉 WiFi连接成功 (动态IP)!")
                print(f"📍 IP地址: {ip}")
                print(f"🌐 网关: {ip_config[2]}")

                return ip
        else:
            print("❌ WiFi连接超时")

            return None
            
    except Exception as e:
        print(f"❌ WiFi连接异常: {e}")

        return None

def connect_with_retry(max_retries=10):
    """带重试的WiFi连接"""
    print("🌐 启动WiFi连接系统...")
    
    for attempt in range(max_retries):
        print(f"\n🔄 第 {attempt + 1}/{max_retries} 次尝试")
        
        ip = do_connect()
        if ip:
            print(f"✅ WiFi连接成功: {ip}")
            return ip
        
        if attempt < max_retries - 1:
            print("⏳ 3秒后重试...")
            time.sleep(3)
    
    print("❌ WiFi连接失败，所有重试已用完")
    return None

if __name__ == "__main__":
    # 测试连接
    ip = connect_with_retry()
    if ip:
        print(f"🎉 测试成功: {ip}")
    else:
        print("❌ 测试失败")
