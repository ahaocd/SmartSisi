"""
标准版ToolNode实现，基于官方LangGraph实现
使用标准消息类型，确保正确的ReAct循环
"""

import json
import asyncio
from typing import Dict, List, Any, Optional, Union, Callable
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, ToolMessage, AIMessage

class ToolNode:
    """
    工具节点 - 用于执行工具调用
    基于官方LangGraph实现，使用标准消息格式
    """
    
    def __init__(self, tools: List[BaseTool]):
        """
        初始化工具节点
        
        Args:
            tools: 可用工具列表
        """
        self.tools = {tool.name: tool for tool in tools}
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具调用
        
        Args:
            state: 输入状态，包含消息历史
            
        Returns:
            Dict[str, Any]: 更新后的状态，包含工具执行结果
        """
        # 使用同步方法调用
        return self.invoke(state)
    
    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具调用(同步方法)
        
        Args:
            state: 输入状态，包含消息历史
            
        Returns:
            Dict[str, Any]: 更新后的状态
        """
        # 检查状态中是否有消息
        if "messages" not in state or not state["messages"]:
            return state
        
        outputs = []
        # 获取最后一条消息
        last_message = state["messages"][-1]
        
        # 检查是否有工具调用
        tool_calls = []
        
        # 1. 首先检查标准的tool_calls属性
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            tool_calls = last_message.tool_calls
            print(f"[ToolNode] 找到标准格式工具调用: {len(tool_calls)}个")
        
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
                        import time
                        tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
                        
                        tool_calls.append({
                            "name": tool_name,
                            "args": args,
                            "id": tool_call_id
                        })
                        print(f"[ToolNode] 解析到ReAct格式工具调用: {tool_name}")
                        break
                
                if tool_calls:
                    break
            
            # 如果还没找到工具调用，检查JSON代码块
            if not tool_calls:
                json_pattern = r'```(?:json)?\s*(.*?)\s*```'
                json_matches = re.findall(json_pattern, content, re.DOTALL)
                
                for json_str in json_matches:
                    try:
                        tool_data = json.loads(json_str)
                        # 支持多种格式
                        if "action" in tool_data and "action_input" in tool_data:
                            tool_name = tool_data["action"]
                            tool_input = tool_data["action_input"]
                            
                            # 生成唯一ID
                            import time
                            tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
                            
                            tool_calls.append({
                                "name": tool_name,
                                "args": tool_input if isinstance(tool_input, dict) else {"input": tool_input},
                                "id": tool_call_id
                            })
                            print(f"[ToolNode] 解析到JSON格式工具调用: {tool_name}")
                            break
                    except Exception as e:
                        print(f"[ToolNode] JSON解析失败: {str(e)}")
                        continue
        
        # 如果没有工具调用，直接返回状态
        if not tool_calls:
            print("[ToolNode] 未检测到工具调用")
            return state
        
        # 执行所有工具调用
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            args = tool_call.get("args", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except:
                    args = {"input": args}
            
            # 获取工具
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
                        # 如果没有input字段，将整个args作为输入
                        input_value = args
                    
                    # 调用工具
                    print(f"[ToolNode] 执行工具 {tool_name}，参数: {input_value}")
                    result = tool.run(input_value)
                    
                    # 创建标准的ToolMessage
                    tool_message = ToolMessage(
                        content=str(result),
                        name=tool_name,
                        tool_call_id=tool_call.get("id", f"call_{tool_name}")
                    )
                    
                    outputs.append(tool_message)
                    print(f"[ToolNode] 工具执行成功: {tool_name}")
                    
                except Exception as e:
                    error_message = f"执行工具时出错: {str(e)}"
                    print(f"[ToolNode] {error_message}")
                    
                    # 即使发生错误也创建ToolMessage
                    tool_message = ToolMessage(
                        content=error_message,
                        name=tool_name,
                        tool_call_id=tool_call.get("id", f"call_{tool_name}")
                    )
                    
                    outputs.append(tool_message)
            else:
                error_message = f"找不到名为 {tool_name} 的工具。可用工具: {', '.join(self.tools.keys())}"
                print(f"[ToolNode] {error_message}")
                
                # 创建错误消息
                tool_message = ToolMessage(
                    content=error_message,
                    name="error",
                    tool_call_id=tool_call.get("id", f"error_{tool_name}")
                )
                
                outputs.append(tool_message)
        
        # 更新状态 - 添加所有工具消息
        if outputs:
            return {"messages": outputs}
        
        # 如果没有输出，返回原始状态
        return state
    
    async def ainvoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具调用(异步方法)
        
        Args:
            state: 输入状态，包含消息历史
            
        Returns:
            Dict[str, Any]: 更新后的状态
        """
        # 简单封装同步方法
        return self.invoke(state) 