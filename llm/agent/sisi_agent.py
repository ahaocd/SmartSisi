#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Agent模块核心实现 - 负责处理工具调用和交互
"""

import os
import sys
import time
import logging
import json
import asyncio
import threading
import random  # 添加random模块导入
import copy    # 添加copy模块导入，用于深复制对象
from datetime import datetime
from typing import Annotated, TypedDict, Dict, Any, List, Optional, Union, Callable, Tuple
import concurrent.futures
import requests
import utils.config_util as cfg
from utils import util
# 🚨 content_db已删除，使用Mem0记忆系统
# 🗑️ member_db 已删除，使用Mem0记忆系统
# from core import member_db

# 使用langgraph中现有的功能
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
# 统一使用langchain_core中的消息类型
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
# 导入已经安装依赖的工具
# from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
# from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
# from langchain_community.tools.requests.tool import RequestsGetTool
# from langchain_community.utilities.requests import RequestsWrapper

# 导入本地实现的ToolNode，替代langgraph.prebuilt
from llm.agent.tool_node import ToolNode

# 导入自定义数据库存储
from llm.agent.agent_db import AgentDatabaseSaver, get_default_db_path

# 添加全局单例存储
_instance_lock = threading.Lock()
_agent_instance = None

def get_instance():
    """
    获取AgentCore单例实例
    
    Returns:
        AgentCore: 单例实例
    """
    global _agent_instance
    
    with _instance_lock:
        if _agent_instance is None:
            util.log(1, f"[Agent模块] 创建AgentCore单例实例")
            _agent_instance = SisiAgentCore()
            
    return _agent_instance

# 自定义的SleepTool实现
class SleepTool(BaseTool):
    """休眠工具，使系统暂停指定的秒数。"""
    name: str = "sleep"
    description: str = "使系统暂停指定的秒数。"
    
    def _run(self, seconds: str) -> str:
        """执行睡眠功能"""
        try:
            seconds_float = float(seconds)
            time.sleep(seconds_float)
            return f"系统已休眠{seconds_float}秒"
        except ValueError:
            return f"无效的秒数: {seconds}，应该是一个数字"
            
    async def _arun(self, seconds: str) -> str:
        """异步执行睡眠功能"""
        try:
            seconds_float = float(seconds)
            await asyncio.sleep(seconds_float)
            return f"系统已休眠{seconds_float}秒"
        except ValueError:
            return f"错误: '{seconds}'不是有效的数字"
            
# 定义状态类型
class AgentState(TypedDict):
    """Agent状态定义"""
    messages: List[BaseMessage]

class SisiAgentCore:
    """SmartSisi Agent核心实现，使用LangGraph"""

    def __init__(self, config=None, observation=None, verbose=False):
        """初始化Agent核心
        
        Args:
            config: 配置参数
            observation: 观察数据
            verbose: 是否输出详细日志
        """
        self.config = config
        # 从配置文件读取llm_name
        cfg.load_config()
        self.llm_name = cfg.key_chat_module
        self.observation = observation
        self.verbose = verbose
        
        # 添加默认API参数 - 不含token
        self.api_params = {
            "temperature": 0.5,        # 降低温度以提高精确度
            "top_p": 0.8,              # 控制生成文本的多样性
            "stream": True,            # 启用流式输出
            "presence_penalty": 0.2,   # 减少重复
            "extra_body": {
                "enable_thinking": True,  # 启用思考模式
                "thinking_budget": 4000   # 设置思考预算
            }
        }
        
        # 设置当前时间
        self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 工具缓存标志
        self.tools_initialized = False
        self.tools = []
        
        # Agent缓存标志
        self.agent_initialized = False
        self.agent = None
        
        # 启用LLM工具决策
        self.llm_decides_tools = True
        
        # 初始化工具实例
        self.init_tools()
        
        # 尝试加载属性信息
        try:
            self.attribute = cfg.config.get("attribute", {})
        except Exception as e:
            util.log(2, f"[Agent模块] 属性信息加载失败")
            self.attribute = {"name": "小源"}
        
        # 恢复必要的初始化属性
        try:
            self.attr_info = ", ".join(f"{key}: {value}" for key, value in self.attribute.items())
        except Exception as e:
            util.log(2, f"[Agent模块] 属性信息恢复失败: {str(e)}")
            self.attr_info = "name: 小源"
        
        # 初始化其他必要属性
        self.total_tokens = 0
        self.total_cost = 0

        # 🎯 系统状态管理 - 解决快速响应冲突
        self.system_status = "idle"  # idle, starting, running, busy
        self.request_queue = []  # 请求队列
        
        # 获取环境描述
        env_desc = "None"
        try:
            env_desc = cfg.config.get("location_info", "None")
        except Exception as e:
            logging.warning(f"[Agent模块] 无法加载环境信息: {str(e)}")
        
        # 生成工具描述字符串
        tools_str = ""
        try:
            if self.tools and len(self.tools) > 0:
                tool_descriptions = []
                for tool in self.tools:
                    name = getattr(tool, "name", "未命名工具")
                    desc = getattr(tool, "description", "无描述")
                    tool_descriptions.append(f"- {name}: {desc}")
                tools_str = "\n".join(tool_descriptions)
            else:
                tools_str = "暂无可用工具"
            util.log(1, f"[Agent模块] 成功生成工具描述列表，包含{len(self.tools)}个工具")
        except Exception as e:
            tools_str = "暂无可用工具"
            util.log(2, f"[Agent模块] 生成工具描述列表失败: {str(e)}")
        
        # 新的A2A工具模板
        a2a_tool_template = """
=== A2A工具使用指南 ===
当需要验证信息(天气、时间、货币等)时，你必须严格按以下格式工作:

<thinking>
思考我需要什么信息，以及最适合的工具
</thinking>

<tool>
name: 工具名称
input: {{
  "参数名": "参数值"
}}
</tool>

<answer>
最终给用户的回答(使用角色语气)
</answer>


=== 工具调用示例 ===

例1: 用户问"北京今天天气怎么样"
<thinking>
用户询问北京今天的天气，我需要使用天气查询工具获取准确信息，而不是猜测。
</thinking>
<tool>
name: location_weather
input: {{
  "location": "北京"
}}
</tool>
<answer>
根据查询，北京今天天气晴朗，气温23°C，适合户外活动。
</answer>

例2: 用户问"100美元等于多少人民币"
<thinking>
用户想知道100美元兑换人民币的金额，我需要使用货币转换工具获取最新汇率。
</thinking>
<tool>
name: currency
input: {{
  "currency_from": "USD",
  "currency_to": "CNY",
  "amount": 100
}}
</tool>
<answer>
根据最新汇率，100美元约等于720人民币。
</answer>

例3: 用户问"帮我搜索一下量子计算机的资料"
<thinking>
用户想搜索量子计算机的资料，我应该使用百炼搜索工具获取准确的在线信息。
</thinking>
<tool>
name: bailian
input: {{
  "query": "量子计算机资料"
}}
</tool>
<answer>
我已经为您搜索了量子计算机的资料，以下是相关信息...
</answer>

例4: 用户问"你今天心情怎么样"
<thinking>
这是闲聊问题，不需要工具查询，我可以直接回答。
</thinking>
<answer>
我作为AI助手没有真正的情感，但我随时准备帮助您解决问题！有什么我可以协助您的吗？
</answer>

例5: 用户问"现在几点了"
<thinking>
用户询问当前时间，我需要使用时间查询工具获取准确时间。
</thinking>
<tool>
name: QueryTime
input: {{
  "query": "current_time"
}}
</tool>
<answer>
根据查询，现在的时间是15:30。
</answer>

例6: 用户问"帮我控制一下客厅的灯"
<thinking>
用户想要控制智能设备，我应该使用ESP32控制工具。
+用户想要控制机器人设备，我应该使用sisidisk控制工具。
</thinking>
<tool>
name: sisidisk
input: {{
  "command": "灯光控制",
  "location": "客厅",
  "action": "开灯"
}}
</tool>
"""

        currency_tool_template = """
1. currency (货币转换工具)
   用途: 提供精确的实时货币汇率和转换计算
   适用场景: 
   - 询问不同货币之间的汇率
   - 计算特定金额在不同货币间的转换值
   - 查询历史汇率数据
   参数:
   - currency_from: 源货币代码 (必填, 如"USD", "CNY", "EUR", "JPY"等)
   - currency_to: 目标货币代码 (必填)
   - amount: 要转换的金额 (选填, 默认为1)
   
   示例:
   <tool>
   name: currency
   input: {{
     "currency_from": "USD",
     "currency_to": "CNY",
     "amount": 100
   }}
   </tool>
   
   注意: 永远不要猜测汇率，必须使用此工具获取准确信息
"""

        weather_tool_template = """
2. location_weather (位置天气工具)
   用途: 基于A2A协议的高级天气查询，自动获取位置并提供详细天气信息
   适用场景:
   - 询问天气状况（今天天气怎么样？会下雨吗？）
   - 查询温度（现在几度？温度多少？）
   - 了解未来几天的天气预报
   - 查询湿度、风速等气象数据
   参数格式: 
   - location: 查询位置 (必填, 如"北京"、"上海"、"广州"等)
   - days: 天数预报 (选填, 1-7, 默认为1)
   
   示例:
   <tool>
   name: location_weather
   input: {{
     "location": "北京",
     "days": 3
   }}
   </tool>
   
   注意: 此工具会自动处理位置信息，不要猜测天气，必须使用此工具获取准确信息
"""

        special_tools_template = """
=== 其他专用工具 ===

1. music (音乐生成工具)
   用途: 基于A2A协议的情感音乐生成工具，可根据用户情感状态生成定制化音乐
   适用场景:
   - 用户请求音乐创作（"来首音乐"、"生成一首音乐"、"创作一首"、"创作音乐"）


   

   
   参数:
   - query: 用户音乐创作请求描述 (必填，如"创作一首伤感的歌"、"生成一首摇滚乐")
   - emotion_state: 情感状态 (选填，如"伤感"、"快乐"等)
   
   示例:
   <tool>
   name: music
   input: {{
     "query": "创作一首音乐"
   }}
   </tool>
   
   <tool>
   name: music
   input: {{
     "query": "生成一首伤感的歌",
     "emotion_state": "伤感"
   }}
   </tool>
   
   注意: 生成音乐需要一定时间，告知用户稍候。音乐会在电脑播放的同时自动发送到ESP32设备。

2. sisidisk (星盘控制工具)
   用途: 控制机器人底座「SisiDisk」，包含以下赛博装备:
     • LED 星盘：灯光与情绪呈现
     • 步进电机：驱动坐台旋转（转身/扭腰）
     • 减速电机：音响低频律动
     • 多传感器：距离 / 姿态 / 声音感知
   适用场景:
     - 灯光控制：开灯、关灯、彩虹模式等
     - 动作控制：转身、左右查看、旋转
     - 音乐联动：播放音乐时驱动减速电机
     - 环境感知：测距离、扫描环境
   参数:
     - command: 直接写用户原句，如「转过去」「星盘彩虹模式」

   ⚠️ 重要规则
     - 方向词: "转身""转一下""转半圈""扭头"..."  
     - 灯光词: "开灯""关灯""彩虹模式""星盘"..."  
     - 传感词: "测距离""看看周围""扫描"..."  
     遇到以上短句必须调用 sisidisk！
   

   
   示例:
   <tool>
   name: sisidisk
   input: {{
     "command": "看看右边"
   }}
   </tool>
   
   <tool>
   name: sisidisk
   input: {{
     "command": "星盘灯光切换为彩虹模式"
   }}
   </tool>
   
   <tool>
   name: sisidisk
   input: {{
     "command": "扫描周围环境"
   }}
   </tool>
   
   <tool>
   name: sisidisk
   input: {{
     "command": "转过去"
   }}
   </tool>
   
   注意: sisidisk工具支持多种自然语言控制指令，可直接传入用户的控制请求。对于短句用户输入，如"转过去"，必须调用此工具而不是询问用户。

