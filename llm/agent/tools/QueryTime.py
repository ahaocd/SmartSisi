from typing import Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool
from utils import util

class QueryTimeInput(BaseModel):
    """查询时间的输入参数"""
    format: Optional[str] = Field(
        default="default",
        description="输出格式，可选值：default(默认格式，时分秒+星期+日期)、full(完整信息，年月日+星期+时分秒)、date(仅日期，年月日+星期)、time(仅时间，时分秒)"
    )

class QueryTime(BaseTool):
    """查询当前时间工具"""
    name: str = "query_time"
    description: str = "查询当前日期、时间和星期信息的工具，可用于回答'现在几点'、'今天几号'、'星期几'、'日期'、'时间'、'几点了'、'报时'等相关问题，支持多种输出格式"
    args_schema: type[BaseModel] = QueryTimeInput
    aliases: List[str] = ["get_time", "QueryTime", "GetTime", "TimeQuery", "getTime", "time"]  # 添加别名支持

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        """初始化查询时间工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        super().__init__(**tool_params)
        
        # 记录工具初始化
        util.log(1, f"[QueryTime] 工具初始化: 名称={self.name}, 别名={self.aliases}")
    
    def get_name_aliases(self) -> List[str]:
        """获取工具名称和别名列表"""
        return [self.name] + self.aliases

    async def _arun(self, format: str = "default") -> str:
        """异步查询当前时间"""
        return self._run(format)

    def _run(self, format: str = "default") -> str:
        """
        查询当前时间
        
        Args:
            format: 时间格式，可选值：default(默认)、full(完整)、date(仅日期)、time(仅时间)
            
        Returns:
            str: 格式化的时间信息
        """
        # 记录工具调用
        util.log(1, f"[QueryTime] 执行工具: {self.name}, 格式={format}")
        
        # 获取当前时间
        now = datetime.now()
        
        # 获取当前日期
        today = now.date()
        
        # 获取星期几的信息
        week_day = now.strftime("%A")
        
        # 将星期几的英文名称转换为中文
        week_day_zh = {
            "Monday": "星期一",
            "Tuesday": "星期二",
            "Wednesday": "星期三",
            "Thursday": "星期四",
            "Friday": "星期五",
            "Saturday": "星期六",
            "Sunday": "星期日",
        }.get(week_day, "未知")
        
        # 将日期格式化为字符串
        date_str = today.strftime("%Y年%m月%d日")
        
        # 将时间格式化为字符串
        time_str = now.strftime("%H:%M:%S")
        
        # 根据格式返回不同的结果
        if format.lower() == "full":
            return f"现在是：{date_str} {week_day_zh} {time_str}"
        elif format.lower() == "date":
            return f"今天是：{date_str} {week_day_zh}"
        elif format.lower() == "time":
            return f"现在时间是：{time_str}"
        else:
            return f"现在是：{time_str} {week_day_zh} {date_str}"

if __name__ == "__main__":
    tool = QueryTime()
    print(f"工具名称: {tool.name}")
    print(f"工具别名: {tool.aliases}")
    result = tool._run()
    print(result)
    print(tool._run("full"))
    print(tool._run("date"))
    print(tool._run("time"))
