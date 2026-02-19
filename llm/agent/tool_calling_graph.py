"""
使用LangGraph框架实现工具调用图
这个模块与现有的快速响应NLP系统并行工作，处理需要工具调用的复杂任务
"""

import os
import logging
import json
import sys
import time
import traceback
from typing import List, Dict, Any, Optional, Tuple, Union, Annotated, TypedDict, Sequence, Callable, cast

# 添加本地langgraph项目到Python路径
sys.path.append('e:/liusisi')

# LangGraph导入
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

# 创建兼容的MessageState类 - 由于导入问题
class MessageState(TypedDict):
    """兼容LangGraph的消息状态"""
    messages: List  # 消息列表
    
# 修正导入路径
from llm.agent.tool_node import ToolNode

# 添加MemorySaver导入
from langgraph.checkpoint.memory import MemorySaver

# 导入cast_state_schema或定义兼容函数
def cast_state_schema(schema_type):
    """将类型转换为图状态模式"""
    # 实际上，这应该使用LangGraph的cast_to函数
    # 但我们这里提供一个简单实现作为兼容层
    return schema_type

# 自定义tools_condition函数
def tools_condition(state):
    """
    检查最后一条消息是否包含工具调用
    
    Args:
        state: Agent状态，包含消息列表
    
    Returns:
        bool: 如果有工具调用返回True，否则返回False
    """
    # 获取消息列表
    messages = state.get("messages", [])
    if not messages:
        return False
    
    # 检查最后一条消息是否为AI消息且包含工具调用
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return True
    
    return False

# 添加缺失的函数
def should_continue(state):
    """决定是否继续执行工具调用或结束对话"""
    # 简化的决策逻辑
    messages = state.get("messages", [])
    if not messages:
        return "end"
    
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"

def get_tool_calling_prompt(config, tool_descs):
    """创建工具调用提示"""
    system_prompt = config.get("system_prompt", """你是一个有用的AI助手。
当需要使用工具时，请使用提供的工具来完成任务。

重要提示：如果需要同时使用多个工具，请一次性列出所有需要的工具调用，使用以下JSON数组格式：
```json
[
  {"action": "工具名称1", "action_input": "输入参数1"},
  {"action": "工具名称2", "action_input": "输入参数2"}
]
```

单个工具调用请使用以下格式：
```json
{"action": "工具名称", "action_input": "输入参数"}
```

可用工具包括:
{tool_descriptions}
""").format(tool_descriptions="\n".join(tool_descs))
    
    return system_prompt

def create_runnable(llm, prompt):
    """创建可执行的节点"""
    def runnable(state):
        """LLM节点处理函数"""
        # 获取消息历史
        messages = state.get("messages", [])
        
        # 记录调用信息
        print(f"[ToolCallingGraph] LLM节点收到 {len(messages)} 条消息")
        
        # 调用llm处理逻辑
        try:
            # 这里应该调用实际的LLM
            # 简化实现，直接返回一个AIMessage
            from langchain_core.messages import AIMessage
            ai_message = AIMessage(content="我是Assistant，有什么可以帮助您的？")
            
            # 将AI消息添加到历史中
            messages.append(ai_message)
            return {"messages": messages}
        except Exception as e:
            print(f"[ToolCallingGraph] LLM调用出错: {str(e)}")
            # 返回错误消息
            from langchain_core.messages import AIMessage
            error_message = AIMessage(content=f"处理请求时出错: {str(e)}")
            messages.append(error_message)
            return {"messages": messages}
    
    return runnable

# LangChain导入
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage, FunctionMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

# 导入SmartSisi项目现有工具
from llm.agent.tools.Weather import Weather
from llm.agent.tools.TimeQuery import TimeQuery
from llm.agent.tools.ToRemind import ToRemind
from llm.agent.tools.QueryTimerDB import QueryTimerDB
from llm.agent.tools.DeleteTimer import DeleteTimer

# 导入项目工具函数
from utils import util
from utils import config_util as cfg
from llm.liusisi import question, chat

