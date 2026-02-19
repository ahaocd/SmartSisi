"""
共享状态模块,用于存储全局状态变量,避免循环导入
"""
import threading
from typing import Any, Dict
from collections import defaultdict

# 状态锁
auto_play_lock = threading.Lock()
agent_lock = threading.Lock()  # Agent状态锁

# 状态标志
can_auto_play = True
is_auto_playing = False

# Agent状态管理
agent_states: Dict[str, Any] = defaultdict(lambda: None)
agent_metrics = {
    "processing_time": [],  # 处理时间记录
    "success_count": 0,     # 成功处理次数
    "error_count": 0,       # 错误次数
    "timeout_count": 0      # 超时次数
}

# 全局状态
global_lock = threading.Lock()  # 用于需要同时控制多个状态的情况

def set_agent_state(key: str, value: Any) -> None:
    """设置Agent状态
    
    Args:
        key: 状态键名
        value: 状态值
    """
    with agent_lock:
        agent_states[key] = value
        
        # 更新指标
        if key == "error":
            agent_metrics["error_count"] += 1
        elif key == "timeout":
            agent_metrics["timeout_count"] += 1
        elif key == "success":
            agent_metrics["success_count"] += 1
            
def get_agent_state(key: str) -> Any:
    """获取Agent状态
    
    Args:
        key: 状态键名
        
    Returns:
        状态值
    """
    with agent_lock:
        return agent_states.get(key)
        
def clear_agent_state(key: str = None) -> None:
    """清除Agent状态
    
    Args:
        key: 要清除的状态键名，如果为None则清除所有状态
    """
    with agent_lock:
        if key:
            agent_states.pop(key, None)
        else:
            agent_states.clear()
            
def record_processing_time(time_ms: float) -> None:
    """记录处理时间
    
    Args:
        time_ms: 处理时间（毫秒）
    """
    with agent_lock:
        agent_metrics["processing_time"].append(time_ms)
        # 只保留最近100条记录
        if len(agent_metrics["processing_time"]) > 100:
            agent_metrics["processing_time"].pop(0)
            
def get_agent_metrics() -> Dict[str, Any]:
    """获取Agent性能指标
    
    Returns:
        包含各项指标的字典
    """
    with agent_lock:
        metrics = agent_metrics.copy()
        # 计算平均处理时间
        if metrics["processing_time"]:
            metrics["avg_processing_time"] = sum(metrics["processing_time"]) / len(metrics["processing_time"])
        else:
            metrics["avg_processing_time"] = 0
        return metrics
