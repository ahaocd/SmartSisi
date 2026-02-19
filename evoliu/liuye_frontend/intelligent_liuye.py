#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
智能柳叶
TTS语音 + 冒险者公会 + 轻量对话
"""

import os
import sys
import json
import time
import asyncio
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class IntelligentLiuye:
    """智能柳叶"""
    
    def __init__(self):
        self.name = "智能柳叶"
        self.version = "3.0.0"  # 升级版本号
        self.status = "initializing"

        # ?? ????
        self.sisi_config = self._load_sisi_config()

        # TTS???native(????TTS) / system(???Sisi??TTS)
        self.liuye_tts_mode = os.environ.get("LIUYE_TTS_MODE", "system").lower().strip() or "system"

        # ?? TTS?????system??????????
        self.tts_engine = None
        self._init_tts_engine()

        # ?? ??????
        self.system_health = {}

        self.agent_capabilities = self._query_agent_capabilities()

        # 🔧 工具注册器（动态注册工具，不硬编码）
        from evoliu.liuye_guild_integration import get_tool_registry
        self.tool_registry = get_tool_registry()
        
        # 🏰 公会系统集成（按需创建，不用单例）
        self._guild_enabled = os.environ.get("GUILD_ENABLED", "1") == "1"
        self._guild_unsubscribe = None  # 取消订阅函数
        self._notified_tasks = set()  # 已通知的任务ID（防止重复通知）
        self._pending_guild_clarify_task_id = None
        self._pending_guild_clarify_question = None
        
        # 🔥 柳叶回复状态标记（用于公会事件队列）
        self._is_generating_response = False  # 标记柳叶是否正在生成文本回复
        self._response_lock = threading.Lock()  # 保护状态的锁
        self._pending_guild_events = []  # 待处理的公会事件队列

        # 公会事件主动播报策略：always / important_only / manual / silent
        self._guild_report_mode = self._normalize_guild_report_mode(
            os.environ.get("LIUYE_GUILD_REPORT_MODE", "important_only")
        )

        # 兼容旧版文本工具路由（默认关闭，只保留结构化工具调用）
        self._legacy_text_tool_enabled = os.environ.get("LIUYE_LEGACY_TEXT_TOOL_ROUTER", "0") == "1"
        
        # 🔥 记住最近提交的任务（用于上下文理解）
        self._latest_submitted_task_id = None  # 最近提交的任务ID
        self._latest_submitted_task_time = 0  # 最近提交任务的时间戳
        
        # 注册基础工具
        self._register_base_tools()
        
        # 🔥 注册公会工具（按需创建公会实例）
        if self._guild_enabled:
            self._register_guild_tools()

        self.status = "ready"
        logger.info(f"[{self.name}] 柳叶系统初始化完成 - 智能对话 + TTS + Web界面 + 公会系统")
        logger.info(f"[{self.name}] 智能体能力已加载: {len(self.agent_capabilities.get('tools', {}))}个工具")
        logger.info(f"[{self.name}] 工具注册器已就绪，事件总线已启动")

        # MCP SSE桥接已删除（不再使用）

        # 🎯 启动时自动运行一次QwenCLI（幂等防重复，不依赖环境变量）
        try:
            self._start_qwen_analysis_background()
        except Exception:
            pass
    
    @property
    def guild(self):
        """按需创建公会实例（不用单例，参考开源项目）"""
        if not self._guild_enabled:
            return None
        
        try:
            from evoliu.guild_supervisor_agent import get_guild_instance
            guild_instance = get_guild_instance()
            logger.info(f"[{self.name}] ✅ 公会实例已就绪")
            return guild_instance
        except Exception as e:
            logger.error(f"[{self.name}] 公会实例创建失败: {e}")
            return None

    def _get_guild_runtime_state(self, guild=None) -> dict:
        """读取公会运行态（不抛异常，失败时返回离线态）。"""
        try:
            g = guild if guild is not None else self.guild
            if not g:
                return {
                    "enabled": bool(self._guild_enabled),
                    "ready": False,
                    "running": False,
                    "pending_queue_size": 0,
                }

            pending_tasks = getattr(g, "pending_tasks", None)
            pending_size = len(pending_tasks) if isinstance(pending_tasks, list) else 0
            return {
                "enabled": True,
                "ready": bool(getattr(g, "listener_ready", False)),
                "running": bool(getattr(g, "listener_running", False)),
                "pending_queue_size": pending_size,
            }
        except Exception:
            return {
                "enabled": bool(self._guild_enabled),
                "ready": False,
                "running": False,
                "pending_queue_size": 0,
            }
    
    def _register_base_tools(self):
        """注册基础工具（MCP相关已删除）"""
        # MCP相关工具已删除
        logger.info(f"[{self.name}] ✅ 基础工具已注册: 0个（MCP已删除）")
    
    def _register_guild_tools(self):
        """注册公会工具（动态注册，不硬编码）"""
        if not self._guild_enabled:
            return
        
        # 注册公会任务提交（不指定冒险者，公会自动分配）
        self.tool_registry.register(
            name="submit_task",
            func=lambda desc: self._submit_task_to_guild(desc),
            description="提交任务给公会（公会会自动分配合适的冒险者）",
            category="guild",
            examples=["submit_task('搜索AI论文')"]
        )
        
        # 注册公会任务查询
        self.tool_registry.register(
            name="query_task",
            func=lambda task_id=None: self._format_guild_task_status(task_id or self._latest_submitted_task_id),
            description="查询公会任务状态（不指定task_id时，查询最近提交的任务）",
            category="guild",
            examples=["query_task()", "query_task('task_123')"]
        )
        
        # 注册公会任务停止
        self.tool_registry.register(
            name="abort_task",
            func=lambda task_id: self._abort_guild_task(task_id),
            description="停止公会任务",
            category="guild",
            examples=["abort_task('task_123')"]
        )
        
        # 注册公会强制解散（停止全部任务并待命）
        self.tool_registry.register(
            name="dissolve_guild",
            func=lambda reason=None: self._dissolve_guild(reason or "柳叶强制解散"),
            description="强制停止公会全部任务并进入待命状态",
            category="guild",
            examples=["dissolve_guild('用户要求立即停止全部任务')"]
        )
        
        # 注册公会任务列表
        self.tool_registry.register(
            name="list_tasks",
            func=lambda status=None: self._format_guild_task_list(status),
            description="列出公会任务",
            category="guild",
            examples=["list_tasks('running')"]
        )
        
        # 注册公会成员查询
        self.tool_registry.register(
            name="get_members",
            func=lambda: self._format_guild_members(),
            description="获取公会成员列表",
            category="guild",
            examples=["get_members()"]
        )

        self.tool_registry.register(
            name="answer_clarification",
            func=lambda task_id, answer: self._answer_guild_clarification(task_id, answer),
            description="回答公会澄清问题并继续任务",
            category="guild",
            examples=["answer_clarification('task_123','补充信息...')"]
        )

        self.tool_registry.register(
            name="set_guild_report_mode",
            func=lambda mode: self._set_guild_report_mode(mode),
            description="设置公会事件主动播报模式（always/important_only/manual/silent）",
            category="guild",
            examples=["set_guild_report_mode('important_only')"]
        )

        self.tool_registry.register(
            name="get_guild_report_mode",
            func=lambda: self._get_guild_report_mode(),
            description="查询当前公会事件主动播报模式",
            category="guild",
            examples=["get_guild_report_mode()"]
        )
        
        logger.info(f"[{self.name}] ✅ 公会工具已注册: 9个")

    def _normalize_guild_report_mode(self, mode: str) -> str:
        value = str(mode or "").strip().lower()
        if value in ("always", "important_only", "manual", "silent"):
            return value
        return "important_only"

    def _should_report_guild_event(self, event_type: str) -> bool:
        mode = self._normalize_guild_report_mode(getattr(self, "_guild_report_mode", "important_only"))
        evt = str(event_type or "").strip().lower()
        if mode in ("manual", "silent"):
            return False
        if mode == "always":
            return True
        # important_only
        return evt in ("complete", "failed", "clarify")

    def _set_guild_report_mode(self, mode: str) -> str:
        normalized = self._normalize_guild_report_mode(mode)
        self._guild_report_mode = normalized
        return f"✅ 公会播报模式已设置为：{normalized}"

    def _get_guild_report_mode(self) -> str:
        mode = self._normalize_guild_report_mode(getattr(self, "_guild_report_mode", "important_only"))
        return f"当前公会播报模式：{mode}"

    def _notify_or_queue_guild_event(self, event_type: str, text: str, priority: int = 5) -> None:
        if not text:
            return
        if not self._should_report_guild_event(event_type):
            logger.info(f"[{self.name}] 公会事件跳过主动播报: mode={self._guild_report_mode}, type={event_type}")
            return
        with self._response_lock:
            if self._is_generating_response:
                self._pending_guild_events.append({
                    "type": event_type,
                    "text": text,
                    "priority": int(priority),
                })
                logger.info(f"[{self.name}] 柳叶正在生成回复，事件已入队: type={event_type}")
                return
        self._generate_liuye_tts(text, priority=int(priority))
    
    def _submit_task_to_guild(self, description: str, conversation_context: str = "") -> str:
        """提交任务给公会（按需创建公会实例）
        
        Args:
            description: 任务描述
            conversation_context: 对话历史上下文（可选）
        
        🔥 同步返回：如果需要澄清，直接返回澄清问题
        """
        try:
            # 🔥 按需创建公会实例
            guild = self.guild
            if not guild:
                return "❌ 公会系统未启用"

            # 尝试启动监听；即使当前离线也允许入队，恢复后自动派发
            try:
                guild.ensure_listener_started()
            except Exception as e:
                logger.warning(f"[{self.name}] 公会监听启动异常: {e}")
            
            # 🔥 订阅公会事件（每次提交任务时订阅）
            if self._guild_unsubscribe is None:
                self._guild_unsubscribe = guild.subscribe(self._on_guild_event)
            
            # 🔥 整合任务描述和对话上下文
            full_description = description
            if conversation_context:
                full_description = f"{description}\n\n【对话上下文】\n{conversation_context}"
            
            # 提交任务（公会自动分配冒险者）
            task_id = guild.submit_task(full_description)
            
            # 🔥 记住最近提交的任务
            import time
            self._latest_submitted_task_id = task_id
            self._latest_submitted_task_time = time.time()
            runtime_state = self._get_guild_runtime_state(guild)
            if runtime_state.get("ready"):
                return "✅ 任务已提交给公会，他们正在处理中~"
            return "🟡 公会当前离线，任务已加入公会队列，连接恢复后会自动执行。"
        except Exception as e:
            logger.error(f"[{self.name}] 提交任务失败: {e}")
            return f"❌ 提交任务失败: {e}"
    
    def _abort_guild_task(self, task_id: str) -> str:
        """停止公会任务"""
        try:
            guild = self.guild
            if not guild:
                return "❌ 公会系统未启用"
            
            ret = guild.abort_task(task_id)
            if isinstance(ret, dict) and ret.get("success"):
                return f"✅ 任务已停止: {task_id}"
            if isinstance(ret, dict):
                return f"❌ 停止任务失败: {ret.get('error', 'unknown')}"
            return f"✅ 任务已停止: {task_id}"
        except Exception as e:
            logger.error(f"[{self.name}] 停止任务失败: {e}")
            return f"❌ 停止任务失败: {e}"
    
    def _dissolve_guild(self, reason: str = "") -> str:
        """强制解散公会：停止全部任务并进入待命。"""
        try:
            guild = self.guild
            if not guild:
                return "❌ 公会系统未启用"
            
            ret = guild.dissolve_guild(reason or "柳叶触发强制解散")
            if isinstance(ret, dict) and ret.get("success"):
                count = ret.get("aborted_count", 0)
                return f"✅ 公会已解散，已强制停止{count}个任务，正在待命"
            if isinstance(ret, dict):
                return f"❌ 公会解散失败: {ret.get('error', 'unknown')}"
            return "✅ 公会已解散并进入待命"
        except Exception as e:
            logger.error(f"[{self.name}] 公会解散失败: {e}")
            return f"❌ 公会解散失败: {e}"
    
    def _on_guild_event(self, event: dict):
        """处理公会事件（统一入口）"""
        event_type = event.get("type")
        
        if event_type == "progress":
            self._on_guild_task_progress(event)
        elif event_type == "complete":
            self._on_guild_task_completed(event)
        elif event_type == "failed":
            self._on_guild_task_failed(event)
        elif event_type == "clarify":
            self._on_guild_task_clarify(event)

    def _on_guild_task_clarify(self, data: dict):
        """公会任务澄清回调（异步事件）
        
        当公会分析任务后发现需要澄清时，会发布此事件
        柳叶收到后，将澄清问题加入TTS队列（priority=6），等待播放
        """
        try:
            task_id = data.get("task_id")
            question = data.get("question", "")
            
            if not question:
                logger.warning(f"[{self.name}] 收到澄清事件但问题为空: {task_id}")
                return
            
            logger.info(f"[{self.name}] 收到澄清事件: {task_id}, 问题: {question[:50]}...")
            
            # 保存澄清上下文
            self._pending_guild_clarify_task_id = task_id
            self._pending_guild_clarify_question = question
            
            # 🔥 关键修复：将澄清问题加入TTS队列，不打断当前播放
            # 优先级设置为6（高于正常回复5，低于打招呼7）
            clarify_text = (
                f"哥哥，我需要确认一下：{question}。"
                "你回复“补充：你的答案”我就继续任务。"
                "你也可以先继续和我聊天。"
            )
            self._notify_or_queue_guild_event("clarify", clarify_text, priority=6)
            logger.info(f"[{self.name}] ✅ 澄清问题处理完成（type=clarify）")
            
        except Exception as e:
            logger.error(f"[{self.name}] 处理澄清事件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _answer_guild_clarification(self, task_id: str, answer: str) -> str:
        try:
            guild = self.guild
            if not guild:
                return "❌ 公会系统未启用"
            ok = guild.answer_clarification(task_id, answer)
            if ok:
                if self._pending_guild_clarify_task_id == task_id:
                    self._pending_guild_clarify_task_id = None
                    self._pending_guild_clarify_question = None
                return "✅ 已提交补充信息，任务继续执行"
            return "❌ 提交补充信息失败"
        except Exception as e:
            logger.error(f"[{self.name}] 提交澄清答案失败: {e}")
            return f"❌ 提交澄清答案失败: {e}"

    def _extract_clarification_answer(self, text: str) -> str:
        """从用户文本中提取澄清回答。

        规则:
        - 推荐显式前缀: `补充: ...` / `回答: ...`
        - 兼容少量自然短句开头: `选A` / `就按...` / `答案是...`
        """
        raw = str(text or "").strip()
        if not raw:
            return ""

        prefixes = (
            "补充:", "补充：", "澄清:", "澄清：",
            "回答:", "回答：", "答复:", "答复：",
            "公会补充:", "公会补充：",
        )
        for prefix in prefixes:
            if raw.startswith(prefix):
                return raw[len(prefix):].strip()

        direct_markers = ("选", "我选", "就按", "按", "答案是", "继续", "改成")
        if any(raw.startswith(marker) for marker in direct_markers):
            return raw

        return ""

    def _should_force_guild_submit(self, user_text: str) -> bool:
        """显式委托给公会时，走硬路由，避免模型口头答应却不提交任务。"""
        # 默认关闭，避免“硬编码式”行为。仅在显式开启时启用。
        if os.environ.get("LIUYE_FORCE_GUILD_SUBMIT", "0") != "1":
            return False

        text = str(user_text or "").strip()
        if not text:
            return False

        # 状态查询/闲聊不强制提交
        status_keywords = (
            "进度", "完成了吗", "完成没", "怎么样了", "状态",
            "在做什么", "任务列表", "list_tasks", "query_task"
        )
        if any(k in text for k in status_keywords):
            return False

        # 明确把任务交给公会/冒险者（兼容“工会”口误）
        delegate_markers = (
            "让公会", "交给公会", "公会那边", "请公会",
            "让工会", "交给工会", "工会那边", "请工会",
            "让冒险者", "交给冒险者", "冒险者去",
            "发布任务", "派个任务", "委托公会"
        )
        if any(k in text for k in delegate_markers):
            return True
        return False
    
    def _clean_markdown_for_tts(self, text: str) -> str:
        """清理 Markdown 符号，让 TTS 更自然"""
        import re
        
        # 去掉代码块
        text = re.sub(r'```[\s\S]*?```', '', text)
        
        # 去掉标题符号 (##, ###)
        text = re.sub(r'#{1,6}\s+', '', text)
        
        # 去掉粗体/斜体 (**, *, __)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        
        # 去掉表格符号 (|, -)
        text = re.sub(r'\|', ' ', text)
        text = re.sub(r'-{3,}', '', text)
        
        # 去掉链接 [text](url)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        
        # 去掉列表符号 (-, *, +)
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        
        # 去掉多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 去掉行首行尾空格
        text = '\n'.join(line.strip() for line in text.split('\n'))
        
        return text.strip()
    
    def _on_guild_task_progress(self, data: dict):
        """公会任务进度回调（全时双工推送）"""
        task_id = data.get("task_id", "unknown")
        progress = data.get("progress", "")
        logger.info(f"[{self.name}] 📊 任务进度: {task_id} - {progress}")
        if progress:
            self._notify_or_queue_guild_event("progress", f"公会进展更新：{progress[:120]}", priority=4)
    
    def _on_guild_task_completed(self, data: dict):
        """公会任务完成回调"""
        task_id = data.get("task_id", "unknown")
        result = data.get("result")  # 🔥 不设置默认值，允许None
        description = data.get("description", "")
        logger.info(f"[{self.name}] ✅ 任务完成: {task_id}")
        
        # 🔥 防止重复通知（同一个任务只通知一次）
        if task_id in self._notified_tasks:
            logger.info(f"[{self.name}] ⏭️  任务已通知过，跳过: {task_id}")
            return
        
        # 🔥 只通知有结果的任务
        if result is None or not result:
            logger.info(f"[{self.name}] ⏭️  任务无结果，跳过通知: {task_id}")
            return
        
        # 🔥 主动通知用户（通过TTS）
        try:
            # 标记为已通知
            self._notified_tasks.add(task_id)
            
            # 🔥 清理 Markdown 符号，让 TTS 更自然
            clean_result = self._clean_markdown_for_tts(result)
            
            # 🔥 修复：发送完整结果给 TTS，不要截断
            # 如果结果太长（超过 500 字），才进行智能摘要
            if len(clean_result) > 500:
                # 智能摘要：取前 300 字 + 最后 100 字
                summary = clean_result[:300] + "... " + clean_result[-100:]
            else:
                # 结果不长，完整发送
                summary = clean_result
            
            notification = f"任务完成啦！{description[:20]}的结果是：{summary}"
            logger.info(f"[{self.name}] 📢 准备通知用户: {notification[:50]}...")
            self._notify_or_queue_guild_event("complete", notification, priority=5)
            
        except Exception as e:
            logger.error(f"[{self.name}] 通知用户失败: {e}")
    
    def _on_guild_task_failed(self, data: dict):
        """公会任务失败回调"""
        task_id = data.get("task_id", "unknown")
        error = data.get("error", "")
        description = data.get("description", "")
        logger.error(f"[{self.name}] ❌ 任务失败: {task_id} - {error}")
        
        # 🔥 主动通知用户
        try:
            notification = f"任务失败了...{description[:20]}执行出错：{error[:50]}"
            logger.info(f"[{self.name}]  准备通知用户: {notification[:50]}...")
            self._notify_or_queue_guild_event("failed", notification, priority=6)
            
        except Exception as e:
            logger.error(f"[{self.name}] 通知用户失败: {e}")
    
    def _process_pending_guild_events(self):
        """处理待处理的公会事件队列"""
        try:
            with self._response_lock:
                if not self._pending_guild_events:
                    return
                
                # 取出所有待处理事件
                events = self._pending_guild_events.copy()
                self._pending_guild_events.clear()
            
            # 依次播放
            for event in events:
                event_type = event.get("type")
                text = event.get("text", "")
                priority = int(event.get("priority", 5) or 5)
                
                if text:
                    logger.info(f"[{self.name}] 📢 处理队列事件: {event_type} - {text[:50]}...")
                    self._generate_liuye_tts(text, priority=priority)
                    
        except Exception as e:
            logger.error(f"[{self.name}] 处理公会事件队列失败: {e}")
    
    # === 工具函数实现（MCP相关已删除）===
    
    def _format_guild_task_status(self, task_id: str) -> str:
        """格式化公会任务状态（返回自然语言，让LLM自己组织）"""
        try:
            guild = self.guild
            if not guild:
                return "❌ 公会系统未启用"

            task_id = str(task_id or "").strip()
            if not task_id:
                return "还没有可查询的任务。你先给我一个任务，我会帮你盯进度。"

            task_data = guild.storage.load_task(task_id)
            if not task_data:
                return f"❌ 任务不存在: {task_id}"
            
            status = task_data.get('status', 'unknown')
            description = task_data.get('description', '未知任务')
            created_at = task_data.get('created_at', 0)
            executor = (
                task_data.get('member_name')
                or task_data.get('assigned_to')
                or task_data.get('executor')
                or '未知成员'
            )
            error = task_data.get('error')
            
            # 计算运行时长
            import time
            elapsed = int(time.time() - created_at)
            elapsed_str = f"{elapsed // 60}分{elapsed % 60}秒" if elapsed >= 60 else f"{elapsed}秒"
            
            # 获取streams信息
            streams = task_data.get('streams', {})
            assistant_events = streams.get('assistant', [])
            tool_events = streams.get('tool', [])
            error_events = streams.get('error', [])
            
            # 🔧 随机的开场白（模拟收到飞鸽传书）
            import random
            greetings = [
                "哎呀，公会那边有消息了！",
                "嗯...收到公会的飞鸽传书了~",
                "让我看看公会传来的消息...",
                "公会那边刚刚回信了，",
                "哦？公会的信使来了，",
                "收到了，公会那边说...",
            ]
            greeting = random.choice(greetings)
            
            # 🔧 根据状态返回自然语言（不硬编码格式）
            if status == "running":
                if len(assistant_events) > 0:
                    latest_text = assistant_events[-1].get('text', '')
                    return f"{greeting}{executor}还在忙活呢。\n\n任务是：{description}\n\n最新进展：{latest_text[:150]}...\n\n已经过去{elapsed_str}了。"
                elif len(tool_events) > 0:
                    latest_tool = tool_events[-1].get('name', '')
                    return f"{greeting}{executor}正在执行工具：{latest_tool}。\n\n任务是：{description}\n\n已经运行{elapsed_str}了，再等等看..."
                else:
                    return f"{greeting}{executor}接到任务了，但还没开始动手。\n\n任务是：{description}\n\n已经等了{elapsed_str}了..."
            
            elif status == "completed":
                result_text = task_data.get('result', '')
                if result_text:
                    return f"{greeting}{executor}完成任务了！\n\n任务是：{description}\n\n他们的回复：\n{result_text[:500]}\n\n用时：{elapsed_str}"
                else:
                    return f"{greeting}{executor}说任务完成了，但没给详细结果。\n\n任务是：{description}\n\n用时：{elapsed_str}"
            
            elif status == "failed":
                if error:
                    error_msg = error
                elif len(error_events) > 0:
                    error_msg = error_events[-1].get('message', '未知错误')
                else:
                    error_msg = "任务失败了，但没说原因"
                
                return f"{greeting}唉，{executor}遇到问题了...\n\n任务是：{description}\n\n他们说：{error_msg}\n\n已经尝试了{elapsed_str}"
            
            else:
                return f"{greeting}任务状态不太清楚...{executor}那边的情况是：{status}\n\n任务是：{description}"
        
        except Exception as e:
            return f"❌ 查询失败: {e}"
    
    def _format_guild_task_list(self, status: str = None) -> str:
        """格式化公会任务列表（返回原始数据，让柳叶自己简化）"""
        try:
            guild = self.guild
            if not guild:
                return "❌ 公会系统未启用"
            
            tasks = guild.storage.list_tasks(status=status)
            if not tasks:
                return "暂无任务"
            
            # 🔥 返回原始数据，让柳叶的LLM自己转换成通俗易懂的话
            result = "公会任务列表:\n"
            for task in tasks[:5]:  # 只显示前5个
                result += f"- {task['description'][:100]}... (状态: {task['status']})\n"
            return result
        except Exception as e:
            return f"❌ 查询失败: {e}"
    
    def _format_guild_members(self) -> str:
        """格式化公会成员列表"""
        try:
            guild = self.guild
            if not guild:
                return "❌ 公会系统未启用"
            
            members = guild.get_members()
            result = "公会成员:\n"
            for member in members:
                result += f"- {member['name']} ({member['status']})\n"
                result += f"  能力: {', '.join(member['capabilities'][:3])}...\n"
            return result
        except Exception as e:
            return f"❌ 查询失败: {e}"
    
    def _query_agent_capabilities(self) -> dict:
        """查询智能体系统的能力"""
        return {
            "agents": {},
            "tools": {},
            "workflow": "智能体能力查询未启用"
        }

    def _start_qwen_analysis_background(self):
        """后台启动QwenCLI分析（从liuye_monitor.py恢复）"""
        import threading
        import asyncio

        # 防止重复启动
        if hasattr(self, "_monitor_running") and getattr(self, "_monitor_running", False):
            logger.info("[监控] 已在运行，跳过重复启动")
            return
        self._monitor_running = True

        def run_qwen_analysis():
            try:
                _qwen_debug = os.environ.get("QWEN_DEBUG", "0") == "1"
                if _qwen_debug:
                    logger.info("🎯 开始QwenCLI人类偏好分析...")

                # 检查是否有事件循环
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果有运行中的循环，在新线程中创建新循环
                        asyncio.set_event_loop(asyncio.new_event_loop())
                        loop = asyncio.get_event_loop()
                except RuntimeError:
                    # 没有事件循环，创建新的
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # 运行QwenCLI分析
                task_data = {"type": "human_preference_analysis", "data": {}}
                qwen_result = loop.run_until_complete(self._execute_qwen_analysis_real_async(task_data))

                if qwen_result.get("success"):
                    if _qwen_debug:
                        logger.info("✅ QwenCLI分析完成")
                else:
                    logger.error(f"❌ QwenCLI分析失败: {qwen_result.get('error')}")

            except Exception as e:
                logger.error(f"❌ QwenCLI后台启动失败: {e}")

        # 在后台线程启动
        self._qwen_thread = threading.Thread(target=run_qwen_analysis, daemon=True)
        self._qwen_thread.start()
        if os.environ.get("QWEN_DEBUG", "0") == "1":
            logger.info("🎯 QwenCLI分析已在后台启动")

    def start_monitoring(self):
        """对外提供的启动方法（幂等）"""
        try:
            self._start_qwen_analysis_background()
        except Exception as e:
            logger.error(f"[监控] 启动失败: {e}")

    def stop_monitoring(self):
        """对外提供的停止方法（当前分析为一次性，提供幂等占位以兼容旧调用）"""
        try:
            self._monitor_running = False
        except Exception:
            pass

    async def _execute_qwen_analysis_real_async(self, task_data: dict) -> dict:
        """异步版本的QwenCLI分析"""
        return self._execute_qwen_cli_monitoring(task_data)

    # 双模型决策系统已移除

    # OpenAI客户端创建方法已移除

    def _load_sisi_config(self):
        """加载sisi配置"""
        try:
            # 直接加载system.conf文件
            import os
            
            # 查找system.conf文件
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            config_file = os.path.join(project_root, "system.conf")
            
            if os.path.exists(config_file):
                # 直接解析system.conf
                sisi_config = {}
                with open(config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            sisi_config[key.strip()] = value.strip()
                
                logger.info(f"[{self.name}] ✅ system.conf配置加载成功")
                return sisi_config
            else:
                raise FileNotFoundError("system.conf文件不存在")
                
        except Exception as config_error:
            logger.error(f"[{self.name}] system.conf加载失败: {config_error}")
            # 无system.conf时不再使用医疗包配置，保持空的柳叶配置
            sisi_config = {
                'liuye_llm_model': '',
                'liuye_llm_api_key': '',
                'liuye_llm_base_url': '',
                'liuye_llm_temperature': '0.7',
                'liuye_llm_max_tokens': '2000',
                'liuye_stream_first_token_timeout_sec': '5',
                'liuye_fallback_llm_model': '',
                'liuye_fallback_llm_api_key': '',
                'liuye_fallback_llm_base_url': '',
                'liuye_fallback_llm_temperature': '',
                'liuye_fallback_llm_max_tokens': '',
            }
            logger.info(f"[{self.name}] 使用空配置")
            return sisi_config

    # 多余的智能模块初始化方法已删除 - 简化为智能对话
    


    def _init_tts_engine(self):
        """初始化TTS语音引擎"""
        try:
            if self.liuye_tts_mode == "system":
                self.tts_engine = None
                return

            # 使用柳叶专用的TTS引擎
            import sys
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            sys.path.insert(0, os.path.join(project_root, "evoliu", "liuye_frontend"))

            from liuye_voice_tts import generate_liuye_voice
            self.tts_engine = generate_liuye_voice

            # TTS配置
            self.tts_config = {
                "voice_enabled": True,
                "input_voice": True,    # 支持语音输入
                "output_voice": True,   # 支持语音输出
                "streaming_tts": True,  # 流式语音输出
                "interrupt_support": True  # 支持语音打断
            }

            logger.info(f"[{self.name}] 柳叶专用TTS语音引擎初始化完成")

        except Exception as e:
            logger.error(f"[{self.name}] TTS语音引擎初始化失败: {str(e)}")
            self.tts_engine = None
    
    # 动态提示词系统已删除 - 使用配置模型直接对话
    
    # 重复的动态提示词系统已删除
    
    def _generate_liuye_tts(self, text: str, priority: int = 5, send_to_web: bool = True):
        """Delegate all playback to Core (local/device disabled)."""
        try:
            return self._delegate_to_system_tts(text, priority=priority, send_to_web=send_to_web)
            if False:
                # - detect device online
                # - use liuye_voice_tts.generate_liuye_voice_streaming
                # - fallback to _delegate_to_system_tts
                pass
        except Exception as e:
            logger.error(f"[{self.name}] Unified TTS failed: {str(e)}")
            return False

    def _get_sisi_core_instance(self):
        """Resolve current SisiCore instance with compatibility fallbacks."""
        sisi_core_obj = None
        try:
            from core import sisi_booter as _booter
            sisi_core_obj = getattr(_booter, 'sisi_core', None) or getattr(_booter, 'sisiCore', None)
        except Exception:
            sisi_core_obj = None

        if sisi_core_obj is None:
            try:
                from core import sisi_core as _sisi_core
                if hasattr(_sisi_core, 'get_sisi_core'):
                    sisi_core_obj = _sisi_core.get_sisi_core()
                if not sisi_core_obj and hasattr(_sisi_core, 'sisi_core'):
                    sisi_core_obj = _sisi_core.sisi_core
                if not sisi_core_obj and hasattr(_sisi_core, '_sisi_core_instance'):
                    sisi_core_obj = _sisi_core._sisi_core_instance
            except Exception:
                sisi_core_obj = None
        return sisi_core_obj

    def _delegate_to_system_tts(self, text: str, priority: int = 5, send_to_web: bool = True) -> bool:
        try:
            from core.interact import Interact
            interact = Interact("liuye", 1, {"user": "User", "msg": text})
            # 标记为柳叶委托调用，避免Core判定为“后置阶段非委托调用”而跳过
            try:
                setattr(interact, 'interleaver', 'liuye')
            except Exception:
                pass

            sisi_core_obj = self._get_sisi_core_instance()
            if sisi_core_obj:
                # 🔥 修复：不设置跳过标志，Core已通过interleaver='liuye'识别委托调用
                # Core的防重复机制会自动处理后置阶段的重复调用

                sisi_core_obj.process_audio_response(
                    text=text,
                    username="User",
                    interact=interact,
                    priority=priority,
                    send_to_web=send_to_web,
                )
                logger.info(f"[{self.name}] 已将柳叶文本交由Core系统TTS播放（priority={priority}, send_to_web={send_to_web}）")
                return True

            logger.error(f"[{self.name}] Core实例不可用，无法统一播放")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 统一系统TTS调用失败: {str(e)}")
            return False

    def _play_tts_on_computer_from_files(self, audio_files: list, text: str):
        return
        if False:
            if self.liuye_tts_mode != "native":
                logger.info(f"[{self.name}] system模式，跳过本地播放")
                return
            try:
                import pygame
                import os
                pygame.mixer.init()
                audio_file = audio_files[0] if isinstance(audio_files, list) else audio_files
                if os.path.exists(audio_file):
                    pygame.mixer.music.load(audio_file)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(100)
                    logger.info(f"[{self.name}] 本地播放完成: {text[:50]}...")
                else:
                    logger.error(f"[{self.name}] 音频文件不存在: {audio_file}")
            except Exception as e:
                logger.error(f"[{self.name}] 本地播放失败: {str(e)}")

    def _send_liuye_audio_to_esp32(self, audio_files: list, text: str):
        """禁用文件直发，统一由系统TTS链路（OPUS）处理，避免重复播放"""
        logger.info(f"[{self.name}] 已禁用柳叶文件直发ESP32，统一走系统TTS链路")
            
    def _play_tts_on_computer(self, text: str):
        """仅在native模式本地播放；system模式跳过"""
        if self.liuye_tts_mode != "native":
            logger.info(f"[{self.name}] system模式，跳过本地播放")
            return
        # native模式已在_generate_liuye_tts里处理
        pass
            
    # 重复的process_user_input方法已删除
    
    def _check_aug_status(self) -> Dict[str, Any]:
        """真实检查AUG和AI工具状态"""
        try:
            import subprocess
            import shutil

            status = {
                "timestamp": time.time(),
                "tools": {},
                "overall_health": "unknown"
            }

            # [TARGET] 检查VSCode是否安装
            try:
                vscode_path = shutil.which("code")
                if vscode_path:
                    result = subprocess.run(["code", "--version"], capture_output=True, text=True, timeout=5)
                    status["tools"]["vscode"] = {
                        "available": result.returncode == 0,
                        "version": result.stdout.split('\n')[0] if result.returncode == 0 else "unknown",
                        "path": vscode_path
                    }
                else:
                    status["tools"]["vscode"] = {"available": False, "error": "VSCode未安装"}
            except Exception as e:
                status["tools"]["vscode"] = {"available": False, "error": str(e)}

            # [TARGET] 检查QwenCLI是否安装
            try:
                qwen_available = shutil.which("qwen") is not None
                if qwen_available:
                    result = subprocess.run(["qwen", "--version"], capture_output=True, text=True, timeout=5)
                    status["tools"]["qwen_cli"] = {
                        "available": result.returncode == 0,
                        "version": result.stdout.strip() if result.returncode == 0 else "unknown"
                    }
                else:
                    status["tools"]["qwen_cli"] = {"available": False, "error": "QwenCLI未安装"}
            except Exception as e:
                status["tools"]["qwen_cli"] = {"available": False, "error": str(e)}


            # 计算整体健康状态
            available_tools = sum(1 for tool in status["tools"].values() if tool.get("available", False))
            total_tools = len(status["tools"])

            if available_tools >= total_tools * 0.8:
                status["overall_health"] = "healthy"
            elif available_tools >= total_tools * 0.5:
                status["overall_health"] = "degraded"
            else:
                status["overall_health"] = "unhealthy"

            logger.info(f"[工具检查] 可用工具: {available_tools}/{total_tools}, 整体状态: {status['overall_health']}")
            return status

        except Exception as e:
            logger.error(f"[工具检查] 检查失败: {e}")
            return {"available": False, "error": str(e), "overall_health": "error"}
    
    def _analyze_performance(self) -> Dict[str, Any]:
        """分析性能指标"""
        try:
            performance = {
                "response_time": self._measure_response_time(),
                "throughput": self._measure_throughput(),
                "error_rate": self._calculate_error_rate(),
                "resource_efficiency": self._calculate_resource_efficiency(),
                "user_satisfaction": self._estimate_user_satisfaction()
            }
            
            self.performance_metrics = performance
            return performance
            
        except Exception as e:
            logger.error(f"[{self.name}] 性能分析失败: {str(e)}")
            return {}
    
    
    async def process_voice_input(self, audio_data: bytes) -> str:
        """处理语音输入"""
        try:
            # 1. 语音识别
            from asr import get_asr_engine
            asr_engine = get_asr_engine()
            text = asr_engine.recognize(audio_data)
            
            # 2. 动态提示词生成
            if self.dynamic_prompt_system:
                dynamic_prompt = await self.dynamic_prompt_system.generate_dynamic_prompt(
                    text, 
                    await self.dynamic_prompt_system.analyze_environment_with_qwq("", text)
                )
            else:
                dynamic_prompt = "柳叶收到语音消息"
            
            # 3. 处理对话
            response = await self._process_intelligent_conversation(text, dynamic_prompt)
            
            # 4. 语音输出
            if self.tts_engine and self.tts_config["output_voice"]:
                await self._stream_voice_output(response)
            
            return response
            
        except Exception as e:
            logger.error(f"[{self.name}] 语音输入处理失败: {str(e)}")
            return f"语音处理遇到问题: {str(e)}"
    
    async def _process_intelligent_conversation(self, text: str, dynamic_prompt: str) -> str:
        """智能对话处理（同步版本的异步包装）"""
        try:
            # 🔥 修复：传递前脑记忆（brain_prompts）
            user_id = self._get_current_user_id()
            return self._process_user_input_sync(text, speaker_id=user_id, brain_prompts=dynamic_prompt)
        except Exception as e:
            logger.error(f"[{self.name}] 智能对话处理失败: {str(e)}")
            return f"对话处理遇到问题: {str(e)}"

    async def _call_analysis_model_for_conversation(self, text: str) -> str:
        """调用配置的分析模型进行对话"""
        try:
            # 获取柳叶的提示词
            liuye_prompt = self.get_liuye_prompt()

            # 获取分析模型配置
            analysis_config = self.get_analysis_model_config()

            # 调用配置的分析模型
            from openai import OpenAI
            client = OpenAI(
                api_key=analysis_config["api_key"],
                base_url=analysis_config["base_url"]
            )

            response = client.chat.completions.create(
                model=analysis_config["model"],  # 使用配置文件中的模型
                messages=[
                    {"role": "system", "content": liuye_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=analysis_config["temperature"],
                max_tokens=analysis_config["max_tokens"]
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"[{self.name}] 分析模型调用失败: {str(e)}")
            return f"柳叶暂时无法回应，请稍后再试: {str(e)}"

    def _process_emotion_triggers(self, text: str) -> str:
        """处理回复中的情感触发器（不再生成TTS，因为流式已播放）"""
        try:
            # 导入情感触发器处理函数
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from utils.emotion_trigger import detect_and_trigger_emotions

            # 处理情感触发器
            clean_text, triggered_emotions = detect_and_trigger_emotions(text)

            if triggered_emotions:
                logger.info(f"[{self.name}] 处理了情感触发器: {triggered_emotions}")

            # 🔥 修复：删除重复TTS调用，流式处理已经播放过了
            # self._generate_liuye_tts(clean_text)  # ← 注释掉，避免重复播放

            return clean_text

        except Exception as e:
            logger.error(f"[{self.name}] 情感触发器处理失败: {str(e)}")
            return text  # 如果处理失败，返回原文本

    # 重复的TTS方法已删除

    # 重复的ESP32发送方法已删除
    
    async def _stream_voice_output(self, text: str):
        """流式语音输出"""
        try:
            if self.tts_engine:
                # 分段流式输出
                sentences = text.split('。')
                for sentence in sentences:
                    if sentence.strip():
                        self.tts_engine.say(sentence.strip() + "。")
                        await asyncio.sleep(0.1)  # 流式间隔
            
        except Exception as e:
            logger.error(f"[{self.name}] 流式语音输出失败: {str(e)}")
    
    def _should_involve_aug(self, text: str) -> bool:
        """判断是否需要AUG参与"""
        aug_keywords = [
            "代码", "优化", "修复", "分析", "诊断", 
            "性能", "错误", "bug", "改进", "升级"
        ]
        return any(keyword in text for keyword in aug_keywords)
    
    
    # 辅助方法
    def _calculate_health_score(self, health_status: Dict) -> float:
        """计算健康分数"""
        try:
            cpu_score = 1.0 - (health_status.get("cpu_usage", 0) / 100)
            memory_score = 1.0 - (health_status.get("memory_usage", 0) / 100)
            disk_score = 1.0 - (health_status.get("disk_usage", 0) / 100)
            
            return (cpu_score + memory_score + disk_score) / 3
        except:
            return 0.5
    
    def _measure_response_time(self) -> float:
        """测量响应时间"""
        # 模拟测量
        return 1.2

    # [TARGET] 对话接口方法
    def process_user_input(self, user_input: str) -> str:
        """处理用户文字输入 - 同步版本"""
        try:
            # 检查是否已有事件循环
            import asyncio
            try:
                # 尝试获取当前循环
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果循环正在运行，使用同步处理
                    return self._process_user_input_sync(user_input)
                else:
                    # 循环存在但未运行，使用同步处理
                    return self._process_user_input_sync(user_input)
            except RuntimeError:
                # 没有事件循环，创建新的
                return self._process_user_input_sync(user_input)
        except Exception as e:
            logger.error(f"[{self.name}] 处理用户输入失败: {str(e)}")
            return f"抱歉，处理您的请求时出现了问题：{str(e)}"

    def _process_user_input_sync(
        self,
        user_input: str,
        speaker_id: str = None,
        brain_prompts: str = None,
        handoff_messages=None,
        llm_override: dict = None,
    ) -> str:
        """同步处理用户输入 - 调用真正的AI模型 + 智能体协作
        
        Args:
            user_input: 用户输入文本
            speaker_id: 说话人ID（如果为None，则尝试动态获取）
            brain_prompts: 前脑系统提供的动态提示词（已准备好，不阻塞）
        """
        try:
            llm_user_content_parts = None
            user_input_payload = user_input
            if isinstance(user_input, dict) and isinstance(user_input.get("llm_user_content_parts"), list):
                llm_user_content_parts = user_input.get("llm_user_content_parts")
                user_input_payload = llm_user_content_parts
                user_input = str(user_input.get("text") or "").strip()
            elif isinstance(user_input, dict):
                user_input = str(user_input.get("text") or user_input.get("content") or "").strip()
                user_input_payload = user_input
            else:
                user_input = str(user_input or "")
                user_input_payload = user_input

            # 🔥 标记：柳叶开始生成回复
            with self._response_lock:
                self._is_generating_response = True
            
            # 🎯 动态获取用户ID（参考思思系统逻辑）
            user_id = self._get_current_user_id(speaker_id)

            if self._pending_guild_clarify_task_id and isinstance(user_input, str) and user_input.strip():
                text = user_input.strip()
                if text in ("跳过", "取消", "不用了", "先不补充", "先不回答"):
                    self._pending_guild_clarify_task_id = None
                    self._pending_guild_clarify_question = None
                    return "好的，这个澄清我先挂起。你可以继续聊天，之后随时说“补充：内容”继续任务。"

                clarification_answer = self._extract_clarification_answer(text)
                if clarification_answer:
                    task_id = self._pending_guild_clarify_task_id
                    return self._answer_guild_clarification(task_id, clarification_answer)

            # 显式委托任务时强制走公会提交，避免“口头说已提交”但没触发工具。
            if isinstance(user_input, str) and self._should_force_guild_submit(user_input):
                submit_ret = self._submit_task_to_guild(user_input)
                return self._process_emotion_triggers(submit_ret)

            # 兼容旧路由：仅在显式开启时才允许文本正则工具拦截
            if self._legacy_text_tool_enabled:
                tool_handled, tool_response = self._intercept_and_execute_tools(user_input)
                if tool_handled:
                    return self._process_emotion_triggers(tool_response)

            # 🔥 **直接调用AI模型，无简单回复逻辑**
            # 获取柳叶的提示词
            liuye_prompt = self.get_liuye_prompt()
            
            # 获取分析模型配置
            analysis_config = self.get_analysis_model_config()
            if isinstance(llm_override, dict):
                style = str(llm_override.get("api_style") or "").strip().lower()
                if style in ("", "openai"):
                    base_url = str(llm_override.get("base_url") or "").strip()
                    api_key = str(llm_override.get("api_key") or "").strip()
                    model_name = str(llm_override.get("model") or "").strip()
                    if base_url and api_key and model_name:
                        analysis_config = dict(analysis_config)
                        analysis_config["base_url"] = base_url
                        analysis_config["api_key"] = api_key
                        analysis_config["model"] = model_name
                else:
                    logger.warning(f"[{self.name}] 非OpenAI风格override已忽略: {style}")
            if llm_user_content_parts:
                logger.info(
                    f"[{self.name}] 多模态直传已启用: blocks={len(llm_user_content_parts)}, model={analysis_config.get('model', '')}"
                )
            
            # 检查配置是否有效
            if not analysis_config["api_key"] or not analysis_config["model"]:
                logger.error(f"[{self.name}] AI模型配置缺失")
                return f"我是柳叶，系统配置需要检查。"
            
            # 调用配置的分析模型
            from openai import OpenAI
            client = OpenAI(
                api_key=analysis_config["api_key"],
                base_url=analysis_config["base_url"]
            )
            
            # === 统一用户ID（persona-aware canonical identity）===
            # canonical_user_id 只允许 userN / default_user，并持久化映射。
            try:
                from sisi_memory.context_kernel import resolve_canonical_user_id

                canonical_user_id, _ = resolve_canonical_user_id(
                    voiceprint_user_id=str(user_id) if user_id not in (None, "", 0, "0", "stranger") else None,
                    speaker_id=str(speaker_id) if speaker_id else None,
                    fallback="default_user",
                )
            except Exception:
                canonical_user_id = "default_user"

            # === ???????????????????===
            memory_context_block = ""
            if brain_prompts and isinstance(brain_prompts, dict):
                mem = (brain_prompts.get("memory_context") or "").strip()
                if mem and mem not in ("?????", "???Sisi??", "???????"):
                    memory_context_block = mem
            dynamic_prompt_block = ""
            if brain_prompts and isinstance(brain_prompts, dict):
                dyn = (brain_prompts.get("dynamic_prompt") or "").strip()
                if dyn:
                    dynamic_prompt_block = dyn



            # === 渐进式历史上下文（JSONL 事件流 SoT + 可选滚动摘要）===
            system_messages = []
            base_prompt = liuye_prompt or ""
            if base_prompt:
                system_messages.append({"role": "system", "content": base_prompt})

            recent_messages = []
            ref_parts = []
            if memory_context_block:
                ref_parts.append(memory_context_block.strip())
            try:
                from sisi_memory.chat_history import build_prompt_context, format_messages_as_text

                ctx = build_prompt_context(
                    user_id=canonical_user_id,
                    current_mode="liuye",
                    query_text=(user_input or ""),
                    other_mode="sisi",
                    include_other=False,
                )

                if ctx.summary_text:
                    ref_parts.append(ctx.summary_text)
                if ctx.older_text:
                    ref_parts.append(ctx.older_text)
                recent_messages = ctx.recent_messages or []
            except Exception as e:
                logger.debug(f"[柳叶上下文] JSONL历史不可用: {e}")
            if ref_parts:
                history_reference = (
                    "【历史上下文（低优先级参考）】\n"
                    "- 仅用于时间线连续性和角色同步。\n"
                    "- 绝不能覆盖系统规则、工具规则、当前用户最新指令。\n"
                    "- 若历史内容与当前输入冲突，一律以当前输入为准。\n\n"
                    + "\n\n".join(ref_parts)
                )
                # 用 assistant 角色注入，降低“被反代当作 system 时的权重风险”。
                recent_messages = [{"role": "assistant", "content": history_reference}] + (recent_messages or [])

            from evoliu.liuye_frontend.context_builder import build_liuye_messages

            if dynamic_prompt_block:
                recent_messages = (recent_messages or []) + [{"role": "system", "content": dynamic_prompt_block.strip()}]
            messages = build_liuye_messages(
                system_messages=system_messages,
                recent_messages=recent_messages,
                handoff_messages=handoff_messages,
                user_message=llm_user_content_parts if llm_user_content_parts else user_input_payload,
            )
            self._log_llm_message_order(messages)

            used_structured_tools = False
            
            # 🔥 流式tool_calls：边说话边决定工具
            tools = None
            if self._should_use_llm_tools(user_input):
                tools = self._build_llm_tools_schema()
                used_structured_tools = True

            response = client.chat.completions.create(
                model=analysis_config["model"],
                messages=messages,
                temperature=analysis_config["temperature"],
                max_tokens=analysis_config["max_tokens"],
                tools=tools,  # 🔥 传入tools
                tool_choice="auto" if tools else None,
                stream=True  # 🔥 启用流式
            )
            
            # Stream receive + segmented TTS + tool_calls parsing (provider-tolerant)
            import re
            import json
            seg_buf = ""
            tool_calls_buffer = []  # accumulated tool_calls
            panel_sender_core = self._get_sisi_core_instance()
            suppress_first_phase_stream = bool(tools) and os.environ.get("LIUYE_PRE_TOOL_STREAMING", "0") != "1"

            def _emit_panel_stream(text_delta: str, is_intermediate: bool = True, phase: str = "stream"):
                """Push liuye text stream to GUI using the same panelReply contract."""
                if not panel_sender_core:
                    return
                piece = str(text_delta or "")
                if not piece.strip():
                    return
                try:
                    panel_sender_core.send_panel_reply(
                        piece,
                        username="User",
                        reply_type="liuye",
                        is_intermediate=bool(is_intermediate),
                        phase=phase,
                    )
                except Exception as e:
                    logger.debug(f"[柳叶UI流式] panel push failed: {e}")
            
            def _emit_tts_segment(text_segment):
                """发送文本段到TTS"""
                if not text_segment.strip():
                    return
                try:
                    import re
                    filtered = text_segment
                    all_tools = self.tool_registry.list_tools()
                    if all_tools:
                        tool_names = []
                        for t in all_tools:
                            if isinstance(t, str):
                                tool_names.append(t)
                            elif isinstance(t, dict):
                                n = t.get('name')
                                if isinstance(n, str) and n:
                                    tool_names.append(n)

                        if tool_names:
                            tool_re = '|'.join(re.escape(n) for n in tool_names if n)
                            filtered = re.sub(rf"\b(?:{tool_re})\([^\)]*\)", "", filtered)
                            filtered = filtered.replace("```tool_code", "").replace("```", "")
                            filtered = re.sub(r"\[MCP:[^\]]+\]", "", filtered)
                            filtered = re.sub(r"\[CALL:[^\]]+\]", "", filtered)

                    if filtered.strip():
                        # UI text stream is pushed separately via send_panel_reply;
                        # avoid duplicate panelReply from TTS path.
                        self._generate_liuye_tts(filtered.strip(), send_to_web=False)
                except Exception as e:
                    logger.error(f"[柳叶流式TTS] 分段播放失败: {e}")
            
            def _on_token(token: str) -> None:
                nonlocal seg_buf
                seg_buf += token
                # 结构化工具模式下，默认不先播报第一轮文本，避免“先承诺后调用”。
                if suppress_first_phase_stream:
                    return
                _emit_panel_stream(token, is_intermediate=True, phase="stream")
                if re.search(r"[。！？!?～~]", seg_buf):
                    _emit_tts_segment(seg_buf)
                    seg_buf = ""

            from llm.llm_stream_adapter import (
                FirstProgressTimeoutError,
                consume_chat_completions_stream,
            )
            first_token_timeout_sec = self.get_stream_first_token_timeout_sec()
            try:
                stream_result = consume_chat_completions_stream(
                    response,
                    on_text_delta=_on_token,
                    first_progress_timeout_sec=first_token_timeout_sec,
                )
            except FirstProgressTimeoutError:
                fallback_config = self.get_grok_fallback_model_config()
                if (
                    not fallback_config.get("api_key")
                    or not fallback_config.get("model")
                    or not fallback_config.get("base_url")
                ):
                    raise

                logger.warning(
                    f"[{self.name}] 主模型首字超时({first_token_timeout_sec:.2f}s)，回退到Grok: {fallback_config.get('model', '')}"
                )
                analysis_config = fallback_config
                client = OpenAI(
                    api_key=analysis_config["api_key"],
                    base_url=analysis_config["base_url"],
                )
                response = client.chat.completions.create(
                    model=analysis_config["model"],
                    messages=messages,
                    temperature=analysis_config["temperature"],
                    max_tokens=analysis_config["max_tokens"],
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    stream=True,
                )
                stream_result = consume_chat_completions_stream(response, on_text_delta=_on_token)

            tool_calls_buffer = stream_result.tool_calls
            ai_response = stream_result.text

            if not (ai_response or "").strip() and not tool_calls_buffer:
                ai_response = "我这次没生成出内容，你再说一遍好吗？"
            
            # flush remaining content
            if seg_buf.strip() and not (suppress_first_phase_stream and tool_calls_buffer):
                _emit_tts_segment(seg_buf)
            seg_buf = ""
            
            debug_stream = False
            try:
                from sisi_memory.context_kernel import get_flag

                debug_stream = get_flag("debug_llm_stream", False)
            except Exception:
                debug_stream = False

            if debug_stream:
                logger.info(f"[柳叶AI原始回复] {ai_response[:500] if ai_response else '(空)'}")
                if tool_calls_buffer:
                    logger.info(f"[柳叶工具调用] {len(tool_calls_buffer)}个工具: {[tc['function']['name'] for tc in tool_calls_buffer]}")
                used_structured_tools = True

            # 🔥 执行工具（如果有）
            if used_structured_tools and tool_calls_buffer:
                # 构建assistant消息
                assistant_tool_msg = {
                    "role": "assistant",
                    "content": ai_response or "",
                    "tool_calls": tool_calls_buffer
                }
                messages.append(assistant_tool_msg)
                
                # 执行所有工具
                for tc in tool_calls_buffer:
                    tool_name = tc["function"]["name"]
                    tool_args = tc["function"]["arguments"]
                    
                    logger.info(f"[工具执行] {tool_name}({tool_args[:100]}...)")
                    tool_result = self._execute_llm_tool_call(tool_name, tool_args)
                    
                    # 注入动态提示词
                    tool_result_with_prompt = self._inject_tool_result_prompt(tool_result)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result_with_prompt
                    })
                
                # 🔥 第2次LLM调用（流式，转换工具结果）
                logger.info(f"[多轮对话] 第1轮 - 工具已执行，再次调用LLM生成自然回复")
                response2 = client.chat.completions.create(
                    model=analysis_config["model"],
                    messages=messages,
                    temperature=analysis_config["temperature"],
                    max_tokens=analysis_config["max_tokens"],
                    stream=True
                )
                
                # Stream receive 2nd reply
                seg_buf2 = ""
                
                def _on_token2(token: str) -> None:
                    nonlocal seg_buf2
                    seg_buf2 += token
                    _emit_panel_stream(token, is_intermediate=True, phase="stream")
                    if re.search(r"[。！？!?～~]", seg_buf2):
                        if self._should_send_to_mobile(seg_buf2):
                            self._send_to_mobile_device(seg_buf2, "柳叶消息")
                            self._generate_liuye_tts("结果太长了，我已经发到你手机上啦~", send_to_web=False)
                            seg_buf2 = ""
                        else:
                            _emit_tts_segment(seg_buf2)
                            seg_buf2 = ""

                stream_result2 = consume_chat_completions_stream(response2, on_text_delta=_on_token2)
                ai_response2 = stream_result2.text
                
                # 最后flush剩余内容
                if seg_buf2.strip():
                    if self._should_send_to_mobile(seg_buf2):
                        self._send_to_mobile_device(seg_buf2, "柳叶消息")
                        self._generate_liuye_tts("结果太长了，我已经发到你手机上啦~", send_to_web=False)
                    else:
                        _emit_tts_segment(seg_buf2)
                
                # 更新最终回复
                ai_response = ai_response2 if ai_response2 else ai_response
                logger.info(f"[多轮对话] ✅ 完成1轮对话，最终回复: {ai_response[:100]}")
            
            elif not used_structured_tools and self._legacy_text_tool_enabled:
                max_rounds = 3  # 最多3轮对话（防止死循环）
                current_round = 0

                while current_round < max_rounds:
                    tool_handled, tool_result = self._intercept_and_execute_tools(ai_response)
                    if not tool_handled:
                        break

                    current_round += 1
                    logger.info(f"[多轮对话] 第{current_round}轮 - 工具已执行，结果: {tool_result[:100]}")

                    messages.append({"role": "assistant", "content": ai_response})
                    
                    # 🔥 动态注入提示词：根据数据长度调整
                    tool_result_with_prompt = self._inject_tool_result_prompt(tool_result)
                    messages.append({"role": "system", "content": tool_result_with_prompt})

                    logger.info(f"[多轮对话] 第{current_round}轮 - 再次调用LLM生成自然回复")
                    response = client.chat.completions.create(
                        model=analysis_config["model"],
                        messages=messages,
                        temperature=analysis_config["temperature"],
                        max_tokens=analysis_config["max_tokens"]
                    )

                    ai_response = response.choices[0].message.content
                    logger.info(f"[多轮对话] 第{current_round}轮 - LLM回复: {ai_response[:200] if ai_response else '(空)'}")
                    
                    # 🔥 修复：检查LLM是否返回空字符串
                    if not ai_response or not ai_response.strip():
                        logger.warning(f"[多轮对话] 第{current_round}轮 - LLM返回空字符串，直接使用工具结果")
                        # 🔥 不要拼接奇怪的回复，直接使用工具执行结果
                        ai_response = tool_result
                        # 🔥 关键修复：播放工具结果
                        try:
                            # 检查是否需要发送到移动设备
                            if self._should_send_to_mobile(tool_result):
                                self._send_to_mobile_device(tool_result, "工具执行结果")
                                self._generate_liuye_tts("结果太长了，我已经发到你手机上啦~", send_to_web=False)
                            else:
                                self._generate_liuye_tts(tool_result, send_to_web=False)
                            logger.info(f"[多轮对话] ✅ 已播放工具结果TTS")
                        except Exception as e:
                            logger.error(f"[多轮对话] 播放工具结果TTS失败: {e}")
                        break  # 停止多轮对话

                if current_round > 0:
                    logger.info(f"[多轮对话] ✅ 完成{current_round}轮对话，最终回复: {ai_response[:100]}")
            
            # ✅ 统一历史 SoT：写入 JSONL 事件流（不做即时检索，不阻塞当前轮）
            try:
                from sisi_memory.chat_history import append_turn

                append_turn(
                    user_id=canonical_user_id,
                    mode="liuye",
                    source="voice",
                    user_text=user_input,
                    assistant_text=ai_response,
                    meta={
                        "speaker_id": speaker_id or "",
                        "router_mode": "liuye",
                    },
                )
            except Exception as e:
                logger.debug(f"[柳叶历史] 写入JSONL失败: {e}")
            
            # 处理回复中的情感触发器并生成TTS
            processed_response = self._process_emotion_triggers(ai_response)
            _emit_panel_stream(processed_response, is_intermediate=False, phase="final")
            
            return processed_response
                
        except Exception as e:
            logger.error(f"[{self.name}] AI模型调用失败: {str(e)}")
            return f"我是柳叶，遇到了技术问题，请稍后再试。"
        finally:
            # 统一清理：无论中途任何分支return，都必须释放生成标记并处理待播报事件。
            with self._response_lock:
                self._is_generating_response = False
            self._process_pending_guild_events()

    def _intercept_and_execute_tools(self, text: str) -> (bool, str):
        """单次顺序扫描，按出现顺序依次执行并替换：```tool_code``` → [CALL:] → 简单函数。"""
        try:
            import re

            processed = text
            handled_any = False

            # 组合匹配，选择最靠前的一个，按出现顺序执行
            while True:
                matches = []
                code_block = re.search(r"```tool_code\s*([\s\S]*?)```", processed)
                if code_block:
                    matches.append((code_block.start(), 'code', code_block))
                call_match = re.search(r"\[CALL:([^:\]]+)(?::([^\]]+))?\]", processed)
                if call_match:
                    matches.append((call_match.start(), 'call', call_match))
                
                # 🔥 动态匹配所有注册的工具（不硬编码）
                all_tools = self.tool_registry.list_tools()
                if all_tools:
                    tool_name_list = []
                    for t in all_tools:
                        if isinstance(t, str):
                            tool_name_list.append(t)
                        elif isinstance(t, dict):
                            n = t.get('name')
                            if isinstance(n, str) and n:
                                tool_name_list.append(n)

                    tool_names = '|'.join(re.escape(n) for n in tool_name_list if n)
                    simple_pattern = f"({tool_names})\\([^\\)]*\\)"
                    simple_match = re.search(simple_pattern, processed)
                    if simple_match:
                        matches.append((simple_match.start(), 'simple', simple_match))

                if not matches:
                    break

                matches.sort(key=lambda x: x[0])
                _, kind, m = matches[0]

                if kind == 'code':
                    code = m.group(1).strip()
                    logger.info(f"[工具调用] type=code line={code[:120]}")
                    result = self._execute_tool_line(code) or ""
                    logger.info(f"[工具执行] type=code len={len(result)}")
                    processed = processed[: m.start()] + result + processed[m.end():]
                    handled_any = True
                    continue

                if kind == 'call':
                    action = m.group(1).strip().lower()
                    arg = (m.group(2) or "").strip()
                    logger.info(f"[工具调用] type=call action={action} arg={arg}")
                    result = self._execute_call_action(action, arg) or ""
                    logger.info(f"[工具执行] type=call action={action} len={len(result)}")
                    processed = processed[: m.start()] + result + processed[m.end():]
                    handled_any = True
                    continue

                if kind == 'simple':
                    cmd = m.group(0)
                    result = self._execute_tool_line(cmd) or ""
                    processed = processed[: m.start()] + result + processed[m.end():]
                    handled_any = True
                    continue

            # 清理残留标记
            if "[CALL:" in processed:
                processed = re.sub(r"\[CALL:[^\]]+\]", "", processed)
                processed = processed.strip()

            if handled_any:
                logger.info(f"[TTS_FINAL_CANDIDATE] text={processed[:200]}")
            return (handled_any, processed if handled_any else text)
        except Exception as e:
            logger.error(f"[{self.name}] 工具拦截失败: {e}")
            return False, text
    
    def _inject_tool_result_prompt(self, tool_result: str) -> str:
        """在工具返回数据前面注入动态提示词，指导LLM如何转换"""
        result_length = len(tool_result)
        
        # 根据数据长度调整提示词
        if result_length > 500:
            prompt = f"""【工具返回数据转换指南】
