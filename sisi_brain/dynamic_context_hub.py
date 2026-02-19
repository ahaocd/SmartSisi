#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
动态大模型中枢
功能：抽取音频分析+记忆+RAG，注入到快速响应模型(liusisi.py)
"""

import json
import time
import logging
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import configparser
import requests
from pathlib import Path
from utils import config_util as cfg

@dataclass
class DynamicContext:
    """动态上下文数据"""
    audio_summary: str          # 音频分析摘要
    memory_context: str         # 记忆上下文
    rag_context: str           # RAG知识上下文
    interaction_suggestions: str # 交互建议
    emotional_state: str       # 情感状态分析
    confidence: float          # 整体置信度
    timestamp: float           # 生成时间戳

class DynamicContextHub:
    """动态大模型中枢"""
    
    def __init__(self, config_path: str = "system.conf"):
        self.logger = logging.getLogger(__name__)
        self.config = configparser.ConfigParser()

        # 🔧 修复：使用正确的绝对路径加载配置文件
        import os
        if not os.path.isabs(config_path):
            # 获取项目根目录 - 修复路径计算错误
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # SmartSisi目录
            config_path = os.path.join(base_dir, config_path)

        if os.path.exists(config_path):
            self.config.read(config_path, encoding='utf-8-sig')
            self.logger.info(f"✅ 动态提示词中枢配置加载成功: {config_path}")
        else:
            self.logger.error(f"❌ 配置文件不存在: {config_path}")
            # 尝试从utils.config_util获取配置
            try:
                from utils.config_util import load_config
                load_config()  # 确保配置已加载
                self.logger.info("✅ 从config_util获取配置成功")
            except Exception as e:
                self.logger.error(f"❌ 从config_util获取配置失败: {e}")
        
        # 从配置文件读取动态提示词系统配置 - 使用正确的键名
        # 动态提示词中枢配置
        try:
            # 从配置文件读取动态提示词中枢专用配置
            self.api_key = self.config.get('key', 'prompt_generator_api_key', fallback='')
            self.base_url = self.config.get('key', 'prompt_generator_base_url', fallback='')
            self.model = self.config.get('key', 'prompt_generator_model', fallback='GLM-4.5-X')
            self.temperature = float(self.config.get('key', 'prompt_generator_temperature', fallback='0.7'))
            self.max_tokens = int(self.config.get('key', 'prompt_generator_max_tokens', fallback='3000'))

            # 如果配置文件中没有API密钥，尝试从config_util获取
            if not self.api_key:
                try:
                    from utils.config_util import memory_llm_api_key, memory_llm_base_url
                    self.api_key = memory_llm_api_key or ''
                    self.base_url = memory_llm_base_url or ''
                    self.logger.info("✅ 从config_util获取API配置")
                except ImportError:
                    self.logger.warning("⚠️ 无法从config_util获取API配置")

        except Exception as e:
            self.logger.error(f"❌ 配置读取失败: {e}")
            # 使用默认配置
            self.api_key = '910663e20c4a49b286f27009dde10497.qYauy3JahUXDed7C'
            self.base_url = 'https://open.bigmodel.cn/api/paas/v4/'
            self.model = 'GLM-4.5-X'
            self.temperature = 0.6
            self.max_tokens = 2000
        
        # 缓存目录
        base_cache = cfg.cache_root or "cache_data"
        self.cache_dir = Path(base_cache) / "dynamic_context"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 🔥 修复：三次提示词缓存机制 - 保持三个最新的动态提示词
        self.context_cache = []  # 存储最近3个动态上下文
        self.max_cache_size = 3  # 最大缓存数量
        self.current_context: Optional[DynamicContext] = None
        
        self.logger.info(f"✅ 动态大模型中枢初始化完成 - 模型: {self.model}")

    def _get_system_prompt(self) -> str:
        """获取专业系统提示词"""
        try:
            from sisi_brain.brain_prompts_config import BrainPromptsConfig
            return BrainPromptsConfig.get_prompt_generator_prompt()
        except ImportError:
            return """You are a dynamic prompt generator.
