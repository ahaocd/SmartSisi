"""
A2A标准通知管理器 - 基于A2A协议实现工具间通信

提供以下功能：
1. 标准A2A任务发送与接收
2. 基于任务订阅的事件分发机制
3. 兼容A2A协议的通知处理
"""

import json
import asyncio
import time
import threading
import uuid
import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Union, Coroutine

# 配置日志
logger = logging.getLogger("a2a_notification")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(name)s] [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# A2A工具管理器单例
_tool_manager = None
_tool_manager_lock = threading.Lock()

# 添加消息队列机制和等待重试函数
_pending_messages = {}  # 存储未发送成功的消息: {target_tool: [messages]}
_pending_messages_lock = threading.Lock()

class A2AToolManager:
    """标准A2A工具管理器，处理工具注册和通信"""
    
    # 单例实例和锁
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        """确保只创建一个实例"""
        with cls._instance_lock:
            if cls._instance is None:
                logger.info("创建A2A工具管理器单例")
                cls._instance = super(A2AToolManager, cls).__new__(cls)
                # 标记是否已初始化
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化工具管理器(只在第一次创建时执行)"""
        if self._initialized:
            # 如果已经初始化过，则跳过
            return
            
        # 注册的工具
        self.tools = {}
        # 任务存储
        self.tasks = {}
        # 订阅关系
        self.subscriptions = {}
        # 事件循环
        self._loop = None
        # 运行状态
        self._running = False
        # 实例ID，用于调试
        self._instance_id = str(uuid.uuid4())[:8]
        
        # 标记为已初始化
        self._initialized = True
        
        logger.info(f"A2A工具管理器初始化完成 [实例ID: {self._instance_id}]")
    
    def get_all_subscriptions(self):
        """获取所有订阅信息，返回工具名和方法的映射"""
        result = {}
        
        # 遍历所有订阅，构建映射关系
        for tool_name, subscriptions in self.subscriptions.items():
            for subscription in subscriptions:
                sub_id = subscription.get("id")
                result[sub_id] = {
                    "tool_name": tool_name,
                    "method": subscription.get("method"),
                    "created_at": subscription.get("created_at")
                }
        
        return result
    
    def register_tool(self, tool_name: str, tool_instance: Any) -> bool:
        """注册工具实例"""
        if tool_name in self.tools:
            logger.warning(f"工具 {tool_name} 已存在，将被覆盖")
        
        self.tools[tool_name] = tool_instance
        logger.info(f"工具 {tool_name} 注册成功")
        return True
    
    def get_tool(self, tool_name: str) -> Any:
        """获取工具实例"""
        return self.tools.get(tool_name)

    def start(self):
        """启动工具管理器"""
        if self._running:
            # 🎯 优化：减少重复启动的日志噪音
            logger.debug(f"工具管理器[实例ID: {self._instance_id}]已经在运行中")
            return

        # 设置运行状态
        self._running = True

        # 创建事件循环线程
        def run_event_loop():
            """在新线程中运行事件循环"""
            try:
                logger.info(f"工具管理器[实例ID: {self._instance_id}]开始创建事件循环")
                
                # 创建新的事件循环
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                
                # 添加关闭事件处理
                def shutdown_handler():
                    logger.info(f"工具管理器[实例ID: {self._instance_id}]事件循环关闭")
                    # 确保其他任务有机会完成
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()
                
                self._loop.set_exception_handler(lambda loop, context: 
                    logger.error(f"事件循环异常: {context['message']} - {context.get('exception', '未知异常')}"))
                
                # 启动事件循环
                logger.info(f"工具管理器[实例ID: {self._instance_id}]事件循环启动")
                self._loop.run_forever()
                
            except Exception as e:
                self._running = False
                logger.error(f"事件循环异常: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                logger.info(f"工具管理器[实例ID: {self._instance_id}]事件循环已退出")
                if self._loop and self._loop.is_running():
                    self._loop.stop()
                if self._loop and not self._loop.is_closed():
                    self._loop.close()

        # 创建并启动线程
        thread = threading.Thread(target=run_event_loop, daemon=True, name=f"a2a-manager-{self._instance_id}")
        thread.start()

        logger.info(f"工具管理器[实例ID: {self._instance_id}]已启动")
        
        # 确保启动过程完成
        time.sleep(0.1)

    def stop(self):
        """停止工具管理器"""
        if not self._running:
            return

        self._running = False

        if self._loop:
            self._loop.stop()

        logger.info("A2A工具管理器已停止")
    
    def send_task(self, source_tool: str, target_tool: str, method: str, params: Dict[str, Any]) -> str:
        """发送标准A2A任务"""
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 构建标准A2A任务
        task = {
            "id": task_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "source": source_tool,
            "target": target_tool,
            "timestamp": datetime.now().isoformat()
        }
        
        # 存储任务
        self.tasks[task_id] = {
            "task": task,
            "status": "pending",
            "created_at": time.time()
        }
        
        # 分发任务给目标工具
        self._dispatch_task(task)
        
        logger.info(f"任务 {task_id} 从 {source_tool} 发送到 {target_tool}, 方法: {method}")
        return task_id
    
    def _dispatch_task(self, task: Dict[str, Any]) -> bool:
        """分发任务到目标工具"""
        try:
            target_tool = task.get("target")
            task_id = task.get("id")
            
            # 查找订阅者
            if target_tool in self.subscriptions:
                # 获取订阅方法列表
                subscriptions = self.subscriptions.get(target_tool, [])
                
                # 任务方法
                method = task.get("method", "")
                
                for subscription in subscriptions:
                    # 检查方法是否匹配
                    if subscription.get("method") == method or subscription.get("method") == "*":
                        # 获取回调函数
                        callback = subscription.get("callback")
                        if callback:
                            # 调用回调
                            if asyncio.iscoroutinefunction(callback):
                                # 异步回调
                                if self._loop:
                                    asyncio.run_coroutine_threadsafe(callback(task), self._loop)
                            else:
                                # 同步回调
                                callback(task)
                        
                        logger.info(f"任务 {task_id} 分发到 {target_tool} 的订阅者")
                return True
            
            logger.warning(f"目标工具 {target_tool} 未订阅方法 {task.get('method')}")
            return False

        except Exception as e:
            logger.error(f"分发任务异常: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def subscribe(self, tool_name: str, method: str, callback: Callable) -> str:
        """订阅任务方法"""
        if tool_name not in self.subscriptions:
            self.subscriptions[tool_name] = []
        
        # 🔧 检查是否已存在相同的订阅
        for existing_sub in self.subscriptions[tool_name]:
            if existing_sub.get("method") == method:
                logger.warning(f"工具 {tool_name} 已订阅方法 {method}，跳过重复订阅，现有订阅ID: {existing_sub.get('id')}")
                return existing_sub.get("id")
        
        # 生成订阅ID
        subscription_id = str(uuid.uuid4())
        
        # 添加订阅
        self.subscriptions[tool_name].append({
            "id": subscription_id,
            "method": method,
            "callback": callback,
            "created_at": time.time()
        })
        
        logger.info(f"工具 {tool_name} 订阅方法 {method}, 订阅ID: {subscription_id}")
        return subscription_id
    
    def unsubscribe(self, tool_name: str, subscription_id: str) -> bool:
        """取消订阅"""
        if tool_name not in self.subscriptions:
            logger.warning(f"工具 {tool_name} 没有任何订阅")
            return False

        # 查找订阅
        subscriptions = self.subscriptions[tool_name]
        for i, subscription in enumerate(subscriptions):
            if subscription.get("id") == subscription_id:
                # 移除订阅
                self.subscriptions[tool_name].pop(i)
                logger.info(f"工具 {tool_name} 取消订阅 {subscription_id}")
                return True

        logger.warning(f"未找到订阅 {subscription_id}")
        return False

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """获取任务详情"""
        return self.tasks.get(task_id, {}).get("task", {})
    
    def update_task_status(self, task_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> bool:
        """更新任务状态"""
        if task_id not in self.tasks:
            logger.warning(f"未找到任务 {task_id}")
            return False

        # 更新状态
        self.tasks[task_id]["status"] = status
        
        # 添加结果
        if result is not None:
            self.tasks[task_id]["result"] = result
        
        # 更新时间
        self.tasks[task_id]["updated_at"] = time.time()
        
        logger.info(f"任务 {task_id} 状态更新为 {status}")
        return True

    def cleanup_old_tasks(self, max_age_seconds: int = 3600) -> int:
        """清理旧任务"""
        current_time = time.time()
        tasks_to_remove = []
        
        # 查找超过最大年龄的任务
        for task_id, task_info in self.tasks.items():
            created_at = task_info.get("created_at", 0)
            if current_time - created_at > max_age_seconds:
                tasks_to_remove.append(task_id)
        
        # 移除任务
        for task_id in tasks_to_remove:
            del self.tasks[task_id]
        
        logger.info(f"清理了 {len(tasks_to_remove)} 个旧任务")
        return len(tasks_to_remove)

# 获取工具管理器单例并确保它已启动
def get_tool_manager() -> A2AToolManager:
    """获取工具管理器单例并确保它已启动"""
    # 直接使用A2AToolManager的单例机制
    manager = A2AToolManager()

    # 🎯 优化：只在真正需要时启动，避免重复日志
    if not manager._running:
        logger.info("工具管理器尚未启动，正在启动...")
        manager.start()
    # 🎯 移除重复的启动检查日志，减少噪音

    return manager

# 添加消息队列机制和等待重试函数
def add_to_pending_queue(source_tool, target_tool, method, params):
    """添加到待处理队列"""
    global _pending_messages
    with _pending_messages_lock:
        if target_tool not in _pending_messages:
            _pending_messages[target_tool] = []
        
        # 构建消息
        message = {
            "source": source_tool,
            "target": target_tool,
            "method": method,
            "params": params,
            "timestamp": time.time()
        }
        
        _pending_messages[target_tool].append(message)
        logger.info(f"消息已加入{target_tool}的待处理队列，当前队列长度: {len(_pending_messages[target_tool])}")
    
    # 触发队列处理器（如果尚未启动）
    ensure_queue_processor_running()

def ensure_queue_processor_running():
    """确保队列处理器正在运行"""
    global _queue_processor_thread
    
    with _pending_messages_lock:
        if not hasattr(ensure_queue_processor_running, "_queue_processor_thread") or \
           not ensure_queue_processor_running._queue_processor_thread or \
           not ensure_queue_processor_running._queue_processor_thread.is_alive():
            # 创建并启动新的处理线程
            ensure_queue_processor_running._queue_processor_thread = threading.Thread(
                target=process_pending_queue,
                daemon=True
            )
            ensure_queue_processor_running._queue_processor_thread.start()
            logger.info("已启动消息队列处理线程")

def process_pending_queue():
    """处理待发送队列中的消息"""
    logger.info("消息队列处理器已启动")
    retry_interval = 1  # 🔥 修复：减少初始重试间隔从2秒到1秒
    max_retry_interval = 10  # 🔥 修复：减少最大重试间隔从30秒到10秒

    # 消息跟踪集合 - 避免重复处理
    processed_message_ids = set()

    while True:
        try:
            with _pending_messages_lock:
                if not _pending_messages:
                    # 队列为空，休眠后继续检查
                    time.sleep(1)
                    continue
                
                # 复制一份队列数据进行处理，避免长时间锁定
                queue_copy = dict(_pending_messages)
            
            any_processed = False
            
            # 处理每个工具的队列
            for target_tool, messages in queue_copy.items():
                if not messages:
                    continue
                
                # 检查目标工具是否已订阅
                subscribed_methods = []
                try:
                    subs = check_subscriptions()
                    for sub_info in subs.get("details", {}).get(target_tool, []):
                        subscribed_methods.append(sub_info.get("method"))
                except Exception as e:
                    logger.error(f"检查订阅状态出错: {str(e)}")
                
                # 尝试发送每条消息
                with _pending_messages_lock:
                    remaining_messages = []
                    for msg in _pending_messages.get(target_tool, []):
                        # 生成消息ID用于跟踪
                        msg_id = f"{msg['source']}:{target_tool}:{msg['method']}:{hash(str(msg['params']))}"
                        
                        # 检查是否已处理过相同消息
                        if msg_id in processed_message_ids:
                            logger.warning(f"跳过重复消息: {msg_id}")
                            continue
                        
                        # 检查消息方法是否已被订阅
                        if msg["method"] in subscribed_methods or "*" in subscribed_methods:
                            # 尝试发送
                            try:
                                task_id = send_task(
                                    source_tool=msg["source"],
                                    target_tool=msg["target"],
                                    method=msg["method"],
                                    params=msg["params"]
                                )
                                if task_id:
                                    logger.info(f"成功从队列发送消息: {msg['source']} -> {msg['target']}, 方法: {msg['method']}")
                                    processed_message_ids.add(msg_id)  # 标记为已处理
                                    # 限制已处理集合大小
                                    if len(processed_message_ids) > 1000:
                                        processed_message_ids = set(list(processed_message_ids)[-500:])
                                    any_processed = True
                                    continue  # 发送成功，不添加到剩余消息
                            except Exception as e:
                                logger.error(f"从队列发送消息失败: {str(e)}")
                        
                        # 消息发送失败或方法未订阅，保留在队列中
                        age = time.time() - msg.get("timestamp", time.time())
                        retry_count = msg.get("retry_count", 0)
                        
                        # 根据重试次数计算最大存活时间
                        max_age = min(300 + (retry_count * 60), 3600)  # 最多保留1小时
                        
                        if age > max_age:  # 超过最大存活时间则丢弃
                            logger.warning(f"丢弃过期消息: {msg['source']} -> {msg['target']}, 方法: {msg['method']}, 存活: {age:.1f}秒, 重试次数: {retry_count}")
                        else:
                            # 增加重试次数
                            if not hasattr(msg, "retry_count"):
                                msg["retry_count"] = 0
                            msg["retry_count"] = retry_count + 1
                            remaining_messages.append(msg)
                    
                    # 更新队列
                    if remaining_messages:
                        _pending_messages[target_tool] = remaining_messages
                    else:
                        _pending_messages.pop(target_tool, None)
            
            # 根据处理状态调整重试间隔
            if any_processed:
                retry_interval = 1  # 🔥 修复：重置为1秒而不是2秒
            else:
                retry_interval = min(retry_interval * 1.2, max_retry_interval)  # 🔥 修复：减少增长倍数从1.5到1.2
            
            # 休眠指定时间后继续处理
            time.sleep(retry_interval)
            
        except Exception as e:
            logger.error(f"处理消息队列时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            time.sleep(5)  # 错误后稍微延迟



# 修改send_task函数，增加订阅检查和队列支持
def send_task(source_tool: str, target_tool: str, method: str, params: Dict[str, Any]) -> str:
    """发送任务给目标工具，如果目标未订阅则加入队列"""
    manager = get_tool_manager()
    
    # 检查目标工具是否已注册了订阅
    has_subscription = False
    if target_tool in manager.subscriptions:
        for sub in manager.subscriptions.get(target_tool, []):
            if sub.get("method") == method or sub.get("method") == "*":
                has_subscription = True
                break
    
    if not has_subscription:
        logger.warning(f"发送任务警告: 目标工具 {target_tool} 未订阅方法 {method}，加入队列")
        add_to_pending_queue(source_tool, target_tool, method, params)
        return f"queued_{uuid.uuid4().hex[:8]}"  # 返回队列ID
    
    task_id = manager.send_task(source_tool, target_tool, method, params)
    logger.info(f"发送任务: 从 {source_tool} 到 {target_tool}, 方法: {method}, ID: {task_id}")
    
    return task_id

# 模块级函数 - 订阅方法
def subscribe(tool_name: str, method: str, callback: Callable) -> str:
    """订阅特定方法的任务通知"""
    manager = get_tool_manager()
    logger.info(f"工具 {tool_name} 尝试订阅方法 {method}")
    
    # 检查工具是否已注册
    if tool_name not in manager.tools:
        logger.warning(f"订阅警告: 工具 {tool_name} 尚未在工具管理器中注册，正在自动注册空实例")
    
    subscription_id = manager.subscribe(tool_name, method, callback)
    
    # 输出当前订阅信息用于调试
    if tool_name in manager.subscriptions:
        subscription_count = len(manager.subscriptions.get(tool_name, []))
        logger.info(f"工具 {tool_name} 当前有 {subscription_count} 个订阅")
        
        # 列出所有订阅的方法
        methods = [sub.get("method") for sub in manager.subscriptions.get(tool_name, [])]
        logger.info(f"工具 {tool_name} 的订阅方法: {methods}")
    
    return subscription_id

# 模块级函数 - 取消订阅
def unsubscribe(tool_name: str, subscription_id: str) -> bool:
    """取消订阅"""
    tool_manager = get_tool_manager()
    return tool_manager.unsubscribe(tool_name, subscription_id)

# 模块级函数 - 获取任务详情
def get_task(task_id: str) -> Dict[str, Any]:
    """获取任务详情"""
    tool_manager = get_tool_manager()
    return tool_manager.get_task(task_id)

# 模块级函数 - 更新任务状态
def update_task_status(task_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> bool:
    """更新任务状态"""
    tool_manager = get_tool_manager()
    return tool_manager.update_task_status(task_id, status, result)

# 模块级函数 - 获取所有订阅
def get_all_subscriptions():
    """获取所有订阅信息"""
    tool_manager = get_tool_manager()
    return tool_manager.get_all_subscriptions()

# 以下是与中转站集成的函数，用于兼容现有代码
def send_notification_to_transit(content, source_tool, content_type="text", metadata=None):
    """
    发送通知到中转站（警告：此函数已被修改，只允许zudao工具直接发送通知）
    其他工具必须通过A2A订阅机制和搜索智能体
    """
    try:
        # 安全检查：只允许指定工具通过此方法直接发送通知
        if source_tool not in ["zudao_tool", "zudao", "bai_lian", "bailian_tool", "music_tool"]:
            logger.warning(f"拒绝直接通知: {source_tool} 未被授权使用直接通知路径，必须通过订阅站和搜索智能体")
            logger.info(f"建议使用标准A2A订阅机制: direct_tool_communication() 函数")
            return False
            
        # 使用统一的导入路径，确保获取同一个中转站实例
        import sys
        from pathlib import Path
        
        # 添加sisi模块根路径
        sisi_root = str(Path(__file__).parent.parent.parent.parent)
        if sisi_root not in sys.path:
            sys.path.insert(0, sisi_root)
            
        # 从Sisi包使用绝对导入
        from SmartSisi.llm.transit_station import get_transit_station
        transit = get_transit_station()
        
        # 记录使用的中转站实例ID，用于调试
        logger.info(f"获取全局中转站: 会话ID={transit.session_id}, SmartSisi核心状态={'已注册' if transit.sisi_core else '未注册'}")
        
        # 构建通知
        notification = {
            "content": content,
            "source_tool": source_tool,
            "content_type": content_type,
            "is_tool_notification": True,
            "metadata": metadata or {},
            "timestamp": time.time()
        }
        
        # 记录发送详情
        logger.info(f"准备发送授权工具通知到中转站: 源={source_tool}, 类型={content_type}, 内容长度={len(str(content))}")
        
        # 添加到中转站
        result = transit.add_intermediate_state(notification, source_tool)
        
        if result:
            logger.info(f"授权工具通知已成功发送到中转站: {source_tool}")
        else:
            logger.error(f"中转站拒绝了通知: {source_tool}")
            
        return result
    except Exception as e:
        logger.error(f"发送通知到中转站失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# 提供向下兼容的API，但内部使用标准A2A方法
def register_subscriber(subscriber_name, event_types, callback_function):
    """向下兼容的订阅注册函数，使用标准A2A方法"""
    # 转换事件类型为方法
    methods = []
    if event_types == "*":
        methods = ["*"]
    elif isinstance(event_types, list):
        methods = [f"event.{event_type}" for event_type in event_types]
    else:
        methods = [f"event.{event_types}"]
    
    # 创建适配器函数，将A2A任务转换为旧格式的事件
    def callback_adapter(task):
        # 转换A2A任务为旧格式事件
        event = {
            "id": task.get("id"),
            "type": task.get("method", "").replace("event.", ""),
            "data": task.get("params", {}),
            "source": task.get("source"),
            "timestamp": task.get("timestamp")
        }
        
        # 调用原回调
        return callback_function(event)
    
    # 注册订阅
    subscription_ids = []
    for method in methods:
        subscription_id = subscribe(subscriber_name, method, callback_adapter)
        subscription_ids.append(subscription_id)
    
    logger.info(f"注册订阅: {subscriber_name} -> {methods}")
    
    # 返回第一个订阅ID
    return subscription_ids[0] if subscription_ids else None

def direct_tool_communication(source_tool, target_tool, data, event_type="store_info"):
    """向下兼容的直接通信函数，使用标准A2A任务"""
    # 构建参数
    params = {
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    
    # 发送任务
    task_id = send_task(source_tool, target_tool, f"event.{event_type}", params)
    
    return task_id is not None

# 检查当前订阅
def check_subscriptions():
    """查看当前订阅状态"""
    tool_manager = get_tool_manager()
    
    # 添加调试信息，确保工具之间的正确通信
    subscribers_detail = {}
    for tool_name, subs in tool_manager.subscriptions.items():
        for sub in subs:
            subscribers_detail.setdefault(tool_name, []).append({
                "id": sub.get("id"),
                "method": sub.get("method"),
                "created_at": sub.get("created_at")
            })
    
    result = {
        "subscribers": list(tool_manager.subscriptions.keys()),
        "count": sum(len(subs) for subs in tool_manager.subscriptions.values()),
        "details": subscribers_detail,
        "tasks": {
            "total": len(tool_manager.tasks),
            "pending": sum(1 for task in tool_manager.tasks.values() if task.get("status") == "pending"),
            "completed": sum(1 for task in tool_manager.tasks.values() if task.get("status") == "completed")
        },
        "tools_registered": list(tool_manager.tools.keys())
    }
    
    return result

