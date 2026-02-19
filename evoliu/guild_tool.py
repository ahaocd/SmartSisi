#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公会工具系统 - 统一接口（参考pi-mono的AgentTool + langgraph的BaseTool）
不再硬编码解析，使用LLM原生工具调用
"""

import json
import logging
from typing import Any, Dict, Callable, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GuildTool:
    """公会工具定义（参考pi-mono的AgentTool）
    
    统一的工具接口，支持：
    1. LLM原生工具调用（OpenAI function calling）
    2. JSON Schema参数验证
    3. 统一的执行接口
    """
    
    name: str
    """工具名称（唯一标识）"""
    
    description: str
    """工具描述（给LLM看的）"""
    
    parameters: Dict[str, Any]
    """参数定义（JSON Schema格式）"""
    
    execute: Callable[[Dict[str, Any]], str]
    """执行函数：接收参数字典，返回结果字符串"""
    
    category: str = "general"
    """工具分类（general/guild/agent/system等）"""
    
    examples: List[str] = field(default_factory=list)
    """使用示例"""
    
    def to_openai_tool(self) -> Dict[str, Any]:
        """转换为OpenAI工具格式（给LLM用）
        
        Returns:
            OpenAI function calling格式的工具定义
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    def validate_args(self, args: Dict[str, Any]) -> bool:
        """验证参数（简单验证，完整验证需要jsonschema库）
        
        Args:
            args: 参数字典
            
        Returns:
            是否验证通过
        """
        # 检查必需参数
        required = self.parameters.get("required", [])
        for param in required:
            if param not in args:
                logger.error(f"[工具验证] 缺少必需参数: {param}")
                return False
        
        return True
    
    def execute_safe(self, args: Dict[str, Any]) -> str:
        """安全执行工具（带验证和错误处理）
        
        Args:
            args: 参数字典
            
        Returns:
            执行结果字符串
        """
        try:
            # 验证参数
            if not self.validate_args(args):
                return f"❌ 参数验证失败: 缺少必需参数"
            
            # 执行工具
            result = self.execute(args)
            
            # 确保返回字符串
            if isinstance(result, str):
                return result
            elif isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False)
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"[工具执行] 执行失败: {self.name} - {e}", exc_info=True)
            return f"❌ 工具执行失败: {e}"


# ==================== 工具构建器 ====================

class GuildToolBuilder:
    """工具构建器 - 简化工具创建"""
    
    @staticmethod
    def create_simple_tool(
        name: str,
        description: str,
        func: Callable[[str], str],
        param_name: str = "input",
        param_description: str = "输入参数",
        category: str = "general"
    ) -> GuildTool:
        """创建简单工具（单个字符串参数）
        
        Args:
            name: 工具名称
            description: 工具描述
            func: 执行函数（接收字符串，返回字符串）
            param_name: 参数名称
            param_description: 参数描述
            category: 工具分类
            
        Returns:
            GuildTool实例
        """
        return GuildTool(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    param_name: {
                        "type": "string",
                        "description": param_description
                    }
                },
                "required": [param_name]
            },
            execute=lambda args: func(args[param_name]),
            category=category
        )
    
    @staticmethod
    def create_guild_task_tool(
        guild_instance,
        member_ids: List[str] = None
    ) -> GuildTool:
        """创建公会任务提交工具
        
        Args:
            guild_instance: 公会实例
            member_ids: 可用的成员ID列表
            
        Returns:
            GuildTool实例
        """
        if member_ids is None:
            member_ids = ["openclaw"]
        
        return GuildTool(
            name="submit_guild_task",
            description="提交任务给公会成员（OpenClaw等）执行",
            parameters={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "任务描述，清晰说明要做什么"
                    },
                    "member_id": {
                        "type": "string",
                        "description": "公会成员ID",
                        "enum": member_ids,
                        "default": "openclaw"
                    }
                },
                "required": ["description"]
            },
            execute=lambda args: guild_instance.submit_task(
                args["description"],
                member_id=args.get("member_id", "openclaw")
            ),
            category="guild",
            examples=[
                "submit_guild_task(description='搜索Python最佳实践', member_id='openclaw')"
            ]
        )


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    # 创建简单工具
    tool = GuildToolBuilder.create_simple_tool(
        name="echo",
        description="回显输入的文本",
        func=lambda x: f"你说: {x}"
    )
    
    print("工具定义:")
    print(json.dumps(tool.to_openai_tool(), ensure_ascii=False, indent=2))
    
    print("\n执行工具:")
    result = tool.execute_safe({"input": "Hello World"})
    print(result)