# 定义状态类型
class AgentState(TypedDict):
    """Agent状态定义"""
    messages: Annotated[List[BaseMessage], add_messages]
    observation: Optional[str]
    uid: int
    tools: List[BaseTool]
    meta: Dict[str, Any]

# 导入A2A工具节点
from llm.agent.a2a_adapter import A2AToolNode, create_a2a_tools

# 使用类型提示
ToolNodeType = Union[ToolNode, A2AToolNode]

class ToolCallingGraph:
    """基于LangGraph的工具调用图"""
    
    # 单例模式的实例变量
    _instance = None
    
    def __init__(self, config=None):
        """初始化工具调用图"""
        self.config = config or {}
        self.uid = 0
        self.observation = "无观测数据"
        
        # 加载配置
        cfg.load_config()
        
        # 初始化工具列表（这里已同时加载标准工具和A2A工具）
        self.tools = self._init_tools()
        
        # 创建内存存储 - 必须在构建图之前初始化
        self.memory = MemorySaver()
        self.thread_id = f"thread_{os.urandom(8).hex()}"
        
        # 创建工具节点
        self.tool_node = ToolNode(self.tools)
        
        # 创建模型实例 - 初始化空值，在构建图时实际创建
        self.llm = None
        
        # 构建状态图
        self.graph = self._build_graph()
        
        util.log(1, f"[ToolCallingGraph] 工具调用图已初始化，线程ID: {self.thread_id}")
    
    def _init_tools(self) -> List[BaseTool]:
        """初始化工具列表"""
        util.log(1, "[ToolCallingGraph] 🚀 开始初始化工具系统...")
        
        # 1. 加载本地工具
        tools = [
            Weather(),              # 天气查询工具
            TimeQuery(),            # 时间查询工具
            ToRemind(),             # 提醒工具
            QueryTimerDB(),         # 查询定时器数据库
            DeleteTimer()           # 删除定时器
        ]
        
        util.log(1, "📦 本地核心工具加载完成:")
        for i, tool in enumerate(tools, 1):
            util.log(1, f"  {i}. {tool.name}: {tool.description[:50]}...")
        
        # 2. 加载A2A工具并合并到工具列表中
        util.log(1, "[ToolCallingGraph] 🔗 正在检查A2A工具连接...")
        if self.config.get("a2a_server_url"):
            util.log(1, f"[ToolCallingGraph] 🌐 A2A服务器地址: {self.config['a2a_server_url']}")
            a2a_tools = create_a2a_tools(self.config["a2a_server_url"])
            if a2a_tools:
                tools.extend(a2a_tools)
                util.log(1, f"[ToolCallingGraph] ✅ 已加载 {len(a2a_tools)} 个A2A工具")
                for tool in a2a_tools:
                    util.log(1, f"[ToolCallingGraph]   - A2A工具: {tool.name}")
            else:
                util.log(1, "[ToolCallingGraph] ⚠️ 未发现任何A2A工具")
        else:
            util.log(1, "[ToolCallingGraph] ℹ️ 未配置A2A服务器，跳过A2A工具加载")
        
        # 输出工具加载总结
        util.log(1, f"[ToolCallingGraph] 📊 工具系统初始化完成！")
        util.log(1, f"[ToolCallingGraph] 🔧 总共加载 {len(tools)} 个工具:")
        for i, tool in enumerate(tools, 1):
            util.log(1, f"[ToolCallingGraph]   {i}. {tool.name}: {tool.description[:50]}...")
        
        util.log(1, f"[ToolCallingGraph] 🎯 可用工具列表: {', '.join(t.name for t in tools)}")
        return tools
    
    def _build_graph(self) -> StateGraph:
        """构建状态图"""
        # 创建状态图
        graph = StateGraph(MessageState)
        
        # 加载GPT模型
        from .model_adapter import SisiLLMAdapter
        from utils.config_util import Config 
        cfg = Config()
        
        self.llm = SisiLLMAdapter(model=cfg.get_value("model"), streaming=True)
        
        # 收集工具说明
        tools_desc = [f"{tool.name}: {tool.description}" for tool in self.tools]
        
        # 创建系统提示
        system_prompt = get_tool_calling_prompt(self.config, tools_desc)
        
        # 为LLM创建处理节点
        llm_node = create_runnable(self.llm, system_prompt)
        
        # 添加LLM节点
        graph.add_node("llm", llm_node)
        
        # 添加工具节点 - 标准工具节点已包含A2A工具
        graph.add_node("tools", self.tool_node)
        
        # 设置开始节点
        graph.set_entry_point("llm")
        
        # 添加条件边缘
        graph.add_conditional_edges(
            "llm",
            tools_condition,
            {
                True: "tools",  # 如果需要工具调用，转到工具节点
                False: END  # 如果不需要工具调用，结束
            }
        )
        
        # 从工具节点到LLM节点的边缘
        graph.add_edge("tools", "llm")
        
        # 添加节点转换监听
        @graph.on_transition()
        def log_transition(state, prev_step, current_step):
            """
            记录节点转换并向中转站发送中间状态
            
            Args:
                state: 当前状态
                prev_step: 前一个节点
                current_step: 当前节点
            """
            try:
                print(f"[ToolCallingGraph] 转换: {prev_step} -> {current_step}")
                util.log(1, f"[LG节点] 转换: {prev_step} -> {current_step}")
                
                # 向中转站发送状态转换信息和中间状态
                if prev_step != current_step:
                    try:
                        # 尝试导入中转站
                        from llm.transit_station import TransitStation
                        transit = TransitStation.get_instance()
                        
                        # 添加节点转换通知
                        transit.add_intermediate_state(
                            f"LangGraph节点转换: {prev_step} -> {current_step}",
                            "LG节点转换"
                        )
                        
                        # 根据不同节点类型，发送详细的中间状态信息
                        if current_step == "llm":
                            transit.add_intermediate_state("正在思考您的问题...", "LangGraph思考节点")
                            
                            # 获取上下文信息
                            messages = state.get("messages", [])
                            if messages and len(messages) > 0:
                                last_msg = messages[-1]
                                if hasattr(last_msg, "content"):
                                    msg_content = last_msg.content[:100] + ("..." if len(last_msg.content) > 100 else "")
                                    transit.add_intermediate_state(
                                        f"思考内容: {msg_content}",
                                        "LangGraph思考上下文"
                                    )
                                    
                        elif current_step == "tool_calling":
                            transit.add_intermediate_state("正在分析需要使用的工具...", "LangGraph工具选择节点")
                            
                        elif current_step == "tools":
                            # 提取工具信息
                            try:
                                messages = state.get("messages", [])
                                if messages:
                                    last_message = messages[-1]
                                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                                        tool_names = [t.get("name", "未知工具") for t in last_message.tool_calls]
                                        tool_list = ", ".join(tool_names)
                                        transit.add_intermediate_state(
                                            f"正在使用工具: {tool_list}",
                                            "LangGraph工具调用节点"
                                        )
                                        
                                        # 添加每个工具的详细信息
                                        for i, tool_call in enumerate(last_message.tool_calls):
                                            tool_name = tool_call.get("name", "未知工具")
                                            tool_args = tool_call.get("args", {})
                                            transit.add_intermediate_state(
                                                f"工具{i+1} - {tool_name}: {json.dumps(tool_args, ensure_ascii=False)}",
                                                "LangGraph工具详情"
                                            )
                            except Exception as tool_err:
                                print(f"[ToolCallingGraph] 提取工具信息出错: {str(tool_err)}")
                        
                        # 工具结果节点
                        elif current_step.startswith("tool_result"):
                            transit.add_intermediate_state("已获得工具结果，正在处理...", "LangGraph工具结果节点")
                            
                            # 尝试添加工具结果详情
                            try:
                                if state.get("observations"):
                                    result = state.get("observations")
                                    transit.add_intermediate_state(
                                        f"工具返回结果: {result[:200]}...",
                                        "LangGraph工具结果详情"
                                    )
                            except Exception as result_err:
                                print(f"[ToolCallingGraph] 提取工具结果出错: {str(result_err)}")
                    except Exception as transit_err:
                        print(f"[ToolCallingGraph] 中转站连接出错: {str(transit_err)}")
            except Exception as e:
                print(f"[ToolCallingGraph] 记录转换出错: {str(e)}")
                util.log(3, f"[LG节点] 转换出错: {str(e)}")
        
        # 编译图
        memory_graph = graph.compile()
        
        # 记录日志
        util.log(1, f"[ToolCallingGraph] 工具调用图已构建, {len(self.tools)} 个工具可用")
        
        return memory_graph
        
    def invoke(self, query: str, uid: int = 0, observation: str = None) -> Dict[str, Any]:
        """处理用户查询"""
        try:
            # 设置用户ID和观测数据
            self.uid = uid
            self.observation = observation or "无观测数据"
            
            # 准备初始状态
            initial_state = {
                "messages": [HumanMessage(content=query)],
                "uid": uid,
                "observation": self.observation,
                "tools": self.tools,
                "meta": {"query_time": time.time()}
            }
            
            # 调用图来处理查询
            result = self.graph.invoke(
                initial_state, 
                config={"configurable": {"thread_id": self.thread_id}}
            )
            
            # 提取响应内容
            messages = result.get("messages", [])
            if messages and len(messages) > 0:
                last_message = messages[-1]
                if isinstance(last_message, AIMessage):
                    return {
                        "response": last_message.content,
                        "has_tool_calls": hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0
                    }
            
            return {"response": "无法处理请求", "has_tool_calls": False}
            
        except Exception as e:
            util.log(3, f"[ToolCallingGraph] 处理查询时出错: {str(e)}")
            return {"response": f"处理查询时出错: {str(e)}", "has_tool_calls": False}

    @classmethod
    def get_instance(cls, config=None):
        """获取ToolCallingGraph单例"""
        if cls._instance is None:
            cls._instance = cls(config)
            util.log(1, f"[ToolCallingGraph] 创建新的工具调用图实例，配置: {config}")
        else:
            util.log(1, f"[ToolCallingGraph] 使用现有工具调用图实例")
        return cls._instance

