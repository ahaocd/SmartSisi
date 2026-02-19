"""
定位和天气工具 - A2A标准实现

集成IP定位和天气查询功能，简单实用的定位和天气查询，满足用户基本需求。
单独查询时简洁，搭配其他工具时可根据情况提供更详细信息。
"""

import requests
import json
import logging
from typing import Dict, Any, Optional, List, Union, Literal, Tuple
import asyncio
import time
import os
import re

# 导入标准A2A工具基类
from SmartSisi.llm.a2a.base_a2a_tool import StandardA2ATool

# 配置logger
logger = logging.getLogger("location_weather")
# 防止重复添加handler
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
# 防止日志传播到root logger
logger.propagate = False

# 腾讯地图API密钥
TENCENT_MAP_KEY = "JNLBZ-Q3TKQ-OEG54-2WPCV-U4AOK-RSFWT"

def get_location_by_ip(ip: Optional[str] = None) -> Dict[str, Any]:
    """
    根据IP地址获取用户位置信息
    
    Args:
        ip: 可选，用户的IP地址。如不提供则使用当前请求的IP
        
    Returns:
        Dict: 包含位置信息的字典
    """
    url = "https://apis.map.qq.com/ws/location/v1/ip"
    params = {"key": TENCENT_MAP_KEY}
    
    if ip:
        params["ip"] = ip
    
    try:
        logger.info(f"[位置获取] 开始请求IP定位: {ip or '当前IP'}")
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data.get("status") == 0:
            result = data.get("result", {})
            location = result.get("location", {})
            ad_info = result.get("ad_info", {})
            
            # 提取位置信息
            location_info = {
                "country": ad_info.get("nation", "中国"),
                "region": ad_info.get("province", ""),
                "city": ad_info.get("city", ""),
                "district": ad_info.get("district", ""),
                "lat": location.get("lat", 0),
                "lon": location.get("lng", 0),
                "adcode": ad_info.get("adcode", 0)
            }
            
            logger.info(f"[位置获取] 成功: {json.dumps(location_info, ensure_ascii=False)}")
            return location_info
        else:
            logger.error(f"[位置获取] API返回错误: {data.get('message')}, 状态码: {data.get('status')}")
            return {}
    except Exception as e:
        logger.error(f"[位置获取] 请求异常: {str(e)}")
        return {}

def get_weather(adcode: Union[int, str], weather_type: str = "now") -> Dict[str, Any]:
    """
    获取指定行政区划的天气信息
    
    Args:
        adcode: 行政区划代码
        weather_type: 天气类型，"now"为实时天气，"future"为未来天气预报
        
    Returns:
        Dict: 天气信息字典，获取失败则返回空字典
    """
    url = "https://apis.map.qq.com/ws/weather/v1/"
    params = {
        "key": TENCENT_MAP_KEY,
        "adcode": adcode,
        "type": weather_type
    }
    
    try:
        logger.info(f"[天气获取] 开始请求天气信息: adcode={adcode}, type={weather_type}")
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data.get("status") == 0:
            result = data.get("result", {})
            
            logger.info(f"[天气获取] 成功")
            logger.debug(f"[天气获取] 完整响应: {json.dumps(data, ensure_ascii=False)}")
            return result
        else:
            logger.error(f"[天气获取] API返回错误: {data.get('message')}, 状态码: {data.get('status')}")
    except Exception as e:
        logger.error(f"[天气获取] 请求异常: {str(e)}")
    
    return {}

