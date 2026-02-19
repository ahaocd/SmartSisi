"""
A2A适配器 - 连接LangGraph与A2A协议工具
"""

import json
import asyncio
import logging
import time
import requests
import traceback  # 添加traceback导入
import urllib.parse  # 添加URL编码模块
import aiohttp  # 添加aiohttp导入
from typing import Dict, List, Any, Optional, Union
from langchain_core.messages import BaseMessage, ToolMessage, AIMessage, HumanMessage
from langchain_core.tools import BaseTool
from utils import util
from llm.transit_station import TransitStation

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class A2ATool(BaseTool):
    """
    A2A工具封装 - 提供与LangChain/LangGraph兼容的工具接口
    """
    
    server_url: str = None  # 添加这个字段声明
    tool_name: str = None   # 添加这个字段声明
    full_url: str = None    # 添加这个字段声明
    task_id_from_server: Optional[str] = None # 新增字段存储来自服务器的task_id
    
    def __init__(self, name: str, description: str, server_url: str, tool_name: str):
        """
        初始化A2A工具
        
        Args:
            name: 工具名称
            description: 工具描述
            server_url: A2A服务器URL (例如: http://localhost:5050)
            tool_name: A2A工具名称 (例如: zudao)
        """
        # 先调用父类初始化
        super().__init__(
            name=name, 
            description=description, 
            return_direct=False
        )
        
        # URL编码工具名称，避免特殊字符问题
        encoded_tool_name = urllib.parse.quote(tool_name)
        
        # 然后设置自己的属性
        object.__setattr__(self, "server_url", server_url)
        object.__setattr__(self, "tool_name", tool_name)
        object.__setattr__(self, "full_url", f"{server_url}/a2a/invoke/{encoded_tool_name}")
        
        # 加载工具元数据
        self._load_metadata()
    
    def _load_metadata(self):
        """从A2A服务器加载工具元数据"""
        try:
            # URL编码工具名称
            encoded_tool_name = urllib.parse.quote(self.tool_name)
            metadata_url = f"{self.server_url}/a2a/tool/{encoded_tool_name}/metadata"
            response = requests.get(metadata_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                # 🔧 修复：支持两种格式
                # 格式1：{result: {name: ..., description: ...}}
                # 格式2：{name: ..., description: ...}
                if "result" in data:
                    metadata = data["result"]
                else:
                    metadata = data  # 直接使用返回的数据
                    
                # 更新工具描述
                if "description" in metadata:
                    self.description = metadata["description"]
                    logger.info(f"[A2ATool] 成功加载{self.tool_name}工具元数据")
            else:
                logger.warning(f"[A2ATool] 无法加载工具元数据 (HTTP {response.status_code}): {response.text}")
        except Exception as e:
            logger.warning(f"[A2ATool] 加载元数据失败 (工具仍可用): {repr(e)}")
    
    def _run(self, query: str = "") -> str:
        """
        执行A2A工具调用(同步版本)
        
        Args:
            query: 用户查询
            
        Returns:
            str: 工具执行结果
        """
        try:
            # 在已有事件循环环境下，避免阻塞主循环
            try:
                existing_loop = asyncio.get_running_loop()
            except RuntimeError:
                existing_loop = None

            if existing_loop and existing_loop.is_running():
                # 已有事件循环在运行，改为线程内启动临时循环
                result_container = {}
                def _runner():
                    loop = asyncio.new_event_loop()
                    try:
                        asyncio.set_event_loop(loop)
                        result_container['value'] = loop.run_until_complete(self._arun(query))
                    finally:
                        loop.close()
                import threading
                t = threading.Thread(target=_runner, daemon=True)
                t.start()
                t.join()
                return result_container.get('value', '')
            else:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(self._arun(query))
                finally:
                    loop.close()
        except Exception as e:
            logger.error(f"[A2ATool] 执行工具{self.name}时出错: {repr(e)}")
            # 使用traceback获取详细错误信息
            import traceback
            logger.error(f"[A2ATool] 详细错误: {traceback.format_exc()}")
            return f"工具执行出错: {str(e)}"
    
    async def _arun(self, query: str = "", **kwargs: Any) -> str:
        """
        异步调用A2A工具
        
        Args:
            query: 查询文本，可以为空字符串
            **kwargs: 可能包含 task_id_from_server
            
        Returns:
            str: 工具返回结果
        """
        logger.info(f"[A2ATool] 异步调用工具: {self.name}, 查询: {query[:30] if query else '空查询'}...")
        
        # 从kwargs获取task_id_from_server (如果存在)
        task_id_to_propagate = kwargs.get("task_id_from_server")
        if task_id_to_propagate:
            logger.info(f"[A2ATool] 将使用服务器提供的task_id进行传播: {task_id_to_propagate}")
        
        try:
            # 如果query为空，使用默认值
            if not query:
                if self.name == "location_weather":
                    query = "查询当前位置天气"
                elif self.name == "zudao":
                    query = "附近有什么"
                else:
                    query = "帮我查询"
            
            # 构造A2A请求
            payload_params = {
                "query": query
            }
            # 如果有来自服务器的 task_id，则将其添加到参数中传递给实际工具
            if task_id_to_propagate:
                payload_params["task_id"] = task_id_to_propagate
            
            payload = {
                "jsonrpc": "2.0",
                "method": "invoke",
                "params": payload_params,
                "id": f"call_{int(time.time())}"
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.full_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 检查是否返回了任务ID (异步模式)
                        if "result" in data and "task_id" in data["result"]:
                            task_id = data["result"]["task_id"]
                            status = data["result"].get("status", "PENDING")
                            async_mode = data["result"].get("async_mode", False)
                            notification_via = data["result"].get("notification_via", "")
                            message = data["result"].get("message", "")
                            
                            # 🔑 关键修复：正确处理WORKING状态 - 不直接返回，而是发送中间状态
                            if ((status == "SUBMITTED" or status == "WORKING") 
                                and async_mode and notification_via == "TransitStation"):
                                logger.info(f"[A2ATool] 检测到TransitStation异步模式工具: {self.tool_name}")
                                logger.info(f"[A2ATool] 任务状态: {status}, 任务ID: {task_id}")
                                
                                # 修复：WORKING状态发送到中转站作为中间状态，而不是直接返回
                                if status == "WORKING":
                                    try:
                                        from llm.transit_station import get_transit_station
                                        transit = get_transit_station()
                                        
                                        # 发送WORKING状态到中转站作为中间状态
                                        working_state = {
                                            "content": message,
                                            "source": f"工具处理中:{self.tool_name}",
                                            "timestamp": int(time.time() * 1000),
                                            "is_final": False  # 明确标记为非最终状态
                                        }
                                        transit.add_intermediate_state(working_state)
                                        logger.info(f"[A2ATool] 已发送WORKING状态到中转站，等待工具完成通知")
                                        
                                        # 检查任务状态，如果失败则返回失败信息
                                        if task_status == "failed":
                                            return f"工具{self.tool_name}执行失败，请稍后重试"
                                        else:
                                            return f"工具{self.tool_name}已启动，正在处理中..."
                                        
                                    except Exception as e:
                                        logger.error(f"[A2ATool] 发送WORKING状态到中转站失败: {str(e)}")
                                        # 失败时仍返回原始消息作为fallback
                                        return message
                                else:
                                    # SUBMITTED状态仍然直接返回
                                    logger.info(f"[A2ATool] 工具将通过TransitStation异步发送最终结果，无需轮询")
                                    return message
                        
                        # 处理成功响应
                        elif "result" in data:
                            if "message" in data["result"]:
                                return data["result"]["message"]
                            return str(data["result"])
                            
                        # 处理错误响应
                        elif "error" in data:
                            error_msg = f"工具调用失败: {data['error'].get('message', '未知错误')}"
                            logger.error(f"[A2ATool] {error_msg}")
                            return error_msg
                        
                        return str(data)
                    else:
                        error_msg = f"请求失败: HTTP {response.status}, {await response.text()}"
                        logger.error(f"[A2ATool] {error_msg}")
                        return error_msg
                        
        except Exception as e:
            error_msg = f"工具调用异常: {repr(e)}"
            logger.error(f"[A2ATool] {error_msg}")
            logger.debug(f"[A2ATool] 异常详情: {traceback.format_exc()}")
            return error_msg
    
    async def _poll_task_status(self, task_id: str, max_retries: int = 75, delay: float = 2.0) -> str:
        """
        轮询任务状态直到完成
        
        Args:
            task_id: 任务ID
            max_retries: 最大尝试次数
            delay: 每次轮询间隔(秒)
            
        Returns:
            str: 任务结果
        """
        import aiohttp
        
        # 确保task_id是字符串类型
        if isinstance(task_id, dict) and "task_id" in task_id:
            task_id = task_id["task_id"]
        
        # 转换为字符串
        task_id = str(task_id)
        
        # URL编码工具名称
        encoded_tool_name = urllib.parse.quote(self.tool_name)
        status_url = f"{self.server_url}/a2a/task/{encoded_tool_name}/{task_id}"
        
        logger.info(f"[A2ATool] 开始轮询任务状态: {task_id}, URL: {status_url}")
        
        retries = 0
        while retries < max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(status_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if "result" in data:
                                task_data = data["result"]
                                status = task_data.get("status")
                                
                                # 任务完成
                                if status == "completed":
                                    logger.info(f"[A2ATool] 轮询检测到任务完成: {task_id}")
                                    
                                    # 获取result字段
                                    if "result" in task_data:
                                        # 尝试提取message字段
                                        if isinstance(task_data["result"], dict) and "message" in task_data["result"]:
                                            result_content = task_data["result"]["message"]
                                        # 回退到整个result内容
                                        else:
                                            result_content = task_data["result"]
                                            
                                        # 将获取到的结果发送到中转站作为最终结果
                                        try:
                                            transit = TransitStation.get_instance()
                                            if not isinstance(result_content, str):
                                                result_content = json.dumps(result_content, ensure_ascii=False)
                                            
                                            # 发送最终结果到中转站，并标记为最终状态
                                            state = {
                                                "content": result_content,
                                                "source": f"工具完成:{self.tool_name}",
                                                "timestamp": int(time.time() * 1000),
                                                "is_final": True
                                            }
                                            transit.add_intermediate_state(state)
                                            logger.info(f"[A2ATool] 已将轮询结果作为最终状态发送到中转站")
                                        except Exception as transit_error:
                                            logger.error(f"[A2ATool] 发送轮询结果到中转站失败: {str(transit_error)}")
                                            
                                        return str(result_content)
                                        
                                    # 如果没有找到结果，返回默认信息
                                    return "任务完成，但没有返回结果"
                                
                                # 任务失败
                                elif status == "failed":
                                    error_msg = task_data.get('error', '未知错误')
                                    # 🔥 修复：工具失败时发送失败状态到中转站
                                    self._send_failed_status_to_transit(error_msg, self.tool_name)
                                    return f"任务失败: {error_msg}"
                                
                                # 工具正在运行
                                elif status == "working":
                                    # 任务还在运行，发送当前状态到中转站
                                    try:
                                        transit = TransitStation.get_instance()
                                        state_msg = {"state": "working", "task_id": task_id}
                                        transit.add_intermediate_state(
                                            json.dumps(state_msg), 
                                            f"工具运行中:{self.tool_name}"
                                        )
                                    except Exception as transit_error:
                                        logger.warning(f"[A2ATool] 发送运行状态到中转站失败: {str(transit_error)}")
                        
                        # 服务器返回错误
                        else:
                            error_text = await response.text()
                            logger.warning(f"[A2ATool] 轮询失败: HTTP {response.status}: {error_text[:100]}")
                
                # 轮询间隔
                await asyncio.sleep(delay)
                retries += 1
                
            except Exception as e:
                logger.error(f"[A2ATool] 轮询异常: {repr(e)}")
                await asyncio.sleep(delay)
                retries += 1
        
        return f"任务 {task_id} 轮询超时，请稍后通过任务ID查询结果"

    def _send_failed_status_to_transit(self, error_message: str, tool_name: str):
        """发送FAILED状态到中转站"""
        try:
            from llm.transit_station import get_transit_station
            transit = get_transit_station()

            # 发送FAILED状态到中转站
            failed_state = {
                "content": f"工具{tool_name}执行失败: {error_message}",
                "source": f"tool:{tool_name}:failed",
                "timestamp": int(time.time() * 1000),
                "is_final": True,
                "tool_failed": True  # 标记为工具失败
            }
            transit.add_intermediate_state(failed_state)
            logger.error(f"[A2ATool] 已发送FAILED状态到中转站: {tool_name} - {error_message}")

        except Exception as e:
            logger.error(f"[A2ATool] 发送FAILED状态到中转站失败: {str(e)}")

    async def _subscribe_task_sse(self, task_id):
        """订阅任务SSE事件流"""
        # 查找可用的SSE端点
        sse_endpoints = [
            f"/a2a/task/subscribe/{task_id}",
            f"/a2a/task/{self.tool_name}/subscribe/{task_id}"
        ]
        
        task_result = None
        
        logger.info(f"[A2ATool] 尝试通过SSE订阅获取任务结果: {task_id}")
        
        async with aiohttp.ClientSession() as session:
            for endpoint in sse_endpoints:
                sse_url = f"{self.server_url}{endpoint}"
                logger.info(f"[A2ATool] 尝试SSE连接: {sse_url}")
                
                try:
                    # 使用更灵活的超时设置
                    timeout = aiohttp.ClientTimeout(total=300, connect=10, sock_connect=10, sock_read=60)
                    
                    # 使用标准SSE头和备用组合
                    headers_options = [
                        {
                            "Accept": "text/event-stream",
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive"
                        },
                        {
                            "Accept": "text/event-stream, application/json",
                            "Cache-Control": "no-cache"
                        },
                        {"Accept": "*/*"},  # 最宽松的Accept头
                        {}  # 空headers作为最后的后备选项
                    ]
                    
                    for headers in headers_options:
                        logger.info(f"[A2ATool] 尝试SSE连接 {sse_url} 使用headers: {headers}")
                        
                        try:
                            async with session.get(sse_url, headers=headers, timeout=timeout) as response:
                                status = response.status
                                
                                if status == 200:
                                    logger.info(f"[A2ATool] SSE连接成功: {sse_url}, HTTP {status}")
                                    logger.info(f"[A2ATool] 响应头: {response.headers}")
                                    
                                    # 处理SSE流或其他响应
                                    task_result = await self._process_sse_stream(response, task_id)
                                    
                                    if task_result:
                                        logger.info(f"[A2ATool] SSE处理完毕，返回结果")
                                        return task_result
                                else:
                                    error_text = await response.text()
                                    logger.warning(f"[A2ATool] SSE连接失败: HTTP {status}, {error_text[:100]}...")
                        
                        except asyncio.TimeoutError as te:
                            logger.warning(f"[A2ATool] SSE连接超时: {str(te)}")
                            continue
                        except Exception as inner_e:
                            logger.warning(f"[A2ATool] SSE连接错误: {str(inner_e)}")
                            continue
                
                except Exception as e:
                    logger.error(f"[A2ATool] SSE连接异常: {str(e)}")
            
            # 如果所有SSE尝试都失败，尝试轮询方式获取结果
            logger.warning(f"[A2ATool] 所有SSE连接尝试均失败，尝试轮询方式")
            
        # 轮询方式获取任务结果
        result = await self._poll_task_status(task_id)
        logger.info(f"[A2ATool] 轮询获取结果: {result[:50] if result else 'None'}...")
        
        # 如果仍然没有结果，直接查询任务状态
        if not result or "轮询超时" in result:
            logger.warning(f"[A2ATool] 轮询失败，尝试直接查询任务状态")
            
            try:
                async with aiohttp.ClientSession() as session:
                    query_url = f"{self.server_url}/a2a/task/{self.tool_name}/{task_id}"
                    
                    async with session.get(query_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"[A2ATool] 直接查询任务成功: {json.dumps(data)[:100]}...")
                            
                            try:
                                content = self.extract_content_from_event(data)
                                if content:
                                    return content
                            except Exception as extract_error:
                                logger.error(f"[A2ATool] 直接查询提取内容出错: {str(extract_error)}")
            except Exception as query_error:
                logger.error(f"[A2ATool] 直接查询任务状态失败: {str(query_error)}")
        
        return result or f"任务 {task_id} 处理失败，无法获取结果"
    
    async def _process_sse_stream(self, response, task_id):
        """
        处理SSE数据流
        
        Args:
            response: SSE响应对象
            task_id: 任务ID
            
        Returns:
            str: 处理结果
        """
        # 检查内容类型并增强检测能力
        content_type = response.headers.get("Content-Type", "").lower()
        logger.info(f"[A2ATool] SSE响应内容类型: {content_type}")
        
        # 更灵活的SSE格式检测 - 多种可能的content-type变体
        sse_content_types = [
            "text/event-stream", 
            "application/x-ndjson",
            "application/stream+json",
            "application/json-seq"
        ]
        is_standard_sse = any(sse_type in content_type for sse_type in sse_content_types)
        
        # 检查是否是JSON但也可能包含SSE事件的情况
        is_json_response = "application/json" in content_type or "json" in content_type
        
        # 如果明确设置了text/event-stream但不包含在content_type中，检测是否有问题
        if not is_standard_sse and "event" in str(response.headers).lower():
            logger.warning(f"[A2ATool] 检测到潜在SSE响应但Content-Type不匹配: {content_type}")
            logger.warning(f"[A2ATool] 响应头中是否包含SSE相关信息: {'event' in str(response.headers).lower()}")
            logger.warning(f"[A2ATool] 完整响应头: {response.headers}")
            # 尝试强制按SSE格式处理
            try:
                # 检查一些响应内容以确定是否是SSE格式
                peek_content = await response.content.read(1024)
                response.content._buffer = peek_content + response.content._buffer
                peek_text = peek_content.decode('utf-8', errors='ignore')
                
                # 如果内容看起来像SSE格式(包含data:)，则强制按SSE处理
                if "data:" in peek_text or "event:" in peek_text:
                    logger.info(f"[A2ATool] 内容看起来像SSE格式，强制按SSE处理:")
                    logger.info(f"[A2ATool] 内容预览: {peek_text[:100]}")
                    is_standard_sse = True
            except Exception as e:
                logger.error(f"[A2ATool] 尝试检测SSE内容时出错: {str(e)}")
        
        # 如果响应是标准的SSE格式(或被强制识别为SSE)
        if is_standard_sse:
            logger.info(f"[A2ATool] 检测到SSE格式，开始处理事件流")
            return await self._process_standard_sse(response, task_id)
        
        # 如果是JSON格式的响应但包含完成的任务数据，可能是直接返回的完整任务状态
        if is_json_response:
            try:
                # 读取少量响应内容检查格式
                peek_content = await response.content.read(1024)
                response.content._buffer = peek_content + response.content._buffer
                peek_text = peek_content.decode('utf-8', errors='ignore')
                
                # 检查是否包含任务完成状态相关的关键词
                if ('state":"completed"' in peek_text or '"final":true' in peek_text or 
                    'COMPLETED' in peek_text or 'artifacts' in peek_text):
                    logger.info(f"[A2ATool] 检测到可能是已完成任务的JSON响应，处理为非SSE格式")
                    logger.info(f"[A2ATool] JSON响应预览: {peek_text[:200]}")
                    # 这里不是标准SSE流，但包含完整的任务状态，以非标准方式处理
                    return await self._process_non_standard_response(response, task_id)
            except Exception as e:
                logger.error(f"[A2ATool] 检查JSON响应格式时出错: {str(e)}")
        
        # 如果不是标准SSE格式，尝试以非标准方式处理
        logger.info(f"[A2ATool] 检测到非标准SSE格式，尝试直接解析响应")
        return await self._process_non_standard_response(response, task_id)
        
    async def _process_non_standard_response(self, response, task_id):
        """
        处理非标准SSE响应
        
        Args:
            response: HTTP响应对象
            task_id: 任务ID
            
        Returns:
            str: 处理结果
        """
        try:
            # 读取完整响应内容
            text = await response.text()
            logger.info(f"[A2ATool] 非SSE响应内容长度: {len(text)}")
            logger.info(f"[A2ATool] 非SSE响应内容预览: {text[:200]}..." if len(text) > 200 else f"[A2ATool] 非SSE响应内容: {text}")
            
            try:
                # 尝试解析为JSON
                data = json.loads(text)
                
                # 检查是否是中间状态，而不是最终结果
                is_working_state = False
                if isinstance(data, dict):
                    # 检查是否存在"state":"working"这样的状态标识
                    if "state" in data and data["state"] == "working":
                        is_working_state = True
                        logger.info(f"[A2ATool] 检测到工作中状态(state:working)，需要等待最终结果")
                    elif "result" in data and isinstance(data["result"], dict):
                        result = data["result"]
                        if "status" in result:
                            if isinstance(result["status"], dict) and result["status"].get("state") == "working":
                                is_working_state = True
                                logger.info(f"[A2ATool] 检测到工作中状态(result.status.state:working)，需要等待最终结果")
                            elif result["status"] == "working":
                                is_working_state = True
                                logger.info(f"[A2ATool] 检测到工作中状态(result.status:working)，需要等待最终结果")
                    
                    # 添加更多状态检测逻辑
                    elif "status" in data:
                        if isinstance(data["status"], str) and data["status"] == "working":
                            is_working_state = True
                            logger.info(f"[A2ATool] 检测到工作中状态(status:working)，需要等待最终结果")
                        elif isinstance(data["status"], dict) and data["status"].get("state") == "working":
                            is_working_state = True
                            logger.info(f"[A2ATool] 检测到工作中状态(status.state:working)，需要等待最终结果")
                
                # 如果是中间状态，发送到中转站并继续轮询等待最终结果
                if is_working_state:
                    try:
                        # 发送到中转站作为中间状态
                        transit = TransitStation.get_instance()
                        state = {
                            "content": "正在处理中，请稍候...",
                            "source": f"工具更新:{self.tool_name}",
                            "timestamp": int(time.time() * 1000),
                            "is_final": False  # 明确标记为非最终状态
                        }
                        transit.add_intermediate_state(state)
                        logger.info(f"[A2ATool] 已发送中间状态到中转站，开始轮询等待最终结果")
                        
                        # 强制等待并轮询结果
                        for _ in range(10):  # 尝试轮询10次
                            await asyncio.sleep(2)  # 每2秒轮询一次
                            poll_result = await self._poll_task_status(task_id, max_retries=1, delay=0.5)
                            if poll_result and "处理中" not in poll_result and "轮询超时" not in poll_result:
                                logger.info(f"[A2ATool] 轮询获取到最终结果: {poll_result[:50]}...")
                                
                                # 发送最终结果到中转站
                                final_state = {
                                    "content": poll_result,
                                    "source": f"工具完成:{self.tool_name}",
                                    "timestamp": int(time.time() * 1000),
                                    "is_final": True
                                }
                                transit.add_intermediate_state(final_state)
                                logger.info(f"[A2ATool] 已发送最终结果到中转站")
                                return poll_result
                        
                        # 如果所有轮询尝试都失败，返回中间状态作为结果
                        logger.warning(f"[A2ATool] 轮询获取最终结果失败，返回处理中状态")
                        return "工具正在处理中，但获取最终结果超时。请稍后查询。"
                    except Exception as transit_error:
                        logger.warning(f"[A2ATool] 处理中间状态异常: {str(transit_error)}")
                        logger.warning(f"[A2ATool] 异常详情: {traceback.format_exc()}")
                
                # 安全地提取内容，避免使用切片作为字典键
                try:
                    content = self.extract_content_from_event(data)
                    content_preview = str(content)[:50] if content else "无内容"
                except Exception as extract_error:
                    logger.error(f"[A2ATool] 从非SSE响应提取内容失败: {str(extract_error)}")
                    content = f"解析内容出错: {str(extract_error)}"
                    content_preview = content[:50]
                
                if content:
                    logger.info(f"[A2ATool] 从非SSE响应提取内容: {content_preview}...")
                    # 发送到中转站
                    try:
                        transit = TransitStation.get_instance()
                        # 确保content是字符串
                        if not isinstance(content, str):
                            content = json.dumps(content, ensure_ascii=False)
                        
                        # 检测是否是完成状态
                        is_completed = False
                        
                        # 方式1: 检查通用状态字段
                        if isinstance(data, dict):
                            # 直接检查顶层状态
                            if data.get("state") == "completed" or data.get("final") is True:
                                is_completed = True
                            
                            # 检查result对象中的状态
                            elif "result" in data and isinstance(data["result"], dict):
                                result = data["result"]
                                
                                # 检查直接的status字段
                                if result.get("status") == "completed":
                                    is_completed = True
                                
                                # 检查嵌套的status对象
                                elif "status" in result and isinstance(result["status"], dict):
                                    if result["status"].get("state") in ["completed", "COMPLETED"]:
                                        is_completed = True
                                
                                # 检查final字段
                                elif result.get("final") is True:
                                    is_completed = True
                            
                            # 检查status对象
                            elif "status" in data and isinstance(data["status"], dict):
                                if data["status"].get("state") in ["completed", "COMPLETED"]:
                                    is_completed = True
                        
                        # 创建状态对象
                        state = {
                            "content": content,
                            "source": f"工具{'完成' if is_completed else '更新'}:{self.tool_name}",
                            "timestamp": int(time.time() * 1000),
                            "is_final": is_completed
                        }
                        
                        transit.add_intermediate_state(state)
                        logger.info(f"[A2ATool] 已发送非SSE内容到中转站{' (标记为最终状态)' if is_completed else ''}")
                    except Exception as transit_error:
                        logger.warning(f"[A2ATool] 发送非SSE内容到中转站失败: {str(transit_error)}")
                        logger.warning(f"[A2ATool] 异常详情: {traceback.format_exc()}")
                return content
            except json.JSONDecodeError:
                logger.warning(f"[A2ATool] 非SSE响应不是有效的JSON: {text[:100]}...")
                return text
        except Exception as e:
            logger.error(f"[A2ATool] 处理非SSE响应异常: {str(e)}")
            logger.error(f"[A2ATool] 异常详情: {traceback.format_exc()}")
            return "未能处理非标准响应"

    async def _process_standard_sse(self, response, task_id):
        """
        处理标准SSE流
        
        Args:
            response: SSE响应对象
            task_id: 任务ID
            
        Returns:
            str: 处理结果
        """
        result_text = ""
        final_result = None
        event_count = 0
        is_completed = False
        last_heartbeat = time.time()
        heartbeat_interval = 30  # 30秒无数据认为心跳超时
        has_sent_final = False  # 跟踪是否已发送最终状态
        
        try:
            logger.info(f"[A2ATool] 开始处理SSE流，任务ID: {task_id}")
            
            # 处理SSE流
            buffer = b""  # 用于组合可能被分割的SSE行
            async for line in response.content:
                # 重置心跳计时器
                last_heartbeat = time.time()
                
                # 合并到缓冲区
                buffer += line
                
                # 处理完整的行
                while b'\n' in buffer:
                    pos = buffer.find(b'\n')
                    line_str = buffer[:pos].decode('utf-8', errors='replace').strip()
                    buffer = buffer[pos+1:]
                    
                    if not line_str:
                        # 空行可能表示事件结束
                        continue
                        
                    # 处理SSE行
                    if line_str.startswith('data: '):
                        event_count += 1
                        data_str = line_str[6:].strip()
                        logger.debug(f"[A2ATool] SSE事件 #{event_count}: {data_str[:100]}...")
                        
                        try:
                            # 解析JSON数据
                            data = json.loads(data_str)
                            
                            # 提取内容
                            content = self.extract_content_from_event(data)
                            
                            if content:
                                # 累加到结果文本
                                if isinstance(content, str):
                                    if result_text and content not in result_text:
                                        result_text += "\n" + content
                                    else:
                                        result_text = content
                                else:
                                    # 对象类型，转为JSON字符串
                                    json_str = json.dumps(content, ensure_ascii=False)
                                    if result_text and json_str not in result_text:
                                        result_text += "\n" + json_str
                                    else:
                                        result_text = json_str
                                
                                # 检查是否是最终事件
                                is_final = False
                                
                                # 优化状态字段检测 - 支持更多路径
                                if isinstance(data, dict):
                                    # 1. 检查result字段路径
                                    if "result" in data and isinstance(data["result"], dict):
                                        result_obj = data["result"]
                                        
                                        # 1.1 直接检查final字段
                                        if "final" in result_obj and result_obj["final"]:
                                            is_final = True
                                            logger.info(f"[A2ATool] 检测到final=true标记")
                                        
                                        # 1.2 检查status字段
                                        if "status" in result_obj:
                                            if isinstance(result_obj["status"], str):
                                                state = result_obj["status"]
                                                if state in ["completed", "failed", "canceled"]:
                                                    is_completed = True
                                                    is_final = True
                                                    logger.info(f"[A2ATool] 任务状态为: {state}")
                                            elif isinstance(result_obj["status"], dict):
                                                status_obj = result_obj["status"]
                                                
                                                # 1.2.1 检查state字段
                                                if "state" in status_obj:
                                                    state = status_obj["state"]
                                                    if state in ["completed", "failed", "canceled"]:
                                                        is_completed = True
                                                        is_final = True
                                                        logger.info(f"[A2ATool] 任务状态为: {state}")
                                    
                                    # 2. 直接检查top-level状态字段
                                    if "status" in data:
                                        if isinstance(data["status"], str) and data["status"] in ["completed", "failed", "canceled"]:
                                            is_completed = True
                                            is_final = True
                                            logger.info(f"[A2ATool] 顶层任务状态为: {data['status']}")
                                        elif isinstance(data["status"], dict) and "state" in data["status"]:
                                            state = data["status"]["state"]
                                            if state in ["completed", "failed", "canceled"]:
                                                is_completed = True
                                                is_final = True
                                                logger.info(f"[A2ATool] 顶层任务状态为: {state}")
                                    
                                    # 3. 检查状态事件类型
                                    if "event" in data:
                                        event_type = data["event"] 
                                        if event_type in ["completed", "failed", "canceled", "done"]:
                                            is_completed = True
                                            is_final = True
                                            logger.info(f"[A2ATool] 事件类型为: {event_type}")
                                
                                # 提取并保存最终结果
                                if is_final or is_completed:
                                    final_result = content
                                    logger.info(f"[A2ATool] 检测到最终结果: {str(content)[:100]}...")
                                
                                # 发送内容到中转站 (如果不是太频繁的更新)
                                try:
                                    # 创建适合中转站的状态
                                    is_important_update = is_final or is_completed or event_count % 3 == 0 or len(str(content)) < 500
                                    
                                    if is_important_update:
                                        transit = TransitStation.get_instance()
                                        # 确保content是字符串
                                        if not isinstance(content, str):
                                            content_str = json.dumps(content, ensure_ascii=False)
                                        else:
                                            content_str = content
                                        
                                        # 创建状态对象
                                        state = {
                                            "content": content_str,
                                            "source": f"工具{'完成' if (is_final or is_completed) else '更新'}:{self.tool_name}",
                                            "timestamp": int(time.time() * 1000),
                                            "is_final": (is_final or is_completed)
                                        }
                                        
                                        transit.add_intermediate_state(state)
                                        
                                        if is_final or is_completed:
                                            has_sent_final = True
                                            logger.info(f"[A2ATool] 已发送SSE最终结果到中转站")
                                        else:
                                            logger.debug(f"[A2ATool] 已发送SSE中间结果到中转站: #{event_count}")
                                except Exception as transit_error:
                                    logger.warning(f"[A2ATool] 发送SSE内容到中转站失败: {str(transit_error)}")
                                    logger.warning(f"[A2ATool] 异常详情: {traceback.format_exc()}")
                        except json.JSONDecodeError as json_error:
                            logger.warning(f"[A2ATool] SSE事件JSON解析错误: {str(json_error)}")
                            logger.warning(f"[A2ATool] 错误数据: {data_str[:100]}...")
                            # 尝试解析非JSON事件
                            if data_str and data_str.strip():
                                # 简单地将原始数据作为字符串内容处理
                                pure_text = data_str.strip()
                                if pure_text and len(pure_text) > 3:  # 忽略太短的内容
                                    if result_text:
                                        result_text += "\n" + pure_text
                                    else:
                                        result_text = pure_text
                                    logger.info(f"[A2ATool] 处理为纯文本内容: {pure_text[:50]}...")
                        except Exception as data_error:
                            logger.error(f"[A2ATool] 处理SSE数据异常: {str(data_error)}")
                            logger.error(f"[A2ATool] 异常详情: {traceback.format_exc()}")
                    
                    # 处理其他类型的SSE行
                    elif line_str.startswith('event:'):
                        event_type = line_str[6:].strip()
                        logger.info(f"[A2ATool] SSE事件类型: {event_type}")
                        
                        # 检查是否是最终事件
                        if event_type in ["done", "complete", "finished", "end"]:
                            is_completed = True
                            logger.info(f"[A2ATool] 检测到结束事件: {event_type}")
                
                # 检查心跳超时
                if time.time() - last_heartbeat > heartbeat_interval:
                    logger.warning(f"[A2ATool] SSE心跳超时({heartbeat_interval}秒无数据)")
                    break
            
            # 处理缓冲区中的最后内容
            if buffer:
                try:
                    line_str = buffer.decode('utf-8', errors='replace').strip()
                    if line_str.startswith('data: '):
                        logger.info(f"[A2ATool] 处理剩余缓冲区的数据: {line_str[:50]}...")
                        # 处理剩余数据
                        data_str = line_str[6:].strip()
                        try:
                            data = json.loads(data_str)
                            content = self.extract_content_from_event(data)
                            if content and result_text and isinstance(content, str) and content not in result_text:
                                result_text += "\n" + content
                        except Exception as e:
                            logger.warning(f"[A2ATool] 处理缓冲区剩余数据时出错: {str(e)}")
                except Exception as buffer_error:
                    logger.warning(f"[A2ATool] 处理最后缓冲区时出错: {str(buffer_error)}")
            
            logger.info(f"[A2ATool] SSE处理完成，事件总数: {event_count}")
            
            # 提取最终结果
            if final_result:
                logger.info(f"[A2ATool] 返回检测到的最终结果")
                return final_result
            
            # 如果没有明确的最终结果，但有累积的内容，返回累积内容
            if result_text:
                # 如果还没发送过最终结果到中转站，现在发送
                if not has_sent_final and event_count > 0:
                    try:
                        transit = TransitStation.get_instance()
                        # 创建最终状态
                        state = {
                            "content": result_text,
                            "source": f"工具完成:{self.tool_name}",
                            "timestamp": int(time.time() * 1000),
                            "is_final": True
                        }
                        transit.add_intermediate_state(state)
                        logger.info(f"[A2ATool] 已发送累积SSE结果作为最终结果到中转站")
                    except Exception as transit_error:
                        logger.warning(f"[A2ATool] 发送累积SSE结果到中转站失败: {str(transit_error)}")
                
                logger.info(f"[A2ATool] 返回累积内容作为结果")
                return result_text
                
            # 没有任何内容
            logger.warning(f"[A2ATool] SSE流没有产生有效内容")
            return "处理SSE流没有获得有效结果"
            
        except Exception as e:
            error_msg = f"处理SSE流异常: {str(e)}"
            logger.error(f"[A2ATool] {error_msg}")
            logger.error(f"[A2ATool] 异常详情: {traceback.format_exc()}")
            
            # 如果有累积的内容，返回它
            if result_text:
                logger.info(f"[A2ATool] 尽管出错，但返回已累积的内容")
                return result_text
                
            return error_msg

    def extract_content_from_event(self, event_data):
        """
        从事件数据中提取内容，支持多种类型
        
        Args:
            event_data: 事件数据字典
            
        Returns:
            提取的内容，可能是字符串或字典，如果没有提取到内容则返回None
        """
        try:
            # 防止错误：使用安全的字符串预览
            preview = str(event_data)[:200] if event_data else "None"
            logger.debug(f"[A2ATool] 提取内容 - 事件数据预览: {preview}")
            
            if not isinstance(event_data, dict):
                logger.warning(f"[A2ATool] 事件数据不是字典类型: {preview}")
                return str(event_data)
            
            # 处理JSON-RPC响应格式
            if "result" in event_data and isinstance(event_data["result"], dict):
                result = event_data["result"]
                logger.debug(f"[A2ATool] 处理result字段")
                
                # 检查是否是任务状态更新
                if "status" in result:
                    status = result["status"]
                    # 记录状态信息
                    if isinstance(status, dict) and "state" in status:
                        state = status["state"]
                        logger.info(f"[A2ATool] 任务状态: {state}")
                        
                        # 如果任务完成，尝试获取产物内容
                        if state == "completed":
                            # 检查是否有产物列表
                            if "artifacts" in result and isinstance(result["artifacts"], list):
                                artifacts = result["artifacts"]
                                logger.info(f"[A2ATool] 找到{len(artifacts)}个产物")
                                
                                # 遍历产物列表
                                for i, artifact in enumerate(artifacts):
                                    logger.info(f"[A2ATool] 处理产物 #{i+1}")
                                    
                                    # 检查产物是否有parts字段
                                    if "parts" in artifact and isinstance(artifact["parts"], list):
                                        parts = artifact["parts"]
                                        logger.info(f"[A2ATool] 找到{len(parts)}个parts")
                                        
                                        # 遍历parts
                                        for j, part in enumerate(parts):
                                            logger.info(f"[A2ATool] 处理part #{j+1}")
                                            
                                            # 处理文本类型
                                            if isinstance(part, dict) and part.get("type") == "text" and "text" in part:
                                                text_content = part["text"]
                                                logger.info(f"[A2ATool] 从产物中提取文本内容")
                                                return text_content
                            else:
                                logger.warning(f"[A2ATool] 任务完成但找不到产物")
                    
                    # 如果有消息，尝试提取
                    if isinstance(status, dict) and "message" in status:
                        message = status["message"]
                        logger.info(f"[A2ATool] 找到状态消息")
                        
                        # 处理message对象
                        if isinstance(message, dict):
                            # 检查message是否有parts字段
                            if "parts" in message and isinstance(message["parts"], list):
                                parts = message["parts"]
                                logger.info(f"[A2ATool] 找到{len(parts)}个parts")
                                
                                # 遍历parts
                                for j, part in enumerate(parts):
                                    logger.info(f"[A2ATool] 处理part #{j+1}")
                                    
                                    # 处理文本类型
                                    if isinstance(part, dict) and part.get("type") == "text" and "text" in part:
                                        text_content = part["text"]
                                        logger.info(f"[A2ATool] 从状态消息中提取文本内容")
                                        return text_content
                        elif isinstance(message, str):
                            logger.info(f"[A2ATool] 直接使用状态消息字符串")
                            return message
                
                # 任务已完成但找不到完整结果，返回状态信息
                if "status" in result and isinstance(result["status"], dict):
                    status_str = json.dumps(result["status"], ensure_ascii=False)
                    logger.warning(f"[A2ATool] 任务 {result.get('task_id', 'unknown')} 状态信息: {status_str}")
                    return f"任务已完成，状态: {status_str}"
            
            # 处理标准Part格式
            if "parts" in event_data and isinstance(event_data["parts"], list):
                parts = event_data["parts"]
                logger.info(f"[A2ATool] 处理顶层parts字段，找到{len(parts)}个parts")
                
                # 遍历parts
                for j, part in enumerate(parts):
                    logger.info(f"[A2ATool] 处理part #{j+1}")
                    
                    # 处理文本类型
                    if isinstance(part, dict) and part.get("type") == "text" and "text" in part:
                        text_content = part["text"]
                        logger.info(f"[A2ATool] 从parts中提取文本内容")
                        return text_content
                    # 处理数据类型
                    elif isinstance(part, dict) and part.get("type") == "data" and "data" in part:
                        logger.info(f"[A2ATool] 从parts中提取数据内容")
                        return part["data"]
            
            # 处理简单文本格式
            if "text" in event_data and isinstance(event_data["text"], str):
                logger.info(f"[A2ATool] 直接提取文本内容")
                return event_data["text"]
                
            # 最后的回退：返回整个数据的字符串表示
            logger.warning(f"[A2ATool] 无法提取内容，返回原始数据")
            return str(event_data)
            
        except Exception as e:
            # 详细记录异常
            logger.error(f"[A2ATool] 提取内容时出错: {str(e)}")
            import traceback
            logger.error(f"[A2ATool] 错误详情: {traceback.format_exc()}")
            
            # 返回错误信息
            return f"处理工具返回数据时出错: {str(e)}"

    # 添加标准A2A接口方法
    def invoke(self, query: str) -> str:
        """
        统一的同步调用接口，与A2A标准一致
        
        Args:
            query: 查询文本
            
        Returns:
            str: 工具返回结果
        """
        return self._run(query)
    
    async def ainvoke(self, query: str) -> str:
        """
        统一的异步调用接口，与A2A标准一致
        
        Args:
            query: 查询文本
            
        Returns:
            str: 工具返回结果
        """
        logger.info(f"[A2ATool] 异步调用接口ainvoke被调用: {self.name}, 查询: {query[:30] if query else '空查询'}...")
        return await self._arun(query)


class A2AToolNode:
    """
    A2A工具节点 - LangGraph工作流的自定义节点
    用于处理对A2A工具的调用，兼容ReAct模式
    """
    
    def __init__(self, a2a_tools: List[A2ATool]):
        """
        初始化A2A工具节点
        
        Args:
            a2a_tools: A2A工具列表
        """
        self.tools = {tool.name: tool for tool in a2a_tools}
        logger.info(f"[A2AToolNode] 初始化完成，工具列表: {list(self.tools.keys())}")
        
        # 尝试导入语义相似度计算库
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.tfidf = TfidfVectorizer(stop_words='english')
            self.use_semantic = True
            logger.info("[A2AToolNode] 已启用语义相似度计算")
        except ImportError:
            self.use_semantic = False
            logger.warning("[A2AToolNode] 未找到sklearn，将使用传统关键词匹配")
    
    def evaluate_query(self, query: str, requested_tool: str = None, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        评估查询对A2A工具的适用性，支持语义匹配和多工具评分
        
        Args:
            query: 用户查询文本
            requested_tool: 请求的工具名称（如果有）
            context: 上下文信息，包含历史消息等
        
        Returns:
            Dict: 包含最合适工具和评分的字典，以及备选工具列表
        """
        # 1. 如果请求了特定工具，且该工具是A2A工具，优先选择
        if requested_tool and requested_tool in self.tools:
            return {
                "tool": self.tools[requested_tool],
                "score": 0.9,  # 高分但非满分，允许更精确的工具覆盖
                "reason": "直接请求的工具",
                "alternatives": []  # 没有备选工具
            }
        
        # 收集所有工具的评分
        tool_scores = []
        
        # 如果使用语义相似度
        if self.use_semantic and len(self.tools) > 1:
            try:
                import numpy as np
                
                # 准备文本语料：工具描述和查询
                corpus = [query.lower()]
                tool_descriptions = []
                for name, tool in self.tools.items():
                    desc = f"{name}: {tool.description.lower()}"
                    corpus.append(desc)
                    tool_descriptions.append((name, tool))
                
                # 计算TF-IDF矩阵
                tfidf_matrix = self.tfidf.fit_transform(corpus)
                
                # 计算余弦相似度
                query_vector = tfidf_matrix[0:1]
                for i, (name, tool) in enumerate(tool_descriptions):
                    tool_vector = tfidf_matrix[i+1:i+2]
                    
                    # 计算余弦相似度
                    similarity = np.dot(query_vector.toarray().flatten(), 
                                        tool_vector.toarray().flatten()) / (
                                            np.linalg.norm(query_vector.toarray()) * 
                                            np.linalg.norm(tool_vector.toarray())
                                        )
                    
                    # 直接名称匹配加分
                    name_match = 0.2 if name.lower() in query.lower() else 0
                    
                    # 最终评分
                    final_score = similarity + name_match
                    
                    tool_scores.append({
                        "tool": tool,
                        "score": float(final_score),  # 转换为Python标准类型
                        "reason": "语义相似度评分"
                    })
                
                logger.info(f"[A2AToolNode] 语义评分完成，共{len(tool_scores)}个工具")
            except Exception as e:
                logger.error(f"[A2AToolNode] 语义评分出错: {repr(e)}，回退到关键词匹配")
                self.use_semantic = False  # 发生错误时回退
        
        # 如果未使用语义相似度或出错，使用关键词匹配
        if not self.use_semantic or not tool_scores:
            for name, tool in self.tools.items():
                # 关键词匹配评分
                keywords = tool.description.lower().split()
                keyword_score = sum(1 for word in keywords if word.lower() in query.lower()) / max(1, len(keywords))
                
                # 工具名称匹配评分
                name_match = 0.3 if name.lower() in query.lower() else 0
                
                # 任务相关性评分 - 使用简单启发式规则
                task_relevance = 0
                if context and "tool_history" in context:
                    # 如果之前使用过该工具且成功，增加评分
                    for tool_use in context["tool_history"]:
                        if tool_use["name"] == name and tool_use["success"]:
                            task_relevance += 0.2
                            break
                
                # 综合评分 (加权平均)
                final_score = (0.6 * keyword_score) + (0.3 * name_match) + (0.1 * task_relevance)
                
                tool_scores.append({
                    "tool": tool,
                    "score": final_score,
                    "reason": "关键词匹配评分"
                })
        
        # 按评分排序
        tool_scores.sort(key=lambda x: x["score"], reverse=True)
        
        # 如果没有工具可用
        if not tool_scores:
            logger.info(f"[A2AToolNode] 评估结果: 没有找到合适的工具")
            return {
                "tool": None,
                "score": 0,
                "reason": "没有合适的工具",
                "alternatives": []
            }
            
        # 记录选择结果
        best_match = tool_scores[0]
        alternatives = tool_scores[1:3] if len(tool_scores) > 1 else []
        
        logger.info(f"[A2AToolNode] 评估结果: 选择工具 {best_match['tool'].name}, 得分: {best_match['score']:.2f}")
        if alternatives:
            logger.info(f"[A2AToolNode] 备选工具: {', '.join([alt['tool'].name for alt in alternatives])}")
            
        return {
            "tool": best_match["tool"],
            "score": best_match["score"],
            "reason": best_match["reason"],
            "alternatives": alternatives
        }
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具调用 - 同步方法
        
        Args:
            state: 输入状态，包含消息历史
            
        Returns:
            Dict[str, Any]: 更新后的状态
        """
        # 兼容已运行事件循环的环境
        try:
            existing_loop = asyncio.get_running_loop()
        except RuntimeError:
            existing_loop = None

        if existing_loop and existing_loop.is_running():
            result_container = {}
            def _runner():
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result_container['value'] = loop.run_until_complete(self.ainvoke(state))
                finally:
                    loop.close()
            import threading
            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join()
            return result_container.get('value', state)
        else:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self.ainvoke(state))
            finally:
                loop.close()
    
    async def ainvoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具调用 - 异步方法
        
        Args:
            state: 输入状态，包含消息历史
            
        Returns:
            Dict[str, Any]: 更新后的状态
        """
        # 检查状态中是否有消息
        if "messages" not in state or not state["messages"]:
            return state
        
        outputs = []
        last_message = state["messages"][-1]
        
        # 检查是否有工具调用
        tool_calls = []
        
        # 1. 检查标准的tool_calls属性
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            tool_calls = last_message.tool_calls
            logger.info(f"[A2AToolNode] 找到标准格式工具调用: {len(tool_calls)}个")
        
        # 2. 如果没有找到工具调用，尝试从消息内容中解析
        elif hasattr(last_message, "content") and isinstance(last_message.content, str):
            content = last_message.content
            
            # 解析ReAct格式的Action行
            import re
            action_patterns = [
                r'Action\s*:\s*(\w+)\[(.*?)\]',
                r'行动\s*:\s*(\w+)\[(.*?)\]',
                r'动作\s*:\s*(\w+)\[(.*?)\]'
            ]
            
            for pattern in action_patterns:
                matches = re.findall(pattern, content, re.DOTALL)
                if matches:
                    for tool_name, args_str in matches:
                        # 尝试解析参数为JSON
                        try:
                            args = json.loads(args_str)
                        except:
                            # 如果不是有效JSON，作为普通字符串处理
                            args = {"input": args_str.strip()}
                        
                        # 生成唯一ID
                        tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
                        
                        tool_calls.append({
                            "name": tool_name,
                            "args": args,
                            "id": tool_call_id
                        })
                        logger.info(f"[A2AToolNode] 解析到ReAct格式工具调用: {tool_name}")
                        break
                
                if tool_calls:
                    break
            
            # 尝试解析JSON格式
            if not tool_calls:
                json_pattern = r'```(?:json)?\s*(.*?)\s*```'
                json_matches = re.findall(json_pattern, content, re.DOTALL)
                
                for json_str in json_matches:
                    try:
                        tool_data = json.loads(json_str)
                        if "action" in tool_data and "action_input" in tool_data:
                            tool_name = tool_data["action"]
                            tool_input = tool_data["action_input"]
                            
                            tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
                            
                            tool_calls.append({
                                "name": tool_name,
                                "args": tool_input if isinstance(tool_input, dict) else {"input": tool_input},
                                "id": tool_call_id
                            })
                            logger.info(f"[A2AToolNode] 解析到JSON格式工具调用: {tool_name}")
                            break
                    except Exception as e:
                        logger.error(f"[A2AToolNode] JSON解析失败: {repr(e)}")
                        continue
        
        # 如果没有工具调用，直接返回状态
        if not tool_calls:
            logger.info("[A2AToolNode] 未检测到A2A工具调用")
            return state
        
        # 执行所有工具调用
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            args = tool_call.get("args", {})
            
            # 获取A2A工具
            tool = self.tools.get(tool_name)
            
            if tool:
                # 执行工具调用
                try:
                    # 确定输入参数
                    if "input" in args:
                        input_value = args["input"]
                    elif len(args) == 0:
                        input_value = ""
                    else:
                        input_value = args
                    
                    # 异步调用工具
                    logger.info(f"[A2AToolNode] 执行A2A工具 {tool_name}，参数: {input_value}")
                    logger.info(f"[A2AToolNode] 调用路径: A2AToolNode.ainvoke -> A2ATool.ainvoke -> A2ATool._arun -> 异步流程")
                    result = await tool.ainvoke(input_value if isinstance(input_value, str) else json.dumps(input_value))
                    
                    # 创建标准的ToolMessage
                    tool_message = ToolMessage(
                        content=result,
                        tool_call_id=tool_call.get("id", ""),
                        name=tool_name,
                    )
                    
                    outputs.append(tool_message)
                    logger.info(f"[A2AToolNode] 工具 {tool_name} 执行完成，结果长度: {len(result)}")
                    
                except Exception as e:
                    logger.error(f"[A2AToolNode] 工具 {tool_name} 执行失败: {repr(e)}")
                    
                    # 生成错误消息
                    error_message = ToolMessage(
                        content=f"Error: {repr(e)}",
                        tool_call_id=tool_call.get("id", ""),
                        name=tool_name,
                    )
                    
                    outputs.append(error_message)
            else:
                logger.warning(f"[A2AToolNode] 未找到工具: {tool_name}")
                
                # 生成错误消息
                error_message = ToolMessage(
                    content=f"Error: Tool '{tool_name}' not found",
                    tool_call_id=tool_call.get("id", ""),
                    name=tool_name,
                )
                
                outputs.append(error_message)
        
        # 更新消息历史
        state["messages"] = state["messages"] + outputs
        
        # 返回更新的状态
        return state


class A2AAdapter:
    """A2A服务适配器 - 处理与A2A服务器的交互"""
    
    def __init__(self, server_url: str):
        """
        初始化A2A适配器
        
        Args:
            server_url: A2A服务器URL
        """
        self.server_url = server_url.rstrip('/')
        logger.info(f"[A2AAdapter] 初始化完成，服务器: {server_url}")
    
    async def check_server_health(self, timeout=5) -> bool:  # 延长超时到5秒
        """
        检查A2A服务器健康状态
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            bool: 服务器是否健康
        """
        try:
            health_url = f"{self.server_url}/a2a/health"
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    health_url,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        status = data.get("status", "")
                        if status == "ok":
                            logger.info("[A2AAdapter] 服务器健康检查通过")
                            return True
                    
                    logger.warning(f"[A2AAdapter] 服务器健康检查失败: HTTP {response.status}")
                    return False
        except Exception as e:
            logger.error(f"[A2AAdapter] 服务器健康检查异常: {repr(e)}")
            return False
    
    async def discover_available_tools(self) -> List[Dict[str, Any]]:
        """
        发现可用的A2A工具
        
        Returns:
            List[Dict[str, Any]]: 工具信息列表
        """
        try:
            discover_url = f"{self.server_url}/a2a/discover"
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    discover_url,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "result" in data and "tools" in data["result"]:
                            tools = data["result"]["tools"]
                            logger.info(f"[A2AAdapter] 发现 {len(tools)} 个工具")
                            return tools
                        else:
                            logger.warning("[A2AAdapter] 发现工具响应格式错误")
                            return []
                    else:
                        logger.error(f"[A2AAdapter] 发现工具失败: HTTP {response.status}")
                        return []
        except Exception as e:
            logger.error(f"[A2AAdapter] 发现工具异常: {repr(e)}")
            return []


def create_a2a_tools(server_url: str) -> List[BaseTool]:
    """
    创建A2A工具列表
    
    Args:
        server_url: A2A服务器URL
        
    Returns:
        List[BaseTool]: A2A工具列表
    """
    # 创建A2A适配器
    adapter = A2AAdapter(server_url)
    
    # 获取可用工具
    tools = []
    
    try:
        # 在任何线程环境下安全地创建事件循环
        try:
            # 尝试获取现有循环
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # 如果在非主线程中且没有循环，创建新循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 使用try-finally确保循环资源被正确释放
        try:
            # 不阻塞主事件循环：如果已有事件循环在运行，改走线程
            def _discover():
                inner = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(inner)
                    # 健康检查失败也不抛异常，返回空列表，避免阻断启动
                    try:
                        ok = inner.run_until_complete(adapter.check_server_health())
                        if not ok:
                            logger.warning(f"[create_a2a_tools] A2A服务器({server_url})不可用，工具跳过")
                            return []
                    except Exception:
                        logger.warning(f"[create_a2a_tools] 健康检查异常，工具跳过")
                        return []
                    return inner.run_until_complete(adapter.discover_available_tools())
                finally:
                    inner.close()

            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None

            if running and running.is_running():
                import threading
                result = {}
                t = threading.Thread(target=lambda: result.setdefault('v', _discover()), daemon=True)
                t.start()
                t.join()
                available_tools = result.get('v', [])
            else:
                available_tools = _discover()

            # 遍历可用工具
            for tool_info in available_tools:
                tool_name = tool_info.get("name", "")
                description = tool_info.get("description", "")
                
                # 创建A2A工具
                tool = A2ATool(
                    name=tool_name,
                    description=description,
                    server_url=server_url,
                    tool_name=tool_name
                )
                
                # 添加到工具列表
                tools.append(tool)
                
                logger.info(f"[create_a2a_tools] 创建A2A工具: {tool_name}")
        finally:
            # 如果是我们创建的新循环，关闭它以防止资源泄漏
            if not loop.is_running() and not loop.is_closed():
                loop.close()
    
    except Exception as e:
        logger.error(f"[create_a2a_tools] 创建A2A工具失败: {repr(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 出错时返回状态工具
        status_tool = BaseTool(
            name="a2a_server_status",
            description="显示A2A服务器状态",
            func=lambda x: f"A2A服务器({server_url})连接失败: {repr(e)}"
        )
        return [status_tool]
    
    # 如果没有发现工具，返回状态工具
    if not tools:
        logger.warning(f"[create_a2a_tools] 未发现任何A2A工具")
        status_tool = BaseTool(
            name="a2a_server_status", 
            description="显示A2A服务器状态",
            func=lambda x: f"A2A服务器({server_url})未提供任何工具"
        )
        return [status_tool]
    
    return tools 