"""
LLM模型适配器 - 为LangGraph提供标准LLM接口
"""

import logging
import json
import os
from typing import Any, Dict, List, Optional, Union, Sequence, Callable, Type, cast

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.runnables import RunnableBinding
from utils import util

class SisiLLMAdapter(BaseChatModel):
    """SmartSisi LLM模型适配器，提供标准的LangChain接口"""
    
    # 定义Pydantic模型属性
    model_name: str = "sisi-llm-adapter"
    history: List[BaseMessage] = []  # 必须在类级别声明所有字段
    
    class Config:
        """配置类"""
        arbitrary_types_allowed = True
    
    def __init__(self, **kwargs):
        """初始化LLM适配器"""
        super().__init__(**kwargs)
        # 不需要在这里设置history，因为已经在类级别声明了
    
    def invoke(self, messages: List[BaseMessage], run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs) -> AIMessage:
        """调用LLM模型处理消息"""
        try:
            # 从消息列表中提取最后的用户消息
            last_user_msg = None
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    last_user_msg = msg
                    break
            
            if not last_user_msg:
                return AIMessage(content="无法找到用户消息")
            
            # 检查是否有绑定工具
            bound_tools = kwargs.get("tools", [])
            if bound_tools:
                # 思考阶段：分析查询并选择最合适的工具
                util.log(1, f"[LLM适配器] 思考阶段：分析查询 '{last_user_msg.content}'")
                
                # 找出最匹配的工具
                best_tool = None
                best_score = 0
                
                for tool in bound_tools:
                    # 解析工具名称和描述
                    tool_name = tool.name if isinstance(tool, BaseTool) else tool[0]
                    tool_desc = tool.description if isinstance(tool, BaseTool) else tool[1]
                    
                    # 评分：检查工具名称和描述是否与查询相关
                    score = 0
                    if tool_name in last_user_msg.content:
                        score += 2
                    if any(keyword in last_user_msg.content for keyword in tool_desc.split()):
                        score += 1
                        
                    if score > best_score:
                        best_score = score
                        best_tool = tool
                        
                if not best_tool:
                    return AIMessage(content="无法找到合适的工具")
                    
                # 执行阶段：生成工具调用
                util.log(1, f"[LLM适配器] 执行阶段：选择工具 {best_tool.name if isinstance(best_tool, BaseTool) else best_tool[0]}")
                
                # 构建工具调用
                tool_call = {
                    "name": best_tool.name if isinstance(best_tool, BaseTool) else best_tool[0],
                    "id": f"call_{util.get_uuid() if hasattr(util, 'get_uuid') else id(last_user_msg.content)}",
                    "args": {"query": last_user_msg.content}
                }
                
                # 观察阶段：返回包含工具调用的消息
                util.log(1, f"[LLM适配器] 观察阶段：生成工具调用 {tool_call['name']}")
                
                return AIMessage(
                    content="我需要使用工具获取信息。",
                    tool_calls=[tool_call]
                )
            
            # 如果没有工具，直接返回需要工具的消息
            return AIMessage(content="我需要使用工具获取信息。")
            
        except Exception as e:
            import traceback
            util.log(3, f"[LLM适配器] 调用异常: {str(e)}")
            util.log(3, f"[LLM适配器] 调用堆栈: {traceback.format_exc()}")
            return AIMessage(content=f"处理请求时出现错误: {str(e)}")
    
    def _should_use_tool(self, query: str) -> bool:
        """判断是否需要使用工具
        
        基于查询内容简单判断是否可能需要工具
        
        Args:
            query: 用户查询
            
        Returns:
            bool: 是否应该使用工具
        """
        # 时间、天气、地图等关键词可能需要工具
        tool_keywords = [
            "几点", "时间", "日期", "天气", "温度", "地图", "导航", 
            "位置", "附近", "周边", "怎么走", "路线", "查询"
        ]
        
        for keyword in tool_keywords:
            if keyword in query:
                util.log(1, f"[LLM适配器] 检测到可能需要工具的关键词: {keyword}")
                return True
        
        return False
    
    def _generate_tool_call(self, query: str, tools: List[Any]) -> AIMessage:
        """生成工具调用，实现ReAct模式的思考-执行-观察循环
        
        Args:
            query: 用户查询
            tools: 可用工具列表
            
        Returns:
            AIMessage: 包含工具调用的消息
        """
        # 思考阶段：分析查询并选择最合适的工具
        util.log(1, f"[LLM适配器] 思考阶段：分析查询 '{query}'")
        
        # 找出最匹配的工具
        best_tool = None
        best_score = 0
        
        for tool in tools:
            # 解析工具名称和描述
            tool_name = ""
            tool_desc = ""
            
            if isinstance(tool, BaseTool):
                tool_name = tool.name
                tool_desc = tool.description
            elif isinstance(tool, tuple) and len(tool) >= 2:
                tool_name = tool[0]
                tool_desc = tool[1]
            elif hasattr(tool, "name") and hasattr(tool, "description"):
                tool_name = tool.name
                tool_desc = tool.description
            else:
                continue
                
            # 简单评分：检查工具名称和描述是否与查询相关
            score = 0
            if tool_name in query:
                score += 2
            if any(keyword in query for keyword in tool_desc.split()):
                score += 1
                
            if score > best_score:
                best_score = score
                best_tool = tool
                
        if not best_tool:
            return AIMessage(content="无法找到合适的工具")
            
        # 执行阶段：生成工具调用
        util.log(1, f"[LLM适配器] 执行阶段：选择工具 {best_tool.name if isinstance(best_tool, BaseTool) else best_tool[0]}")
        
        # 构建工具调用
        tool_call = {
            "name": best_tool.name if isinstance(best_tool, BaseTool) else best_tool[0],
            "id": f"call_{util.get_uuid() if hasattr(util, 'get_uuid') else id(query)}",
            "args": {"query": query}
        }
        
        # 观察阶段：返回包含工具调用的消息
        util.log(1, f"[LLM适配器] 观察阶段：生成工具调用 {tool_call['name']}")
        
        return AIMessage(
            content="我需要使用工具获取信息。",
            tool_calls=[tool_call]
        )
    
    async def ainvoke(self, messages: List[BaseMessage], run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs) -> AIMessage:
        """异步调用LLM模型处理消息"""
        return self.invoke(messages, run_manager, **kwargs)
    
    def get_num_tokens(self, text: str) -> int:
        """获取文本的token数量"""
        # 简单估算：中文字符算1个token，其他字符按字节数/2算
        chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_count = len(text) - chinese_count
        return chinese_count + (other_count // 2)
        
    def _generate(self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs):
        """实现抽象方法_generate
        
        这是BaseChatModel的抽象方法，必须实现它才能实例化类
        """
        from langchain_core.outputs import ChatGeneration, ChatResult
        
        # 调用我们已经实现的invoke方法获取响应
        ai_message = self.invoke(messages, **kwargs)
        
        # 创建ChatGeneration对象
        generation = ChatGeneration(message=ai_message)
        
        # 返回ChatResult
        return ChatResult(generations=[generation])
    
    def bind_tools(
        self, tools: Sequence[Union[BaseTool, Type[BaseTool], Callable]], **kwargs: Any
    ) -> RunnableBinding[Any, Any]:
        """
        将工具绑定到模型。
        这是LangGraph集成所必需的，用于ReAct代理。
        
        Args:
            tools: 要绑定的工具列表
            **kwargs: 其他参数
            
        Returns:
            一个新的RunnableBinding实例，包含绑定的工具
        """
        util.log(1, f"[LLM适配器] 绑定工具到模型: {len(tools)} 个工具")
        
        # 创建一个从模型到绑定模型的包装函数
        def _bind_tools_wrapper(self, tools, **kwargs):
            """内部包装函数，用于创建带有工具的模型副本"""
            # 无需实际绑定工具，因为我们的模型不直接支持工具调用
            # 只需创建一个新的绑定，让LangGraph认为工具已经绑定
            return RunnableBinding(
                bound=self,
                kwargs={
                    "tools": [
                        # 格式化为工具格式，以便LangGraph可以理解
                        (t.name, t.description, t.args_schema)
                        if isinstance(t, BaseTool)
                        else t
                        for t in tools
                    ]
                }
            )
            
        # 返回包装后的绑定
        return _bind_tools_wrapper(self, tools, **kwargs)
    
    @property
    def _llm_type(self) -> str:
        """实现抽象属性_llm_type
        
        这是BaseChatModel的抽象属性，必须实现它才能实例化类
        """
        return "sisi-llm-adapter"

# 单例实例
_llm_instance = None

def get_llm_model() -> BaseChatModel:
    """获取LLM模型单例实例
    
    Returns:
        BaseChatModel: LLM适配器实例
    """
    global _llm_instance
    
    if _llm_instance is None:
        _llm_instance = SisiLLMAdapter()
        util.log(1, f"[模型适配器] 创建LLM适配器单例实例")
    
    return _llm_instance 