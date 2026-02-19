#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
柳叶公会集成模块 - 工具注册器 + 事件总线
不硬编码，支持全时双工通信

参考架构：
- LangChain Tool 系统（工具注册）
- Redis Pub/Sub（事件总线）
- EventEmitter 模式（发布/订阅）
"""

import logging
import threading
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ==================== 工具注册器 ====================

class ToolRegistry:
    """工具注册器 - 动态注册和管理柳叶的工具"""
    
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        logger.info("[工具注册器] 初始化完成")
    
    def register(
        self, 
        name: str, 
        func: Callable, 
        description: str,
        category: str = "general",
        examples: list = None
    ):
        """动态注册工具
        
        Args:
            name: 工具名称（函数名）
            func: 工具函数
            description: 工具描述
            category: 工具分类（general/guild/agent/system等）
            examples: 使用示例
        """
        self._tools[name] = {
            "func": func,
            "description": description,
            "category": category,
            "examples": examples or []
        }
        logger.info(f"[工具注册器] ✅ 注册工具: {name} ({category})")
    
    def unregister(self, name: str):
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"[工具注册器] 注销工具: {name}")
    
    def execute(self, name: str, *args, **kwargs) -> Optional[str]:
        """执行工具
        
        Args:
            name: 工具名称
            *args, **kwargs: 工具参数
            
        Returns:
            工具执行结果（字符串）
        """
        if name not in self._tools:
            logger.warning(f"[工具注册器] 工具不存在: {name}")
            return None
        
        try:
            tool = self._tools[name]
            result = tool["func"](*args, **kwargs)
            logger.info(f"[工具注册器] ✅ 执行工具: {name}")
            return str(result) if result is not None else None
        except Exception as e:
            logger.error(f"[工具注册器] ❌ 执行工具失败: {name} - {e}")
            return f"❌ 工具执行失败: {e}"
    
    def get_tools_by_category(self, category: str = None) -> Dict[str, Dict]:
        """获取指定分类的工具"""
        if category is None:
            return self._tools
        
        return {
            name: tool 
            for name, tool in self._tools.items() 
            if tool["category"] == category
        }
    
    def get_prompt_section(self, category: str = None) -> str:
        """生成工具列表的提示词片段
        
        Args:
            category: 工具分类（None表示所有工具）
            
        Returns:
            提示词片段
        """
        tools = self.get_tools_by_category(category)
        
        if not tools:
            return ""
        
        prompt = ""
        for name, tool in tools.items():
            prompt += f"- **{name}()**: {tool['description']}\n"
            if tool['examples']:
                prompt += f"  示例: {tool['examples'][0]}\n"
        
        return prompt
    
    def list_tools(self) -> list:
        """列出所有工具"""
        return [
            {
                "name": name,
                "description": tool["description"],
                "category": tool["category"]
            }
            for name, tool in self._tools.items()
        ]


# ==================== 事件总线 ====================

class EventBus:
    """事件总线 - 支持发布/订阅模式（全时双工通信）"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._event_history: List[Dict] = []  # 保存最近100个事件
        self._max_history = 100
        logger.info("[事件总线] 初始化完成")
    
    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件
        
        Args:
            event_type: 事件类型（如 "task_progress", "task_completed"）
            callback: 回调函数，接收 data: dict 参数
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                logger.info(f"[事件总线] ✅ 订阅事件: {event_type}")
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)
                    logger.info(f"[事件总线] 取消订阅: {event_type}")
    
    def publish(self, event_type: str, data: dict):
        """发布事件（异步通知所有订阅者）
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        with self._lock:
            # 记录事件历史
            event_record = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            self._event_history.append(event_record)
            
            # 限制历史记录数量
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            
            # 获取订阅者列表（复制，避免回调中修改订阅列表）
            subscribers = self._subscribers.get(event_type, []).copy()
        
        # 在锁外执行回调（避免死锁）
        logger.info(f"[事件总线] 📢 发布事件: {event_type} -> {len(subscribers)}个订阅者")
        
        for callback in subscribers:
            try:
                # 在新线程中执行回调（避免阻塞）
                threading.Thread(
                    target=callback,
                    args=(data,),
                    daemon=True
                ).start()
            except Exception as e:
                logger.error(f"[事件总线] ❌ 事件回调失败: {event_type} - {e}")
    
    def get_event_history(self, event_type: str = None, limit: int = 10) -> List[Dict]:
        """获取事件历史
        
        Args:
            event_type: 事件类型（None表示所有事件）
            limit: 返回数量
            
        Returns:
            事件列表（最新的在前）
        """
        with self._lock:
            if event_type is None:
                history = self._event_history
            else:
                history = [e for e in self._event_history if e["type"] == event_type]
            
            return list(reversed(history[-limit:]))
    
    def clear_history(self):
        """清空事件历史"""
        with self._lock:
            self._event_history.clear()
            logger.info("[事件总线] 清空事件历史")
    
    def list_subscribers(self) -> Dict[str, int]:
        """列出所有订阅者"""
        with self._lock:
            return {
                event_type: len(callbacks)
                for event_type, callbacks in self._subscribers.items()
            }


# ==================== 全局单例 ====================

_tool_registry = None
_event_bus = None
_lock = threading.Lock()


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册器实例（单例）"""
    global _tool_registry
    if _tool_registry is None:
        with _lock:
            if _tool_registry is None:
                _tool_registry = ToolRegistry()
    return _tool_registry


def get_event_bus() -> EventBus:
    """获取全局事件总线实例（单例）"""
    global _event_bus
    if _event_bus is None:
        with _lock:
            if _event_bus is None:
                _event_bus = EventBus()
    return _event_bus


# ==================== 模块初始化 ====================

logger.info("[柳叶公会集成] 模块加载完成 - 工具注册器 + 事件总线已就绪")
