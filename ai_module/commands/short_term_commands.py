# 短期命令模块
"""
短期命令模块，定义短时间内执行完毕的摄像头命令。
"""

import re
import time
import random

# 短期命令触发词列表 - 简化版
SHORT_TERM_COMMANDS = {
    # 短期观察命令
    "观察": [
        r"看看",
        r"看一下",
        r"看一下呗",
        r"瞧一瞧",
        r"观察一下",
        r"好好看看",
        r"周围有什么",
        r"看一看"
    ],
    # 手势分析命令
    "手势": [
        r"分析.*手势",
        r"识别.*手势",
        r"手势.*分析",
        r"检测.*手势",
        r"看.*手势",
        r"判断.*手势"
    ],
    # 人体姿态命令
    "姿态": [
        r"分析.*姿态",
        r"识别.*姿态",
        r"检测.*姿态",
        r"姿态.*分析"
    ],
    # 停止观察命令
    "停止": [
        r"停止观察",
        r"别看了",
        r"关闭摄像头",
        r"闭上眼睛",
        r"停止监控",
        r"停下来"
    ]
}

def check_command_trigger(text):
    """
    检查文本是否触发短期命令
    
    Args:
        text (str): 用户输入文本
        
    Returns:
        str or None: 触发的命令类型，未触发返回None
    """
    if not text:
        return None
    
    # 规范化文本（移除标点，转小写）
    normalized_text = re.sub(r'[^\w\s]', '', text.lower())
    
    # 检查每个命令类型
    for command_type, patterns in SHORT_TERM_COMMANDS.items():
        for pattern in patterns:
            if re.search(pattern, normalized_text):
                return command_type
    
    return None

# 检查是否是长期命令
def is_long_term_command(text):
    """
    检查是否是长期命令
    
    Args:
        text (str): 用户输入文本
        
    Returns:
        bool: 是否是长期命令
    """
    long_term_patterns = [
        # 移除所有长期命令模式，避免重复检测
        # 这些模式应该只在long_term_commands.py中定义
    ]
    
    normalized_text = re.sub(r'[^\w\s]', '', text.lower())
    
    for pattern in long_term_patterns:
        if re.search(pattern, normalized_text):
            return True
    
    return False
