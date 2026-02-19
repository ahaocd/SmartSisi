"""
工具Schema工厂 - 为LangChain工具生成符合OpenAI函数调用格式的schema
"""

from typing import Dict, Any, List, Optional, Type
from pydantic import BaseModel
from langchain.tools import BaseTool

def create_tool_schema(tool: BaseTool) -> Dict[str, Any]:
    """
    为LangChain工具创建符合OpenAI函数调用格式的schema
    
    Args:
        tool: LangChain工具实例
        
    Returns:
        符合OpenAI函数调用格式的schema字典
    """
    # 基本结构
    schema = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
    
    # 如果工具有参数模式，从中提取参数信息
    if hasattr(tool, 'args_schema') and tool.args_schema is not None:
        # 获取参数模式类
        args_schema_cls = tool.args_schema
        
        # 获取字段信息
        for field_name, field in args_schema_cls.__fields__.items():
            # 添加字段到properties
            field_info = field.field_info
            field_type = _get_json_type(field.type_)
            
            # 创建参数属性
            param_property = {
                "type": field_type
            }
            
            # 添加描述（如果有）
            if hasattr(field_info, 'description') and field_info.description:
                param_property["description"] = field_info.description
                
            # 添加到properties
            schema["function"]["parameters"]["properties"][field_name] = param_property
            
            # 如果是必需字段，添加到required列表
            if field.required:
                schema["function"]["parameters"]["required"].append(field_name)
    
    return schema

def _get_json_type(python_type: Type) -> str:
    """
    将Python类型转换为JSON Schema类型
    
    Args:
        python_type: Python类型
        
    Returns:
        对应的JSON Schema类型字符串
    """
    # 基本类型映射
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object"
    }
    
    # 尝试从映射中获取类型
    for py_type, json_type in type_map.items():
        if python_type == py_type or (hasattr(python_type, "__origin__") and python_type.__origin__ == py_type):
            return json_type
    
    # 默认为字符串类型
    return "string"

def add_schema_to_tools(tools: List[BaseTool]) -> List[BaseTool]:
    """
    为工具列表中的每个工具添加tool_schema属性
    
    Args:
        tools: LangChain工具列表
        
    Returns:
        更新后的工具列表
    """
    for tool in tools:
        if not hasattr(tool, 'tool_schema'):
            tool.tool_schema = create_tool_schema(tool)
    
    return tools