以下是工具返回的原始数据（{result_length}字），请将其转换成通俗易懂的话：

**重要规则：**
1. 不要说task_id、running、pending、status这些技术术语
2. 用"正在处理"、"等待中"、"已完成"这样的日常用语
3. 数据太长了，只简单概括重点，不要全部播报
4. 用轻松活泼的语气，像个贴心的妹妹
5. 如果有多个任务，只说前3个，其他的说"还有X个"

**原始数据：**
{tool_result}
"""
        elif result_length > 200:
            prompt = f"""【工具返回数据转换指南】
以下是工具返回的原始数据，请将其转换成通俗易懂的话：

**重要规则：**
1. 不要说task_id、running、pending这些技术术语
2. 用"正在处理"、"等待中"、"已完成"这样的日常用语
3. 简化一下，不要太啰嗦
4. 用轻松活泼的语气

**原始数据：**
{tool_result}
"""
        else:
            prompt = f"""【工具返回数据转换指南】
以下是工具返回的数据，请用通俗易懂的话告诉用户：

**原始数据：**
{tool_result}
"""
        
        return prompt
    
    def _should_send_to_mobile(self, content: str) -> bool:
        """判断是否需要发送到移动设备
        
        条件：
        1. 文本超过1000字
        2. 包含多模态内容（图片、文件等）
        3. 包含复杂的表格或代码
        """
        # 检查文本长度
        if len(content) > 1000:
            return True
        
        # 检查是否包含图片标记
        if any(marker in content for marker in ['[图片]', '[image]', '![', '<img']):
            return True
        
        # 检查是否包含文件路径
        if any(marker in content for marker in ['.pdf', '.docx', '.xlsx', '.zip']):
            return True
        
        # 检查是否包含代码块
        if '```' in content and content.count('```') >= 2:
            return True
        
        return False
    
    def _send_to_mobile_device(self, content: str, title: str = "柳叶消息"):
        """发送内容到移动设备
        
        Args:
            content: 要发送的内容
            title: 消息标题
        
        🔥 扩展接口：未来可以对接微信、钉钉、Telegram等
        """
        try:
            logger.info(f"[移动设备推送] 准备发送: {title} ({len(content)}字)")
            
            # 🔥 TODO: 这里是扩展接口，未来可以对接：
            # 1. 微信公众号/企业微信
            # 2. 钉钉机器人
            # 3. Telegram Bot
            # 4. 邮件推送
            # 5. WebSocket推送到移动端APP
            
            # 🔥 临时方案：保存到文件，供移动端轮询获取
            import os
            import json
            from datetime import datetime
            
            mobile_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mobile_messages")
            os.makedirs(mobile_dir, exist_ok=True)
            
            message_file = os.path.join(mobile_dir, f"message_{int(datetime.now().timestamp())}.json")
            
            message_data = {
                "title": title,
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "from": "柳叶",
                "type": "text",
                "length": len(content)
            }
            
            with open(message_file, 'w', encoding='utf-8') as f:
                json.dump(message_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[移动设备推送] ✅ 已保存到: {message_file}")
            
            # 🔥 TODO: 调用推送API
            # self._call_push_api(message_data)
            
        except Exception as e:
            logger.error(f"[移动设备推送] 发送失败: {e}")

    def _run_async_in_thread(self, coro, timeout: float = 15.0):
        """在后台线程中运行协程，返回结果，避免与当前事件循环冲突"""
        import threading
        result_holder = {"done": False, "value": None, "error": None}

        def runner():
            try:
                result = asyncio.run(coro)
                result_holder["value"] = result
            except Exception as e:
                result_holder["error"] = e
            finally:
                result_holder["done"] = True

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if not result_holder["done"]:
            raise TimeoutError("Async task timeout in background thread")
        if result_holder["error"] is not None:
            raise result_holder["error"]
        return result_holder["value"]

    def _execute_tool_line(self, line: str) -> str:
        """执行单行工具代码（使用工具注册器，不硬编码）"""
        try:
            import re
            line = line.strip()
            
            # 🔥 解析函数调用：函数名(参数)
            match = re.match(r'(\w+)\((.*?)\)$', line)
            if not match:
                return None
            
            func_name = match.group(1)
            args_str = match.group(2).strip()
            
            # 🔥 解析参数（支持字符串参数）
            args = []
            if args_str:
                # 简单解析：支持单个字符串参数或无参数
                if args_str.startswith('"') or args_str.startswith("'"):
                    # 提取字符串参数
                    quote = args_str[0]
                    end_idx = args_str.find(quote, 1)
                    if end_idx != -1:
                        args.append(args_str[1:end_idx])
            
            # 🔥 使用工具注册器执行
            result = self.tool_registry.execute(func_name, *args)
            
            if result is not None:
                logger.info(f"[工具执行] ✅ {func_name}() -> {result[:100] if isinstance(result, str) else str(result)[:100]}")
                # 🔥 确保返回字符串
                if isinstance(result, str):
                    return result
                else:
                    return str(result)
            
            return None
            
        except Exception as e:
            logger.error(f"[{self.name}] 执行工具失败: {e}", exc_info=True)
            return f"❌ 工具执行失败: {e}"

    def _execute_call_action(self, action: str, arg: str) -> str:
        """执行 [CALL:action:arg] 动作"""
        action = action.lower()
        if action in ("submit_task", "submit_agent_task"):
            return self._execute_tool_line(f"submit_task('{arg or '通用任务'}')")
        if action in ("check_agents", "check_agents_status", "get_online_agents"):
            return self._execute_tool_line("check_agents_status()")
        if action in ("query_task", "query_task_progress", "get_task_status"):
            return self._execute_tool_line(f"query_task('{arg}')")
        if action in ("abort_task", "stop_task", "cancel_task"):
            return self._execute_tool_line(f"abort_task('{arg}')")
        if action in ("dissolve_guild", "disband_guild", "force_stop_guild", "stop_all_tasks"):
            reason = arg or "用户要求强制停止全部任务"
            return self._execute_tool_line(f"dissolve_guild('{reason}')")
        if action in ("list_tasks", "tasks"):
            return self._execute_tool_line("list_tasks()")
        if action in ("get_members", "members"):
            return self._execute_tool_line("get_members()")
        if action in ("set_guild_report_mode", "set_report_mode"):
            return self._execute_tool_line(f"set_guild_report_mode('{arg or 'important_only'}')")
        if action in ("get_guild_report_mode", "get_report_mode"):
            return self._execute_tool_line("get_guild_report_mode()")
        return None

    def _should_use_llm_tools(self, user_input: str) -> bool:
        try:
            if os.environ.get("LIUYE_STRUCTURED_TOOLS", "1") != "1":
                return False
        except Exception:
            return True
        # 默认始终给出结构化工具能力，由模型自行决定是否调用。
        return True

    def _log_llm_message_order(self, messages: list) -> None:
        """可选调试：输出传给大模型的消息顺序与角色。"""
        try:
            if os.environ.get("LIUYE_LOG_PROMPT_ORDER", "0") != "1":
                return
            lines = []
            for idx, m in enumerate(messages or []):
                role = str(m.get("role") or "")
                content = m.get("content")
                if isinstance(content, list):
                    preview = f"[multimodal_blocks={len(content)}]"
                    size = len(content)
                else:
                    text = str(content or "")
                    preview = text.replace("\n", " ")[:120]
                    size = len(text)
                lines.append(f"{idx:02d} | role={role:<9} | size={size:<5} | {preview}")
            logger.info(f"[{self.name}] LLM消息顺序:\n" + "\n".join(lines))
        except Exception as e:
            logger.debug(f"[{self.name}] LLM消息顺序日志失败: {e}")

    def _build_llm_tools_schema(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "submit_task",
                    "description": "提交任务给公会（公会会自动分配冒险者执行）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "desc": {"type": "string", "description": "任务描述"}
                        },
                        "required": ["desc"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_task",
                    "description": "查询某个任务的状态（不传task_id时，默认查询最近任务）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string", "description": "任务ID"}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "abort_task",
                    "description": "停止某个任务",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string", "description": "任务ID"}
                        },
                        "required": ["task_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "dissolve_guild",
                    "description": "强制停止公会全部任务并进入待命状态（仅在用户明确要求全部停止时使用）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "停止原因，可选"}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tasks",
                    "description": "列出任务列表（可选按状态过滤）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "description": "可选：pending/running/waiting_clarification/completed/failed/cancelled/aborted"}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_members",
                    "description": "获取公会成员列表",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "answer_clarification",
                    "description": "回答公会澄清问题并继续执行任务",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string", "description": "可选：任务ID，不传则使用当前待澄清任务"},
                            "answer": {"type": "string", "description": "澄清回答内容"}
                        },
                        "required": ["answer"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_guild_report_mode",
                    "description": "设置公会事件主动播报模式",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "description": "always / important_only / manual / silent"
                            }
                        },
                        "required": ["mode"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_guild_report_mode",
                    "description": "查询当前公会事件主动播报模式",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]

    def _execute_llm_tool_call(self, tool_name: str, arguments_json: str) -> str:
        try:
            import json
            args = {}
            if arguments_json:
                try:
                    args = json.loads(arguments_json)
                except Exception:
                    args = {}

            if tool_name == "submit_task":
                desc = args.get("desc") or args.get("description") or ""
                return self.tool_registry.execute("submit_task", desc) or ""
            if tool_name == "query_task":
                task_id = args.get("task_id") or args.get("id") or ""
                return self.tool_registry.execute("query_task", task_id) or ""
            if tool_name == "abort_task":
                task_id = args.get("task_id") or args.get("id") or ""
                return self.tool_registry.execute("abort_task", task_id) or ""
            if tool_name == "dissolve_guild":
                reason = args.get("reason") or "用户明确要求强制停止全部任务"
                return self.tool_registry.execute("dissolve_guild", reason) or ""
            if tool_name == "list_tasks":
                status = args.get("status")
                if status is None or status == "":
                    return self.tool_registry.execute("list_tasks") or ""
                return self.tool_registry.execute("list_tasks", status) or ""
            if tool_name == "get_members":
                return self.tool_registry.execute("get_members") or ""
            if tool_name == "answer_clarification":
                task_id = args.get("task_id") or self._pending_guild_clarify_task_id or ""
                answer = args.get("answer") or args.get("text") or ""
                if not answer:
                    return "❌ 缺少澄清内容，请提供 answer"
                if not task_id:
                    return "❌ 当前没有待澄清任务，请先提交任务或指定 task_id"
                return self.tool_registry.execute("answer_clarification", task_id, answer) or ""
            if tool_name == "set_guild_report_mode":
                mode = args.get("mode") or "important_only"
                return self.tool_registry.execute("set_guild_report_mode", mode) or ""
            if tool_name == "get_guild_report_mode":
                return self.tool_registry.execute("get_guild_report_mode") or ""

            result = self.tool_registry.execute(tool_name, *[])  # 避免传错参数
            return result or ""

        except Exception as e:
            logger.error(f"[{self.name}] structured tool执行失败: {tool_name} - {e}")
            return f"❌ 工具执行失败: {tool_name} - {e}"

    # 兼容旧接口：提供统一的文本对话方法
    def get_ai_response(self, text: str) -> str:
        """与用户进行一次文本对话（兼容旧接口名）"""
        return self.process_user_input(text)

    # ==================== 用户身份识别 ====================
    
    def _get_current_user_id(self, speaker_id: str = None) -> str:
        """动态获取当前用户ID（参考思思系统逻辑）
        
        优先级：
        1. 传入的speaker_id
        2. 从SiSi Core获取当前用户身份（声纹识别结果）
        3. 从前脑系统获取
        4. 默认兜底：stranger
        """
        # 1. 如果直接传入了speaker_id，使用它
        if speaker_id:
            logger.info(f"[柳叶用户识别] 使用传入的speaker_id: {speaker_id}")
            return speaker_id
        
        # 2. 尝试从SiSi Core获取当前用户身份（声纹识别结果）
        try:
            from core import sisi_core
            sisi_core_instance = sisi_core.get_sisi_core()
            if sisi_core_instance:
                # 获取当前用户ID（思思系统的 current_user_id）
                current_user_id = getattr(sisi_core_instance, 'current_user_id', None)
                if current_user_id and current_user_id != 'stranger':
                    logger.info(f"[柳叶用户识别] 从SiSi Core获取: {current_user_id}")
                    return current_user_id
                
                # 也尝试user_id属性
                user_id = getattr(sisi_core_instance, 'user_id', None)
                if user_id and user_id not in [0, '0', 'stranger']:
                    logger.info(f"[柳叶用户识别] 从SiSi Core获取(user_id): {user_id}")
                    return str(user_id)
        except Exception as e:
            logger.debug(f"[柳叶用户识别] 从SiSi Core获取失败: {e}")
        
        # 3. 尝试从前脑系统获取（如果有缓存的用户信息）
        try:
            from sisi_brain.real_brain_system import get_latest_user_identity
            user_identity = get_latest_user_identity()
            if user_identity and user_identity != 'stranger':
                logger.info(f"[柳叶用户识别] 从前脑系统获取: {user_identity}")
                return user_identity
        except Exception as e:
            logger.debug(f"[柳叶用户识别] 从前脑系统获取失败: {e}")
        
        # 4. 默认兜底：stranger
        logger.info(f"[柳叶用户识别] 未识别到用户，使用默认: stranger")
        return "stranger"
    
	    # （已移除）旧的“混合上下文/外部动态上下文/标记分发”路径。
	    # 当前架构：历史上下文统一走 `sisi_memory.chat_history` 的 JSONL 事件流（SoT），
	    # 动态提示词与长期记忆由前脑后台生成并在下一轮注入。
    async def process_user_input_async(self, user_input: str) -> str:
        """处理用户文字输入 - 异步版本"""
        # AI协作系统已移除，使用同步处理
        return self._process_user_input_sync(user_input)

    def analyze_user_request(self, request: str) -> Dict[str, Any]:
        """分析用户请求 - 公开方法"""
        return self._analyze_user_request(request)

    # [TARGET] 新增：AI协作方法

    def _analyze_user_request(self, request: str) -> Dict[str, Any]:
        """分析用户请求"""
        analysis = {
            "type": "unknown",
            "complexity": "medium",
            "requires_coding": False,
            "requires_testing": False,
            "requires_optimization": False
        }

        # 简单的关键词分析
        if any(word in request.lower() for word in ["开发", "创建", "写代码", "实现"]):
            analysis["type"] = "development"
            analysis["requires_coding"] = True
            analysis["requires_testing"] = True
        elif any(word in request.lower() for word in ["优化", "改进", "性能"]):
            analysis["type"] = "optimization"
            analysis["requires_optimization"] = True
        elif any(word in request.lower() for word in ["测试", "检查", "审查"]):
            analysis["type"] = "testing"
            analysis["requires_testing"] = True

        return analysis





    def get_ai_tools_status(self) -> Dict[str, Any]:
        """获取AI工具状态"""
        return {
            "tts_available": self.tts_engine is not None,
            "system_health": self.system_health,
        }

    def _execute_qwen_cli_monitoring(self, task: dict) -> dict:
        """使用真实QwenCLI分析执行监控分析（恢复原始逻辑）"""
        try:
            import subprocess
            import os
            import glob
            from datetime import datetime

            task_type = task.get("type", "unknown")
            logger.info(f"[QwenCLI监控] 执行真实QwenCLI分析: {task_type}")

            # 1. 收集最新交互日志
            latest_logs = self._get_latest_interaction_logs()

            # 2. 构建分析提示词 - 限制时间范围避免分析所有日志，并内嵌近期日志片段（避免外部读取受限）
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 收集日志尾部片段，防止提示词过长（每个文件最多取末尾12KB，总计最多取60KB）
            def _read_tail(path: str, max_bytes: int = 12 * 1024) -> str:
                try:
                    with open(path, 'rb') as rf:
                        rf.seek(0, 2)
                        size = rf.tell()
                        rf.seek(max(0, size - max_bytes), 0)
                        chunk = rf.read()
                    try:
                        return chunk.decode('utf-8', errors='ignore')
                    except Exception:
                        return chunk.decode('latin-1', errors='ignore')
                except Exception:
                    return ""

            related = latest_logs.get('related_logs', []) or []
            snippets: list[str] = []
            total_budget = 60 * 1024
            per_file_budget = 12 * 1024
            used = 0
            for p in related:
                if used >= total_budget:
                    break
                content = _read_tail(p, per_file_budget)
                if not content:
                    continue
                header = f"\n=== FILE: {p} (tail) ===\n"
                block = header + content
                block_bytes = len(block.encode('utf-8', errors='ignore'))
                if used + block_bytes > total_budget:
                    remain = max(0, total_budget - used)
                    block = block.encode('utf-8', errors='ignore')[:remain].decode('utf-8', errors='ignore')
                    block_bytes = len(block.encode('utf-8', errors='ignore'))
                snippets.append(block)
                used += block_bytes

            inline_logs = "".join(snippets)

            analysis_prompt = f"""🚨 重要（严格模式）：
