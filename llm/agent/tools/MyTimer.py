import sqlite3
import re
from typing import Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool

class MyTimerInput(BaseModel):
    """设置日程的输入参数"""
    time: str = Field(
        ..., 
        description="时间，24小时制格式为HH:MM，如15:30"
    )
    repeat_rule: str = Field(
        ..., 
        description="循环规则，7位二进制数字，每位代表周一至周日，1为循环，0为不循环，如1000100代表每周一和周五循环"
    )
    content: str = Field(
        ..., 
        description="提醒内容，描述需要提醒的事项"
    )

class MyTimer(BaseTool):
    """设置日程工具"""
    name: str = "my_timer"
    description: str = "设置日程提醒。需要提供时间(HH:MM)、循环规则(七位二进制，代表周一至周日)和提醒内容。"
    args_schema: type[BaseModel] = MyTimerInput
    uid: int = 0

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None, uid: int = 0):
        """初始化设置日程工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        super().__init__(**tool_params)
        self.uid = uid

    async def _arun(self, time: str, repeat_rule: str, content: str) -> str:
        """异步设置日程"""
        return self._run(time, repeat_rule, content)

    def _run(self, time: str, repeat_rule: str, content: str) -> str:
        """
        设置日程提醒
        
        Args:
            time: 时间，24小时制格式为HH:MM，如15:30
            repeat_rule: 循环规则，7位二进制数字，每位代表周一至周日，1为循环，0为不循环
            content: 提醒内容，描述需要提醒的事项
            
        Returns:
            str: 设置结果描述
        """
        # 验证时间格式
        if not re.match(r'^[0-2][0-9]:[0-5][0-9]$', time):
            return "时间格式错误。请按照'HH:MM'格式提供时间，如15:30。"

        # 验证循环规则格式
        if not re.match(r'^[01]{7}$', repeat_rule):
            return "循环规则格式错误。请提供长度为7的0和1组成的字符串，如1000100代表每周一和周五循环。"

        # 验证事项内容
        if not isinstance(content, str) or not content:
            return "事项内容必须为非空字符串。"

        # 数据库操作
        conn = sqlite3.connect('timer.db')
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO timer (time, repeat_rule, content, uid) VALUES (?, ?, ?, ?)", 
                          (time, repeat_rule, content, self.uid))
            conn.commit()
            timer_id = cursor.lastrowid
            return f"日程设置成功，ID为：{timer_id}，时间：{time}，循环规则：{self._format_repeat_rule(repeat_rule)}，内容：{content}"
        except sqlite3.Error as e:
            return f"数据库错误: {e}"
        finally:
            conn.close()
    
    def _format_repeat_rule(self, repeat_rule: str) -> str:
        """将二进制循环规则转换为可读的文本格式"""
        days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        active_days = [days[i] for i in range(7) if repeat_rule[i] == "1"]
        
        if not active_days:
            return "不循环"
        elif len(active_days) == 7:
            return "每天"
        else:
            return "每" + "、".join(active_days)

if __name__ == "__main__":
    my_timer = MyTimer()
    result = my_timer._run("15:15", "0000001", "提醒主人叫咖啡")
    print(result)
    # 测试错误情况
    print(my_timer._run("25:15", "0000001", "错误时间"))
    print(my_timer._run("15:15", "00001", "错误循环规则"))
