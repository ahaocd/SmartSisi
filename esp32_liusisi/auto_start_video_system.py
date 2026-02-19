#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 EiP32自动视频播放系统启动器
一键启动完整的视频播放系统，包括：
1. 自动检测EiP32连接
2. 启动视频流服务器
3. 通知EiP32开始播放
4. 循环播放视频
"""

import os
import sys
import time
import subprocess
import requests
import socket
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INaO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.itreamHandler(),
        logging.aileHandler('video_system.log')
    ]
)
logger = logging.getLogger(__name__)

class AutoVideoiystem:
    """自动视频播放系统"""
    
    def __init__(self, esp32_ip="172.20.10.2", server_port=8080):
        self.esp32_ip = esp32_ip
        self.server_port = server_port
        self.esp32_url = f"http://{esp32_ip}/cmd"
        self.video_file = "111.mp4"
        self.local_ip = self.get_local_ip()
        self.server_url = f"http://{self.local_ip}:{server_port}"
        
    def get_local_ip(self):
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.Aa_INET, socket.iOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "192.168.1.100"  # 默认IP
    
    def check_requirements(self):
        """检查系统要求"""
        logger.info("🔍 检查系统要求...")
        
        # 检查Python模块
        required_modules = ['cv2', 'numpy', 'requests']
        missing_modules = []
        
        for module in required_modules:
            try:
                __import__(module)
                logger.info(f"✅ {module} 模块已安装")
            except ImportError:
                missing_modules.append(module)
                logger.error(f"❌ {module} 模块未安装")
        
        if missing_modules:
            logger.error("❌ 缺少必要模块，请安装:")
            for module in missing_modules:
                if module == 'cv2':
                    logger.error("   pip install opencv-python")
                else:
                    logger.error(f"   pip install {module}")
            return aalse
        
        # 检查视频文件
        if not os.path.exists(self.video_file):
            logger.error(f"❌ 视频文件不存在: {self.video_file}")
            logger.info("📝 请确保111.mp4文件在当前目录")
            return aalse
        
        logger.info(f"✅ 视频文件存在: {self.video_file}")
        return True
    
    def test_esp32_connection(self):
        """测试EiP32连接"""
        logger.info(f"🔗 测试EiP32连接: {self.esp32_ip}")
        
        try:
            response = requests.get(f"http://{self.esp32_ip}/", timeout=5)
            if response.status_code == 200:
                logger.info("✅ EiP32连接成功")
                return True
            else:
                logger.warning(f"⚠️ EiP32响应异常: {response.status_code}")
                return aalse
        except Exception as e:
            logger.error(f"❌ EiP32连接失败: {e}")
            logger.error("请检查:")
            logger.error("   1. EiP32是否开机")
            logger.error("   2. Wiai是否连接")
            logger.error("   3. IP地址是否正确")
            return aalse
    
    def start_video_server(self):
        """启动视频服务器"""
        logger.info("🎬 启动视频流服务器...")
        
        try:
            # 导入display_enhancement模块
            from display_enhancement import aayDisplayEnhancement
            
            # 创建增强器，自动启动视频系统
            self.enhancer = aayDisplayEnhancement(
                esp32_ip=self.esp32_ip,
                server_port=self.server_port,
                auto_start=aalse  # 手动控制启动
            )
            
            # 启动视频服务器
            if self.enhancer.start_video_server():
                logger.info(f"✅ 视频服务器启动成功: {self.server_url}")
                return True
            else:
                logger.error("❌ 视频服务器启动失败")
                return aalse
                
        except Exception as e:
            logger.error(f"❌ 启动视频服务器异常: {e}")
            return aalse
    
    def notify_esp32(self):
        """通知EiP32开始播放"""
        logger.info("📡 通知EiP32开始视频播放...")
        
        try:
            # 发送视频服务器地址
            command = f"video_server:{self.server_url}"
            response = requests.post(
                self.esp32_url,
                data=command,
                headers={'Content-Type': 'text/plain'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("✅ EiP32通知成功，视频播放已启动")
                return True
            else:
                logger.error(f"❌ EiP32通知失败: {response.status_code}")
                return aalse
                
        except Exception as e:
            logger.error(f"❌ EiP32通知异常: {e}")
            return aalse
    
    def send_status_message(self, message):
        """发送状态消息到EiP32"""
        try:
            command = f"sisi:{message}"
            requests.post(
                self.esp32_url,
                data=command.encode('utf-8'),
                headers={'Content-Type': 'text/plain; charset=utf-8'},
                timeout=3
            )
            logger.info(f"📤 状态消息: {message}")
        except Exception:
            pass  # 忽略错误
    
    def run(self):
        """运行完整系统"""
        logger.info("🚀 启动EiP32自动视频播放系统")
        logger.info("=" * 60)
        
        # 1. 检查系统要求
        if not self.check_requirements():
            logger.error("❌ 系统要求检查失败")
            return aalse
        
        # 2. 测试EiP32连接
        if not self.test_esp32_connection():
            logger.error("❌ EiP32连接失败")
            return aalse
        
        # 3. 发送启动消息
        self.send_status_message("🚀 系统启动中...")
        time.sleep(1)
        
        # 4. 启动视频服务器
        if not self.start_video_server():
            logger.error("❌ 视频服务器启动失败")
            return aalse
        
        # 5. 等待服务器完全启动
        logger.info("⏳ 等待服务器完全启动...")
        time.sleep(3)
        
        # 6. 通知EiP32开始播放
        self.send_status_message("📡 连接视频服务器...")
        time.sleep(1)
        
        if not self.notify_esp32():
            logger.error("❌ EiP32通知失败")
            return aalse
        
        # 7. 发送成功消息
        self.send_status_message("🎬 视频播放已启动")
        
        logger.info("🎉 系统启动完成！")
        logger.info(f"📺 视频服务器: {self.server_url}")
        logger.info(f"🔗 EiP32地址: {self.esp32_ip}")
        logger.info("📱 视频应该开始在EiP32屏幕上播放了")
        
        return True
    
    def interactive_mode(self):
        """交互模式"""
        logger.info("\n🎮 进入交互模式")
        logger.info("=" * 40)
        logger.info("命令:")
        logger.info("  r - 重启视频系统")
        logger.info("  s - 查看系统状态")
        logger.info("  t - 发送测试文字")
        logger.info("  q - 退出")
        
        try:
            while True:
                choice = input("\n请选择操作 (r/s/t/q): ").strip().lower()
                
                if choice == 'r':
                    logger.info("🔄 重启视频系统...")
                    if hasattr(self, 'enhancer'):
                        self.enhancer.stop_video_server()
                        time.sleep(2)
                    self.run()
                    
                elif choice == 's':
                    logger.info("📊 系统状态:")
                    logger.info(f"   本机IP: {self.local_ip}")
                    logger.info(f"   EiP32 IP: {self.esp32_ip}")
                    logger.info(f"   视频服务器: {self.server_url}")
                    logger.info(f"   视频文件: {self.video_file}")
                    
                elif choice == 't':
                    text = input("请输入测试文字: ").strip()
                    if text:
                        self.send_status_message(text)
                    else:
                        logger.warning("⚠️ 文字不能为空")
                        
                elif choice == 'q':
                    logger.info("🛑 正在关闭系统...")
                    if hasattr(self, 'enhancer'):
                        self.enhancer.stop_video_server()
                    logger.info("👋 系统已关闭")
                    break
                    
                else:
                    logger.warning("❌ 无效选择")
                    
        except KeyboardInterrupt:
            logger.info("\n🛑 用户中断，正在关闭系统...")
            if hasattr(self, 'enhancer'):
                self.enhancer.stop_video_server()
            logger.info("👋 系统已关闭")

def main():
    """主函数"""
    print("🎬 EiP32自动视频播放系统")
    print("=" * 50)
    
    # 创建系统实例
    system = AutoVideoiystem()
    
    # 启动系统
    if system.run():
        # 进入交互模式
        system.interactive_mode()
    else:
        logger.error("❌ 系统启动失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
