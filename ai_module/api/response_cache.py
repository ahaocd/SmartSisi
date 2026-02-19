# 响应缓存模块
"""
响应缓存模块，用于缓存API响应结果，减少重复请求。
"""

import time
import threading
from collections import OrderedDict

class ResponseCache:
    """API响应缓存，使用LRU策略管理缓存项"""
    
    def __init__(self, max_size=100, expiration_time=30):
        """
        初始化响应缓存
        
        Args:
            max_size (int): 缓存最大项数
            expiration_time (int): 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.expiration_time = expiration_time
        self.cache = OrderedDict()
        self.timestamps = {}  # 记录每个缓存项的创建时间
        self.lock = threading.Lock()
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }
    
    def get(self, key):
        """
        获取缓存项
        
        Args:
            key (str): 缓存键
            
        Returns:
            any: 缓存值，如果不存在或已过期则返回None
        """
        with self.lock:
            if key not in self.cache:
                self.metrics["misses"] += 1
                return None
            
            # 检查是否过期
            if time.time() - self.timestamps[key] > self.expiration_time:
                # 删除过期项
                self.cache.pop(key)
                self.timestamps.pop(key)
                self.metrics["misses"] += 1
                self.metrics["evictions"] += 1
                return None
            
            # 移动到末尾（最近使用）
            value = self.cache.pop(key)
            self.cache[key] = value
            self.metrics["hits"] += 1
            return value
    
    def put(self, key, value):
        """
        添加缓存项
        
        Args:
            key (str): 缓存键
            value (any): 缓存值
        """
        with self.lock:
            # 如果已存在，先移除
            if key in self.cache:
                self.cache.pop(key)
            
            # 如果达到最大容量，移除最老的项
            if len(self.cache) >= self.max_size:
                oldest_key, _ = self.cache.popitem(last=False)
                self.timestamps.pop(oldest_key)
                self.metrics["evictions"] += 1
            
            # 添加新项
            self.cache[key] = value
            self.timestamps[key] = time.time()
    
    def set(self, key, value):
        """
        添加缓存项（put方法的别名）
        
        Args:
            key (str): 缓存键
            value (any): 缓存值
        """
        # 直接调用put方法
        self.put(key, value)
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.timestamps.clear()
    
    def get_metrics(self):
        """
        获取缓存指标
        
        Returns:
            dict: 缓存性能指标
        """
        with self.lock:
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.metrics["hits"],
                "misses": self.metrics["misses"],
                "hit_ratio": self.metrics["hits"] / (self.metrics["hits"] + self.metrics["misses"]) if (self.metrics["hits"] + self.metrics["misses"]) > 0 else 0,
                "evictions": self.metrics["evictions"]
            }
