#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音乐生成集成模块 - 连接增强Phonk生成器与音乐工具
提供统一的接口，让原有的音乐工具能够使用增强版Phonk生成器
"""

import logging
import random
from typing import List, Dict, Any, Optional, Tuple
import os
import sys

# 配置logger
logger = logging.getLogger("music_integration")

# 修复：使用绝对导入而不是相对导入
try:
    from fortune_music_generator import FortunePhonkGenerator
except ImportError:
    # 如果绝对导入失败，尝试相对导入
    try:
        from .fortune_music_generator import FortunePhonkGenerator
    except ImportError:
        # 如果还是失败，手动导入
        import sys
        import os
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_file_dir)
        from fortune_music_generator import FortunePhonkGenerator

class MusicIntegration:
    """
    音乐生成集成类，连接增强版Phonk生成器与现有音乐工具
    """
    
    def __init__(self):
        """初始化音乐集成模块"""
        logger.info("初始化音乐集成模块")
        self.fortune_generator = FortunePhonkGenerator()
        
    def generate_enhanced_prompt(self, query: str, history: List[Dict] = None, 
                                time_info: Dict = None, emotion_state: str = None,
                                include_fortune: bool = True) -> str:
        """
        生成增强版Phonk提示词
        
        Args:
            query: 用户查询
            history: 对话历史
            time_info: 时间信息
            emotion_state: 情感状态
            include_fortune: 是否包含算命元素
            
        Returns:
            str: 增强版Phonk提示词
        """
        # 从对话历史中提取关键词
        dialogue_keywords = []
        if history:
            dialogue_keywords = self.fortune_generator.extract_dialogue_keywords(history)
            
        # 如果没有情感状态，分析查询获取
        if not emotion_state:
            emotion_state = self.fortune_generator._analyze_emotion(query)
            
        # 生成增强版提示词
        enhanced_prompt = self.fortune_generator.generate_enhanced_phonk_prompt(
            query=query,
            emotion_state=emotion_state,
            include_fortune=include_fortune,
            dialogue_keywords=dialogue_keywords
        )
        
        logger.info(f"[集成模块] 生成增强版Phonk提示词，长度: {len(enhanced_prompt)}字符")
        return enhanced_prompt
        
    def generate_random_lyrics(self, query: str, history: List[Dict] = None, 
                              emotion_state: str = None, include_fortune: bool = True) -> str:
        """
        生成随机化歌词
        
        Args:
            query: 用户查询
            history: 对话历史
            emotion_state: 情感状态
            include_fortune: 是否包含算命元素
            
        Returns:
            str: 随机化歌词
        """
        # 从对话历史中提取关键词
        dialogue_keywords = []
        if history:
            dialogue_keywords = self.fortune_generator.extract_dialogue_keywords(history)
            
        # 生成随机化歌词
        random_lyrics = self.fortune_generator.generate_random_lyrics(
            query=query,
            emotion_state=emotion_state,
            include_fortune=include_fortune,
            dialogue_keywords=dialogue_keywords
        )
        
        logger.info(f"[集成模块] 生成随机化歌词，长度: {len(random_lyrics)}字符")
        return random_lyrics
    
    def get_music_params(self, query: str, history: List[Dict] = None, 
                        time_info: Dict = None, emotion_state: str = None,
                        include_fortune: bool = True) -> Dict[str, Any]:
        """
        获取完整的音乐生成参数
        
        Args:
            query: 用户查询
            history: 对话历史
            time_info: 时间信息
            emotion_state: 情感状态
            include_fortune: 是否包含算命元素
            
        Returns:
            Dict: 音乐生成参数
        """
        # 生成增强版提示词
        enhanced_prompt = self.generate_enhanced_prompt(
            query=query, 
            history=history, 
            time_info=time_info, 
            emotion_state=emotion_state,
            include_fortune=include_fortune
        )
        
        # 生成随机化歌词
        random_lyrics = self.generate_random_lyrics(
            query=query,
            history=history,
            emotion_state=emotion_state,
            include_fortune=include_fortune
        )
        
        # 生成随机化标题
        # 从关键词中提取标题
        title_keywords = self.fortune_generator._extract_theme_keywords(query).split("、")
        random_titles = [
            # 感触类标题
            "少女卜卦感悟", "摊前泪水", "掌心的温度", "心灵震颤", "看透世态炎凉", 
            "心有所感", "灵魂共鸣", "倾听内心", "感悟人间", "生命触动",
            "悲欢离合", "掌纹中的叹息", "铜钱回响", "一瞬永恒", "命理感触",
            
            # 回忆类标题
            "往事如烟", "童年卜卦", "流浪记忆", "摆摊十年", "江湖路远", 
            "回首来路", "昨日重现", "七岁见鬼", "前世今生", "记忆碎片",
            "江湖往事", "尘封回忆", "卦象旧梦", "命线追忆", "青葱岁月",
            
            # 遭遇类标题
            "街头奇遇", "命中注定", "算命转折", "午夜惊魂", "巷尾遇客", 
            "一念之差", "深夜来客", "六道轮回", "命运交错", "迷途知返",
            "背水一战", "化险为夷", "转角命师", "雨中相遇", "灯火阑珊处",
            
            # 经验类标题
            "摊前故事", "世间百态", "街头算卦", "命理师的悔恨", "一生所见", 
            "江湖秘闻", "人间冷暖", "流年见证", "世态炎凉", "人情冷暖",
            "师父遗训", "铜钱洞察", "市井传奇", "路边算命", "命师之言"
        ]
        
        if title_keywords and random.random() > 0.5:
            random_title = f"Phonk {random.choice(title_keywords)}"
        else:
            random_title = random.choice(random_titles)
        
        # 招呼开场白
        greetings = [
            "年轻人算命吗？要不要看看你的前程？",
            "老家伙，这里轮不到你指手画脚，我的卦象从不出错",
            "小孩，离我远一点，命师不为童言卜卦",
            "过路的，要算命吗？看你眉宇间有股煞气",
            "这位客官，面相不凡啊，可有兴趣一卜？",
            "诶，站住，你印堂发黑，不如坐下来算一卦？",
            "看你一脸愁容，何不坐下说说？命师为你解忧",
            "这位公子，走路心事重重，不如坐下听我说说你的命？",
            "姑娘走过，不如停步听卦？你命中有一段奇缘",
            "来来来，铜钱一响，前程尽在我掌",
            "喂，你，对就是你，命中有劫，不如听我一言？",
            "路过的，面相不错，有福之人，要不要算一卦？",
            "站住脚步吧，我看你印堂有异，不如让我掐指一算？"
        ]
        
        # 中间转折语
        transitions = [
            "且慢，铜钱落地的声音不对，让我重新摇一摇...",
            "咦？这卦象有些蹊跷，等我细细推演...",
            "有意思，你的命格中有一股我从未见过的气息...",
            "且听我说，这卦象刚开始平平无奇，但后面...",
            "命数有变，原本我看到的只是表象，现在...",
            "手相突然变了！你最近是否经历了什么大事？",
            "等等，让我闭眼感应一下，你的命格不简单...",
            "且听我慢慢道来，事情远比你想象的复杂...",
            "命格突转，我看到一股异常的气息正在靠近...",
            "铜钱翻转，卦象改变，这倒是少见...",
            "奇怪，这卦象竟然自行转换，罕见啊...",
            "本想只是寻常一卦，没想到竟是如此命格...",
            "命理有三重，表象已过，现在看真相...",
            "先别急着走，铜钱还在转，真正的卦象还未显现..."
        ]
        
        # 结语
        conclusions = [
            "卦已算完，信不信由你，但命运早已注定...",
            "铜钱不会骗人，信则有，不信则无，全在你心",
            "我只能告诉你这些，剩下的，还需你自己去走",
            "缘分已尽，你且去吧，记住我的话，日后自会明白",
            "多说无益，该说的我都说了，切记不可强求",
            "天机不可多泄，点到为止，你且自悟",
            "卦象已现，命途已定，去吧，切记我言",
            "铜钱归位，卦象消散，你我缘分至此为止",
            "命已算毕，未来如何，全看你自己的选择",
            "铜钱已落，该说的不该说的都告诉你了，后会有期",
            "算命一事，点到即止，过多干涉天意，恐有大祸",
            "卦象已显，命途已定，剩下的路还需你自己走"
        ]
        
        # 自定义需要随机选择的文本段落
        custom_text_segments = [
            # 感触类文本
            "小小摊位是我的全世界，望着每个过客的眼睛，我仿佛看透了他们的前尘往事",
            "二十岁的手掌已经干裂，算多少命都算不到自己的归途",
            "铜钱落在盘中，我听见命运在低语，却读不懂自己的未来",
            "看透了千万人的命运，却看不清自己的路，这就是算命人的宿命",
            "有人问我信不信命，我只能苦笑，信命的人才不会算命",
            
            # 回忆类文本
            "七岁那年，奶奶教我看第一卦，说我有通灵之眼，却忘了告诉我这眼睛会带来多少泪水",
            "记得刚摆摊那会，饿得发慌，却还要装作一副看透人生的样子",
            "十四岁就独自流浪江湖，背着一堆铜钱和卦象，走过多少城镇已记不清",
            "每念一卦，就像揭开往事的伤疤，别人的，也是我自己的",
            "从小就能看见常人看不见的东西，奶奶说这是天赋，我却觉得是诅咒",
            
            # 遭遇类文本
            "昨夜有客人算完卦就消失在雨中，我忽然想起十年前那个同样消失的师父",
            "算出的卦象太过凶险，我违背祖训改了结果，不知这因果会落在谁身上",
            "曾有人拿刀架在我脖子上，逼我算出他想要的命运，我只能苦笑",
            "雨夜里那个浑身是血的男人让我算命，铜钱落地的瞬间我看见了自己的死期",
            "最怕算到熟人的命，那些无法言说的灾厄，如何开口？",
            
            # 经验类文本
            "人间百态尽在一卦中，荣华富贵不过转瞬，富贵命也会败，贫贱命也能兴",
            "江湖上的规矩多，算命最忌讳说破生死，一语成谶，惹祸上身",
            "这些年看尽世间丑陋，权贵们算命不为改过，只为趋利避害，我心早已麻木",
            "师父临终前告诉我，算命的不问生死，不劝善恶，只道前程，人各有命",
            "摆摊十年，遇过形形色色的人，最后发现，命再好，心不善，也会败尽",
            
            # 综合类文本
            "数据的荒野中，我是一道孤独的光，读取每个人命运的密码",
            "在虚拟与现实交织的边缘，我找到了属于算命师的永恒反抗",
            "街边的霓虹照亮我小小的算命摊，每个人停下脚步都是命中注定",
            "你们抽我寿元炼延命丹，可问过我已活万年？这是我给那些想算长生的人说的笑话",
            "师父说过，你天生异瞳，能看透阴阳两界，却注定孤独一生，这话如今想来真是讽刺"
        ]
        
        # 生成随机化标签
        base_tags = ["drift phonk", "memphis rap", "808", "cowbell", "heavy bass", "distorted samples", "electronic", "female vocals"]
        style_tags = ["dark atmosphere", "mystic", "ritual beats", "haunting", "spiritual", "ominous", "hypnotic rhythm"]
        mood_tags = ["melancholic", "mysterious", "introspective", "nostalgic", "eerie", "dreamy", "unsettling"]
        
        # 根据情感状态选择额外标签
        if emotion_state:
            if "悲伤" in emotion_state or "忧郁" in emotion_state:
                extra_mood = ["sorrowful", "tearful", "heartbreaking", "regretful"]
            elif "愤怒" in emotion_state or "激动" in emotion_state:
                extra_mood = ["aggressive", "intense", "passionate", "furious"]
            elif "平静" in emotion_state or "冷静" in emotion_state:
                extra_mood = ["calm", "serene", "peaceful", "tranquil"]
            else:
                extra_mood = ["emotional", "thoughtful", "reflective", "contemplative"]
            
            # 随机选择2-3个情绪标签
            selected_mood_tags = random.sample(mood_tags + extra_mood, random.randint(2, 3))
        else:
            selected_mood_tags = random.sample(mood_tags, random.randint(2, 3))
        
        # 随机选择2-3个风格标签
        selected_style_tags = random.sample(style_tags, random.randint(2, 3))
        
        # 随机选择4-5个基础标签
        selected_base_tags = random.sample(base_tags, random.randint(4, 5))
        
        # 算命相关标签
        if include_fortune:
            fortune_tags = ["street fortune teller", "mystic girl", "young oracle", "wanderer", "spiritual journey", "fate seeker", "lonely seer", "destiny reader"]
            selected_fortune_tags = random.sample(fortune_tags, random.randint(2, 3))
            all_tags = selected_base_tags + selected_style_tags + selected_mood_tags + selected_fortune_tags
        else:
            all_tags = selected_base_tags + selected_style_tags + selected_mood_tags
        
        # 随机打乱并拼接所有标签
        random.shuffle(all_tags)
        tags = ", ".join(all_tags)
        
        # 构建完整故事文本：开场白+中间段落+转折+结语
        selected_greeting = random.choice(greetings)
        selected_transition = random.choice(transitions)
        selected_conclusion = random.choice(conclusions)
        
        # 随机选择3-5段核心文本
        selected_core_texts = random.sample(custom_text_segments, random.randint(3, 5))
        
        # 构建完整故事文本
        story_parts = [
            selected_greeting,
            *selected_core_texts[:2],  # 前半部分文本
            selected_transition,
            *selected_core_texts[2:],  # 后半部分文本
            selected_conclusion
        ]
        
        custom_text = "\n\n".join(story_parts)
        
        # 获取简洁音乐结构描述
        music_structure = self.generate_concise_music_structure(emotion_state)
        
        # 返回完整参数
        return {
            "prompt": enhanced_prompt,  # 灵感模式提示词（自动生成完整音乐）
            "lyrics": random_lyrics,    # 自定义模式歌词（用户可精确控制歌词内容）
            "title": random_title,      # 自定义模式标题（用户可指定音乐标题）
            "tags": tags,               # 自定义模式标签（控制音乐风格和元素）
            "emotion_state": emotion_state,  # 情感状态（影响音乐情绪）
            "custom_text": custom_text,  # 自定义文本（20岁算命女孩的感受与经历）
            "music_structure": music_structure,  # 简洁的音乐结构描述
            "greeting": selected_greeting,  # 开场白
            "transition": selected_transition,  # 转折语
            "conclusion": selected_conclusion  # 结语
        }
        
    def generate_concise_music_structure(self, emotion_state: str = None) -> Dict[str, str]:
        """
        生成简洁的音乐结构描述，每个部分限制在10个字以内
        
        Args:
            emotion_state: 情感状态
            
        Returns:
            Dict: 包含音乐各部分简洁描述的字典
        """
        # 前奏描述选项
        intro_options = [
            "神秘钟声渐起",
            "低沉铜钱声响",
            "虚幻电子氛围",
            "808鼓点渐入",
            "空灵风铃摇曳",
            "雾中卜卦声起",
            "钟鼓渐起铺垫",
            "静谧电音前奏",
            "卦盘铜钱落地",
            "远处鼓声渐近",
            "算命女声低喃",
            "街边摊位噪音"
        ]
        
        # 开头描述选项
        beginning_options = [
            "算命女嗓招呼",
            "街边叫卖声起",
            "算命师邀路人",
            "命师低语询问",
            "少女算命邀请",
            "铜钱乍响起始",
            "急促节拍引入",
            "故事开场铺陈",
            "命运低语开场",
            "招揽客人声起",
            "命运交谈开始",
            "街头对话展开"
        ]
        
        # 中间过渡描述选项
        middle_options = [
            "节奏加快转折",
            "音效叠加转变",
            "故事徐徐展开",
            "铜钱交错共鸣",
            "命运轨迹交错",
            "阴阳交织变奏",
            "情绪起伏波动",
            "命师叹息过渡",
            "卦象突变转折",
            "命运线索交织",
            "对话戛然而止",
            "铜钱突然静止"
        ]
        
        # 高潮描述选项
        climax_options = [
            "强烈低音爆发",
            "命运揭晓震撼",
            "节奏全面释放",
            "灵魂共振高潮",
            "铜钱碰撞巅峰",
            "命格转变强烈",
            "卦象完整展现",
            "阴阳共振极致",
            "预言狂热迸发",
            "命运真相揭露",
            "卦象撼动心灵",
            "命师强烈呐喊"
        ]
        
        # 结尾描述选项
        outro_options = [
            "渐弱回归平静",
            "卦象完成消散",
            "电音余韵散去",
            "命师低语告别",
            "余音缓缓散去",
            "命运尘埃落定",
            "铜钱声音远去",
            "静谧回归本源",
            "道别声渐消逝",
            "命运线索断开",
            "人声渐行渐远",
            "摊前喧嚣散去"
        ]
        
        # 根据情感状态随机调整选择
        if emotion_state:
            if "悲伤" in emotion_state or "忧郁" in emotion_state:
                # 选择更忧伤的描述组合
                selected_intro = random.sample(intro_options[:8], random.randint(1, 2))
                selected_beginning = random.sample(beginning_options[:8], random.randint(1, 2))
                selected_middle = random.sample(middle_options[:8], random.randint(1, 2))
                selected_climax = random.sample(climax_options[:8], random.randint(1, 2))
                selected_outro = random.sample(outro_options[:8], random.randint(1, 2))
            elif "愤怒" in emotion_state or "激动" in emotion_state:
                # 选择更激烈的描述组合
                selected_intro = random.sample(intro_options[4:], random.randint(1, 2))
                selected_beginning = random.sample(beginning_options[4:], random.randint(1, 2))
                selected_middle = random.sample(middle_options[4:], random.randint(1, 2))
                selected_climax = random.sample(climax_options[4:], random.randint(1, 2))
                selected_outro = random.sample(outro_options[4:], random.randint(1, 2))
            elif "平静" in emotion_state or "冷静" in emotion_state:
                # 选择更平静的描述组合
                selected_intro = random.sample(intro_options[2:10], random.randint(1, 2))
                selected_beginning = random.sample(beginning_options[2:10], random.randint(1, 2))
                selected_middle = random.sample(middle_options[2:10], random.randint(1, 2))
                selected_climax = random.sample(climax_options[2:10], random.randint(1, 2))
                selected_outro = random.sample(outro_options[2:10], random.randint(1, 2))
            else:
                # 随机选择
                selected_intro = random.sample(intro_options, random.randint(1, 2))
                selected_beginning = random.sample(beginning_options, random.randint(1, 2))
                selected_middle = random.sample(middle_options, random.randint(1, 2))
                selected_climax = random.sample(climax_options, random.randint(1, 2))
                selected_outro = random.sample(outro_options, random.randint(1, 2))
        else:
            # 随机选择
            selected_intro = random.sample(intro_options, random.randint(1, 2))
            selected_beginning = random.sample(beginning_options, random.randint(1, 2))
            selected_middle = random.sample(middle_options, random.randint(1, 2))
            selected_climax = random.sample(climax_options, random.randint(1, 2))
            selected_outro = random.sample(outro_options, random.randint(1, 2))
        
        # 返回音乐结构描述
        return {
            "intro": " + ".join(selected_intro),
            "beginning": " + ".join(selected_beginning),
            "middle": " + ".join(selected_middle),
            "climax": " + ".join(selected_climax),
            "outro": " + ".join(selected_outro)
        }

# 创建单例实例
music_integration = MusicIntegration()

def get_enhanced_music_params(query: str, history: List[Dict] = None, 
                             time_info: Dict = None, emotion_state: str = None,
                             include_fortune: bool = True) -> Dict[str, Any]:
    """
    获取增强版音乐生成参数的便捷函数
    
    Args:
        query: 用户查询
        history: 对话历史
        time_info: 时间信息
        emotion_state: 情感状态
        include_fortune: 是否包含算命元素
        
    Returns:
        Dict: 音乐生成参数
    """
    return music_integration.get_music_params(
        query=query,
        history=history,
        time_info=time_info,
        emotion_state=emotion_state,
        include_fortune=include_fortune
    ) 