# 生成简洁的天气描述
def generate_weather_summary(location_info: Dict[str, Any], weather_info: Dict[str, Any], is_brief: bool = True) -> str:
    """
    生成天气描述文本
    
    Args:
        location_info: 位置信息
        weather_info: 天气信息
        is_brief: 是否简洁模式
        
    Returns:
        str: 天气描述文本
    """
    # 提取位置信息
    city = location_info.get("city", "未知城市")
    if not city and location_info.get("region"):
        city = location_info.get("region")  # 如果没有城市信息，使用省份信息
    
    # 简洁模式，只返回关键信息
    if is_brief:
        # 检查是否有实时天气数据
        if "realtime" in weather_info and weather_info["realtime"]:
            # 处理realtime是列表的情况
            if isinstance(weather_info["realtime"], list):
                realtime = weather_info["realtime"][0]
            else:
                realtime = weather_info["realtime"]
                
            infos = realtime.get("infos", {})
            weather = infos.get("weather", "未知")
            temperature = infos.get("temperature", "未知")
            return f"{city}当前天气{weather}，气温{temperature}℃"
        
        # 检查是否有预报天气数据
        elif "forecast" in weather_info and weather_info["forecast"]:
            # 处理forecast是列表的情况
            if isinstance(weather_info["forecast"], list):
                forecast_data = weather_info["forecast"]
            else:
                forecast_data = [weather_info["forecast"]]
                
            if forecast_data and len(forecast_data) > 0:
                forecast_item = forecast_data[0]
                infos_array = forecast_item.get("infos", [])
                if infos_array and len(infos_array) > 0:
                    today = infos_array[0]  # 第一个预报条目
                    date = today.get("date", "今天")
                    day_info = today.get("day", {})
                    day_weather = day_info.get("weather", "未知")
                    day_temp = day_info.get("temperature", "未知")
                    night_temp = today.get("night", {}).get("temperature", "未知")
                    return f"{city}{date}天气{day_weather}，气温{night_temp}~{day_temp}℃"
            
        return f"抱歉，未能获取{city}的天气信息"
    
    # 详细模式
    else:
        result = []
        
        # 添加位置信息
        location_str = f"{location_info.get('region', '')}{location_info.get('city', '')}"
        if location_info.get('district'):
            location_str += location_info.get('district')
        
        result.append(f"📍 **{location_str}**")
        
        # 添加实时天气
        if "realtime" in weather_info and weather_info["realtime"]:
            # 处理realtime是列表的情况
            if isinstance(weather_info["realtime"], list):
                realtime = weather_info["realtime"][0]
            else:
                realtime = weather_info["realtime"]
                
            result.append("\n**实时天气**")
            infos = realtime.get("infos", {})
            result.append(f"🌡️ 温度: {infos.get('temperature')}℃")
            result.append(f"☁️ 天气: {infos.get('weather')}")
            result.append(f"💨 风向: {infos.get('wind_direction')} {infos.get('wind_power')}")
            result.append(f"💧 湿度: {infos.get('humidity')}%")
            result.append(f"🕒 更新: {realtime.get('update_time')}")
        
        # 添加预报天气
        if "forecast" in weather_info and weather_info["forecast"]:
            # 处理forecast是列表的情况
            if isinstance(weather_info["forecast"], list):
                forecast_data = weather_info["forecast"]
            else:
                forecast_data = [weather_info["forecast"]]
                
            if forecast_data:
                result.append("\n**未来天气预报**")
                
                for day in forecast_data[:3]:  # 只显示接下来3天
                    date = day.get("date")
                    week = day.get("week")
                    day_info = day.get("day", {})
                    night_info = day.get("night", {})
                    
                    result.append(f"\n• **{date} {week}**")
                    result.append(f"  白天: {day_info.get('weather')} {day_info.get('temperature')}℃")
                    result.append(f"  夜间: {night_info.get('weather')} {night_info.get('temperature')}℃")
                    result.append(f"  风向: {day_info.get('wind_direction')} {day_info.get('wind_power')}")
        
        return "\n".join(result)