def process_query(query: str, uid: int = 0, observation: str = None) -> Dict[str, Any]:
    """处理用户查询的便捷函数"""
    graph = ToolCallingGraph.get_instance()
    return graph.invoke(query, uid, observation)

def build_agent_graph():
    """
    构建LangGraph Agent图
    
    该图包含以下节点:
    - llm: 处理输入并决定下一步操作
    - tool_calling: 处理工具调用
    - end: 结束对话
    
    Returns:
        (compiled_graph, llm_node): 编译后的图和LLM节点的引用
    """
    # 创建状态图
    graph = StateGraph(AgentState)
    
    # 添加LLM节点
    graph.add_node("llm", llm_node)
    
    # 添加工具调用节点
    graph.add_node("tool_calling", tool_calling_node)
    
    # 设置入口点
    graph.set_entry_point("llm")
    
    # 添加条件边
    graph.add_conditional_edges(
        "llm",
        route_next_step,
        {
            "tool": "tool_calling",
            "end": END
        }
    )
    
    # 工具调用节点返回到LLM节点
    graph.add_edge("tool_calling", "llm")
    
    # 添加流式日志拦截器 - 记录每次节点间转换
    @graph.on_transition()
    def log_transition(state, prev_step, current_step):
        """记录节点转换和当前状态"""
        util.log(1, f"[LangGraph流] 节点转换: {prev_step} → {current_step}")
        
        # 记录最新消息的详细内容
        messages = state.get("messages", [])
        if messages and len(messages) > 0:
            last_msg = messages[-1]
            msg_type = type(last_msg).__name__
            
            # 记录消息类型和内容前缀
            if hasattr(last_msg, "content"):
                content = last_msg.content[:100] + ("..." if len(last_msg.content) > 100 else "")
                util.log(1, f"[LangGraph流] 当前消息({msg_type}): {content}")
            
            # 记录工具调用详情
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                for tool_call in last_msg.tool_calls:
                    util.log(1, f"[LangGraph流] 工具调用: {tool_call}")
    
    # 编译状态图
    compiled_graph = graph.compile()
    
    return compiled_graph, llm_node

