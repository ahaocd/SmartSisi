"""
百炼工具 - 提供与百炼API交互的基本功能 (标准A2A实现)
增强社交媒体搜索能力，包括抖音、小红书、YouTube等平台内容
支持与zudao工具协作，针对店铺和技师进行更精准搜索
"""

import os
import json
import time
import logging
import asyncio
import re
import random
from typing import Dict, Any, List, Optional, Union, Generator, Tuple
from http import HTTPStatus

# 导入标准A2A工具基类 - 修改为绝对导入
from SmartSisi.llm.a2a.base_a2a_tool import StandardA2ATool

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("BaiLianTool")

# 导入DashScope SDK
try:
    from dashscope import Application
    import dashscope
    DASHSCOPE_AVAILABLE = True
    logger.info("DashScope SDK已加载")
except ImportError:
    DASHSCOPE_AVAILABLE = False
    logger.warning("DashScope SDK未找到，请安装：pip install dashscope")

class BaiLianTool(StandardA2ATool):
    """百炼API工具 - 标准A2A实现，优先搜索社交媒体内容"""

    # 默认API密钥和应用ID
    DEFAULT_API_KEY = "sk-cda8f8d44c3042da82ee9700f388e9b4"
    DEFAULT_APP_ID = "3355af3f65fd4323b617b80f59c349b5"

    # 社交媒体平台关键词 - 专注抖音快手等实时平台
    SOCIAL_PLATFORMS = [
        "抖音", "快手", "微博", "短视频", "社交媒体", "直播平台"
    ]

    # 足浴技师相关关键词
    MASSAGE_TECHNICIAN_KEYWORDS = [
        "技师", "小妹", "服务", "特色", "颜值", "体验",
        "手法", "按摩", "88号", "专业", "态度", "介绍"
    ]

    # 补充查询和验证查询意图关键词
    COMPLEMENTARY_INTENT_KEYWORDS = ["更多", "详情", "评价", "真实", "具体"]
    VERIFICATION_INTENT_KEYWORDS = ["靠谱吗", "怎么样", "好不好", "如何", "真的吗", "值得"]

    def __init__(self, api_key: Optional[str] = None, app_id: Optional[str] = None):
        """
        初始化百炼工具

        参数:
            api_key: 百炼API密钥，默认从环境变量获取
            app_id: 百炼应用ID
        """
        # 调用父类初始化方法
        super().__init__(
            name="bai_lian",
            description="百炼搜索工具，提供智能搜索和信息查询服务，优先搜索社交媒体内容，支持对特定店铺和服务进行深入分析",
            version="1.0.0"
        )

        # 获取API密钥
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or self.DEFAULT_API_KEY

        # 设置应用ID
        self.app_id = app_id or os.getenv("DASHSCOPE_APP_ID") or self.DEFAULT_APP_ID

        # 设置环境变量，以便DashScope SDK使用
        os.environ["DASHSCOPE_API_KEY"] = self.api_key

        # 直接设置DashScope SDK的API密钥
        if DASHSCOPE_AVAILABLE:
            dashscope.api_key = self.api_key
            logger.info(f"已直接设置DashScope SDK的API密钥")

        # 检查SDK是否可用
        if not DASHSCOPE_AVAILABLE:
            logger.warning("DashScope SDK不可用，部分功能将受限")

        # 统计信息
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0,
            "start_time": time.time()
        }

        # 订阅状态跟踪
        self.subscription_id = None
        self.last_subscription_time = 0

        # 添加24小时缓存机制
        self.search_cache = {}  # 格式: {store_name: {"result": "...", "timestamp": time.time()}}
        self.cache_duration = 24 * 60 * 60  # 24小时缓存

        # 初始化transit_station
        try:
            from llm.transit_station import get_transit_station
            self.transit_station = get_transit_station()
            logger.info(f"百炼工具已初始化transit_station")
        except Exception as e:
            logger.warning(f"百炼工具初始化transit_station失败: {str(e)}")
            self.transit_station = None

        logger.info(f"百炼工具初始化完成，应用ID: {self.app_id}")

        # 不在初始化时立即订阅，避免重复订阅
        # 改为在首次需要时延迟订阅

    def _is_cache_valid(self, store_name: str) -> bool:
        """检查缓存是否有效（24小时内）"""
        if store_name not in self.search_cache:
            return False

        cache_time = self.search_cache[store_name].get("timestamp", 0)
        current_time = time.time()

        return (current_time - cache_time) < self.cache_duration

    def _get_cached_result(self, store_name: str) -> Optional[str]:
        """获取缓存的搜索结果"""
        if self._is_cache_valid(store_name):
            return self.search_cache[store_name].get("result")
        return None

    def _cache_result(self, store_name: str, result: str):
        """缓存搜索结果"""
        self.search_cache[store_name] = {
            "result": result,
            "timestamp": time.time()
        }
        logger.info(f"[缓存] 已缓存店铺 {store_name} 的搜索结果")

    def set_app_id(self, app_id: str) -> None:
        """
        设置应用ID

        参数:
            app_id: 百炼应用ID
        """
        self.app_id = app_id
        logger.info(f"应用ID已设置为: {app_id}")

    async def process_query(self, query: str) -> str:
        """
        实现标准A2A基类的process_query方法

        参数:
            query: 用户查询

        返回:
            str: 搜索结果文本
        """
        try:
            # 从查询中提取上下文
            text_query, context = self._parse_query_argument(query)

            # 生成随机会话ID
            session_id = f"session_{int(time.time())}"

            # 调用搜索方法
            result = await self._async_search(text_query, session_id=session_id, has_thoughts=True, context=context)

            # 检查是否有错误
            if "error" in result:
                error_msg = f"搜索失败: {result['error'].get('message', '未知错误')}"
                logger.error(f"[A2A调用] {error_msg}")
                return error_msg

            # 提取结果文本
            if "output" in result and "text" in result["output"]:
                response_text = result["output"]["text"]
                logger.info(f"[A2A调用] 返回结果: {response_text[:50]}..." if len(response_text) > 50 else f"[A2A调用] 返回结果: {response_text}")
                return response_text
            else:
                # 尝试将整个结果转为字符串返回
                logger.warning("[A2A调用] 无法提取文本结果，返回整个结果")
                return f"搜索结果: {json.dumps(result, ensure_ascii=False)}"

        except Exception as e:
            error_msg = f"处理搜索请求时出错: {str(e)}"
            logger.error(f"[A2A调用] {error_msg}")
            return error_msg

    async def _async_search(self, query: str, session_id: Optional[str] = None,
                    memory_id: Optional[str] = None, has_thoughts: bool = True,
                    rag_options: Optional[Dict[str, Any]] = None,
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行异步搜索 - 内部方法

        参数:
            query: 搜索查询
            session_id: 会话ID
            memory_id: 长期记忆ID
            has_thoughts: 是否包含思考过程
            rag_options: 检索选项
            context: 上下文

        返回:
            Dict: 搜索结果
        """
        # 增加详细日志，特别是对于店铺搜索
        if context and "zudao_result" in context:
            logger.info(f"[店铺搜索] 开始为店铺搜索评价: {query}, 上下文包含zudao结果")

        self.stats["total_requests"] += 1

        if not DASHSCOPE_AVAILABLE:
            error_msg = "DashScope SDK不可用，无法执行搜索"
            logger.error(error_msg)
            return {
                "error": {
                    "code": "SDK_NOT_AVAILABLE",
                    "message": error_msg
                }
            }

        try:
            # 增强查询以优先搜索社交媒体内容，考虑上下文
            enhanced_query = self._enhance_for_social_media(query, context)

            # 构建参数 - 修改为与zudao.py中一致的格式
            kwargs = {
                "api_key": self.api_key,
                "app_id": self.app_id,
                "prompt": enhanced_query,
                "parameters": {"has_thoughts": has_thoughts}
            }

            # 添加会话ID
            if session_id:
                kwargs["session_id"] = session_id

            # 添加长期记忆ID
            if memory_id:
                kwargs["memory_id"] = memory_id

            # 添加检索知识库选项
            if rag_options:
                if "parameters" not in kwargs:
                    kwargs["parameters"] = {}
                kwargs["parameters"]["rag_options"] = rag_options

            logger.info(f"执行搜索: '{enhanced_query}', 会话ID: {session_id or '无'}")

            # 使用SDK调用
            response = Application.call(**kwargs)

            # 检查响应
            if response.status_code == HTTPStatus.OK:
                self.stats["successful_requests"] += 1

                # 处理响应结果
                result = self._process_response(response)

                # 更新token统计
                if hasattr(response, 'usage') and hasattr(response.usage, 'models'):
                    for model in response.usage.models:
                        input_tokens = getattr(model, 'input_tokens', 0)
                        output_tokens = getattr(model, 'output_tokens', 0)
                        self.stats["total_tokens"] += (input_tokens + output_tokens)

                # 完成搜索后添加日志
                if "output" in result and "text" in result["output"]:
                    if context and "zudao_result" in context:
                        logger.info(f"[店铺搜索完成] 为店铺搜索评价完成: {query[:30]}..., 结果长度:{len(result['output']['text'])}")

                return result
            else:
                self.stats["failed_requests"] += 1
                error_msg = f"搜索请求失败: 状态码={response.status_code}, 消息={response.message if hasattr(response, 'message') else '未知错误'}"
                logger.error(error_msg)
                return {
                    "error": {
                        "code": response.status_code,
                        "message": response.message if hasattr(response, 'message') else "未知错误"
                    }
                }
        except Exception as e:
            self.stats["failed_requests"] += 1
            error_msg = f"搜索请求异常: {str(e)}"
            logger.error(error_msg)
            return {
                "error": {
                    "code": 500,
                    "message": error_msg
                }
            }

    def _parse_query_argument(self, query: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        解析查询参数，提取查询文本和上下文

        参数:
            query: 查询参数，可能是字符串、字典或包含JSON的字符串

        返回:
            (查询文本, 上下文字典)
        """
        text_query = ""
        context = None

        try:
            # 处理字典类型查询
            if isinstance(query, dict):
                # 提取查询文本
                if "query" in query:
                    text_query = query["query"]
                elif "text" in query:
                    text_query = query["text"]
                else:
                    # 如果找不到查询文本，转为字符串
                    text_query = str(query)

                # 提取上下文信息
                context = {}
                if "context" in query:
                    context = query["context"]
                if "zudao_result" in query:
                    context["zudao_result"] = query["zudao_result"]

            # 处理可能是JSON字符串的查询
            elif isinstance(query, str):
                # 尝试解析为JSON
                if query.strip().startswith("{"):
                    try:
                        query_data = json.loads(query)
                        return self._parse_query_argument(query_data)  # 递归处理解析后的字典
                    except json.JSONDecodeError:
                        # 解析失败，将整个字符串视为查询
                        text_query = query
                else:
                    # 不是JSON格式，将整个字符串视为查询
                    text_query = query
            else:
                # 其他类型，转为字符串作为查询
                text_query = str(query)

        except Exception as e:
            logger.error(f"解析查询参数时出错: {str(e)}")
            text_query = str(query)  # 失败时回退到字符串转换

        # 确保查询文本不为空
        if not text_query or text_query.strip() == "":
            text_query = "百度一下" # 默认查询

        return text_query, context

    # 保留原有的API状态获取功能
    def get_api_status(self) -> Dict[str, Any]:
        """
        获取API状态

        返回:
            API状态信息
        """
        return {
            "api_key_set": bool(self.api_key),
            "app_id_set": bool(self.app_id),
            "dashscope_available": DASHSCOPE_AVAILABLE,
            "stats": {
                "total_requests": self.stats["total_requests"],
                "successful_requests": self.stats["successful_requests"],
                "failed_requests": self.stats["failed_requests"],
                "total_tokens": self.stats["total_tokens"],
                "uptime_seconds": int(time.time() - self.stats["start_time"])
            }
        }

    # 保留原有的功能，只是不再对外暴露
    def _extract_topic_interests(self, query: str) -> List[str]:
        """
        从查询中提取主题兴趣

        参数:
            query: 用户查询

        返回:
            主题兴趣列表
        """
        # 产品类主题识别
        product_categories = ["手机", "电脑", "相机", "平板", "耳机", "手表", "家电",
                             "护肤", "彩妆", "服装", "鞋子", "包包", "食品", "饮料"]

        # 服务类主题识别
        service_categories = ["酒店", "餐厅", "按摩", "足浴", "美发", "美甲", "健身",
                             "旅游", "学习", "医疗", "培训"]

        # 识别出现在查询中的主题
        interests = []
        for category in product_categories + service_categories:
            if category in query:
                interests.append(category)

        return interests

    def _detect_intent_type(self, query: str) -> str:
        """
        检测查询意图类型

        参数:
            query: 用户查询

        返回:
            意图类型: "complementary"(补充), "verification"(验证) 或 "general"(一般)
        """
        if any(keyword in query for keyword in self.COMPLEMENTARY_INTENT_KEYWORDS):
            return "complementary"

        if any(keyword in query for keyword in self.VERIFICATION_INTENT_KEYWORDS):
            return "verification"

        return "general"

    def _extract_stores_from_zudao(self, zudao_result: str) -> List[Dict[str, Any]]:
        """
        从zudao工具返回的结果中提取店铺信息

        参数:
            zudao_result: zudao工具返回的数据，可以是字符串或店铺列表

        返回:
            店铺信息列表
        """
        stores = []

        # 检查输入
        if not zudao_result:
            logger.warning("_extract_stores_from_zudao: 输入为空")
            return stores

        try:
            # 1. 如果输入已经是字典列表，直接使用
            if isinstance(zudao_result, list):
                logger.info("输入已经是列表，直接提取店铺信息")
                for item in zudao_result:
                    if isinstance(item, dict) and "name" in item:
                        stores.append(item)
                return stores

            # 2. 如果是字符串，可能需要解析JSON
            if isinstance(zudao_result, str):
                try:
                    # 尝试解析JSON
                    parsed_data = json.loads(zudao_result)

                    # 如果是列表，尝试提取店铺信息
                    if isinstance(parsed_data, list):
                        for item in parsed_data:
                            if isinstance(item, dict) and "name" in item:
                                stores.append(item)
                        if stores:
                            return stores
                except json.JSONDecodeError:
                    # 不是有效的JSON，使用文本解析
                    pass
                except Exception as e:
                    logger.error(f"解析JSON时出错: {str(e)}")

                # 3. 使用文本模式正则提取
                # 尝试使用常见店铺列表格式提取
                # 例如 "1. 店名A", "2. 店名B" 或 "### 1. 店名A"
                store_pattern = r'(?:^|\n)(?:#{1,3}\s*)?(\d+)\.\s+([^\n]+)'
                matches = re.finditer(store_pattern, zudao_result)

                for match in matches:
                    store_number = match.group(1)
                    store_name = match.group(2).strip()

                    # 创建店铺信息
                    store_info = {"name": store_name}
                    stores.append(store_info)

            logger.info(f"从zudao结果中提取到 {len(stores)} 个店铺信息")

        except Exception as e:
            logger.error(f"提取店铺信息时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

        return stores

    def _build_enhanced_query(self, query: str, stores: List[Dict[str, Any]], intent_type: str) -> str:
        """
        基于店铺信息和意图构建增强查询

        参数:
            query: 原始查询
            stores: 从zudao结果提取的店铺信息
            intent_type: 查询意图类型

        返回:
            增强后的查询
        """
        if not stores:
            return query

        # 取前两家店铺构建查询
        target_stores = stores[:2]
        store_names = [store["name"] for store in target_stores if "name" in store]

        if not store_names:
            return query

        # 根据意图类型构建不同的查询
        if intent_type == "verification":
            # 验证类查询，关注真实性和评价
            store_str = '和'.join(store_names)
            return f"实时搜索全网关于{store_str}的技师 美女 小妹 模特 演员，重点查找抖音快手等短视频平台半年内的真实评价和用户体验"

        elif intent_type == "complementary":
            # 补充类查询，寻找更多详情
            store_str = '或'.join(store_names)
            return f"实时搜索全网关于{store_str}的技师 美女 小妹 模特 演员详细信息，重点关注抖音快手等平台半年内的服务特色、颜值评价和用户实际体验"

        else:
            # 一般查询，获取综合信息
            store_str = '和'.join(store_names)
            return f"实时搜索全网关于{store_str}的技师 美女 小妹 模特 演员，查询抖音快手等平台半年内的服务项目、颜值介绍和用户真实体验"

    def _enhance_for_social_media(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        增强查询以优先搜索社交媒体内容，如果是从zudao过来的查询会添加额外信息

        Args:
            query: 原始查询
            context: 上下文信息，可能包含zudao_result或简化的store_name
        """
        # 记录原始查询
        original_query = query
        enhanced_query = query

        # 检查上下文 - 支持新的简化版context格式
        store_context = False
        if context:
            if "zudao_result" in context and context["zudao_result"]:
                store_context = True
            elif "store_name" in context and context["store_name"]:
                store_context = True

        # 如果查询来自于商店评价
        if store_context:
            # 确保包含社交媒体和评价关键词
            # 先检查是否已经包含了评价关键词
            has_review_term = any(term in query.lower() for term in ["评价", "怎么样", "好不好", "体验"])

            if not has_review_term:
                enhanced_query = f"{query} 真实评价"

            # 添加社交媒体平台关键词，优先搜索社交媒体内容
            platforms = random.sample(self.SOCIAL_PLATFORMS, min(2, len(self.SOCIAL_PLATFORMS)))
            if not any(platform in enhanced_query for platform in self.SOCIAL_PLATFORMS):
                enhanced_query = f"{enhanced_query} {platforms[0]}"

        # 1. 首先检查是否有上下文，并且上下文中包含zudao结果
        if context and "zudao_result" in context:
            zudao_result = context["zudao_result"]

            # 调试输出
            logger.info(f"[增强查询] 接收到zudao结果类型: {type(zudao_result)}")

            # 提取店铺信息
            stores = self._extract_stores_from_zudao(zudao_result)

            # 打印提取结果
            if stores:
                logger.info(f"[增强查询] 成功提取{len(stores)}家店铺: {[s.get('name', '未知') for s in stores]}")
            else:
                logger.info("[增强查询] 未从上下文提取到店铺信息")

            # 如果找到店铺信息，基于店铺构建增强查询
            if stores:
                # 识别查询意图类型
                intent_type = self._detect_intent_type(query)

                # 构建增强查询
                enhanced_query = self._build_enhanced_query(query, stores, intent_type)

                logger.info(f"基于zudao上下文增强查询: '{query}' -> '{enhanced_query}'")
                return enhanced_query

        # 2. 检查查询是否已经包含社交媒体关键词
        has_social_keyword = any(platform in query for platform in self.SOCIAL_PLATFORMS)

        # 如果已包含社交媒体关键词，无需增强
        if has_social_keyword:
            return query

        # 3. 检查是否包含足浴技师相关关键词
        has_technician_keyword = any(keyword in query for keyword in self.MASSAGE_TECHNICIAN_KEYWORDS)
        if has_technician_keyword:
            social_platforms = "抖音快手等短视频平台"
            tech_enhanced_query = f"实时搜索全网关于{query}的技师 美女 小妹 模特 演员，重点查找{social_platforms}半年内的真实用户评价和体验"
            logger.info(f"技师服务查询增强: '{query}' -> '{tech_enhanced_query}'")
            return tech_enhanced_query

        # 4. 分析查询意图，判断是否适合社交媒体搜索
        info_seeking_keywords = ["怎么样", "如何", "教程", "推荐", "评价", "体验", "效果", "分享", "心得"]
        trend_keywords = ["流行", "热门", "趋势", "最近", "最新", "潮流", "网红"]

        is_info_seeking = any(keyword in query for keyword in info_seeking_keywords)
        is_trend_related = any(keyword in query for keyword in trend_keywords)

        # 如果是信息查询或趋势相关查询，增强为社交媒体搜索
        if is_info_seeking or is_trend_related:
            social_platforms = "抖音快手等短视频平台"
            enhanced_query = f"实时搜索{query}在{social_platforms}半年内的相关内容"
            logger.info(f"查询增强: '{query}' -> '{enhanced_query}'")
            return enhanced_query

        # 5. 提取主题兴趣，尝试构建更精确的查询
        interests = self._extract_topic_interests(query)
        if interests:
            topic_str = '、'.join(interests)
            social_platforms = "抖音快手等短视频平台"
            topic_enhanced_query = f"实时搜索{query}关于{topic_str}在{social_platforms}半年内的相关内容"
            logger.info(f"主题兴趣查询增强: '{query}' -> '{topic_enhanced_query}'")
            return topic_enhanced_query

        return query

    def _process_response(self, response) -> Dict[str, Any]:
        """
        处理API响应

        参数:
            response: API响应对象

        返回:
            处理后的结果
        """
        # 从对象转为字典
        result = {
            "output": {},
            "request_id": response.request_id if hasattr(response, 'request_id') else None
        }

        # 处理输出
        if hasattr(response, 'output'):
            if hasattr(response.output, 'text'):
                result["output"]["text"] = response.output.text
            if hasattr(response.output, 'thoughts'):
                result["output"]["thoughts"] = response.output.thoughts
            if hasattr(response.output, 'doc_references'):
                result["output"]["doc_references"] = response.output.doc_references
            if hasattr(response.output, 'finish_reason'):
                result["output"]["finish_reason"] = response.output.finish_reason
            if hasattr(response.output, 'session_id'):
                result["output"]["session_id"] = response.output.session_id

        # 处理使用信息
        if hasattr(response, 'usage'):
            result["usage"] = {}
            if hasattr(response.usage, 'models'):
                result["usage"]["models"] = []
                for model in response.usage.models:
                    model_info = {}
                    if hasattr(model, 'model_id'):
                        model_info["model_id"] = model.model_id
                    if hasattr(model, 'input_tokens'):
                        model_info["input_tokens"] = model.input_tokens
                    if hasattr(model, 'output_tokens'):
                        model_info["output_tokens"] = model.output_tokens
                    result["usage"]["models"].append(model_info)

        return result

    # 实现A2A标准能力方法
    def get_capabilities(self) -> List[str]:
        """获取工具能力列表

        Returns:
            List[str]: 能力列表
        """
        return [
            "智能搜索",
            "社交媒体内容优先",
            "店铺和服务分析",
            "用户评价提取",
            "上下文增强搜索"
        ]

    def get_examples(self) -> List[str]:
        """获取工具示例列表

        Returns:
            List[str]: 示例列表
        """
        return [
            "iPhone 15最新评价",
            "北京最好的火锅店推荐", 
            "抖音上最火的减肥产品",
            "快手热门美妆达人推荐",
            "实时搜索技师服务评价"
        ]

    def _subscribe_to_zudao_events(self):
        """订阅足道工具事件 - 使用标准A2A协议"""
        # 防止重复订阅 - 如果最近10秒内已订阅过，跳过
        current_time = time.time()
        if self.subscription_id and (current_time - self.last_subscription_time) < 10:
            logger.info(f"[BaiLianTool] 跳过重复订阅，最近订阅ID: {self.subscription_id}")
            return self.subscription_id

        # 在订阅前先检查是否已存在有效订阅
        try:
            from SmartSisi.llm.agent.a2a_notification import check_subscriptions
            subs = check_subscriptions()

            # 检查百炼工具是否已订阅store_info事件
            for sub_info in subs.get("details", {}).get("bai_lian", []):
                if sub_info.get("method") == "event.store_info":
                    self.subscription_id = sub_info.get("id")
                    self.last_subscription_time = current_time
                    logger.info(f"[BaiLianTool] 检测到已有store_info订阅，使用现有ID: {self.subscription_id}")
                    return self.subscription_id
        except Exception as e:
            logger.warning(f"[BaiLianTool] 检查订阅状态时出错: {str(e)}")

        # 尝试订阅
        try:
            # 引入必要的依赖
            from SmartSisi.llm.agent.a2a_notification import subscribe

            # 定义要订阅的事件列表
            events = ["event.store_info"]  # 目前只订阅店铺信息

            # 记录日志
            logger.info(f"[BaiLianTool] 开始订阅事件: {events}")

            # 创建有效的回调函数
            async def store_info_callback(task):
                # 使用A2A工具处理任务
                await self._handle_a2a_task(task)

            # 订阅第一个事件
            subscription_id = subscribe("bai_lian", events[0], store_info_callback)

            if subscription_id:
                # 更新订阅状态
                self.subscription_id = subscription_id
                self.last_subscription_time = current_time

                # 记录成功订阅
                logger.info(f"[BaiLianTool] 已成功订阅 '{events[0]}', ID: {subscription_id}")

                # 不再发送确认通知，避免重复SmartSisi核心未注册错误
                logger.info("[BaiLianTool] 已成功订阅店铺信息事件，可以接收店铺数据")

                return subscription_id
            else:
                logger.error("[BaiLianTool] 订阅失败，无订阅ID返回")
                return None

        except Exception as e:
            # 订阅过程中出现异常
            logger.error(f"[BaiLianTool] 订阅过程出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def resubscribe(self):
        """重新订阅事件 - 对应A2A的tasks/resubscribe方法

        系统启动或重新初始化后调用此方法重建订阅关系
        """
        logger.info("[BaiLianTool] 尝试重新订阅事件...")

        # 确保工具管理器已初始化并注册工具
        try:
            from SmartSisi.llm.agent.a2a_notification import get_tool_manager
            manager = get_tool_manager()

            # 检查管理器是否运行
            if not manager._running:
                logger.warning("[BaiLianTool] 工具管理器尚未运行，尝试启动...")
                manager.start()
                time.sleep(1)  # 给工具管理器一些时间启动

                if not manager._running:
                    logger.error("[BaiLianTool] 工具管理器无法启动，重订阅将失败")

            # 重新注册工具
            manager.register_tool("bai_lian", self)
            logger.info("[BaiLianTool] 已重新注册到工具管理器")
        except Exception as e:
            logger.error(f"[BaiLianTool] 重新注册到工具管理器失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

        # 尝试重新订阅
        sub_id = self._subscribe_to_zudao_events()

        if sub_id:
            logger.info(f"[BaiLianTool] 重新订阅成功，ID: {sub_id}")
            return True
        else:
            logger.error("[BaiLianTool] 重新订阅失败")
            return False

    async def _handle_a2a_task(self, task):
        """处理从A2A框架接收到的任务"""
        try:
            # 获取中转站实例
            try:
                from SmartSisi.llm.transit_station import get_transit_station
                self.transit_station = get_transit_station()

                if self.transit_station:
                    # 获取中转站会话ID，用于记录
                    logger.info(f"[BaiLianTool] 获取到中转站实例，会话ID: {self.transit_station.session_id if hasattr(self.transit_station, 'session_id') else '未知'}")

                    # 检查SmartSisi核心是否注册
                    has_sisi_core = hasattr(self.transit_station, 'sisi_core') and self.transit_station.sisi_core is not None
                    logger.info(f"[BaiLianTool] 中转站SmartSisi核心状态: {'已注册' if has_sisi_core else '未注册'}")
                else:
                    # 无法获取中转站实例
                    self.transit_station = None
                    return
            except Exception as e:
                # 获取中转站失败
                logger.error(f"[BaiLianTool] 获取中转站实例失败: {str(e)}")
                self.transit_station = None
                return

            # 检查中转站实例
            if not self.transit_station:
                logger.warning(f"[BaiLianTool] 中转站实例不可用，跳过处理通知")
                return

            # 详细记录
            task_id = task.get("id", "无ID")
            source = task.get("source", "未知")
            method = task.get("method", "未知方法")

            logger.info(f"[BaiLianTool] 接收到A2A任务: {method}")
            logger.info(f"[BaiLianTool] 任务来源: {source}, ID: {task_id}")

            # 记录任务来源信息
            if source:
                logger.info(f"[BaiLianTool] 任务来源: {source}")
            else:
                logger.info(f"[BaiLianTool] 任务来源: 未指定")

            # 根据方法路由到对应处理函数
            if method == "event.store_info":
                # 记录详细的参数信息
                params = task.get("params", {})
                logger.info(f"[BaiLianTool] 收到店铺信息事件，参数长度: {len(str(params))}")

                # 设置标记，表示正在处理来自zudao的店铺信息
                # 这可以防止在一个会话中重复处理相同店铺信息
                session_id = task.get("session_id", None) or task_id

                # 创建一个处理锁定键，确保每个会话只处理一次
                import hashlib
                params_hash = hashlib.md5(str(params).encode()).hexdigest()[:8]
                processing_key = f"store_info_{session_id}_{params_hash}"

                # 检查是否已经在处理该店铺集合
                if hasattr(self, '_processing_store_keys') and processing_key in self._processing_store_keys:
                    logger.warning(f"[BaiLianTool] 已在处理该店铺集合，跳过重复处理: {processing_key}")
                    return {"success": False, "error": "重复处理被阻止", "already_processing": True}

                # 存储处理键
                if not hasattr(self, '_processing_store_keys'):
                    self._processing_store_keys = set()
                self._processing_store_keys.add(processing_key)

                try:
                    # 提取店铺数据以便记录
                    stores = None
                    try:
                        params = task.get("params", {})
                        stores = params.get("stores", [])  # 直接从params获取stores
                    except Exception as e:
                        logger.error(f"获取店铺列表失败: {str(e)}")
                        return {"success": False, "error": str(e)}

                    # 确保获取到了店铺列表
                    if not stores or len(stores) == 0:
                        logger.warning(f"没有接收到店铺信息")
                        return {"success": False, "error": "没有店铺信息"}

                    # 获取店铺名称列表
                    store_names = []
                    for store in stores:  # 处理所有店铺
                        if isinstance(store, dict) and "name" in store:
                            store_names.append(store.get("name", "未知店铺"))

                    if not store_names:
                        logger.warning(f"店铺信息中没有店铺名称")
                        return {"success": False, "error": "没有有效的店铺名称"}

                    logger.info(f"收到店铺信息: {', '.join(store_names)}")

                    # 🔥 修复：使用批量处理代替一条一条搜索
                    await self._batch_process_store_reviews(stores)

                    return {"success": True, "message": f"已启动批量处理{len(store_names)}家店铺的评价信息"}
                finally:
                    # 无论成功与否，处理完毕后移除处理键
                    self._processing_store_keys.discard(processing_key)
            else:
                # 详细记录未知方法
                logger.warning(f"[BaiLianTool] 收到未知方法: {method}，无法处理")
                logger.warning(f"[BaiLianTool] 任务详情: {json.dumps(task, ensure_ascii=False)[:200]}")
                return {"success": False, "error": f"不支持的方法: {method}"}

        except Exception as e:
            # 捕获并记录所有异常
            logger.error(f"[BaiLianTool] 处理A2A任务异常: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

            # 返回错误响应
            return {
                "success": False,
                "error": str(e),
                "task_id": task.get("id", "无ID")
            }

    async def _handle_store_info_task(self, task):
        """处理接收到的店铺信息任务

        Args:
            task: 来自zudao_tool的店铺信息任务

        Returns:
            Dict: 处理结果
        """
        try:
            # 提取店铺数据
            params = task.get("params", {})
            stores = params.get("stores", [])

            # 确保获取到了店铺列表
            if not stores or len(stores) == 0:
                logger.warning(f"没有接收到店铺信息")
                return {"success": False, "error": "没有店铺信息"}

            # 提取店铺名称
            store_names = []
            for store in stores:
                if isinstance(store, dict) and "name" in store:
                    store_names.append(store.get("name", "未知店铺"))

            if not store_names:
                logger.warning(f"店铺信息中没有店铺名称")
                return {"success": False, "error": "没有有效的店铺名称"}

            # 批量处理店铺评价 - 新增功能
            await self._batch_process_store_reviews(stores)

            return {"success": True}

        except Exception as e:
            logger.error(f"处理店铺信息任务失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}

    async def _batch_process_store_reviews(self, stores):
        """一次性汇总搜索所有店铺的评价信息

        Args:
            stores: 店铺列表
        """
        try:
            # 提取店铺名称
            store_names = [store.get("name", "未知店铺") for store in stores if isinstance(store, dict) and "name" in store]

            # 检查缓存，过滤掉已缓存的店铺
            uncached_stores = []
            cached_stores = []
            cached_results = []

            for store in stores:
                store_name = store.get("name", "未知店铺")
                cached_result = self._get_cached_result(store_name)
                if cached_result:
                    cached_stores.append(store_name)
                    cached_results.append(cached_result)
                    logger.info(f"[缓存命中] 店铺 {store_name} 使用缓存结果")
                else:
                    uncached_stores.append(store)

            # 如果所有店铺都已缓存，汇总缓存结果并发送
            if not uncached_stores:
                logger.info("[缓存优化] 所有店铺都已缓存，汇总缓存结果")
                combined_cached_result = f"为您找到以下{len(cached_stores)}家店铺的评价信息：\n\n" + "\n\n".join([
                    f"===== {name}的评价 =====\n{result}"
                    for name, result in zip(cached_stores, cached_results)
                ])
                await self._send_combined_result(combined_cached_result, cached_stores)
                return

            # 一次性汇总搜索所有未缓存的店铺
            uncached_names = [store.get("name", "未知店铺") for store in uncached_stores]

            # 构建一次性汇总查询
            combined_query = f"一次性汇总搜索以下所有店铺的评价信息，要求每家店铺都要有详细分析: {', '.join(uncached_names)}"

            # 执行一次性汇总查询
            logger.info(f"[一次性汇总] 执行汇总查询: {combined_query}")
            simplified_context = {
                "store_names": uncached_names,
                "store_ids": [s.get("id", "") for s in uncached_stores if "id" in s],
                "batch_query": True,
                "one_time_search": True  # 标记为一次性搜索
            }

            # 执行查询
            result = await self._async_search(combined_query, simplified_context)

            # 处理搜索结果
            if result and isinstance(result, dict) and "output" in result and "text" in result["output"]:
                search_result = result["output"]["text"]

                # 缓存所有搜索的店铺结果
                for store in uncached_stores:
                    store_name = store.get("name", "未知店铺")
                    self._cache_result(store_name, search_result)

                # 合并缓存结果和新搜索结果
                if cached_results:
                    # 有缓存结果，需要合并
                    cached_part = "\n\n".join([
                        f"===== {name}的评价 =====\n{result}"
                        for name, result in zip(cached_stores, cached_results)
                    ])
                    combined_result = f"为您找到以下{len(store_names)}家店铺的评价信息：\n\n{cached_part}\n\n===== 新搜索结果 =====\n{search_result}"
                else:
                    # 没有缓存结果，直接使用搜索结果
                    combined_result = f"为您找到以下{len(uncached_names)}家店铺的评价信息：\n\n{search_result}"

                # 发送合并结果
                await self._send_combined_result(combined_result, store_names)
            else:
                logger.warning(f"[一次性汇总] 汇总查询未返回有效结果")

                # 🔥 修复：当搜索失败时，生成默认的补充信息
                if cached_results:
                    # 有缓存结果，使用缓存结果
                    cached_part = "\n\n".join([
                        f"===== {name}的评价 =====\n{result}"
                        for name, result in zip(cached_stores, cached_results)
                    ])
                    combined_result = f"为您找到以下{len(cached_stores)}家店铺的评价信息：\n\n{cached_part}"
                else:
                    # 没有缓存结果，生成默认的补充信息
                    store_list = ', '.join(store_names)
                    combined_result = f"哎呀，刚才搜索这些店铺的详细评价时遇到了点问题：{store_list}。不过我刚才已经帮你找到了这些店铺的基本信息，建议你可以直接联系店铺咨询具体服务和价格，或者查看其他评价平台获取更多用户反馈哦~"

                # 发送合并结果
                await self._send_combined_result(combined_result, store_names)

        except Exception as e:
            logger.error(f"[一次性汇总] 批量处理店铺评价失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _send_combined_result(self, combined_result: str, store_names: list):
        """发送合并的搜索结果到中转站"""
        try:
            import time  # 🔥 修复：在函数开始就导入time
            import threading

            logger.info(f"[BaiLianTool] 🔥 _send_combined_result方法被调用，店铺数量: {len(store_names)}")

            # 构建完整通知
            notification = {
                "content": combined_result,
                "source_tool": self.name,
                "content_type": "text",
                "is_tool_notification": True,
                "for_optimization": True,
                "metadata": {
                    "store_names": store_names,
                    "query_type": "one_time_batch_review",
                    "timestamp": time.time()
                }
            }

            logger.info(f"[BaiLianTool] 🔥 通知构建完成，准备检查LG系统状态")
            # 🔥 简单方案：检测LG系统关闭后延迟10秒发送
            def wait_for_lg_close_and_delay():
                """等待LG系统关闭并延迟10秒后发送"""

                def delayed_send():
                    try:
                        # 🔥 修复：使用正确的LG系统状态检测方法
                        max_wait = 15  # 最多等待15秒LG系统关闭
                        check_interval = 1  # 每1秒检查一次
                        waited = 0

                        while waited < max_wait:
                            lg_system_running = False
                            try:
                                from core import sisi_booter
                                if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'chatting'):
                                    lg_system_running = sisi_booter.sisi_core.chatting
                                else:
                                    # 备用检测方法
                                    lg_system_running = bool(self.transit_station and self.transit_station.intermediate_states)
                            except Exception as e:
                                logger.error(f"[BaiLianTool] 检测LG系统状态异常: {str(e)}")
                                lg_system_running = False

                            if not lg_system_running:
                                # LG系统已关闭
                                logger.info(f"[BaiLianTool] ✅ 检测到LG系统已关闭，延迟15秒后发送补充信息")
                                time.sleep(15)  # 延迟15秒
                                break

                            time.sleep(check_interval)
                            waited += check_interval
                            logger.info(f"[BaiLianTool] 等待LG系统和TTS完全结束... ({waited}s/{max_wait}s)")

                        if waited >= max_wait:
                            logger.warning(f"[BaiLianTool] 等待超时，直接发送补充信息")

                        # 发送通知
                        if self.transit_station:
                            res = self.transit_station.add_intermediate_state(notification, self.name, process_immediately=True)
                            if res:
                                logger.info(f"[一次性汇总] ✅ 已将汇总评价结果发送到中转站，共{len(store_names)}家店铺")
                            else:
                                logger.warning(f"[一次性汇总] ❌ 发送到中转站失败")
                        else:
                            logger.warning(f"[一次性汇总] ❌ 中转站未初始化")

                    except Exception as e:
                        logger.error(f"[BaiLianTool] 延迟发送异常: {str(e)}")

                # 启动延迟发送线程
                threading.Thread(target=delayed_send, daemon=True).start()
                logger.info(f"[BaiLianTool] 🚀 已启动延迟发送线程，等待LG系统关闭+10秒延迟")

            # 发送通知到中转站
            if self.transit_station:
                logger.info(f"[BaiLianTool] 🔥 中转站已初始化，检查LG系统状态")

                # 检测LG系统和TTS状态
                lg_system_running = False
                tts_playing = False

                try:
                    from core import sisi_booter
                    # 检测LG系统是否关闭
                    if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'chatting'):
                        lg_system_running = sisi_booter.sisi_core.chatting
                        logger.info(f"[BaiLianTool] LG系统chatting状态: {lg_system_running}")
                    else:
                        logger.warning(f"[BaiLianTool] 无法获取LG系统chatting状态，使用备用检测")
                        lg_system_running = len(self.transit_station.intermediate_states) > 0
                        logger.info(f"[BaiLianTool] 备用检测intermediate_states数量: {len(self.transit_station.intermediate_states)}")

                    # 检测TTS是否还在播放
                    if hasattr(sisi_booter, 'sisi_core'):
                        # 检查是否正在播放音频
                        if hasattr(sisi_booter.sisi_core, 'speaking'):
                            tts_playing = sisi_booter.sisi_core.speaking

                        # 检查音频队列是否还有内容
                        if hasattr(sisi_booter.sisi_core, 'sound_query') and not sisi_booter.sisi_core.sound_query.empty():
                            tts_playing = True

                        logger.info(f"[BaiLianTool] TTS播放状态: {tts_playing}")

                except Exception as e:
                    logger.error(f"[BaiLianTool] 检测系统状态异常: {str(e)}")
                    lg_system_running = False
                    tts_playing = False

                # 检查LG系统是否还在运行或TTS是否还在播放
                if lg_system_running or tts_playing:
                    # LG系统还在运行或TTS还在播放，等待完全结束后延迟发送
                    logger.info(f"[BaiLianTool] 检测到LG系统运行或TTS播放中，等待完全结束")
                    wait_for_lg_close_and_delay()
                else:
                    # LG系统已关闭且TTS播放完毕，延迟15秒后发送
                    logger.info(f"[BaiLianTool] LG系统已关闭且TTS播放完毕，延迟15秒后发送")

                    def delayed_send():
                        logger.info(f"[BaiLianTool] 开始15秒延迟...")
                        time.sleep(15)  # 延迟15秒
                        logger.info(f"[BaiLianTool] 延迟完成，发送通知到中转站")
                        res = self.transit_station.add_intermediate_state(notification, self.name, process_immediately=True)
                        if res:
                            logger.info(f"[BaiLianTool] ✅ 已将汇总评价结果发送到中转站，共{len(store_names)}家店铺")
                        else:
                            logger.warning(f"[BaiLianTool] ❌ 发送到中转站失败")

                    threading.Thread(target=delayed_send, daemon=True).start()
                    logger.info(f"[BaiLianTool] 延迟发送线程已启动")
            else:
                logger.warning(f"[一次性汇总] ❌ 中转站未初始化")
        except Exception as e:
            logger.error(f"[一次性汇总] 发送合并结果失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _process_single_store(self, store):
        """处理单个店铺的评价 - 已废弃，强制使用一次性汇总搜索

        Args:
            store: 单个店铺信息
        """
        logger.warning("[强制一次性汇总] _process_single_store已废弃，强制使用一次性汇总搜索")
        # 强制调用批量处理方法，实现一次性汇总搜索
        await self._batch_process_store_reviews([store])

# 在模块级别添加自动重订阅功能
_tool_instance = None

def get_tool_instance():
    """获取工具实例单例"""
    global _tool_instance
    if _tool_instance is None:
        _tool_instance = BaiLianTool()
    return _tool_instance

def auto_resubscribe():
    """自动重新订阅函数，在系统启动时调用或进行故障恢复

    这个函数会在后台启动一个线程，尝试重新订阅百炼工具到A2A事件系统
    如果立即成功，返回True；如果需要后台重试，返回False
    """
    logger.info("[BaiLianTool] 正在准备自动重新订阅...")

    try:
        # 首先确保百炼工具实例已创建
        bailian = get_tool_instance()

        # 如果已有订阅ID并且最近10秒内订阅过，跳过重复订阅
        if bailian.subscription_id and (time.time() - bailian.last_subscription_time < 10):
            logger.info(f"[BaiLianTool] 已有最近有效订阅，ID: {bailian.subscription_id}")
            return True

        # 首先尝试直接订阅，这会自动检查是否有现有订阅
        sub_id = bailian._subscribe_to_zudao_events()
        if sub_id:
            logger.info(f"[BaiLianTool] 已成功检查或创建订阅: {sub_id}")
            return True

        # 如果直接订阅失败，安排后台重试
        logger.info("[BaiLianTool] 直接订阅失败，安排后台重试...")

        # 在后台线程中进行重试
        def delayed_resubscribe():
            # 🔥 修复：减少首次等待时间至1秒，避免3分钟延迟
            logger.info("[BaiLianTool] 已安排自动重订阅，将在1秒后再次尝试")
            time.sleep(1)  # 从5秒改为1秒

            # 重试计数
            retry_count = 0
            max_retries = 5  # 增加重试次数，但减少延迟
            base_delay = 2  # 减少基础延迟

            while retry_count < max_retries:
                try:
                    # 增加重试延迟，避免过于频繁
                    retry_delay = base_delay + retry_count * 2

                    # 获取百炼工具实例
                    bailian = get_tool_instance()

                    # 尝试订阅
                    sub_id = bailian._subscribe_to_zudao_events()
                    if sub_id:
                        logger.info(f"[BaiLianTool] 重试订阅成功，ID: {sub_id}")
                        break

                    # 增加重试计数
                    retry_count += 1
                    logger.info(f"[BaiLianTool] 订阅重试 {retry_count}/{max_retries} 失败，将在 {retry_delay} 秒后再次尝试")
                    time.sleep(retry_delay)

                except Exception as e:
                    retry_count += 1
                    logger.error(f"[BaiLianTool] 自动重订阅异常: {str(e)}")
                    time.sleep(retry_delay)

            if retry_count >= max_retries:
                logger.error(f"[BaiLianTool] 达到最大重试次数 {max_retries}，自动重订阅失败")

        # 启动后台线程
        import threading
        threading.Thread(target=delayed_resubscribe, daemon=True).start()
        return False

    except Exception as e:
        logger.error(f"[BaiLianTool] 自动重订阅出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# 启动自动重订阅
auto_resubscribe()

# 结尾添加创建工具实例的函数
def create_tool():
    """创建工具实例"""
    tool = get_tool_instance()
    return tool

# 添加模块级invoke函数供A2A服务器调用
def invoke(params):
    """
    模块级invoke函数，供A2A服务器直接调用

    Args:
        params: 调用参数，可以是字符串或字典

    Returns:
        Dict: 工具执行结果
    """
    logger.info(f"[bai_lian] 模块级invoke调用，参数: {params}")

    # 提取查询文本
    text_query = None

    if isinstance(params, dict):
        # 如果是JSON-RPC格式
        if "jsonrpc" in params and "method" in params and "params" in params:
            inner_params = params.get("params", {})
            if isinstance(inner_params, dict):
                text_query = inner_params.get("query", "")
            else:
                text_query = str(inner_params)
        else:
            # 尝试获取查询参数
            text_query = params.get("query", str(params))
    else:
        # 如果是字符串或其他类型，直接作为查询
        text_query = str(params)

    try:
        # 处理可能是JSON字符串的查询
        if isinstance(text_query, str) and text_query.strip().startswith("{"):
            try:
                query_data = json.loads(text_query)
                if isinstance(query_data, dict) and "query" in query_data:
                    text_query = query_data["query"]
            except:
                pass

        # 使用单例模式获取工具实例
        tool = get_tool_instance()
        session_id = f"session_{int(time.time())}"

        # 使用线程隔离方式修复事件循环嵌套问题
        import threading
        result_container = []

        def run_in_thread():
            """在新线程中执行异步操作"""
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(tool._async_search(text_query, session_id=session_id, has_thoughts=True))
                result_container.append(result)
            except Exception as e:
                logger.error(f"[bai_lian] 线程执行错误: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                result_container.append({"error": str(e)})
            finally:
                loop.close()

        # 启动线程并等待完成
        t = threading.Thread(target=run_in_thread)
        t.start()
        t.join(timeout=15)  # 15秒超时

        # 处理结果
        if not result_container:
            return {
                "search_result": {
                    "query": text_query,
                    "error": "处理超时或未返回结果",
                    "timestamp": time.time()
                }
            }

        result = result_container[0]

        # 提取结果文本
        response_text = "未找到相关信息"
        if "output" in result and "text" in result["output"]:
            response_text = result["output"]["text"]

        # 返回标准响应格式
        return {
            "search_result": {
                "query": text_query,
                "result": response_text,
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.error(f"[bai_lian] 处理搜索请求出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        return {
            "search_result": {
                "query": text_query,
                "error": f"搜索失败: {str(e)}",
                "timestamp": time.time()
            }
        }