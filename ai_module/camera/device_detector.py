# 设备检测模块
"""
设备检测模块，负责检测和管理系统中可用的摄像头设备。
"""

import cv2
import os
import time
import logging
from utils import util

class DeviceDetector:
    """摄像头设备检测器，用于检测和选择可用的摄像头设备"""
    
    def __init__(self):
        """初始化设备检测器"""
        self.logger = logging.getLogger(__name__)
        self.available_devices = []
        self.last_detection_time = 0
        # 检测间隔时间（秒）
        self.detection_interval = 60
    
    def detect_devices(self, force=False):
        """
        检测系统中所有可用的摄像头设备
        
        Args:
            force (bool): 是否强制重新检测，忽略检测间隔
            
        Returns:
            list: 可用设备ID列表
        """
        # 检查是否需要重新检测
        current_time = time.time()
        if not force and current_time - self.last_detection_time < self.detection_interval:
            # 如果设备列表不为空且未超过检测间隔，直接返回缓存结果
            if self.available_devices:
                return self.available_devices
        
        # 更新最后检测时间
        self.last_detection_time = current_time
        self.available_devices = []
        
        # 检测设备
        util.log(1, "正在检测摄像头设备...")
        
        # 检查常见设备ID (0-10)
        for device_id in range(10):
            if self._check_device(device_id):
                self.available_devices.append(device_id)
                util.log(1, f"检测到可用摄像头设备: {device_id}")
                
        if not self.available_devices:
            util.log(1, "未检测到可用摄像头设备")
            
        return self.available_devices
    
    def _check_device(self, device_id):
        """
        检查指定ID的摄像头设备是否可用
        
        Args:
            device_id (int): 设备ID
            
        Returns:
            bool: 设备是否可用
        """
        try:
            # 尝试打开摄像头
            cap = cv2.VideoCapture(device_id)
            
            # 检查是否成功打开
            if not cap.isOpened():
                return False
            
            # 尝试读取一帧
            ret, _ = cap.read()
            
            # 释放资源
            cap.release()
            
            return ret
        except Exception as e:
            util.log(1, f"检查设备 {device_id} 时出错: {str(e)}")
            return False
