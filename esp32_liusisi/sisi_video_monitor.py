#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 视频播放系统监听器
独立运行，监听SmartSisi进程启动，自动触发ESP32视频播放
"""

import os
import sys
import time
import threading
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('sisi_video_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

class SisiVideoMonitor:
    """SmartSisi视频播放监听器"""
    
    def __init__(self):
        self.is_running = False
        self.video_system = None
        self.sisi_was_running = False
        
    def check_dependencies(self):
        """检查依赖"""
        try:
            # 检查display_enhancement模块
            if not os.path.exists("display_enhancement.py"):
                logger.error("❌ display_enhancement.py 不存在")
                return False
            
            # 检查视频文件
            if not os.path.exists("111.mp4"):
                logger.error("❌ 111.mp4 视频文件不存在")
                return False
            
            # 检查Python模块
            required_modules = ['psutil', 'cv2', 'numpy', 'requests']
            missing = []
            
            for module in required_modules:
                try:
                    __import__(module)
                except ImportError:
                    missing.append(module)
            
            if missing:
                logger.error(f"❌ 缺少模块: {missing}")
                logger.info("请安装: pip install psutil opencv-python numpy requests")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 依赖检查异常: {e}")
            return False
    
    def is_sisi_running(self):
        """检查SmartSisi是否运行"""
        try:
            import psutil
            
            # 检查进程
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        cmdline = proc.info['cmdline']
                        if cmdline:
                            # 检查是否是SISI的main.py
                            cmdline_str = ' '.join(cmdline).lower()
                            if 'main.py' in cmdline_str and ('sisi' in cmdline_str or 'SmartSisi' in cmdline_str):
                                return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 检查SmartSisi进程异常: {e}")
            return False
    
    def start_video_system(self):
        """启动视频播放系统"""
        try:
            logger.info("🎬 启动ESP32视频播放系统...")
            
            from display_enhancement import SisiDisplayEnhancement
            
            # 创建视频系统实例（不自动启动监听，避免循环）
            self.video_system = SisiDisplayEnhancement(
                esp32_ip="172.20.10.2",
                server_port=8080,
                auto_start=False  # 手动控制启动
            )
            
            # 手动启动系统
            if self.video_system.auto_start_system():
                logger.info("✅ ESP32视频播放系统启动成功")
                return True
            else:
                logger.error("❌ ESP32视频播放系统启动失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动视频系统异常: {e}")
            return False
    
    def stop_video_system(self):
        """停止视频播放系统"""
        try:
            if self.video_system:
                logger.info("🛑 停止ESP32视频播放系统...")
                self.video_system.stop_video_server()
                self.video_system = None
                logger.info("✅ ESP32视频播放系统已停止")
        except Exception as e:
            logger.error(f"❌ 停止视频系统异常: {e}")
    
    def monitor_loop(self):
        """监听循环"""
        logger.info("🔍 开始监听SmartSisi进程...")
        
        while self.is_running:
            try:
                sisi_running = self.is_sisi_running()
                
                # SmartSisi启动了
                if sisi_running and not self.sisi_was_running:
                    logger.info("🎉 检测到SmartSisi进程启动！")
                    self.sisi_was_running = True
                    
                    # 延迟5秒确保SISI完全启动
                    time.sleep(5)
                    
                    # 启动视频系统
                    self.start_video_system()
                
                # SmartSisi停止了
                elif not sisi_running and self.sisi_was_running:
                    logger.info("⚠️ 检测到SmartSisi进程停止")
                    self.sisi_was_running = False
                    
                    # 停止视频系统
                    self.stop_video_system()
                
                time.sleep(3)  # 每3秒检查一次
                
            except KeyboardInterrupt:
                logger.info("🛑 用户中断监听")
                break
            except Exception as e:
                logger.error(f"❌ 监听循环异常: {e}")
                time.sleep(5)
    
    def start(self):
        """启动监听器"""
        logger.info("🚀 启动SmartSisi视频播放监听器")
        logger.info("=" * 50)
        
        # 检查依赖
        if not self.check_dependencies():
            logger.error("❌ 依赖检查失败，无法启动")
            return False
        
        logger.info("✅ 依赖检查通过")
        
        # 检查SmartSisi当前状态
        if self.is_sisi_running():
            logger.info("🎉 SISI已在运行，立即启动视频系统")
            self.sisi_was_running = True
            self.start_video_system()
        else:
            logger.info("⏳ SISI未运行，等待SISI启动...")
        
        # 启动监听
        self.is_running = True
        
        try:
            self.monitor_loop()
        except KeyboardInterrupt:
            logger.info("🛑 用户中断")
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """停止监听器"""
        logger.info("🛑 停止SISI视频播放监听器...")
        self.is_running = False
        self.stop_video_system()
        logger.info("👋 监听器已停止")

def main():
    """主函数"""
    print("🔍 SISI视频播放系统监听器")
    print("=" * 50)
    print("📋 功能:")
    print("   - 自动监听SmartSisi进程启动/停止")
    print("   - SISI启动时自动开始ESP32视频播放")
    print("   - SISI停止时自动停止视频播放")
    print("   - 完全独立运行，不修改SISI代码")
    print("=" * 50)
    print("💡 使用方法:")
    print("   1. 确保111.mp4文件在当前目录")
    print("   2. 运行此脚本: python sisi_video_monitor.py")
    print("   3. 正常启动SmartSisi，视频会自动播放")
    print("   4. 按Ctrl+C停止监听器")
    print("=" * 50)
    
    monitor = SisiVideoMonitor()
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        print("\n🛑 用户中断")
    except Exception as e:
        print(f"\n❌ 监听器异常: {e}")
    finally:
        monitor.stop()

if __name__ == "__main__":
    main()
