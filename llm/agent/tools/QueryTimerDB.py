import sqlite3
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool

class QueryTimerDBInput(BaseModel):
    """查询提醒数据库的输入参数"""
    query: Optional[str] = Field(
        default="",
        description="可选的查询条件，默认为空表示查询所有提醒"
    )

class QueryTimerDB(BaseTool):
    """提醒数据库查询工具"""
    name: str = "query_timer_db"
    description: str = "查询所有日程提醒，返回的数据包含：时间、循环规则（如:'1000100'代表星期一和星期五循环，'0000000'代表不循环）、执行的事项"
    args_schema: type[BaseModel] = QueryTimerDBInput

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        """初始化查询提醒工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        super().__init__(**tool_params)

    async def _arun(self, query: str = "") -> str:
        """异步查询提醒数据库"""
        return self._run(query)

    def _run(self, query: str = "") -> str:
        """
        查询提醒数据库
        
        Args:
            query: 可选的查询条件，默认为空表示查询所有提醒
            
        Returns:
            str: 格式化的提醒列表
        """
        try:
            conn = sqlite3.connect('timer.db')
            cursor = conn.cursor()
            
            # 执行查询
            cursor.execute("SELECT * FROM timer")
            
            # 获取所有记录
            rows = cursor.fetchall()
            
            # 如果没有记录
            if not rows:
                return "没有找到任何提醒事项。"
                
            # 格式化结果
            result = "已设置的提醒如下：\n"
            for i, row in enumerate(rows, 1):
                timer_id, time_str, repeat_rule, content = row
                repeat_desc = self._format_repeat_rule(repeat_rule)
                result += f"{i}. ID: {timer_id}, 时间: {time_str}, 重复: {repeat_desc}, 内容: {content}\n"
            
            conn.close()
            return result.strip()
            
        except Exception as e:
            return f"查询提醒数据库时出错: {str(e)}"
    
    def _format_repeat_rule(self, rule: str) -> str:
        """格式化重复规则为可读形式"""
        if not rule or rule == "0000000":
            return "不重复"
            
        days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        active_days = [days[i] for i, c in enumerate(rule) if c == "1"]
        
        if not active_days:
            return "不重复"
        return "每" + "、".join(active_days)


if __name__ == "__main__":
    tool = QueryTimerDB()
    result = tool._run("")
    print(result)
