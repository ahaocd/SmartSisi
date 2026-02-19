"""
Sisi LLM agent模块
"""

# 按照依赖顺序导入，避免循环引用
# 1. 首先导入Task Manager
from .a2a_task_manager import A2ATaskManager, get_instance as get_task_manager

# 2. 然后导入LangGraph适配器
from .langgraph_adapter import LangGraphAdapter, get_instance as get_langgraph_adapter

# 3. 接着导入A2A适配器工具
from .a2a_adapter import A2ATool, A2AToolNode, create_a2a_tools

# 4. 最后导入A2A集成
from .a2a_integration import A2ALangGraphIntegration, get_instance as get_a2a_integration

# 导出agentss模块（核心功能模块）
try:
    from .agentss import AGENTSS, get_instance as get_agentss
except ImportError:
    import logging
    logging.error("无法导入agentss模块，请检查模块是否存在")

# 为向后兼容提供别名
agentss = None

