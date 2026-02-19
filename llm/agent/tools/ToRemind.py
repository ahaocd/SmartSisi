import random
from typing import Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool

class ToRemindInput(BaseModel):
    """创建提醒的输入参数"""
    content: str = Field(..., description="提醒的内容，描述需要提醒的事项")

class ToRemind(BaseTool):
    """创建提醒工具"""
    name: str = "to_remind"
    description: str = "创建即时提醒，传入事项内容作为参数"
    args_schema: type[BaseModel] = ToRemindInput

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        """初始化创建提醒工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        super().__init__(**tool_params)

    async def _arun(self, content: str) -> str:
        """异步创建提醒"""
        return self._run(content)

    def _run(self, content: str) -> str:
        """
        创建即时提醒
        
        Args:
            content: 提醒的内容，描述需要提醒的事项
            
        Returns:
            str: 提醒创建结果
        """
        # 处理输入内容
        content = content.replace("提醒", "回复")
        
        # 提醒模板
        templates = [
            "主人！是时候（事项内容）了喔~",
            "亲爱的主人，现在是（事项内容）的时候啦！",
            "嘿，主人，该（事项内容）了哦~",
            "温馨提醒：（事项内容）的时间到啦，主人！",
            "小提醒：主人，现在可以（事项内容）了~"
        ]

        # 随机选择一个模板并返回
        return f"成功创建即时提醒，将以友善的方式提醒：{content}\n示例: " + random.choice(templates).replace("（事项内容）", content)

if __name__ == "__main__":
    tool = ToRemind()
    result = tool._run("喝水")
    print(result)
