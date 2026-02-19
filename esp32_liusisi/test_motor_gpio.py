#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 电机GPIO测试
🔧 专门测试GPIO3和GPIO46的输出
"""

import requests
import time

def test_motor_gpio(esp32_ip="172.20.10.2"):
    """测试电机GPIO输出"""
    base_url = f"http://{esp32_ip}"
    
    print("🔧 ESP32 电机GPIO专项测试")
    print("=" * 40)
    print(f"🎯 目标设备: {esp32_ip}")
    print("🔧 测试GPIO3和GPIO46的输出")
    print("=" * 40)
    
    # 测试连接
    print("🔗 测试ESP32连接...")
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200:
            print(f"✅ ESP32连接正常")
        else:
            print(f"❌ ESP32响应异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ ESP32连接失败: {e}")
        return False
    
    # 测试电机控制命令
    motor_tests = [
        ("正转50%", "motor:50"),
        ("正转100%", "motor:100"),
        ("反转50%", "motor:-50"),
        ("反转100%", "motor:-100"),
        ("停止", "motor:0")
    ]
    
    for test_name, command in motor_tests:
        print(f"\n🔧 测试: {test_name}")
        print(f"📤 发送命令: {command}")
        
        try:
            response = requests.post(
                f"{base_url}/cmd",
                data=command,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ 命令发送成功")
                print(f"📋 响应: {response.text}")
                print("🔍 请用万用表测量GPIO3和GPIO46的电压:")
                if "50" in command:
                    print("   📊 应该看到PWM信号或中等电压")
                elif "100" in command:
                    print("   📊 应该看到满电压3.3V")
                elif command == "motor:0":
                    print("   📊 应该看到0V")
                
                # 等待观察
                print("⏱️ 等待5秒观察...")
                time.sleep(5)
            else:
                print(f"❌ 命令失败: {response.status_code}")
                print(f"   响应: {response.text}")
                
        except Exception as e:
            print(f"❌ 命令异常: {e}")
    
    # 测试拍照特效中的电机
    print(f"\n🎬 测试拍照特效中的电机控制")
    print("📸 调用 /camera/snap 看电机是否转动...")
    
    try:
        response = requests.post(f"{base_url}/camera/snap", timeout=20)
        
        if response.status_code == 200:
            print(f"✅ 拍照成功")
            print("🔍 观察电机是否在以下时间转动:")
            print("   🚗 0-2.5秒: 正转 (GPIO3=HIGH, GPIO46=LOW)")
            print("   🚗 2.5-5秒: 反转 (GPIO3=LOW, GPIO46=HIGH)")
            print("   🛑 5秒后: 停止 (GPIO3=LOW, GPIO46=LOW)")
            print("⏱️ 等待10秒观察...")
            time.sleep(10)
        else:
            print(f"❌ 拍照失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 拍照异常: {e}")
    
    print(f"\n🔧 GPIO测试完成!")
    print("🔍 检查清单:")
    print("   ✅ ESP32连接正常")
    print("   🔧 GPIO3/GPIO46是否有电压输出？")
    print("   🔌 DRV8833的VCC是否接3.3V？")
    print("   🔌 DRV8833的GND是否接地？")
    print("   🔌 DRV8833的IN1是否接GPIO3？")
    print("   🔌 DRV8833的IN2是否接GPIO46？")
    print("   🔌 DRV8833的OUT1/OUT2是否接电机？")
    print("   🔌 DRV8833是否有SLEEP/EN引脚需要拉高？")
    print("   ⚡ 电机电源是否足够？")
    
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ESP32电机GPIO专项测试")
    parser.add_argument("--ip", default="172.20.10.2", help="ESP32设备IP地址")
    args = parser.parse_args()
    
    test_motor_gpio(args.ip)
    
    print("\n🔥 测试完成！请检查硬件连接！")
