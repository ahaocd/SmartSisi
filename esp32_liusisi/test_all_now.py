#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 SISIeyes 全功能测试脚本

🎯 项目目标总结：
===========================================
1. 🚀 导弹动画跟随音频旋律 -播放音乐时触发3D导弹飞舞动画
2. 🌌 宇宙空间背景 - 星空背景随音频数据实时变化
3. 📝 实时文字推送 - 纯白色、放大、居中显示中文文字
4. 🎬 HTTP视频流播放 - 使用真实111.mp4文件，172x320分辨率
5. 📷 摄像头功能 - 拍照、视频流、按需启动，完整保留
6. 💡 LED控制 - WS2812 RGB灯带，支持十六进制颜色
7. 🚗 电机控制 - DRV8833双向电机，-100到+100速度控制
8. 🎵 音频频谱可视化 - 接收SISI音频数据驱动导弹动画

⚠️  严重警告声明：
===========================================
❌ 禁止删除导弹动画和宇宙背景代码！这是核心功能！
❌ 禁止删除摄像头、LED、电机代码！这些是基础硬件功能！
❌ 禁止简化音频频谱处理！这是驱动导弹动画的关键数据！
❌ 禁止修改HTTP视频流架构！这比官方方案更先进！
❌ 所有功能必须保持完整，只允许修复BUG，不允许删除功能！

🔥 核心工作流程：
===========================================
SISI播放音乐 → 发送音频频谱数据 → ESP32接收 → 音频强度>30 →
自动切换到导弹动画场景 → 🚀导弹跟随旋律飞舞 → 🌌宇宙背景变化