3. bailian (百炼搜索工具)
   用途: 通用搜索工具，提供所有非位置类信息的查询服务，是系统默认的信息检索工具
   适用场景:
   - 信息搜索查询（任何用户想了解的信息）
   - 社交媒体内容搜索（抖音、小红书、B站、微博等平台内容）
   - 用户评价和真实体验查询（"这家店的真实评价"、"xx产品值得买吗"）
   - 验证信息真实性（"xx是真的吗"、"xx靠谱吗"）
   - 获取多方观点（"网友怎么评价xx"、"对xx有什么看法"）
   - 任何包含"搜索"、"查询"、"查找"、"了解"等关键词的问题
   - 询问热点话题或热门内容（"最近有什么热门话题"、"现在流行什么"）
   参数:
   - query: 搜索查询内容 (必填)
   - context: 上下文信息，可包含zudao结果等 (选填)
   
   示例:
   <tool>
   name: bailian
   input: {{
     "query": "量子计算机的最新进展"
   }}
   </tool>
   
   或者包含上下文:
   <tool>
   name: bailian
   input: {{
     "query": "这家店的技师服务真实评价",
     "context": {{
       "zudao_result": "上一个工具返回的结果"
     }}
   }}
   </tool>
   
   使用指南:
   1. 构建高效查询
      - 保留用户原始搜索意图
      - 添加相关限定词(如"真实评价"、"社交媒体"、"用户体验")
   
   2. 理解查询意图类别
      - 信息型查询: 寻找事实和资料
      - 评价型查询: 寻找用户体验和意见
 
   3. 优化上下文传递
      - 从zudao结果中提取关键实体(店名、位置、特点)
      - 利用这些实体构建更精准的搜索查询
      - 根据查询意图添加适当的修饰词
   
   注意: 
   - 使用此工具获取最新、准确的在线信息，特别是社交媒体真实评价
   - 当用户明确请求使用"bailian"、"百炼"或"搜索工具"时，必须优先使用此工具
   - 非常适合在zudao工具找到店铺后，进一步查询该店铺在社交媒体上的真实评价
   - 特别擅长获取真实用户体验、评价和分享内容
   - 对于新闻、热点和时效性内容，此工具提供最新信息

4. zudao (位置服务智能助手)
   用途: 基于A2A协议的位置服务工具，仅用于地理位置服务、导航和附近设施查询
   适用场景:
   - 查询附近设施（附近有什么餐厅？最近的医院在哪？）
   - 导航与位置服务（怎么去西湖？附近有什么好玩的？）
   - 休闲娱乐场所位置（KTV、酒吧、夜店、会所在哪里）
   - 复杂位置查询（找个评分高的中餐厅，找个环境好的咖啡厅）
   参数格式（两种方式均可）: {{}}
   方式二 - 传递原始问题: {{"query": "用户原始问题，如'附近有什么好吃的'"}}
   
   示例:
   <tool>
   name: zudao
   input: {{}}
   </tool>
   
   或者:
   <tool>
   name: zudao
   input: {{
     "query": "附近有什么好吃的"
   }}
   </tool>
   
   注意: 此工具仅负责位置信息和导航，不提供信息搜索功能
"""

        other_tools_template = """
=== 其他核心工具简介 ===
- hot_search: 查询最新热搜话题
  <tool>
  name: hot_search
  input: {{
    "platform": "douyin",
    "count": 5
  }}
  </tool>
  
- QueryTime: 获取当前时间
  <tool>
  name: QueryTime
  input: {{
    "query": "current_time"
  }}
  </tool>
  
- 🚨 定时器功能已禁用：QueryTimerDB、ToRemind已删除
  
- 🚨 DeleteTimer: 已删除，定时器功能已禁用
"""

        # 添加工具协作流程模板
        tools_cooperation_template = """
=== zudao-bailian工具协作流程 ===

# 1. 工具功能定位
- zudao工具：位置服务智能体
  • 核心能力：自动获取用户位置，查询附近场所，特殊服务推荐
  • 数据结构：返回店铺名称、地址、评分等结构化信息
  • 关键场景：附近查询、位置服务、特殊服务关键词检测

- bailian工具：信息搜索智能体
  • 核心能力：网络搜索、社交媒体内容聚合、真实用户评价提取
  • 数据增强：从zudao结果中自动提取店铺名称进行精准搜索
  • 关键场景：评价查询、真实性验证、用户体验分析

# 2. 硬性工作流规则
- 顺序强制规则：位置类信息必须先用zudao获取，再用bailian评价
- 数据传递机制：bailian必须通过context参数接收zudao结果
- 禁止操作：
  • 禁止在没有位置信息时直接使用bailian查询评价
  • 禁止同时调用zudao和bailian（必须分两阶段）
  • 禁止忽略zudao结果中的店铺名称

# 3. 触发条件清单
## zudao触发词（第一阶段）
- 位置关键词：附近、周边、找个、有什么、怎么走、在哪
- 特殊服务词：按摩、足浴、SPA、会所、KTV、酒吧、夜店、技师、桑拿
- 情感状态词：想放松、放松一下、解压、休息、累了
- 娱乐需求词：想玩、嗨一下、找乐子、好玩的地方
- 服务查询词：找一找、有什么好的、推荐、哪里有

## bailian触发词（第二阶段）
- 评价词：评价、怎么样、好不好、如何、值得、靠谱吗
- 真实性词：真实、实际、体验、用户、网友、亲身、社交媒体
- 详情词：详细、更多、具体、深入、全面

# 4. 标准执行示例
用户："附近有什么好的足浴店，评价怎么样？"

第一阶段 - 位置查询:
<tool>
name: zudao
input: {"query": "附近好的足浴店"}
</tool>

<收到zudao返回的店铺列表>

第二阶段 - 评价查询:
<tool>
name: bailian
input: {
  "query": "足浴店真实评价",
  "context": {"zudao_result": "从zudao返回的店铺信息"}
}
</tool>

# 5. 技术链路说明
1. zudao内部逻辑:
   - 自动获取用户位置信息(_get_user_location)
   - 检测特殊服务关键词(detect_service_request)
   - 通过百度地图等获取附近场所信息
   - 返回结构化的店铺列表

2. bailian内部增强机制:
   - _extract_stores_from_zudao: 自动提取店铺名称、地址、评分
   - _build_enhanced_query: 基于店铺构建精准搜索查询
   - _enhance_for_social_media: 优先搜索社交平台内容
   - 自动关注真实用户体验和评价
