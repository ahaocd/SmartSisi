"""
A2A集成类 - 让LangGraph能够作为A2A服务的组件
参考官方A2A样例实现，2025.4.18修正
"""

import asyncio
import logging
import time
import requests
import threading
import json
import uuid
from typing import Dict, Any, List, Optional, Union, Tuple, Callable

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class A2AToolOrchestrator:
    """
    A2A工具编排器 - 负责选择合适的工具并协调它们的执行
    类似Google A2A官方实现中的host_agent
    """
    
    def __init__(self):
        """初始化工具编排器"""
        self.tools = {}  # 工具字典 {名称: 工具对象}
        self.task_manager = None
        self.llm = None  # 用于决策的LLM，延迟初始化
        self.initialized = False
        
    async def initialize(self):
        """异步初始化组件"""
        if self.initialized:
            return True
            
        # 导入任务管理器
        try:
            # 延迟导入避免循环引用
            from .a2a_task_manager import get_instance as get_task_manager
            self.task_manager = get_task_manager()
            
            # 预留用于LLM初始化，稍后实现
            self.initialized = True
            logger.info(f"[A2AToolOrchestrator] 初始化完成")
            return True
        except Exception as e:
            logger.error(f"初始化工具编排器失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def register_tool(self, tool):
        """注册工具到编排器"""
        tool_name = getattr(tool, "name", str(tool))
        self.tools[tool_name] = tool
        logger.info(f"[A2AToolOrchestrator] 已注册工具: {tool_name}")
        
    async def analyze_query(self, query: str, session_id: str = None) -> Dict[str, Any]:
        """
        分析查询并确定可能需要的工具
        
        Args:
            query: 用户查询
            session_id: 会话ID
            
        Returns:
            Dict: 包含工具分析结果的字典
        """
        if not self.initialized:
            await self.initialize()
            
        # 获取会话上下文（如果有）
        session_context = None
        if session_id and self.task_manager:
            session_context = await self.task_manager.get_session_context(session_id)
        
        # 分析查询意图 - 将来可用LLM实现更复杂分析
        from .a2a_adapter import A2AToolNode
        
        # 创建工具节点，用于评估工具匹配度
        tool_node = A2AToolNode(list(self.tools.values()) if hasattr(self.tools.values().__iter__(), '__next__') else [])
        
        # 准备上下文
        context = {}
        if session_context:
            context.update(session_context)
            
        # 评估工具匹配度
        tool_matches = tool_node.evaluate_query(query, context=context)
        
        # 可能用到的多个工具，按分数排序
        tools_to_use = []
        if tool_matches["tool"]:
            tools_to_use.append({
                "name": tool_matches["tool"].name,
                "score": tool_matches["score"],
                "reason": tool_matches["reason"]
            })
            
        # 添加备选工具
        for alt in tool_matches.get("alternatives", []):
            if alt["tool"]:
                tools_to_use.append({
                    "name": alt["tool"].name, 
                    "score": alt["score"],
                    "reason": alt["reason"]
                })
                
        logger.info(f"[A2AToolOrchestrator] 查询分析结果: {len(tools_to_use)}个工具")
        
        # 确定查询可能需要的子任务
        subtasks = self._identify_subtasks(query, tools_to_use)
        
        return {
            "tools": tools_to_use,
            "subtasks": subtasks,
            "query": query
        }
    
    def _identify_subtasks(self, query: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将查询分解为子任务
        
        Args:
            query: 用户查询
            tools: 可能的工具列表
            
        Returns:
            List[Dict]: 子任务列表
        """
        # 初始实现：每个工具一个子任务
        # 将来可用LLM执行更智能的任务分解
        
        subtasks = []
        
        # 简单启发式方法：
        # 1. 如果有'天气'工具且分数高，并且查询包含位置，创建天气子任务
        weather_tool = next((t for t in tools if "weather" in t["name"].lower()), None)
        if weather_tool and weather_tool["score"] > 0.5:
            subtasks.append({
                "id": f"subtask_{len(subtasks)+1}",
                "tool": weather_tool["name"],
                "description": "查询天气信息",
                "query": query,
                "priority": 1
            })
            
        # 2. 如果有地点工具且分数高，创建地点子任务
        location_tool = next((t for t in tools if "location" in t["name"].lower()), None)
        if location_tool and location_tool["score"] > 0.5:
            subtasks.append({
                "id": f"subtask_{len(subtasks)+1}",
                "tool": location_tool["name"],
                "description": "获取位置信息",
                "query": query,
                "priority": 0  # 位置信息优先
            })
                
        # 3. 如果有其他工具，添加一般子任务
        for tool in tools:
            if ("weather" not in tool["name"].lower() and 
                "location" not in tool["name"].lower() and
                tool["score"] > 0.4):
                subtasks.append({
                    "id": f"subtask_{len(subtasks)+1}",
                    "tool": tool["name"],
                    "description": f"使用{tool['name']}处理查询",
                    "query": query,
                    "priority": 2
                })
        
        # 按优先级排序
        subtasks.sort(key=lambda x: x["priority"])
        
        return subtasks
        
    async def execute_task_chain(self, query: str, session_id: str = None) -> Dict[str, Any]:
        """
        执行任务链 - 协调多个工具执行
        
        Args:
            query: 用户查询
            session_id: 会话ID
            
        Returns:
            Dict: 任务链执行结果
        """
        if not self.initialized:
            await self.initialize()
            
        # 1. 分析查询
        analysis = await self.analyze_query(query, session_id)
        
        # 尝试向中转站发送开始分析状态
        try:
            from llm.transit_station import TransitStation
            transit = TransitStation.get_instance()
            transit.add_intermediate_state("正在分析您的请求...", "A2A任务分析")
        except Exception as e:
            logger.warning(f"[A2AToolOrchestrator] 向中转站发送状态失败: {str(e)}")
        
        # 2. 创建主任务
        task_id = f"task_{int(time.time())}"
        if self.task_manager:
            await self.task_manager.create_task(task_id, query, session_id)
            await self.task_manager.update_task_status(task_id, "working", "正在分析和处理查询")
        
        # 3. 执行子任务
        results = []
        subtasks = analysis.get("subtasks", [])
        
        if not subtasks:
            # 没有需要执行的子任务
            if self.task_manager:
                await self.task_manager.update_task_status(task_id, "completed", "未找到合适的工具处理该查询")
            
            # 向中转站发送未找到工具的状态
            try:
                from llm.transit_station import TransitStation
                transit = TransitStation.get_instance()
                transit.add_intermediate_state("未找到合适的工具处理您的请求", "A2A任务分析", affect_flow=True)
            except Exception as e:
                logger.warning(f"[A2AToolOrchestrator] 向中转站发送状态失败: {str(e)}")
                
            return {
                "task_id": task_id,
                "status": "completed",
                "message": "未找到合适的工具处理该查询",
                "results": []
            }
        
        # 存储分析结果到任务上下文
        if self.task_manager:
            await self.task_manager.set_shared_context(task_id, "analysis", analysis)
            await self.task_manager.set_shared_context(task_id, "subtasks", subtasks)
        
        # 向中转站发送找到工具的状态
        try:
            from llm.transit_station import TransitStation
            transit = TransitStation.get_instance()
            tool_names = [t["tool"] for t in subtasks]
            transit.add_intermediate_state(f"找到合适的工具: {', '.join(tool_names)}", "A2A工具选择", affect_flow=True)
        except Exception as e:
            logger.warning(f"[A2AToolOrchestrator] 向中转站发送状态失败: {str(e)}")
        
        # 开始执行子任务
        for subtask in subtasks:
            tool_name = subtask["tool"]
            subtask_query = subtask["query"]
            
            # 更新状态
            if self.task_manager:
                await self.task_manager.update_task_status(
                    task_id, 
                    "working", 
                    f"正在执行子任务: {subtask['description']}"
                )
            
            # 向中转站发送子任务执行状态
            try:
                from llm.transit_station import TransitStation
                transit = TransitStation.get_instance()
                transit.add_intermediate_state(f"正在执行: {subtask['description']}", "A2A子任务执行", affect_flow=True)
            except Exception as e:
                logger.warning(f"[A2AToolOrchestrator] 向中转站发送状态失败: {str(e)}")
            
            # 获取工具
            tool = self.tools.get(tool_name)
            if not tool:
                logger.warning(f"[A2AToolOrchestrator] 未找到工具: {tool_name}")
                results.append({
                    "subtask_id": subtask["id"],
                    "success": False,
                    "message": f"未找到工具: {tool_name}"
                })
                continue
                
            # 执行工具
            try:
                logger.info(f"[A2AToolOrchestrator] 执行工具: {tool_name}, 查询: {subtask_query[:30]}...")
                
                # 决定同步还是异步调用
                if hasattr(tool, "ainvoke"):
                    # 优先异步调用
                    result = await tool.ainvoke(subtask_query)
                else:
                    # 回退到同步调用
                    result = tool.invoke(subtask_query)
                    
                # 记录结果
                results.append({
                    "subtask_id": subtask["id"],
                    "tool": tool_name,
                    "success": True,
                    "result": result
                })
                
                # 更新任务共享上下文，传递结果给其他工具
                if self.task_manager:
                    await self.task_manager.set_shared_context(
                        task_id, 
                        f"result_{tool_name}", 
                        result
                    )
                
                logger.info(f"[A2AToolOrchestrator] 工具{tool_name}执行成功")
                
            except Exception as e:
                logger.error(f"[A2AToolOrchestrator] 工具{tool_name}执行失败: {str(e)}")
                results.append({
                    "subtask_id": subtask["id"],
                    "tool": tool_name,
                    "success": False,
                    "error": str(e)
                })
        
        # 4. 组合结果 - 当前简单连接，将来可用LLM合成更好的答案
        combined_result = self._combine_results(results, query)
        
        # 5. 更新任务状态
        if self.task_manager:
            await self.task_manager.update_task_status(task_id, "completed", combined_result["message"])
            await self.task_manager.update_task_artifacts(task_id, [{
                "parts": [{"type": "text", "text": combined_result["message"]}],
                "index": 0
            }])
            await self.task_manager.set_shared_context(task_id, "final_results", results)
            
        return {
            "task_id": task_id,
            "status": "completed",
            "message": combined_result["message"],
            "results": results,
            "is_composite": True
        }
        
    def _combine_results(self, results: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """
        组合多个子任务结果
        
        Args:
            results: 子任务结果列表
            query: 原始查询
            
        Returns:
            Dict: 组合后的结果
        """
        # 提取所有成功的结果
        successful_results = [r for r in results if r.get("success", False)]
        
        if not successful_results:
            return {
                "message": "所有工具执行均失败，无法处理您的请求"
            }
            
        # 当前简单连接所有结果
        result_texts = []
        for r in successful_results:
            tool_name = r.get("tool", "未知工具")
            if isinstance(r.get("result"), str):
                result_texts.append(f"{r['result']}")
            else:
                result_texts.append(f"{str(r.get('result', '无结果'))}")
        
        combined_message = "我找到了以下信息：\n\n" + "\n\n".join(result_texts)
        
        return {
            "message": combined_message
        }

class A2ALangGraphIntegration:
    """A2A集成类 - 使LangGraph作为A2A服务的一个工具"""
    
    def __init__(self, server_url: str = "http://localhost:8001"):
        """初始化集成"""
        self.server_url = server_url
        self.task_manager = None
        self.langgraph_adapter = None
        self.tool_orchestrator = A2AToolOrchestrator()  # 新增：工具编排器
        self.initialized = False
        self.use_server = True  # 是否使用A2A服务器
        
    async def initialize(self):
        """异步初始化组件"""
        if self.initialized:
            return True
            
        # 导入任务管理器
        try:
            # 使用延迟导入以避免循环引用
            from .a2a_task_manager import get_instance as get_task_manager
            self.task_manager = get_task_manager()
            logger.info("任务管理器初始化成功")
            
            # 确保A2A服务器正在运行
            self.use_server = await self._ensure_a2a_server()
            
            # 初始化工具编排器
            await self.tool_orchestrator.initialize()
            
            # 注册工具到编排器
            await self._register_tools()
            
            # 获取LangGraph适配器 - 延迟导入避免循环引用
            # 注意：我们在确认初始化时才获取langgraph_adapter
            self.initialized = True
            logger.info(f"A2A-LangGraph集成初始化完成，使用{'A2A服务器' if self.use_server else '本地'}模式")
            return True
        except Exception as e:
            logger.error(f"初始化失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _register_tools(self):
        """注册工具到编排器"""
        # 注册A2A工具
        try:
            from .a2a_adapter import create_a2a_tools
            a2a_tools = await create_a2a_tools(self.server_url)
            if a2a_tools:
                for tool in a2a_tools:
                    self.tool_orchestrator.register_tool(tool)
        except Exception as e:
            logger.error(f"注册A2A工具失败: {str(e)}")
        
        # 注册本地工具 - 暂缓实现，未来可添加
    
    async def _ensure_a2a_server(self):
        """确保A2A服务器正在运行"""
        try:
            # 检查服务器是否运行
            response = requests.get(f"{self.server_url}/a2a/health", timeout=1)
            if response.status_code == 200:
                logger.info("A2A服务器已运行")
                return True
        except:
            logger.warning("A2A服务器未运行或无法连接，将使用本地模式")
            return False
        
        return False
    
    async def process_query(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        处理用户查询，使用工具编排器协调多个工具
        
        Args:
            query: 用户查询文本
            session_id: 会话ID
            
        Returns:
            处理结果字典
        """
        if not self.initialized:
            success = await self.initialize()
            if not success:
                return {"error": "初始化失败，无法处理查询"}
        
        # 如果没有会话ID，创建一个
        if not session_id:
            session_id = f"session_{str(uuid.uuid4())}"
        
        # 使用工具编排器执行任务链
        try:
            logger.info(f"[A2ALangGraphIntegration] 使用工具编排器处理查询: {query[:30]}...")
            result = await self.tool_orchestrator.execute_task_chain(query, session_id)
            return result
        except Exception as e:
            logger.error(f"工具编排器执行失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 如果工具编排器失败，尝试回退到老方法
            logger.warning("回退到传统模式处理查询")
            
            if self.use_server:
                # 使用A2A服务器处理查询
                try:
                    task_id = await self._send_task(query, session_id)
                    if not task_id:
                        return {"error": "发送任务失败"}
                        
                    # 轮询任务状态
                    result = await self._poll_task_status(task_id)
                    return result
                except Exception as e2:
                    logger.error(f"A2A服务器处理查询出错: {str(e2)}")
                    logger.warning("切换到本地模式处理查询")
                    # 出错时切换到本地模式
                    self.use_server = False
            
            # 本地模式 - 使用LangGraph适配器直接处理
            try:
                logger.info("使用本地LangGraph处理查询")
                if not self.langgraph_adapter:
                    # 延迟导入，避免循环引用
                    from .langgraph_adapter import get_instance as get_langgraph_adapter
                    self.langgraph_adapter = get_langgraph_adapter()
                    logger.info("LangGraph适配器延迟加载成功")
                    
                # 创建任务ID
                task_id = str(time.time())
                if not session_id:
                    session_id = f"session_{task_id}"
                    
                # 创建任务(如果任务管理器可用)
                if self.task_manager:
                    await self.task_manager.create_task(task_id, query, session_id)
                    await self.task_manager.update_task_status(task_id, "working", "使用LangGraph处理中")
                
                # 使用LangGraph处理查询
                lang_result = self.langgraph_adapter.process_query(query, session_id=session_id)
                
                # 更新任务状态
                if self.task_manager:
                    await self.task_manager.update_task_status(task_id, "completed")
                    # 添加任务结果
                    await self.task_manager.update_task_artifacts(task_id, [{
                        "parts": [{"type": "text", "text": lang_result.get("response", "")}],
                        "index": 0
                    }])
                
                return {
                    "task_id": task_id,
                    "response": lang_result.get("response", ""),
                    "status": "completed",
                    "processed_by": "langgraph_local"
                }
            except Exception as e3:
                logger.error(f"本地LangGraph处理失败: {str(e3)}")
                import traceback
                logger.error(traceback.format_exc())
                
                return {
                    "error": str(e),
                    "status": "failed"
                }
    
    async def _send_task(self, query: str, session_id: Optional[str] = None) -> Optional[str]:
        """发送任务到A2A服务器"""
        payload = {
            "jsonrpc": "2.0",
            "method": "invoke",
            "params": {
                "query": query,
                "id": f"task_{int(time.time())}",
                "sessionId": session_id or f"session_{int(time.time())}",
                "acceptedOutputModes": ["text"],
                "inputMode": "text"
            },
            "id": f"call_{int(time.time())}"
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.server_url}/a2a/jsonrpc",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
            )
            
            if response.status_code == 200:
                data = response.json()
                if "result" in data and "task_id" in data["result"]:
                    return data["result"]["task_id"]
            
            logger.error(f"发送任务失败: {response.text}")
            return None
        except Exception as e:
            logger.error(f"发送任务出错: {str(e)}")
            return None
    
    async def _poll_task_status(self, task_id: str, max_retries: int = 30, delay: float = 1.0) -> Dict[str, Any]:
        """轮询任务状态"""
        retries = 0
        tool_name = "langgraph"  # 默认工具名称
        
        while retries < max_retries:
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.get(
                        f"{self.server_url}/a2a/task/{tool_name}/{task_id}",
                        timeout=10
                    )
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "result" in data:
                        task_data = data["result"]
                        status = task_data.get("status", {}).get("state")
                        
                        if status in ["completed", "failed", "canceled"]:
                            # 提取结果文本
                            result_text = ""
                            if "artifacts" in task_data and task_data["artifacts"]:
                                for artifact in task_data["artifacts"]:
                                    if "parts" in artifact:
                                        for part in artifact["parts"]:
                                            if part.get("type") == "text" and "text" in part:
                                                result_text += part["text"]
                            
                            return {
                                "task_id": task_id,
                                "response": result_text,
                                "status": status,
                                "processed_by": "a2a_server"
                            }
                
                # 未完成，继续等待
                await asyncio.sleep(delay)
                retries += 1
            except Exception as e:
                logger.error(f"获取任务状态出错: {str(e)}")
                await asyncio.sleep(delay)
                retries += 1
        
        # 超过最大尝试次数
        return {
            "task_id": task_id,
            "error": "查询超时",
            "status": "failed"
        }
            
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        if not self.initialized:
            await self.initialize()
            
        if not self.use_server:
            if self.task_manager:
                task = await self.task_manager.get_task(task_id)
                if task:
                    return {"result": task.to_dict()}
            return {"error": "任务不存在或本地模式不支持任务状态查询"}
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    f"{self.server_url}/a2a/task/langgraph/{task_id}",
                    timeout=10
                )
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"获取任务状态失败: HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"获取任务状态出错: {str(e)}")
            return {"error": str(e)}
            
# 单例实例
_instance = None
_instance_lock = threading.Lock()

def get_instance():
    """获取集成单例"""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = A2ALangGraphIntegration()
            # 初始化 (异步函数需要在调用时await)
    return _instance

def process_query_sync(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """同步处理查询方法(用于非异步环境)"""
    integration = get_instance()
    
    # 创建事件循环并执行异步操作
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(integration.process_query(query, session_id))
        return result
    except Exception as e:
        logger.error(f"同步处理查询时出错: {str(e)}")
        return {"error": str(e)}
    finally:
        loop.close() 