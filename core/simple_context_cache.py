"""
简单的上下文缓存系统（默认保留10段）
用于SISI主交互的对话连贯性，不依赖复杂的记忆系统
"""

import time
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class ContextItem:
    """上下文项"""
    user_input: str
    system_response: str
    timestamp: float
    speaker_id: str

class SimpleContextCache:
    """简单的上下文缓存系统"""
    
    def __init__(self, max_contexts: int = 10):
        """
        初始化上下文缓存
        Args:
            max_contexts: 最大缓存上下文数量，默认10段
        """
        self.max_contexts = max_contexts
        self.contexts: List[ContextItem] = []
        self._lock = None
        
    def add_context(self, user_input: str, system_response: str, speaker_id: str = "user"):
        """
        添加上下文
        Args:
            user_input: 用户输入
            system_response: 系统回复
            speaker_id: 说话人ID
        """
        try:
            context_item = ContextItem(
                user_input=user_input[:100],  # 限制长度
                system_response=system_response[:100],  # 限制长度
                timestamp=time.time(),
                speaker_id=speaker_id
            )
            
            # 添加到列表开头
            self.contexts.insert(0, context_item)
            
            # 保持最大数量限制
            if len(self.contexts) > self.max_contexts:
                self.contexts = self.contexts[:self.max_contexts]
                
            print(f"[上下文缓存] ✅ 已添加上下文，当前缓存: {len(self.contexts)}/{self.max_contexts}")
            
        except Exception as e:
            print(f"[上下文缓存] ❌ 添加上下文失败: {e}")
    
    def get_context_string(self, max_length: int = 200) -> str:
        """
        获取上下文字符串
        Args:
            max_length: 最大长度
        Returns:
            格式化的上下文字符串
        """
        try:
            if not self.contexts:
                return "无相关上下文"
            
            context_parts = []
            current_length = 0
            
            # 获取当前系统模式，做上下文标记，避免跨Agent混淆
            for i, context in enumerate(self.contexts):
                if i >= self.max_contexts:  # 最多按配置段数
                    break
                    
                # 保留语音标记，思思需要知道环境信息
                user_input = context.user_input[:80]
                system_response = context.system_response[:80]

                # 动态获取说话人身份，用于LLM理解参与者
                part = f"{user_input}... {system_response}..."
                
                if current_length + len(part) > max_length:
                    break
                    
                context_parts.append(part)
                current_length += len(part)
            
            if context_parts:
                return " | ".join(context_parts)
            else:
                return "无相关上下文"
                
        except Exception as e:
            print(f"[上下文缓存] ❌ 获取上下文失败: {e}")
            return "上下文获取失败"
    
    def get_recent_context(self) -> Optional[ContextItem]:
        """获取最近的上下文"""
        try:
            if self.contexts:
                return self.contexts[0]
            return None
        except Exception as e:
            print(f"[上下文缓存] ❌ 获取最近上下文失败: {e}")
            return None
    
    def clear_old_contexts(self, max_age_seconds: int = 3600):
        """
        清理过期的上下文
        Args:
            max_age_seconds: 最大保存时间（秒），默认1小时
        """
        try:
            current_time = time.time()
            self.contexts = [
                context for context in self.contexts
                if current_time - context.timestamp < max_age_seconds
            ]
            print(f"[上下文缓存] 🧹 已清理过期上下文，剩余: {len(self.contexts)}")
        except Exception as e:
            print(f"[上下文缓存] ❌ 清理上下文失败: {e}")
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        try:
            if not self.contexts:
                return {"count": 0, "oldest": None, "newest": None}
            
            timestamps = [c.timestamp for c in self.contexts]
            return {
                "count": len(self.contexts),
                "oldest": min(timestamps),
                "newest": max(timestamps),
                "age_range": max(timestamps) - min(timestamps)
            }
        except Exception as e:
            print(f"[上下文缓存] ❌ 获取统计失败: {e}")
            return {"count": 0, "error": str(e)}

# 全局单例
_context_cache_instance = None

def get_simple_context_cache() -> SimpleContextCache:
    """获取简单上下文缓存单例"""
    global _context_cache_instance
    if _context_cache_instance is None:
        _context_cache_instance = SimpleContextCache(max_contexts=10)
        print("[上下文缓存] ✅ 简单上下文缓存初始化完成")
    return _context_cache_instance

def add_interaction_context(user_input: str, system_response: str, speaker_id: str = "user"):
    """便捷函数：添加交互上下文"""
    cache = get_simple_context_cache()
    cache.add_context(user_input, system_response, speaker_id)

def get_context_for_llm() -> str:
    """便捷函数：获取用于LLM的上下文字符串"""
    cache = get_simple_context_cache()
    return cache.get_context_string(max_length=800)
