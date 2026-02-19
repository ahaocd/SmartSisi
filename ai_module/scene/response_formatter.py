# 响应格式化模块
"""
响应格式化模块，负责将分析结果和对话内容格式化为统一的响应格式。
"""

import time
import json
import threading
from utils import util

class ResponseFormatter:
    """响应格式化器，将分析结果和对话转换为标准格式"""
    
    # 单例实例
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """
        获取ResponseFormatter的单例实例
        
        Returns:
            ResponseFormatter: 响应格式化器实例
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = ResponseFormatter()
            return cls._instance
    
    def __init__(self):
        """初始化响应格式化器"""
        pass
    
    def format_response(self, scene_data, dialogue, command_info=None):
        """
        将场景数据和对话格式化为统一响应
        
        Args:
            scene_data (dict): 场景分析数据
            dialogue (str): 生成的对话内容
            command_info (dict, optional): 命令相关信息
            
        Returns:
            dict: 格式化的响应
        """
        # 基本响应结构
        response = {
            "success": True,
            "timestamp": time.time(),
            "data": {
                "dialogue": dialogue,
                "scene": scene_data
            },
            "error": None
        }
        
        # 添加命令信息（如果有）
        if command_info:
            response["data"]["command"] = command_info
        
        return response
    
    def format_error(self, error_message, error_code=500):
        """
        格式化错误响应
        
        Args:
            error_message (str): 错误信息
            error_code (int, optional): 错误代码，默认500
            
        Returns:
            dict: 格式化的错误响应
        """
        return {
            "success": False,
            "timestamp": time.time(),
            "data": None,
            "error": {
                "code": error_code,
                "message": error_message
            }
        }
    
    def to_json(self, response_data):
        """
        将响应数据转换为JSON字符串
        
        Args:
            response_data (dict): 响应数据
            
        Returns:
            str: JSON格式的响应
        """
        try:
            return json.dumps(response_data, ensure_ascii=False)
        except Exception as e:
            util.log(1, f"响应数据JSON序列化失败: {str(e)}")
            return json.dumps(self.format_error("响应数据序列化失败"), ensure_ascii=False)