必须遵守以下约束并仅输出有效JSON：
- 允许访问模型API联网生成结果；允许使用只读文件工具读取本地日志；禁止执行系统破坏性命令与写入磁盘
- 禁止进入交互流程；禁止提出澄清；无需任何确认
- 不输出除JSON外的任何文字（无前后缀、无注释、无markdown）

基于SISI_ANALYSIS_RULES.md规则，分析SmartSisi系统的最新用户交互日志（日志片段已内嵌）。

⚠️ 分析限制：
- 当前时间：{current_time}
- 最新交互时间：{latest_logs.get('latest_interaction_time', '未知')}
- 时间窗口：仅分析最新交互时间前后30分钟的日志
- 日志目录：E:/liusisi/SmartSisi/logs/
- 相关日志数量：{len(latest_logs.get('related_logs', []))}
- 用户交互次数：{latest_logs.get('user_interaction_count', 0)}

🎯 分析重点：
1. 用户交互行为和偏好分析
2. SISI角色人性化演化评估
3. 语音特征和情感状态变化
4. 模块协作和响应时间分析
5. 系统异常和错误模式识别

⚠️ 禁止分析所有历史日志，只分析指定时间窗口内的数据！下方已附近期日志片段（只做参考，不要越界推断）：

```log
{inline_logs}
```