Output <= 50 characters.
Format: ENV_REF:<quiet|noisy|music|talk|crowded|mixed|unknown>;SCENE:<short guess>
Background only. No reply suggestions, no templates, no identity/policy/strategy."""

    def extract_and_generate_context(self,
                                   audio_batches: List[Dict[str, Any]],
                                   memory_data: Dict[str, Any] = None,
                                   rag_data: Dict[str, Any] = None,
                                   current_user_input: str = "") -> DynamicContext:
        """
        抽取并生成动态上下文
        
        Args:
            audio_batches: 音频累积批次数据
            memory_data: 记忆系统数据
            rag_data: RAG系统数据
            
        Returns:
            DynamicContext: 生成的动态上下文
        """
        try:
            self.logger.info(f"🎯 开始抽取和生成动态上下文 - 音频批次: {len(audio_batches)}")

            # 🔥 关键日志：检查接收到的音频数据
            self.logger.info(f"🔥 [关键接收] 动态中枢接收到音频批次数据:")
            for i, batch in enumerate(audio_batches):
                audio_analysis = batch.get('audio_analysis', {})
                music_results = batch.get('music_results', [])
                self.logger.info(f"🔥 [关键接收] 批次{i+1}: 情况描述={audio_analysis.get('situation_description', 'N/A')}")
                self.logger.info(f"🔥 [关键接收] 批次{i+1}: 地点猜测={audio_analysis.get('location_guess', 'N/A')}")
                self.logger.info(f"🔥 [关键接收] 批次{i+1}: 音乐分析={audio_analysis.get('music_analysis', 'N/A')}")
                self.logger.info(f"🔥 [关键接收] 批次{i+1}: 音乐结果数量={len(music_results)}")

            # 1. 构建综合分析提示词
            analysis_prompt = self._build_comprehensive_prompt(audio_batches, memory_data, rag_data, current_user_input)
            
            # 2. 调用大模型进行综合分析 - 传递音频批次数据
            self._current_audio_batches = audio_batches  # 存储供造句逻辑使用
            analysis_result = self._call_llm_analysis(analysis_prompt)
            
            # 3. 解析生成动态上下文
            dynamic_context = self._parse_dynamic_context(analysis_result)
            
            # 4. 🔥 修复：三次提示词缓存机制 - 保持最新的三个动态提示词
            import time
            dynamic_context.timestamp = time.time()  # 添加时间戳

            # 添加到缓存队列
            self.context_cache.append(dynamic_context)

            # 保持最多3个缓存
            if len(self.context_cache) > self.max_cache_size:
                old_context = self.context_cache.pop(0)  # 移除最旧的
                self.logger.info(f"🗑️ 移除最旧的动态上下文 (年龄: {time.time() - old_context.timestamp:.1f}秒)")

            # 设置当前上下文为最新的
            self.current_context = dynamic_context
            self.logger.info(f"� 动态上下文已缓存 (当前缓存数: {len(self.context_cache)}/3)")
            
            self.logger.info(f"✅ 动态上下文生成完成 - 置信度: {dynamic_context.confidence:.2f}")
            return dynamic_context
            
        except Exception as e:
            self.logger.error(f"❌ 动态上下文生成失败: {e}")
            return self._create_fallback_context(audio_batches, memory_data, rag_data)
    
    def inject_to_nlp_response(self, user_input: str, asr_text: str = None) -> Dict[str, Any]:
        """
        注入动态上下文到快速响应模型 - 挂载到下次对话

        Args:
            user_input: 用户输入
            asr_text: ASR识别的文本

        Returns:
            Dict[str, Any]: 增强的输入数据
        """
        try:
            if not self.current_context:
                self.logger.warning("⚠️ 没有可用的动态上下文")
                return {'user_input': user_input, 'asr_text': asr_text}

            # 构建增强的系统提示词 - 挂载动态上下文
            enhanced_system_prompt = self._build_enhanced_system_prompt()

            # 构建增强的用户输入
            enhanced_user_input = self._build_enhanced_user_input(user_input, asr_text)

            injection_data = {
                'original_user_input': user_input,
                'original_asr_text': asr_text,
                'enhanced_system_prompt': enhanced_system_prompt,
                'enhanced_user_input': enhanced_user_input,
                'dynamic_context': {
                    'audio_summary': self.current_context.audio_summary,
                    'memory_context': self.current_context.memory_context,
                    'rag_context': self.current_context.rag_context,
                    'interaction_suggestions': self.current_context.interaction_suggestions,
                    'emotional_state': self.current_context.emotional_state
                },
                'injection_timestamp': time.time(),
                'context_confidence': self.current_context.confidence
            }

            self.logger.info(f"📤 动态上下文已注入到快速响应模型 (置信度: {self.current_context.confidence:.2f})")
            return injection_data

        except Exception as e:
            self.logger.error(f"❌ 动态上下文注入失败: {e}")
            return {'user_input': user_input, 'asr_text': asr_text}

    def get_dynamic_prompt_for_sisi(self) -> str:
        """?Sisi??????????<=50??"""
        try:
            if self.context_cache:
                latest_context = self.context_cache[-1]
                import time
                age = time.time() - latest_context.timestamp
                if age < 60:
                    self.current_context = latest_context
                else:
                    self.context_cache = [ctx for ctx in self.context_cache if time.time() - ctx.timestamp < 60]

            if not self.current_context:
                return ""

            return self._clamp_dynamic_prompt(self.current_context.audio_summary)
        except Exception as e:
            self.logger.error(f"? ??Sisi???????: {e}")
            return ""

    def _get_memory_context_for_user(self, user_id: str = "碧潭飘雪", query: str = "最近的对话", max_memories: int = 3) -> str:
        """
        🧠 动态提示词中枢搜索相关记忆 - 只使用搜索功能
        """
        try:
            from sisi_memory.sisi_mem0 import get_sisi_memory_system

            memory_system = get_sisi_memory_system()
            if not memory_system or not memory_system.is_available():
                return "记忆系统不可用"

            # 🔥 只使用搜索相关记忆功能
            memories = memory_system.search_sisi_memory(
                query=query,  # 基于查询词搜索
                speaker_id=user_id,
                limit=max_memories
            )

            if memories and len(memories) > 0:
                memory_parts = []
                for i, memory in enumerate(memories[:max_memories]):
                    if isinstance(memory, dict):
                        content = memory.get('memory', memory.get('content', str(memory)))
                        memory_parts.append(f"[{i+1}] {content[:80]}...")
                    else:
                        memory_parts.append(f"[{i+1}] {str(memory)[:80]}...")

                self.logger.info(f"✅ 动态提示词中枢搜索到{len(memories)}条相关记忆")
                return " | ".join(memory_parts)
            else:
                return "无相关历史记忆"

        except Exception as e:
            self.logger.warning(f"⚠️ 动态提示词中枢记忆搜索失败: {e}")
            return "记忆搜索失败"
    
    def _build_comprehensive_prompt(self,
                                  audio_batches: List[Dict[str, Any]],
                                  memory_data: Dict[str, Any] = None,
                                  rag_data: Dict[str, Any] = None,
                                  current_user_input: str = "") -> str:
        """构建综合分析提示词"""
        
        # 整理音频分析数据
        audio_summary = []
        for i, batch in enumerate(audio_batches, 1):
            audio_analysis = batch.get('audio_analysis', {})
            music_results = batch.get('music_results', [])
            
            audio_summary.append(f"""