def llm_node(state: AgentState):
    """
    LLM节点处理函数
    
    读取消息历史，添加工具信息，调用LLM获取响应
    """
    # 获取消息历史
    messages = state.get("messages", [])
    # 将_init_tools()用作get_tools()的替代
    tools = state.get("tools", _init_tools_static())
    
    # 记录状态
    util.log(1, f"[LangGraph] LLM节点收到 {len(messages)} 条消息")
    
    # 记录输入消息详情
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            util.log(1, f"[LangGraph流] LLM输入({type(last_msg).__name__}): {last_msg.content[:100]}...")
    
    # TODO: 调用实际的LLM处理函数
    # 这里只是一个模拟实现
    try:
        # 移除硬编码天气关键词判断
        # 调用正确的LLM处理逻辑
        from llm.agent.sisi_agent import call_llm
        
        # 创建简单响应用于测试
        response = "我是Assistant，有什么可以帮助您的？"
        
        # 创建AI消息
        ai_message = AIMessage(content=response)
        
        # 添加到消息列表
        messages.append(ai_message)
        
        # 记录LLM的思考过程和输出结果
        util.log(1, f"[LangGraph流] LLM思考过程: {response[:150]}...")
        
        return {"messages": messages}
    except Exception as e:
        # 记录错误
        util.log(3, f"[LangGraph] LLM节点处理出错: {str(e)}")
        # 创建错误消息
        error_message = AIMessage(content=f"处理请求时出错: {str(e)}")
        messages.append(error_message)
        return {"messages": messages}

