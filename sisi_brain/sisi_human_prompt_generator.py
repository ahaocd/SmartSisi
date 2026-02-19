#!/usr/bin/env python3
"""
🧠 Sisi人性化提示词生成器
收集所有信息，生成真正人性化的提示词

信息收集源：
1. FunASR - 语音识别结果
2. YAMNet - 音频环境分析 (音乐、噪音、人数)
3. Mem0 - 历史记忆
4. RAG - 相关知识
5. 用户画像 - 说话人特征
6. 情境分析 - 当前环境

使用Kimi K2模型生成人性化提示词
"""

import os
import sys
import json
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass
import asyncio

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))
from utils import util

# 设置日志
def setup_human_prompt_logger():
    logger = logging.getLogger('human_prompt_generator')
    logger.setLevel(logging.INFO)
    
    log_dir = Path(util.ensure_log_dir("brain"))
    
    handler = logging.FileHandler(log_dir / "human_prompt_generator.log", encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [人性化提示词] %(message)s')
    handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger

human_logger = setup_human_prompt_logger()

@dataclass
class AudioEnvironment:
    """音频环境分析"""
    has_music: bool = False
    music_type: str = "unknown"  # 古典、流行、摇滚等
    noise_level: float = 0.0     # 0-1噪音等级
    people_count: int = 1        # 估计人数
    environment_type: str = "quiet"  # quiet, noisy, crowded, music
    audio_quality: float = 1.0   # 音频质量

@dataclass
class SpeakerProfile:
    """说话人画像"""
    speaker_id: str = "unknown"
    familiarity: float = 0.0     # 熟悉度
    interaction_count: int = 0   # 交互次数
    personality_traits: List[str] = None  # 性格特征
    preferences: List[str] = None         # 偏好
    mood_history: List[str] = None        # 情绪历史

@dataclass
class ContextInfo:
    """上下文信息"""
    current_time: str = ""
    conversation_topic: str = ""
    last_responses: List[str] = None
    user_intent: str = ""
    emotional_state: str = "neutral"

class SisiHumanPromptGenerator:
    """🧠 Sisi人性化提示词生成器"""
    
    def __init__(self):
        self.config = self._load_config()
        self.kimi_client = None
        self._initialize_kimi()
        
        # 人性化回应模板
        self.human_responses = {
            "music_detected": [
                "哇，这首歌不错呢！",
                "听起来很有感觉~",
                "这个节奏我喜欢",
                "音乐品味不错哦"
            ],
            "noisy_environment": [
                "好吵啊，谁在一直啰嗦？",
                "这么吵怎么聊天啊",
                "能不能安静点？",
                "吵死了，说话都听不清"
            ],
            "crowded_situation": [
                "人好多啊",
                "这么热闹？",
                "大家都在干嘛呢",
                "人声鼎沸的"
            ],
            "singing_detected": [
                "唱得不错呢！",
                "有才华哦~",
                "继续继续！",
                "声音很好听"
            ]
        }
        
        human_logger.info("🧠 Sisi人性化提示词生成器初始化完成")
    
    def _load_config(self) -> Dict:
        """加载配置 - 从system.conf读取前脑系统配置"""
        try:
            import configparser

            # 读取前脑系统配置
            config_parser = configparser.ConfigParser()
            config_parser.read("system.conf", encoding='utf-8')

            # 从system.conf读取动态提示词生成器配置
            api_key = config_parser.get('key', 'prompt_generator_api_key', fallback='')
            base_url = config_parser.get('key', 'prompt_generator_base_url', fallback='https://api.siliconflow.cn/v1')
            model = config_parser.get('key', 'prompt_generator_model', fallback='moonshotai/Kimi-K2-Instruct')

            return {
                "provider": "siliconflow",
                "api_key": api_key,
                "base_url": base_url,
                "models": {
                    "prompt_generator": {
                        "llm_model": model
                    }
                }
            }
        except Exception as e:
            human_logger.error(f"❌ 配置加载失败: {e}")
            return self._default_config()
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            "provider": "siliconflow",
            "api_key": "",
            "base_url": "https://api.siliconflow.cn/v1",
            "models": {
                "prompt_generator": {
                    "llm_model": "moonshotai/Kimi-K2-Instruct"
                }
            }
        }
    
    def _initialize_kimi(self):
        """初始化Kimi K2模型"""
        try:
            import openai
            self.kimi_client = openai.OpenAI(
                api_key=self.config["api_key"],
                base_url=self.config["base_url"]
            )
            human_logger.info("✅ Kimi K2模型初始化成功")
        except Exception as e:
            human_logger.error(f"❌ Kimi K2初始化失败: {e}")
    
    def analyze_audio_environment(self, audio_path: str) -> AudioEnvironment:
        """分析音频环境 - 调用YAMNet"""
        env = AudioEnvironment()
        
        try:
            # 这里调用YAMNet分析
            # 模拟分析结果
            import random
            
            # 检测音乐
            music_classes = ["music", "singing", "piano", "guitar", "drums"]
            noise_classes = ["crowd", "traffic", "construction", "wind"]
            
            # 简单模拟 - 实际需要调用YAMNet
            if random.random() > 0.7:
                env.has_music = True
                env.music_type = random.choice(["流行", "古典", "摇滚", "民谣"])
            
            env.noise_level = random.uniform(0.1, 0.8)
            env.people_count = random.randint(1, 5)
            
            if env.noise_level > 0.6:
                env.environment_type = "noisy"
            elif env.people_count > 2:
                env.environment_type = "crowded"
            elif env.has_music:
                env.environment_type = "music"
            else:
                env.environment_type = "quiet"
            
            human_logger.info(f"🎵 音频环境分析: {env.environment_type}, 噪音{env.noise_level:.2f}")
            
        except Exception as e:
            human_logger.error(f"❌ 音频环境分析失败: {e}")
        
        return env
    
    def get_speaker_profile(self, speaker_id: str) -> SpeakerProfile:
        """获取说话人画像 - 从记忆系统"""
        profile = SpeakerProfile(speaker_id=speaker_id)
        
        try:
            # 这里调用Mem0获取用户画像
            # 模拟数据
            profile.familiarity = 0.8
            profile.interaction_count = 15
            profile.personality_traits = ["活泼", "幽默", "直接"]
            profile.preferences = ["音乐", "聊天", "开玩笑"]
            profile.mood_history = ["开心", "兴奋", "好奇"]
            
            human_logger.info(f"👤 说话人画像: {speaker_id} - 熟悉度{profile.familiarity:.2f}")
            
        except Exception as e:
            human_logger.error(f"❌ 说话人画像获取失败: {e}")
        
        return profile
    
    def get_context_info(self, text: str) -> ContextInfo:
        """获取上下文信息"""
        context = ContextInfo()
        
        try:
            import datetime
            context.current_time = datetime.datetime.now().strftime("%H:%M")
            
            # 简单意图识别
            if any(word in text for word in ["唱", "歌", "音乐"]):
                context.user_intent = "music_related"
            elif any(word in text for word in ["吵", "安静", "声音"]):
                context.user_intent = "noise_complaint"
            else:
                context.user_intent = "general_chat"
            
            # 情绪识别
            if any(word in text for word in ["开心", "高兴", "哈哈"]):
                context.emotional_state = "happy"
            elif any(word in text for word in ["烦", "吵", "讨厌"]):
                context.emotional_state = "annoyed"
            else:
                context.emotional_state = "neutral"
            
            human_logger.info(f"📝 上下文分析: {context.user_intent} - {context.emotional_state}")
            
        except Exception as e:
            human_logger.error(f"❌ 上下文分析失败: {e}")
        
        return context
    
    def generate_human_prompt(self, 
                            text: str, 
                            audio_path: str, 
                            speaker_id: str,
                            module_type: str) -> str:
        """生成人性化提示词 - 主函数"""
        
        start_time = time.time()
        
        # 1. 收集所有信息
        audio_env = self.analyze_audio_environment(audio_path)
        speaker_profile = self.get_speaker_profile(speaker_id)
        context_info = self.get_context_info(text)
        
        # 2. 构建信息包
        info_package = {
            "用户输入": text,
            "音频环境": {
                "环境类型": audio_env.environment_type,
                "有音乐": audio_env.has_music,
                "音乐类型": audio_env.music_type,
                "噪音等级": audio_env.noise_level,
                "人数估计": audio_env.people_count
            },
            "说话人画像": {
                "熟悉度": speaker_profile.familiarity,
                "交互次数": speaker_profile.interaction_count,
                "性格特征": speaker_profile.personality_traits,
                "偏好": speaker_profile.preferences
            },
            "上下文": {
                "时间": context_info.current_time,
                "意图": context_info.user_intent,
                "情绪": context_info.emotional_state
            },
            "目标模块": module_type
        }
        
        # 3. 调用Kimi K2生成人性化提示词
        human_prompt = self._call_kimi_k2(info_package)
        
        processing_time = round((time.time() - start_time) * 1000, 2)
        human_logger.info(f"🧠 人性化提示词生成完成 ({processing_time}ms)")
        
        return human_prompt
    
    def _call_kimi_k2(self, info_package: Dict) -> str:
        """调用Kimi K2生成提示词"""
        
        if not self.kimi_client:
            return self._fallback_prompt_generation(info_package)
        
        try:
            # 构建给Kimi K2的提示词
            system_prompt = """你是Sisi的人类语言特征分析器和提示词生成器。

基于人类语言学和心理学特征框架生成提示词：

## 人类语言特征框架：

### 1. 语言习惯特征
- 口语化表达：用"咋样"而不是"如何"
- 语气词使用：啊、呢、哦、嗯等
- 省略和简化：说"好的"而不是"好的，我明白了"
- 重复强调：真的真的、好好好

### 2. 情感表达特征
- 情绪词汇：开心→爽、生气→烦死了
- 语调变化：疑问、感叹、平述
- 情感强度：轻微不满→严重抱怨
- 共情反应：理解、安慰、共鸣

### 3. 社交互动特征
- 关系距离：熟人随意、陌生人礼貌
- 话题转换：自然过渡、突然转折
- 互动期待：希望回应、寻求认同
- 社交礼仪：问候、道谢、道歉

### 4. 认知处理特征
- 联想思维：从A想到B再到C
- 经验对比：这个像之前那个
- 直觉判断：感觉、觉得、好像
- 记忆提取：想起来了、记得

### 5. 环境适应特征
- 场景感知：安静时轻声、吵闹时大声
- 氛围匹配：严肃场合正式、轻松时随意
- 时间感知：早上问好、晚上道别
- 文化背景：本地化表达习惯

请基于这个框架分析用户输入和环境信息，生成符合人类语言特征的提示词。"""

            user_content = f"""信息包：
{json.dumps(info_package, ensure_ascii=False, indent=2)}

请为{info_package['目标模块']}生成人性化提示词。"""

            response = self.kimi_client.chat.completions.create(
                model=self.config["models"]["prompt_generator"]["llm_model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.8,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            human_logger.error(f"❌ Kimi K2调用失败: {e}")
            return self._fallback_prompt_generation(info_package)
    
    def _fallback_prompt_generation(self, info_package: Dict) -> str:
        """备用提示词生成"""
        audio_env = info_package["音频环境"]
        speaker_info = info_package["说话人画像"]
        context = info_package["上下文"]
        
        # 根据环境选择人性化回应
        human_reactions = []
        
        if audio_env["环境类型"] == "noisy":
            human_reactions.extend(self.human_responses["noisy_environment"])
        elif audio_env["环境类型"] == "music":
            human_reactions.extend(self.human_responses["music_detected"])
        elif audio_env["环境类型"] == "crowded":
            human_reactions.extend(self.human_responses["crowded_situation"])
        
        # 构建基础提示词
        prompt = f"""[{info_package['目标模块']}提示词]

当前情况：{audio_env['环境类型']}环境，{context['情绪']}情绪
用户特征：熟悉度{speaker_info['熟悉度']:.1f}，{speaker_info['性格特征']}
时间：{context['时间']}

用户说：{info_package['用户输入']}

人性化回应风格：{', '.join(human_reactions[:2]) if human_reactions else '自然随意'}

要求：像真人一样回应，不要像机器人。"""

        return prompt

# 全局实例
_human_prompt_generator = None

def get_human_prompt_generator():
    """获取人性化提示词生成器实例"""
    global _human_prompt_generator
    if _human_prompt_generator is None:
        _human_prompt_generator = SisiHumanPromptGenerator()
    return _human_prompt_generator

def generate_human_prompts_for_modules(text: str, audio_path: str, speaker_id: str) -> Dict[str, str]:
    """为三个模块生成人性化提示词"""
    generator = get_human_prompt_generator()
    
    return {
        "quick_response": generator.generate_human_prompt(text, audio_path, speaker_id, "快速响应模块"),
        "optimization_station": generator.generate_human_prompt(text, audio_path, speaker_id, "优化站"),
        "subscription_station": generator.generate_human_prompt(text, audio_path, speaker_id, "订阅站")
    }

def test_human_prompt_generator():
    """测试人性化提示词生成器"""
    print("🧪 测试Sisi人性化提示词生成器")
    print("="*60)
    
    generator = get_human_prompt_generator()
    
    test_cases = [
        ("好吵啊，能不能安静点？", "noisy_audio.wav", "speaker_01"),
        ("这首歌不错呢", "music_audio.wav", "speaker_02"),
        ("你好，我是新用户", "quiet_audio.wav", "speaker_03")
    ]
    
    for text, audio_path, speaker_id in test_cases:
        print(f"\n💬 测试输入: {text}")
        
        prompts = generate_human_prompts_for_modules(text, audio_path, speaker_id)
        
        for module, prompt in prompts.items():
            print(f"\n🎯 {module}:")
            print(prompt[:200] + "..." if len(prompt) > 200 else prompt)
    
    print("\n🎉 人性化提示词生成器测试完成！")

if __name__ == "__main__":
    test_human_prompt_generator()