批次{i} (时间: {time.strftime('%H:%M:%S', time.localtime(batch.get('timestamp', time.time())))}):
- 情况描述: {audio_analysis.get('situation_description', 'N/A')}
- 地点猜测: {audio_analysis.get('location_guess', 'N/A')}
- 人员分析: {audio_analysis.get('people_analysis', 'N/A')}
- 音乐分析: {len(music_results)}首歌曲
""")
            
            for j, music in enumerate(music_results, 1):
                song_info = music.get('song_info', {})
                audio_summary.append(f"  歌曲{j}: {song_info.get('title', 'Unknown')} - {song_info.get('artist', 'Unknown')}")
                audio_summary.append(f"  情感分析: {music.get('emotional_analysis', 'N/A')}")
        
        # 🔥 关键修复：正确处理前脑系统传递的记忆数据
        memory_summary = "暂无记忆数据"
        if memory_data:
            # 前脑系统传递的格式：{"context": memory_context, "round": self.current_round}
            memory_context = memory_data.get('context', '')
            current_round = memory_data.get('round', 0)

            if memory_context and memory_context != "记忆系统不可用":
                memory_summary = f"""
前脑系统记忆 (第{current_round}轮):
{memory_context}
"""
                self.logger.info(f"🧠 [动态中枢] 接收到前脑记忆: {memory_context[:100]}...")
            else:
                memory_summary = f"第{current_round}轮对话 (暂无相关记忆)"
                self.logger.info(f"🧠 [动态中枢] 前脑记忆为空: {memory_context}")
        else:
            self.logger.warning(f"🧠 [动态中枢] 未接收到记忆数据")
        
        # 整理RAG数据
        rag_summary = "暂无知识库数据"
        if rag_data:
            rag_summary = f"""
相关知识:
- 主题: {rag_data.get('topics', 'N/A')}
- 内容摘要: {rag_data.get('summary', 'N/A')}
- 相关度: {rag_data.get('relevance', 'N/A')}
"""
        
        # 🎯 柳思思个性特征
        sisi_personality = """
柳思思个性特征：
- 温柔体贴但有自己的小脾气，会用"呢"、"哦"、"嗯"等语气词
- 对陌生人保持礼貌距离，对熟人更加亲近
- 听到喜欢的音乐会兴奋，环境嘈杂时会不满
- 善于察言观色，喜欢侧面表达关心
- 有自己的口头禅和说话习惯
"""

        # 🎯 时间轴分析
        timeline_analysis = self._build_timeline_analysis(audio_batches)

        # 🎯 获取所有可用的上下文数据
        current_time = time.strftime('%H:%M:%S')
        current_date = time.strftime('%Y年%m月%d日')

        # 🎯 提取音乐识别结果
        music_info = self._extract_music_info(audio_batches)

        # 🎯 提取环境数据
        environment_info = self._extract_environment_info(audio_batches)

        # 🎯 提取对话历史
        conversation_history = self._extract_conversation_history(memory_summary)

        prompt = f"""
你是柳思思的Context Engineering台词生成器，基于所有真实数据生成人性化的台词建议。

=== 真实数据全景 ===
🕐 当前时间: {current_date} {current_time}
📍 真实地点: {environment_info}
👤 说话人: {self._extract_real_speaker(memory_summary)}
🌍 环境状态: {environment_info}
🎵 音乐状态: {music_info}
💬 对话历史: {conversation_history}
🗣️ 当前输入: "{current_user_input}"
🧠 记忆档案: {memory_summary}
🎭 柳思思性格: {sisi_personality}
📊 时间轴分析: {timeline_analysis}
🔊 音频感知: {''.join(audio_summary)}

