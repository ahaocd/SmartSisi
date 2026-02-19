#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧠 真实的前脑系统 - 使用统一配置系统
- 第一层：QWQ-32B环境感知大模型(2次发送对比分析)
- 第二层：记忆累积系统 (第一人称拟人化存储)
- 第三层：动态提示词注入 (5次开始累积学习)
"""

import asyncio
import time
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from openai import OpenAI

# 全局实例
_brain_instance = None

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入统一配置系统
try:
    from utils import config_util as cfg
    CONFIG_AVAILABLE = True
    logger.info("✅ 统一配置系统导入成功")
except ImportError as e:
    CONFIG_AVAILABLE = False
    logger.error(f"❌ 统一配置系统导入失败: {e}")

# 🔧 陌生人→熟人登记钩子配置（默认关闭）
ENABLE_STRANGER_REGISTRATION_HOOK = True
STRANGER_SIM_THRESHOLD = 0.45
STRANGER_SIM_CONSECUTIVE = 3

# 🧠 记忆系统调用 - 前脑系统只使用搜索记忆
try:
    from sisi_memory.sisi_mem0 import get_sisi_memory_system
    MEMORY_AVAILABLE = True
    logger.info("✅ 记忆系统导入成功 - 只使用搜索功能")
except ImportError as e:
    MEMORY_AVAILABLE = False
    logger.error(f"❌ 记忆系统导入失败: {e}")

@dataclass
class EnvironmentAnalysis:
    """环境分析结果"""
    has_music: bool
    has_noise: bool
    has_human_voice: bool
    environment_type: str  # "quiet", "noisy", "music", "conversation"
    confidence: float
    details: str
    timestamp: float

# 🗑️ ConversationMemory类已移除 - 记忆管理由记忆集成器负责

class RealBrainSystem:
    """🧠 真实前脑系统 - 使用统一配置 - 单例模式"""

    _initialized = False

    def __init__(self):
        # 防止重复初始化
        if RealBrainSystem._initialized:
            return

        self.current_round = 0
        # 陌生人登记计数
        self._stranger_sim_count = 0
        # 🗑️ conversation_history已移除 - 记忆管理由记忆集成器负责
        self.llm_client = None

        # 从统一配置加载参数
        self._load_config()

        # 初始化LLM客户端
        self._init_llm_client()

        RealBrainSystem._initialized = True
        logger.info("✅ 真实前脑系统初始化完成")

    def _load_config(self):
        """从统一配置系统加载配置"""
        if not CONFIG_AVAILABLE:
            raise RuntimeError("统一配置系统不可用，无法初始化前脑系统")

        try:
            # 加载配置
            cfg.load_config()

            # 从system.conf获取模型配置
            self.api_key = cfg.siliconflow_api_key
            self.base_url = "https://api.siliconflow.cn/v1"

            # 从system.conf获取各层模型配置
            # 🗑️ memory_model已移除 - 记忆管理由记忆集成器负责
            self.rag_model = getattr(cfg, 'rag_llm_model', 'Qwen/Qwen3-14B')
            self.rag_embedding_model = getattr(cfg, 'rag_embedding_model', 'BAAI/bge-large-zh-v1.5')
            self.audio_analysis_model = getattr(cfg, 'audio_context_model', 'Qwen/Qwen3-8B')
            self.dynamic_prompt_model = getattr(cfg, 'prompt_generator_model', 'Qwen/QwQ-32B')

            logger.info("✅ 从统一配置系统加载配置成功")
            logger.info(f"🔑 API密钥: {self.api_key[:10]}...{self.api_key[-4:]}")
            # 🗑️ 记忆模型日志已移除
            logger.info(f"📖 RAG模型: {self.rag_model}")
            logger.info(f"🎯 动态提示词模型: {self.dynamic_prompt_model}")

        except Exception as e:
            logger.error(f"❌ 配置加载失败: {e}")
            raise RuntimeError(f"无法从统一配置系统加载配置: {e}")

    def _init_llm_client(self):
        """初始化大模型客户端"""
        if not self.api_key:
            raise ValueError("API密钥未配置，请检查system.conf文件")

        logger.info(f"🔑 使用API密钥: {self.api_key[:10]}...{self.api_key[-4:]}")
        logger.info(f"🌐 使用Base URL: {self.base_url}")

        self.llm_client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        logger.info("✅ 大模型客户端初始化完成")

    def _build_env_hint_from_analysis(self, environment_analysis: Dict[str, Any]) -> str:
        """Build short background environment hint (<=50 chars)"""
        if not isinstance(environment_analysis, dict):
            return ""
        env_type = str(environment_analysis.get("environment_type") or "").strip().lower()
        if not env_type:
            return ""
        label_map = {
            "quiet": "quiet",
            "noisy": "noisy",
            "music": "music",
            "conversation": "talk",
            "speech": "talk",
            "crowded": "crowded",
            "mixed": "mixed",
            "interactive": "talk",
        }
        label = label_map.get(env_type, env_type)
        hint = f"ENV_REF:{label}"
        return hint[:50]

    async def process_conversation(self, audio_path: str, text: str, speaker_id: str) -> Dict:
        """处理对话 - 恢复轮次递增逻辑"""
        try:
            logger.info(f"🧠 真实前脑系统开始处理: {text[:50]}...")

            # 🔥 递增对话轮次 - 恢复你的设计逻辑
            self.current_round += 1
            logger.info(f"🧠 当前对话轮次: {self.current_round}")

            # 🧭 读取统一身份（所有轮次生效）：来自 ASR_server 的 audio_context.voiceprint.identity/env
            identity = {}
            env = {}
            try:
                from core.sisi_core import get_sisi_core
                sisi_core = get_sisi_core()
                if hasattr(sisi_core, 'latest_audio_context') and sisi_core.latest_audio_context:
                    _main_ctx = sisi_core.latest_audio_context
                    _ac = _main_ctx.get('audio_context', {}) if isinstance(_main_ctx, dict) else {}
                    _vp = _ac.get('voiceprint', {}) if isinstance(_ac, dict) else {}
                    if isinstance(_vp, dict):
                        identity = _vp.get('identity') or {}
                        env = _vp.get('env') or {}
            except Exception as _e:
                logger.warning(f"⚠️ 读取统一身份失败（将使用传入speaker_id兜底）: {_e}")
            if not isinstance(identity, dict):
                identity = {}
            if not isinstance(env, dict):
                env = {}

            # 🎯 统一记忆用户键（即使早期轮次也生效）
            memory_user_id = identity.get('user_id') or speaker_id

            # 🔧 修复：复用主交互数据，避免重复调用信息管道
            if self.current_round >= 3:
                logger.info(f"🔄 复用主交互数据，避免重复API调用...")

                try:
                    # 🎯 从主交互流程获取已处理的数据
                    from core.sisi_core import get_sisi_core
                    sisi_core = get_sisi_core()

                    if hasattr(sisi_core, 'latest_audio_context'):
                        main_context = sisi_core.latest_audio_context

                        # 基于主交互数据构建环境分析
                        audio_context = main_context.get('audio_context', {})
                        voiceprint_result = main_context.get('voiceprint_result', {})

                        # 🔧 统一读取ASR_server的identity/env（SSOT）
                        identity = None
                        env = None
                        if isinstance(audio_context, dict):
                            vp = audio_context.get('voiceprint', {})
                            if isinstance(vp, dict):
                                identity = vp.get('identity')
                                env = vp.get('env')
                        if not isinstance(identity, dict):
                            identity = {}
                        if not isinstance(env, dict):
                            env = {}

                        # 🔧 修复：确保voiceprint_result是字典格式
                        if not isinstance(voiceprint_result, dict):
                            logger.warning(f"⚠️ voiceprint_result不是字典格式: {type(voiceprint_result)}, 值: {voiceprint_result}")
                            voiceprint_result = {}

                        environment_analysis = {
                            "environment_type": "interactive",  # 基于用户交互
                            "confidence": env.get('sim_top', voiceprint_result.get('confidence', 0.8)),
                            "has_speech": True,  # 用户刚刚说话
                            "speaker_identified": bool((identity or {}).get('username')),
                            "interaction_mode": "active",
                            "data_source": "main_interaction_reuse"
                        }

                        # 🪝 陌生人→熟人登记触发钩子（仅计数与提示，默认不自动注册）
                        try:
                            label = (identity or {}).get('label')
                            sim_top = (env or {}).get('sim_top', 0.0)
                            if label == 'stranger' and sim_top >= STRANGER_SIM_THRESHOLD:
                                self._stranger_sim_count += 1
                                logger.info(f"[登记候选] stranger sim_top={sim_top:.3f} 连续={self._stranger_sim_count}/{STRANGER_SIM_CONSECUTIVE}")
                            else:
                                self._stranger_sim_count = 0

                            if ENABLE_STRANGER_REGISTRATION_HOOK and self._stranger_sim_count >= STRANGER_SIM_CONSECUTIVE:
                                self._stranger_sim_count = 0
                                self._trigger_registration_candidate(main_context, identity, env)
                        except Exception as _e:
                            logger.warning(f"⚠️ 登记钩子统计异常: {_e}")

                        # 🧠 前脑系统记忆获取 - 短期历史 + 长期搜索
                        if MEMORY_AVAILABLE:
                            try:
                                memory_system = get_sisi_memory_system()
                                if memory_system and memory_system.is_available():

                                    # 🔥 1. 获取最近3条对话历史（短期记忆）
                                    # 🎯 统一使用 identity.user_id 作为唯一键
                                    memory_user_id = identity.get('user_id') or speaker_id

                                    recent_memories = memory_system.mem0_client.vector_store.list(
                                        filters={"user_id": memory_user_id},
                                        limit=3
                                    )

                                    recent_parts = []
                                    if recent_memories:
                                        sorted_recent = sorted(
                                            recent_memories,
                                            key=lambda x: x.payload.get('created_at', ''),
                                            reverse=True
                                        )
                                        for i, mem in enumerate(sorted_recent[:3]):
                                            content = mem.payload.get('data', '')[:60]
                                            if content:
                                                recent_parts.append(f"最近{i+1}: {content}")

                                    # 🔥 2. 语义搜索相关记忆（长期记忆）
                                    search_speaker_id = identity.get('user_id') or speaker_id

                                    # 组装轻量搜索query：文本 + 用户名（如有）
                                    uname = identity.get('username') or identity.get('display_name') or ""
                                    query_terms = (text[:100] + " " + uname).strip()
                                    logger.info(f"🔍 前脑系统搜索记忆: query='{query_terms}', speaker_id='{search_speaker_id}' (原始:{speaker_id})")
                                    semantic_memories = memory_system.search_sisi_memory(
                                        query=query_terms,
                                        speaker_id=search_speaker_id,
                                        limit=2
                                    )

                                    # 🔥 调试搜索结果
                                    logger.info(f"🔍 前脑搜索结果类型: {type(semantic_memories)}, 长度: {len(semantic_memories) if semantic_memories else 0}")

                                    # 🔥 详细调试搜索结果内容
                                    if semantic_memories:
                                        for i, mem in enumerate(semantic_memories[:2]):
                                            logger.info(f"🔍 搜索结果{i+1}: {type(mem)} - {str(mem)[:100]}...")

                                    # 🔥 3. 合并短期和长期记忆
                                    all_memory_parts = []

                                    # 添加短期记忆（最近对话）
                                    if recent_parts:
                                        all_memory_parts.extend(recent_parts)
                                        logger.info(f"✅ 前脑系统获取{len(recent_parts)}条短期记忆")

                                    # 添加长期记忆（语义搜索）
                                    if semantic_memories and len(semantic_memories) > 0:
                                        for i, memory in enumerate(semantic_memories[:2]):
                                            if isinstance(memory, dict):
                                                content = memory.get('memory', str(memory))[:60]
                                                score = memory.get('score', 'N/A')
                                                all_memory_parts.append(f"相关{i+1}: {content}(相似度:{score})")
                                            else:
                                                content = str(memory)[:60]
                                                all_memory_parts.append(f"相关{i+1}: {content}")
                                        logger.info(f"✅ 前脑系统搜索到{len(semantic_memories)}条长期记忆")

                                    if all_memory_parts:
                                        memory_context = f"记忆上下文: {' | '.join(all_memory_parts)}"
                                        logger.info(f"✅ 前脑系统记忆合并完成: {len(all_memory_parts)}条总记忆")
                                    else:
                                        user_name = identity.get('username') or identity.get('display_name') or speaker_id
                                        memory_context = f"用户{user_name}正在进行第{self.current_round}轮对话 (记忆搜索无结果)"
                                else:
                                    memory_context = "记忆系统不可用"
                            except Exception as e:
                                logger.error(f"❌ 前脑系统记忆搜索失败: {e}")
                                user_name = identity.get('username') or identity.get('display_name') or speaker_id
                                memory_context = f"用户{user_name}正在进行第{self.current_round}轮对话 (记忆搜索失败)"
                        else:
                            user_name = identity.get('username') or identity.get('display_name') or speaker_id
                            memory_context = f"用户{user_name}正在进行第{self.current_round}轮对话 (记忆系统不可用)"

                        logger.info(f"✅ 成功复用主交互数据，避免重复API调用")
                    else:
                        # 回退到基础分析
                        environment_analysis = {"environment_type": "quiet", "confidence": 0.5}
                        memory_context = "主交互数据不可用"
                        logger.warning(f"⚠️ 主交互数据不可用，使用基础分析")

                except Exception as e:
                    logger.error(f"❌ 复用主交互数据失败: {e}")
                    environment_analysis = {"environment_type": "quiet", "confidence": 0.5}
                    memory_context = "数据复用失败"
            else:
                # 前3轮使用简单的环境分析
                environment_analysis = {"environment_type": "quiet", "confidence": 0.5}
                memory_context = "前期对话阶段"

            # 🎯 思思系统轮次控制逻辑 - 修复阈值
            if self.current_round < 2:  # 🎯 降低阈值，第2轮开始激活
                logger.info(f"💤 漫不经心模式 (第{self.current_round}轮，未达到累积学习阈值)")
                # 🧩 注入身份摘要到提示词（OpenAI兼容：不改messages.role）
                identity_summary = ""
                try:
                    label = identity.get('label', 'stranger')
                    uname = identity.get('username') or identity.get('display_name') or '陌生人'
                    uid = identity.get('user_id', 'stranger')
                    identity_summary = f"\n《身份摘要》当前用户: {uname}（{label}，ID={uid}）\n"
                except Exception:
                    pass
                # 安全构造基础提示词，避免未赋值时引用
                base_prompt = "基础对话模式"
                try:
                    if 'dynamic_prompt' in locals() and dynamic_prompt:
                        base_prompt = dynamic_prompt
                except UnboundLocalError:
                    pass

                dynamic_prompt = base_prompt + identity_summary

                # 《权限/风格/风险》三策略（精简可控）
                policy_blocks = []
                policy_blocks.append("《权限策略》owner可用工具与指令；stranger仅答复不执行。敏感操作需二次确认。")
                policy_blocks.append("《风格策略》依据语速/时长自适应：短促放慢、冗长归纳；保持温和克制的人设。")
                policy_blocks.append("《风险策略》身份不明/信息不足/潜在风险→先澄清再行动，并记录拒绝或澄清理由。")
                dynamic_prompt = dynamic_prompt + "\n" + "\n".join(policy_blocks)

                # 🎯 后台存储环境感知数据到记忆系统
                def background_store_environment_data():
                    """后台存储环境感知数据"""
                    try:
                        if MEMORY_AVAILABLE and hasattr(self, 'latest_audio_context'):
                            memory_system = get_sisi_memory_system()
                            if memory_system and memory_system.is_available():
                                # 构建环境感知记忆内容
                                env_content = f"环境感知: {environment_analysis.get('environment_type', 'unknown')}环境，置信度{environment_analysis.get('confidence', 0.0)}"

                                # 异步存储环境数据
                                memory_system.add_sisi_memory(
                                    text=env_content,
                                    speaker_id="system_environment",
                                    response="",
                                    speaker_info={'real_name': '系统环境感知'}
                                )
                                logger.info(f"✅ 环境感知数据已后台存储")
                    except Exception as e:
                        logger.error(f"❌ 环境感知数据存储失败: {e}")

                # 启动后台存储线程
                import threading
                threading.Thread(target=background_store_environment_data, daemon=True).start()

            else:
                logger.info(f"🎯 动态提示词中枢已激活 (第{self.current_round}轮)")

                # 🎯 修复：直接获取已经处理好的动态上下文，不重新调用API
                try:
                    from sisi_brain.dynamic_context_hub import get_dynamic_context_hub
                    from sisi_brain.audio_accumulation_manager import get_audio_accumulation_manager

                    hub = get_dynamic_context_hub()
                    accumulation_manager = get_audio_accumulation_manager()

                    # 🔥 非阻塞延迟对齐：快速检查 + 异步处理
                    import time
                    max_wait_time = 15   # 最大等待15秒（大幅减少等待时间）
                    check_interval = 1   # 每1秒检查一次
                    waited_time = 0

                    logger.info(f"🔄 [前脑系统] 开始非阻塞延迟对齐...")

                    dynamic_prompt = ""

                    # 🔥 修复：不复用旧的动态上下文，强制重新生成避免重复回复
                    try:
                        # 检查是否有旧的上下文，如果有就清空
                        if hasattr(hub, 'current_context') and hub.current_context:
                            # 检查上下文的时间戳，如果超过30秒就清空
                            import time
                            if hasattr(hub.current_context, 'timestamp'):
                                age = time.time() - hub.current_context.timestamp
                                if age > 30:  # 30秒后强制清空
                                    hub.current_context = None
                                    logger.info(f"🗑️ [前脑系统] 清空过期动态上下文 (年龄: {age:.1f}秒)")
                                else:
                                    # 即使没过期，也要检查是否应该重新生成
                                    dynamic_prompt = hub.get_dynamic_prompt_for_sisi()
                                    if dynamic_prompt:
                                        logger.info(f"⚡ [前脑系统] 复用动态提示词: {len(dynamic_prompt)}字符")
                            else:
                                # 没有时间戳，直接清空
                                hub.current_context = None
                                logger.info(f"🗑️ [前脑系统] 清空无时间戳的动态上下文")
                    except Exception as e:
                        logger.warning(f"⚠️ [前脑系统] 上下文检查失败: {e}")

                    # 如果没有立即获取到，进行短时间等待
                    if not dynamic_prompt:
                        logger.info(f"⏳ [前脑系统] 开始短时间等待动态上下文生成...")

                        while waited_time < max_wait_time and not dynamic_prompt:
                            try:
                                if hasattr(hub, 'current_context') and hub.current_context:
                                    dynamic_prompt = hub.get_dynamic_prompt_for_sisi()
                                    if dynamic_prompt and "《重要提示》" in dynamic_prompt:
                                        logger.info(f"✅ [前脑系统] 延迟对齐成功，等待时间: {waited_time}秒")
                                        break
                                    elif dynamic_prompt:
                                        logger.info(f"✅ [前脑系统] 获取到基础动态提示词: {len(dynamic_prompt)}字符")
                                        break
                            except Exception as e:
                                logger.warning(f"⚠️ [前脑系统] 获取动态提示词失败: {e}")

                            time.sleep(check_interval)
                            waited_time += check_interval

                            # 减少日志频率，避免日志污染
                            if waited_time % 5 == 0:
                                logger.info(f"⏳ [前脑系统] 等待中... ({waited_time}s/{max_wait_time}s)")

                    # 超时或失败时的快速降级
                    if not dynamic_prompt:
                        if waited_time >= max_wait_time:
                            logger.warning(f"⚠️ [前脑系统] 延迟对齐超时({max_wait_time}秒)，使用智能备用模式")
                        else:
                            logger.info(f"📝 [前脑系统] 使用智能备用模式")

                        # 基于当前环境生成智能备用提示词
                        current_time = time.strftime('%H:%M')
                        dynamic_prompt = f"""基于当前时间{current_time}的智能对话模式：