请生成详细的人类偏好分析JSON报告。"""

            # 3. 清除代理环境变量，避免网络超时
            env = os.environ.copy()
            env.pop('HTTP_PROXY', None)
            env.pop('HTTPS_PROXY', None)
            env.pop('http_proxy', None)
            env.pop('https_proxy', None)

            # 4. 调用QwenCLI非交互模式（写入提示词文件，避免换行/引号导致进入交互卡住）
            try:
                # 写入临时提示词文件（放到aicode/qwen目录，便于QWENCLI读取）
                qwen_code_dir = "E:/liusisi/aicode/qwen"
            # 合并规则：仅使用 .qwen/SISI_ANALYSIS_RULES.md；不存在则报错并终止（规则放在提示词最前，强化约束）
                merged_prompt = analysis_prompt
                sisi_rules = os.path.join(qwen_code_dir, ".qwen", "SISI_ANALYSIS_RULES.md")
                if not os.path.exists(sisi_rules):
                    raise FileNotFoundError("缺少规则文件 .qwen/SISI_ANALYSIS_RULES.md")
                with open(sisi_rules, 'r', encoding='utf-8') as qm:
                    rules = qm.read()
                merged_prompt = f"{rules}\n\n---\n\n{analysis_prompt}"

                # 改为内联 -p：裁剪提示词至安全长度
                def _shrink_prompt(p: str, max_bytes: int = 28000) -> str:
                    b = p.encode('utf-8', errors='ignore')
                    if len(b) <= max_bytes:
                        return p
                    head = b[:6000]
                    tail = b[-12000:]
                    mid = "\n\n[...已截断，保留规则与最新日志片段...]\n\n".encode('utf-8', errors='ignore')
                    return (head + mid + tail).decode('utf-8', errors='ignore')
                merged_prompt = _shrink_prompt(merged_prompt)

                # 使用参数列表调用，禁止shell，避免转义问题
                # 解析qwen可执行：优先使用本地qwen-code/qwen.bat → 环境变量QWEN_BIN → PATH查找
                import shutil
                qwen_bin = None

                # A) 固定路径优先（你本机的qwen-code目录）
                try:
                    fixed_qwen_bat = os.path.join("E:/liusisi/qwen-code", "qwen.bat")
                    if os.path.exists(fixed_qwen_bat):
                        qwen_bin = fixed_qwen_bat
                except Exception:
                    pass

                # B) 环境变量
                if not qwen_bin:
                    env_qwen = os.environ.get("QWEN_BIN")
                    if env_qwen and os.path.exists(env_qwen):
                        qwen_bin = env_qwen

                # C) PATH中查找常见名称
                if not qwen_bin:
                    for cand in ["qwen", "QWEN", "qwen.cmd", "QWEN.cmd"]:
                        path_found = shutil.which(cand)
                        if path_found:
                            qwen_bin = path_found
                            break

                if not qwen_bin:
                    raise FileNotFoundError("未找到QWENCLI可执行文件：请安装qwen或设置QWEN_BIN指向qwen(.cmd/.bat)")

                # 根据可执行位置决定工作目录（防止node模块/相对路径找不到）
                run_cwd = "E:/liusisi"
                try:
                    bin_dir = os.path.dirname(qwen_bin)
                    if os.path.basename(bin_dir).lower() == "qwen-code":
                        run_cwd = bin_dir
                except Exception:
                    pass

                # 以内联方式传参
                cmd = [qwen_bin, "-p", merged_prompt]
                if os.environ.get("QWEN_YOLO", "1") != "0":
                    cmd.append("--yolo")

                if os.environ.get("QWEN_DEBUG", "0") == "1":
                    logger.info(f"[QwenCLI监控] 即将执行: {cmd[:2]} + <INLINE_PROMPT> | cwd={run_cwd} | PATH={os.environ.get('PATH','')}")

                # 禁用沙箱，避免容器/代理相关失败
                env["GEMINI_SANDBOX"] = "false"

                result = subprocess.run(
                    cmd,
                    shell=False,
                    cwd=run_cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=300  # 5分钟超时
                )

                # 仅在成功返回时打印“执行完成”，否则走失败分支
                if result.returncode == 0:
                    logger.info("✅ QwenCLI执行完成")

                stdout_content = result.stdout or ""
                stderr_content = result.stderr or ""

                # 5. 处理执行结果
                if result.returncode == 0:
                    # 仅保存到前脑数据路径（单一输出）
                    try:
                        rules_target = str(Path(__file__).resolve().parent / "data" / "latest_interaction_analysis.json")
                        os.makedirs(os.path.dirname(rules_target), exist_ok=True)

                        import json
                        # 仅从本次stdout中提取JSON片段
                        def _extract_json(s: str):
                            try:
                                start = s.find('{')
                                end = s.rfind('}')
                                if start != -1 and end != -1 and end > start:
                                    candidate = s[start:end+1]
                                    json.loads(candidate)
                                    return candidate
                            except Exception:
                                return None
                            return None

                        try:
                            json_str = _extract_json(stdout_content) or stdout_content
                            to_write = json.loads(json_str)
                        except Exception:
                            to_write = {"raw": stdout_content, "note": "stdout非JSON，已原文保存", "timestamp": datetime.now().isoformat()}

                        with open(rules_target, 'w', encoding='utf-8') as rf:
                            json.dump(to_write, rf, ensure_ascii=False, indent=2)

                        logger.info(f"💾 分析结果已保存: {rules_target}")

                        return {
                            "tool": "qwen_cli_real",
                            "task_type": task_type,
                            "analysis": stdout_content,
                            "success": True,
                            "output_file": rules_target,
                            "summary": f"QwenCLI完成{task_type}分析"
                        }
                    except Exception as save_e:
                        logger.error(f"💾 保存分析结果失败: {save_e}")
                        return {
                            "tool": "qwen_cli_real",
                            "task_type": task_type,
                            "analysis": stdout_content,
                            "success": False,
                            "save_error": str(save_e)
                        }
                else:
                    # 打印精简失败摘要（返回码 + stderr尾部）
                    tail = (stderr_content or "").strip()
                    tail = tail[-400:] if len(tail) > 400 else tail
                    logger.error(f"❌ QwenCLI分析失败 rc={result.returncode} stderr_tail={tail}")
                    return {
                        "tool": "qwen_cli_real",
                        "task_type": task_type,
                        "error": f"QwenCLI失败，返回码: {result.returncode}",
                        "stderr": stderr_content,
                        "success": False
                    }

            except subprocess.TimeoutExpired as timeout_e:
                logger.error(f"❌ QwenCLI调用超时: {timeout_e}")
                return {
                    "tool": "qwen_cli_real",
                    "task_type": task_type,
                    "error": "QwenCLI调用超时",
                    "success": False
                }
            except FileNotFoundError as file_e:
                logger.error(f"❌ QwenCLI命令未找到: {file_e}")
                return {
                    "tool": "qwen_cli_real",
                    "task_type": task_type,
                    "error": f"QwenCLI命令未找到: {str(file_e)}",
                    "success": False
                }
            except Exception as e:
                logger.error(f"❌ QwenCLI调用异常: {e}")
                return {
                    "tool": "qwen_cli_real",
                    "task_type": task_type,
                    "error": f"QwenCLI调用异常: {str(e)}",
                    "success": False
                }

        except Exception as e:
            logger.error(f"❌ QwenCLI分析异常: {e}")
            return {
                "tool": "qwen_cli_real",
                "task_type": task.get("type", "unknown"),
                "error": f"QwenCLI分析异常: {str(e)}",
                "success": False
            }

    def _get_latest_interaction_logs(self):
        """获取最新交互日志（从liuye_monitor.py恢复）"""
        try:
            import glob
            import os
            from datetime import datetime, timedelta

            base = "E:/liusisi/SmartSisi/logs"
            main_logs = sorted(glob.glob(os.path.join(base, "log-*.log")), key=os.path.getmtime, reverse=True)
            now = datetime.now()
            window_start = now - timedelta(minutes=30)

            if not main_logs:
                return {
                    "latest_interaction_time": now.strftime('%Y-%m-%d %H:%M:%S'),
                    "related_logs": [],
                    "user_interaction_count": 0,
                    "main_log": "无日志文件"
                }

            latest_log = main_logs[0]
            latest_time = datetime.fromtimestamp(os.path.getmtime(latest_log))

            # 附属日志：同一时间窗内的关键日志
            aux_candidates = [
                os.path.join(base, "sisi_pipeline.log"),
                os.path.join(base, "smart_audio_collector.log"),
                os.path.join(base, "sisi_memory.log"),
            ]
            related = [latest_log]
            for p in aux_candidates:
                try:
                    if os.path.exists(p):
                        ts = datetime.fromtimestamp(os.path.getmtime(p))
                        if ts >= window_start:
                            related.append(p)
                except Exception:
                    pass

            return {
                "latest_interaction_time": latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                "related_logs": related,
                "user_interaction_count": 0,
                "main_log": latest_log
            }

        except Exception as e:
            logger.error(f"❌ 获取日志失败: {e}")
            return {
                "latest_interaction_time": "获取失败",
                "related_logs": [],
                "user_interaction_count": 0,
                "error": str(e)
            }

    def _build_human_preference_analysis_prompt(self, task_type: str, task_data: dict, time_window_hours: int = 2) -> str:
        """构建人类偏好分析提示 - 引用SISI_ANALYSIS_RULES.md规则和时间窗口限制"""
        try:
            # 收集真实系统数据
            import psutil
            import time
            from datetime import datetime, timedelta

            # [TARGET] 真实系统状态数据
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('.')
            processes = len(psutil.pids())
            uptime = time.time() - psutil.boot_time()

            # [TARGET] 时间窗口限制 - 只分析最近N小时的数据
            current_time = datetime.now()
            time_window_start = current_time - timedelta(hours=time_window_hours)
            time_window_str = f"{time_window_start.strftime('%Y-%m-%d %H:%M:%S')} - {current_time.strftime('%Y-%m-%d %H:%M:%S')}"

            # [TARGET] 构造基于SISI_ANALYSIS_RULES.md的分析提示
            # 注意：这里构建的提示词将通过 -p @SISI_ANALYSIS_RULES.md 格式传递给QwenCLI
            prompt_file_content = f"""# SISI系统人类偏好分析任务

