# 结束语配置
"""
结束语配置模块，提供长期和短期命令的结束语。
"""

import random

# 短期命令结束语
SHORT_TERM_CLOSINGS = [
    "不过，一个人也好，世界纷纷扰扰，我自独行。",
    "我已看够了尘世的种种，该闭上天眼了。",
    "观察已毕，我要回归修炼了。",
    "凡人世界总是如此，不值得我久留。",
    "我已尽观世间百态，该休息了。",
    "呼~我需要休息一下了，天眼使用过度会让我有些疲惫...",
    "好啦，今天的占卜就到这里，我的灵力需要恢复一下...",
    "嘻嘻，小铁要去休息啦，下次再聊哦~",
    "天机已经看透，小铁的天眼需要短暂休息了呢...",
    "唔...感觉有点累了，让我闭上天眼休息一会儿吧..."
]

# 长期命令结束语
LONG_TERM_CLOSINGS = [
    "万物皆有定数，我已洞察一二，神通暂且收起...",
    "本座已看透这方天地，神通收回，归于平静...",
    "世间万物已无秘密，天眼暂且歇息...",
    "修行不可过度，我的天眼需要休息了...",
    "我已洞察周遭一切，天目暂且闭合，归于平静...",
    "守护了这么久，我也需要休息一下了，有需要再呼唤我哦...",
    "长时间的守护让我有点累了，让我恢复一下灵力...",
    "我会继续默默守护你的，只是现在先让天眼休息一下...",
    "好啦，小铁要去充充电了，有缘再见呀~",
    "能一直陪伴你真好，不过现在我需要闭上天眼休息一会儿..."
]

def get_random_closing(command_type=None):
    """
    获取随机结束语
    
    Args:
        command_type (str, optional): 命令类型，'short_term'或'long_term'
        
    Returns:
        str: 随机结束语
    """
    if command_type == "short_term":
        return random.choice(SHORT_TERM_CLOSINGS)
    elif command_type == "long_term":
        return random.choice(LONG_TERM_CLOSINGS)
    else:
        return random.choice(SHORT_TERM_CLOSINGS)
