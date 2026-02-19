# 摄像头管理核心模块
"""
摄像头管理核心模块，负责摄像头的初始化、获取图像和资源释放。
"""

import cv2
import time
import threading
import logging
import numpy as np
from utils import util
from ai_module.camera.device_detector import DeviceDetector

class CameraManager:
    """摄像头管理类，负责摄像头的初始化、获取图像和资源释放"""
    
    # 单例实例
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """
        获取CameraManager的单例实例
        
        Returns:
            CameraManager: 摄像头管理器实例
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = CameraManager()
            return cls._instance
    
    def __init__(self):
        """初始化摄像头管理器"""
        self.logger = logging.getLogger(__name__)
        self.device_detector = DeviceDetector()
        
        # 摄像头状态
        self.initialized = False
        self.active = False
        self.cap = None
        self.device_id = None
        
        # 摄像头参数
        self.frame_width = 640
        self.frame_height = 480
        self.fps = 30
        
        # 并发控制
        self.lock = threading.Lock()
        
        # 后端尝试顺序
        self.backends = [
            cv2.CAP_DSHOW,       # DirectShow (Windows优先)
            cv2.CAP_MSMF,        # Media Foundation (Windows)
            cv2.CAP_V4L2,        # Video for Linux
            cv2.CAP_AVFOUNDATION # AVFoundation (macOS)
        ]
    
    def detect_devices(self):
        """
        检测可用的摄像头设备
        
        Returns:
            list: 可用设备ID列表
        """
        return self.device_detector.detect_devices()
    
    def initialize(self):
        """
        初始化摄像头
        
        Returns:
            bool: 是否初始化成功
        """
        with self.lock:
            # 如果已经初始化过并且摄像头仍然活跃，则不需要重新初始化
            if self.initialized and self.active and self.cap is not None:
                # 尝试读取一帧确认摄像头仍然正常工作
                try:
                    ret, frame = self.cap.read()
                    if ret and frame is not None and frame.size > 0:
                        util.log(1, "摄像头已经初始化且工作正常，无需重新初始化")
                        return True
                    else:
                        util.log(1, "摄像头已初始化但读取测试失败，需要重新初始化")
                        self._release_resources()  # 释放资源以便重新初始化
                except Exception as e:
                    util.log(1, f"测试摄像头状态时出错: {str(e)}，需要重新初始化")
                    self._release_resources()  # 释放资源以便重新初始化
            
            # 确保释放可能存在的旧资源
            if self.cap is not None:
                util.log(1, "重置摄像头资源以便重新初始化")
                self._release_resources()
            
            # 设置初始状态
            self.initialized = False
            self.active = False
            
            # 检测摄像头设备
            util.log(1, "开始检测摄像头设备")
            device_ok = self._detect_camera_device()
            if not device_ok:
                util.log(1, "未检测到可用的摄像头设备")
                return False
            
            # 尝试初始化摄像头
            util.log(1, "开始尝试初始化摄像头")
            backend_ok = self._try_camera_backends()
            if not backend_ok:
                util.log(1, "所有摄像头后端都初始化失败")
                return False
            
            # 标记为初始化成功
            self.initialized = True
            self.active = True
            util.log(1, "摄像头初始化成功")
            return True
    
    def _detect_camera_device(self):
        """
        检测摄像头设备
        
        Returns:
            bool: 是否检测到设备
        """
        # 读取系统配置
        from utils import config_util as cfg
        cfg.load_config()
        camera_id = cfg.get_value('video_camera_id') or 0
        
        try:
            camera_id = int(camera_id)
            self.device_id = camera_id
        except (ValueError, TypeError):
            util.log(1, f"无效的摄像头ID: {camera_id}，使用默认值0")
            self.device_id = 0
        
        # 检测可用设备
        devices = self.detect_devices()
        if not devices:
            util.log(1, "未检测到可用摄像头设备")
            return False
        
        # 验证设备ID是否超出范围
        if self.device_id >= len(devices):
            util.log(1, f"指定的摄像头ID {self.device_id} 超出了可用范围，将使用ID 0")
            self.device_id = 0
        
        return True
    
    def _try_camera_backends(self):
        """
        尝试使用不同的后端初始化摄像头
        
        Returns:
            bool: 是否有一个后端成功
        """
        for backend in self.backends:
            try:
                # 使用特定后端打开摄像头
                self.cap = cv2.VideoCapture(self.device_id, backend)
                
                # 设置参数
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                
                # 读取一帧测试是否成功
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    util.log(1, f"摄像头后端 {backend} 初始化成功")
                    return True
                else:
                    self.cap.release()
                    self.cap = None
            except Exception as e:
                util.log(1, f"尝试后端 {backend} 时出错: {str(e)}")
                if self.cap:
                    self.cap.release()
                    self.cap = None
        
        return False
    
    def get_frame(self):
        """
        获取一帧图像
        
        Returns:
            tuple: (成功标志, 图像数据)
        """
        with self.lock:
            if not self.initialized or not self.active or self.cap is None:
                # 尝试自动初始化
                util.log(1, "摄像头未初始化或未激活，尝试自动初始化")
                if self.initialize():
                    util.log(1, "摄像头自动初始化成功")
                else:
                    util.log(1, "摄像头自动初始化失败")
                    return False, None
            
            try:
                ret, frame = self.cap.read()
                if not ret or frame is None or frame.size == 0:
                    # 读取失败，尝试重新初始化
                    util.log(1, "读取图像失败，尝试重新初始化摄像头")
                    self._release_resources()
                    self.initialized = False
                    
                    # 立即尝试重新初始化
                    if self.initialize():
                        util.log(1, "摄像头重新初始化成功，重试获取图像")
                        ret, frame = self.cap.read()
                        if ret and frame is not None and frame.size > 0:
                            return True, frame
                    
                    return False, None
                return True, frame
            except Exception as e:
                util.log(1, f"获取图像时出错: {str(e)}")
                # 发生异常也尝试重新初始化
                self._release_resources()
                self.initialized = False
                return False, None
    
    def deactivate(self):
        """
        停用摄像头（不释放资源，便于重新激活）
        """
        with self.lock:
            self.active = False
    
    def activate(self):
        """
        激活摄像头（如果已经初始化但被停用）
        
        Returns:
            bool: 是否成功激活
        """
        with self.lock:
            if not self.initialized:
                return False
            
            self.active = True
            return True
    
    def start(self):
        """
        启动摄像头（初始化后的显式启动，保持与旧版接口兼容）
        
        Returns:
            bool: 是否成功启动
        """
        with self.lock:
            # 如果摄像头未初始化，则先初始化
            if not self.initialized and not self.initialize():
                util.log(1, "摄像头初始化失败，无法启动")
                return False
            
            # 激活摄像头
            self.active = True
            
            # 检查摄像头状态
            if self.cap is None or not self.cap.isOpened():
                util.log(1, "摄像头已初始化但未打开，重新打开")
                return self.initialize()
                
            return True
    
    def release(self):
        """
        释放摄像头资源
        
        Returns:
            bool: 释放是否成功
        """
        with self.lock:
            if self.cap is not None:
                try:
                    self.cap.release()
                    self.cap = None
                    self.active = False
                    return True
                except Exception as e:
                    self.logger.error(f"释放摄像头资源失败: {str(e)}")
                    return False
            return True
            
    def close(self):
        """
        关闭摄像头并释放资源（与release保持一致，提供接口兼容性）
        
        Returns:
            bool: 关闭是否成功
        """
        return self.release()
    
    def _release_resources(self):
        """释放摄像头资源"""
        try:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.active = False
            # 添加短暂延迟，让系统有时间释放摄像头资源
            time.sleep(0.5)
            return True
        except Exception as e:
            util.log(1, f"释放摄像头资源时出错: {str(e)}")
            self.cap = None
            self.active = False
            return False
    
    def is_active(self):
        """
        检查摄像头是否处于活动状态
        
        Returns:
            bool: 摄像头是否活动
        """
        with self.lock:
            return self.active and self.initialized and self.cap is not None and self.cap.isOpened()
    
    def is_initialized(self):
        """
        检查摄像头是否已初始化
        
        Returns:
            bool: 是否已初始化
        """
        return self.initialized
    
    def get_camera_id(self):
        """
        获取当前使用的摄像头ID
        
        Returns:
            int: 摄像头ID
        """
        return self.device_id