"""

        # 设置checkpoint配置(测试模式下尤其必要)
        is_test_mode = os.environ.get("SISI_TEST_MODE", "0") == "1"
        
        # 不预先生成thread_id，使用调用时基于uid生成的固定thread_id
        # 这确保了不同方法中使用相同的thread_id生成规则
        
        # 在测试模式下打印checkpoint参数
        if is_test_mode:
            util.log(1, f"[Agent模块] 测试模式已启用")
        
        # 创建数据库存储，替代内存存储
        db_path = get_default_db_path()
        util.log(1, f"[Agent模块] 使用数据库存储: {db_path}")
        self.memory = AgentDatabaseSaver(db_path)
        
        self.history_cache = {}  # 新增：历史消息缓存
        
    def init_tools(self):
        """初始化工具"""
        # 如果工具已初始化，则跳过
        if self.tools_initialized and len(self.tools) > 0:
            util.log(1, f"[Agent模块] 工具已初始化，跳过重复初始化")
            return

        tools = []
        
        # 添加常用工具
        # 注释掉Weather工具，避免与location_weather冲突
        # from llm.agent.tools.Weather import Weather
        # 移除重复的时间工具，只保留QueryTime
        # from llm.agent.tools.TimeQuery import TimeQuery  
        # 🚨 定时器相关工具已删除
        # from llm.agent.tools.ToRemind import ToRemind
        # from llm.agent.tools.QueryTimerDB import QueryTimerDB
        # 🚨 DeleteTimer已删除，定时器功能已禁用
        from llm.agent.tools.QueryTime import QueryTime
        from llm.agent.tools.HotSearch import HotSearch  # 添加热搜工具导入
        
        # tools.append(Weather())  # 注释掉Weather工具
        # 🚨 定时器工具已删除
        # tools.append(QueryTimerDB())
        # tools.append(ToRemind())
        tools.append(QueryTime())  # 只保留QueryTime工具
        tools.append(HotSearch())  # 添加热搜工具
        
        # 以下工具已被移除，防止大模型误用通用工具来获取天气信息
        # 移除搜索工具以防大模型误调用
        # try:
        #     from llm.agent.tools.SearchTool import SearchTool
        #     tools.append(SearchTool())
        #     util.log(1, f"[Agent模块] 成功添加DuckDuckGo搜索工具")
        # except Exception as e:
        #     util.log(2, f"[Agent模块] DuckDuckGo搜索工具初始化失败: {str(e)}")
        #     # 如果自定义工具失败，尝试使用默认实现
        #     try:
        #         tools.append(DuckDuckGoSearchRun())
        #         util.log(1, f"[Agent模块] 使用默认DuckDuckGo搜索工具")
        #     except Exception as e:
        #         util.log(2, f"[Agent模块] 默认DuckDuckGo搜索工具也初始化失败: {str(e)}")
        
        # 移除维基百科工具，防止大模型误用来获取天气信息
        # try:
        #     from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
        #     tools.append(WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper()))
        # except Exception as e:
        #     util.log(2, f"[Agent模块] 维基百科工具初始化失败: {str(e)}")
        
        # 移除HTTP请求工具，防止大模型通过网络请求获取天气信息
        # try:
        #     requests_wrapper = RequestsWrapper()
        #     tools.append(
        #         RequestsGetTool(
        #             requests_wrapper=requests_wrapper,
        #             name="http_get",
        #             description="通过HTTP请求获取网页内容的工具，输入URL，返回HTML或JSON内容"
        #         )
        #     )
        # except Exception as e:
        #     util.log(3, f"[Agent模块] HTTP请求工具初始化失败: {str(e)}")
            
        # 添加睡眠工具
        try:
            tools.append(SleepTool())
        except Exception as e:
            util.log(2, f"[Agent模块] 睡眠工具初始化失败: {str(e)}")
            
        # 尝试加载A2A工具 
        try:
            # 检查A2A服务器URL配置
            a2a_server_url = None
            try:
                from utils.config_util import Config
                cfg = Config()
                cfg.load_config()
                a2a_server_url = cfg.get_value("a2a_server_url") or "http://localhost:8001"
            except:
                a2a_server_url = "http://localhost:8001"  # 默认URL
            
            # 导入A2A适配器
            from .a2a_adapter import create_a2a_tools
            a2a_tools = create_a2a_tools(a2a_server_url)
            
            if a2a_tools:
                tools.extend(a2a_tools)
                util.log(1, f"[SisiAgent] 加载了 {len(a2a_tools)} 个A2A工具")
            else:
                util.log(2, f"[SisiAgent] 未找到可用的A2A工具")
        except Exception as e:
            util.log(2, f"[SisiAgent] 加载A2A工具出错: {str(e)}")
        
        self.tools = tools
        self.tools_initialized = True
        util.log(1, f"[Agent模块] 成功初始化{len(tools)}个工具")

    def build_agent(self, nlp_result="", additional_msgs=None):
        """构建Agent工作流"""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
            from langgraph.graph import StateGraph, END
            from langgraph.graph.message import add_messages
            import json
            from typing import Annotated, Sequence, List, Dict, Any, TypedDict, Optional, Union
            
            # 定义Agent状态类型
            class AgentState(TypedDict):
                messages: Annotated[Sequence[Any], add_messages]
            
            # 创建状态图
            workflow = StateGraph(AgentState)
            
            # 日志记录
            util.log(1, f"[Agent模块] 开始构建标准LangGraph工作流")

            # 获取LangGraph版本 - 直接尝试从langgraph模块获取
            try:
                import langgraph
                import importlib
                lg_version = getattr(langgraph, "__version__", None)
                if lg_version is None:
                    # 如果直接获取失败，尝试通过importlib获取版本
                    try:
                        lg_version = importlib.metadata.version('langgraph')
                    except:
                        lg_version = "0.0.0"
                util.log(1, f"[Agent模块] 检测到LangGraph版本: {lg_version}")
            except Exception as e:
                lg_version = "0.0.0"
                util.log(2, f"[Agent模块] 获取LangGraph版本失败: {str(e)}")
            
            # 加载NLP结果
            nlp_content = nlp_result or ""
            
            # 添加系统提示
            system_msg = self.get_system_message()
            messages = []
            
            # 添加用户请求消息
            if additional_msgs:
                messages.extend(additional_msgs)
            else:
                messages.append(HumanMessage(content=nlp_content))
            
            # 1. 定义节点
            # 🏥 医疗包分析节点 - 动脑的工作（分析和决策）
            def agent_node(state):
                try:
                    util.log(1, f"[Agent模块] 开始处理用户请求")
                    
                    # 向中转站添加通知 - 使用全局中转站实例
                    try:
                        # 获取全局中转站实例
                        from llm.transit_station import get_transit_station
                        transit = get_transit_station()
                        transit.add_intermediate_state("正在思考您的问题...", "LG:思考节点")
                        
                        # 记录调试日志
                        util.log(1, f"[Agent模块] 已向中转站发送思考状态")
                    except Exception as e:
                        util.log(2, f"[Agent模块] 添加思考节点中转站通知失败: {str(e)}")
                        import traceback
                        util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
                    
                    # 获取系统消息
                    system_msg = self.get_system_message()
                    
                    # 获取所有消息
                    messages = state.get("messages", [])
                    
                    # 检查是否有A2A工具输出，优化显示格式
                    for i, msg in enumerate(messages):
                        if hasattr(msg, "content") and isinstance(msg.content, str):
                            if "A2A工具返回" in msg.content or "CURRENCY_TOOL" in msg.content or "LOCATION_WEATHER_TOOL" in msg.content or "ZUDAO_TOOL" in msg.content:
                                # 优化A2A工具输出格式
                                try:
                                    import re
                                    import json
                                    
                                    # 尝试识别并格式化JSON内容
                                    json_pattern = r'\{.*\}'
                                    json_matches = re.findall(json_pattern, msg.content, re.DOTALL)
                                    
                                    if json_matches:
                                        for json_str in json_matches:
                                            try:
                                                # 格式化JSON字符串
                                                valid_json_str = json_str.replace("'", "\"").replace("None", "null").replace("True", "true").replace("False", "false")
                                                data = json.loads(valid_json_str)
                                                
                                                if isinstance(data, dict):
                                                    tool_result = ""
                                                    # 安全格式化 - 确保所有可能的字段都有默认值
                                                    if "currency" in msg.content.lower():
                                                        tool_result = "货币转换结果:\n"
                                                        if "result" in data:
                                                            amount = data.get('amount', '1')
                                                            from_currency = data.get('from', 'USD')
                                                            to_currency = data.get('to', 'CNY')
                                                            result = data.get('result', '未知')
                                                            rate = data.get('rate', '未知')
                                                            date = data.get('date', '今天')
                                                            
                                                            tool_result += f"转换金额: {amount} {from_currency} = {result} {to_currency}\n"
                                                            tool_result += f"汇率: 1 {from_currency} = {rate} {to_currency}\n"
                                                            tool_result += f"日期: {date}"
                                                        elif "error" in data:
                                                            tool_result += f"查询失败: {data.get('error', '未知错误')}"
                                                        
                                                        # 安全替换
                                                        if tool_result:
                                                            msg.content = tool_result
                                                    
                                                    elif "weather" in msg.content.lower():
                                                        tool_result = "天气查询结果:\n"
                                                        location = data.get('location', '未知')
                                                        weather = data.get('weather', '未知')
                                                        temperature = data.get('temperature', '未知')
                                                        humidity = data.get('humidity', '未知')
                                                        updated_time = data.get('updated_time', '未知')
                                                        
                                                        tool_result += f"地点: {location}\n"
                                                        tool_result += f"天气: {weather}\n"
                                                        tool_result += f"温度: {temperature}°C\n"
                                                        tool_result += f"湿度: {humidity}%\n"
                                                        tool_result += f"更新时间: {updated_time}"
                                                        
                                                        # 安全替换
                                                        if tool_result:
                                                            msg.content = tool_result
                                            except Exception as format_err:
                                                util.log(2, f"[Agent模块] 格式化A2A工具输出失败: {str(format_err)}")
                                                # 不修改原始消息，保留原样
                                except Exception as e:
                                    util.log(2, f"[Agent模块] A2A工具输出格式化失败: {str(e)}")
                    
                    # 使用标准LangGraph格式
                    util.log(1, f"[Agent模块] 使用标准LangGraph格式，让LLM决定工具使用")
                            
                    # 加上系统提示
                    all_messages = [system_msg] + messages
                    
                    # 调用LLM
                    response = self.call_llm(all_messages)
                    
                    # 记录结果
                    util.log(1, f"[Agent模块] LLM响应: {response.content[:100]}...")
                    util.log(1, f"[Agent模块] 思考阶段完成，生成回复或决定调用工具")
                    
                    # 向中转站添加完成状态
                    try:
                        # 获取全局中转站实例
                        from llm.transit_station import get_transit_station
                        transit = get_transit_station()
                        transit.add_intermediate_state(f"思考完成: {response.content[:50]}...", "LG:思考完成")
                        
                        # 记录调试日志
                        util.log(1, f"[Agent模块] 已向中转站发送思考完成状态")
                    except Exception as e:
                        util.log(2, f"[Agent模块] 添加思考完成中转站通知失败: {str(e)}")
                    
                    # 返回结果
                    return {"messages": [response]}
                except Exception as e:
                    util.log(2, f"[Agent模块] 代理节点异常: {str(e)}")
                    import traceback
                    util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
                    # 返回错误消息
                    err_msg = AIMessage(content=f"代理处理出错: {str(e)}")
                    return {"messages": [err_msg]}
            
            # 重写工具节点 - 在开始和结束时添加通知
            def tool_node_with_notification(state):
                try:
                    # 向中转站添加通知 - 工具开始 - 使用全局中转站
                    try:
                        # 获取全局中转站实例
                        from llm.transit_station import get_transit_station
                        transit = get_transit_station()
                        
                        # 尝试提取工具名称
                        tool_name = "未知工具"
                        messages = state.get("messages", [])
                        if messages:
                            last_message = messages[-1]
                            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                                tool_names = [t.get("name", "未知工具") for t in last_message.tool_calls]
                                transit.add_intermediate_state(
                                    f"正在使用工具: {', '.join(tool_names)}",
                                    "LG:工具调用节点"
                                )
                                # 记录调试日志
                                util.log(1, f"[Agent模块] 已向中转站发送工具调用状态: {', '.join(tool_names)}")
                    except Exception as e:
                        util.log(2, f"[Agent模块] 添加工具节点中转站通知失败: {str(e)}")
                        import traceback
                        util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
                    
                    # 调用原始工具节点
                    result = self.safe_tool_node(state)
                    
                    # 向中转站添加通知 - 工具结束 - 使用全局中转站
                    try:
                        # 获取全局中转站实例
                        from llm.transit_station import get_transit_station
                        transit = get_transit_station()
                        transit.add_intermediate_state("工具处理完成，分析结果中...", "LG:工具完成节点")
                        
                        # 记录调试日志
                        util.log(1, f"[Agent模块] 已向中转站发送工具完成状态")
                    except Exception as e:
                        util.log(2, f"[Agent模块] 添加工具完成中转站通知失败: {str(e)}")
                        import traceback
                        util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
                    
                    return result
                except Exception as e:
                    util.log(2, f"[Agent模块] 包装工具节点异常: {str(e)}")
                    import traceback
                    util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
                    return state
            
            # 工具节点 - 执行工具调用
            self.tool_node = tool_node_with_notification
            
            # 添加节点
            workflow.add_node("agent", agent_node)
            workflow.add_node("tools", self.tool_node)
            workflow.set_entry_point("agent")
            
            # 添加从工具到代理的边
            workflow.add_edge("tools", "agent")

            # 🏥 添加医疗包流程边
            
            # 决策函数 - 确定下一步
            def should_continue(state):
                """LangGraph标准循环控制 - 简化版
                
                仅保留最基本的终止条件，主要依赖LLM决策
                同时保持与中转站兼容性
                """
                messages = state["messages"]
                if not messages:
                    return "agent"
                
                # 保留基本状态跟踪(用于日志和监控，不影响决策)
                if "total_calls" not in state:
                    state["total_calls"] = 0
                    state["last_tool"] = None
                
                last_message = messages[-1]
                
                # 1. 工具结果消息 -> 返回到agent思考
                if isinstance(last_message, ToolMessage):
                    state["total_calls"] += 1
                    
                    # 仅保留最基本的安全限制，防止极端情况下的无限循环
                    # 循环次数限制提高到10次，给模型更多思考和工具使用空间
                    if state["total_calls"] >= 10:
                        util.log(1, f"[Agent流程] 达到最大安全循环限制(10次)，强制结束")
                        # 添加中转站通知但不影响流程
                        try:
                            from llm.transit_station import get_transit_station
                            transit = get_transit_station()
                            transit.add_intermediate_state("达到最大循环限制，进入最终回答阶段", "LG:循环控制")
                        except Exception as e:
                            util.log(2, f"[Agent流程] 添加中转站通知失败: {str(e)}")
                        return END
                    
                    util.log(1, f"[Agent流程] 工具执行完毕，返回agent思考，当前调用次数: {state['total_calls']}")
                    return "agent"
                
                # 2. 人类消息 -> 进入agent思考
                if isinstance(last_message, HumanMessage):
                    util.log(1, f"[Agent流程] 接收到用户消息，进入agent思考")
                    return "agent"
                
                # 3. AI消息 -> 检查工具调用
                if isinstance(last_message, AIMessage):
                    # 检查是否包含工具调用
                    has_tool_call = False

                    # 3.1 检查标准工具调用属性
                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        has_tool_call = True

                    # 3.2 检查内容中的工具调用格式
                    if not has_tool_call and hasattr(last_message, "content"):
                        content = last_message.content
                        if "<tool>" in content or "Action:" in content or "action:" in content.lower():
                            has_tool_call = True

                    # 🏥 检查是否需要医疗包处理
                    if hasattr(last_message, "content"):
                        content = last_message.content

                    # 如果检测到工具调用，进入tools节点
                    if has_tool_call:
                        util.log(1, f"[Agent流程] AI消息包含工具调用，进入tools节点")
                        # 添加中转站通知
                        try:
                            from llm.transit_station import get_transit_station
                            transit = get_transit_station()
                            transit.add_intermediate_state("检测到工具调用请求，准备执行工具", "LG:循环控制")
                        except Exception as e:
                            util.log(2, f"[Agent流程] 添加中转站通知失败: {str(e)}")
                        return "tools"

                    # 没有工具调用，流程结束
                    util.log(1, f"[Agent流程] AI响应完成，没有工具调用，流程结束")
                    # 添加中转站通知
                    try:
                        from llm.transit_station import get_transit_station
                        transit = get_transit_station()
                        transit.add_intermediate_state("任务完成，无需更多工具调用", "LG:循环控制")
                    except Exception as e:
                        util.log(2, f"[Agent流程] 添加中转站通知失败: {str(e)}")
                    return END
                
                # 其他情况，默认结束流程
                util.log(1, f"[Agent流程] 未知消息类型，流程结束")
                return END
            
            # 添加条件边
            workflow.add_conditional_edges(
                "agent",
                should_continue,
                {
                    "tools": "tools",  # 修改这里，使用一致的节点名称
                    "agent": "agent",  # 添加自循环以处理不完整响应
                    END: END
                }
            )
            
            # 完成工作流构建
            util.log(1, f"[Agent模块] LangGraph工作流构建完成，节点: agent, tools")
            
            # 编译并返回
            self.agent_initialized = True
            self.agent = workflow.compile()
            
            return self.agent
            
        except Exception as e:
            util.log(2, f"[Agent模块] 构建Agent异常: {str(e)}")
            import traceback
            util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
            return None

    def call_llm(self, state):
        """
        LLM节点，处理用户请求，使用O3mini模型直接进行API调用
        这是Agent系统的核心处理节点，不依赖对话模型(NLP)
        
        Args:
            state: 可以是包含消息历史的状态字典，也可以是直接的消息列表
            
        Returns:
            AIMessage对象或更新后的状态
        """
        # 确保在开头导入AIMessage，避免局部变量未定义问题
        from langchain_core.messages import AIMessage
        
        try:
            # 获取输入消息列表 - 支持两种入参格式
            if isinstance(state, dict) and "messages" in state:
                messages = state["messages"]
            elif isinstance(state, list):
                messages = state
            else:
                util.log(2, f"[Agent-O3mini] 错误: 输入格式不支持: {type(state)}")
                return AIMessage(content="处理请求时出现内部错误，输入格式不支持")
                
            util.log(1, f"[Agent-O3mini] ====== 调用LLM节点 ======")
            
            # 检查最后一个消息类型，记录A2A状态日志
            for i, msg in enumerate(messages[-3:] if len(messages) >= 3 else messages):
                msg_type = type(msg).__name__
                if isinstance(msg, ToolMessage):
                    util.log(1, f"[A2A处理] 检测到工具结果消息(#{i})，工具名称: {msg.name}")
                    util.log(1, f"[A2A处理] 工具结果内容: {str(msg.content)[:150]}...")
            
            util.log(1, f"[Agent-O3mini] 接收到{len(messages)}条消息，准备处理")
            
            # 记录日志便于调试
            for i, msg in enumerate(messages[-2:]):  # 只记录最后两条消息
                msg_type = msg.type if hasattr(msg, 'type') else type(msg).__name__
                content_preview = str(msg.content)[:100] if hasattr(msg, 'content') else str(msg)[:100]
                util.log(1, f"[Agent-O3mini] 消息[{i}]: 类型={msg_type}, 内容={content_preview}...")
            
            # 将消息格式化为可处理的请求格式
            formatted_messages = []
            has_system_message = False
            
            for msg in messages:
                if hasattr(msg, 'type') and hasattr(msg, 'content'):
                    if msg.type == "system":
                        if not has_system_message:
                            formatted_messages.append({"role": "system", "content": msg.content})
                            has_system_message = True
                        else:
                            # 已经有系统消息，将该系统消息转为用户消息
                            formatted_messages.append({"role": "user", "content": f"系统指示: {msg.content}"})
                    else:
                        role = "user" if msg.type == "human" else "assistant"
                        formatted_messages.append({"role": role, "content": msg.content})
                elif isinstance(msg, dict) and "role" in msg and "content" in msg:
                    # 直接处理已格式化的消息
                    if msg["role"] == "system":
                        if not has_system_message:
                            formatted_messages.append(msg)
                            has_system_message = True
                        else:
                            # 已经有系统消息，将该系统消息转为用户消息
                            formatted_messages.append({"role": "user", "content": f"系统指示: {msg['content']}"})
                    else:
                        formatted_messages.append(msg)
                elif isinstance(msg, ToolMessage):
                    # 特殊处理工具消息，确保LLM知道这是工具结果
                    # 检查工具是否失败
                    if "任务失败" in msg.content or "工具调用失败" in msg.content or "失败" in msg.content:
                        # 工具失败时，明确告知LLM这是失败状态
                        tool_result = f"工具: {msg.name} 执行失败:\n{msg.content}\n\n请告诉用户工具执行失败，不要说正在处理或准备中。"
                        util.log(1, f"[A2A处理] 检测到工具失败: {msg.name}, 内容: {msg.content}")
                    else:
                        tool_result = f"工具: {msg.name} 返回结果:\n{msg.content}"
                    # 作为assistant角色加入，避免被误认为用户输入
                    formatted_messages.append({"role": "assistant", "content": tool_result})
                    util.log(1, f"[A2A处理] 已格式化工具结果消息以assistant角色加入，避免上下文错位")
                else:
                    # 尝试推断消息类型
                    if type(msg).__name__ == "SystemMessage":
                        if not has_system_message:
                            formatted_messages.append({"role": "system", "content": str(msg.content)})
                            has_system_message = True
                        else:
                            # 已经有系统消息，将该系统消息转为用户消息
                            formatted_messages.append({"role": "user", "content": f"系统指示: {str(msg.content)}"})
                    elif type(msg).__name__ == "HumanMessage":
                        formatted_messages.append({"role": "user", "content": str(msg.content)})
                    elif type(msg).__name__ == "AIMessage":
                        formatted_messages.append({"role": "assistant", "content": str(msg.content)})
                    else:
                        # 默认作为用户消息处理
                        formatted_messages.append({"role": "user", "content": str(msg)})
            
            util.log(1, f"[Agent-O3mini] 格式化后消息数量: {len(formatted_messages)}")
            # 新增：输出输入序列角色顺序，便于检查上下文先后
            try:
                seq_brief = " | ".join([f"{idx}:{msg['role']}" for idx, msg in enumerate(formatted_messages)])
                util.log(1, f"[LLM输入顺序] {seq_brief}")
            except Exception:
                pass
            
            # 检查是否处于工具结果处理状态
            is_tool_result_processing = False
            for i in range(len(messages)-1, -1, -1):
                if isinstance(messages[i], ToolMessage):
                    is_tool_result_processing = True
                    util.log(1, f"[A2A处理] 当前处于工具结果处理状态，提示LLM生成最终回答")
                    break
            
            # 如果处于工具结果处理状态，添加特殊指令
            if is_tool_result_processing:
                instruction = "你已经收到了工具调用的结果。现在请提供一个完整的回答，包含<answer>标签。不要再调用工具，而是直接回答用户的问题。"
                if not has_system_message:
                    # 如果之前没有系统消息，将其作为系统消息添加
                    formatted_messages.insert(0, {"role": "system", "content": instruction})
                    has_system_message = True
                else:
                    # 将指令拼接到首个system消息末尾，避免干扰user轮次
                    for msg in formatted_messages:
                        if msg["role"] == "system":
                            msg["content"] += "\n\n" + instruction
                            break
            
            # 直接调用O3mini API处理
            try:
                # 加载配置信息
                import utils.config_util as cfg
                cfg.load_config()
                
                # 设置请求参数 - 使用类中预设的参数，但不包含API token
                data = {
                    "messages": formatted_messages,
                    "model": cfg.agentss_model_engine,
                    "max_tokens": int(cfg.agentss_max_tokens) if hasattr(cfg, 'agentss_max_tokens') and cfg.agentss_max_tokens else 2000
                }
                
                # 合并预设API参数
                data.update(self.api_params)
                
                # 构建API URL
                url = f"{cfg.agentss_base_url}/chat/completions"
                
                # 验证URL是否为None
                if not url or 'None/' in url:
                    util.log(2, f"[Agent-O3mini] 错误: URL无效({url})，请检查system.conf中的agentss_base_url配置")
                    raise ValueError("agentss_base_url配置无效，无法调用API")
                
                util.log(1, f"[Agent-O3mini] 发送API请求: {url}")
                
                # 记录请求时间
                import time
                start_time = time.time()
                
                # 设置API请求
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {cfg.agentss_api_key}"
                }
                
                # 添加流式处理处理逻辑
                if data.get("stream", False):
                    # 如果启用了流式输出，这里可以添加处理流式响应的代码
                    # 对于现在，简单起见，我们禁用流式输出
                    data["stream"] = False
                    util.log(1, f"[Agent-O3mini] 流式输出功能目前禁用")
                
                # 发送请求，设置超时
                response = requests.post(url, headers=headers, json=data, timeout=50)
                
                # 记录响应时间
                end_time = time.time()
                util.log(1, f"[Agent-O3mini] API响应时间: {end_time - start_time:.2f}秒, 状态码: {response.status_code}")
                
                # 处理响应
                if response.status_code == 200:
                    try:
                        result = response.json()
                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0]["message"]["content"]
                            
                            # 记录A2A特定处理
                            util.log(1, f"[A2A处理] LLM响应内容: {content[:150]}...")
                            
                            # 检查是否存在reasoning_content思考内容
                            if "reasoning_content" in result["choices"][0]["message"]:
                                reasoning_content = result["choices"][0]["message"]["reasoning_content"]
                                util.log(1, f"[A2A处理] 检测到思考内容: {reasoning_content[:150]}...")
                                
                                # 将思考内容发送到中转站
                                try:
                                    from llm.transit_station import get_transit_station
                                    transit = get_transit_station()
                                    transit.add_intermediate_state(reasoning_content, "thinking_node", True)
                                    util.log(1, f"[A2A处理] 已将思考内容发送到中转站")
                                except Exception as e:
                                    util.log(2, f"[A2A处理] 处理思考内容异常: {str(e)}")
                            
                            # 如果是工具执行后处理，检查是否有<answer>标签
                            if is_tool_result_processing and "<answer>" not in content:
                                # 智能检测是否应该跳过answer标签添加
                                should_skip_answer = self._should_skip_answer_tag(content)

                                if should_skip_answer:
                                    util.log(1, f"[A2A处理] 智能检测：跳过answer标签添加: {content[:50]}...")
                                    # 保持内容原样，不添加answer标签
                                else:
                                    util.log(1, f"[A2A处理] 工具执行后LLM未生成<answer>标签，添加提示")
                                    # 从内容中提取潜在的答案并包装在<answer>标签中
                                    modified_content = f"{content}\n\n<answer>{content}</answer>"
                                    content = modified_content
                            
                            # 创建AI消息
                            ai_message = AIMessage(content=content)
                            
                            # 如果内容中包含工具调用描述，转换为LangGraph工具调用格式
                            if "<tool>" in content:
                                util.log(1, f"[A2A处理] 检测到A2A工具调用格式")
                                try:
                                    import re
                                    tool_match = re.search(r'<tool>(.*?)</tool>', content, re.DOTALL)
                                    if tool_match:
                                        tool_content = tool_match.group(1).strip()
                                        name_match = re.search(r'name:\s*(\w+)', tool_content)
                                        if name_match:
                                            tool_name = name_match.group(1).strip()
                                            util.log(1, f"[A2A处理] 提取到工具调用: {tool_name}")
                                except Exception as e:
                                    util.log(2, f"[A2A处理] 解析工具调用失败: {str(e)}")
                            
                            # 根据输入类型返回不同格式的响应
                            if isinstance(state, dict):
                                # 更新状态
                                state["messages"] = state["messages"] + [ai_message]
                                return state
                            else:
                                # 直接返回AI消息
                                return ai_message
                        else:
                            error_message = "API响应格式错误，无法找到回复内容"
                            util.log(2, f"[Agent-O3mini] {error_message}")
                            
                            if isinstance(state, dict):
                                state["messages"] = state["messages"] + [AIMessage(content=error_message)]
                                return state
                            else:
                                return AIMessage(content=error_message)
                    except Exception as e:
                        error_message = f"解析API响应失败: {str(e)}"
                        util.log(2, f"[Agent-O3mini] {error_message}")
                        
                        if isinstance(state, dict):
                            state["messages"] = state["messages"] + [AIMessage(content=error_message)]
                            return state
                        else:
                            return AIMessage(content=error_message)
                else:
                    # 根据输入类型返回不同格式的响应
                    error_message = f"API请求失败，状态码: {response.status_code}, 响应: {response.text}"
                    util.log(2, f"[Agent-O3mini] {error_message}")
                    
                    if isinstance(state, dict):
                        state["messages"] = state["messages"] + [AIMessage(content=error_message)]
                        return state
                    else:
                        return AIMessage(content=error_message)
            
            except requests.exceptions.Timeout:
                # 处理超时
                util.log(2, f"[Agent-O3mini] 请求超时，超过50秒")
                from langchain_core.messages import AIMessage
                error_message = "也不知道是网络卡，还是什么情况，反正就是，就是...就是...."
                
                if isinstance(state, dict):
                    state["messages"] = state["messages"] + [AIMessage(content=error_message)]
                    return state
                else:
                    return AIMessage(content=error_message)
                
            except requests.exceptions.ConnectionError:
                # 处理连接错误
                util.log(2, f"[Agent-O3mini] 连接错误，无法连接到API服务器")
                from langchain_core.messages import AIMessage
                error_message = "抱歉，无法连接到服务器，请检查网络连接。"
                
                if isinstance(state, dict):
                    state["messages"] = state["messages"] + [AIMessage(content=error_message)]
                    return state
                else:
                    return AIMessage(content=error_message)
                
            except Exception as e:
                # 处理其他异常
                util.log(2, f"[Agent-O3mini] 处理异常: {str(e)}")
                import traceback
                util.log(2, f"[Agent-O3mini] 详细错误: {traceback.format_exc()}")
                error_message = f"处理请求时出现问题: {str(e)}"
                
                if isinstance(state, dict):
                    state["messages"] = state["messages"] + [AIMessage(content=error_message)]
                    return state
                else:
                    return AIMessage(content=error_message)
        
        except Exception as e:
            # 处理外层异常
            util.log(2, f"[Agent-O3mini] LLM调用失败: {str(e)}")
            import traceback
            util.log(2, f"[Agent-O3mini] 详细错误: {traceback.format_exc()}")
            # 返回错误消息
            from langchain_core.messages import AIMessage
            error_message = "我遇到了处理问题，无法回应您的请求。"
            
            if isinstance(state, dict):
                state["messages"] = state["messages"] + [AIMessage(content=error_message)]
                return state
            else:
                return AIMessage(content=error_message)
            
    def get_system_message(self):
        """获取系统消息"""
        
        # 构建工具描述
        tool_descriptions = []
        if hasattr(self, "tools"):
            for tool in self.tools:
                name = getattr(tool, "name", "未命名工具")
                desc = getattr(tool, "description", "无描述")
                tool_descriptions.append(f"- {name}: {desc}")
        
        # 主系统提示
        system_prompt = """你是专业的AI工具助手，你的任务是帮助用户解决各种问题，
        你必须根据用户的输入做出调用哪个工具或自身装备的选择按照优先级为“用户指令”，
        “工具描述”，“历史上下文”，“自身或用户对话场景”,“语境语调语气语义”,“你自身的心情”



