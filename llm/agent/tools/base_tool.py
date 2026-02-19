"""
自定义基础工具类，支持OpenAI函数调用格式
"""

from typing import Dict, Any, Optional, ClassVar
from langchain.tools import BaseTool as LangChainBaseTool
from pydantic import Field, PrivateAttr

class SisiBaseTool(LangChainBaseTool):
    """
    SmartSisi项目的基础工具类，扩展LangChain的BaseTool
    添加对OpenAI函数调用格式的支持
    """
    # 添加tool_schema字段，用于存储OpenAI函数调用格式的schema
    tool_schema: Optional[Dict[str, Any]] = Field(default=None, exclude=True)
    # 添加uid字段，用于标识用户ID
    uid: int = Field(default=0, exclude=True)
    
    def __init__(self, **data):
        """初始化工具，设置tool_schema"""
        super().__init__(**data)
        
        # 如果没有设置tool_schema，则创建一个默认的
        if self.tool_schema is None:
            self.tool_schema = self._create_tool_schema()
    
    def _create_tool_schema(self) -> Dict[str, Any]:
        """创建符合OpenAI函数调用格式的schema"""
        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }
        
        # 如果有参数模式，从中提取参数信息
        if hasattr(self, 'args_schema') and self.args_schema is not None:
            # 获取参数模式类
            args_schema_cls = self.args_schema
            
            # 尝试获取schema
            try:
                params_schema = args_schema_cls.schema()
                
                # 从schema中提取properties和required
                if "properties" in params_schema:
                    schema["function"]["parameters"]["properties"] = params_schema["properties"]
                
                if "required" in params_schema:
                    schema["function"]["parameters"]["required"] = params_schema["required"]
            except Exception as e:
                # 如果获取schema失败，使用空对象
                print(f"为工具 {self.name} 创建schema时出错: {str(e)}")
        
        return schema
