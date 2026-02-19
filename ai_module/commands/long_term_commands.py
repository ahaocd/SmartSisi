# 长期命令模块
"""
长期命令模块，定义需要持续执行的摄像头命令。
"""

import re
import time
import random

# 长期命令触发词列表 - 统一定义版
LONG_TERM_COMMANDS = {
    # 长期观察命令
    "监控": [
        r"睁开眼睛[，。]?",
        r"睁开眼[，。]?",     # 增加对"睁开眼"的支持
        r"睁眼[，。]?",       # 增加对"睁眼"的支持
        r"开眼[，。]?",       # 增加对"开眼"的支持
        r"护法[，。]?",
        r"长期观察[，。]?",
        r"天眼[，。]?",       # 符合修真风格的触发词
        r"监控[，。]?",       # 直接支持"监控"关键词
        r"开天眼[，。]?"      # 更多变体
    ]
}

# 用于简单匹配的关键词列表（不使用正则表达式）
YOLO_COMMAND_KEYWORDS = [
    "睁开眼睛", "睁开眼", "睁眼", "打开眼睛", "打开眼", "开眼", 
    "护法", "天眼", "监控", "长期观察", "开天眼", "监控模式"
]

# 用于模糊匹配的关键词（当输入很短时使用）
YOLO_SHORT_KEYWORDS = ["眼", "监"]

# 命令有效期（秒）
COMMAND_DURATION = {
    "监控": 600  # 监控命令持续600秒（10分钟）
}

def check_command_trigger(text):
    """
    检查文本是否触发长期命令
    
    Args:
        text (str): 用户输入文本
        
    Returns:
        str or None: 触发的命令类型，未触发返回None
    """
    if not text:
        return None
    
    # 规范化文本（保留标点，转小写）
    normalized_text = text.lower()
    
    # 检查每个命令类型的正则表达式模式
    for command_type, patterns in LONG_TERM_COMMANDS.items():
        for pattern in patterns:
            if re.search(pattern, normalized_text):
                return command_type
    
    # 特殊处理：检查简单关键词匹配
    for keyword in YOLO_COMMAND_KEYWORDS:
        if keyword in text:
            return "监控"
    
    # 特殊处理：短文本模糊匹配
    if len(text) <= 5:
        for short_keyword in YOLO_SHORT_KEYWORDS:
            if short_keyword in text:
                return "监控"
    
    return None

def get_command_duration(command_type):
    """
    获取命令的持续时间
    
    Args:
        command_type (str): 命令类型
        
    Returns:
        int: 命令持续时间（秒）
    """
    return COMMAND_DURATION.get(command_type, 60)