=== 多维度信息巧妙融入对话 ===
基于已分析的音频数据，将多维度信息巧妙地融入自然对话中：

**融入策略（模拟人类思考）**：
- 主动话题偏移：根据环境变化自然转移话题
- 巧妙提醒：将重要信息包装成关心或调侃
- 情感共鸣：基于音频情感状态调整回复语气
- 时空感知：自然地表达对时间和环境的感知
- 记忆连接：与历史对话形成逻辑连贯

=== 输出格式 ===
《重要提示》

【时间维度融入】基于音频时间轴，巧妙融入过去现在未来：
- 过去："你刚才说话，我现在还没有回过神"
- 现在："听你这语气，心情应该不错，我懂的[laughter]"
- 未来："你待会儿是不是还要继续问我？"
- 要求：将真实的音频分析结果自然地融入时间表达中

【空间维度融入】基于环境和地点分析，自然表达空间感知：
- "你那边[环境状态]应该[地点描述]吧"
- "感觉[社交情况]，我这边也能感受到"
- "听起来[地点描述]，[环境状态]的样子"
- 要求：不直接说"检测到室内环境"，而是巧妙暗示

【记忆维度融入】结合对话历史，形成连贯逻辑：
- "你又[重复行为]，我就知道会这样"
- "还记得[历史事件]吗，现在[当前状态]"
- "你这样[当前行为]，让我想起[相关记忆]"
- 要求：与历史对话自然连接，不突兀提及过去

【事件组合融入】将多个音频事件巧妙组合：
- "刚才[事件A]，现在[事件B]，我都有点[情感反应]"
- "一边[音频事件]一边[用户行为]，你这是[推测意图]？"
- "听到[环境音]又听到[语音内容]，[综合判断]"
- 要求：自然地将多个分析结果组合成连贯表达

=== 融入要求 ===
1. **巧妙融入，不突兀描述** - 不说"检测到语音活动"，而说"你刚才说话"
2. **多维度信息组合** - 将时间、空间、记忆、事件自然组合
3. **符合对话历史** - 与之前的对话逻辑连贯，不跳跃
4. **模拟人类思考** - 像人类一样考虑话题偏移、回复策略
5. **保持随机性** - 每次提供不同的融入方式和表达
6. **人类语言习惯** - 有语气词、停顿、情感色彩
7. **基于真实数据** - 所有表达都要有音频分析数据支撑

=== 输出格式 ===
请提供5个不同的对话建议，每个建议都要：
- 融入不同维度的信息（时间/空间/记忆/事件）
- 使用不同的融入策略
- 体现不同的情感色彩和语气
- 符合柳思思的个性特征
- 与当前用户输入"{current_user_input}"形成自然回应
"""
        
        return prompt

    def _build_timeline_analysis(self, audio_batches: List[Dict[str, Any]]) -> str:
        """构建时间轴分析 - 按对话轮次和重要性排序"""
        if not audio_batches:
            return "暂无时间轴数据"

        timeline_events = []
        current_time = time.time()

        for i, batch in enumerate(audio_batches, 1):
            batch_time = batch.get('timestamp', current_time)
            time_ago = int((current_time - batch_time) / 60)  # 分钟前

            audio_analysis = batch.get('audio_analysis', {})
            music_results = batch.get('music_results', [])

            # 🎯 判断事件重要性
            importance = self._calculate_event_importance(audio_analysis, music_results)

            event_desc = f"""
