"""
异步交互管理器
=============

功能说明：
- 统一管理所有用户输入的异步处理
- 支持智能打断优先级处理
- 提供完整的错误处理和日志记录
- 支持并发输入处理

架构设计：
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   用户输入      │───▶│  异步管理器      │───▶│  SmartSisi核心处理    │
│ (Flask接口)     │    │ (队列+线程池)    │    │ (智能打断+NLP)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘

使用示例：
```python
# 在Flask接口中使用
from core.async_interaction_manager import AsyncInteractionManager

manager = AsyncInteractionManager.get_instance()
success = manager.process_interaction_async(interact, priority="high")
```

测试方法：
```bash
cd SmartSisi
python test_async_interaction.py
```
"""

import threading
import queue
import time
from typing import Optional, Dict, Any
from core.interact import Interact
from utils import util


class AsyncInteractionManager:
    """异步交互管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # 交互队列 - 支持优先级
        self.interaction_queue = queue.PriorityQueue()
        
        # 线程池
        self.worker_threads = []
        self.max_workers = 3  # 最大并发处理数
        self.running = True
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'total_errors': 0,
            'current_processing': 0,
            'queue_size': 0
        }
        
        # 启动工作线程
        self._start_workers()
        
        util.log(1, "[异步管理器] 初始化完成")
    
    @classmethod
    def get_instance(cls) -> 'AsyncInteractionManager':
        """获取单例实例"""
        return cls()
    
    def _start_workers(self):
        """启动工作线程"""
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"AsyncWorker-{i+1}",
                daemon=True
            )
            worker.start()
            self.worker_threads.append(worker)
            util.log(1, f"[异步管理器] 启动工作线程: {worker.name}")
    
    def _worker_loop(self):
        """工作线程主循环"""
        thread_name = threading.current_thread().name
        
        while self.running:
            try:
                # 获取任务 (优先级, 时间戳, 交互对象, 回调函数)
                priority, timestamp, interact, callback = self.interaction_queue.get(timeout=1.0)
                
                # 更新统计
                self.stats['current_processing'] += 1
                self.stats['queue_size'] = self.interaction_queue.qsize()
                
                util.log(1, f"[{thread_name}] 开始处理交互: {interact.data.get('msg', '')[:50]}...")
                
                # 处理交互
                result = self._process_interaction(interact)
                
                # 执行回调
                if callback:
                    try:
                        callback(result, None)
                    except Exception as e:
                        util.log(2, f"[{thread_name}] 回调执行异常: {str(e)}")
                
                # 更新统计
                self.stats['total_processed'] += 1
                self.stats['current_processing'] -= 1
                
                util.log(1, f"[{thread_name}] 交互处理完成")
                
            except queue.Empty:
                continue
            except Exception as e:
                self.stats['total_errors'] += 1
                self.stats['current_processing'] -= 1
                util.log(2, f"[{thread_name}] 工作线程异常: {str(e)}")
    
    def _process_interaction(self, interact: Interact) -> Any:
        """处理单个交互"""
        try:
            # 导入SmartSisi核心 (延迟导入避免循环依赖)
            from core import sisi_booter
            
            # 调用SmartSisi核心处理
            result = sisi_booter.sisi_core.on_interact(interact)
            return result
            
        except Exception as e:
            util.log(2, f"[异步管理器] 交互处理异常: {str(e)}")
            raise
    
    def process_interaction_async(
        self, 
        interact: Interact, 
        priority: str = "normal",
        callback: Optional[callable] = None
    ) -> bool:
        """
        异步处理交互
        
        Args:
            interact: 交互对象
            priority: 优先级 ("high", "normal", "low")
            callback: 完成回调函数 callback(result, error)
        
        Returns:
            bool: 是否成功加入队列
        """
        try:
            # 转换优先级 (数字越小优先级越高)
            priority_map = {
                "high": 1,    # 智能打断等紧急操作
                "normal": 2,  # 普通用户输入
                "low": 3      # 自动播放等后台操作
            }
            
            priority_num = priority_map.get(priority, 2)
            timestamp = time.time()
            
            # 加入队列
            self.interaction_queue.put((priority_num, timestamp, interact, callback))
            
            # 更新统计
            self.stats['queue_size'] = self.interaction_queue.qsize()
            
            util.log(1, f"[异步管理器] 交互已加入队列: 优先级={priority}, 队列大小={self.stats['queue_size']}")
            return True
            
        except Exception as e:
            util.log(2, f"[异步管理器] 加入队列失败: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        self.stats['queue_size'] = self.interaction_queue.qsize()
        return self.stats.copy()
    
    def stop(self):
        """停止管理器"""
        self.running = False
        util.log(1, "[异步管理器] 正在停止...")
        
        # 等待所有任务完成
        while not self.interaction_queue.empty():
            time.sleep(0.1)
        
        util.log(1, "[异步管理器] 已停止")


# 全局实例
_async_manager = None

def get_async_manager() -> AsyncInteractionManager:
    """获取全局异步管理器实例"""
    global _async_manager
    if _async_manager is None:
        _async_manager = AsyncInteractionManager()
    return _async_manager


def process_interaction_async(interact: Interact, priority: str = "normal") -> bool:
    """
    便捷函数：异步处理交互
    
    Args:
        interact: 交互对象
        priority: 优先级 ("high", "normal", "low")
    
    Returns:
        bool: 是否成功
    """
    manager = get_async_manager()
    return manager.process_interaction_async(interact, priority)


def get_interaction_stats() -> Dict[str, Any]:
    """便捷函数：获取处理统计"""
    manager = get_async_manager()
    return manager.get_stats()
