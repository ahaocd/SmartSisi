"""
异步工具调用模块 - 提供高效的工具调用能力
该模块作为一个桥接层，连接现有的Agent系统和直接工具调用
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any, Tuple
from utils import util

# 导入直接工具调用模块
# try:
#     from llm.direct_tools import quick_tool_detection, process_with_tools
#     DIRECT_TOOLS_AVAILABLE = True
# except ImportError:
#     DIRECT_TOOLS_AVAILABLE = False

# 导入Agent模块
try:
    from llm.agent import sisi_agent
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

async def process_message_async(msg: str, uid: int = 0, observation: str = "", timeout: float = 3.5) -> Tuple[str, str]:
    """
    异步处理消息，优先使用直接工具，超时则回退
    
    参数:
        msg: 用户输入消息
        uid: 用户ID
        observation: 观察数据
        timeout: Agent处理超时时间（秒）
        
    返回:
        (处理结果, 语气风格)
    """
    result = None
    style = "gentle"
    
    # 步骤1: 尝试使用直接工具处理
    # if DIRECT_TOOLS_AVAILABLE and quick_tool_detection(msg):
    #     try:
    #         util.log(1, f"[异步处理] 尝试使用直接工具处理: {msg[:30]}...")
    #         start_time = time.time()
    #         
    #         # 设置短超时确保快速响应
    #         tool_result = await asyncio.wait_for(
    #             process_with_tools(msg, uid),
    #             timeout=2.0  # 直接工具应该很快完成
    #         )
    #         
    #         if tool_result:
    #             util.log(1, f"[异步处理] 直接工具处理成功, 耗时: {time.time() - start_time:.2f}秒")
    #             return tool_result, style
    #             
    #         util.log(1, f"[异步处理] 直接工具未能处理，转为Agent处理")
    #     except asyncio.TimeoutError:
    #         util.log(1, f"[异步处理] 直接工具处理超时，转为Agent处理")
    #     except Exception as e:
    #         util.log(1, f"[异步处理] 直接工具处理出错: {str(e)}")
    
    # 步骤2: 尝试使用Agent处理
    if AGENT_AVAILABLE:
        try:
            util.log(1, f"[异步处理] 尝试使用Agent处理: {msg[:30]}...")
            start_time = time.time()
            
            # 创建一个事件循环用于包装同步调用
            loop = asyncio.get_event_loop()
            
            # 使用线程执行器包装同步Agent调用
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                agent_core = sisi_agent.SisiAgentCore()
                agent_future = loop.run_in_executor(
                    executor,
                    agent_core.run,
                    msg, uid
                )
                
                try:
                    # 等待Agent处理，但有超时限制
                    result = await asyncio.wait_for(agent_future, timeout=timeout)
                    util.log(1, f"[异步处理] Agent处理成功, 耗时: {time.time() - start_time:.2f}秒")
                    return result, style
                except asyncio.TimeoutError:
                    util.log(1, f"[异步处理] Agent处理超时(>{timeout}秒)，需要回退")
                    # 不取消Future，让它继续在后台执行
        except Exception as e:
            util.log(1, f"[异步处理] Agent处理出错: {str(e)}")
    
    # 返回None表示需要回退到默认处理
    return None, style

# 同步包装异步调用 - 用于现有代码无需大改
def process_message(msg: str, uid: int = 0, observation: str = "", timeout: float = 3.5) -> Tuple[Optional[str], str]:
    """同步包装异步处理函数"""
    try:
        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # 执行异步处理
        result, style = loop.run_until_complete(
            process_message_async(msg, uid, observation, timeout)
        )
        return result, style
    except Exception as e:
        util.log(1, f"[同步包装] 异步处理出错: {str(e)}")
        return None, "gentle"

# 直接添加必要的简化函数到此文件
def quick_tool_detection(text: str) -> bool:
    """快速检测是否可能是工具请求(简化版，仅作兼容接口)"""
    return False
    
def process_with_tools(text: str, uid: int = 0) -> str:
    """使用工具处理文本请求(简化版，仅作兼容接口)"""
    return None