第{i}轮数据 ({time_ago}分钟前) - 重要性: {importance}
- 环境: {audio_analysis.get('situation_description', '未知')}
- 地点: {audio_analysis.get('location_guess', '未知')}
- 人员: {audio_analysis.get('people_analysis', '未知')}
"""

            if music_results:
                for music in music_results:
                    song_info = music.get('song_info', {})
                    event_desc += f"- 音乐: {song_info.get('title', '未知')} - {song_info.get('artist', '未知')}\n"

            timeline_events.append({
                'time_ago': time_ago,
                'importance': importance,
                'description': event_desc,
                'round': i
            })

        # 按重要性排序，重要事件优先
        timeline_events.sort(key=lambda x: (-x['importance'], x['time_ago']))

        # 只保留最重要的3个事件
        important_events = timeline_events[:3]

        timeline_text = "=== 重要事件时间轴 ===\n"
        for event in important_events:
            timeline_text += event['description'] + "\n"

        return timeline_text

    def _calculate_event_importance(self, audio_analysis: Dict, music_results: List) -> int:
        """计算事件重要性 (1-10分)"""
        importance = 1

        # 音乐事件 +3分
        if music_results:
            importance += 3

        # 环境变化 +2分
        situation = audio_analysis.get('situation_description', '')
        if any(keyword in situation for keyword in ['变化', '新', '不同', '特殊']):
            importance += 2

        # 人员变化 +2分
        people = audio_analysis.get('people_analysis', '')
        if any(keyword in people for keyword in ['多人', '陌生', '新人', '离开']):
            importance += 2

        # 地点变化 +1分
        location = audio_analysis.get('location_guess', '')
        if location and location != '未知':
            importance += 1

        return min(importance, 10)  # 最高10分

    def _call_llm_analysis(self, prompt: str) -> str:
        """??????????????????????"""

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.model,
            'messages': [
                {
                    'role': 'system',
                    'content': self._get_system_prompt()
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }

        max_retries = 3
        timeout_seconds = 60

        def async_full_analysis():
            try:
                for attempt in range(max_retries):
                    try:
                        response = requests.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=data,
                            timeout=timeout_seconds
                        )
                        if response.status_code == 200:
                            result = response.json()
                            _ = result['choices'][0]['message']['content']
                            self.logger.info("? ???????????(??)")
                            break
                    except requests.exceptions.Timeout:
                        if attempt < max_retries - 1:
                            self.logger.warning(f"?? API????? {attempt + 1}/{max_retries}")
                            time.sleep(2 ** attempt)
                        else:
                            self.logger.error(f"? API??????{max_retries}????")
                            break
                    except Exception as e:
                        self.logger.error(f"? API????: {e}")
                        break
            except Exception as e:
                self.logger.error(f"? ???????????: {e}")

        threading.Thread(target=async_full_analysis, daemon=True).start()

        env_hint = self._build_env_hint_from_batches(getattr(self, '_current_audio_batches', []))
        return self._clamp_dynamic_prompt(env_hint)

    def _clamp_dynamic_prompt(self, text: str, limit: int = 50) -> str:
        """????????????????"""
        if not text:
            return ""
        compact = " ".join(str(text).split())
        return compact[:limit]

    def _build_env_hint_from_batches(self, audio_batches) -> str:
        """Build short background environment hint"""
        label_map = {
            'quiet': 'quiet',
            'noisy': 'noisy',
            'music': 'music',
            'conversation': 'talk',
            'speech': 'talk',
            'crowded': 'crowded',
            'mixed': 'mixed',
        }
        env_label = None
        scene = None
        try:
            for batch in audio_batches or []:
                audio_analysis = batch.get('audio_analysis', {}) or {}
                env_type = str(audio_analysis.get('environment_type') or '').strip().lower()
                if env_type:
                    env_label = label_map.get(env_type, env_type)
                if not scene:
                    scene = str(audio_analysis.get('location_guess') or audio_analysis.get('situation_description') or '').strip()
                if env_label:
                    break
        except Exception:
            env_label = None

        if not env_label:
            env_label = 'unknown'
        if scene:
            scene = " ".join(scene.split())[:12]
            return f"ENV_REF:{env_label};SCENE:{scene}"
        return f"ENV_REF:{env_label}"

    def _generate_daily_responses(self, audio_batches, memory_context, current_time, user_name) -> str:
        """???????????"""
        return ""

    def _analyze_audio_features(self, audio_batches: List[Dict[str, Any]]) -> Dict[str, str]:
        """分析音频特征，基于真实原始数据"""
        # 🔥 默认值基于"无数据"状态，不是假数据
        features = {
            'activity': '没什么动静',
            'voice_quality': '听不太清',
            'mood_guess': '不太确定',
            'location': '不知道哪里',
            'environment': '不太清楚',
            'music_hint': '没听到什么',
            'atmosphere': '说不上来',
            'social_context': '不太清楚',
            'adaptation': '不知道',
            'memory_trigger': '想不起来',
            'current_state': '不太确定',
            'reason_guess': '不知道为什么',
            'emotion_analysis': '听不出来'
        }

        if not audio_batches:
            return features

        # 🎯 基于真实原始数据分析 - 不依赖硬编码的AudioAnalysisResult
        speech_count = 0
        music_detected = False
        yamnet_classes = []
        sensevoice_texts = []
        raw_audio_types = []
        raw_confidences = []

        for batch in audio_batches:
            # 🔥 优先使用原始音频数据，而不是硬编码的分析结果
            raw_contexts = batch.get('raw_audio_contexts', [])

            for context in raw_contexts:
                # 从SmartAudioCollector的原始数据中提取
                audio_type = context.get('audio_type', 'unknown')
                confidence = context.get('confidence', 0.0)

                raw_audio_types.append(audio_type)
                raw_confidences.append(confidence)

                if audio_type == 'speech' and confidence > 0.8:
                    speech_count += 1
                elif audio_type == 'music' and confidence > 0.8:
                    music_detected = True

                # 从features中获取更详细的分析
                features_data = context.get('features', {})

                # SenseVoice原始数据
                sensevoice = features_data.get('sensevoice_result', {})
                if sensevoice.get('text'):
                    sensevoice_texts.append(sensevoice['text'])

                # 情感分析
                emotion = sensevoice.get('emotion', 'neutral')
                if emotion != 'neutral':
                    features['emotion_analysis'] = f'听起来{emotion}'

                # YAMNet原始数据
                yamnet = features_data.get('yamnet_result', {})
                if yamnet.get('top_class'):
                    yamnet_classes.append(yamnet['top_class'])

            # 🔥 同时尝试解析raw_audio_contexts（如果存在）
            raw_contexts = batch.get('raw_audio_contexts', [])
            for context in raw_contexts:
                features_data = context.get('features', {})

                # SenseVoice数据
                sensevoice = features_data.get('sensevoice_result', {})
                if sensevoice.get('text'):
                    sensevoice_texts.append(sensevoice['text'])

                if sensevoice.get('has_bgm'):
                    music_detected = True

                # YAMNet数据
                yamnet = features_data.get('yamnet_result', {})
                if yamnet.get('top_class'):
                    yamnet_classes.append(yamnet['top_class'])

        # 🎯 基于真实数据生成描述 - 增强版
        # 基于语音活动分析
        if speech_count >= 3:
            features['voice_quality'] = '听起来挺有精神的'
            features['current_state'] = '话挺多的'
            features['activity'] = '聊得挺起劲'
        elif speech_count >= 1:
            features['voice_quality'] = '有点懒懒的感觉'
            features['current_state'] = '不太想说话的样子'
            features['activity'] = '偶尔说两句'

        # 基于音乐检测
        if music_detected:
            features['music_hint'] = '刚才那首'
            features['atmosphere'] = '有音乐的感觉'
            features['activity'] = '听音乐'

        # 基于YAMNet分类
        if 'Speech' in yamnet_classes:
            features['social_context'] = '和人聊天'
            features['environment'] = '有人声'

        # 🔥 基于真实原始数据生成特征，不依赖硬编码分析
        # 基于语音检测数量
        if speech_count > 0:
            features['activity'] = '说话聊天'
            features['social_context'] = '在聊天'
            features['current_state'] = '有在说话'

        # 基于音频类型统计
        if raw_audio_types:
            speech_ratio = raw_audio_types.count('speech') / len(raw_audio_types)
            if speech_ratio > 0.7:
                features['environment'] = '对话环境'
                features['location'] = '室内聊天'
            elif speech_ratio > 0.3:
                features['environment'] = '偶有人声'
                features['location'] = '安静环境'
            else:
                features['environment'] = '比较安静'
                features['location'] = '静音环境'

        # 基于SenseVoice文本内容
        if sensevoice_texts:
            combined_text = ' '.join(sensevoice_texts)
            if len(combined_text) > 10:
                features['voice_quality'] = '说话挺清楚的'
                features['current_state'] = '表达挺流畅'
            else:
                features['voice_quality'] = '说话简短'
                features['current_state'] = '话不多'

        return features

    def _analyze_time_context(self, current_time: str) -> Dict[str, str]:
        """分析时间上下文"""
        try:
            from datetime import datetime
            now = datetime.now()
            hour = now.hour

            if 6 <= hour < 12:
                return {
                    'time_desc': '大早上',
                    'weather_guess': '清爽',
                }
            elif 12 <= hour < 18:
                return {
                    'time_desc': '大下午',
                    'weather_guess': '暖和',
                }
            elif 18 <= hour < 22:
                return {
                    'time_desc': '晚上',
                    'weather_guess': '凉快',
                }
            else:
                return {
                    'time_desc': '大半夜',
                    'weather_guess': '安静',
                }
        except:
            return {
                'time_desc': '这会儿',
                'weather_guess': '不错',
            }

    def _get_time_perception(self, current_time: str) -> str:
        """基于时间生成时间感知"""
        try:
            from datetime import datetime
            now = datetime.now()
            hour = now.hour

            if 6 <= hour < 12:
                return "*时间感知：早上的阳光透过窗户，新的一天开始了"
            elif 12 <= hour < 18:
                return "*时间感知：午后的时光，适合慢慢聊天"
            elif 18 <= hour < 22:
                return "*时间感知：夜幕降临，灯光温暖"
            else:
                return "*时间感知：夜深了，你还不睡吗？"
        except:
            return "*时间感知：时光流转，此刻正好"
    
    def _parse_dynamic_context(self, analysis_text: str) -> DynamicContext:
        """?????????????"""
        try:
            text = (analysis_text or "").strip()
            summary = self._clamp_dynamic_prompt(text)
            return DynamicContext(
                audio_summary=summary,
                memory_context="",
                rag_context="",
                interaction_suggestions="",
                emotional_state="",
                confidence=0.6 if summary else 0.0,
                timestamp=time.time()
            )
        except Exception as e:
            self.logger.error(f"? ?????????: {e}")
            return self._create_fallback_context()

    def _create_fallback_context(self, audio_batches=None, memory_data=None, rag_data=None) -> DynamicContext:
        """创建备用动态上下文 - 使用真实原始数据，不进行大模型分析"""
        try:
            # 🎯 提取真实音频数据
            real_audio_summary = self._extract_real_audio_data(audio_batches) if audio_batches else "无音频数据"

            # 🎯 使用真实记忆数据
            real_memory_context = self._extract_real_memory_data(memory_data) if memory_data else "无记忆数据"

            # 🎯 提取真实RAG数据
            real_rag_context = self._extract_real_rag_data(rag_data) if rag_data else "无知识库数据"

            # 🎯 基于音频数据推测情感状态
            emotional_state = self._infer_emotion_from_audio(audio_batches) if audio_batches else "neutral"

            return DynamicContext(
                audio_summary=real_audio_summary,
                memory_context=real_memory_context,
                rag_context=real_rag_context,
                interaction_suggestions="基于原始数据的基础交互模式",
                emotional_state=emotional_state,
                confidence=0.4,  # 有真实数据支持，置信度适中
                timestamp=time.time()
            )
        except Exception as e:
            self.logger.error(f"❌ 创建备用上下文失败: {e}")
            return DynamicContext(
                audio_summary="无可用音频数据",
                memory_context="无可用记忆数据",
                rag_context="无可用知识库数据",
                interaction_suggestions="使用基础对话模式",
                emotional_state="neutral",
                confidence=0.1,
                timestamp=time.time()
            )

    def _extract_real_audio_data(self, audio_batches) -> str:
        """提取真实音频数据，基于AudioHumanizedAnalyzer的分析结果"""
        if not audio_batches:
            return "无音频批次数据"

        try:
            audio_info = []
            for i, batch in enumerate(audio_batches, 1):
                # 🎯 提取AudioHumanizedAnalyzer的分析结果
                audio_analysis = batch.get('audio_analysis', {})
                if audio_analysis:
                    situation = audio_analysis.get('situation_description', '')
                    location = audio_analysis.get('location_guess', '')
                    music_analysis = audio_analysis.get('music_analysis', '')
                    people_analysis = audio_analysis.get('people_analysis', '')

                    if situation and situation != 'N/A':
                        audio_info.append(f"环境分析: {situation}")
                    if location and location != 'N/A':
                        audio_info.append(f"地点推测: {location}")
                    if people_analysis and people_analysis != 'N/A':
                        audio_info.append(f"人员分析: {people_analysis}")
                    if music_analysis and music_analysis != 'N/A':
                        audio_info.append(f"音乐状态: {music_analysis}")

                # 提取音乐识别真实数据
                music_results = batch.get('music_results', [])
                if music_results:
                    for music in music_results:
                        song_info = music.get('song_info', {})
                        title = song_info.get('title', 'Unknown')
                        artist = song_info.get('artist', 'Unknown')
                        audio_info.append(f"音乐识别: {title} - {artist}")

            if audio_info:
                return "基于真实音频分析的环境感知:\n" + "\n".join(audio_info)
            else:
                return "音频分析暂无有效结果"

        except Exception as e:
            self.logger.error(f"❌ 提取音频数据失败: {e}")
            return f"音频数据提取失败: {str(e)}"

    def _extract_real_memory_data(self, memory_data) -> str:
        """🗑️ 已移除提取记忆数据 - 只使用搜索记忆"""
        return "已移除提取记忆数据功能，只使用搜索记忆"

    def _extract_real_rag_data(self, rag_data) -> str:
        """提取真实RAG数据"""
        if not rag_data:
            return "无RAG检索数据"

        try:
            if isinstance(rag_data, dict):
                documents = rag_data.get('documents', [])
                if documents:
                    doc_info = []
                    for i, doc in enumerate(documents[:3], 1):
                        title = doc.get('title', 'Unknown')
                        content = doc.get('content', '')[:50]
                        score = doc.get('score', 0.0)
                        doc_info.append(f"文档{i}: {title}, 内容: {content}..., 相关度: {score}")
                    return "RAG检索结果:\n" + "\n".join(doc_info)
                else:
                    return "RAG检索无匹配文档"
            else:
                return f"RAG数据: {str(rag_data)[:100]}"

        except Exception as e:
            self.logger.error(f"❌ 提取RAG数据失败: {e}")
            return f"RAG数据提取失败: {str(e)}"

    def _infer_emotion_from_audio(self, audio_batches) -> str:
        """基于音频数据推测情感状态"""
        if not audio_batches:
            return "neutral"

        try:
            # 基于YAMNet分类推测情感
            for batch in audio_batches:
                yamnet_data = batch.get('yamnet_result', {})
                top_classes = yamnet_data.get('top_classes', [])
                has_music = yamnet_data.get('has_music', False)

                if has_music:
                    return "relaxed"  # 有音乐通常比较放松
                elif any(cls in ['Speech', 'Conversation'] for cls in top_classes):
                    return "engaged"  # 有对话表示参与状态
                elif any(cls in ['Noise', 'Traffic'] for cls in top_classes):
                    return "stressed"  # 有噪音可能比较紧张

            return "calm"  # 默认平静状态

        except Exception as e:
            self.logger.error(f"❌ 推测情感状态失败: {e}")
            return "neutral"
    
    def _save_context_cache(self, context: DynamicContext) -> None:
        """保存上下文缓存"""
        try:
            cache_file = self.cache_dir / f"context_{int(time.time())}.json"
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'audio_summary': context.audio_summary,
                    'memory_context': context.memory_context,
                    'rag_context': context.rag_context,
                    'interaction_suggestions': context.interaction_suggestions,
                    'emotional_state': context.emotional_state,
                    'confidence': context.confidence,
                    'timestamp': context.timestamp
                }, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.error(f"❌ 保存上下文缓存失败: {e}")

    def _extract_music_info(self, audio_batches: List[Dict]) -> str:
        """提取音乐识别信息"""
        try:
            music_results = []
            for batch in audio_batches:
                if isinstance(batch, dict):
                    # 检查音乐识别结果
                    if 'music_results' in batch and batch['music_results']:
                        for music in batch['music_results']:
                            music_results.append(f"识别到音乐: {music.get('title', '未知')} - {music.get('artist', '未知艺术家')}")

                    # 检查音频类型
                    if 'audio_type' in batch:
                        if batch['audio_type'] == 'music':
                            music_results.append(f"检测到音乐环境 (置信度: {batch.get('confidence', 0.0)})")

            return "; ".join(music_results) if music_results else "无音乐检测"
        except Exception as e:
            return f"音乐信息提取失败: {e}"

    def _extract_environment_info(self, audio_batches: List[Dict]) -> str:
        """提取环境信息"""
        try:
            env_info = []
            for batch in audio_batches:
                if isinstance(batch, dict) and 'analysis' in batch:
                    analysis = batch['analysis']
                    if isinstance(analysis, dict):
                        location = analysis.get('location_guess', '')
                        situation = analysis.get('situation_description', '')
                        if location:
                            env_info.append(f"地点: {location}")
                        if situation:
                            env_info.append(f"情况: {situation}")

            return "; ".join(env_info) if env_info else "室内环境，相对安静"
        except Exception as e:
            return f"环境信息提取失败: {e}"

    def _extract_conversation_history(self, memory_summary: str) -> str:
        """提取对话历史关键信息"""
        try:
            if not memory_summary or memory_summary == "暂无相关记忆":
                return "无历史对话记录"

            # 简化记忆摘要，提取关键对话
            history_lines = memory_summary.split('\n')
            key_conversations = []

            for line in history_lines:
                if '说' in line or '回应' in line or '询问' in line:
                    # 提取关键对话信息
                    if len(line.strip()) > 10:  # 过滤太短的内容
                        key_conversations.append(line.strip()[:50] + "...")

            return "; ".join(key_conversations[:3]) if key_conversations else "无关键对话历史"
        except Exception as e:
            return f"对话历史提取失败: {e}"

    def _extract_real_speaker(self, memory_summary: str) -> str:
        """从记忆中提取真实说话人信息"""
        try:
            if "碧潭飘雪" in memory_summary:
                return "碧潭飘雪 (从记忆识别)"
            elif "user1" in memory_summary:
                return "user1 (声纹识别)"
            else:
                return "未知用户"
        except Exception as e:
            return f"说话人识别失败: {e}"

    def get_current_context(self) -> Optional[DynamicContext]:
        """获取当前动态上下文"""
        return self.current_context
    
    def clear_context(self) -> None:
        """清空当前上下文"""
        self.current_context = None
        self.logger.info("🗑️ 已清空当前动态上下文")

# 全局实例
_dynamic_context_hub = None

def get_dynamic_context_hub() -> DynamicContextHub:
    """获取动态大模型中枢实例"""
    global _dynamic_context_hub
    if _dynamic_context_hub is None:
        _dynamic_context_hub = DynamicContextHub()
    return _dynamic_context_hub

if __name__ == "__main__":
    # 测试代码
    hub = get_dynamic_context_hub()
    
    # 模拟音频批次数据
    test_batches = [
        {
            'audio_analysis': {
                'situation_description': '用户在听音乐放松',
                'location_guess': '家中客厅',
                'people_analysis': '1人独处'
            },
            'music_results': [
                {
                    'song_info': {'title': '稻香', 'artist': '周杰伦'},
                    'emotional_analysis': '怀旧温暖的情感'
                }
            ],
            'timestamp': time.time()
        }
    ]
    
    # 生成动态上下文
    context = hub.extract_and_generate_context(test_batches)
    print(f"🎯 动态上下文:")
    print(f"音频摘要: {context.audio_summary}")
    print(f"交互建议: {context.interaction_suggestions}")
    print(f"情感状态: {context.emotional_state}")
    
    # 测试注入
    injection_data = hub.inject_to_nlp_response("你好", "你好")
    print(f"📤 注入数据: {json.dumps(injection_data, ensure_ascii=False, indent=2)}")