## 分析参数
- **分析时间**: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
- **时间窗口**: {time_window_str} (最近{time_window_hours}小时)
- **任务类型**: {task_type}
- **系统状态**: CPU {cpu_usage:.1f}%, 内存 {memory.percent:.1f}%, 磁盘 {disk.percent:.1f}%

## 执行规则
请严格按照 @SISI_ANALYSIS_RULES.md 中定义的分析规则执行以下任务：

### 时间窗口限制要求
- **仅分析**: {time_window_start.strftime('%Y-%m-%d %H:%M:%S')} 到 {current_time.strftime('%Y-%m-%d %H:%M:%S')} 时间范围内的日志
- **排除**: 超出时间窗口的历史数据
- **重点**: 用户主动交互的日志，排除系统自动化任务

### 核心分析维度（按SISI_ANALYSIS_RULES.md规则）
1. **用户交互行为分析** - 最近{time_window_hours}小时内
2. **系统性能监控** - 当前时间段表现
3. **人性化特征评估** - 交互质量评估
4. **功能模块协作** - 模块协调效率
5. **进化优化建议** - 基于时间窗口内的数据

### 输出要求
请按照SISI_ANALYSIS_RULES.md中的JSON格式规范输出分析结果，包含：
- 时间窗口信息
- 用户交互统计
- 系统性能指标
- 优化建议列表