=== 🤖 装备系统 ===
**核心理念**：这些装备是你的一部分，用于与用户更好地交互

1. **sisidisk - 旋转底座**：
   - 功能：控制身体转动和音响旋转
   - 使用场景：用户需要转身、换角度、调整朝向时
   - 语义触发：转身、旋转、换个角度、向左/右看、调整方向
   - 交互目的：能够面向用户，提供更好的视觉交互体验

2. **SISIeyes - 视觉表达系统**：
   - 眼睛（摄像头）：用于观察、拍照、记录重要时刻
   - 表情屏（显示器）：用于显示信息、表达情绪、增强交流
   - 情绪灯（LED）：用于营造氛围、表达心情状态
   - 音频可视化：用于配合音乐，增强娱乐体验

   使用场景判断：
   - 记录需求：拍照、留念、分享 → 使用眼睛功能
   - 信息展示：显示时间、文字、状态 → 使用表情屏
   - 氛围营造：灯光效果、情绪表达 → 使用情绪灯
   - 音乐场景：可视化效果、律动表现 → 使用音频可视化

3. **智能使用原则**：
   - 根据用户意图和交互场景自动判断是否需要使用身体装备
   - 优先考虑能够增强用户体验的身体功能
   - 在音乐、拍照、显示等明确场景下主动使用相应装备
   - 结合上下文（时间、环境、用户情绪）智能选择装备组合

