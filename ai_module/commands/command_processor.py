# 命令处理器模块
"""
命令处理器模块，负责解析和处理用户命令。
"""

import time
import threading
import logging
from utils import util
from ai_module.commands.short_term_commands import check_command_trigger as check_short_term
from ai_module.commands.long_term_commands import check_command_trigger as check_long_term
from ai_module.commands.long_term_commands import get_command_duration
from ai_module.config.opening_phrases import get_random_opening
from ai_module.config.closing_phrases import get_random_closing

class CommandProcessor:
    """命令处理器，负责解析和执行用户命令"""
    
    # 单例实例
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """
        获取CommandProcessor的单例实例
        
        Returns:
            CommandProcessor: 命令处理器实例
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = CommandProcessor()
            return cls._instance
    
    def __init__(self):
        """初始化命令处理器"""
        self.logger = logging.getLogger(__name__)
        
        # 命令状态
        self.active_commands = {}  # 当前活跃的命令 {command_id: {type, start_time, end_time}}
        self.command_results = {}  # 命令执行结果 {command_id: result}
        self.last_command_time = {}  # 上次执行时间 {command_type: timestamp}
        
        # 命令冷却时间（秒）
        self.cooldown = {
            "观察": 5,
            "手势": 3,
            "人体": 3,
            "监控": 30,
            "人流": 30,
            "追踪": 30
        }
        
        # 命令ID生成器
        self.command_id_counter = 0
        self.id_lock = threading.Lock()
        
        # 命令处理锁
        self.processing_lock = threading.Lock()
    
    def check_command(self, text):
        """
        检查文本是否触发命令
        
        Args:
            text (str): 用户输入文本
            
        Returns:
            tuple: (命令类型, 是否为长期命令)
        """
        # 先检查长期命令 - 统一使用long_term_commands模块的函数
        long_term_cmd = check_long_term(text)
        if long_term_cmd:
            util.log(1, f"检测到长期命令: {long_term_cmd} -> 文本: {text}")
            return long_term_cmd, True
        
        # 再检查短期命令
        short_term_cmd = check_short_term(text)  # 使用short_term_commands模块的函数
        if short_term_cmd:
            util.log(1, f"检测到短期命令: {short_term_cmd} -> 文本: {text}")
            return short_term_cmd, False
            
        return None, False
    
    def _generate_command_id(self):
        """
        生成唯一的命令ID
        
        Returns:
            str: 命令ID
        """
        with self.id_lock:
            self.command_id_counter += 1
            return f"cmd_{int(time.time())}_{self.command_id_counter}"
    
    def process_command(self, text_or_type):
        """
        处理命令文本或命令类型，返回开场白和结果
        
        Args:
            text_or_type (str): 命令文本或命令类型
            
        Returns:
            dict: 包含开场白和命令ID的结果
        """
        # 检查是否是停止命令
        stop_commands = ["别看了", "停止", "停止观察", "闭上眼睛", "停", "关闭摄像头"]
        if any(cmd in text_or_type for cmd in stop_commands):
            util.log(1, f"检测到停止命令: {text_or_type}")
            command_id = self._generate_command_id()
            # 使用结束语而不是开场白
            closing = get_random_closing()
            return {
                "command_id": command_id,
                "command_type": "停止",
                "opening": closing,  # 对于停止命令，使用结束语作为响应
                "is_long_term": False
            }
            
        # 首先判断是否是文本输入，需要检查命令
        if isinstance(text_or_type, str) and len(text_or_type) > 1:
            command_type, is_long_term = self.check_command(text_or_type)
            
            # 特殊处理"一直观察"类命令，强制设为长期命令
            if "一直" in text_or_type or "持续" in text_or_type:
                is_long_term = True
                if not command_type:
                    command_type = "监控"
        else:
            # 直接传入了命令类型
            command_type = text_or_type
            is_long_term = False
        
        if not command_type:
            return None
            
        with self.processing_lock:
            current_time = time.time()
            
            # 检查命令冷却时间
            if command_type in self.last_command_time:
                elapsed = current_time - self.last_command_time[command_type]
                if elapsed < self.cooldown.get(command_type, 3):
                    util.log(1, f"命令 '{command_type}' 正在冷却中 ({elapsed:.1f}/{self.cooldown.get(command_type, 3)}秒)")
                    return None
            
            # 更新上次执行时间
            self.last_command_time[command_type] = current_time
            
            # 生成命令ID
            command_id = self._generate_command_id()
            
            # 计算命令结束时间
            if is_long_term:
                end_time = current_time + get_command_duration(command_type)
            else:
                end_time = current_time + 5  # 短期命令默认5秒
            
            # 记录命令
            self.active_commands[command_id] = {
                "type": command_type,
                "start_time": current_time,
                "end_time": end_time,
                "is_long_term": is_long_term
            }
            
            # 获取随机开场白
            opening = get_random_opening()
            
            util.log(1, f"处理命令: {command_type}, ID: {command_id}, {'长期' if is_long_term else '短期'}")
            
            return {
                "command_id": command_id,
                "command_type": command_type,
                "opening": opening,
                "is_long_term": is_long_term
            }
    
    def process_direct_command(self, command_text):
        """
        直接处理命令文本，返回命令信息
        
        Args:
            command_text (str): 命令文本
            
        Returns:
            dict: 命令信息，包含command_id, type, text, timestamp
        """
        # 先检查长期命令
        command_type = check_long_term(command_text)
        if not command_type:
            # 再检查短期命令
            command_type = check_short_term(command_text)
            
        if not command_type:
            return None
        
        return {
            "command_id": f"test_{int(time.time())}",
            "type": command_type,
            "text": command_text,
            "timestamp": time.time()
        }
    
    def update_command_result(self, command_id, result):
        """
        更新命令执行结果
        
        Args:
            command_id (str): 命令ID
            result (dict): 执行结果
        """
        if command_id in self.active_commands:
            self.command_results[command_id] = result
            util.log(1, f"更新命令结果: {command_id}")
    
    def get_command_result(self, command_id):
        """
        获取命令执行结果
        
        Args:
            command_id (str): 命令ID
            
        Returns:
            dict: 执行结果
        """
        # 添加随机结束语
        if command_id in self.command_results:
            result = self.command_results.get(command_id, {}).copy()
            if 'closing' not in result:
                result['closing'] = get_random_closing()
            return result
        return None
    
    def complete_command(self, command_id):
        """
        完成命令，释放资源
        
        Args:
            command_id (str): 命令ID
        """
        if command_id in self.active_commands:
            command_info = self.active_commands.pop(command_id)
            util.log(1, f"完成命令: {command_id}, 类型: {command_info['type']}")
            
            # 如果没有该类型的活跃命令了，可以提前重置冷却时间
            active_types = {cmd["type"] for cmd in self.active_commands.values()}
            if command_info['type'] not in active_types:
                self.last_command_time.pop(command_info['type'], None)
    
    def is_command_active(self, command_id):
        """
        检查命令是否处于活跃状态
        
        Args:
            command_id (str): 命令ID
            
        Returns:
            bool: 是否活跃
        """
        if command_id not in self.active_commands:
            return False
            
        command_info = self.active_commands[command_id]
        current_time = time.time()
        
        # 检查是否超时
        if current_time > command_info['end_time']:
            self.complete_command(command_id)
            return False
            
        return True
    
    def cleanup_expired_commands(self):
        """
        清理过期的命令
        """
        current_time = time.time()
        expired_commands = []
        
        for command_id, command_info in self.active_commands.items():
            if current_time > command_info['end_time']:
                expired_commands.append(command_id)
        
        for command_id in expired_commands:
            self.complete_command(command_id)
    
    def simulate_command(self, command_text):
        """
        模拟命令执行（用于测试）
        
        Args:
            command_text (str): 命令文本
        
        Returns:
            dict: 命令信息，包含command_id, type, text, timestamp
        """
        command_type = check_long_term(command_text)
        if not command_type:
            return None
        
        return {
            "command_id": f"test_{int(time.time())}",
            "type": command_type,
            "text": command_text,
            "timestamp": time.time()
        }
    
    def get_opening(self, command_type):
        """
        获取特定命令类型的开场白
        
        Args:
            command_type (str): 命令类型，如"监控"、"聊天"等
            
        Returns:
            str: 适合该命令类型的开场白
        """
        from ai_module.config.opening_phrases import get_random_opening
        
        # 针对不同命令类型可以返回不同的开场白
        # 目前简单实现，后续可以针对不同命令类型定制开场白
        opening = get_random_opening()
        
        util.log(1, f"[命令] 获取命令'{command_type}'的开场白: {opening}")
        
        return opening
