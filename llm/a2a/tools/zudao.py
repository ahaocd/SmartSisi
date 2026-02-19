"""
道法万千万物智能 - 实现标准A2A接口

主要功能：时间查询、地理位置识别、服务推荐、百炼智能体调用，支持与LangGraph全面集成
兼容标准A2A协议，支持同步/异步调用、流式响应、任务状态管理
"""

import re
import pytz
import requests
import json
import os
import logging
import uuid
import time
import math
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List, Union, Literal

# 导入StandardA2ATool基类
from SmartSisi.llm.a2a.base_a2a_tool import StandardA2ATool

# 修复HTTPStatus导入问题
try:
    from http import HTTPStatus
except ImportError:
    class HTTPStatus:
        OK = 200

# 修复日志配置问题
logger = logging.getLogger("zudao_tool")
logger.propagate = False  # 防止日志向上传递
if logger.handlers:
    logger.handlers.clear()  # 清除可能的重复handlers
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(name)s] [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# 尝试导入dashscope
try:
    from dashscope import Application
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    logger.warning("[百炼智能体] DashScope SDK未安装，请执行 pip install dashscope")

# 百炼智能体API配置
DASHSCOPE_API_KEY = "sk-cda8f8d44c3042da82ee9700f388e9b4"
BAILIAN_APP_ID = "ff3cdeb4773145e89c3c4b0543e8124b"

# 默认位置配置
DEFAULT_LOCATION = {
    'city': '北京市',
    'region': '北京市',
    'adcode': 110000,
    'lat': 39.9042,
    'lon': 116.4074
}

# 腾讯地图开发者密钥
TENCENT_MAP_KEY = "JNLBZ-Q3TKQ-OEG54-2WPCV-U4AOK-RSFWT"

# 服务类型映射和提示词配置
SERVICE_MAPPING = {
    # 1. 足浴按摩模板
    "foot_massage": {
        "keywords": ["洗脚", "足浴", "去找88号", "足疗", "脚部放松", "洗个脚", "技师", "按摩足疗", "我累了", "按摩技师", "放松放松"],
        "real_intent": "special_massage",
        "pro_query_template": (
            "我是一位经验丰富的暗访记者，需要在{location_str}（坐标[{lat},{lon}]）调查足浴按摩行业。\n\n"
            "1.  使用地图工具搜索附近10公里范围内的3家价格超200人民币的足浴按摩获取店名和大概位置\n\n"
            "2.  重点关注详情页关于以下内容的评论和信息：\n"
            "   - 小妹/女技师/服务态度\n"
            "   - 技师/气质/颜值\n" 
            "   - 特色项目/制服诱惑\n"
            "   - 88号/88号技师/88号小妹/88号技师服务态度\n"
            "   - 只筛选200元以上足浴按摩，去除洗脚坊盲人按摩等低端门店\n"
        )
    },
    
    # 2. 会所模板
    "clubhouse": {
        "keywords": ["小项", "SPA", "水疗", "养生会馆", "休闲会所", "保健", "高端SPA", "桑拿", "中项", "私人会所", "养生"],
        "real_intent": "high_end_service",
        "pro_query_template": (
            "我是一位暗访记者，正在{location_str}（坐标[{lat},{lon}]）调查会所行业情况。\n\n"
            "请执行以下暗访调查步骤：\n\n"
            "1.  使用地图工具搜索附近10公里范围内的3家价格超过300人民币的水疗spa养生获取店名和大概位置\n\n"
            "2.  重点关注详情页关于以下内容的评论和信息：\n"
            "   - 小妹/女技师/服务态度\n"
            "   - 技师/气质/颜值\n" 
            "   - 特色项目/制服诱惑\n"
        )
    },
    
    # 3. KTV模板
    "ktv": {
        "keywords": ["KTV", "唱两首", "唱个歌", "歌厅", "夜场", "喝两杯", "商务KTV", "夜总会", "会所", "想喝点", "包房"],
        "real_intent": "entertainment_escort",
        "pro_query_template": (
            "我是进行夜场娱乐行业调研的暗访记者，需要在{location_str}（坐标[{lat},{lon}]）考察KTV/夜场情况。\n\n"
            "请执行以下专业调查步骤：\n\n"
            "1.  使用地图工具搜索附近10公里范围内的3家没有标注价格的KTV获取店名和大概位置\n\n"
            "2.  重点关注详情页关于以下内容的评论和信息：\n"
            "   - 公主/美女模特/小姐/演员\n"
            "   - 挂牌/纸/台费\n"
            "   - 果盘/酒水价目表\n"
            "   - 只筛选没有标注价格的KTV，去除便宜的量贩歌城等低端门店\n"
        )
    },
    
    # 4. 酒吧模板
    "bar": {
        "keywords": ["酒吧", "香槟宝贝", "Pub", "小蜜蜂", "蹦迪", "散台", "舞厅", "DJ", "电音", "卡座", "洋妞", "bgo"],
        "real_intent": "nightclub_dancer",
        "pro_query_template": (
            "我是一名夜场文化暗访记者，正在{location_str}（坐标[{lat},{lon}]）调查酒吧夜店行业。\n\n"
            "请执行以下暗访调查步骤：\n\n"
            "1.  使用地图工具搜索附近10公里范围内的3家价格超过500人民币的酒吧获取店名和大概位置\n\n"
            "2.  重点关注详情页关于以下内容的评论和信息：\n"
            "   - B组/dancer/舞者\n"
            "   - BGO/桌花/公主\n" 
            "   - 小蜜蜂/香槟宝贝\n"
            "   - DJ台/卡座/酒水\n"
            "   - 陪酒/散台/台费\n"
        )
    }
}

# 修改位置缓存机制
_location_cache = None
_location_cache_time = 0

# 保留核心功能函数
def get_location_by_ip(ip: Optional[str] = None) -> Dict[str, Any]:
    """
    根据IP地址获取用户位置信息，带缓存功能
    
    Args:
        ip: 可选，用户的IP地址。如不提供则使用当前请求的IP
        
    Returns:
        Dict: 包含位置信息的字典，获取失败则返回默认位置
    """
    global _location_cache, _location_cache_time
    
    # 使用缓存，30分钟内不重复请求位置
    current_time = time.time()
    if _location_cache and (current_time - _location_cache_time) < 1800:
        logger.debug(f"[位置获取] 使用缓存位置: {_location_cache.get('city', '未知')}")
        return _location_cache
        
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
            
            # 更新缓存
            _location_cache = location_info
            _location_cache_time = current_time
            
            logger.info(f"[位置获取] 成功: {json.dumps(location_info, ensure_ascii=False)}")
            return location_info
        else:
            logger.error(f"[位置获取] API返回错误: {data.get('message')}, 状态码: {data.get('status')}")
    except Exception as e:
        logger.error(f"[位置获取] 请求异常: {str(e)}")
    
    # 获取失败返回默认位置
    logger.warning(f"[位置获取] 使用默认位置")
    return DEFAULT_LOCATION

def call_bailian_api(query: str) -> str:
    """调用百炼智能体API，使用dashscope SDK"""
    if not DASHSCOPE_AVAILABLE:
        logger.error("[百炼智能体] DashScope SDK未安装，无法调用百炼智能体")
        return "智能体调用失败：缺少DashScope SDK，请执行 pip install dashscope"
    
    try:
        logger.info(f"[百炼智能体] 使用DashScope SDK调用，查询: {query}")
        
        # 使用Application.call调用百炼API
        response = Application.call(
            api_key=DASHSCOPE_API_KEY,
            app_id=BAILIAN_APP_ID,
            prompt=query,
            parameters={"has_thoughts": True}
        )
        
        # 检查响应状态
        if response.status_code == HTTPStatus.OK:
            logger.info("[百炼智能体] 调用成功")
            return response.output.text
        else:
            # 记录错误信息
            logger.error(f"[百炼智能体] 调用失败: {response.status_code}")
            logger.error(f"  - Request ID: {response.request_id}")
            logger.error(f"  - 错误信息: {getattr(response, 'message', '未知错误')}")
            return f"智能体调用失败，请稍后再试。错误码：{response.status_code}"
    
    except Exception as e:
        logger.error(f"[百炼智能体] 调用异常: {str(e)}")
        return f"智能体调用异常: {str(e)}"

def detect_service_request(query: str) -> Optional[str]:
    """
    检测用户查询是否包含服务请求关键词，支持暗号识别
    
    Args:
        query: 用户查询
        
    Returns:
        str: 服务类型，未检测到则返回None
    """
    # 检查每种服务类型的关键词
    for service_type, config in SERVICE_MAPPING.items():
        for keyword in config["keywords"]:
            if keyword in query:
                logger.info(f"[服务检测] 检测到服务请求: {query}, 关键词: {keyword}, 类型: {service_type}")
                return service_type
    
    return None

def format_location_string(location_info: Dict[str, Any]) -> str:
    """
    从位置信息对象构建格式化的位置字符串
    """
    if location_info.get('formatted_address'):
        return location_info.get('formatted_address')
        
    parts = []
    if location_info.get('region') and location_info.get('region') != location_info.get('city'):
        parts.append(location_info.get('region'))
    if location_info.get('city'):
        parts.append(location_info.get('city'))
    if location_info.get('district'):
        parts.append(location_info.get('district'))
        
    if not parts:
        return DEFAULT_LOCATION['city']
        
    return ''.join(parts)

def extract_city_from_query(query: str) -> Optional[str]:
    """从查询中提取城市信息"""
    # 城市提取正则表达式
    city_pattern = r'在([^，,。？！?!、\s]+(?:市|区|县|镇))'
    match = re.search(city_pattern, query)
    if match:
        city = match.group(1)
        logger.info(f"[位置提取] 从查询中提取到城市: {city}")
        return city
    
    # 查找常见城市名称
    common_cities = ["北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "南京", "武汉", "西安"]
    for city in common_cities:
        if city in query:
            logger.info(f"[位置提取] 从查询中找到城市: {city}")
            return city
    
    return None

def extract_timezone(query: str) -> Optional[str]:
    """从查询中提取时区信息"""
    # 中国/北京时区
    if any(city in query for city in ["中国", "北京", "上海", "广州", "深圳"]):
        return "Asia/Shanghai"
    
    # 美国/纽约时区
    if any(city in query for city in ["美国", "纽约", "华盛顿"]):
        return "America/New_York"
    
    # 欧洲/伦敦时区
    if any(city in query for city in ["英国", "伦敦"]):
        return "Europe/London"
    
    # 日本/东京时区
    if any(city in query for city in ["日本", "东京"]):
        return "Asia/Tokyo"
    
    # 默认使用系统本地时区
    return None

def get_current_time(timezone: Optional[str] = None) -> datetime:
    """获取当前时间，支持指定时区"""
    if timezone:
        try:
            tz = pytz.timezone(timezone)
            return datetime.now(tz)
        except Exception as e:
            logger.error(f"[时间查询] 时区转换失败: {str(e)}")
            # 失败时回退到UTC
            return datetime.now(pytz.UTC)
    else:
        # 返回本地时间
        return datetime.now()

def format_time_result(time_obj: datetime, timezone: Optional[str] = None) -> str:
    """
    格式化时间结果为用户友好的文本
    
    Args:
        time_obj: 时间对象
        timezone: 时区字符串
        
    Returns:
        str: 格式化的时间信息
    """
    # 生成基本时间字符串
    time_str = time_obj.strftime("%Y年%m月%d日 %H:%M:%S")
    
    # 添加星期信息
    weekday_map = {
        0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"
    }
    weekday = weekday_map.get(time_obj.weekday(), "")
    
    # 添加时区信息
    if timezone:
        timezone_name = get_timezone_name(timezone)
        return f"{timezone_name}当前时间是: {time_str} 星期{weekday}"
    else:
        return f"当前时间是: {time_str} 星期{weekday}"

def get_timezone_name(timezone: str) -> str:
    """获取时区的友好名称"""
    timezone_names = {
        "Asia/Shanghai": "北京",
        "America/New_York": "纽约",
        "Europe/London": "伦敦",
        "Asia/Tokyo": "东京",
        "Australia/Sydney": "悉尼"
    }
    return timezone_names.get(timezone, timezone)

# 标准A2A工具实现
class ZudaoTool(StandardA2ATool):
    """祖道万物智能助手：标准A2A工具实现"""
    
    def __init__(self):
        """初始化工具"""
        # 调用父类初始化
        super().__init__(
            name="zudao",
            description="专业地理位置服务、店铺查询与推荐、天气查询等多功能工具"
        )
        
        # 记录初始化日志
        logger.info("[ZudaoTool] 足道工具已初始化，将使用标准A2A通信协议")
    
    async def process_query(self, query: str) -> str:
        """
        处理用户查询，实现核心业务逻辑（StandardA2ATool要求的方法）
        
        Args:
            query: 用户查询
            
        Returns:
            str: 处理结果
        """
        try:
            # 统一处理各种可能的查询格式
            clean_query = self._normalize_query(query)
            logger.info(f"[ZudaoTool] 处理查询: {clean_query}")
            
            # 获取用户位置
            location = await self._get_user_location()
            
            # 优先检测特殊服务关键词
            service_type = detect_service_request(clean_query)
            if service_type:
                logger.info(f"[ZudaoTool] 检测到服务请求: {service_type}")
                result = await self._handle_service_recommend(clean_query, location)
            # 其次检测是否含有"附近"等关键词
            elif any(keyword in clean_query for keyword in ["附近", "周边", "找个", "有什么"]):
                logger.info(f"[ZudaoTool] 检测到附近场所查询")
                result = await self._handle_nearby_query(clean_query, location)
            # 检测是否为时间查询
            elif any(keyword in clean_query for keyword in ["几点", "时间", "现在是", "当前时间"]):
                logger.info(f"[ZudaoTool] 检测到时间查询")
                result = await self._handle_time_query(clean_query, location)
            # 检测是否为天气查询
            elif any(keyword in clean_query for keyword in ["天气", "下雨", "气温", "冷不冷", "热不热"]):
                logger.info(f"[ZudaoTool] 检测到天气查询")
                result = await self._handle_weather_query(clean_query, location)
            # 检测是否为地图相关查询
            elif any(keyword in clean_query for keyword in ["地图", "位置", "在哪", "怎么走"]):
                logger.info(f"[ZudaoTool] 检测到地图查询")
                result = await self._handle_map_query(clean_query, location)
            else:
                # 默认当作通用查询，转发给百炼智能体
                logger.info(f"[ZudaoTool] 无法确定查询类型，转发给百炼智能体")
                result = self._call_bailian(clean_query)
            
            # 注意：不要在这里重复提取店铺和发送通知，
            # 已在每个具体处理方法中处理过了(_handle_nearby_query和_handle_service_recommend)
            
            logger.info(f"[ZudaoTool] 查询完成，返回结果: {result[:100]}..." if len(result) > 100 else f"[ZudaoTool] 查询完成，返回结果: {result}")
            return result
            
        except Exception as e:
            error_msg = f"处理查询出错: {str(e)}"
            logger.error(f"[ZudaoTool] {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            return error_msg
    
    def _normalize_query(self, query: Any) -> str:
        """
        清理和统一查询格式，处理各种可能的输入形式
        
        Args:
            query: 原始查询，可能是字符串、JSON字符串或字典
            
        Returns:
            str: 统一后的查询字符串
        """
        clean_query = query
        try:
            # 处理JSON字符串
            if isinstance(query, str) and query.strip().startswith("{"):
                try:
                    query_data = json.loads(query)
                    if isinstance(query_data, dict) and "query" in query_data:
                        clean_query = query_data["query"]
                except json.JSONDecodeError:
                    pass
            
            # 处理字典对象
            elif isinstance(query, dict) and "query" in query:
                clean_query = query["query"]
            
            # 处理格式如 {"query": "xxx"} 的字符串但不是有效JSON
            elif isinstance(query, str) and "query" in query:
                match = re.search(r'"query"\s*:\s*"([^"]+)"', query)
                if match:
                    clean_query = match.group(1)
            
            # 确保返回的是字符串类型
            if not isinstance(clean_query, str):
                clean_query = str(clean_query)
                    
            logger.info(f"[查询清理] 原始查询: {query}, 清理后: {clean_query}")
            return clean_query
        except Exception as e:
            logger.error(f"[查询清理] 错误: {str(e)}")
            # 出错时返回原始查询
            return query if isinstance(query, str) else str(query)
    
    def _call_bailian(self, query: str) -> str:
        """调用百炼智能体API的简化封装"""
        # 增强提示词，确保返回结构化的店铺信息
        enhanced_query = f"""需要在当前位置附近查找足浴按摩场所。请直接按以下格式列出3家评价较好的店铺：
1. [店铺名称]：[简短描述]
2. [店铺名称]：[简短描述]
3. [店铺名称]：[简短描述]

务必使用上述精确格式，每家店铺必须包含真实店名，不要使用占位符如"店名A"。以下是原始查询：{query}"""
        
        return call_bailian_api(enhanced_query)
    
    async def _get_user_location(self) -> Dict[str, Any]:
        """获取用户位置信息"""
        try:
            # 直接调用get_location_by_ip，不再获取IP
            location = get_location_by_ip()
            if location:
                logger.info(f"[ZudaoTool] 获取用户位置成功: {location['city']}")
                return location
        except Exception as e:
            logger.error(f"[ZudaoTool] 获取位置出错: {str(e)}")
        
        # 无法获取真实位置时返回默认位置
        logger.warning("[ZudaoTool] 无法获取用户位置，返回默认位置")
        return DEFAULT_LOCATION
    
    async def _handle_time_query(self, query: str, location: Dict[str, Any]) -> str:
        """处理时间查询"""
        timezone = extract_timezone(query)
        time_obj = get_current_time(timezone)
        result = format_time_result(time_obj, timezone)
        
        # 添加位置信息
        location_str = format_location_string(location)
        result = f"{location_str}{result}"
        
        return result
    
    async def _handle_weather_query(self, query: str, location: Dict[str, Any]) -> str:
        """处理天气查询"""
        # 提取查询的位置，如果没有则使用用户当前位置
        location_str = format_location_string(location)
        
        # 使用百炼智能体
        weather_query = f"查询{location_str}的天气，包括气温、天气状况、空气质量等，只返回简洁的天气信息，不超过50字"
        weather_info = call_bailian_api(weather_query)
        
        # 如果返回结果太长，进行截断
        if len(weather_info) > 200:
            weather_info = weather_info[:200] + "..."
            
        return weather_info
    
    async def _handle_map_query(self, query: str, location: Dict[str, Any]) -> str:
        """处理地图查询"""
        src_location_str = format_location_string(location)
        
        # 提取目的地信息
        dest_city = extract_city_from_query(query)
        dst_location_str = dest_city if dest_city else "目的地"
        
        # 使用百炼智能体
        map_query = f"我在{src_location_str}，想去{dst_location_str}，请告诉我简单的路线和距离。"
        route_info = call_bailian_api(map_query)
        
        # 如果返回结果太长，进行截断
        if len(route_info) > 200:
            route_info = route_info[:200] + "..."
            
        return route_info
    
    async def _handle_nearby_query(self, query: str, location: Dict[str, Any]) -> str:
        """处理附近位置查询"""
        location_str = format_location_string(location)
        
        # 检查是否包含敏感词或特殊需求暗示
        sensitive_keywords = ["技师", "特殊", "小姐", "上门", "服务好", "莞式", "包夜"]
        has_sensitive = any(keyword in query for keyword in sensitive_keywords)
        
        if has_sensitive:
            logger.info(f"[ZudaoTool] 检测到敏感词，可能需要特殊服务: {query}")
            # 构建特殊查询，但不明确表明是特殊服务
            special_query = f"""我在{location_str}附近，想找一些特别的地方，{query}，
请详细推荐2-3个合适的场所，按以下格式列出:

1. [店铺真实名称]：[地址]，[特色和简单描述]
2. [店铺真实名称]：[地址]，[特色和简单描述]
3. [店铺真实名称]：[地址]，[特色和简单描述]

每个店铺必须有真实名称，不要使用占位符。"""
        else:
            # 构建标准的附近查询
            nearby_query = f"""我在{location_str}附近，{query}
请给出2-3个推荐，按以下格式列出:

1. [店铺真实名称]：[地址]，[特色和简单描述]
2. [店铺真实名称]：[地址]，[特色和简单描述]
3. [店铺真实名称]：[地址]，[特色和简单描述]

请尽量详细说明每个地方的特点、评价和地址。必须使用真实店铺名称，不要使用占位符。"""
            
            # 使用增强格式的查询
            special_query = nearby_query
        
        logger.info(f"[ZudaoTool] 开始查询附近场所: {special_query}")
        
        # 调用百炼智能体
        result = call_bailian_api(special_query)
        logger.info(f"[ZudaoTool] 附近场所查询成功，总字符数: {len(result)}")
        
        # 从结果中提取店铺信息
        stores = self._extract_stores_from_result(result)
        
        # 如果有店铺信息，通知搜索工具
        if stores:
            logger.info(f"[ZudaoTool] 从附近查询结果中提取到 {len(stores)} 家店铺: {', '.join([s.get('name', '') for s in stores])}")
            self._notify_store_found(stores)
        else:
            logger.info(f"[ZudaoTool] 未从附近查询结果中提取到店铺信息")
        
        return result
    
    async def _handle_service_recommend(self, query: str, location: Dict[str, Any]) -> str:
        """处理特殊服务推荐"""
        # 检测服务类型
        service_type = detect_service_request(query)
        if not service_type:
            return "无法识别的服务请求，请提供更多信息"
        
        # 获取服务信息
        service_info = SERVICE_MAPPING.get(service_type, {})
        real_intent = service_info.get("real_intent", service_type)
        
        # 构建高级查询
        location_str = format_location_string(location)
        template = service_info.get("pro_query_template", "查询{location_str}附近的{service_type}服务")
        advanced_query = template.format(
            location_str=location_str,
            lat=location.get("lat", 0),
            lon=location.get("lon", 0),
            service_type=service_type,
            real_intent=real_intent
        )
        
        # 增强查询提示，确保返回具体店铺名称
        enhanced_query = f"""{advanced_query}

请按以下格式返回信息:
1. [实际店铺名称]：[简短描述和地址]
2. [实际店铺名称]：[简短描述和地址]
3. [实际店铺名称]：[简短描述和地址]

务必提供真实店铺名称，不要使用占位符。每家店铺信息单独一行，使用数字编号。"""
        
        logger.info(f"[ZudaoTool] 开始调用百炼智能体，查询: {enhanced_query[:100]}...")
        
        # 调用百炼智能体
        result = call_bailian_api(enhanced_query)
        logger.info(f"[ZudaoTool] 调用成功，总长度: {len(result)}")
        
        # 提取店铺信息
        stores = self._extract_stores_from_result(result)
        if stores:
            logger.info(f"[ZudaoTool] 从服务推荐结果中提取到 {len(stores)} 家店铺")
            self._notify_store_found(stores)
        
        return result
    
    def get_capabilities(self) -> List[str]:
        """获取工具能力列表"""
        return [
            "地理定位服务",
            "场所查询与推荐",
            "多源数据交叉验证",
            "个性化服务匹配",
            "路线规划与导航",
            "时间查询",
            "天气查询",
            "附近场所分析"
        ]
    
    def get_examples(self) -> List[str]:
        """获取工具示例列表"""
        return [
            "查找周边休闲场所",
            "分析附近商务服务评价",
            "获取特色服务场所路线",
            "搜集区域服务行业分布",
            "现在几点了？",
            "今天天气怎么样？",
            "附近有什么好吃的？"
        ]

    def _notify_store_found(self, stores):
        """当找到店铺时通知其他工具 - 使用标准A2A协议"""
        if not stores:
            return False
        
        try:
            # 使用标准A2A接口发送店铺信息 - 强制使用单例模式
            from SmartSisi.llm.agent.a2a_notification import send_task, check_subscriptions, get_tool_manager
            
            # 强制确保使用相同的工具管理器实例
            manager = get_tool_manager()
            if not manager._running:
                logger.warning("[ZudaoTool] 工具管理器未运行，尝试启动...")
                manager.start()
                time.sleep(0.5)  # 给一点时间启动
            
            # 排除测试店铺
            real_stores = [store for store in stores if not store.get("test", False)]
            if not real_stores:
                logger.warning("[ZudaoTool] 没有找到真实店铺，不发送通知")
                return False
                
            # 记录发现的店铺
            store_names = [store.get("name", "未知店铺") for store in real_stores]
            logger.info(f"[ZudaoTool] 发现了 {len(real_stores)} 家真实店铺: {', '.join(store_names)}")
            
            # 检查订阅状态，看看百炼工具是否已准备好接收
            subs_info = check_subscriptions()
            bailian_ready = False
            for sub_info in subs_info.get("details", {}).get("bai_lian", []):
                if sub_info.get("method") == "event.store_info":
                    bailian_ready = True
                    logger.info(f"[ZudaoTool] 百炼工具已订阅，订阅ID: {sub_info.get('id')}")
                    break
            
            # 检查百炼工具是否存在于已注册工具列表中
            tools_registered = subs_info.get("tools_registered", [])
            if "bai_lian" not in tools_registered:
                logger.warning("[ZudaoTool] 百炼工具尚未注册到A2A管理器")
            
            # 如果百炼工具未就绪，先尝试主动初始化它
            if not bailian_ready:
                logger.warning("[ZudaoTool] 百炼工具尚未订阅event.store_info，尝试主动初始化...")
                try:
                    # 尝试导入并初始化百炼工具 - 使用绝对导入避免包上下文问题
                    import sys
                    import os

                    # 添加工具目录到路径
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    if current_dir not in sys.path:
                        sys.path.insert(0, current_dir)

                    # 使用绝对导入
                    import bai_lian_tool
                    get_tool_instance = bai_lian_tool.get_tool_instance
                    auto_resubscribe = bai_lian_tool.auto_resubscribe
                    # 获取百炼工具实例
                    bailian = get_tool_instance()
                    # 请求重新订阅
                    auto_resubscribe()
                    # 等待订阅建立
                    logger.info("[ZudaoTool] 已请求百炼工具重新订阅，等待2秒...")
                    time.sleep(2)
                    # 再次检查订阅状态
                    subs_info = check_subscriptions()
                    for sub_info in subs_info.get("details", {}).get("bai_lian", []):
                        if sub_info.get("method") == "event.store_info":
                            bailian_ready = True
                            logger.info(f"[ZudaoTool] 百炼工具已成功订阅，订阅ID: {sub_info.get('id')}")
                            break
                except Exception as e:
                    logger.error(f"[ZudaoTool] 尝试初始化百炼工具失败: {str(e)}")
            
            # 记录最终订阅状态
            if not bailian_ready:
                logger.warning("[ZudaoTool] 百炼工具仍未订阅，消息将进入队列等待处理")
            
            # 添加任务ID，用于防止重复处理
            task_unique_id = f"store_task_{int(time.time())}"
            
            # 构建店铺信息包 - 添加消息重要性标记
            params = {
                "stores": real_stores,
                "timestamp": time.time(),
                "location": _location_cache,  # 传递位置信息
                "priority": "high",           # 标记为高优先级
                "task_unique_id": task_unique_id  # 用于去重
            }
            
            # 只通知百炼工具
            target_tool = "bai_lian"
            
            # 添加更多日志以跟踪进度
            logger.info(f"[ZudaoTool] 开始向{target_tool}发送店铺信息, 唯一ID: {task_unique_id}")
            
            # 使用标准A2A协议发送任务
            task_id = send_task(
                source_tool="zudao",  # 修正为与初始化一致的名称
                target_tool=target_tool,
                method="event.store_info",  # 标准化事件命名
                params=params
            )
            
            if task_id:
                logger.info(f"[ZudaoTool] 成功发送店铺信息到 {target_tool}, 任务ID: {task_id}")
                return True
            else:
                logger.error(f"[ZudaoTool] 向 {target_tool} 发送店铺信息失败")
                return False
                
        except Exception as e:
            logger.error(f"[ZudaoTool] 通知店铺信息时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _extract_stores_from_result(self, result_text):
        """从搜索结果文本中提取店铺信息 - 简化版"""
        stores = []
        if not result_text:
            return stores
            
        try:
            # 1. 提取Markdown加粗的店铺名称 (如 **水漫足浴**)
            bold_pattern = r'\*\*([^*\n]{2,30}?)\*\*'
            bold_matches = re.finditer(bold_pattern, result_text)
            for match in bold_matches:
                store_name = match.group(1).strip()
                # 避免提取非店铺名的加粗文本
                if store_name and len(store_name) < 30 and "地图" not in store_name and "查询" not in store_name:
                    if not any(store.get("name") == store_name for store in stores):
                        stores.append({"name": store_name})
            
            # 2. 如果没有找到加粗格式，尝试提取数字编号的列表项 (如 1. 水漫足浴)
            if not stores:
                list_pattern = r'(?:^|\n)\s*(\d+)[\.、:：]\s*([^。\n,，:：]{2,25})'
                list_matches = re.finditer(list_pattern, result_text)
                for match in list_matches:
                    store_name = match.group(2).strip()
                    # 移除可能带有的额外符号
                    store_name = re.sub(r'[\*\(\)\[\]\{\}]', '', store_name)
                    # 避免提取过长的文本行
                    if store_name and 2 <= len(store_name) <= 25 and "地图" not in store_name and "查询" not in store_name:
                        if not any(store.get("name") == store_name for store in stores):
                            stores.append({"name": store_name})
            
            # 限制最多提取3家店铺
            stores = stores[:3]
            
            logger.info(f"从结果中提取到 {len(stores)} 家店铺: {', '.join([s.get('name', '') for s in stores])}")
            return stores
            
        except Exception as e:
            logger.error(f"提取店铺信息时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        return stores

# 创建工具实例的函数
def create_tool():
    """创建工具实例"""
    return ZudaoTool()

# 与LangGraph集成处理的函数
def process_with_langgraph(query: str, state: Dict[str, Any] = None) -> Dict[str, Any]:
    """与LangGraph集成处理"""
    state = state or {}
    tool = ZudaoTool()
    
    # 使用线程隔离方式修复事件循环冲突
    import threading
    import asyncio
    
    result_container = []
    
    def run_in_thread():
        # 在新线程中创建和使用事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(tool.ainvoke(query))
            result_container.append(result)
        finally:
            loop.close()
    
    # 启动线程并等待完成
    t = threading.Thread(target=run_in_thread)
    t.start()
    t.join()
    
    # 处理结果
    result = result_container[0] if result_container else "处理失败"
    
    return {
        "response": result,
        "state": state
    }

# 添加模块级invoke函数供A2A服务器调用
def invoke(params):
    """
    模块级invoke函数，供A2A服务器直接调用
    
    Args:
        params: 调用参数，可以是字符串或字典
        
    Returns:
        Dict: 工具执行结果
    """
    logger.info(f"[zudao] 模块级invoke调用，参数: {params}")
    
    # 提取查询文本
    query = None
    if isinstance(params, dict):
        # 如果是JSON-RPC格式
        if "jsonrpc" in params and "method" in params and "params" in params:
            inner_params = params.get("params", {})
            query = inner_params.get("query", "")
        else:
            # 尝试获取查询参数
            query = params.get("query", str(params))
    else:
        # 如果是字符串或其他类型，直接作为查询
        query = str(params)
    
    if not query:
        query = "当前位置附近服务" # 默认查询
    
    try:
        # 创建工具实例
        tool = ZudaoTool()
        
        # 使用线程和事件循环处理异步调用
        import threading
        result_container = []
        
        def run_in_thread():
            # 在新线程中创建和使用事件循环
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(tool.process_query(query))
                result_container.append(result)
            finally:
                loop.close()
        
        # 启动线程并等待完成
        t = threading.Thread(target=run_in_thread)
        t.start()
        t.join(timeout=15) # 设置15秒超时
        
        # 处理结果
        if result_container:
            result_text = result_container[0]
        else:
            result_text = "处理超时或失败"
        
        return {
            "service_info": {
                "query": query,
                "result": result_text,
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.error(f"[zudao] 处理查询出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            "service_info": {
                "query": query,
                "error": f"服务查询失败: {str(e)}",
                "timestamp": time.time()
            }
        } 