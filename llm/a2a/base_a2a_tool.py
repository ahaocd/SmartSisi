"""
标准A2A工具基类 - 实现A2A协议规范，统一任务状态管理

提供完整的任务生命周期管理，确保所有工具符合A2A规范
支持标准SSE流式响应格式
"""

import uuid
import time
import logging
import asyncio
import json
from typing import Dict, Any, Optional, Union, List, Literal, AsyncIterable, AsyncGenerator, Callable, Set
from datetime import datetime
from dataclasses import dataclass, field, asdict

# 配置统一日志记录
logger = logging.getLogger("A2ABaseTool")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(name)s] [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

@dataclass
class TaskStatusEvent:
    """任务状态更新事件，用于SSE流式输出"""
    task_id: str
    status: str = "working"  # working, completed, failed, canceled
    message: Dict[str, Any] = field(default_factory=dict)
    final: bool = False
    
    def to_json(self) -> str:
        """将状态事件转换为JSON字符串"""
        return json.dumps(asdict(self), ensure_ascii=False)
    
    @staticmethod
    def create_working(task_id: str, message: str) -> 'TaskStatusEvent':
        """创建一个工作中的状态事件"""
        return TaskStatusEvent(
            task_id=task_id,
            status="working",
            message={"parts": [{"type": "text", "text": message}]},
            final=False
        )
    
    @staticmethod
    def create_completed(task_id: str, message: str) -> 'TaskStatusEvent':
        """创建一个完成的状态事件"""
        return TaskStatusEvent(
            task_id=task_id,
            status="completed",
            message={"parts": [{"type": "text", "text": message}]},
            final=True
        )
    
    @staticmethod
    def create_failed(task_id: str, error_message: str) -> 'TaskStatusEvent':
        """创建一个失败的状态事件"""
        return TaskStatusEvent(
            task_id=task_id,
            status="failed",
            message={"parts": [{"type": "text", "text": f"错误: {error_message}"}]},
            final=True
        )

class StandardA2ATool:
    """
    A2A协议标准工具基类，提供统一的任务状态管理和API接口
    
    所有A2A工具应继承此基类，并重写process_query方法
    """
    
    def __init__(self, name: str, description: str, version: str = "1.0.0"):
        """初始化标准A2A工具
        
        Args:
            name: 工具名称
            description: 工具描述
            version: 工具版本
        """
        self.name = name
        self.description = description
        self.version = version
        self.task_states = {}  # 存储任务状态 {task_id: {status, created_at, updated_at, query, result}}
        self.subscribers = {}  # 存储任务订阅者 {task_id: [queue1, queue2, ...]}
        self.lock = asyncio.Lock()  # 用于保护共享数据访问
        
    def create_task(self, query: str) -> str:
        """创建任务并设置初始状态
        
        Args:
            query: 用户查询
            
        Returns:
            str: 任务ID
        """
        task_id = str(uuid.uuid4())
        self.task_states[task_id] = {
            "status": "submitted",  # 使用A2A规范的状态名称
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "query": query,
            "result": None
        }
        self.subscribers[task_id] = set()
        logger.info(f"[{self.name}] 创建任务: {task_id}")
        return task_id
    
    async def update_task_state(self, task_id: str, status: str, content: Any = None, is_final: bool = False):
        """更新任务状态并通知订阅者
        
        Args:
            task_id: 任务ID
            status: 状态 (submitted, working, input-required, completed, canceled, failed)
            content: 结果或中间内容
            is_final: 是否最终状态
        """
        # 使用锁保护并发访问
        async with self.lock:
            if task_id in self.task_states:
                # 更新内存中的状态
                self.task_states[task_id].update({
                    "status": status,
                    "updated_at": datetime.now().isoformat()
                })
                
                if content is not None:
                    self.task_states[task_id]["result"] = content
                
                logger.info(f"[{self.name}] 更新任务 {task_id} 状态: {status}")
                
                # 创建状态事件对象
                event = TaskStatusEvent(
                    task_id=task_id,
                    status=status,
                    message={"parts": [{"type": "text", "text": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False) if content else None}]},
                    final=is_final
                )
                
                # 通知所有订阅者
                if task_id in self.subscribers and self.subscribers[task_id]:
                    for callback in self.subscribers[task_id]:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                # 创建一个任务来异步调用回调，但不等待它完成
                                asyncio.create_task(callback(task_id, status, content))
                            else:
                                callback(task_id, status, content)
                        except Exception as e:
                            logger.error(f"[{self.name}] 通知订阅者出错: {str(e)}")
            else:
                logger.warning(f"[{self.name}] 尝试更新不存在的任务: {task_id}")
    
    def get_task_state(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务状态信息
        """
        return self.task_states.get(task_id, {"status": "unknown"})
    
    async def subscribe_task(self, task_id: str, callback: Callable) -> bool:
        """订阅任务状态更新
        
        Args:
            task_id: 任务ID
            callback: 当任务状态变化时要调用的函数
            
        Returns:
            bool: 订阅是否成功
        """
        async with self.lock:
            if task_id not in self.subscribers:
                self.subscribers[task_id] = set()
            
            if callback in self.subscribers[task_id]:
                logger.info(f"[{self.name}] 重复订阅任务: {task_id}")
                return True
            
            self.subscribers[task_id].add(callback)
            logger.info(f"[{self.name}] 添加订阅: {task_id}")
            return True
    
    async def unsubscribe_task(self, task_id: str, callback: Callable) -> bool:
        """取消订阅任务状态更新
        
        Args:
            task_id: 任务ID
            callback: 先前注册的回调函数
            
        Returns:
            bool: 取消订阅是否成功
        """
        async with self.lock:
            if task_id not in self.subscribers:
                logger.warning(f"[{self.name}] 取消订阅失败，任务不存在: {task_id}")
                return False
            
            if callback not in self.subscribers[task_id]:
                logger.warning(f"[{self.name}] 取消订阅失败，回调函数不存在: {task_id}")
                return False
            
            self.subscribers[task_id].remove(callback)
            logger.info(f"[{self.name}] 移除订阅: {task_id}")
            return True
    
    async def process_query(self, query: str) -> str:
        """处理查询的具体实现 (需要子类重写)
        
        Args:
            query: 用户查询
            
        Returns:
            str: 处理结果
        """
        raise NotImplementedError("子类必须实现process_query方法")
    
    async def process_query_stream(self, query: str, task_id: str) -> AsyncGenerator[TaskStatusEvent, None]:
        """流式处理查询，发送中间状态 (子类可重写以提供更好的流式体验)
        
        此默认实现会调用process_query并返回结果
        子类可以重写此方法实现真正的流式处理
        
        Args:
            query: 用户查询
            task_id: 任务ID
            
        Yields:
            TaskStatusEvent: 流式处理的中间状态
        """
        try:
            # 发送处理中状态
            await self.update_task_state(task_id, "working", f"开始处理查询: {query[:30]}..." if len(query) > 30 else query)
            yield TaskStatusEvent.create_working(task_id, f"开始处理查询: {query[:30]}..." if len(query) > 30 else query)
            
            # 调用标准处理方法
            result = await self.process_query(query)
            
            # 发送完成状态
            await self.update_task_state(task_id, "completed", result, is_final=True)
            yield TaskStatusEvent.create_completed(task_id, result)
            
        except Exception as e:
            error_msg = f"处理查询时出错: {str(e)}"
            logger.error(f"[{self.name}] {error_msg}")
            
            # 发送错误状态
            await self.update_task_state(task_id, "failed", error_msg, is_final=True)
            yield TaskStatusEvent.create_failed(task_id, error_msg)
    
    async def ainvoke(self, query: Any, stream: bool = False) -> Any:
        """A2A异步调用接口
        
        Args:
            query: 用户查询，可以是字符串或包含查询和上下文的字典
            stream: 是否使用流式模式返回中间结果
            
        Returns:
            If stream=False, return str: 处理结果
            If stream=True, return AsyncIterable[TaskStatusEvent]: 状态更新流
        """
        logger.info(f"[{self.name}] 异步调用: {str(query)[:50]}..." if len(str(query)) > 50 else f"[{self.name}] 异步调用: {query}")
        
        try:
            # 标准化查询格式
            clean_query = self._normalize_query(query)
            
            # 创建任务
            task_id = self.create_task(clean_query)
            
            # 更新状态为处理中
            await self.update_task_state(task_id, "working")
            
            if stream:
                return self.process_query_stream(clean_query, task_id)
            else:
                # 处理查询
                result = await self.process_query(clean_query)
                
                # 更新状态为完成
                await self.update_task_state(task_id, "completed", result, is_final=True)
                
                logger.info(f"[{self.name}] 任务 {task_id} 完成")
                return result
            
        except Exception as e:
            logger.error(f"[{self.name}] 处理查询异常: {str(e)}")
            
            # 如果有活跃任务，更新状态为错误
            if 'task_id' in locals():
                await self.update_task_state(task_id, "failed", f"处理出错: {str(e)}", is_final=True)
                
            if stream:
                return self.process_query_stream(clean_query, task_id)
            else:
                return f"处理查询时出错: {str(e)}"
    
    def invoke(self, query: Any) -> str:
        """A2A同步调用接口
        
        Args:
            query: 用户查询，可以是字符串或包含查询和上下文的字典
            
        Returns:
            str: 处理结果
        """
        logger.info(f"[{self.name}] 同步调用: {str(query)[:50]}..." if len(str(query)) > 50 else f"[{self.name}] 同步调用: {query}")
        
        # 使用事件循环运行异步方法
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.ainvoke(query))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 同步调用事件循环异常: {str(e)}")
            return f"处理查询时出错: {str(e)}"
    
    async def ainvoke_stream(self, query: Any) -> AsyncIterable[TaskStatusEvent]:
        """A2A异步流式调用接口
        
        Args:
            query: 用户查询，可以是字符串或包含查询和上下文的字典
            
        Returns:
            AsyncIterable[TaskStatusEvent]: 状态更新流
        """
        logger.info(f"[{self.name}] 异步流式调用: {str(query)[:50]}..." if len(str(query)) > 50 else f"[{self.name}] 异步流式调用: {query}")
        
        try:
            # 标准化查询格式
            clean_query = self._normalize_query(query)
            
            # 创建任务
            task_id = self.create_task(clean_query)
            
            # 订阅任务状态更新
            await self.subscribe_task(task_id, lambda task_id, status, content: None)
            logger.info(f"[{self.name}] 已订阅任务状态更新: {task_id}")
            
            try:
                # 启动处理任务
                process_task = asyncio.create_task(
                    self.process_query_stream(clean_query, task_id)
                )
                
                # 从队列接收状态更新，直到最终状态
                while True:
                    try:
                        # 等待状态更新，设置超时防止无限等待
                        event = await asyncio.wait_for(process_task, timeout=30)
                        
                        # 转换为A2A标准格式并返回
                        yield event
                        
                        # 如果是最终状态，结束循环
                        if event.final:
                            logger.info(f"[{self.name}] 收到最终状态，结束流式传输: {task_id}")
                            break
                            
                    except asyncio.TimeoutError:
                        # 检查处理任务是否仍在运行
                        if process_task.done():
                            logger.warning(f"[{self.name}] 处理任务已完成但未收到最终状态事件: {task_id}")
                            # 发送一个最终状态
                            if process_task.exception():
                                error = str(process_task.exception())
                                final_event = TaskStatusEvent.create_failed(task_id, f"处理出错: {error}")
                            else:
                                result = process_task.result()
                                if isinstance(result, list) and result:
                                    final_content = result[-1]  # 取最后一个元素作为结果
                                else:
                                    final_content = result
                                final_event = TaskStatusEvent.create_completed(task_id, final_content)
                            
                            yield final_event
                            break
                        else:
                            # 任务仍在运行，发送心跳事件
                            logger.info(f"[{self.name}] 发送心跳事件: {task_id}")
                            heartbeat = TaskStatusEvent.create_working(task_id, "处理中...")
                            yield heartbeat
            finally:
                # 取消订阅
                await self.unsubscribe_task(task_id, lambda task_id, status, content: None)
                logger.info(f"[{self.name}] 已取消订阅任务: {task_id}")
        
        except Exception as e:
            logger.error(f"[{self.name}] 流式处理异常: {str(e)}")
            # 创建错误事件
            error_event = TaskStatusEvent.create_failed("unknown", f"流式处理出错: {str(e)}")
            yield error_event
    
    async def get_sse_response(self, query: Any) -> AsyncIterable[str]:
        """获取SSE格式的响应流
        
        Args:
            query: 用户查询
            
        Yields:
            str: SSE格式的响应行
        """
        # 发送SSE响应头（需要由外部HTTP服务器设置）
        # Content-Type: text/event-stream
        # Cache-Control: no-cache
        # Connection: keep-alive
        
        try:
            # 标准化查询
            clean_query = self._normalize_query(query)
            
            # 创建任务
            task_id = self.create_task(clean_query)
            
            # 订阅任务状态更新
            await self.subscribe_task(task_id, lambda task_id, status, content: None)
            
            try:
                # 启动处理任务
                process_task = asyncio.create_task(
                    self.process_query_stream(clean_query, task_id)
                )
                
                # 从队列接收状态更新，直到最终状态
                while True:
                    try:
                        # 等待状态更新，设置超时防止无限等待
                        event = await asyncio.wait_for(process_task, timeout=30)
                        
                        # 转换为SSE格式并返回
                        yield event.to_json()
                        
                        # 如果是最终状态，结束循环
                        if event.final:
                            break
                            
                    except asyncio.TimeoutError:
                        # 检查处理任务是否仍在运行
                        if process_task.done():
                            # 处理任务已完成但未收到最终状态事件
                            if process_task.exception():
                                error = str(process_task.exception())
                                final_event = TaskStatusEvent.create_failed(task_id, f"处理出错: {error}")
                            else:
                                try:
                                    result = process_task.result()
                                    if isinstance(result, list) and result:
                                        final_content = result[-1]  # 取最后一个元素作为结果
                                    else:
                                        final_content = result
                                    final_event = TaskStatusEvent.create_completed(task_id, final_content)
                                except Exception as result_error:
                                    final_event = TaskStatusEvent.create_failed(task_id, f"获取结果出错: {str(result_error)}")
                            
                            yield final_event.to_json()
                            break
                        else:
                            # 任务仍在运行，发送心跳事件
                            heartbeat = TaskStatusEvent.create_working(task_id, "处理中...")
                            yield heartbeat.to_json()
                
                # 发送结束标记
                yield "event: done\ndata: {}\n\n"
                
            finally:
                # 取消订阅
                await self.unsubscribe_task(task_id, lambda task_id, status, content: None)
        
        except Exception as e:
            logger.error(f"[{self.name}] SSE响应生成异常: {str(e)}")
            # 创建错误事件
            error_event = TaskStatusEvent.create_failed("unknown", f"SSE响应生成出错: {str(e)}")
            yield error_event.to_json()
            # 发送结束标记
            yield "event: done\ndata: {}\n\n"
    
    def _normalize_query(self, query: Any) -> str:
        """标准化查询格式
        
        Args:
            query: 原始查询，可能是字符串、JSON字符串或字典
            
        Returns:
            str: 标准化后的查询字符串
        """
        if isinstance(query, str):
            # 尝试解析JSON字符串
            if query.strip().startswith('{'):
                try:
                    data = json.loads(query)
                    if isinstance(data, dict) and 'query' in data:
                        return data['query']
                except:
                    pass
            return query
        
        elif isinstance(query, dict):
            # 从字典中提取查询
            if 'query' in query:
                return query['query']
            elif 'text' in query:
                return query['text']
            else:
                return str(query)
        
        # 默认转换为字符串
        return str(query)
    
    def get_capabilities(self) -> List[str]:
        """获取工具能力列表 (子类可重写)
        
        Returns:
            List[str]: 能力列表
        """
        return ["基础查询处理", "流式处理", "SSE响应"]
    
    def get_examples(self) -> List[str]:
        """获取工具示例列表 (子类可重写)
        
        Returns:
            List[str]: 示例列表
        """
        return ["示例查询"] 