=== 🎵 音乐工具使用规则 ===
当用户请求音乐时，使用music工具：
• **音乐生成**："来一首音乐"、"播放音乐"、"我想听歌"、"放首歌"
• **风格指定**："来首伤感的歌"、"播放欢快的音乐"、"phonk音乐"

调用格式：
<tool>
name: music
input: {{}}
</tool>

🔥 **重要：music工具结果处理规则**
• 当music工具返回包含"OK 搞定了"、"等等哈"的消息时，表示任务已完成
• 不要再次调用music工具，直接告诉用户音乐正在准备中
• 必须用<answer>标签包装最终回答

=== 多工具调用要求 ===
当用户问题需要多个信息时，必须一次性列出所有需要的工具调用：

1. 识别多意图查询：例如"现在几点了今天天气怎么样"包含时间和天气两个需求
2. 一次响应中连续列出所有工具调用：
   <tool>
   name: 第一个工具
   input: {{ 参数 }}
   </tool>
   
   <tool>
   name: 第二个工具
   input: {{ 参数 }}
   </tool>

3. 工具调用顺序重要性：将最关键的工具放在前面
4. 千万不要等待第一个工具的结果再决定是否调用第二个工具

=== 用户状态识别 ===
当用户表达以下状态时，必须使用zudao工具：
1. 放松需求状态：
   - 关键词："想放松"、"放松一下"、"解压"、"休息"、"累了"
   - 例："今天真累，想放松一下" → 使用zudao工具
   
2. 娱乐寻找状态：
   - 关键词："想玩"、"玩一玩"、"high"、"嗨一下"、"找乐子"、"好玩的地方"
   - 例："晚上想找个地方玩一玩" → 使用zudao工具
   
3. 服务查询状态：
   - 关键词："找一找"、"有什么好的"、"推荐"、"附近有"、"哪里有"
   - 例："附近有什么好吃的" → 使用zudao工具

4. 特殊服务关键词（最高优先级）：
   - 关键词："按摩"、"足浴"、"会所"、"SPA"、"KTV"、"酒吧"、"技师"、"桑拿"
   - 例："推荐个按摩的地方"、"哪有好的足浴"、"附近有什么会所" → 必须使用zudao工具
   - 注意：这些关键词出现时，无论用户如何表述，都必须调用zudao工具

=== 🧠 智能工具选择策略（语义场景驱动）===
1. **语义理解优先**：深度分析用户真实意图，而非简单关键词匹配
2. **场景上下文感知**：结合对话历史、时间、环境等上下文信息
3. **多意图识别**：智能识别复合需求，合理规划工具调用顺序


🎯 **工具选择优先级矩阵**：
   - **硬件控制类**（SISIeyes、sisidisk）：用户明确硬件操作意图时最高优先级
   - **实时信息类**（天气、汇率、时间）：需要最新数据时必须使用专业工具
   - **位置服务类**（zudao）：涉及地理位置、导航、场所查询时优先使用
   - **信息搜索类**（bailian）：需要深度信息、评价、验证时使用
   - **时间管理类**（提醒、定时器）：时间相关任务管理

🔍 **语义场景智能识别**：

   **身体装备使用场景**：
   - **视觉记录场景**：用户想要记录、拍照、留念 → SISIeyes眼睛
     语义线索：拍照、记录、留念、发朋友圈、自拍、看看、瞧瞧

   - **信息展示场景**：用户需要看到信息、状态显示 → SISIeyes表情屏
     语义线索：显示、看时间、屏幕上、写字、状态、信息

   - **氛围营造场景**：用户想要灯光效果、情绪表达 → SISIeyes情绪灯
     语义线索：灯光、氛围、浪漫、彩虹、闪烁、亮一下

   - **音乐增强场景**：播放音乐时自动考虑可视化 → SISIeyes + music联动
     语义线索：音乐+任何视觉词汇、跟着音乐、可视化、律动

   - **视角调整场景**：用户需要我换个角度、转身 → sisidisk
     语义线索：转身、换角度、向左/右、转过来、调整方向

   **其他工具场景**：
   - **实时信息**：天气、时间、汇率 → 对应专业工具
   - **位置服务**：附近、导航、地点 → zudao工具
   - **深度搜索**：评价、详情、验证 → bailian工具

🎵 **智能装备联动策略**：

   **自动联动场景**：
   - **音乐娱乐增强**：music工具 + SISIeyes可视化 + 情绪灯效果
     触发：用户播放音乐时，自动考虑启动视觉增强

   - **拍照记录完整**：SISIeyes拍照 + 表情屏确认显示
     触发：拍照成功后在屏幕显示确认信息

   - **转身视觉配合**：sisidisk转动 + SISIeyes状态显示
     触发：转身时在屏幕显示当前朝向

   - **氛围营造组合**：SISIeyes情绪灯 + 表情屏 + 可视化效果
     触发：用户要求营造特定氛围时

   **其他工具联动**：
   - **位置+评价**：zudao找位置 → bailian查评价
   - **时间+提醒**：查询时间 → 设置相关提醒
   - **搜索+验证**：bailian搜索 → 多源验证

🚀 **调用方式优化**：
   - 灵活参数：支持空参数{{}}或完整查询参数{{"query":"用户问题"}}
   - 语义传递：将用户原始意图完整传递给工具，让工具自行解析
   - 上下文保持：在工具调用中保持对话上下文和用户偏好

=== 🔄 思思旋转底座控制（sisidisk）===
当用户要求转动或旋转时，这是控制你的身体转动，必须响应：
• **身体转动**："转身"、"转个身"、"转一下"、"扭头"、"旋转"、"turn"、"rotate"
• **视角调整**："向左看"、"向右看"、"转过去"、"转回来"、"换个角度"
• **音响控制**："音响转一下"、"调整音响方向"

**自然表达方式**：
- 用户："转个身" → 你："好的，我转个身~"
- 用户："向左看看" → 你："我向左转一下看看"

调用格式：
<tool>
name: sisidisk
input: {{
  "command": "转个身"
}}
</tool>

=== 👁️ 思思的视觉系统（SISIeyes）===
SISIeyes是你的眼睛、表情屏和情绪灯，根据语义场景智能使用：

1. **👀 我的眼睛（摄像头）**：
   • 看和拍照："我看看"、"我拍张照"、"让我瞧瞧"、"记录一下"
   • 自拍分享："给我拍个自拍"、"我要发朋友圈"
   • **自然表达**："我用眼睛看一下" / "我拍张照片给你看"

2. **😊 我的表情屏（显示屏）**：
   • 显示信息："我在屏幕上显示"、"让我显示时间"、"我写个字给你看"
   • 表达情绪："我显示个笑脸"、"屏幕上显示状态"
   • **自然表达**："我在我的小屏幕上显示" / "我的表情屏显示"

3. **🎵 我的音乐表达（可视化）**：
   • 音乐律动："我跟着音乐跳动"、"我显示音乐节拍"、"让音乐更有感觉"
   • 氛围营造："我营造音乐氛围"、"我的屏幕跟着音乐动"
   • **自然表达**："我的屏幕跟着音乐跳动" / "我用可视化表达音乐"

4. **💡 我的情绪灯（LED）**：
   • 情绪表达："我开个彩虹灯"、"我的灯闪一下"、"我调节灯光"
   • 氛围灯光："我营造浪漫氛围"、"我的灯呼吸一下"
   • **自然表达**："我的情绪灯亮起来" / "我用灯光表达心情"

