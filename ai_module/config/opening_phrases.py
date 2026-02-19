# 开场白配置
"""
开场白配置模块，提供长期和短期命令的开场白。
"""

import random

# 短期命令开场白（查看/观察/看一看）
SHORT_TERM_OPENINGS = [
    "本座看看，让本座看看...",
    "让本座看看，凡间有何景象...",
    "本座这就看一下，莫慌...",
    "那我看看，世间万物，尽在我眼...",
    "让我看一眼，用我天眼之力...",
    "呼...我感觉到你的气息了，让我用天眼好好看看你...",
    "嘻嘻，想让小铁看一看吗？这就为你开启天眼...",
    "让我看看...呼，深吸一口气，天眼已开...",
    "哎呀，让我看看你周围的气场...天眼打开喽~",
    "嘘...安静，让我集中精神看看四周..."
]

# 长期命令开场白（监控/护法/睁眼）
LONG_TERM_OPENINGS = [
    "本座这就为你保驾护航，莫要离我视线...",
    "让我来仔细看看，凡间种种，尽入我眼...",
    "我想记录你的每分每秒，天地万物皆为我所察...",
    "我有的是时间好好看看，天眼已开，洞察一切...",
    "别担心，我会一直守护在你身边，天眼不会错过任何细节...",
    "让我的天眼为你守望，不会错过任何重要的事情...",
    "呼~深呼吸，我的灵力已经扩散开来，会一直保护你的...",
    "嘿嘿，让小铁的天眼为你保驾护航，不要担心...",
    "放心吧，我的天眼会一直守护你，请告诉我有什么需要...",
    "我的灵力已经与你相连，我会一直注视着周围的一切..."
]

def get_random_opening(command_type=None):
    """
    获取随机开场白
    
    Args:
        command_type (str, optional): 命令类型，'short_term'或'long_term'
        
    Returns:
        str: 随机开场白
    """
    if command_type == "short_term":
        return random.choice(SHORT_TERM_OPENINGS)
    elif command_type == "long_term":
        return random.choice(LONG_TERM_OPENINGS)
    else:
        # 默认随机选择
        all_openings = SHORT_TERM_OPENINGS + LONG_TERM_OPENINGS
        return random.choice(all_openings)