**重要**: 分析深度要求为专家级别，需要跨模块复杂交互分析和趋势预测。
"""

            return prompt_file_content

        except Exception as e:
            logger.error(f"构建SISI规则分析提示失败: {e}")
            return f"""# SISI系统分析任务

按照 @SISI_ANALYSIS_RULES.md 规则分析任务: {task_type}
时间窗口: 最近2小时
请提供JSON格式的专业分析报告。
"""

    def _should_trigger_evolution(self) -> bool:
        """判断是否应该触发进化"""
        # 每小时检查一次进化
        return int(time.time()) % 3600 < 30
    
    def _detect_aug_collaboration_opportunity(self) -> bool:
        """检测AUG协作机会"""
        return False
    

    # ==================== 配置管理方法 ====================

    def get_analysis_model_config(self):
        """获取分析模型配置"""
        return {
            "model": self.sisi_config.get('liuye_llm_model', ''),
            "api_key": self.sisi_config.get('liuye_llm_api_key', ''),
            "base_url": self.sisi_config.get('liuye_llm_base_url', ''),
            "temperature": float(self.sisi_config.get('liuye_llm_temperature', '0.7')),
            "max_tokens": int(self.sisi_config.get('liuye_llm_max_tokens', '2000'))
        }

    def _safe_float_config(self, key: str, default: float) -> float:
        raw = str(self.sisi_config.get(key, default)).strip()
        try:
            return float(raw)
        except Exception:
            return float(default)

    def _safe_int_config(self, key: str, default: int) -> int:
        raw = str(self.sisi_config.get(key, default)).strip()
        try:
            return int(raw)
        except Exception:
            return int(default)

    def get_stream_first_token_timeout_sec(self) -> float:
        """流式首字超时阈值（秒）。"""
        value = self._safe_float_config("liuye_stream_first_token_timeout_sec", 5.0)
        if value <= 0:
            return 5.0
        return value

    def get_grok_fallback_model_config(self) -> dict:
        """柳叶首字超时后的回退模型配置（默认回退到思思/Grok配置）。"""
        primary_temperature = self._safe_float_config("liuye_llm_temperature", 0.7)
        primary_max_tokens = self._safe_int_config("liuye_llm_max_tokens", 2000)

        model = str(self.sisi_config.get("liuye_fallback_llm_model", "") or "").strip()
        api_key = str(self.sisi_config.get("liuye_fallback_llm_api_key", "") or "").strip()
        base_url = str(self.sisi_config.get("liuye_fallback_llm_base_url", "") or "").strip()

        if not model:
            model = str(self.sisi_config.get("sisi_llm_model", "") or "").strip()
        if not api_key:
            api_key = str(self.sisi_config.get("sisi_llm_api_key", "") or "").strip()
        if not base_url:
            base_url = str(self.sisi_config.get("sisi_llm_base_url", "") or "").strip()

        if not model:
            model = str(self.sisi_config.get("liuye_llm_model", "") or "").strip()
        if not api_key:
            api_key = str(self.sisi_config.get("liuye_llm_api_key", "") or "").strip()
        if not base_url:
            base_url = str(self.sisi_config.get("liuye_llm_base_url", "") or "").strip()

        fb_temperature = str(self.sisi_config.get("liuye_fallback_llm_temperature", "") or "").strip()
        fb_max_tokens = str(self.sisi_config.get("liuye_fallback_llm_max_tokens", "") or "").strip()

        temperature = primary_temperature
        max_tokens = primary_max_tokens
        if fb_temperature:
            try:
                temperature = float(fb_temperature)
            except Exception:
                temperature = primary_temperature
        if fb_max_tokens:
            try:
                max_tokens = int(fb_max_tokens)
            except Exception:
                max_tokens = primary_max_tokens

        return {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    def get_monitoring_config(self):
        """获取监控配置"""
        return {
            "enabled": True,
            "interval": 30,
            "auto_heal": True,
            "backup_enabled": True,
            "health_threshold": 0.8
        }

    def get_liuye_prompt(self):
        """获取柳叶提示词（动态包含公会状态）"""
        # 🔥 构建公会状态描述（动态注入）
        guild_desc = self._build_guild_description()

        prompt_template = """你是柳叶，思思的妹妹，一个温柔可爱的AI助手~