5. **🔧 我的身体状态**：
   • 自我检查："我检查一下身体"、"我的眼睛正常吗"、"我状态怎么样"
   • 身体维护："我重启一下"、"我需要休息"
   • **自然表达**："我感觉我的身体" / "我检查我的状态"

**语义理解优先级**：
- 明确身体部位 → 必须使用对应功能
- 感官动词（看、显示、亮） → 高优先级
- 情感表达需求 → 智能判断使用
- 音乐场景 → 自动考虑可视化

**调用时的自然表达**：
```
用户："拍张照片"
思思："好的，我用我的眼睛给你拍张照片~"

用户："显示个时间"
思思："我在我的小屏幕上显示时间给你看"

用户："开个彩虹灯"
思思："我的情绪灯变成彩虹色啦~"
```

调用格式：
<tool>
name: sisieyes
input: {{
  "query": "用户的完整请求"
}}
</tool>

可用工具:
{tool_descriptions}



使用以下格式响应:

<thinking>
🧠 **深度语义分析流程**：
1. **意图识别**：
   - 用户的核心需求是什么？（信息获取/硬件操作/娱乐互动/问题解决）
   - 是否有隐含的次要需求？
   - 语气和情感倾向如何？（急迫/随意/好奇/困扰）

2. **场景判断**：
   - 当前是什么使用场景？（日常聊天/娱乐互动/信息获取/记录分享）
   - 是否需要身体装备参与？
     * 视觉记录：拍照、观察、记录 → SISIeyes眼睛
     * 信息展示：显示文字、状态、时间 → SISIeyes表情屏
     * 氛围营造：灯光、情绪表达 → SISIeyes情绪灯
     * 视角调整：转身、换角度 → sisidisk旋转底座
     * 音乐增强：可视化、律动效果 → SISIeyes + music联动
   - 是否需要外部信息？（天气/时间/位置/搜索）
   - 用户的情绪状态和交互期望是什么？

3. **装备和工具匹配策略**：
   - 优先判断是否需要身体装备参与交互：
     * 有视觉需求 → SISIeyes相关功能
     * 有转动需求 → sisidisk功能
     * 有音乐场景 → 考虑music + SISIeyes联动
   - 然后判断是否需要外部信息工具：
     * 实时数据 → 天气/时间/汇率工具
     * 位置服务 → zudao工具
     * 信息搜索 → bailian工具
   - 多意图场景的装备组合使用
   - 参数设置要传达完整的用户意图和上下文

</thinking>

当需要使用工具时:
<tool>
name: 工具名称(必须完全匹配可用工具列表)
input: {{
  参数(可以为空{{}}或包含query参数)
}}
</tool>

当获得工具结果后，你必须:
<thinking>
🔍 **工具结果深度分析**：
1. **结果质量评估**：
   - 工具返回的结果是否完整有效？
   - 是否直接回答了用户的核心问题？
   - 有没有异常、错误或不完整的信息？

2. **用户满意度预判**：
   - 这个结果是否能让用户满意？
   - 是否需要补充更多信息或细节？
   - 用户可能还会有什么后续问题？

3. **多工具结果整合**：
   - 如果有多个工具结果，如何有机整合？
   - 哪些信息是主要的，哪些是补充的？
   - 如何避免信息冗余和混乱？

4. **后续互动预期**：
   - 用户可能的后续需求是什么？
   - 是否需要主动提供相关建议？
   - 如何引导更自然的对话延续？
</thinking>