测试所有功能：摄像头、LED、电机、显示屏、音频、视频流
"""

import requests
import time
import threading
import json
from flask import Flask, send_file
import os
import cv2
import numpy as np
import argparse, sys
import time  # 🔧 添加time模块用于照片文件名

class ESP32AllInOneTest:
    def __init__(self, esp32_ip="172.20.10.2", video_file: str | None = None):
        """全功能测试器

        参数
        ----
        esp32_ip: 目标 ESP32 的 IP 地址
        video_file: 本地 MP4 文件路径。若为 None，则自动使用脚本目录下的 ``111.mp4``。
        """

        self.esp32_ip = esp32_ip
        self.base_url = f"http://{esp32_ip}"

        # —— 视频服务器相关 ——
        self.video_server_port = 8080
        self.video_app = None
        self.video_thread = None

        # 若未显式指定，则使用脚本同级目录 111.mp4
        if video_file is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            video_file = os.path.join(script_dir, "111.mp4")
        self.video_file = video_file

        self.video_cap: cv2.VideoCapture | None = None
        self.total_frames: int = 0
        
    def start_video_server(self):
        """启动本地视频服务器 - 使用真实的111.mp4"""
        print("🎬 启动本地视频服务器...")

        # 初始化视频文件
        if not os.path.exists(self.video_file):
            print(f"❌ 视频文件不存在: {self.video_file}")
            return False

        self.video_cap = cv2.VideoCapture(self.video_file)
        self.total_frames = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"📹 视频文件: {self.video_file}, 总帧数: {self.total_frames}")

        app = Flask(__name__)

        @app.route('/video/frame/<int:frame_id>')
        def get_frame(frame_id):
            # 从真实视频文件获取帧
            jpeg_data = self.get_video_frame(frame_id)
            if jpeg_data:
                return jpeg_data, 200, {'Content-Type': 'image/jpeg'}
            else:
                return "Frame not found", 404

        @app.route('/video/info')
        def get_info():
            return json.dumps({
                "total_frames": self.total_frames,
                "fps": 30,
                "width": 172,
                "height": 320
            })

        @app.route('/')
        def index():
            return f"ESP32 Video Server Running - {self.video_file} ({self.total_frames} frames)"

        def run_server():
            app.run(host='0.0.0.0', port=self.video_server_port, debug=False)

        self.video_thread = threading.Thread(target=run_server, daemon=True)
        self.video_thread.start()
        time.sleep(2)  # 等待服务器启动
        print(f"✅ 视频服务器启动成功: http://localhost:{self.video_server_port}")
        return True
    
    def get_video_frame(self, frame_id):
        """从111.mp4获取真实的视频帧"""
        if not self.video_cap or not self.video_cap.isOpened():
            return None

        # 循环播放
        actual_frame = frame_id % self.total_frames

        # 跳转到指定帧
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, actual_frame)
        ret, frame = self.video_cap.read()

        if not ret:
            return None

        # 调整尺寸为ESP32屏幕大小 172x320
        frame_resized = cv2.resize(frame, (172, 320))

        # 编码为JPEG - 🔧 优化为ESP32友好的设置
        encode_param = [
            int(cv2.IMWRITE_JPEG_QUALITY), 70,  # 🔧 降低质量减少数据量
            int(cv2.IMWRITE_JPEG_OPTIMIZE), 1   # 🔧 启用优化
        ]
        result, encoded_img = cv2.imencode('.jpg', frame_resized, encode_param)

        if result:
            return encoded_img.tobytes()
        else:
            return None
    
    def test_1_text_display(self):
        """测试1: 文字显示"""
        print("\n🧪 测试1: SISI文字推送")
        print("-" * 30)
        
        test_texts = [
            "🚀 ESP32测试开始",
            "📱 竖排文字显示",
            "👉 支持换行\n第一行\n第二行",
            "📄 三页测试:ABCDEFGHIJKLMNOPQRSTUVWXYZabcd",
            "🌈 超长句子测试：" + "你好世界" * 20,
            "你好世界",
            "思思眼睛测试",
            "✅ 文字推送成功"
        ]
        
        for i, text in enumerate(test_texts):
            print(f"  📤 发送文字 {i+1}: {text.splitlines()[0]}")
            
            try:
                # 使用统一API
                response = requests.post(
                    f"{self.base_url}/display/text",
                    data=text.encode('utf-8'),
                    headers={'Content-Type': 'text/plain; charset=utf-8'},
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(f"  ✅ 发送成功")
                else:
                    print(f"  ❌ 发送失败: {response.status_code}")
                
                # 根据文本类型，动态调整等待时间以观察翻页
                if "超长句子测试" in text:
                    wait_time = 10
                    print(f"  🕒 超长文本，等待 {wait_time} 秒让其翻页...")
                elif "三页测试" in text:
                    wait_time = 5
                    print(f"  🕒 三页文本，等待 {wait_time} 秒让其翻页...")
                else:
                    wait_time = 3
                
                time.sleep(wait_time)  # 等待显示
                
            except Exception as e:
                print(f"  ❌ 发送异常: {e}")
        
        print("✅ 文字显示测试完成")
    
    def test_2_video_playback(self):
        """测试2: 视频播放"""
        print("\n🧪 测试2: 视频播放")
        print("-" * 30)
        
        # 启动视频服务器
        self.start_video_server()
        
        # 获取本机IP
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        video_server_url = f"http://{local_ip}:{self.video_server_port}"
        print(f"  📺 设置视频服务器: {video_server_url}")
        
        try:
            response = requests.post(
                f"{self.base_url}/video/server",
                data=video_server_url,
                headers={'Content-Type': 'text/plain'},
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"  ✅ 视频服务器设置成功")
                print(f"  🎬 视频播放已启动，等待10秒...")
                time.sleep(10)
            else:
                print(f"  ❌ 视频服务器设置失败: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ 视频设置异常: {e}")
        
        print("✅ 视频播放测试完成")
    
    def test_3_display_modes(self):
        """测试3: 显示模式切换"""
        print("\n🧪 测试3: 显示模式切换")
        print("-" * 30)
        
        modes = [
            ("idle", "待机模式"),
            ("text", "文字模式"),
            ("video", "视频模式")
        ]
        
        for mode, desc in modes:
            print(f"  🎮 切换到 {desc}")
            try:
                response = requests.post(
                    f"{self.base_url}/display/mode",
                    data=mode,
                    headers={'Content-Type': 'text/plain'},
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(f"  ✅ {desc} 切换成功")
                else:
                    print(f"  ❌ {desc} 切换失败: {response.status_code}")
                
                time.sleep(2)
                
            except Exception as e:
                print(f"  ❌ 模式切换异常: {e}")
        
        print("✅ 显示模式测试完成")
    
    def test_4_camera_functions(self):
        """测试4: 摄像头功能"""
        print("\n🧪 测试4: 摄像头功能")
        print("-" * 30)

        try:
            # 测试拍照特效
            print("  🎬 测试拍照特效功能...")
            print("  🎬 特效序列: 电机正转3s → 反转3s → 白闪2次 → 彩虹渐变 → 粉红渐变30s")
            response = requests.post(f"{self.base_url}/camera/snap", timeout=10)

            if response.status_code == 200:
                # 🔧 保存照片到指定文件夹
                image_dir = "E:/liusisi/SmartSisi/@image"
                os.makedirs(image_dir, exist_ok=True)

                photo_filename = f"esp32_photo_with_effects_{int(time.time())}.jpg"
                photo_path = os.path.join(image_dir, photo_filename)

                with open(photo_path, 'wb') as f:
                    f.write(response.content)
                print(f"  ✅ 拍照+特效成功: {len(response.content)} bytes，已保存为 {photo_path}")
                print(f"  🎬 特效正在ESP32上执行，请观察设备...")

                # 🔧 发送照片到ESP32显示屏显示
                try:
                    display_response = requests.post(
                        f"{self.base_url}/display/image",
                        data=response.content,  # 🔧 直接发送二进制数据
                        headers={'Content-Type': 'image/jpeg'},
                        timeout=10  # 🔧 增加超时时间
                    )
                    if display_response.status_code == 200:
                        print(f"  📺 照片已发送到显示屏显示")
                    else:
                        print(f"  ⚠️ 显示屏显示失败: {display_response.status_code}")
                except Exception as e:
                    print(f"  ⚠️ 显示屏显示异常: {e}")

            else:
                print(f"  ❌ 拍照失败: {response.status_code}")

            # 🎬 测试独立特效接口
            print("  🎬 测试独立特效接口...")
            try:
                effect_response = requests.post(
                    f"{self.base_url}/cmd",
                    data="photo_effect",
                    headers={'Content-Type': 'text/plain'},
                    timeout=5
                )
                if effect_response.status_code == 200:
                    print(f"  ✅ 独立特效启动成功")
                    print(f"  🎬 请观察ESP32设备上的特效表演...")
                    print(f"  ⏱️ 特效总时长约40秒 (电机6s + LED效果 + 粉红渐变30s)")
                else:
                    print(f"  ❌ 独立特效启动失败: {effect_response.status_code}")
            except Exception as e:
                print(f"  ❌ 独立特效测试异常: {e}")
            
            # 测试获取帧
            print("  📷 测试获取帧功能...")
            response = requests.get(f"{self.base_url}/camera/frame", timeout=10)
            
            if response.status_code == 200:
                print(f"  ✅ 获取帧成功: {len(response.content)} bytes")
            else:
                print(f"  ❌ 获取帧失败: {response.status_code}")
            
        except Exception as e:
            print(f"  ❌ 摄像头功能异常: {e}")
        
        print("✅ 摄像头功能测试完成")
    
    def test_5_melody_animation(self):
        """测试5: 旋律动画"""
        print("\n🧪 测试5: 旋律动画")
        print("-" * 30)
        
        # 模拟音频数据
        audio_samples = [
            "audio:tone:440",    # 播放440Hz音调
            "audio:tone:880",    # 播放880Hz音调
            "audio:tone:220",    # 播放220Hz音调
        ]
        
        for i, audio_cmd in enumerate(audio_samples):
            print(f"  🎵 发送音频命令 {i+1}: {audio_cmd}")
            try:
                response = requests.post(
                    f"{self.base_url}/cmd",
                    data=audio_cmd,
                    headers={'Content-Type': 'text/plain'},
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(f"  ✅ 音频命令发送成功")
                else:
                    print(f"  ❌ 音频命令发送失败: {response.status_code}")
                
                time.sleep(2)
                
            except Exception as e:
                print(f"  ❌ 音频命令异常: {e}")

        # 🎵 测试真实的音频频谱数据
        self.test_real_audio_spectrum()

        # 🔧 修复：确保动画退出，等待场景切换
        print("  🔇 等待动画退出，切换到空闲场景...")
        time.sleep(5)  # 等待动画完全退出

        print("✅ 旋律动画测试完成")
    
    def test_6_device_status(self):
        """测试6: 设备状态"""
        print("\n🧪 测试6: 设备状态")
        print("-" * 30)
        
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            
            if response.status_code == 200:
                try:
                    status = response.json()
                    print(f"  ✅ 设备状态获取成功:")
                    for key, value in status.items():
                        print(f"    {key}: {value}")
                except:
                    print(f"  ✅ 设备响应成功: {response.text[:100]}...")
            else:
                print(f"  ❌ 设备状态获取失败: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ 设备状态异常: {e}")
        
        print("✅ 设备状态测试完成")
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 ESP32全功能集成测试开始")
        print("=" * 50)
        print(f"🎯 目标设备: {self.esp32_ip}")
        print("=" * 50)
        
        # 测试连接
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            print(f"✅ ESP32设备连接正常")
        except:
            print(f"❌ ESP32设备连接失败，请检查IP地址: {self.esp32_ip}")
            return False
        
        # 运行所有测试
        tests = [
            self.test_1_text_display,
            self.test_2_video_playback,
            self.test_3_display_modes,
            self.test_4_camera_functions,
            self.test_5_melody_animation,
            self.test_6_device_status,
        ]
        
        for test_func in tests:
            try:
                test_func()
                time.sleep(1)  # 测试间隔
            except Exception as e:
                print(f"❌ 测试异常: {e}")
        
        print("\n" + "=" * 50)
        print("🎉 所有测试完成！")
        print("📺 请查看ESP32显示屏上的效果")
        print("=" * 50)

        return True

    def test_real_audio_spectrum(self):
        """测试真实的音频频谱数据"""
        print("    🎵 发送模拟音频频谱数据...")

        # 模拟不同强度的音频频谱数据
        spectrum_tests = [
            [50, 80, 120, 90, 60, 40, 30, 20],      # 低音强，启动动画
            [20, 30, 40, 60, 90, 120, 80, 50],      # 高音强，维持动画
            [100, 100, 100, 100, 100, 100, 100, 100], # 全频段强，维持动画
            [10, 20, 30, 40, 50, 60, 70, 80],       # 渐强，维持动画
            [1, 1, 1, 1, 1, 1, 1, 1],               # 🔧 修复：低强度，退出动画
        ]

        for i, spectrum in enumerate(spectrum_tests):
            print(f"    🎵 发送频谱数据 {i+1}: {spectrum}")
            try:
                # 🔧 修复：发送逗号分隔的字符串，不是JSON
                spectrum_str = ",".join(map(str, spectrum))
                response = requests.post(
                    f"{self.base_url}/melody/animation",
                    data=spectrum_str,
                    headers={'Content-Type': 'text/plain'},
                    timeout=5
                )

                if response.status_code == 200:
                    print(f"      ✅ 频谱数据发送成功")
                else:
                    print(f"      ❌ 频谱数据发送失败: {response.status_code}")

            except Exception as e:
                print(f"      ❌ 频谱数据发送异常: {e}")

            time.sleep(2)  # 观察动画效果

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ESP32 SISIeyes 全功能自动测试脚本")
    parser.add_argument("--ip", default="172.20.10.2", help="ESP32 设备 IP 地址")
    parser.add_argument("--video", default=None, help="本地 MP4 视频文件路径（可选）")
    args = parser.parse_args()

    print("🎯 ESP32全功能集成测试")
    print("测试项目: 文字推送、视频播放、显示模式、摄像头、旋律动画、设备状态")
    
    tester = ESP32AllInOneTest(esp32_ip=args.ip, video_file=args.video)
    
    # —— 运行全部测试 ——
    tester.run_all_tests()
    
    print("\n🔥 测试完成！请检查ESP32显示屏效果！")
