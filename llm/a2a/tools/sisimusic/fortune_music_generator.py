#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
增强版Phonk音乐生成器 - 随机元素扩展版
提供更多样化的音乐生成元素和针对算命大师角色的定制化生成功能
"""

import random
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

# 配置logger
logger = logging.getLogger("fortune_music")

class FortunePhonkGenerator:
    """增强版Phonk音乐生成器，专注于随机性和特殊场景"""
    
    def __init__(self):
        """初始化增强版Phonk音乐生成器"""
        logger.info("初始化增强版Phonk音乐生成器")
    
    def generate_enhanced_phonk_prompt(self, query: str, emotion_state: str = "伤感", 
                                      include_fortune: bool = True, 
                                      dialogue_keywords: List[str] = None) -> str:
        """
        生成强化Phonk特征的专业提示词，加入随机性和算命元素
        
        Args:
            query: 用户查询
            emotion_state: 情感状态
            include_fortune: 是否包含算命大师元素
            dialogue_keywords: 从对话历史中提取的关键词
            
        Returns:
            str: 强化Phonk特征的提示词
        """
        # 核心Phonk音乐元素 - 随机选择3-5个
        core_phonk_elements = [
            "强烈的808重低音（808 heavy bass）贯穿全曲",
            "明显的cowbell节奏作为主导元素",
            "Memphis采样和Lo-fi质感",
            "侧链压缩（sidechain compression）效果",
            "变调处理的vocal samples",
            "BPM控制在70-90之间的中速节奏",
            "失真处理的电子音效",
            "VHS复古噪音和磁带饱和度",
            "重复的钢琴样本",
            "轻微破碎的鼓点",
            "低沉的低音线条",
            "回声处理的采样",
            "反转的音频片段"
        ]
        
        # 女声Phonk特有元素 - 随机选择2-3个
        female_phonk_elements = [
            "伤感女声说唱（emotional female rap）",
            "声音经过pitch shift和reverb处理",
            "在808重低音下的情感宣泄",
            "带有电子质感的人声处理",
            "Memphis风格的vocal chops",
            "低沉女声低语",
            "悠远回声女声",
            "碎片化女声采样",
            "虚幻女声音效"
        ]
        
        # 情感和氛围描述 - 随机选择一个对应情感的描述
        emotional_descriptions = {
            "伤感": [
                "深夜孤独感、都市冷漠、内心挣扎",
                "雨夜思念、失落城市、心碎时刻",
                "黑暗中的哭泣、远去的背影、消逝的记忆",
                "玻璃窗上的雨滴、映照孤独面容、泪水无声滑落"
            ],
            "愤怒": [
                "压抑的怒火、反叛精神、对抗情绪", 
                "内心燃烧、无处发泄、爆发边缘",
                "压抑已久的不满、冰冷眼神中的火焰",
                "如同火山喷发前的平静、即将爆发的情绪"
            ], 
            "孤独": [
                "夜晚街道、霓虹灯下的孤寂、思念痛苦",
                "空荡房间、旧物触发回忆、无人分享的痛楚",
                "人潮中的格格不入、被世界遗忘的角落",
                "繁华背后的寂寞、无人理解的心灵世界"
            ],
            "忧郁": [
                "雨夜思绪、回忆片段、内心阴霾",
                "灰色天空下的徘徊、无尽循环的困境",
                "时间凝固的痛苦、记忆的重担",
                "模糊视线中的世界、冰冷触感的现实"
            ],
            "狂躁": [
                "失控边缘、情绪爆发、极限压抑",
                "快速闪动的思绪、无法停止的内心躁动",
                "理智与疯狂的边界、崩溃前的挣扎",
                "电流般穿过大脑的焦虑、无法平静的心跳"
            ]
        }
        
        # 算命大师/道士元素 - 如果启用了算命元素
        fortune_elements = [
            "古老占卜的神秘氛围",
            "命运的轮回与抉择",
            "八卦与五行的平衡",
            "道士咒语的低语",
            "算命铃铛的清脆声响",
            "塔罗牌预示的未来",
            "阴阳交汇的奇妙时刻",
            "算命道士的箴言",
            "紫微斗数的星象",
            "周易卦象的变化",
            "香火袅袅中的启示",
            "命运线交织的图景",
            "预言与谶语的低吟"
        ]
        
        # 随机选择核心Phonk元素
        selected_phonk_elements = random.sample(core_phonk_elements, random.randint(3, 5))
        
        # 随机选择女声元素（女声是必选元素）
        selected_female_elements = random.sample(female_phonk_elements, random.randint(2, 3))
        
        # 选择情感描述
        emotion_desc_list = emotional_descriptions.get(emotion_state, emotional_descriptions["伤感"])
        emotion_desc = random.choice(emotion_desc_list)
        
        # 从用户查询中提取关键主题
        theme_keywords = self._extract_theme_keywords(query)
        
        # 整合对话关键词（如果有）
        dialogue_theme = ""
        if dialogue_keywords and len(dialogue_keywords) > 0:
            filtered_keywords = [k for k in dialogue_keywords if len(k) >= 2 and k not in theme_keywords]
            if filtered_keywords:
                dialogue_theme = f"，对话关键词：{'、'.join(filtered_keywords[:2])}"
        
        # 添加算命大师元素（如果启用）
        fortune_theme = ""
        if include_fortune:
            selected_fortune = random.sample(fortune_elements, random.randint(2, 3))
            fortune_theme = f"，融合算命元素：{' + '.join(selected_fortune)}"
        
        # 构建最终的专业Phonk提示词
        phonk_elements_text = "，".join(selected_phonk_elements)
        female_elements_text = "，".join(selected_female_elements)
        
        phonk_prompt = f"""创作TWISTED Drift Phonk：{phonk_elements_text}。{female_elements_text}，表达{emotion_desc}。主题：{theme_keywords}{dialogue_theme}{fortune_theme}。标签：drift phonk,female rap,808 bass,cowbell,memphis,emotional,dark,fortune teller。必须有明显808 bass和cowbell特征！"""

        logger.info(f"[增强Phonk生成] 随机化提示词已生成，长度: {len(phonk_prompt)}字符")
        return phonk_prompt
    
    def generate_random_lyrics(self, query: str, emotion_state: str = None, 
                               include_fortune: bool = True,
                               dialogue_keywords: List[str] = None) -> str:
        """
        生成随机化的歌词，避免重复内容
        
        Args:
            query: 用户查询
            emotion_state: 情感状态
            include_fortune: 是否包含算命元素
            dialogue_keywords: 对话关键词
            
        Returns:
            str: 生成的随机歌词
        """
        # 确保有情感状态
        if not emotion_state:
            emotion_state = self._analyze_emotion(query)
            
        # 各种情感的歌词模板库 - 每种情感多个模板
        emotion_lyrics = {
            "伤感": [
                "无尽的夜 我独自徘徊\n思念如潮水 心碎难释怀\n回忆里的画面 一幕幕闪现\n你的笑容 已成为过去",
                "城市的灯光 照不亮心中的迷茫\n时间带走了一切 却带不走思念\n泪水落下 只剩下孤独与伤感\n这条路 我只能一个人走到尽头",
                "冰冷的雨滴 敲打着窗台\n模糊了视线 也模糊了未来\n曾经的誓言 如今只剩叹息\n谁能懂我 心中的悲伤",
                "深夜里独自行走 霓虹灯闪烁不停\n回忆如刀割 划过心的伤痕\n寻找着逝去的温暖 却只剩下冰冷\n灵魂在黑暗中 寻找光明的出口"
            ],
            "愤怒": [
                "压抑的怒火 在胸口燃烧\n无法控制的情绪 即将爆发\n眼神中的冰冷 隐藏着不满\n这一刻 我要释放真实的自我",
                "面具下的真相 终将被揭露\n假装的平静 掩盖不了内心的怒火\n世界的不公 让人窒息\n我要挣脱枷锁 找回自由",
                "被欺骗的感觉 如同刀割\n信任崩塌的瞬间 怒火中烧\n伪装的面孔 终将被撕破\n这一次 我不再沉默",
                "愤怒在血液中沸腾 眼中只有冰冷\n被背叛的感觉 像毒药蔓延全身\n曾经的温柔 如今化作利剑\n我要让真相 大白于天下"
            ],
            "孤独": [
                "人群中的孤独 最为痛苦\n千万人之中 没人懂我心\n寂静的夜 只有月光相伴\n在无人的角落 独自哭泣",
                "繁华世界 我是局外人\n走过热闹街道 内心却如此空洞\n寻找着共鸣 却找不到回应\n孤独已成为 我生命的一部分",
                "空荡的房间 回荡着寂寞\n四下无人 只有思绪蔓延\n试图寻找温暖 却只有冰冷\n孤独如影随形 无法摆脱",
                "孤独是一座孤岛 四面环海\n远离喧嚣 也远离理解\n无人能懂我心中的世界\n只能在黑暗中 独自前行"
            ]
        }
        
        # 算命/道士主题歌词模板
        fortune_lyrics = [
            "十年漂泊 走遍千山万水\n看尽世间悲欢 学会窥探天机\n当年师父离去 只留一句话\n命中注定的人 终会相遇",
            "七岁那年 我看见别人看不见的东西\n村里人都说我疯了 只有师父收留我\n掌纹里藏着过去 眼神中能读到未来\n这是诅咒 也是我的宿命",
            "曾经为钱算尽天机 如今只求一份心安\n多少人来求姻缘 我却算不准自己的情路\n前世欠下的债 今生必须偿还\n听我一言 或许能改变你的命运",
            "摆摊十年 风里雨里不曾停歇\n多少人的秘密 我都看在眼里藏在心里\n有人感谢我指明方向 有人恨我道破天机\n这卦金难换 真相最伤人"
        ]
        
        # 获取对应情感的歌词模板
        lyric_templates = emotion_lyrics.get(emotion_state, emotion_lyrics["伤感"])
        
        # 随机选择一个情感模板
        selected_lyrics = random.choice(lyric_templates)
        
        # 如果包含算命元素，有50%概率使用算命主题歌词
        if include_fortune and random.random() > 0.5:
            selected_lyrics = random.choice(fortune_lyrics)
        
        # 在歌词中融入用户查询和对话的关键词
        lyrics_lines = selected_lyrics.split('\n')
        
        # 从查询中提取关键词
        query_keywords = []
        if len(query) > 5:
            import re
            query_keywords = re.findall(r'[\w\u4e00-\u9fff]{2,4}', query)
            query_keywords = [k for k in query_keywords if len(k) >= 2 and k not in ["音乐", "歌曲", "创作", "生成"]]
        
        # 从对话历史中提取的关键词
        history_keywords = []
        if dialogue_keywords:
            history_keywords = [k for k in dialogue_keywords if len(k) >= 2 and k not in ["音乐", "歌曲", "创作", "生成"]]
        
        # 整合所有关键词
        all_keywords = query_keywords + history_keywords
        
        # 修改歌词，添加关键词（如果有）
        if all_keywords and len(all_keywords) > 0 and len(lyrics_lines) >= 4:
            # 随机选择1-2个关键词
            selected_keywords = random.sample(all_keywords, min(2, len(all_keywords)))
            
            # 随机选择歌词行进行修改
            line_index = random.randint(1, len(lyrics_lines) - 2)
            
            # 添加关键词
            if len(selected_keywords) == 1:
                lyrics_lines[line_index] += f" {selected_keywords[0]}的痕迹"
            else:
                lyrics_lines[line_index] += f" {selected_keywords[0]}与{selected_keywords[1]}"
                
            # 重组歌词
            selected_lyrics = '\n'.join(lyrics_lines)
        
        return selected_lyrics
    
    def _analyze_emotion(self, query: str) -> str:
        """分析查询中的情感倾向"""
        emotions = ["伤感", "愤怒", "孤独", "忧郁", "狂躁"]
        
        # 情感关键词映射
        emotion_keywords = {
            "伤感": ["伤心", "难过", "悲伤", "痛苦", "思念", "哭", "泪", "心碎"],
            "愤怒": ["生气", "愤怒", "气愤", "发火", "暴怒", "恼火", "憎恨"],
            "孤独": ["孤独", "寂寞", "一个人", "孤单", "无人理解", "独自"],
            "忧郁": ["忧伤", "忧郁", "低落", "消沉", "灰心", "郁闷"],
            "狂躁": ["狂躁", "兴奋", "激动", "疯狂", "躁动", "亢奋"]
        }
        
        # 检测查询中是否包含情感关键词
        detected_emotions = []
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in query:
                    detected_emotions.append(emotion)
                    break
        
        # 如果检测到情感，返回第一个匹配的情感
        if detected_emotions:
            return detected_emotions[0]
        
        # 如果没有检测到明确情感，随机返回一个情感（偏向伤感）
        weights = [0.5, 0.1, 0.2, 0.15, 0.05]  # 各情感的权重
        return random.choices(emotions, weights=weights, k=1)[0]
    
    def _extract_theme_keywords(self, query: str) -> str:
        """
        从用户查询中提取主题关键词
        
        Args:
            query: 用户查询
            
        Returns:
            str: 提取的关键词
        """
        if not query or len(query.strip()) < 3:
            return "深夜情感"
        
        # 简单的关键词提取逻辑
        import re
        keywords = re.findall(r'[\w\u4e00-\u9fff]{2,8}', query)
        
        # 过滤常用词
        filter_words = {"音乐", "歌曲", "创作", "生成", "播放", "下载", "首", "一", "的", "了", "在", "是", "有", "我", "要", "想", "听"}
        keywords = [k for k in keywords if k not in filter_words and len(k) >= 2]
        
        if keywords:
            # 随机打乱关键词顺序
            random.shuffle(keywords)
            return "、".join(keywords[:3])  # 最多取3个关键词
        else:
            # 如果没有提取到关键词，返回随机主题
            random_themes = ["夜晚思绪", "情感世界", "命运轨迹", "心灵深处", "时光流转", "记忆碎片"]
            return random.choice(random_themes)
    
    def extract_dialogue_keywords(self, history: List[Dict]) -> List[str]:
        """
        从对话历史中提取关键词
        
        Args:
            history: 对话历史列表
            
        Returns:
            List[str]: 提取的关键词列表
        """
        if not history or len(history) == 0:
            return []
            
        # 合并最近3轮对话文本
        recent_texts = []
        for i in range(min(3, len(history))):
            entry = history[-(i+1)]  # 从最近的开始
            if "content" in entry:
                recent_texts.append(entry["content"])
                
        if not recent_texts:
            return []
            
        combined_text = " ".join(recent_texts)
        
        # 提取关键词
        import re
        keywords = re.findall(r'[\w\u4e00-\u9fff]{2,8}', combined_text)
        
        # 过滤常用词和短词
        filter_words = {"音乐", "歌曲", "创作", "生成", "播放", "下载", "首", "一", "的", "了", "在", "是", "有", "我", "要", "想", "听", "好", "这", "那", "就", "吧", "呢", "啊", "嗯", "哦", "呀"}
        keywords = [k for k in keywords if k not in filter_words and len(k) >= 2]
        
        # 去重
        unique_keywords = list(set(keywords))
        
        # 最多返回5个关键词
        if unique_keywords:
            # 随机打乱顺序
            random.shuffle(unique_keywords)
            return unique_keywords[:5]
        
        return [] 