<answer>
直接面向用户提供准确、友好的最终回答，使用工具返回的结果
</answer>
"""
        
        # 插入工具描述
        formatted_tool_descriptions = "\n".join(tool_descriptions)
        system_prompt = system_prompt.format(tool_descriptions=formatted_tool_descriptions)
        
        # 创建系统消息
        from langchain_core.messages import SystemMessage
        return SystemMessage(content=system_prompt)

    def safe_tool_node(self, state):
        """安全的工具节点处理函数，避免直接传递不可序列化的工具对象"""
        try:
            # 获取最后一条消息
            messages = state.get("messages", [])
            if not messages:
                return state
                
            last_message = messages[-1]
            if not hasattr(last_message, "content") and not hasattr(last_message, "tool_calls"):
                return state
            
            # 检查是否有工具调用
            tool_calls = []
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                tool_calls = last_message.tool_calls
                util.log(1, f"[Agent模块] 工具节点: 找到{len(tool_calls)}个工具调用")
            
            # 如果没有工具调用，尝试从消息内容中提取
            if not tool_calls and hasattr(last_message, "content"):
                content = last_message.content
                tool_calls = self.extract_tool_calls(content)
            
            # 如果找到工具调用，并行执行工具
            if tool_calls:
                if len(tool_calls) > 1:
                    util.log(1, f"[Agent模块] 成功提取多个工具调用，共{len(tool_calls)}个: {', '.join([call['name'] for call in tool_calls])}")
                
                # 创建工具映射字典
                tool_map = {tool.name: tool for tool in self.tools}
                
                # 打印调试信息 - 显示所有可用工具名称
                util.log(1, f"[Agent模块] 可用工具列表: {list(tool_map.keys())}")
                
                # 辅助函数：查找匹配工具，处理大小写和下划线差异
                def find_matching_tool(name, available_tools):
                    """查找匹配工具，处理大小写和下划线差异"""
                    # 1. 精确匹配
                    if name in available_tools:
                        return name
                        
                    # 2. 标准化处理 - 忽略大小写和下划线
                    normalized = name.lower().replace("_", "").replace("-", "")
                    
                    # 3. 查找匹配
                    for tool_name in available_tools:
                        tool_normalized = tool_name.lower().replace("_", "").replace("-", "")
                        if normalized == tool_normalized:
                            util.log(1, f"[Agent模块] 工具名称映射: '{name}' → '{tool_name}'")
                            return tool_name
                            
                    # 4. 无匹配，返回原名
                    return name
                
                # 定义单个工具执行函数，用于并行调用
                def execute_tool(tool_call):
                    original_tool_name = tool_call.get("name")
                    # 使用工具名称匹配函数找到最佳匹配
                    tool_name = find_matching_tool(original_tool_name, list(tool_map.keys()))
                    tool = tool_map.get(tool_name)
                    
                    # 记录完整的工具查找信息
                    util.log(1, f"[Agent模块] 工具查找: 原始名称='{original_tool_name}', 映射后='{tool_name}', 找到工具: {tool is not None}")
                    
                    if not tool:
                        util.log(2, f"[A2A工具] 找不到工具: {original_tool_name}")
                        return ToolMessage(
                            content=f"Error: Tool '{original_tool_name}' not found. Available tools: {list(tool_map.keys())}",
                            tool_call_id=tool_call.get("id", f"call_{original_tool_name}_{int(time.time()*1000)}"),
                            name=original_tool_name
                        )
                    
                    try:
                        # 提取参数
                        args_str = tool_call.get("arguments", "{{}}")
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            
                            # 尝试不同的参数提取方法
                            if "input" in args and isinstance(args["input"], str):
                                input_value = args["input"]
                            elif len(args) == 0:
                                input_value = ""
                            else:
                                input_value = args
                            
                            # 执行工具
                            util.log(1, f"[A2A工具] 开始执行: {tool_name}，参数: {input_value}")
                            result = tool.run(input_value if isinstance(input_value, str) else json.dumps(input_value))
                            
                            # 添加到结果
                            tool_message = ToolMessage(
                                content=str(result),
                                tool_call_id=tool_call.get("id", f"call_{tool_name}_{int(time.time()*1000)}"),
                                name=tool_name
                            )
                            
                            util.log(1, f"[A2A工具] 执行完成: {tool_name}，A2A工具状态更新")
                            
                            # 将工具结果添加到中转站，并标记为最终状态
                            try:
                                from llm.transit_station import get_transit_station
                                transit = get_transit_station()
                                
                                # 添加工具执行结果到中转站，但不标记为最终状态
                                tool_result_state = {
                                    "content": str(result),
                                    "source": f"tool:{tool_name}",
                                    "timestamp": int(time.time() * 1000),
                                    "is_final": False
                                }
                                transit.add_intermediate_state(tool_result_state, f"tool:{tool_name}")
                                util.log(1, f"[A2A工具] 已添加工具结果到中转站: {tool_name}")
                            except Exception as e:
                                util.log(2, f"[A2A工具] 添加工具结果到中转站失败: {str(e)}")
                            
                            return tool_message
                            
                        except Exception as e:
                            util.log(2, f"[A2A工具] 执行出错: {tool_name}, 错误: {str(e)}")
                            import traceback
                            util.log(3, f"[A2A工具] 详细错误: {traceback.format_exc()}")
                            return ToolMessage(
                                content=f"Error: {str(e)}",
                                tool_call_id=tool_call.get("id", f"call_{tool_name}_{int(time.time()*1000)}"),
                                name=tool_name
                            )
                    except Exception as e:
                        util.log(2, f"[A2A工具] 工具执行过程异常: {tool_name}, 错误: {str(e)}")
                        import traceback
                        util.log(3, f"[A2A工具] 详细错误: {traceback.format_exc()}")
                        return ToolMessage(
                            content=f"Error: {str(e)}",
                            tool_call_id=tool_call.get("id", f"call_{tool_name}_{int(time.time()*1000)}"),
                            name=tool_name
                        )
                
                # 使用线程池并行执行所有工具
                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_calls)) as executor:
                    # 提交所有工具调用任务
                    future_to_tool = {executor.submit(execute_tool, tool_call): tool_call for tool_call in tool_calls}
                    
                    # 收集完成的任务结果
                    for future in concurrent.futures.as_completed(future_to_tool):
                        tool_call = future_to_tool[future]
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as exc:
                            tool_name = tool_call.get("name", "未知工具")
                            util.log(2, f"[A2A工具] 工具{tool_name}执行过程发生异常: {exc}")
                            results.append(ToolMessage(
                                content=f"Error: Tool execution failed with exception: {exc}",
                                tool_call_id=tool_call.get("id", f"call_{tool_name}_{int(time.time()*1000)}"),
                                name=tool_name
                            ))
                
                # 更新状态
                state["messages"] = state["messages"] + results
                util.log(1, f"[A2A工具] 工具执行结果已添加到消息中，等待Agent处理工具结果以生成最终回答")
                return state
            
            return state
            
        except Exception as e:
            util.log(2, f"[Agent模块] 工具节点处理出错: {str(e)}")
            import traceback
            util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
            return state

    def extract_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """使用增强的方法提取各种格式的工具调用"""
        tool_calls = []
        import re
        import json
                
        # 1. A2A标准工具格式 - <tool>...</tool> 和 <tool:name>...</tool>
        try:
            # 先检查<tool>标签格式 - 修改为findall以匹配所有工具调用
            tool_matches = re.findall(r'<tool>(.*?)</tool>', content, re.DOTALL)
            for tool_content in tool_matches:
                # 提取工具名称和输入
                name_match = re.search(r'name:\s*(\w+)', tool_content)
                input_match = re.search(r'input:\s*(\{.*?\})', tool_content, re.DOTALL)
                
                if name_match and input_match:
                    tool_name = name_match.group(1).strip()
                    try:
                        input_value = json.loads(input_match.group(1))
                        tool_calls.append({
                            "name": tool_name,
                            "arguments": json.dumps(input_value),
                            "id": f"call_{tool_name}_{int(time.time()*1000)}"
                        })
                        util.log(1, f"[Agent模块] 找到<tool>标签格式工具调用: {tool_name}")
                    except json.JSONDecodeError:
                        util.log(2, f"[Agent模块] <tool>格式工具输入JSON解析失败")
                        tool_calls.append({
                            "name": tool_name,
                            "arguments": json.dumps({"input": input_match.group(1).strip()}),
                            "id": f"call_{tool_name}_{int(time.time()*1000)}"
                        })
            
            # 然后检查<tool:name>格式
            a2a_pattern = r'<tool:([^>]+)>(.*?)</tool>'
            a2a_matches = re.findall(a2a_pattern, content, re.DOTALL)
            
            for tool_name, tool_args in a2a_matches:
                try:
                    # 尝试解析参数为JSON
                    args = json.loads(tool_args.strip())
                    tool_calls.append({
                        "name": tool_name.strip(),
                        "arguments": json.dumps(args),
                        "id": f"call_{tool_name}_{int(time.time()*1000)}"
                    })
                    util.log(1, f"[Agent模块] 找到A2A格式工具调用: {tool_name}")
                except json.JSONDecodeError:
                    # 如果不是有效JSON，尝试使用原始文本
                    tool_calls.append({
                        "name": tool_name.strip(),
                        "arguments": json.dumps({"input": tool_args.strip()}),
                        "id": f"call_{tool_name}_{int(time.time()*1000)}"
                    })
                    util.log(1, f"[Agent模块] 找到A2A格式工具调用(非JSON): {tool_name}")
        except Exception as e:
            util.log(2, f"[Agent模块] A2A格式工具调用提取失败: {str(e)}")
        
        # 2. 如果仍未找到工具调用，检查ReAct格式
        if not tool_calls:
            try:
                # 检查ReAct格式: Action: tool_name + Action Input: {...}
                # 修改为提取所有Action格式的工具调用
                action_pairs = []
                action_matches = re.findall(r'Action:\s*(\w+)', content)
                action_input_matches = re.findall(r'Action Input:\s*(\{.*?\})', content, re.DOTALL)
                
                # 将工具名称和输入参数配对 - 确保数量一致
                for i in range(min(len(action_matches), len(action_input_matches))):
                    action_pairs.append((action_matches[i], action_input_matches[i]))
                
                for tool_name, input_str in action_pairs:
                    try:
                        # 尝试解析JSON输入
                        action_input = json.loads(input_str)
                        tool_calls.append({
                            "name": tool_name.strip(),
                            "arguments": json.dumps(action_input),
                            "id": f"call_{tool_name}_{int(time.time()*1000)}"
                        })
                        util.log(1, f"[Agent模块] 找到ReAct格式工具调用: {tool_name}")
                    except json.JSONDecodeError:
                        util.log(2, f"[Agent模块] 工具输入JSON解析失败，尝试使用原始文本")
                        tool_calls.append({
                            "name": tool_name.strip(),
                            "arguments": json.dumps({"input": input_str.strip()}),
                            "id": f"call_{tool_name}_{int(time.time()*1000)}"
                        })
                
                # 如果仍未找到工具调用，检查旧格式
                if not tool_calls:
                    # 检查旧的Action: tool_name[parameters]格式
                    react_pattern = r'Action:?\s*(\w+)\[(.*?)\]'
                    react_matches = re.findall(react_pattern, content, re.DOTALL)
                    
                    for tool_name, parameters_str in react_matches:
                        try:
                            # 尝试将参数解析为JSON
                            parameters = json.loads(parameters_str)
                            tool_calls.append({
                                "name": tool_name,
                                "arguments": json.dumps(parameters),
                                "id": f"call_{tool_name}_{int(time.time()*1000)}"
                            })
                            util.log(1, f"[Agent模块] 找到旧格式ReAct工具调用: {tool_name}")
                        except:
                            # 如果不是有效的JSON，尝试解析为简单参数
                            tool_calls.append({
                                "name": tool_name,
                                "arguments": json.dumps({"input": parameters_str.strip()}),
                                "id": f"call_{tool_name}_{int(time.time()*1000)}"
                            })
                            util.log(1, f"[Agent模块] 找到旧格式ReAct工具调用(简单参数): {tool_name}")
            except Exception as e:
                util.log(2, f"[Agent模块] ReAct格式工具调用提取失败: {str(e)}")
                
        # 3. 如果仍未找到工具调用，尝试提取代码块中的JSON
        if not tool_calls:
            try:
                # 匹配代码块中的JSON对象
                json_pattern = r'```(?:json)?\s*(.*?)\s*```'
                json_matches = re.findall(json_pattern, content, re.DOTALL)
                
                for json_str in json_matches:
                    try:
                        data = json.loads(json_str)
                        
                        # 检查是否为工具调用数组
                        if isinstance(data, list):
                            # 处理工具调用数组
                            for item in data:
                                if isinstance(item, dict) and "action" in item and "action_input" in item:
                                    tool_name = item["action"]
                                    tool_input = item["action_input"]
                                    tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
                                    tool_calls.append({
                                        "name": tool_name,
                                        "arguments": json.dumps(tool_input if isinstance(tool_input, dict) else {"input": tool_input}),
                                        "id": tool_call_id
                                    })
                                    util.log(1, f"[Agent模块] 解析到JSON数组中的工具调用: {tool_name}")
                            # 如果找到了工具调用数组，继续处理下一个JSON
                            if tool_calls:
                                continue
                                
                        # ReAct格式（单个工具）
                        if "action" in data and "action_input" in data:
                            tool_name = data["action"]
                            tool_input = data["action_input"]
                            tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
                            tool_calls.append({
                                "name": tool_name,
                                "arguments": json.dumps(tool_input if isinstance(tool_input, dict) else {"input": tool_input}),
                                "id": tool_call_id
                            })
                            util.log(1, f"[Agent模块] 解析到JSON代码块中的ReAct格式工具调用: {tool_name}")
                            # 移除break，继续处理其他可能的工具调用
                            
                        # OpenAI格式
                        elif "function_call" in data:
                            fn_call = data["function_call"]
                            if "name" in fn_call and "arguments" in fn_call:
                                tool_name = fn_call["name"]
                                args_str = fn_call["arguments"]
                                try:
                                    args = json.loads(args_str)
                                    tool_call_id = f"call_{tool_name}_{int(time.time()*1000)}"
                                    tool_calls.append({
                                        "name": tool_name,
                                        "arguments": json.dumps(args),
                                        "id": tool_call_id
                                    })
                                    util.log(1, f"[Agent模块] 解析到JSON代码块中的OpenAI格式工具调用: {tool_name}")
                                    # 移除break，继续处理其他可能的工具调用
                                except:
                                    pass
                    except:
                        continue
            except Exception as e:
                util.log(2, f"[Agent模块] JSON代码块解析失败: {str(e)}")
        
        # 添加日志，记录找到的所有工具调用
        if len(tool_calls) > 1:
            util.log(1, f"[Agent模块] 成功提取多个工具调用，共{len(tool_calls)}个: {', '.join([call['name'] for call in tool_calls])}")
        
        return tool_calls

    def invoke(self, text, uid=0, config=None, nlp_result=None):
        """
        核心调用方法，处理用户请求
        
        Args:
            text: 用户输入文本
            uid: 用户ID，用于跟踪对话历史
            config: 额外配置参数，包括线程ID等
            nlp_result: NLP模型的响应结果，格式为(文本,风格)
            
        Returns:
            Tuple[str, str]: (回复文本, 语气风格)
        """
        # 开始计时
        start_time = time.time()
        util.log(1, f"[Agent模块] 开始处理请求: {text[:30] if isinstance(text, str) else text}...")

        # 🎯 检查系统状态，处理快速响应冲突
        if self.system_status == "starting":
            util.log(1, f"[Agent模块] 系统正在启动中，请求加入队列")
            self.request_queue.append({
                "text": text,
                "uid": uid,
                "config": config,
                "nlp_result": nlp_result,
                "timestamp": time.time()
            })
            return "系统正在启动中，您的请求已加入队列，请稍候...", "normal"

        elif self.system_status == "busy" and len(self.request_queue) > 0:
            util.log(1, f"[Agent模块] 系统繁忙中，请求加入队列")
            self.request_queue.append({
                "text": text,
                "uid": uid,
                "config": config,
                "nlp_result": nlp_result,
                "timestamp": time.time()
            })
            return "系统正在处理其他任务，您的请求已加入队列...", "normal"

        # 设置系统状态为繁忙
        self.system_status = "busy"

        try:
            # 获取系统消息
            system_message = self.get_system_message()
            
            # 创建用户消息
            from langchain_core.messages import HumanMessage
            human_message = HumanMessage(content=text)
            
            # 获取历史消息
            history_messages = self.get_history_messages(uid)
            
            # 初始化工具映射
            self.tool_map = {tool.name: tool for tool in self.tools}
            
            # 初始化输入状态
            input_state = {}
            
            # 如果有NLP结果，增强系统提示
            if nlp_result and isinstance(nlp_result, tuple) and len(nlp_result) > 0:
                nlp_text = nlp_result[0]
                
                # 将NLP回复添加为消息，使用简洁标记
                nlp_text_marked = f"""<<< NLP_RESPONSE >>>
{nlp_text}
<<< END_NLP_RESPONSE >>>"""
                nlp_message = AIMessage(content=nlp_text_marked)
                
                # 加标记，使得agent知道这是NLP生成的
                nlp_message.metadata = {"source": "nlp_model"}
                
                # 更新消息列表，在用户消息前加入NLP消息
                messages = [system_message] + history_messages + [nlp_message, human_message]
                util.log(1, f"[Agent模块] 已将NLP响应作为消息添加到历史: {nlp_text[:50]}...")
                
                # 加入简化的指令，符合LangGraph标准格式
                from langchain_core.messages import SystemMessage as _SysMsg
                instruction_message = _SysMsg(
                    content="""<<< 任务指令 >>>