# 添加静态工具初始化函数
def _init_tools_static() -> List[BaseTool]:
    """初始化工具列表（静态方法）"""
    util.log(1, "[Agent工具] 🚀 开始初始化工具系统...")
    
    tools = [
        Weather(),              # 天气查询工具
        TimeQuery(),            # 时间查询工具
        ToRemind(),             # 提醒工具
        QueryTimerDB(),         # 查询定时器数据库
        DeleteTimer()           # 删除定时器
    ]
    
    # 输出详细的工具启动日志
    util.log(1, f"[Agent工具] ✅ 成功加载 {len(tools)} 个核心工具:")
    for i, tool in enumerate(tools, 1):
        util.log(1, f"[Agent工具]   {i}. {tool.name}: {tool.description[:50]}...")
    
    util.log(1, f"[Agent工具] 💼 工具系统启动完成！")
    util.log(1, f"[Agent工具] 🔧 可用工具: {', '.join(t.name for t in tools)}")
    
    return tools

def tool_calling_node(state: AgentState):
    """
    工具调用节点处理函数
    
    解析LLM输出中的工具调用指令，执行工具调用
    """
    # 获取消息历史和工具列表
    messages = state.get("messages", [])
    # 使用_init_tools_static替代get_tools
    tools = state.get("tools", _init_tools_static())
    
    # 记录可用工具列表
    tool_names = [t.name for t in tools]
    util.log(1, f"[LangGraph流] 可用工具列表: {tool_names}")
    
    # 获取最后一条AI消息
    if not messages:
        return state
    
    last_ai_message = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai_message = msg
            break
    
    if not last_ai_message:
        return state
    
    # 解析工具调用
    content = last_ai_message.content
    util.log(1, f"[LangGraph流] 解析工具调用: {content[:100]}...")
    
    # 使用正则表达式解析工具调用
    import re
    import json
    
    # 收集所有工具调用
    tool_calls = []
    
    # 1. 提取单个工具调用 - 使用更宽松的正则表达式
    single_tool_matches = re.findall(r'```(?:json)?\s*\n?\s*(\{.*?"action":\s*"([^"]+)".*?"action_input":\s*(.+?)\s*\})\s*\n?```', content, re.DOTALL)
    for match_full, tool_name, tool_input_raw in single_tool_matches:
        try:
            # 尝试解析完整的JSON
            full_json = json.loads(match_full)
            if "action" in full_json and "action_input" in full_json:
                tool_calls.append({"name": full_json["action"], "input": full_json["action_input"]})
                util.log(1, f"[LangGraph流] 解析到单个工具调用: {full_json['action']}")
        except:
            # 如果完整解析失败，使用正则提取的结果
            try:
                # 尝试解析工具输入
                if tool_input_raw.startswith('"') and tool_input_raw.endswith('"'):
                    # 字符串类型的输入
                    tool_input = tool_input_raw.strip('"')
                else:
                    # 可能是对象或其他JSON结构
                    tool_input = json.loads(tool_input_raw)
                
                tool_calls.append({"name": tool_name, "input": tool_input})
                util.log(1, f"[LangGraph流] 解析到单个工具调用(降级处理): {tool_name}")
            except Exception as e:
                util.log(2, f"[LangGraph流] 解析工具输入失败: {str(e)}")
    
    # 2. 提取多工具数组格式 - 更灵活的匹配
    array_matches = re.findall(r'```(?:json)?\s*\n?\s*(\[.*?\])\s*\n?```', content, re.DOTALL)
    for array_json_str in array_matches:
        try:
            # 解析JSON数组
            tool_array = json.loads(array_json_str)
            if isinstance(tool_array, list):
                for tool_obj in tool_array:
                    if isinstance(tool_obj, dict) and "action" in tool_obj and "action_input" in tool_obj:
                        tool_calls.append({"name": tool_obj["action"], "input": tool_obj["action_input"]})
                        util.log(1, f"[LangGraph流] 解析到数组中的工具调用: {tool_obj['action']}")
        except Exception as e:
            util.log(2, f"[LangGraph流] 解析JSON工具数组出错: {str(e)}")
    
    # 3. 检查ReAct格式
    react_patterns = [
        r'Action\s*:\s*(\w+)\[(.*?)\]',
        r'行动\s*:\s*(\w+)\[(.*?)\]',
        r'动作\s*:\s*(\w+)\[(.*?)\]'
    ]
    
    for pattern in react_patterns:
        react_matches = re.findall(pattern, content, re.DOTALL)
        for tool_name, args_str in react_matches:
            # 尝试解析参数为JSON
            try:
                args = json.loads(args_str)
            except:
                # 如果不是有效JSON，作为普通字符串处理
                args = {"input": args_str.strip()}
            
            # 生成唯一ID
            import time
            tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
            
            tool_calls.append({"name": tool_name, "input": args})
            util.log(1, f"[LangGraph流] 解析到ReAct格式工具调用: {tool_name}")
    
    if not tool_calls:
        # 没有找到工具调用
        util.log(1, f"[LangGraph流] 未检测到工具调用指令，内容: {content[:200]}")
        return state
    
    # 记录找到的工具调用
    util.log(1, f"[LangGraph流] 找到 {len(tool_calls)} 个工具调用")
    for i, call in enumerate(tool_calls):
        util.log(1, f"[LangGraph流] 工具调用 #{i+1}: {call['name']} - 参数: {call['input']}")
    
    # 导入中转站
    try:
        from llm.transit_station import TransitStation
        transit = TransitStation.get_instance()
        transit.add_intermediate_state(
            f"检测到 {len(tool_calls)} 个工具调用",
            "LangGraph工具调用节点"
        )
    except:
        pass
    
    # 导入异步库
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    # 定义并行执行工具的函数
    async def execute_tools_in_parallel(tool_calls):
        """并行执行多个工具调用"""
        results = []
        
        # 定义单个工具执行函数
        def execute_single_tool(call):
            tool_name = call["name"]
            tool_input = call["input"]
            
            # 查找匹配的工具
            tool = None
            normalized_request = tool_name.lower().replace("_", "").replace("-", "")
            
            # 尝试精确匹配（不区分大小写）
            for t in tools:
                if t.name.lower() == tool_name.lower():
                    tool = t
                    break
            
            # 检查别名
            if not tool:
                for t in tools:
                    if hasattr(t, "aliases") and isinstance(t.aliases, list):
                        for alias in t.aliases:
                            if alias.lower() == tool_name.lower():
                                tool = t
                                break
                        if tool:
                            break
            
            # 尝试更灵活的匹配
            if not tool:
                for t in tools:
                    normalized_tool = t.name.lower().replace("_", "").replace("-", "")
                    if normalized_tool == normalized_request:
                        tool = t
                        break
                    
                    # 检查标准化别名
                    if hasattr(t, "aliases") and isinstance(t.aliases, list):
                        for alias in t.aliases:
                            normalized_alias = alias.lower().replace("_", "").replace("-", "")
                            if normalized_alias == normalized_request:
                                tool = t
                                break
                        if tool:
                            break
            
            if not tool:
                return {"name": tool_name, "result": f"找不到工具: {tool_name}", "error": True}
            
            # 执行工具
            try:
                util.log(1, f"[LangGraph流] 开始执行工具: {tool.name}")
                result = tool.run(tool_input)
                return {"name": tool.name, "result": str(result), "error": False}
            except Exception as e:
                error_msg = f"工具 {tool_name} 执行出错: {str(e)}"
                util.log(2, f"[LangGraph流] {error_msg}")
                return {"name": tool_name, "result": error_msg, "error": True}
        
        # 使用线程池并行执行工具
        with ThreadPoolExecutor() as executor:
            # 创建任务列表
            tasks = [
                asyncio.get_event_loop().run_in_executor(executor, execute_single_tool, call)
                for call in tool_calls
            ]
            
            # 并行等待所有任务完成
            results = await asyncio.gather(*tasks)
            return results
    
    # 执行工具并获取结果
    try:
        # 创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # 如果没有事件循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 执行并行工具调用
        tool_results = loop.run_until_complete(execute_tools_in_parallel(tool_calls))
        
        # 从结果创建函数消息
        function_messages = []
        for result in tool_results:
            function_messages.append(
                FunctionMessage(content=result["result"], name=result["name"])
            )
        
        # 添加结果到消息历史
        state["messages"] = messages + function_messages
        
        # 记录工具执行结果
        for result in tool_results:
            result_preview = result["result"][:100] + ("..." if len(result["result"]) > 100 else "")
            util.log(1, f"[LangGraph流] 工具 {result['name']} 执行结果: {result_preview}")
        
        # 尝试向中转站发送工具执行结果
        try:
            from llm.transit_station import TransitStation
            transit = TransitStation.get_instance()
            for result in tool_results:
                transit.add_intermediate_state(
                    f"工具 {result['name']} 执行结果: {result['result'][:200]}...",
                    "LangGraph工具执行结果"
                )
        except:
            pass
            
    except Exception as e:
        # 处理整体执行错误
        error_msg = f"并行执行工具调用出错: {str(e)}"
        util.log(2, f"[LangGraph流] {error_msg}")
        state["messages"] = messages + [FunctionMessage(content=error_msg, name="tool_executor")]
    
    return state

