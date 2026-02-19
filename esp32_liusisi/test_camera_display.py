#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 SISIeyes 拍照+显示专项测试
📸 专门测试摄像头拍照和图片显示功能
"""

import requests
import time
import os
from datetime import datetime

class ESP32CameraDisplayTest:
    def __init__(self, esp32_ip="172.20.10.2"):
        """拍照+显示专项测试器"""
        self.esp32_ip = esp32_ip
        self.base_url = f"http://{esp32_ip}"
        
        # 创建保存照片的目录
        self.image_dir = "E:/liusisi/SmartSisi/@image"
        os.makedirs(self.image_dir, exist_ok=True)
        
    def test_esp32_connection(self):
        """测试ESP32连接"""
        print("🔗 测试ESP32连接...")
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                print(f"✅ ESP32连接正常: {self.esp32_ip}")
                try:
                    status = response.json()
                    print("📊 设备状态:")
                    for key, value in status.items():
                        print(f"   {key}: {value}")
                except:
                    print(f"📊 设备响应: {response.text[:100]}...")
                return True
            else:
                print(f"❌ ESP32响应异常: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ ESP32连接失败: {e}")
            return False
            
    def test_camera_snap(self):
        """测试拍照功能"""
        print("\n📸 测试拍照功能...")
        
        try:
            print("📷 发送拍照请求...")
            response = requests.post(f"{self.base_url}/camera/snap", timeout=15)
            
            if response.status_code == 200:
                # 保存照片
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                photo_filename = f"esp32_photo_{timestamp}.jpg"
                photo_path = os.path.join(self.image_dir, photo_filename)
                
                with open(photo_path, 'wb') as f:
                    f.write(response.content)
                    
                print(f"✅ 拍照成功!")
                print(f"   📁 文件大小: {len(response.content)} bytes")
                print(f"   💾 保存路径: {photo_path}")
                
                return response.content
            else:
                print(f"❌ 拍照失败: {response.status_code}")
                print(f"   响应内容: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ 拍照异常: {e}")
            return None
            
    def test_camera_frame(self):
        """测试获取帧功能"""
        print("\n📷 测试获取帧功能...")
        
        try:
            print("🎬 发送获取帧请求...")
            response = requests.get(f"{self.base_url}/camera/frame", timeout=10)
            
            if response.status_code == 200:
                print(f"✅ 获取帧成功: {len(response.content)} bytes")
                return response.content
            else:
                print(f"❌ 获取帧失败: {response.status_code}")
                print(f"   响应内容: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ 获取帧异常: {e}")
            return None
            
    def test_display_image_method1(self, image_data):
        """测试方法1: 发送图片数据到ESP32显示"""
        print("\n📺 测试方法1: 发送图片到ESP32显示...")
        
        if not image_data:
            print("❌ 没有图片数据")
            return False
            
        try:
            print("📤 发送图片数据到ESP32...")
            response = requests.post(
                f"{self.base_url}/display/image",
                data=image_data,
                headers={'Content-Type': 'image/jpeg'},
                timeout=15
            )
            
            if response.status_code == 200:
                print("✅ 图片发送成功!")
                print("📺 请观察ESP32显示屏上的图片")
                print("⏱️ 图片将显示60秒")
                return True
            else:
                print(f"❌ 图片发送失败: {response.status_code}")
                print(f"   响应内容: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 图片发送异常: {e}")
            return False
            
    def test_display_image_method2(self):
        """测试方法2: ESP32自拍并显示"""
        print("\n📺 测试方法2: ESP32自拍并显示...")
        
        try:
            print("📸 发送自拍并显示请求...")
            response = requests.post(f"{self.base_url}/display/image", timeout=15)
            
            if response.status_code == 200:
                print("✅ 自拍并显示成功!")
                print("📺 请观察ESP32显示屏上的图片")
                print("⏱️ 图片将显示60秒")
                return True
            else:
                print(f"❌ 自拍并显示失败: {response.status_code}")
                print(f"   响应内容: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 自拍并显示异常: {e}")
            return False
            
    def test_multiple_photos(self, count=3):
        """测试连续拍照"""
        print(f"\n📸 测试连续拍照 ({count}张)...")
        
        photos = []
        for i in range(count):
            print(f"📷 拍照 {i+1}/{count}...")
            photo_data = self.test_camera_snap()
            if photo_data:
                photos.append(photo_data)
                print(f"✅ 第{i+1}张拍照成功")
            else:
                print(f"❌ 第{i+1}张拍照失败")
            
            time.sleep(2)  # 间隔2秒
            
        print(f"📊 连续拍照结果: {len(photos)}/{count} 张成功")
        return photos
        
    def run_comprehensive_test(self):
        """运行综合测试"""
        print("🎯 ESP32拍照+显示综合测试")
        print("=" * 50)
        print(f"🎯 目标设备: {self.esp32_ip}")
        print(f"📁 照片保存目录: {self.image_dir}")
        print("=" * 50)
        
        # 1. 测试连接
        if not self.test_esp32_connection():
            return False
            
        # 2. 测试单次拍照
        print("\n🔍 步骤1: 单次拍照测试")
        photo_data = self.test_camera_snap()
        
        # 3. 测试获取帧
        print("\n🔍 步骤2: 获取帧测试")
        frame_data = self.test_camera_frame()
        
        # 4. 测试显示方法1 (发送图片数据)
        if photo_data:
            print("\n🔍 步骤3: 显示方法1测试")
            success1 = self.test_display_image_method1(photo_data)
            if success1:
                print("⏱️ 等待10秒观察显示效果...")
                time.sleep(10)
        
        # 5. 测试显示方法2 (ESP32自拍显示)
        print("\n🔍 步骤4: 显示方法2测试")
        success2 = self.test_display_image_method2()
        if success2:
            print("⏱️ 等待10秒观察显示效果...")
            time.sleep(10)
            
        # 6. 测试连续拍照
        print("\n🔍 步骤5: 连续拍照测试")
        photos = self.test_multiple_photos(3)
        
        # 7. 测试连续显示
        if photos:
            print("\n🔍 步骤6: 连续显示测试")
            for i, photo in enumerate(photos):
                print(f"📺 显示第{i+1}张照片...")
                self.test_display_image_method1(photo)
                time.sleep(5)  # 每张照片显示5秒
                
        print("\n" + "=" * 50)
        print("🎉 拍照+显示测试完成!")
        print("📊 测试总结:")
        print(f"   📸 拍照功能: {'✅ 正常' if photo_data else '❌ 异常'}")
        print(f"   📷 获取帧功能: {'✅ 正常' if frame_data else '❌ 异常'}")
        print(f"   📺 显示方法1: {'✅ 正常' if photo_data and 'success1' in locals() and success1 else '❌ 异常'}")
        print(f"   📺 显示方法2: {'✅ 正常' if 'success2' in locals() and success2 else '❌ 异常'}")
        print(f"   📸 连续拍照: ✅ {len(photos)}/3 张成功")
        print("=" * 50)
        
        return True
        
    def run_quick_test(self):
        """运行快速测试 - 只测试一次"""
        print("⚡ ESP32拍照+显示快速测试 (单次)")
        print("=" * 40)

        # 测试连接
        if not self.test_esp32_connection():
            return False

        # 只测试一次拍照并显示
        print("📸 单次拍照并显示测试...")
        photo_data = self.test_camera_snap()
        if photo_data:
            success = self.test_display_image_method1(photo_data)
            if success:
                print("⏱️ 等待30秒观察显示效果...")
                print("📺 请仔细观察ESP32显示屏上的图片")
                time.sleep(30)
            else:
                print("❌ 显示失败")
        else:
            print("❌ 拍照失败")

        print("✅ 单次测试完成!")
        return True

    def run_snap_only_test(self):
        """只拍照不显示"""
        print("📸 ESP32只拍照测试")
        print("=" * 40)

        # 测试连接
        if not self.test_esp32_connection():
            return False

        # 只拍照，不显示
        photo_data = self.test_camera_snap()
        if photo_data:
            print("✅ 拍照完成，照片已保存到PC")
            print("❌ 不发送到ESP32显示")
        else:
            print("❌ 拍照失败")

        return True

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ESP32拍照+显示专项测试")
    parser.add_argument("--ip", default="172.20.10.2", help="ESP32设备IP地址")
    parser.add_argument("--quick", action="store_true", help="运行快速测试")
    parser.add_argument("--snap-only", action="store_true", help="只拍照不显示")
    args = parser.parse_args()

    tester = ESP32CameraDisplayTest(esp32_ip=args.ip)

    if args.snap_only:
        tester.run_snap_only_test()
    elif args.quick:
        tester.run_quick_test()
    else:
        tester.run_comprehensive_test()

    print("\n🔥 测试完成！请检查ESP32显示屏效果！")