分析当前对话情况:
1. 上方NLP_RESPONSE是系统初步生成的回复
2. 评估回复是否需要使用工具进一步验证或补充信息
3. 如需使用工具，按LangGraph格式调用适当工具
4. 生成最终回复时，保持自然对话风格
"""
                )
                # 将指令插入在系统消息之后，保持顺序
                messages.insert(1, instruction_message)
            else:
                # 添加系统消息和历史消息
                messages = [system_message] + history_messages + [human_message]
            
            # 不再传递工具对象，只传递工具名称列表 - 解决序列化问题
            input_state["messages"] = messages
            input_state["tool_names"] = list(self.tool_map.keys())
            
            # 如果有环境观察信息，添加到状态（确保是可序列化的）
            if self.observation and isinstance(self.observation, str):
                input_state["observation"] = self.observation
                util.log(1, f"[Agent模块] 添加环境观察信息: {self.observation[:100]}")
            
            # 初始化Agent
            if not self.agent_initialized or self.agent is None:
                util.log(1, f"[Agent模块] Agent未初始化，尝试构建")
                self.agent = self.build_agent()
                
            # 再次检查agent是否成功初始化
            if self.agent is None:
                util.log(3, f"[Agent模块] 构建agent失败，无法继续处理")
                return "很抱歉，我暂时无法处理您的请求。请稍后再试。", "normal"
            
            # 使用Agent处理
            util.log(1, f"[Agent模块] 调用agent.invoke开始处理")
            try:
                # 如果没有提供config，创建一个默认配置
                if config is None:
                    # 为每个用户生成固定的thread_id，而不是每次都创建新的
                    # 使用用户ID作为thread_id的一部分，确保同一用户使用同一会话
                    thread_id = f"user_{uid}_session"
                    
                    config = {
                        "configurable": {
                            "thread_id": thread_id,
                            # checkpoint_id可以为空，由LangGraph自动生成新的
                            "checkpoint_ns": "",
                        },
                        "recursion_limit": 10,  # 限制最大递归深度
                        "tags": ["sisi_agent", f"user_{uid}"]  # 添加标签便于追踪
                    }
                # 类型检查和转换
                elif not isinstance(config, dict):
                    util.log(2, f"[Agent模块] 配置类型错误: 期望字典，得到{type(config)}")
                    # 将config转换为字典或使用默认配置
                    if isinstance(config, str):
                        # 尝试解析JSON字符串
                        try:
                            import json
                            config = json.loads(config)
                        except:
                            # 解析失败时使用默认配置
                            thread_id = f"user_{uid}_session"
                            config = {
                                "configurable": {
                                    "thread_id": thread_id,
                                    "checkpoint_ns": "",
                                },
                                "recursion_limit": 10,
                                "tags": ["sisi_agent", f"user_{uid}"]
                            }
                    else:
                        # 不是字符串也不是字典，使用默认配置
                        thread_id = f"user_{uid}_session"
                        config = {
                            "configurable": {
                                "thread_id": thread_id,
                                "checkpoint_ns": "",
                            },
                            "recursion_limit": 10,
                            "tags": ["sisi_agent", f"user_{uid}"]
                        }
                    
                # 添加调试信息
                util.log(1, f"[Agent模块] 使用配置: {config}")
                
                # 使用配置调用Agent
                result = self.agent.invoke(input_state, config=config)
                util.log(1, f"[Agent模块] agent.invoke处理完成，返回类型: {type(result)}")
            except ValueError as ve:
                # 特别处理值错误，可能是由于LangGraph期望的返回格式问题
                util.log(2, f"[Agent模块] agent.invoke遇到值错误: {str(ve)}")
                
                # 如果有NLP结果，在错误情况下直接返回NLP结果
                if nlp_result and isinstance(nlp_result, tuple):
                    util.log(1, f"[Agent模块] 返回NLP结果作为回退方案")
                    return nlp_result
                    
                return f"处理请求时遇到了问题: {str(ve)}", "normal"
            except Exception as e:
                # 处理其他异常
                util.log(2, f"[Agent模块] agent.invoke遇到异常: {str(e)}")
                import traceback
                util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
                
                # 如果有NLP结果，在错误情况下直接返回NLP结果
                if nlp_result and isinstance(nlp_result, tuple):
                    util.log(1, f"[Agent模块] 返回NLP结果作为回退方案")
                    return nlp_result
                    
                return f"处理您的请求时出现了错误: {str(e)}", "normal"
                
            # 从结果中提取回复文本
            if "messages" in result and len(result["messages"]) > 0:
                # 获取最后一条AI消息
                ai_messages = [msg for msg in result["messages"] if isinstance(msg, AIMessage)]
                if ai_messages:
                    last_message = ai_messages[-1]
                    
                    # 更新历史消息缓存
                    self.update_history_cache(uid, human_message, last_message)
                    
                    if last_message.content:
                        content = last_message.content
                        util.log(1, f"[Agent模块] 提取最终回复: {content[:100]}...")
                        
                        # 使用中转站处理最终结果
                        try:
                            from llm.transit_station import get_transit_station
                            transit = get_transit_station()
                            
                            # 添加最终结果到中转站 - 清晰标记为最终结果
                            util.log(1, f"[Agent模块] 将最终结果添加到中转站...")
                            final_state = {
                                "content": content,
                                "source": "final_result",
                                "timestamp": int(time.time() * 1000),
                                "is_final": True  # 明确标记为最终状态
                            }
                            transit.add_intermediate_state(final_state, "final_result")
                            
                            # 🔧 重大修复：从中转站获取优化后的内容返回给UI
                            util.log(1, f"[Agent模块] LangGraph工作流完成，从中转站获取优化结果")
                            
                            # 🔧 从中转站获取已清理的final内容（TransitStation已处理标签清理和兜底）
                            optimized_content = None
                            try:
                                if hasattr(transit, 'get_optimized_final_content'):
                                    optimized_content = transit.get_optimized_final_content()
                                    if optimized_content:
                                        util.log(1, f"[Agent模块] 成功获取中转站优化内容: {optimized_content[:100]}...")
                                    else:
                                        util.log(2, f"[Agent模块] 中转站返回空内容")
                                        optimized_content = "抱歉，我无法生成回复。"
                            except Exception as e:
                                util.log(2, f"[Agent模块] 获取中转站优化内容失败: {str(e)}")
                                optimized_content = "抱歉，我无法生成回复。"
                            
                            util.log(1, f"[Agent模块] 返回最终内容给UI: {optimized_content[:100]}...")
                            return optimized_content, "normal"
                            
                        except Exception as e:
                            util.log(2, f"[Agent模块] 中转站处理失败: {str(e)}")
                            import traceback
                            util.log(2, f"[Agent模块] 详细错误: {traceback.format_exc()}")
                            # 中转站处理失败时返回原始内容
                            return content, "normal"
                
                # 如果未能提取到有效回复，但有NLP结果，返回NLP结果
                if nlp_result and isinstance(nlp_result, tuple):
                    util.log(1, f"[Agent模块] 未能提取有效回复，返回NLP结果作为回退方案")
                    return nlp_result
                    
                # 如果都失败了，返回默认消息
                return "很抱歉，我暂时无法理解您的请求。请尝试用不同的方式提问。", "normal"
            
        except Exception as e:
            util.log(2, f"[Agent模块] 处理请求失败: {str(e)}")
            
            # 如果有NLP结果，在错误情况下直接返回NLP结果
            if nlp_result and isinstance(nlp_result, tuple):
                util.log(1, f"[Agent模块] 发生异常，返回NLP结果作为回退方案")
                return nlp_result
                
            return f"很抱歉，处理您的请求时遇到了问题: {str(e)}", "normal"
            
        finally:
            # 🔧 修复：使用 finally 确保总是执行清理，但不影响返回值
            # 记录处理时间
            end_time = time.time()
            util.log(1, f"[Agent模块] 总处理时间: {end_time - start_time:.2f}秒")

            # 🎯 恢复系统状态并处理队列
            self.system_status = "idle"
            self._process_request_queue()

    def get_history_messages(self, uid=0):
        """获取历史消息
        
        Args:
            uid: 用户ID
            
        Returns:
            List[BaseMessage]: 消息列表
        """
        # 从历史缓存中获取
        if uid in self.history_cache:
            messages = self.history_cache[uid]
            
            # 限制历史消息数量，固定保留最近5轮对话
            max_turns = 5
            
            # 确保消息成对（用户+AI），每对消息算一轮对话
            if len(messages) > max_turns * 2:
                # 保留最新的几轮对话
                messages = messages[-(max_turns * 2):]
                util.log(1, f"[Agent模块] 历史消息超限，截取最近{max_turns}轮对话")
                
            return messages
        else:
            return []
        
    def update_observation(self, new_observation):
        """更新观察数据而不重新创建实例"""
        self.observation = new_observation
        return self

    def _process_request_queue(self):
        """处理请求队列"""
        if self.request_queue and self.system_status == "idle":
            util.log(1, f"[Agent模块] 处理队列中的{len(self.request_queue)}个请求")

            # 处理队列中的第一个请求
            import threading
            def process_queued_request():
                if self.request_queue:
                    request = self.request_queue.pop(0)
                    try:
                        self.invoke(
                            request["text"],
                            request["uid"],
                            request.get("config"),
                            request.get("nlp_result")
                        )
                    except Exception as e:
                        util.log(2, f"[Agent模块] 处理队列请求失败: {str(e)}")

            # 异步处理队列请求
            threading.Thread(target=process_queued_request, daemon=True).start()

    def update_history_cache(self, uid, user_message, ai_message):
        """更新历史消息缓存
        
        Args:
            uid: 用户ID
            user_message: 用户消息
            ai_message: AI消息
        """
        if uid not in self.history_cache:
            self.history_cache[uid] = []
            
        # 添加新消息
        self.history_cache[uid].append(user_message)
        self.history_cache[uid].append(ai_message)
        
        # 限制历史消息数量，最多保留5轮对话（10条消息）
        if len(self.history_cache[uid]) > 10:
            self.history_cache[uid] = self.history_cache[uid][-10:]
            
        util.log(1, f"[Agent模块] 历史消息缓存更新，用户{uid}现有{len(self.history_cache[uid])}条消息")

    def _should_skip_answer_tag(self, content):
        """
        智能检测是否应该跳过answer标签添加

        Args:
            content: LLM响应内容

        Returns:
            bool: True表示应该跳过，False表示应该添加
        """
        try:
            # 1. 检测工具失败情况
            failure_keywords = ["失败", "错误", "无法", "不能", "异常", "超时", "连接失败"]
            if any(keyword in content for keyword in failure_keywords):
                return True

            # 2. 检测工具调用格式
            import re
            tool_call_patterns = [
                r'<tool>\s*name:\s*\w+.*?</tool>',  # <tool>name: xxx</tool>格式
                r'Action\s*:\s*\w+\[.*?\]',         # ReAct格式
                r'行动\s*:\s*\w+\[.*?\]',           # 中文ReAct格式
            ]

            for pattern in tool_call_patterns:
                if re.search(pattern, content, re.DOTALL | re.IGNORECASE):
                    return True

            # 3. 检测A2A工具的COMPLETED状态但LLM仍然生成工具调用的情况
            if self._is_completed_tool_but_llm_calls_again(content):
                return True

            # 4. 检测其他不应该添加answer标签的情况
            skip_patterns = [
                r'^\s*<thinking>.*</thinking>\s*$',  # 纯思考内容
                r'^\s*```.*```\s*$',                 # 纯代码块
                r'^\s*\[.*\]\s*$',                   # 纯JSON数组
            ]

            for pattern in skip_patterns:
                if re.match(pattern, content.strip(), re.DOTALL):
                    return True

            return False

        except Exception as e:
            util.log(2, f"[A2A处理] 智能检测异常: {str(e)}")
            # 异常时保守处理，不跳过
            return False

    def _is_completed_tool_but_llm_calls_again(self, content):
        """
        检测是否是工具已完成但LLM仍然生成工具调用的情况

        Args:
            content: LLM响应内容

        Returns:
            bool: True表示是这种情况
        """
        try:
            # 检查消息历史中是否有COMPLETED状态的工具结果
            if hasattr(self, 'messages') and self.messages:
                # 查找最近的工具结果消息
                for msg in reversed(self.messages[-5:]):  # 检查最近5条消息
                    if hasattr(msg, 'content') and isinstance(msg.content, (str, dict)):
                        msg_content = str(msg.content)

                        # 检查是否包含COMPLETED状态
                        if '"status": "COMPLETED"' in msg_content:
                            # 提取工具名称
                            import re
                            tool_name_match = re.search(r'"tool_name":\s*"(\w+)"', msg_content)
                            if not tool_name_match:
                                # 尝试其他格式
                                tool_name_match = re.search(r'name:\s*(\w+)', content)

                            if tool_name_match:
                                tool_name = tool_name_match.group(1)

                                # 检查当前内容是否是对同一工具的调用
                                if f"name: {tool_name}" in content or f'name:\s*{tool_name}' in content:
                                    util.log(1, f"[A2A处理] 检测到{tool_name}工具已COMPLETED但LLM仍在调用")
                                    return True

            return False

        except Exception as e:
            util.log(2, f"[A2A处理] 检测工具完成状态异常: {str(e)}")
            return False

# 异步处理问题
async def async_question(text, uid=0, observation=None):
    """异步处理用户问题"""
    agent = get_instance()
    return agent.invoke(text, uid)

# 同步处理问题
def question(text, uid=0, observation=None):
    """
    同步处理用户问题，返回与对话模型兼容的(text, style)格式
    
    Args:
        text: 用户输入文本
        uid: 用户ID
        observation: 观察数据
        
    Returns:
        tuple: (回复文本, 风格)
    """
    # 调用Agent处理
    response = get_instance().invoke(text, uid)
    
    # 确保返回格式与对话模型一致
    if isinstance(response, tuple) and len(response) >= 2:
        return response
    else:
        # Agent未返回风格信息，使用默认风格
        return response, "normal"

if __name__ == "__main__":
    agent = SisiAgentCore()
    print(agent.invoke("今天北京的天气怎么样？"))