def route_next_step(state: AgentState):
    """
    路由决策函数，决定下一步走向
    
    分析最后一条AI消息，决定是执行工具调用还是结束对话
    """
    # 获取消息历史
    messages = state.get("messages", [])
    
    # 获取最后一条AI消息
    if not messages:
        return "end"
    
    last_ai_message = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai_message = msg
            break
    
    if not last_ai_message:
        return "end"
    
    # 分析是否需要工具调用
    content = last_ai_message.content
    
    # 检测工具调用格式 - 更灵活的正则表达式
    import re
    import json
    
    # 单工具调用检测 - 更宽松以匹配更多格式
    single_tool_pattern = r'```(?:json)?\s*\n?\s*\{\s*"action":\s*"([^"]+)"'
    
    # 工具调用数组检测 - 更宽松
    # 先尝试提取JSON代码块
    has_tool_call = False
    
    # 1. 检查单个工具调用
    if re.search(single_tool_pattern, content):
        has_tool_call = True
        util.log(1, f"[LangGraph流] 检测到单个工具调用")
    
    # 2. 检查可能的工具数组
    if not has_tool_call:
        array_matches = re.findall(r'```(?:json)?\s*\n?\s*(\[.*?\])\s*\n?```', content, re.DOTALL)
        for array_json in array_matches:
            try:
                # 解析JSON数组
                tool_array = json.loads(array_json)
                if isinstance(tool_array, list) and len(tool_array) > 0:
                    for item in tool_array:
                        if isinstance(item, dict) and "action" in item:
                            has_tool_call = True
                            util.log(1, f"[LangGraph流] 检测到工具调用数组，包含{len(tool_array)}个工具")
                            break
            except Exception as e:
                # 解析失败记录日志
                util.log(2, f"[LangGraph流] JSON数组解析失败: {str(e)}")
                pass
    
    # 3. 检查ReAct格式
    if not has_tool_call:
        react_patterns = [
            r'Action\s*:\s*(\w+)\[',
            r'行动\s*:\s*(\w+)\[',
            r'动作\s*:\s*(\w+)\['
        ]
        for pattern in react_patterns:
            if re.search(pattern, content):
                has_tool_call = True
                util.log(1, f"[LangGraph流] 检测到ReAct格式工具调用")
                break
    
    # 日志记录判断结果
    util.log(1, f"[LangGraph流] 路由决策: {'执行工具' if has_tool_call else '结束对话'}")
    
    if has_tool_call:
        return "tool"
    else:
        return "end"

