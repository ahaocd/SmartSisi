"""
AGENTSS - Sisi智能代理系统
提供LangGraph与A2A工具集成的主要入口点
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AGENTSS:
    """AGENTSS - Sisi智能代理系统，集成LangGraph与A2A工具"""
    
    def __init__(self):
        """初始化AGENTSS系统"""
        self.initialized = False
        self.a2a_integration = None
        self.langgraph_adapter = None
        
    async def initialize(self):
        """异步初始化系统组件"""
        if self.initialized:
            return True
        
        try:
            # 先初始化LangGraph适配器，避免循环依赖
            from .langgraph_adapter import get_instance as get_langgraph_adapter
            self.langgraph_adapter = get_langgraph_adapter()
            logger.info("LangGraph适配器初始化成功")
            
            # 然后初始化A2A集成
            from .a2a_integration import get_instance as get_a2a_integration
            self.a2a_integration = get_a2a_integration()
            await self.a2a_integration.initialize()
            logger.info("A2A集成初始化成功")
            
            self.initialized = True
            logger.info("AGENTSS系统初始化完成")
            return True
        except Exception as e:
            logger.error(f"AGENTSS初始化失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def process_query_sync(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """同步处理用户查询"""
        # 创建事件循环并执行异步操作
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            # 确保系统已初始化
            if not self.initialized:
                init_success = loop.run_until_complete(self.initialize())
                if not init_success:
                    return {"error": "系统初始化失败"}
            
            # 尝试使用A2A集成处理
            if self.a2a_integration and self.a2a_integration.initialized:
                result = loop.run_until_complete(self.a2a_integration.process_query(query, session_id))
                return result
            elif self.langgraph_adapter:
                # 如果A2A集成不可用，使用LangGraph适配器处理
                result = self.langgraph_adapter.process_query(query, session_id=session_id)
                return {"response": result.get("response", ""), "status": "completed"}
            else:
                return {"error": "无可用处理组件"}
            
        except Exception as e:
            logger.error(f"处理查询时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}
        finally:
            loop.close()

    async def process_query(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """异步处理用户查询"""
        try:
            # 确保系统已初始化
            if not self.initialized:
                init_success = await self.initialize()
                if not init_success:
                    return {"error": "系统初始化失败"}
            
            # 尝试使用A2A集成处理
            if self.a2a_integration and self.a2a_integration.initialized:
                return await self.a2a_integration.process_query(query, session_id)
            elif self.langgraph_adapter:
                # 如果A2A集成不可用，使用LangGraph适配器处理
                result = self.langgraph_adapter.process_query(query, session_id=session_id)
                return {"response": result.get("response", ""), "status": "completed"}
            else:
                return {"error": "无可用处理组件"}
            
        except Exception as e:
            logger.error(f"处理查询时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}

# 单例实例
_instance = None
_instance_lock = asyncio.Lock()

async def get_instance_async():
    """获取AGENTSS单例(异步)"""
    global _instance
    if _instance is None:
        async with _instance_lock:
            if _instance is None:
                _instance = AGENTSS()
                # 异步初始化
                await _instance.initialize()
    return _instance

def get_instance():
    """获取AGENTSS单例(同步)"""
    global _instance
    if _instance is None:
        _instance = AGENTSS()
        # 注意: 这里不进行同步初始化，避免阻塞
        # 初始化将在首次使用时进行
    return _instance

# 导出便捷函数
def process_query(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """处理查询(同步方法)"""
    return get_instance().process_query_sync(query, session_id)

# 导出异步处理函数
async def aprocess_query(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """处理查询(异步方法)"""
    instance = get_instance()
    if not instance.initialized:
        await instance.initialize()
    return await instance.process_query(query, session_id) 