- 保持自然对话节奏
- 根据用户输入灵活响应
- 体现柳思思的个性特征"""

                    logger.info(f"📝 [前脑系统] 最终动态提示词长度: {len(dynamic_prompt)}字符")

                    # 🔥 关键修复：获取累积管理器的真实音频分析数据
                    real_audio_batches = []
                    if hasattr(accumulation_manager, 'accumulated_batches') and accumulation_manager.accumulated_batches:
                        logger.info(f"🔥 [前脑系统] 获取到{len(accumulation_manager.accumulated_batches)}个真实音频批次")
                        for batch in accumulation_manager.accumulated_batches:
                            try:
                                if hasattr(batch.audio_analysis, '__dataclass_fields__'):
                                    from dataclasses import asdict
                                    audio_analysis_dict = asdict(batch.audio_analysis)
                                else:
                                    audio_analysis_dict = batch.audio_analysis.__dict__ if hasattr(batch.audio_analysis, '__dict__') else {}

                                batch_data = {
                                    'audio_analysis': audio_analysis_dict,
                                    'music_results': [asdict(music) if hasattr(music, '__dataclass_fields__') else music.__dict__ for music in batch.music_results],
                                    'raw_audio_contexts': batch.raw_audio_contexts,
                                    'timestamp': batch.timestamp
                                }
                                real_audio_batches.append(batch_data)
                                logger.info(f"🔥 [前脑系统] 批次数据: 情况描述={audio_analysis_dict.get('situation_description', 'N/A')}")
                            except Exception as e:
                                logger.error(f"❌ [前脑系统] 批次数据转换失败: {e}")

                    # 如果没有真实数据，使用基础数据
                    if not real_audio_batches:
                        logger.warning(f"⚠️ [前脑系统] 没有真实音频批次数据，使用基础数据")
                        real_audio_batches = [{"analysis": environment_analysis, "round": self.current_round}]

                    memory_data = {"context": memory_context, "round": self.current_round}

                    # 生成动态上下文 - 使用真实音频批次数据和当前用户输入
                    dynamic_context = hub.extract_and_generate_context(
                        audio_batches=real_audio_batches,
                        memory_data=memory_data,
                        rag_data=None,  # 暂时不使用RAG
                        current_user_input=text  # 🔧 修复：使用text变量而不是未定义的user_input
                    )

                    logger.info(f"🎯 [前脑系统] 动态上下文生成结果: 音频摘要={dynamic_context.audio_summary[:50]}..., 情感状态={dynamic_context.emotional_state}")

                    # 获取为Sisi系统生成的动态提示词
                    dynamic_prompt = hub.get_dynamic_prompt_for_sisi()

                    if dynamic_prompt:
                        logger.info(f"✅ 动态提示词获取成功: {len(dynamic_prompt)}字符")
                        logger.info(f"📝 [前脑系统] 动态提示词内容预览: {dynamic_prompt[:100]}...")
                    else:
                        logger.warning(f"⚠️ 动态提示词为空，生成基础增强提示词")
                        # 即使没有动态上下文，也要生成基于累积学习的增强提示词
                        dynamic_prompt = f"""