def invoke(query, tools=None):
    """
    调用Agent处理查询
    
    Args:
        query: 用户查询
        tools: 可选的工具列表
        
    Returns:
        str: Agent的响应
    """
    try:
        # 构建Agent图
        graph, _ = build_agent_graph()
        
        # 准备初始状态
        if tools is None:
            # 使用_init_tools_static替代get_tools
            tools = _init_tools_static()
        
        initial_state = {
            "messages": [HumanMessage(content=query)],
            "tools": tools,
            "meta": {"query_time": time.time()}
        }
        
        # 执行图 - 使用流式处理获取详细日志
        util.log(1, f"[LangGraph流] 开始处理查询: {query}")
        
        # 启用流式执行
        for event in graph.stream(initial_state, stream_mode="values"):
            if "messages" in event:
                # 记录每一步的消息变化
                messages = event["messages"]
                if messages and len(messages) > 0:
                    last_msg = messages[-1]
                    msg_type = type(last_msg).__name__
                    if hasattr(last_msg, "content"):
                        content = last_msg.content[:100] + ("..." if len(last_msg.content) > 100 else "")
                        util.log(1, f"[LangGraph流事件] {msg_type}: {content}")
        
        # 获取最终状态
        final_state = graph.get_state()
        
        # 提取结果
        messages = final_state.get("messages", [])
        if not messages:
            return "未能生成响应"
        
        # 获取最后一条AI消息
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                return msg.content
        
        # 如果没有找到AI消息，返回最后一条消息的内容
        last_message = messages[-1]
        if hasattr(last_message, "content"):
            return last_message.content
        
        return str(last_message)
    
    except Exception as e:
        util.log(2, f"[LangGraph] 处理查询出错: {str(e)}")
        traceback.print_exc()
        return f"处理您的请求时出现错误: {str(e)}"

# 测试代码
if __name__ == "__main__":
    result = invoke("今天北京的天气怎么样？")
    print(f"查询结果: {result}")
