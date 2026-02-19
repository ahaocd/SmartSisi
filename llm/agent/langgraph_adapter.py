"""
LangGraph适配器 - 用于将LangGraph图形接口适配到Sisi系统
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
import threading
from utils import util

# 全局实例
_instance = None
_instance_lock = threading.Lock()

def get_instance():
    """获取LangGraph适配器单例"""
    global _instance
    
    with _instance_lock:
        if _instance is None:
            _instance = LangGraphAdapter()
            util.log(1, f"[LangGraph适配器] 初始化单例实例")
    
    return _instance

class LangGraphAdapter:
    """
    LangGraph适配器，用于管理LangGraph的集成
    提供与Agent工具交互的标准接口
    """
    
    def __init__(self):
        """初始化LangGraph适配器"""
        self.initialized = False
        self.agent = None
        
        # 对接结果缓存，避免重复处理
        self.result_cache = {}
        # 缓存超时时间（秒）
        self.cache_timeout = 300  # 5分钟
        
        # 延迟初始化agent，避免循环导入
        # 注意：我们避免在构造函数中调用_initialize_agent，防止循环引用
        # 初始化将在首次需要时执行
    
    def _initialize_agent(self):
        """延迟初始化Agent，避免循环引用"""
        if not self.initialized:
            try:
                # 使用绝对导入路径避免循环引用
                import importlib
                sisi_agent_module = importlib.import_module("llm.agent.sisi_agent")
                get_agent_instance = getattr(sisi_agent_module, "get_instance")
                
                self.agent = get_agent_instance()
                util.log(1, f"[LangGraphAdapter] Agent初始化成功")
                self.initialized = True
            except Exception as e:
                util.log(3, f"[LangGraphAdapter] Agent初始化失败: {str(e)}")
                self.agent = None
                import traceback
                util.log(3, f"[LangGraphAdapter] 错误详情: {traceback.format_exc()}")

    def process_query(self, text: str, uid: int = 0, session_id: str = None, observation: str = None) -> Dict[str, Any]:
        """
        处理用户查询
        
        Args:
            text: 用户输入文本
            uid: 用户ID
            session_id: 会话ID
            observation: 可选的环境观察信息
            
        Returns:
            Dict: 包含处理结果和元数据的字典
        """
        # 检查缓存
        cache_key = f"{text}:{uid}:{observation}"
        current_time = time.time()
        if cache_key in self.result_cache:
            cached_result, timestamp = self.result_cache[cache_key]
            # 如果缓存未过期，直接返回
            if current_time - timestamp < self.cache_timeout:
                util.log(1, f"[LangGraphAdapter] 使用缓存结果: {cache_key[:30]}...")
                return cached_result
        
        try:
            util.log(1, f"[LangGraphAdapter] 处理查询: {text[:30]}...")
            
            # 确保Agent已初始化
            if not self.initialized:
                self._initialize_agent()
            
            if not self.initialized or self.agent is None:
                return {
                    "success": False,
                    "response": "LangGraph适配器未正确初始化，无法处理请求",
                    "has_tool_calls": False
                }
                
            # 直接调用Agent，让LLM自主决定是否使用工具
            config = {
                "configurable": {
                    "thread_id": f"user_{uid}_session"
                }
            }
            if observation:
                # 直接添加到状态，而不是作为参数传递
                self.agent.update_observation(observation)
            response = self.agent.invoke(text, uid, config=config)
            
            # 格式化结果
            if isinstance(response, tuple) and len(response) >= 1:
                result = {
                    "response": response[0],
                    "has_tool_calls": False,  # 由Agent内部确定
                    "style": response[1] if len(response) > 1 else "normal"
                }
            else:
                result = {
                    "response": str(response),
                    "has_tool_calls": False,
                    "style": "normal"
                }
            
            # 缓存结果
            self.result_cache[cache_key] = (result, current_time)
            
            return result
        except Exception as e:
            util.log(3, f"[LangGraphAdapter] 处理查询时出错: {str(e)}")
            error_result = {
                "response": f"处理查询时出错: {str(e)}",
                "has_tool_calls": False,
                "error": str(e)
            }
            self.result_cache[cache_key] = (error_result, current_time)
            return error_result
    
    def clean_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        # 清理缓存中的过期项
        expired_keys = [
            key for key, (_, timestamp) in self.result_cache.items()
            if current_time - timestamp > self.cache_timeout
        ]
        
        # 删除过期项
        for key in expired_keys:
            del self.result_cache[key]
            
        util.log(1, f"[LangGraphAdapter] 已清理 {len(expired_keys)} 个过期缓存项")

    def should_use_tool_calling(self, text: str) -> bool:
        """
        判断是否应该使用工具调用
        
        使用官方标准的语义理解方式，通过LLM判断是否需要工具
        而不是简单的关键词匹配
        
        Args:
            text: 用户输入文本
            
        Returns:
            bool: 如果应该使用工具调用则返回True，否则返回False
        """
        try:
            # 仅根据显式标记触发（{langgrph}）
            import re
            tag_match = re.search(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}', text or "")
            tag = (tag_match.group(1).lower() if tag_match else "")
            needs_tool = tag == "langgrph"
            util.log(1, f"[LangGraph适配器] tag={tag or 'none'} -> needs_tool={needs_tool}")
            return needs_tool
        except Exception as e:
            util.log(3, f"[LangGraph适配器] 标记解析失败: {str(e)}")
            return False

