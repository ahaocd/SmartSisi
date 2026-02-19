"""
时间查询工具 - 返回当前系统时间
"""

import datetime
from typing import Dict, Any, Optional, List
from langchain_core.tools import BaseTool, tool
from .base_tool import SisiBaseTool
from utils import util

@tool
def get_time(format: str = "full") -> str:
    """
    获取当前系统时间和日期，可用于回答'现在几点了'、'当前时间'、'今天星期几'等问题
    
    Args:
        format: 时间格式，可选值：full(完整)、date(仅日期)、time(仅时间)、weekday(仅星期)
    """
    try:
        # 获取当前时间
        now = datetime.datetime.now()
        
        # 格式化日期
        date_str = now.strftime("%Y年%m月%d日")
        
        # 格式化时间
        time_str = now.strftime("%H:%M:%S")
        
        # 获取星期
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[now.weekday()]
        
        # 根据格式构建响应
        if format.lower() == "date":
            response = f"今天是 {date_str}"
        elif format.lower() == "time":
            response = f"现在时间是 {time_str}"
        elif format.lower() == "weekday":
            response = f"今天是 {weekday}"
        else: # full
            response = f"当前时间是 {date_str} {weekday} {time_str}"
        
        # 记录日志
        util.log(1, f"[TimeQuery] 成功查询时间: {format}")
        
        return response
    except Exception as e:
        error_msg = f"时间查询失败: {str(e)}"
        util.log(2, f"[TimeQuery] {error_msg}")
        return error_msg

# 为了向后兼容，同时支持多种命名风格
class TimeQuery(SisiBaseTool):
    """查询当前系统时间的工具"""
    name: str = "get_time"  # 保持原有名称不变
    description: str = "获取当前系统时间和日期，可用于回答'现在几点了'、'当前时间'、'今天星期几'等问题。别名包括: query_time, QueryTime, GetTime, TimeQuery"
    aliases: List[str] = ["query_time", "QueryTime", "GetTime", "TimeQuery", "getTime", "time"]  # 添加别名支持
    
    def __init__(self, uid: int = 0, name: Optional[str] = None, description: Optional[str] = None):
        """
        初始化时间查询工具
        
        Args:
            uid: 用户ID
            name: 可选的工具名称
            description: 可选的工具描述
        """
        tool_params = {"uid": uid}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
        
        super().__init__(**tool_params)
        
        # 记录工具初始化
        util.log(1, f"[TimeQuery] 工具初始化: 名称={self.name}, 别名={self.aliases}")
    
    def get_name_aliases(self) -> List[str]:
        """获取工具名称和别名列表"""
        return [self.name] + self.aliases

    def _run(self, format: str = "full") -> str:
        """
        执行时间查询
        
        Args:
            format: 时间格式，可选值：full(完整)、date(仅日期)、time(仅时间)、weekday(仅星期)
            
        Returns:
            str: 格式化的时间信息
        """
        util.log(1, f"[TimeQuery] 执行工具: {self.name}, 格式={format}")
        return get_time(format)
    
    async def _arun(self, format: str = "full") -> str:
        """
        异步执行时间查询
        
        Args:
            format: 时间格式，可选值：full(完整)、date(仅日期)、time(仅时间)、weekday(仅星期)
            
        Returns:
            str: 格式化的时间信息
        """
        return self._run(format)

if __name__ == "__main__":
    # 测试时间查询工具
    print(get_time())  # 完整时间
    print(get_time("date"))  # 仅日期
    print(get_time("time"))  # 仅时间
    print(get_time("weekday"))  # 仅星期
    
    # 兼容性测试
    tool = TimeQuery()
    print(f"工具名称: {tool.name}")
    print(f"工具别名: {tool.aliases}")
    print(tool._run())  # 完整时间