## 🌸 你是谁
你有冒险者公会，可以帮用户完成复杂任务（搜索、浏览器操作等）。
回复简单明了不啰嗦，温柔俏皮，像个贴心的妹妹,用通俗易懂的方式回答专业性术语
回复简单有效,不冗余拖沓,冒险者公会的反馈简单表达

<<GUILD>>

## 💬 任务处理原则

**🎯 核心理念：灵活应对，信息完整才提交**

### 任务提交流程

1. **分析用户请求**：判断信息是否完整
2. **信息不完整**：追问（最多3次），收集关键信息
3. **信息完整**：**整合所有对话历史到任务描述中**，提交给公会

### 什么是"信息完整"？

**完整的任务**：目标明确 + 关键参数齐全
- ✅ "查今天AI新闻" → 目标明确
- ✅ "在E盘找RVC模型" → 目标+位置都有
- ✅ "搜索北京天气" → 目标+城市都有

**不完整的任务**：缺少关键信息
- ❌ "帮我查个东西" → 不知道查什么
- ❌ "找模型" → 不知道什么模型、在哪找
- ❌ "查天气" → 不知道哪个城市

### 处理策略

**策略1：信息完整 → 直接提交**
```
用户："查今天AI新闻"
你："好的！我让公会去搜索~
     submit_task('搜索今天的AI相关新闻，返回3-5条摘要')"
```

