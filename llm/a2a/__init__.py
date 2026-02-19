"""
A2A协议模块 - 提供服务端和客户端实现
"""

# 导出常用接口
from .a2a_server import (
    A2AServer,  # 新的服务器类
    AgentCard,
    AgentCapabilities,
    AgentProvider,
    AgentSkill,
    AgentAuthentication
)

# 兼容层 - 为了兼容旧代码
app = None  # 旧版本应用实例，现在由A2AServer内部管理
server = None  # 旧版本服务器实例，现在由A2AServer内部管理

def start_server(host="0.0.0.0", port=8001):
    """启动A2A服务器"""
    global server
    # 创建并启动新的A2AServer实例
    from .a2a_server import create_default_agent_card
    agent_card = create_default_agent_card()
    server = A2AServer(agent_card=agent_card, host=host, port=port)
    server.start()
    return server

# 清理任务现在由A2AServer内部管理
def start_cleanup_task():
    """启动清理任务"""
    # 该函数保留为兼容层，实际清理由A2AServer管理
    pass 