# A2A标准工具类实现
class LocationWeatherTool(StandardA2ATool):
    """定位和天气查询工具"""
    
    # 默认高德地图API密钥
    DEFAULT_API_KEY = "470fdf698e3aad13a197f75430ef1eda"
    
    # API相关配置
    GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
    WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"
    WEATHER_FORECAST_URL = "https://restapi.amap.com/v3/weather/weatherInfo"
    
    # 城市查询正则表达式
    CITY_PATTERN = r'([\u4e00-\u9fa5]{1,10}(?:省|市|区|县|自治区|自治州)?)'
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化定位和天气查询工具
        
        Args:
            api_key: 高德地图API密钥（可选）
        """
        # 调用父类初始化方法
        super().__init__(
            name="location_weather",
            description="定位和天气查询工具，支持自动获取位置和查询天气",
            version="1.0.0"
        )
        
        # 设置API密钥
        self.api_key = api_key or os.getenv("AMAP_API_KEY") or self.DEFAULT_API_KEY
        
        # 天气关键词
        self.weather_keywords = [
            "天气", "气温", "温度", "下雨", "下雪", "晴天", "阴天", "多云",
            "气象", "预报", "今天", "明天", "后天", "冷不冷", "热不热", "冷吗", "热吗"
        ]
        
        # 预报关键词
        self.forecast_keywords = [
            "预报", "明天", "后天", "未来", "这周", "周末", "趋势", "变化"
        ]
        
        logger.info("LocationWeatherTool 初始化完成")
    
    async def process_query(self, query: str) -> str:
        """
        处理用户查询，实现A2A基类的抽象方法
        
        Args:
            query: 用户查询
            
        Returns:
            str: 处理结果
        """
        try:
            # 处理空查询和标准化查询
            if not query or len(query.strip()) < 2:
                logger.info(f"[天气] 收到空查询，将返回当前位置天气")
                location_info = get_location_by_ip()
                weather_info = get_weather(location_info.get("adcode"), "now")
                return generate_weather_summary(location_info, weather_info, True)
                
            # 处理简单天气查询
            if query.strip() in ["天气", "天气如何", "天气怎样", "天气怎么样", "天气预报"]:
                logger.info(f"[天气] 简单天气查询: {query}, 将返回当前位置天气")
                location_info = get_location_by_ip()
                weather_type = "future" if "预报" in query else "now"
                weather_info = get_weather(location_info.get("adcode"), weather_type)
                return generate_weather_summary(location_info, weather_info, True)
                
            # 正常处理其他查询
            logger.info(f"[天气] 处理查询: {query}")
            return await self._handle_query(query)
        except Exception as e:
            logger.error(f"[天气] 处理查询异常: {str(e)}")
            return f"处理天气查询时出错: {str(e)}"
    
    async def _handle_query(self, query: str) -> str:
        """
        处理天气查询
        
        Args:
            query: 查询文本
            
        Returns:
            str: 天气信息
        """
        # 判断是否是天气查询
        if not self._is_weather_query(query):
            return "这不是一个天气查询，请尝试询问'北京天气怎么样'或'今天天气如何'等。"
        
        # 判断是否需要详细信息
        is_brief = True
        if "详细" in query or "具体" in query:
            is_brief = False
        
        # 判断是否是预报查询
        is_forecast = self._is_forecast_query(query)
        
        # 提取城市名称
        city_name = self._extract_city_name(query)
        logger.info(f"[天气] 提取的城市名: {city_name}")
        
        # 如果没有提取到城市名称，则使用IP定位获取当前位置
        if city_name is None:
            logger.info(f"[天气] 未指定城市，使用IP定位")
            location_info = get_location_by_ip()
            
            # 检查是否成功获取位置
            if not location_info:
                return "无法获取当前位置，请明确指定城市名称。"
                
            adcode = location_info.get("adcode")
            if not adcode:
                return "获取当前位置编码失败，请明确指定城市名称。"
            
            # 获取天气信息
            weather_type = "future" if is_forecast else "now"
            weather_info = get_weather(adcode, weather_type)
            
            # 生成天气描述
            return generate_weather_summary(location_info, weather_info, is_brief)
        
        # 有指定城市的情况，继续使用高德地图API
        return await self._async_get_weather(city_name, is_forecast)
    
    def _parse_query_argument(self, query: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        解析查询参数
        
        Args:
            query: 可能是字符串或字典
            
        Returns:
            Tuple[str, Optional[Dict]]: 查询文本和上下文
        """
        context = None
        
        if isinstance(query, dict):
            # 从字典中提取文本和上下文
            text = query.get("query", query.get("text", ""))
            context = query.get("context")
        elif isinstance(query, str):
            # 尝试解析JSON
            if query.strip().startswith('{'):
                try:
                    data = json.loads(query)
                    text = data.get("query", data.get("text", query))
                    context = data.get("context")
                except:
                    text = query
            else:
                text = query
        else:
            text = str(query)
        
        return text, context
    
    def _extract_city_name(self, query: str) -> Optional[str]:
        """
        从查询中提取城市名称
        
        Args:
            query: 查询文本
            
        Returns:
            Optional[str]: 提取的城市名称或None（当查询中不包含城市名时）
        """
        # 空查询或极短查询直接返回None，使用IP定位
        if not query or len(query.strip()) < 3:
            logger.info(f"[天气] 空查询或极短查询，将使用IP定位")
            return None
            
        # 处理固定格式查询
        if query.strip() == "查询当前位置天气" or "当前位置天气" in query or "查询天气" == query.strip():
            logger.info(f"[天气] 标准化查询或明确要求当前位置天气，将使用IP定位")
            return None
        
        # 天气查询关键词，这些词本身不是城市名
        non_city_keywords = [
            "天气", "气温", "温度", "详细", "具体", 
            "预报", "明天", "后天", "未来", "今天", 
            "怎么样", "如何", "查询", "查看", "了解", "告诉我", "当前",
            "位置", "定位", "我的", "这里", "现在", "实时", "所在", "这边"
        ]
        
        # 清理查询文本，移除非城市关键词
        clean_query = query
        for keyword in non_city_keywords:
            clean_query = clean_query.replace(keyword, " ")
        
        # 检查是否剩余内容为空，如果是则使用IP定位
        if not clean_query.strip():
            logger.info(f"[天气] 清理关键词后无内容，将使用IP定位")
            return None
        
        # 使用正则表达式查找城市名
        city_matches = re.findall(self.CITY_PATTERN, clean_query)
        if city_matches:
            # 返回找到的第一个城市名
            logger.info(f"[天气] 成功提取城市名: {city_matches[0]}")
            return city_matches[0]
            
        # 检查特殊查询"查询当前位置天气"等
        if re.search(r'当前|现在|这里|我这里|这边|所在地|我的位置', query):
            logger.info(f"[天气] 检测到位置指示词，将使用IP定位")
            return None
            
        # 查询不包含城市名和当前位置的指示，也使用IP定位
        if query.strip() in ["天气", "天气如何", "天气怎样", "天气预报"]:
            logger.info(f"[天气] 检测到单纯天气查询，将使用IP定位")
            return None
            
        # 尝试从查询中提取剩余最可能的城市名候选词
        candidates = re.sub(r'[^\u4e00-\u9fa5]', ' ', clean_query).split()
        if candidates:
            # 过滤掉常见非地名词汇
            common_non_location_words = ["帮我", "请", "问一下", "知道", "想", "需要", "帮忙", "最近"]
            filtered_candidates = [word for word in candidates if word not in common_non_location_words and len(word) >= 2]
            
            if filtered_candidates:
                # 取最长的词作为可能的城市名
                filtered_candidates.sort(key=len, reverse=True)
                logger.info(f"[天气] 提取可能的城市名: {filtered_candidates[0]}")
                return filtered_candidates[0]
        
        # 无法提取城市名，返回None，表示需要使用IP定位
        logger.info(f"[天气] 无法提取城市名，将使用IP定位")
        return None
    
    def _is_weather_query(self, query: str) -> bool:
        """
        判断是否是天气查询
        
        Args:
            query: 查询文本
            
        Returns:
            bool: 是否是天气查询
        """
        for keyword in self.weather_keywords:
            if keyword in query:
                return True
        return False
    
    def _is_forecast_query(self, query: str) -> bool:
        """
        判断是否是天气预报查询
        
        Args:
            query: 查询文本
            
        Returns:
            bool: 是否是天气预报查询
        """
        for keyword in self.forecast_keywords:
            if keyword in query:
                return True
        return False
    
    async def _async_get_location(self, city_name: str) -> str:
        """
        异步获取位置信息
        
        Args:
            city_name: 城市名称
            
        Returns:
            str: 位置信息
        """
        params = {
            "key": self.api_key,
            "address": city_name,
            "output": "json"
        }
        
        try:
            response = requests.get(self.GEOCODE_URL, params=params, timeout=5)
            data = response.json()
            
            if data.get("status") == "1" and data.get("count", "0") != "0":
                result = data.get("geocodes", [{}])[0]
                return result
            else:
                logger.warning(f"无法找到城市 {city_name} 的编码")
                return {}
        except Exception as e:
            logger.error(f"获取位置信息出错: {str(e)}")
            return {}
    
    def _get_location(self, city_name: str) -> str:
        """
        同步获取位置信息
        
        Args:
            city_name: 城市名称
            
        Returns:
            str: 位置信息
        """
        # 创建事件循环运行异步方法
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._async_get_location(city_name))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"同步获取位置信息出错: {str(e)}")
            return {}
    
    async def _async_get_weather(self, city_name: str, is_forecast: bool = False) -> str:
        """
        异步获取天气信息
        
        Args:
            city_name: 城市名称
            is_forecast: 是否获取天气预报
            
        Returns:
            str: 天气信息
        """
        try:
            # 获取城市编码
            location = await self._async_get_location(city_name)
            if not location:
                return f"无法找到城市'{city_name}'的位置信息。"
            
            # 提取adcode
            adcode = location.get("adcode", "")
            if not adcode:
                return f"无法获取城市'{city_name}'的行政区划编码。"
            
            # 构建请求参数
            params = {
                "key": self.api_key,
                "city": adcode,
                "extensions": "all" if is_forecast else "base",
                "output": "json"
            }
            
            # 选择API URL
            api_url = self.WEATHER_FORECAST_URL if is_forecast else self.WEATHER_URL
            
            # 发送请求
            response = requests.get(api_url, params=params, timeout=5)
            data = response.json()
            
            if data.get("status") == "1":
                # 处理结果
                if is_forecast:
                    # 天气预报
                    forecasts = data.get("forecasts", [])
                    if forecasts and len(forecasts) > 0:
                        forecast = forecasts[0]
                        city = forecast.get("city", city_name)
                        casts = forecast.get("casts", [])
                        
                        # 构建位置信息
                        location_info = {
                            "city": city,
                            "region": location.get("province", ""),
                            "adcode": adcode
                        }
                        
                        # 构建天气信息
                        weather_info = {
                            "forecast": {
                                "infos": casts
                            }
                        }
                        
                        # 生成天气描述
                        return generate_weather_summary(location_info, weather_info, True)
                    else:
                        return f"未能获取'{city_name}'的天气预报信息。"
                else:
                    # 实时天气
                    lives = data.get("lives", [])
                    if lives and len(lives) > 0:
                        live = lives[0]
                        city = live.get("city", city_name)
                        
                        # 构建位置信息
                        location_info = {
                            "city": city,
                            "region": location.get("province", ""),
                            "adcode": adcode
                        }
                        
                        # 构建天气信息
                        weather_info = {
                            "realtime": {
                                "infos": {
                                    "weather": live.get("weather", "未知"),
                                    "temperature": live.get("temperature", "未知"),
                                    "wind_direction": live.get("winddirection", "未知"),
                                    "wind_power": f"{live.get('windpower', '未知')}级",
                                    "humidity": live.get("humidity", "未知")
                                },
                                "update_time": live.get("reporttime", "未知")
                            }
                        }
                        
                        # 生成天气描述
                        return generate_weather_summary(location_info, weather_info, True)
                    else:
                        return f"未能获取'{city_name}'的实时天气信息。"
            else:
                return f"获取'{city_name}'的天气信息失败: {data.get('info', '未知错误')}"
                
        except Exception as e:
            logger.error(f"获取天气信息出错: {str(e)}")
            return f"获取'{city_name}'的天气信息时出错: {str(e)}"
    
    def _get_weather(self, city_name: str, is_forecast: bool = False) -> str:
        """
        同步获取天气信息
        
        Args:
            city_name: 城市名称
            is_forecast: 是否获取天气预报
            
        Returns:
            str: 天气信息
        """
        # 创建事件循环运行异步方法
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._async_get_weather(city_name, is_forecast))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"同步获取天气信息出错: {str(e)}")
            return f"获取'{city_name}'的天气信息时出错: {str(e)}"
    
    def _get_city_code(self, city_name: str) -> Optional[str]:
        """
        获取城市编码
        
        Args:
            city_name: 城市名称
            
        Returns:
            Optional[str]: 城市编码
        """
        params = {
            "key": self.api_key,
            "address": city_name,
            "output": "json"
        }
        
        try:
            response = requests.get(self.GEOCODE_URL, params=params, timeout=5)
            data = response.json()
            
            if data.get("status") == "1" and data.get("count", "0") != "0":
                geocodes = data.get("geocodes", [])
                if geocodes:
                    return geocodes[0].get("adcode", "")
            
            logger.warning(f"无法找到城市 {city_name} 的编码")
            return None
        except Exception as e:
            logger.error(f"获取城市编码出错: {str(e)}")
            return None
    
    def get_api_status(self) -> Dict[str, Any]:
        """
        获取API状态
        
        Returns:
            Dict: API状态信息
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "api_key_configured": bool(self.api_key),
            "capabilities": self.get_capabilities()
        }
    
    def get_capabilities(self) -> List[str]:
        """
        获取工具能力列表
        
        Returns:
            List[str]: 能力列表
        """
        return [
            "实时天气查询",
            "天气预报查询",
            "支持全国城市",
            "自动IP定位",
            "自动识别城市名",
            "简洁/详细模式"
        ]
    
    def get_examples(self) -> List[str]:
        """
        获取示例查询
        
        Returns:
            List[str]: 示例查询列表
        """
        return [
            "北京今天天气怎么样？",
            "上海明天会下雨吗？",
            "天气怎么样？",  # 使用IP定位自动获取当前位置
            "详细查询广州天气",
            "未来三天杭州天气预报",
            "我在成都，天气如何？"
        ]

def create_tool(api_key: Optional[str] = None):
    """
    创建工具实例
    
    Args:
        api_key: 高德地图API密钥
        
    Returns:
        LocationWeatherTool: 工具实例
    """
    return LocationWeatherTool(api_key)

# 添加模块级invoke函数供A2A服务器调用
def invoke(params):
    """
    模块级invoke函数，供A2A服务器直接调用
    
    Args:
        params: 调用参数，可以是字符串或字典
        
    Returns:
        Dict: 工具执行结果
    """
    logger.info(f"[location_weather] 模块级invoke调用，参数: {params}")
    
    # 提取查询文本
    query = None
    if isinstance(params, dict):
        # 如果是JSON-RPC格式
        if "jsonrpc" in params and "method" in params and "params" in params:
            inner_params = params.get("params", {})
            query = inner_params.get("query", inner_params.get("location", ""))
        else:
            # 尝试各种可能的参数名
            query = params.get("query", params.get("location", ""))
    else:
        # 如果是字符串或其他类型
        query = str(params)
    
    if not query:
        query = "天气如何"  # 默认查询
    
    try:
        # 使用同步方法获取位置和天气信息，避免事件循环问题
        if "北京" in query or "beijing" in query.lower():
            location_info = {
                "country": "中国", 
                "region": "北京市", 
                "city": "北京市",
                "district": "", 
                "adcode": 110000
            }
            weather_info = get_weather(110000)
        elif "上海" in query or "shanghai" in query.lower():
            location_info = {
                "country": "中国", 
                "region": "上海市", 
                "city": "上海市",
                "district": "", 
                "adcode": 310000
            }
            weather_info = get_weather(310000)
        elif "广州" in query or "guangzhou" in query.lower():
            location_info = {
                "country": "中国", 
                "region": "广东省", 
                "city": "广州市",
                "district": "", 
                "adcode": 440100
            }
            weather_info = get_weather(440100)
        else:
            # 默认使用IP定位
            location_info = get_location_by_ip()
            adcode = location_info.get("adcode", 0)
            weather_info = get_weather(adcode) if adcode else {}
        
        # 安全处理返回数据
        logger.info(f"[location_weather] 获取到的天气数据: {weather_info}")
        realtime_data = {}
        
        # 处理realtime数据可能是列表的情况
        if "realtime" in weather_info:
            if isinstance(weather_info["realtime"], list):
                if len(weather_info["realtime"]) > 0:
                    realtime_data = weather_info["realtime"][0]
            else:
                realtime_data = weather_info["realtime"]
            
        # 安全提取信息
        temperature = "未知"
        condition = "未知"
        humidity = "未知"
        
        if "infos" in realtime_data:
            infos = realtime_data.get("infos", {})
            temperature = infos.get("temperature", "未知")
            condition = infos.get("weather", "未知")
            humidity = infos.get("humidity", "未知")
        
        # 简化版本的天气描述
        city_name = location_info.get("city", location_info.get("region", "未知位置"))
        if not city_name or city_name == "":
            city_name = "当前位置"
            
        # 简单生成天气描述
        weather_text = f"{city_name}当前天气{condition}，气温{temperature}°C，湿度{humidity}%"
        logger.info(f"[location_weather] 生成的天气描述: {weather_text}")
        
        return {
            "weather": {
                "query": query,
                "location": city_name,
                "result": weather_text,
                "temperature": temperature,
                "condition": condition,
                "humidity": humidity,
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.error(f"[location_weather] 处理查询出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            "weather": {
                "query": query,
                "error": f"获取天气信息失败: {str(e)}",
                "timestamp": time.time()
            }
        }

# 测试代码
if __name__ == "__main__":
    # 测试代码省略
    async def test_async():
        # 测试代码，保持不变...
        ...
    
    asyncio.run(test_async()) 