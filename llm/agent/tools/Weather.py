import os
from typing import Any, Optional, Dict
import requests
import json
import time
from utils import util, config_util
from langchain_core.tools import BaseTool, tool
from pydantic import Field, BaseModel

class WeatherInput(BaseModel):
    """天气查询工具的输入结构"""
    location: str = Field(
        ..., 
        description="要查询天气的城市名称，例如：北京、上海、广州、深圳、杭州、南京、重庆、成都、西安、武汉等。直接输入中文城市名即可，无需其他格式。"
    )

class Weather(BaseTool):
    """查询天气情况的工具。
    
    当用户询问关于天气、温度、气温、阴晴、下雨、下雪、季节、冷热等相关问题时使用此工具。
    
    如果用户没有明确指定位置，应先使用IP定位工具获取当前位置，再查询天气。
    
    参数: 
    - location (可选): 城市名称或地区。如未提供，将自动获取位置。
    
    使用场景:
    - "今天天气怎么样?" → 获取位置后查询
    - "成都冷不冷?" → 查询成都温度
    - "明天会下雨吗?" → 获取位置后查询明天降水概率
    """
    name: str = "weather"
    description: str = "用于查询全国城市天气预报、天气状况、温度、空气质量、预警信息等。适用于回答'今天天气怎么样'、'北京天气'、'上海下雨吗'、'广州温度多少'、'济南天气预报'、'成都空气质量'、'杭州会下雨吗'等天气相关问题。只需提供城市名称即可，支持全国所有中文城市名。"
    args_schema: type[BaseModel] = WeatherInput
    
    # 百度云天气API参数
    _api_url: str = "https://getweather.api.bdymkt.com/lundear/weather1d"
    _api_app_code: str = "3116c02bf3c741b9ace221e5ce73d59d"  # 新的AppCode
    
    # 缓存机制，避免频繁请求
    _cache = {}
    _cache_time = {}
    _cache_expire = 600  # 10分钟缓存
    
    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        """初始化天气工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        super().__init__(**tool_params)
    
    async def _arun(self, location: str) -> str:
        """异步查询天气"""
        return self._run(location)
    
    def _run(self, location: str) -> str:
        """
        查询指定城市的天气情况
        
        Args:
            location: 城市名称，如北京、上海等
            
        Returns:
            str: 格式化的天气信息
        """
        # 检查缓存
        current_time = time.time()
        if location in self._cache and current_time - self._cache_time.get(location, 0) < self._cache_expire:
            return self._cache[location]
        
        # 准备API请求参数
        params = {
            'areaCn': location,
            'needIndex': '1',  # 获取生活指数
            'needalarm': '1'   # 获取天气预警
        }
        
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'X-Bce-Signature': f'AppCode/{self._api_app_code}'
        }
        
        try:
            # 发送请求
            response = requests.get(
                self._api_url, 
                params=params, 
                headers=headers,
                timeout=5  # 5秒超时
            )
            
            if response.status_code != 200:
                return f"天气查询失败，HTTP状态码: {response.status_code}"
            
            # 解析响应
            result = response.json()
            
            # 检查API返回状态
            if result.get("code") != "0":
                error_msg = result.get("desc", "未知错误")
                return f"天气查询失败: {error_msg}"
            
            # 提取天气数据
            data = result.get("data", {})
            city_info = data.get("cityInfo", {})
            now = data.get("now", {})
            day = data.get("day", {})
            night = data.get("night", {})
            
            # 获取城市名
            city_name = city_info.get("areaCn", location)
            
            # 提取当前天气情况
            current_weather = now.get("weather", "未知")
            current_temp = now.get("temp", "未知")
            current_wind = f"{now.get('WD', '未知')} {now.get('WS', '未知')}"
            current_humidity = now.get("SD", "未知")
            current_aqi = now.get("aqi", "未知")
            
            # 提取今日天气预报
            day_weather = day.get("weather", "未知")
            day_temp = day.get("temperature", "未知")
            night_temp = night.get("temperature", "未知")
            day_wind = f"{day.get('wind', '未知')} {day.get('wind_pow', '未知')}"
            
            # 格式化输出
            output = f"{city_name}天气情况：\n"
            output += f"当前：{current_weather}，{current_temp}°C，{current_wind}，湿度{current_humidity}，空气质量指数{current_aqi}\n"
            output += f"今日：{day_weather}，{night_temp}°C~{day_temp}°C，{day_wind}\n"
            
            # 添加日出日落信息
            sun_up = day.get("sunUp", "")
            sun_down = night.get("sunDown", "")
            if sun_up or sun_down:
                output += f"日出日落：{sun_up or '未知'} / {sun_down or '未知'}\n"
            
            # 提取并添加天气预警信息
            alarm_list = data.get("alarmList", [])
            if alarm_list:
                output += "\n预警信息:\n"
                for alarm in alarm_list:
                    signal_type = alarm.get("signalType", "未知")
                    signal_level = alarm.get("signalLevel", "未知")
                    issue_time = alarm.get("issueTime", "未知")
                    output += f"- {signal_type}{signal_level} ({issue_time})\n"
            
            # 提取并添加生活指数
            life_index = data.get("lifeIndex", {})
            if life_index:
                output += "\n生活指数:\n"
                # 添加一些关键的生活指数
                index_map = {
                    "cold": "感冒指数",
                    "clothes": "穿衣指数",
                    "uv": "紫外线指数",
                    "carwash": "洗车指数",
                    "sport": "运动指数",
                    "umbrella": "雨伞指数"
                }
                for index_key, index_name in index_map.items():
                    if index_key in life_index:
                        index_info = life_index[index_key]
                        index_desc = index_info.get("desc", "未知")
                        output += f"- {index_name}: {index_desc}\n"
            
            # 更新缓存
            self._cache[location] = output
            self._cache_time[location] = current_time
            
            return output
            
        except requests.Timeout:
            return "天气查询超时，请稍后再试"
        except Exception as e:
            util.log(2, f"天气查询失败: {str(e)}")
            return f"天气查询失败: {str(e)}"

# 测试用例
if __name__ == "__main__":
    weather_tool = Weather()
    print(weather_tool._run("北京"))
    print(weather_tool._run("上海"))
    print(weather_tool._run("成都"))