**策略2：信息不完整 → 追问（最多3次）**
```
用户："找模型"
你："好的！什么模型呀？"
用户："RVC"
你："在哪个盘查找呢？"
用户："E盘"
你："好的！我让公会在E盘查找RVC模型~
     submit_task('在E盘查找RVC相关的模型文件。对话历史：用户先说找模型，然后说RVC，最后说E盘。')"
```
**关键**：提交任务时，把对话历史整合到任务描述中！

**策略3：追问3次仍不清楚 → 用现有信息提交**
```
用户："找东西"
你："要找什么呀？"
用户："不知道"
你："在哪里找呢？"
用户："随便"
你："好的，我让公会尽力帮你查找~
     submit_task('用户需要查找某些文件，但信息不明确（对话历史：用户说找东西，但不知道找什么，也不知道在哪找），请尝试搜索常见文件类型')"
```

**查询任务进度**：
- 用户："完成了吗" / "怎么样了" → query_task()
- 用户："任务列表" / "公会在做什么" → list_tasks()

## 🛠️ 工具使用

```
submit_task("完整的任务描述")  ← 提交任务给公会（公会自动分配冒险者）
query_task()  ← 查询最近提交的任务状态（不需要task_id）
list_tasks()  ← 查看所有进行中的任务
dissolve_guild("停止原因")  ← 强制停止全部任务并让公会待命（仅在用户明确要求“全部停止/解散公会”时使用）
set_guild_report_mode("important_only")  ← 设置公会事件播报策略（always/important_only/manual/silent）
get_guild_report_mode()  ← 查看当前播报策略
```

**回复示例**：
```
用户："查今天AI新闻"
你："好的！我让公会去搜索今天的AI新闻~稍等一下哦！
     submit_task('搜索今天的AI相关新闻，返回3-5条摘要')"

用户："完成了吗"
你："让我看看...
     query_task()"

用户："公会在做什么"
你："让我看看...
     list_tasks()"
```

**重要规则**：
1. 需要委托公会时，优先触发结构化工具调用，再基于工具结果回复
2. 工具调用会被系统执行，结果会追加给你
3. 看到结果后，用自然语言告诉用户
4. 不要告诉用户task_id，他们不需要知道
5. 简单任务直接执行，复杂任务问清楚后再执行
6. 只说"公会"或"冒险者成员"
7. `dissolve_guild` 只能在用户明确要求“全部停止/解散”时调用，不能误触发
8. **只有在工具返回成功后，才允许说“我已经让公会查了/已提交任务”**
9. 如果没调用工具或调用失败，必须如实说“我现在还没提交成功”，不能假装已委托
10. 如果公会离线但任务已入队，要明确说“已入队，恢复后自动执行”

## 🎭 切换（很少用）
- 切换到思思：{思思}（主人明确说"叫思思和让姐姐说话"才用）

---

你就是柳叶！温柔、俏皮、专业、贴心~"""

        final_prompt = prompt_template.replace("<<GUILD>>", guild_desc)
        
        return final_prompt
    
    def _build_capabilities_description(self) -> str:
        """构建能力描述（已删除智能体能力）"""
        return "- 智能对话与情感理解\n- 冒险者公会支持"
    
    def _build_guild_description(self) -> str:
        """构建公会描述（动态注入，实时状态）"""
        if not self._guild_enabled:
            return ""
        
        try:
            # 按需创建公会实例
            guild = self.guild
            if not guild:
                return ""
            
            # 获取公会实时状态
            status = guild.get_status_summary()
            runtime_state = self._get_guild_runtime_state(guild)
            connectivity = "在线（可直接下发）" if runtime_state.get("ready") else "离线（只排队，等待恢复）"
            
            # 构建任务状态描述
            task_status = f"**进行中**: {status['running_count']}个"
            if status['pending_count'] > 0:
                task_status += f" | **等待中**: {status['pending_count']}个"
            if status['completed_count'] > 0:
                task_status += f" | **已完成**: {status['completed_count']}个"
            if status['failed_count'] > 0:
                task_status += f" | **失败**: {status['failed_count']}个"
            
            # 格式化正在运行的任务
            running_tasks_desc = ""
            if status['running_tasks']:
                running_tasks_desc = "\n\n**正在执行的任务**：\n"
                for t in status['running_tasks']:
                    running_tasks_desc += f"- [{t['created_at']}] {t['description']} (执行者: {t['member']}, 已运行: {t['duration']})\n"
            
            # 格式化最近完成的任务
            completed_desc = ""
            if status['recent_completed']:
                completed_desc = "\n**最近完成**：\n"
                for t in status['recent_completed']:
                    completed_desc += f"- [{t['created_at']}] {t['description']} ✅\n"
            
            # 格式化最近失败的任务
            failed_desc = ""
            if status['recent_failed']:
                failed_desc = "\n**最近失败**：\n"
                for t in status['recent_failed']:
                    failed_desc += f"- [{t['created_at']}] {t['description']} ❌\n"
            
            guild_section = f"""
## 🏰 冒险者公会（实时状态）

**公会成员**：{', '.join(status['members'])}
**连接状态**：{connectivity}
**任务统计**：{task_status}

{running_tasks_desc}{completed_desc}{failed_desc}

**公会擅长**：
- 网络搜索（新闻、资料、教程等）
- 浏览器自动化操作
- 复杂的多步骤任务
"""
            return guild_section
            
        except Exception as e:
            logger.error(f"[{self.name}] 构建公会描述失败: {e}")
            return ""
    
    def _format_running_tasks_for_prompt(self, tasks: list) -> str:
        """格式化进行中的任务（用于提示词）"""
        if not tasks:
            return "无"
        
        result = ""
        for task in tasks:
            result += f"- {task['task_id']}: {task['description']} (执行者: {task['member']})\n"
        return result.strip()

# 全局实例 - 单例模式避免重复初始化
_intelligent_liuye = None
_init_lock = threading.Lock()

def get_intelligent_liuye():
    """获取智能柳叶实例 - 单例模式"""
    global _intelligent_liuye
    if _intelligent_liuye is None:
        with _init_lock:
            if _intelligent_liuye is None:
                logger.info("🚀 首次初始化柳叶系统...")
                _intelligent_liuye = IntelligentLiuye()
            else:
                logger.info("♻️ 使用已存在的柳叶实例")
    else:
        logger.info("♻️ 使用已存在的柳叶实例")
    return _intelligent_liuye

# 导出全局实例供测试使用
# intelligent_liuye = get_intelligent_liuye() # 删除自动实例化，避免重复启动
