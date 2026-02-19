#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# display_enhancement.py - ESP32显示屏增强模块 + 自动视频播放
# 专门为您的ESP32显示屏提供SmartSisi丰富内容和自动视频播放

import time
import json
import requests
import threading
import os
import cv2
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
import logging
from typing import Dict, List, Optional

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoStreamHandler(BaseHTTPRequestHandler):
    """视频流HTTP处理器"""

    def do_GET(self):
        """处理GET请求"""

        if self.path == '/video/info':
            # 返回视频信息
            self.send_video_info()

        elif self.path.startswith('/video/frame/'):
            # 返回指定帧
            frame_num = int(self.path.split('/')[-1])
            self.send_frame(frame_num)

        elif self.path == '/video/stream':
            # 返回MJPEG流
            self.send_mjpeg_stream()

        else:
            self.send_error(404, "Not Found")

    def send_video_info(self):
        """发送视频信息"""
        video_path = os.path.join(os.path.dirname(__file__), "111.mp4")

        if not os.path.exists(video_path):
            self.send_error(404, "Video file not found")
            return

        # 使用OpenCV获取视频信息
        cap = cv2.VideoCapture(video_path)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        info = {
            "total_frames": frame_count,
            "fps": fps,
            "duration": frame_count / fps if fps > 0 else 0,
            "width": width,
            "height": height,
            "target_width": 172,
            "target_height": 320,
            "format": "JPEG"
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        response = json.dumps(info).encode('utf-8')
        self.wfile.write(response)

        logger.info(f"📊 发送视频信息: {frame_count} 帧, {fps:.1f}fps")

    def send_frame(self, frame_num):
        """发送指定帧"""
        video_path = os.path.join(os.path.dirname(__file__), "111.mp4")

        if not os.path.exists(video_path):
            self.send_error(404, "Video file not found")
            return

        try:
            # 打开视频文件
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if frame_num >= total_frames:
                frame_num = frame_num % total_frames  # 循环播放

            # 跳转到指定帧
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                self.send_error(500, "Failed to read frame")
                return

            # 调整尺寸为ESP32屏幕大小 (172x320)
            frame_resized = cv2.resize(frame, (172, 320))

            # 转换为JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            result, jpeg_data = cv2.imencode('.jpg', frame_resized, encode_param)

            if not result:
                self.send_error(500, "Failed to encode frame")
                return

            jpeg_bytes = jpeg_data.tobytes()

            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(jpeg_bytes)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            self.wfile.write(jpeg_bytes)
            logger.info(f"📷 发送帧 {frame_num}: {len(jpeg_bytes)} bytes")

        except Exception as e:
            logger.error(f"❌ 发送帧错误: {e}")
            self.send_error(500, str(e))

    def log_message(self, format, *args):
        """禁用默认日志"""
        pass

class SisiDisplayEnhancement:
    """SmartSisi显示屏内容增强器 + 统一HTTP协议视频播放系统"""

    # SmartSisi的21种情感对应的显示映射
    EMOTION_MAPPING = {
        # 基础情感
        "neutral": {"icon": "😐", "description": "平静"},
        "happy": {"icon": "😊", "description": "开心"},
        "excited": {"icon": "🤩", "description": "兴奋"},
        "sad": {"icon": "😢", "description": "难过"},
        "angry": {"icon": "😠", "description": "生气"},
        "surprised": {"icon": "😲", "description": "惊讶"},
        "confused": {"icon": "😕", "description": "困惑"},
        "thinking": {"icon": "🤔", "description": "思考中"},
        "sleepy": {"icon": "😴", "description": "困倦"},
        "worried": {"icon": "😟", "description": "担心"},
        "confident": {"icon": "😎", "description": "自信"},
        "disappointed": {"icon": "😞", "description": "失望"},
        "embarrassed": {"icon": "😳", "description": "尴尬"},
        "love": {"icon": "😍", "description": "喜爱"},
        "afraid": {"icon": "😨", "description": "害怕"},
        "bored": {"icon": "😑", "description": "无聊"},
        "curious": {"icon": "🧐", "description": "好奇"},
        "frustrated": {"icon": "😤", "description": "沮丧"},
        "hopeful": {"icon": "🤗", "description": "希望"},
        "proud": {"icon": "😏", "description": "骄傲"},
        "relaxed": {"icon": "😌", "description": "放松"}
    }
    
    def __init__(self, websocket_client=None, esp32_ip="172.20.10.2", server_port=8080, auto_start=True):
        self.websocket_client = websocket_client
        self.esp32_ip = esp32_ip
        self.esp32_url = f"http://{esp32_ip}/cmd"
        self.server_port = server_port
        self.current_emotion = "neutral"
        self.conversation_history = []
        self.system_stats = {
            "conversations": 0,
            "runtime": 0,
            "last_interaction": None
        }

        # 视频服务器相关
        self.video_server = None
        self.video_server_thread = None
        self.server_url = f"http://192.168.1.100:{server_port}"  # 需要替换为实际IP

        # 监听器相关
        self.sisi_monitor_thread = None
        self.is_monitoring = False

        # 自动启动功能
        if auto_start:
            self.start_sisi_monitor()
        
    def get_enhanced_emotion_display(self, emotion: str) -> Dict:
        """获取增强的情感显示信息"""
        base_emotion = self.EMOTION_MAPPING.get(emotion, self.EMOTION_MAPPING["neutral"])
        
        return {
            "type": "llm",
            "emotion": emotion,
            "emotion_icon": base_emotion["icon"],
            "emotion_text": base_emotion["description"],
            "timestamp": int(time.time()),
            "enhanced": True
        }
    
    def get_conversation_summary(self) -> str:
        """获取对话摘要，适合在小屏幕显示"""
        if not self.conversation_history:
            return "等待开始对话..."
            
        recent_count = len([c for c in self.conversation_history if c["timestamp"] > time.time() - 3600])
        total_count = len(self.conversation_history)
        
        return f"今日对话 {recent_count}次 | 总计 {total_count}次"
    
    def get_system_status_display(self) -> Dict:
        """获取系统状态显示信息"""
        current_time = time.strftime("%H:%M")
        uptime_hours = int(self.system_stats["runtime"] / 3600)
        
        status_text = f"{current_time} | 运行{uptime_hours}h"
        
        if self.system_stats["last_interaction"]:
            last_time = time.time() - self.system_stats["last_interaction"]
            if last_time < 60:
                status_text += " | 刚刚活跃"
            elif last_time < 3600:
                status_text += f" | {int(last_time/60)}分钟前"
            else:
                status_text += f" | {int(last_time/3600)}小时前"
        
        return {
            "type": "status",
            "text": status_text,
            "conversations": self.system_stats["conversations"],
            "uptime": uptime_hours
        }
    
    def add_conversation(self, role: str, content: str):
        """添加对话记录"""
        self.conversation_history.append({
            "role": role,
            "content": content[:50] + "..." if len(content) > 50 else content,
            "timestamp": time.time()
        })
        
        # 保持最近100条记录
        if len(self.conversation_history) > 100:
            self.conversation_history = self.conversation_history[-100:]
            
        self.system_stats["conversations"] += 1
        self.system_stats["last_interaction"] = time.time()
    
    def send_to_esp32(self, text: str) -> bool:
        """使用统一HTTP协议发送文字到ESP32显示屏"""
        try:
            # 方法1: 使用新的统一API
            response = requests.post(
                f"http://{self.esp32_ip}/display/text",
                data=text.encode('utf-8'),
                headers={'Content-Type': 'text/plain; charset=utf-8'},
                timeout=3
            )

            if response.status_code == 200:
                logger.info(f"✅ 统一API发送成功: {text}")
                return True

            # 方法2: 兼容旧的/cmd接口
            command = f"sisi:{text}"
            response = requests.post(
                self.esp32_url,
                data=command.encode('utf-8'),
                headers={'Content-Type': 'text/plain; charset=utf-8'},
                timeout=3
            )

            if response.status_code == 200:
                logger.info(f"✅ 兼容API发送成功: {text}")
                return True

            logger.error(f"❌ 两种API都失败: {response.status_code}")
            return False

        except Exception as e:
            logger.error(f"❌ ESP32连接失败: {e}")
            return False

    def set_display_mode(self, mode: str) -> bool:
        """设置ESP32显示模式"""
        try:
            response = requests.post(
                f"http://{self.esp32_ip}/display/mode",
                data=mode,
                headers={'Content-Type': 'text/plain'},
                timeout=3
            )

            if response.status_code == 200:
                logger.info(f"✅ 显示模式设置成功: {mode}")
                return True
            else:
                logger.error(f"❌ 显示模式设置失败: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ 设置显示模式异常: {e}")
            return False

    def set_video_server_unified(self, server_url: str) -> bool:
        """使用统一HTTP协议设置视频服务器"""
        try:
            response = requests.post(
                f"http://{self.esp32_ip}/video/server",
                data=server_url,
                headers={'Content-Type': 'text/plain'},
                timeout=5
            )

            if response.status_code == 200:
                logger.info(f"✅ 统一API设置视频服务器成功: {server_url}")
                return True
            else:
                logger.error(f"❌ 统一API设置视频服务器失败: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ 统一API设置视频服务器异常: {e}")
            return False

    def send_enhanced_display_data(self, message_type: str, **kwargs):
        """发送增强的显示数据到ESP32"""
        try:
            if message_type == "emotion":
                emotion = kwargs.get("emotion", "neutral")
                emotion_info = self.EMOTION_MAPPING.get(emotion, self.EMOTION_MAPPING["neutral"])
                text = f"{emotion_info['icon']} {emotion_info['description']}"
                return self.send_to_esp32(text)

            elif message_type == "conversation":
                role = kwargs.get("role", "user")
                content = kwargs.get("content", "")
                self.add_conversation(role, content)

                # 发送对话内容到ESP32
                if role == "user":
                    text = f"👤 {content[:50]}"
                else:
                    text = f"🤖 {content[:50]}"
                return self.send_to_esp32(text)

            elif message_type == "status":
                status_info = self.get_system_status_display()
                return self.send_to_esp32(status_info["text"])

            elif message_type == "notification":
                content = kwargs.get("content", "")
                return self.send_to_esp32(f"📢 {content}")

            else:
                return False

        except Exception as e:
            print(f"发送显示数据失败: {e}")
            return False
    
    def get_personality_display(self) -> Dict:
        """获取SmartSisi个性化显示内容"""
        personality_phrases = [
            "我是您的AI助手SmartSisi",
            "随时为您服务",
            "让我们开始对话吧",
            "有什么可以帮助您的吗？",
            "今天您想聊什么呢？",
            "我在这里倾听您的想法",
            "让我们一起探索知识的海洋",
            "您的问题就是我的使命"
        ]
        
        import random
        phrase = random.choice(personality_phrases)
        
        return {
            "type": "personality",
            "content": phrase,
            "emotion": "friendly",
            "timestamp": int(time.time())
        }
    
    def update_runtime(self):
        """更新运行时间"""
        self.system_stats["runtime"] += 1
    
    def get_conversation_stats(self) -> str:
        """获取对话统计信息"""
        total = len(self.conversation_history)
        recent = len([c for c in self.conversation_history if c["timestamp"] > time.time() - 3600])

        if total == 0:
            return "还没有对话记录"
        elif recent == 0:
            return f"共{total}次对话，今日暂无"
        else:
            return f"今日{recent}次，总计{total}次对话"

    # 🚀 SISI专用方法
    def sisi_speak(self, text: str) -> bool:
        """SmartSisi说话时推送到ESP32"""
        return self.send_to_esp32(f"🤖 SmartSisi: {text[:40]}")

    def user_input(self, text: str) -> bool:
        """用户输入时推送到ESP32"""
        return self.send_to_esp32(f"👤 用户: {text[:40]}")

    def sisi_thinking(self) -> bool:
        """SmartSisi思考状态"""
        return self.send_to_esp32("🤔 SmartSisi正在思考...")

    def sisi_ready(self) -> bool:
        """SmartSisi准备就绪"""
        return self.send_to_esp32("✅ SmartSisi已准备就绪")

    def test_esp32_connection(self) -> bool:
        """测试ESP32连接"""
        return self.send_to_esp32("🔗 SmartSisi连接测试")

    def start_sisi_monitor(self):
        """🔍 启动SmartSisi监听器"""
        logger.info("🔍 启动SmartSisi进程监听器...")

        def monitor_worker():
            self.is_monitoring = True
            sisi_detected = False

            while self.is_monitoring:
                try:
                    # 检查SmartSisi进程是否运行
                    if self.is_sisi_running():
                        if not sisi_detected:
                            logger.info("🎉 检测到SmartSisi进程启动！")
                            sisi_detected = True

                            # 延迟5秒确保SISI完全启动
                            time.sleep(5)

                            # 启动视频播放系统
                            self.auto_start_system()
                    else:
                        if sisi_detected:
                            logger.info("⚠️ SmartSisi进程已停止")
                            sisi_detected = False
                            self.stop_video_server()

                    time.sleep(3)  # 每3秒检查一次

                except Exception as e:
                    logger.error(f"❌ SmartSisi监听异常: {e}")
                    time.sleep(5)

        self.sisi_monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        self.sisi_monitor_thread.start()
        logger.info("✅ SmartSisi监听器已启动")

    def is_sisi_running(self):
        """检查SmartSisi进程是否运行"""
        try:
            import psutil

            # 检查进程名包含python和main.py的进程
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        cmdline = proc.info['cmdline']
                        if cmdline and any('main.py' in arg for arg in cmdline):
                            # 进一步检查是否是SISI的main.py
                            if any('SmartSisi' in arg or 'sisi' in arg for arg in cmdline):
                                return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return False

        except ImportError:
            # 如果没有psutil，使用简单的端口检查
            return self.check_sisi_port()
        except Exception as e:
            logger.error(f"❌ 检查SmartSisi进程异常: {e}")
            return False

    def check_sisi_port(self):
        """检查SmartSisi常用端口是否开放"""
        try:
            import socket

            # SmartSisi常用端口
            sisi_ports = [5000, 9001, 10001]

            for port in sisi_ports:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result == 0:  # 端口开放
                    return True

            return False

        except Exception:
            return False

    def auto_start_system(self):
        """🚀 自动启动完整系统"""
        logger.info("🚀 SmartSisi已启动，开始启动ESP32视频播放系统...")

        # 1. 检查视频文件
        video_path = os.path.join(os.path.dirname(__file__), "111.mp4")
        if not os.path.exists(video_path):
            logger.error(f"❌ 视频文件不存在: {video_path}")
            logger.info("📝 请确保111.mp4文件在当前目录")
            return False

        # 2. 测试ESP32连接
        logger.info("🔗 测试ESP32连接...")
        if not self.test_esp32_connection():
            logger.warning("⚠️ ESP32暂时连接失败，将持续尝试...")
            # 不直接返回False，继续启动服务器
        else:
            logger.info("✅ ESP32连接成功！")

        # 3. 启动视频服务器
        logger.info("🎬 启动视频流服务器...")
        if self.start_video_server():
            # 4. 延迟后通知ESP32
            time.sleep(3)  # 等待服务器完全启动

            # 持续尝试通知ESP32
            self.start_esp32_notification_loop()

            logger.info("🎉 视频播放系统启动完成！")
            return True
        else:
            logger.error("❌ 视频服务器启动失败")
            return False

    def start_esp32_notification_loop(self):
        """启动ESP32通知循环"""
        def notification_worker():
            max_attempts = 10
            attempt = 0

            while attempt < max_attempts:
                try:
                    if self.notify_esp32_video_server():
                        logger.info("✅ ESP32通知成功！")

                        # 发送启动消息
                        time.sleep(1)
                        self.send_to_esp32("🎬 SmartSisi视频系统已启动")
                        time.sleep(1)
                        self.send_to_esp32("📺 正在加载视频流...")
                        break
                    else:
                        attempt += 1
                        logger.info(f"⏳ ESP32通知失败，重试 {attempt}/{max_attempts}")
                        time.sleep(5)  # 等待5秒后重试

                except Exception as e:
                    logger.error(f"❌ ESP32通知异常: {e}")
                    attempt += 1
                    time.sleep(5)

            if attempt >= max_attempts:
                logger.warning("⚠️ ESP32通知达到最大重试次数，请检查ESP32连接")

        threading.Thread(target=notification_worker, daemon=True).start()

    def start_video_server(self):
        """启动视频流服务器"""
        def server_worker():
            try:
                with socketserver.TCPServer(("", self.server_port), VideoStreamHandler) as httpd:
                    logger.info(f"🚀 视频流服务器启动: http://0.0.0.0:{self.server_port}")
                    logger.info(f"📡 可用端点:")
                    logger.info(f"   GET /video/info - 获取视频信息")
                    logger.info(f"   GET /video/frame/N - 获取第N帧")
                    logger.info(f"   GET /video/stream - MJPEG流")
                    self.video_server = httpd
                    httpd.serve_forever()
            except Exception as e:
                logger.error(f"❌ 视频服务器启动失败: {e}")

        try:
            self.video_server_thread = threading.Thread(target=server_worker, daemon=True)
            self.video_server_thread.start()
            return True
        except Exception as e:
            logger.error(f"❌ 视频服务器线程启动失败: {e}")
            return False

    def notify_esp32_video_server(self):
        """使用统一HTTP协议通知ESP32视频服务器地址"""
        try:
            # 获取本机IP地址
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()

            self.server_url = f"http://{local_ip}:{self.server_port}"

            # 方法1: 使用新的统一API
            if self.set_video_server_unified(self.server_url):
                logger.info(f"✅ 统一API设置视频服务器成功: {self.server_url}")
                return True

            # 方法2: 兼容旧的/cmd接口
            command = f"video_server:{self.server_url}"
            response = requests.post(
                self.esp32_url,
                data=command,
                headers={'Content-Type': 'text/plain'},
                timeout=5
            )

            if response.status_code == 200:
                logger.info(f"✅ 兼容API设置视频服务器成功: {self.server_url}")
                return True
            else:
                logger.warning(f"⚠️ 两种API都失败: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ ESP32通知异常: {e}")
            return False

    def stop_video_server(self):
        """停止视频服务器"""
        if self.video_server:
            try:
                self.video_server.shutdown()
                logger.info("🛑 视频服务器已停止")
            except Exception as e:
                logger.error(f"❌ 停止视频服务器失败: {e}")

    def restart_video_system(self):
        """重启视频系统"""
        logger.info("🔄 重启视频播放系统...")
        self.stop_video_server()
        time.sleep(2)
        return self.auto_start_system()

def create_sisi_display_enhancer(adapter_instance=None):
    """创建SISI显示增强器实例"""
    websocket_client = None
    
    if adapter_instance and hasattr(adapter_instance, 'clients'):
        # 获取活跃的WebSocket客户端
        active_clients = list(adapter_instance.clients.values())
        if active_clients:
            websocket_client = active_clients[0]  # 使用第一个活跃客户端
    
    return SisiDisplayEnhancement(websocket_client)

# 🚀 SmartSisi监听式自动视频播放系统
if __name__ == "__main__":
    print("🔍 启动SmartSisi监听式视频播放系统...")
    print("=" * 50)
    print("📋 系统将自动监听SmartSisi进程启动")
    print("🎬 检测到SmartSisi启动时会自动开始视频播放")
    print("=" * 50)

    # 创建增强器，启动SmartSisi监听
    enhancer = SisiDisplayEnhancement(esp32_ip="172.20.10.2", auto_start=True)

    print("\n🎮 交互式控制模式")
    print("=" * 40)
    print("命令:")
    print("  1 - 重启视频系统")
    print("  2 - 发送测试文字")
    print("  3 - 停止视频服务器")
    print("  4 - 查看系统状态")
    print("  5 - 自定义文字推送")
    print("  q - 退出")

    try:
        while True:
            choice = input("\n请选择操作 (1/2/3/4/5/q): ").strip()

            if choice == '1':
                print("🔄 重启视频系统...")
                if enhancer.restart_video_system():
                    print("✅ 视频系统重启成功")
                else:
                    print("❌ 视频系统重启失败")

            elif choice == '2':
                print("📤 发送测试文字...")
                test_texts = [
                    "SmartSisi数字人启动",
                    "视频播放系统运行中",
                    "连接状态正常",
                    "准备开始对话",
                    "你好，我是SmartSisi"
                ]

                for i, text in enumerate(test_texts):
                    print(f"📤 推送第{i+1}条: {text}")
                    success = enhancer.sisi_speak(text)
                    if success:
                        print("✅ 推送成功")
                    else:
                        print("❌ 推送失败")
                    time.sleep(2)

            elif choice == '3':
                print("🛑 停止视频服务器...")
                enhancer.stop_video_server()
                print("✅ 视频服务器已停止")

            elif choice == '4':
                print("📊 系统状态:")
                print(f"   ESP32 IP: {enhancer.esp32_ip}")
                print(f"   视频服务器: {enhancer.server_url}")
                print(f"   服务器端口: {enhancer.server_port}")
                print(f"   对话次数: {enhancer.system_stats['conversations']}")

                # 测试连接状态
                if enhancer.test_esp32_connection():
                    print("   ESP32连接: ✅ 正常")
                else:
                    print("   ESP32连接: ❌ 失败")

            elif choice == '5':
                text = input("请输入要发送的文字: ").strip()
                if text:
                    if enhancer.send_to_esp32(text):
                        print("✅ 文字发送成功")
                    else:
                        print("❌ 文字发送失败")
                else:
                    print("⚠️ 文字不能为空")

            elif choice.lower() == 'q':
                print("🛑 正在关闭系统...")
                enhancer.stop_video_server()
                print("👋 系统已关闭")
                break

            else:
                print("❌ 无效选择")

    except KeyboardInterrupt:
        print("\n🛑 用户中断，正在关闭系统...")
        enhancer.stop_video_server()
        print("👋 系统已关闭")