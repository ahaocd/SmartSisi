"""
Sisi Agent协调器 - 实现多模型并行/异步处理
提升响应速度和处理灵活性
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
import traceback
import threading
import uuid
import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Dict, List, Any, Optional  # 添加必要的类型导入

import utils.config_util as cfg
from langchain.tools import BaseTool
from llm import agent_llm
from llm import liusisi
from llm.agent.sisi_agent import SisiAgentCore, get_instance as get_agent_instance
from llm.agent.langgraph_adapter import get_instance as get_langgraph_adapter
from utils import util

# 全局单例对象
_COORDINATOR_INSTANCE = None

def get_coordinator():
    """获取AgentCoordinator单例实例
    
    Returns:
        AgentCoordinator: 协调器实例
    """
    global _COORDINATOR_INSTANCE
    if _COORDINATOR_INSTANCE is None:
        _COORDINATOR_INSTANCE = AgentCoordinator()
    return _COORDINATOR_INSTANCE

class AgentCoordinator:
    """
    代理协调器：协调对话模型和Agent模型的双轨处理
    """
    
    def __init__(self, use_websocket=True):
        self.processing_tasks = {}  # 存储正在处理的任务
        self.model_map = {}
        self.use_websocket = use_websocket
        self.agent_module = "agent_llm"  # 默认使用agent_llm模块处理Agent请求
        # 创建一个线程池执行器，用于异步任务处理
        self.executor = ThreadPoolExecutor(max_workers=5)
        
        # 初始化事件循环属性
        self.loop = None
        
        # 添加skip_audio属性，修复"skip_audio"属性缺失问题
        self.skip_audio = False
        
        # 初始化agent_model为None，避免未定义错误
        self.agent_model = None
        
        # 添加信号量，控制并发
        self.semaphore = threading.Semaphore(1)
        
        # 尝试获取(不是加载)模型单例
        try:
            # agent模型 - 使用单例模式
            self.agent_model = get_agent_instance()
            # 增加self.agent别名，指向同一个对象
            self.agent = self.agent_model
            util.log(1, f"[协调器] Agent模型(AGENTSS)获取成功")
        except Exception as e:
            util.log(2, f"[协调器] Agent模型(AGENTSS)获取失败：{repr(e)}")
        
        # 初始化LangGraph适配器 - 使用单例模式
        try:
            self.langgraph_adapter = get_langgraph_adapter()
            util.log(1, f"[协调器] LangGraph适配器获取成功")
        except Exception as e:
            util.log(2, f"[协调器] LangGraph适配器获取失败：{str(e)}")
            self.langgraph_adapter = None
            
        # 移除自动播放和QA配置加载，这些功能应由独立组件处理
        
        # 记录请求编号
        self._request_number = 0
        
        # 特殊场景词配置 - 这些词需要特殊处理
        self.scene_keywords = {
            '开场白': True,      # 开场白在数据返回前播放
            '问候语': True,      # 问候语在数据返回前播放
            '介绍': False,       # 介绍在返回数据时播放
            '场景词': False,     # 场景词在返回数据时播放
            '故事': False,       # 故事在返回数据时播放
            '笑话': False        # 笑话在返回数据时播放
        }
        
        # 处理日志
        self.processing_logs = {}
        
        # 初始化未完成的Agent任务字典
        self._pending_agent_tasks = {}
    
    async def process_request(self, text, uid=0, observation="", stream_callback=None, nlp_response=None):
        """
        处理用户请求，双轨架构核心实现
        
        Args:
            text: 用户输入的文本
            uid: 用户ID
            observation: 观察信息
            stream_callback: 流式回调函数
            nlp_response: 已有的对话模型处理结果，如果提供则不再调用对话模型
            
        Returns:
            Tuple: (响应文本, 语气风格)
        """
        from llm import liusisi
        
        start_time = time.time()
        util.log(1, f"[协调器] 使用{'WebSocket流式响应' if stream_callback else '非流式响应'}, 对话模型处理: {text[:30] if isinstance(text, str) else text}...")
        
        # 如果提供了已有的对话模型结果，保存到实例变量
        if nlp_response:
            self._nlp_response = nlp_response
            util.log(1, f"[协调器] 接收到已处理的对话模型结果: {nlp_response[0][:30]}...")
        else:
            self._nlp_response = None
        
        response = ""
        style = "gentle"
        
        # 创建结果容器和事件标志
        nlp_result = {"done": False, "response": "", "style": "gentle", "error": None}
        agent_result = {"done": False, "response": "", "style": "gentle", "error": None}
        langgraph_result = {"done": False, "response": "", "style": "gentle", "error": None}
        nlp_done_event = asyncio.Event()
        agent_done_event = asyncio.Event()
        langgraph_done_event = asyncio.Event()
        
        # 记录是否需要Agent处理的标志
        agent_required = False
        langgraph_required = False
        
        # 移除关键词硬编码判断，让模型自主决定是否需要工具
        # 通过配置或上下文决定是否使用工具，不再依赖硬编码关键词
        might_need_tool = True  # 默认启用工具调用能力，由模型判断是否需要使用
        
        # 为每个请求创建一个唯一的ID用于追踪
        request_id = f"req_{int(time.time() * 1000)}"
        util.log(1, f"[协调器] 请求ID: {request_id} - 开始处理")
        
        # 获取或创建事件循环，避免"事件循环已运行"错误
        try:
            # 安全获取事件循环
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # 如果没有运行中的事件循环，创建一个新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 确保我们有一个有效的循环
            if loop is None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
                self.loop = loop
        except Exception as e:
            util.log(2, f"[协调器] 事件循环初始化异常: {str(e)}")
            # 在出错的情况下，回退到同步处理
            return self.process_request_sync(text, nlp_response, uid)
        
        # 1. 对话模型处理 (优先处理部分)
        async def process_nlp():
            nonlocal nlp_result
            try:
                # 如果已经有对话模型(7B)的处理结果，则直接使用，不需要重复调用对话模型
                if hasattr(self, '_nlp_response') and self._nlp_response:
                    util.log(1, f"[协调器] 使用已有的对话模型结果，跳过重复调用")
                    nlp_text, nlp_style = self._nlp_response
                    
                    # 更新结果
                    nlp_result["response"] = nlp_text
                    nlp_result["style"] = nlp_style
                    
                    # 如果有流式回调，发送对话模型响应
                    if stream_callback:
                        try:
                            if inspect.iscoroutinefunction(stream_callback):
                                await stream_callback(nlp_text)
                            else:
                                stream_callback(nlp_text)
                            util.log(1, f"[协调器] 流式回调成功执行")
                        except Exception as e:
                            util.log(2, f"[协调器] 流式回调异常: {str(e)}")
                            traceback.print_exc()
                        return
                
                # 直接使用对话模型处理，不等待Agent结果
                # 这是双轨架构的核心 - 对话模型需要迅速响应
                nlp_start_time = time.time()
                util.log(1, f"[协调器] 使用常规对话模型方法: liusisi.chat")
                
                # 设置较短的超时(10秒)，确保对话模型能快速响应
                try:
                    # 创建异步任务
                    nlp_task = asyncio.create_task(
                        asyncio.wait_for(
                            asyncio.to_thread(
                                liusisi.question, 
                                text, 
                                uid, 
                                self.skip_audio
                            ),
                            timeout=30.0  # 增加超时时间从3秒到30秒，减少超时风险
                        )
                    )
                    
                    # 等待结果
                    nlp_response = await nlp_task
                    
                    nlp_end_time = time.time()
                    util.log(1, f"[协调器] 对话模型响应耗时: {nlp_end_time - nlp_start_time:.2f}秒, 结果类型: {type(nlp_response)}")
                    
                    # 提取响应和样式
                    if isinstance(nlp_response, tuple) and len(nlp_response) >= 2:
                        nlp_text, nlp_style = nlp_response[0], nlp_response[1]
                        util.log(1, f"[协调器] 对话模型响应: {nlp_response}, 提取文本: {nlp_text[:50] if isinstance(nlp_text, str) else nlp_text}...")
                        
                        # 更新结果
                        nlp_result["response"] = nlp_text
                        nlp_result["style"] = nlp_style
                        
                        # 如果有流式回调，发送对话模型响应
                        if stream_callback:
                            try:
                                if inspect.iscoroutinefunction(stream_callback):
                                    await stream_callback(nlp_text)
                                else:
                                    stream_callback(nlp_text)
                                util.log(1, f"[协调器] 流式回调成功执行")
                            except Exception as e:
                                util.log(2, f"[协调器] 流式回调异常: {str(e)}")
                                traceback.print_exc()
                    else:
                        util.log(2, f"[协调器] 对话模型返回格式异常: {nlp_response}")
                        nlp_result["response"] = str(nlp_response) if nlp_response else "对话模型未返回有效响应"
                        nlp_result["error"] = "格式错误"
                
                except asyncio.TimeoutError:
                    util.log(2, f"[协调器] 对话模型响应超时(>30秒)")
                    nlp_result["response"] = "抱歉，我需要多一点时间思考..."
                    nlp_result["error"] = "超时"
                
                except Exception as e:
                    util.log(2, f"[协调器] 对话模型处理异常: {str(e)}")
                    traceback.print_exc()
                    nlp_result["response"] = f"对话处理出现问题: {str(e)}"
                    nlp_result["error"] = str(e)
            
            finally:
                # 标记对话模型处理完成
                nlp_result["done"] = True
                nlp_done_event.set()
        
        # 2. Agent模型处理 (后台处理部分)
        async def process_agent():
            nonlocal agent_result, agent_required
            try:
                # 如果预判断不需要工具，可以跳过Agent处理
                if not might_need_tool:
                    util.log(1, f"[协调器] 预判断不需要工具，跳过Agent处理")
                    agent_result["response"] = "无需工具处理"
                    return
                
                # 后台启动Agent处理
                agent_start_time = time.time()
                util.log(1, f"[协调器] 后台Agent处理: {text[:30] if isinstance(text, str) else text}...")
                
                # 调用Agent模块处理请求
                try:
                    # 直接从agent_llm模块导入并使用，避免递归调用
                    from llm import agent_llm
                    
                    # 添加详细日志
                    util.log(1, f"[协调器] 开始处理请求...")
                    
                    # 将NLP结果传递给agent_llm
                    nlp_text, nlp_style = nlp_result
                    # 直接使用agent_llm模块的方法，避免递归调用self.process_request
                    agent_response, agent_style = agent_llm.chat(text, uid, observation, nlp_result=(nlp_text, nlp_style))
                    agent_end_time = time.time()
                    util.log(1, f"[协调器] Agent处理完成，耗时: {agent_end_time - agent_start_time:.2f}秒")
                    
                    # 检查是否有$SKIP$标记
                    if agent_response and agent_response.startswith("$SKIP$"):
                        util.log(1, f"[协调器] 检测到$SKIP$标记，Agent决定不回复")
                        # 使用NLP结果
                        agent_result["response"] = "无需Agent补充"
                        agent_result["style"] = "skip"
                    elif agent_response and "需要使用" in agent_response:
                        # 标记此请求需要Agent处理
                        agent_required = True
                        util.log(1, f"[协调器] 发现已完成的Agent任务，结果: {agent_response[:50] if isinstance(agent_response, str) else agent_response}...")
                        
                        # 更新结果
                        agent_result["response"] = agent_response
                        agent_result["style"] = agent_style
                        
                        # 如果有流式回调，发送Agent响应
                        if stream_callback:
                            try:
                                if inspect.iscoroutinefunction(stream_callback):
                                    # 在后台线程中无法直接调用协程，使用事件循环
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        # 使用run_coroutine_threadsafe处理协程
                                        future = asyncio.run_coroutine_threadsafe(
                                            stream_callback(agent_response), 
                                            loop
                                        )
                                        # 等待结果但设置超时
                                        future.result(timeout=30)
                                        util.log(1, f"[协调器] 异步流回调函数调用成功")
                                    except Exception as async_e:
                                        util.log(2, f"[协调器] 异步回调异常: {str(async_e)}")
                                    finally:
                                        loop.close()
                            except Exception as e:
                                util.log(2, f"[协调器] Agent流式回调异常: {str(e)}")
                                traceback.print_exc()
                    else:
                        # Agent未给出需要执行的工具
                        util.log(1, f"[协调器] Agent未检测到需要执行的工具")
                        agent_result["response"] = "无需工具处理"
                
                except Exception as e:
                    util.log(2, f"[协调器] Agent处理异常: {str(e)}")
                    traceback.print_exc()
                    agent_result["response"] = f"Agent处理出现问题: {str(e)}"
                    agent_result["error"] = str(e)
            
            finally:
                # 标记Agent处理完成
                agent_result["done"] = True
                agent_done_event.set()
        
        # 3. LangGraph工具调用处理 (并行处理部分)
        async def process_langgraph():
            nonlocal langgraph_result, langgraph_required
            try:
                # 检查是否有LangGraph适配器
                if self.langgraph_adapter is None:
                    util.log(1, f"[协调器] LangGraph适配器未初始化，跳过处理")
                    langgraph_result["response"] = "LangGraph适配器未初始化"
                    return
                
                # 检查是否预判断需要工具调用
                if not self.langgraph_adapter.should_use_tool_calling(text):
                    util.log(1, f"[协调器] 预判断不需要工具调用，跳过LangGraph处理")
                    langgraph_result["response"] = "无需工具调用"
                    return
                
                # 开始LangGraph处理
                langgraph_start_time = time.time()
                util.log(1, f"[协调器] LangGraph处理: {text[:30] if isinstance(text, str) else text}...")
                
                # 调用LangGraph适配器处理请求
                try:
                    lg_result = self.langgraph_adapter.process_query(text, uid, observation)
                    langgraph_end_time = time.time()
                    util.log(1, f"[协调器] LangGraph处理完成，耗时: {langgraph_end_time - langgraph_start_time:.2f}秒")
                    
                    # 检查是否有工具调用
                    has_tool_calls = lg_result.get("has_tool_calls", False)
                    
                    if has_tool_calls:
                        # 标记此请求需要LangGraph处理
                        langgraph_required = True
                        util.log(1, f"[协调器] 发现LangGraph工具调用，结果: {lg_result.get('response', '')[:50] if isinstance(lg_result.get('response', ''), str) else lg_result.get('response', '')}...")
                        
                        # 更新结果
                        langgraph_result["response"] = lg_result.get("response", "")
                        langgraph_result["style"] = "gentle"
                        
                        # 如果有流式回调，发送LangGraph响应
                        if stream_callback:
                            try:
                                if inspect.iscoroutinefunction(stream_callback):
                                    await stream_callback(lg_result.get("response", ""))
                                else:
                                    stream_callback(lg_result.get("response", ""))
                                util.log(1, f"[协调器] LangGraph流式回调成功执行")
                            except Exception as e:
                                util.log(2, f"[协调器] LangGraph流式回调异常: {str(e)}")
                                traceback.print_exc()
                    else:
                        # LangGraph未使用工具
                        util.log(1, f"[协调器] LangGraph未检测到工具调用，无需进一步处理")
                        langgraph_result["response"] = "无需工具调用"
                
                except Exception as e:
                    util.log(2, f"[协调器] LangGraph处理异常: {str(e)}")
                    traceback.print_exc()
                    langgraph_result["response"] = f"LangGraph处理出现问题: {str(e)}"
                    langgraph_result["error"] = str(e)
            
            finally:
                # 标记LangGraph处理完成
                langgraph_result["done"] = True
                langgraph_done_event.set()
        
        try:
            # 并行启动三个处理任务
            nlp_task = asyncio.create_task(process_nlp())
            agent_task = asyncio.create_task(process_agent())
            langgraph_task = asyncio.create_task(process_langgraph())
            
            # 优先等待对话模型完成 - 这是关键 - 确保对话模型先返回
            await nlp_done_event.wait()
            
            # 获取对话模型结果
            response = nlp_result["response"]
            style = nlp_result["style"]
            
            # 如果有错误，记录错误信息
            if nlp_result["error"]:
                util.log(2, f"[协调器] 对话模型错误: {nlp_result['error']}")
            
            # 记录总处理时间
            end_time = time.time()
            util.log(1, f"[协调器] 总处理时间: {end_time - start_time:.2f}秒")
            
            # 返回对话模型的结果
            # 注意：Agent和LangGraph的结果会通过流式回调发送
            return response, style
            
        except Exception as e:
            util.log(2, f"[协调器] 处理请求异常: {str(e)}")
            traceback.print_exc()
            return f"处理请求出现问题: {str(e)}", "gentle"
    
    def process_request_sync(self, text, uid=0, observation="", stream_callback=None, nlp_result=None):
        """同步处理请求
        
        Args:
            text: 用户请求文本
            uid: 用户ID，用于跟踪对话历史
            observation: 环境观察数据
            stream_callback: 流式回调函数
            nlp_result: NLP模型生成的结果（可选），格式为(文本,风格)
            
        Returns:
            Tuple[str, str] or None: (回复文本, 语气风格)或None表示中转站已处理
        """
        
        # 记录处理开始时间
        start_time = time.time()
        
        # 日志记录
        util.log(1, f"[Agent协调器] 开始同步处理请求，已有NLP结果：{'是' if nlp_result else '否'}")
        
        # 使用信号量控制并发
        with self.semaphore:
            try:
                # 提取配置参数
                config = {
                    "configurable": {
                        "thread_id": f"user_{uid}_{int(time.time())}"  # 提供唯一的thread_id
                    }
                }
                
                # 智能决策处理流程
                # 不再尝试重建Agent工作流，而是直接在invoke方法中处理NLP结果
                # Agent将基于NLP结果进行增强或补充，而不是直接替换
                
                # 调用Agent处理，传递NLP结果
                response = self._run_agent_with_timeout(
                    text=text,
                    uid=uid,
                    config=config,
                    timeout=50,
                    nlp_result=nlp_result  # 传递完整的NLP结果
                )
                
                # 如果返回None，表示已由中转站处理完成，不需要再处理
                if response is None:
                    util.log(1, f"[Agent协调器] 中转站已处理完成，返回None表示无需SmartSisi核心处理")
                    return None, None  # 返回None,None而不是None，避免解包错误
                
                # 记录处理完成
                end_time = time.time()
                util.log(1, f"[Agent协调器] 请求处理完成，耗时: {end_time - start_time:.2f}秒，是否由Agent处理: True")
                
                # 返回结果
                return response
            except Exception as e:
                # 记录错误
                end_time = time.time()
                util.log(2, f"[Agent协调器] 处理请求出错: {str(e)}")
                import traceback
                util.log(2, f"[Agent协调器] 错误详情: {traceback.format_exc()}")
                
                # 如果有NLP结果，在错误情况下回退到NLP结果
                if nlp_result:
                    util.log(1, f"[Agent协调器] Agent处理失败，回退到NLP结果")
                    if isinstance(nlp_result, tuple):
                        return nlp_result
                    return nlp_result, "gentle"
                
                # 返回错误消息
                return f"处理请求时发生错误: {str(e)}", "error"

    def _run_agent_with_timeout(self, text, uid, config, timeout=50, nlp_result=None):
        """使用超时机制运行Agent处理
        
        Args:
            text: 用户请求文本
            uid: 用户ID
            config: 额外配置参数
            timeout: 超时时间（秒）
            nlp_result: NLP模型生成的结果（可选）
            
        Returns:
            Tuple[str, str]: (回复文本, 语气风格)
        """
        try:
            # 直接调用agent处理
            result = self.agent_model.invoke(
                text=text,
                uid=uid,
                config=config,
                nlp_result=nlp_result  # 传递完整的NLP结果
            )
            
            # 如果返回None，表示已由中转站处理完毕
            if result is None:
                util.log(1, f"[Agent协调器] 中转站已完全处理，跳过后续流程")
                return None
                
            # 正常返回结果
            return result
            
        except TimeoutError:
            util.log(1, f"[Agent协调器] 处理请求超时，超过{timeout}秒")
            return "很抱歉，您的问题比较复杂，我需要更多时间思考。请稍后再试或尝试简化您的问题。", "gentle"
        except Exception as e:
            import traceback
            util.log(2, f"[Agent协调器] 运行Agent处理时出错: {str(e)}")
            util.log(2, f"[Agent协调器] 错误详情: {traceback.format_exc()}")
            return f"处理您的请求时出现错误: {str(e)}", "error"

    def _process_agent_in_background(self, text, uid=0, observation="", stream_callback=None):
        """在后台线程中处理Agent请求"""
        thread_id = threading.get_ident()
        util.log(1, f"[协调器] Agent模型类型: {type(self.agent_model).__name__}")
        util.log(1, f"[协调器] ====== 开始后台Agent处理 ======")
        
        try:
            # 清理输入文本中可能存在的模型标记
            text = self._clean_model_tags(text)
            
            # 记录处理开始时间
            agent_start_time = time.time()
            util.log(1, f"[协调器] 调用agent_model.chat方法...")
            
            # 直接调用Agent模型处理请求
            if hasattr(self.agent_model, 'chat'):
                # 使用O3 MINI模型处理
                agent_response, agent_style = self.agent_model.chat(text, uid, observation)
            else:
                # 回退到process_agent_request
                from llm import agent_llm
                agent_response, agent_style = agent_llm.process_agent_request(text)
                
            # 清理输出文本中可能存在的模型标记
            if agent_response and isinstance(agent_response, str):
                agent_response = self._clean_model_tags(agent_response)
                
            # 计算处理耗时
            agent_time = time.time() - agent_start_time
            
            if isinstance(agent_response, str) and isinstance(agent_style, str):
                util.log(1, f"[协调器] Agent处理完成，耗时: {agent_time:.2f}秒")
                
                # 检查响应类型和内容
                util.log(1, f"[协调器] Agent返回类型: {type(agent_response)}, 内容预览: '{agent_response[:100]}'")
                
                # 如果有回调函数，发送Agent的响应
                if stream_callback:
                    try:
                        if inspect.iscoroutinefunction(stream_callback):
                            # 在后台线程中无法直接调用协程，使用事件循环
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                # 使用run_coroutine_threadsafe处理协程
                                future = asyncio.run_coroutine_threadsafe(
                                    stream_callback(agent_response), 
                                    loop
                                )
                                # 等待结果但设置超时
                                future.result(timeout=30)
                                util.log(1, f"[协调器] 异步流回调函数调用成功")
                            except Exception as async_e:
                                util.log(2, f"[协调器] 异步回调异常: {str(async_e)}")
                            finally:
                                loop.close()
                        else:
                            # 非协程函数直接调用
                            stream_callback(agent_response)
                            util.log(1, f"[协调器] 同步流回调函数调用成功")
                    except Exception as e:
                        util.log(2, f"[协调器] 流回调函数调用失败: {str(e)}")
                        traceback.print_exc()
            else:
                util.log(2, f"[协调器] Agent响应格式错误: {type(agent_response)}")
                
            # 记录总处理时间
            total_agent_time = time.time() - agent_start_time
            util.log(1, f"[协调器] ====== 后台Agent处理完成，总耗时: {total_agent_time:.2f}秒 ======")
            
        except Exception as e:
            # 详细记录异常信息
            import traceback
            stack_trace = traceback.format_exc()
            util.log(3, f"[协调器] 后台Agent处理异常: {str(e)}\n{stack_trace}")
            
            # 如果有回调，发送错误信息
            if stream_callback:
                try:
                    error_message = f"处理请求时出现错误: {str(e)}"
                    if inspect.iscoroutinefunction(stream_callback):
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            # 使用run_coroutine_threadsafe处理协程
                            future = asyncio.run_coroutine_threadsafe(
                                stream_callback(error_message), 
                                loop
                            )
                            # 等待结果但设置超时
                            future.result(timeout=30)
                        except Exception as async_e:
                            util.log(3, f"[协调器] 异步错误回调异常: {str(async_e)}")
                        finally:
                            loop.close()
                    else:
                        # 非协程函数直接调用
                        stream_callback(error_message)
                        util.log(3, f"[协调器] 同步错误回调完成")
                except Exception as callback_error:
                    util.log(3, f"[协调器] 错误回调异常: {str(callback_error)}")
                    traceback.print_exc()
    
    def _is_command_request(self, text: str) -> bool:
        """
        判断是否是命令请求 - 已弃用
        新的流程依赖Agent自己决定是否需要调用工具
        
        这个方法仅作为兼容性保留，始终返回True以传递所有请求给Agent
        
        Args:
            text: 用户输入文本
            
        Returns:
            bool: 始终返回True
        """
        # 不再使用硬编码关键词，由Agent自己判断
        return True
    
    def _process_langgraph_in_background(self, text, uid=0, observation="", stream_callback=None):
        """
        在后台处理LangGraph工具调用请求，不阻塞主流程
        
        Args:
            text: 用户输入文本
            uid: 用户ID
            observation: 可选的观察信息
            stream_callback: 流式回调函数
            
        Returns:
            str: LangGraph处理结果
        """
        try:
            util.log(1, f"[协调器] ====== 开始后台LangGraph处理 ======")
            util.log(1, f"[协调器] 调用LangGraph适配器处理请求，输入：'{text[:50]}...'")
            
            # 调用LangGraph适配器处理请求
            start_time = time.time()
            result = self.langgraph_adapter.process_query(text, uid, observation)
            end_time = time.time()
            
            util.log(1, f"[协调器] 后台LangGraph处理完成，耗时: {end_time - start_time:.2f}秒")
            
            # 检查是否有工具调用结果
            if result.get("has_tool_calls", False):
                response = result.get("response", "")
                
                # 如果有流式回调，发送结果
                if stream_callback and response:
                    try:
                        stream_callback(response)
                    except Exception as e:
                        util.log(2, f"[协调器] LangGraph结果流式回调异常: {str(e)}")
                
                # 记录未完成任务（如果有必要）
                task_id = f"langgraph_{int(time.time()*1000)}"
                self._pending_agent_tasks[task_id] = {
                    "uid": uid,
                    "text": text,
                    "result": response,
                    "time": time.time()
                }
                
                return response
            else:
                util.log(1, f"[协调器] LangGraph未检测到工具调用，无需进一步处理")
                return None
                
        except Exception as e:
            util.log(2, f"[协调器] 后台LangGraph处理异常: {str(e)}")
            traceback.print_exc()
            return f"LangGraph处理出现问题: {str(e)}"

    def _clean_model_tags(self, text):
        """清理文本中的模型标记"""
        if not text or not isinstance(text, str):
            return text
            
        # 定义需要清理的模型标记
        model_tags = [
            "[NLP-7B]", "[Agent-O3]", "[Agent-O3错误]", 
            "[LLM]", "[Agent]", "[GPT]", "[AI]"
        ]
        
        # 移除所有模型标记
        cleaned_text = text
        for tag in model_tags:
            cleaned_text = cleaned_text.replace(tag, "").strip()
            
        # 如果进行了清理，记录到日志
        if cleaned_text != text:
            util.log(1, f"[协调器] 清理了模型标记: {text[:30]} -> {cleaned_text[:30]}")
            
        return cleaned_text