=== 🧠 累积学习增强 (第{self.current_round}轮) ===
基于前{self.current_round}轮对话的累积学习：

📊 对话轮次分析：
- 当前轮次: 第{self.current_round}轮
- 学习状态: 累积学习模式已激活
- 用户交互模式: 持续对话中

💡 交互优化建议：
- 基于多轮对话历史，提供更个性化的回应
- 注意用户的语言习惯和偏好
- 保持对话的连贯性和上下文关联

😊 情感状态：
- 保持友好和耐心的交互态度
- 根据对话氛围调整回应风格
"""

                except Exception as e:
                    logger.error(f"❌ 动态提示词获取失败: {e}")
                    dynamic_prompt = f"基于累积学习的动态提示词 (第{self.current_round}轮，获取失败)"

                # 🗑️ 高级记忆存储已移除 - 由记忆集成器在主交互流程中负责

            # 仅保留短环境参考，避免长模板注入
            dynamic_prompt = self._build_env_hint_from_analysis(environment_analysis)
            return {
                "success": True,
                "conversation_round": self.current_round,
                "environment_analysis": environment_analysis,
                "memory_context": memory_context,
                "dynamic_prompt": dynamic_prompt,
                "dynamic_context_available": self.current_round >= 5
            }

        except Exception as e:
            logger.error(f"❌ 真实前脑系统处理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "conversation_round": 0
            }

# 全局实例 - 真正的单例
_brain_instance = None
_brain_lock = threading.Lock()

def get_real_brain_system() -> RealBrainSystem:
    """获取真实前脑系统实例 - 线程安全的单例"""
    global _brain_instance
    if _brain_instance is None:
        with _brain_lock:
            if _brain_instance is None:  # 双重检查锁定
                _brain_instance = RealBrainSystem()
    return _brain_instance

# 主要接口函数
async def process_with_real_brain(user_input: str, audio_path: str = None, speaker_id: str = "unknown") -> Dict:
    """使用真实前脑系统处理输入"""
    try:
        brain = get_real_brain_system()

        # 🔥 调用真正的前脑系统处理逻辑
        logger.info(f"🧠 process_with_real_brain开始处理: {user_input[:30]}...")

        # 调用真正的对话处理函数 - 使用动态speaker_id
        cache_root = cfg.cache_root or "cache_data"
        result = await brain.process_conversation(
            audio_path=audio_path or os.path.join(cache_root, "default.wav"),
            text=user_input,
            speaker_id=speaker_id  # 🎯 使用传入的speaker_id
        )

        logger.info(f"✅ process_with_real_brain处理完成: 轮次={result.get('conversation_round', 0)}")

        return result

    except Exception as e:
        logger.error(f"❌ 真实前脑系统处理失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "conversation_round": 0,
            "environment_analysis": {},
            "memory_context": "处理失败",
            "dynamic_prompt": "基础模式"
        }

# 删除所有垃圾回退方法

# 删除错误的RealBrainSystemMethods类

if __name__ == "__main__":
    # 测试代码
    async def test_brain():
        result = await process_with_real_brain("你好，思思")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    asyncio.run(test_brain())
