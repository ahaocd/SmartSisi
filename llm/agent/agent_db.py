#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Agent数据库模块 - 用于保存Agent对话历史
"""

import os
import json
import sqlite3
import logging
import importlib
from typing import Dict, Any, Optional, List, Sequence, Tuple
from datetime import datetime
from collections import ChainMap
from langgraph.types import StateSnapshot, CheckpointMetadata
from contextlib import contextmanager


def get_default_db_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_dir = os.path.join(base_dir, "sisi_memory", "data")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "agent_history.db")

def _serialize_message(message):
    """序列化LangChain消息对象"""
    if hasattr(message, 'content') and hasattr(message, '__class__'):
        result = {
            "lc": 1,  # LangChain序列化版本标识
            "type": "constructor",
            "id": [message.__class__.__module__, message.__class__.__name__],
            "kwargs": {
                "content": message.content
            }
        }
        # 添加额外属性
        if hasattr(message, 'additional_kwargs') and message.additional_kwargs:
            result["kwargs"]["additional_kwargs"] = message.additional_kwargs
        if hasattr(message, 'response_metadata') and message.response_metadata:
            result["kwargs"]["response_metadata"] = message.response_metadata
        return result
    return str(message)

def _serialize_state(state):
    """递归序列化状态对象"""
    if state is None:
        return None
        
    if isinstance(state, dict):
        return {k: _serialize_state(v) for k, v in state.items()}
    elif isinstance(state, list):
        return [_serialize_state(item) for item in state]
    # 处理LangChain消息对象
    elif hasattr(state, 'content') and hasattr(state, '__class__'):
        return _serialize_message(state)
    return state

def _serialize_config(config):
    """将配置对象转换为可序列化的字典"""
    if config is None:
        return None
        
    # 处理 ChainMap 对象
    if isinstance(config, ChainMap):
        config = dict(config)
        
    # 递归处理嵌套字典中的 ChainMap
    if isinstance(config, dict):
        return {k: _serialize_config(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_serialize_config(item) for item in config]
    else:
        return config

def _deserialize_message(data):
    """反序列化为LangChain消息对象"""
    if not isinstance(data, dict):
        return data
        
    if data.get("lc") == 1 and data.get("type") == "constructor" and data.get("id"):
        try:
            # 获取模块和类名
            module_parts = data.get("id", [])
            if not module_parts or len(module_parts) < 2:
                return data
                
            module_name = ".".join(module_parts[:-1])
            class_name = module_parts[-1]
            
            # 导入模块
            module = importlib.import_module(module_name)
            # 获取类
            cls = getattr(module, class_name)
            # 实例化对象
            kwargs = data.get("kwargs", {})
            return cls(**kwargs)
        except (ImportError, AttributeError, TypeError) as e:
            logging.warning(f"反序列化消息失败: {e}")
            return data
    return data

def _deserialize_state(state):
    """递归反序列化状态"""
    if state is None:
        return None
        
    if isinstance(state, dict):
        # 检查是否为LangChain消息对象
        if state.get("lc") == 1 and state.get("type") == "constructor":
            return _deserialize_message(state)
        # 常规字典处理
        return {k: _deserialize_state(v) for k, v in state.items()}
    elif isinstance(state, list):
        return [_deserialize_state(item) for item in state]
    return state

class AgentDatabase:
    """Agent数据库管理类"""
    
    def __init__(self, db_path=None):
        """初始化数据库"""
        self.db_path = db_path or get_default_db_path()
        self._init_db()
        
    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建对话历史表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                checkpoint_id TEXT NOT NULL,
                config TEXT,
                state TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(thread_id, checkpoint_id)
            )
            ''')
            
            # 创建会话表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_threads (
                thread_id TEXT PRIMARY KEY,
                user_id TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            conn.commit()
            logging.info(f"Agent数据库初始化完成: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接(使用上下文管理器)"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def persist(self, thread_id: str, checkpoint_id: str, state: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        """保存状态到数据库"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 先更新会话表
                cursor.execute('''
                INSERT OR REPLACE INTO agent_threads 
                (thread_id, last_updated) 
                VALUES (?, ?)
                ''', (thread_id, datetime.now().isoformat()))
                
                # 序列化配置
                serialized_config = json.dumps(_serialize_config(config)) if config else None
                
                # 序列化状态(处理LangChain消息对象)
                serialized_state = json.dumps(_serialize_state(state))
                
                # 保存检查点
                cursor.execute('''
                INSERT OR REPLACE INTO agent_checkpoints 
                (thread_id, checkpoint_id, config, state, timestamp) 
                VALUES (?, ?, ?, ?, ?)
                ''', (
                    thread_id, 
                    checkpoint_id, 
                    serialized_config,
                    serialized_state,
                    datetime.now().isoformat()
                ))
                
                conn.commit()
                logging.debug(f"成功保存检查点: {thread_id}/{checkpoint_id}")
        except Exception as e:
            logging.error(f"保存状态失败: {str(e)}", exc_info=True)
            raise
        
    def get_state(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取状态"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if checkpoint_id:
                    # 获取特定检查点
                    cursor.execute('''
                    SELECT state FROM agent_checkpoints 
                    WHERE thread_id = ? AND checkpoint_id = ?
                    ''', (thread_id, checkpoint_id))
                else:
                    # 获取最新的检查点
                    cursor.execute('''
                    SELECT state FROM agent_checkpoints 
                    WHERE thread_id = ? 
                    ORDER BY timestamp DESC LIMIT 1
                    ''', (thread_id,))
                
                result = cursor.fetchone()
                
                if result:
                    # 反序列化状态(处理LangChain消息对象)
                    state_data = json.loads(result[0])
                    return _deserialize_state(state_data)
                return None
        except Exception as e:
            logging.error(f"获取状态失败: {str(e)}", exc_info=True)
            return None
    
    def list_threads(self, limit: int = 10) -> List[Dict[str, Any]]:
        """列出最近的会话"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                SELECT thread_id, user_id, metadata, created_at, last_updated 
                FROM agent_threads
                ORDER BY last_updated DESC
                LIMIT ?
                ''', (limit,))
                
                threads = []
                for row in cursor.fetchall():
                    threads.append({
                        "thread_id": row[0],
                        "user_id": row[1],
                        "metadata": json.loads(row[2]) if row[2] else {},
                        "created_at": row[3],
                        "last_updated": row[4]
                    })
                
                return threads
        except Exception as e:
            logging.error(f"列出会话失败: {str(e)}", exc_info=True)
            return []
    
    def get_thread_history(self, thread_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取会话历史"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                SELECT checkpoint_id, state, timestamp 
                FROM agent_checkpoints
                WHERE thread_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                ''', (thread_id, limit))
                
                checkpoints = []
                for row in cursor.fetchall():
                    state_data = json.loads(row[1])
                    checkpoints.append({
                        "checkpoint_id": row[0],
                        "state": _deserialize_state(state_data),
                        "timestamp": row[2]
                    })
                
                return checkpoints
        except Exception as e:
            logging.error(f"获取会话历史失败: {str(e)}", exc_info=True)
            return []
    
    def clear_thread(self, thread_id: str):
        """清除会话数据"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM agent_checkpoints WHERE thread_id = ?', (thread_id,))
                cursor.execute('DELETE FROM agent_threads WHERE thread_id = ?', (thread_id,))
                
                conn.commit()
                logging.info(f"成功清除会话: {thread_id}")
        except Exception as e:
            logging.error(f"清除会话失败: {str(e)}", exc_info=True)
            raise

class AgentDatabaseSaver:
    """自定义数据库存储实现"""
    def __init__(self, db_path=None):
        self.db = AgentDatabase(db_path)
        self._version = 0  # 添加版本计数器

    def get_next_version(self, current: Optional[str], channel: Any) -> str:
        """获取下一个版本号
        Args:
            current: 当前版本号
            channel: 通道对象
        Returns:
            str: 下一个版本号
        """
        self._version += 1
        return str(self._version)

    def save(self, thread_id: str, checkpoint_id: str, state: Dict[str, Any]) -> None:
        """保存状态"""
        self.db.persist(thread_id, checkpoint_id, state)

    def load(self, thread_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """加载状态"""
        return self.db.get_state(thread_id, checkpoint_id)

    def list_threads(self) -> List[str]:
        """列出所有会话"""
        return [thread["thread_id"] for thread in self.db.list_threads()]

    def clear_thread(self, thread_id: str) -> None:
        """清除会话数据"""
        self.db.clear_thread(thread_id)

    def put_writes(self, config: Dict[str, Any], writes: Sequence[tuple[str, Any]], task_id: str, task_path: Optional[str] = "") -> None:
        """保存写入操作
        Args:
            config: 配置信息
            writes: 写入操作列表，每个元素为 (channel, value) 对
            task_id: 任务ID
            task_path: 任务路径
        """
        try:
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            checkpoint_id = config.get("configurable", {}).get("checkpoint_id", str(self._version + 1))
            
            # 将写入操作转换为状态
            state = {}
            for key, value in writes:
                state[key] = value
                
            # 保存状态
            self.save(thread_id, checkpoint_id, state)
            logging.debug(f"保存写入操作成功: thread_id={thread_id}, task_id={task_id}")
        except Exception as e:
            logging.error(f"保存写入操作失败: {str(e)}", exc_info=True)
            # 错误发生时不抛出异常，避免中断工作流

    def put(self, config: Dict[str, Any], checkpoint: Dict[str, Any], metadata: Dict[str, Any], channel_versions: Dict[str, str] = None) -> Dict[str, Any]:
        """保存检查点数据
        Args:
            config: 配置信息
            checkpoint: 检查点数据
            metadata: 元数据
            channel_versions: 通道版本信息
        Returns:
            Dict[str, Any]: 更新后的配置信息
        """
        try:
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            checkpoint_id = config.get("configurable", {}).get("checkpoint_id", str(self._version + 1))
            
            # 保存状态
            self.db.persist(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                state=checkpoint.get("channel_values", {}),
                config=config
            )
            
            # 返回更新后的配置
            return {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id
                }
            }
        except Exception as e:
            logging.error(f"保存检查点数据失败: {str(e)}", exc_info=True)
            # 确保返回有效的配置
            return {
                "configurable": {
                    "thread_id": config.get("configurable", {}).get("thread_id", "default"),
                    "checkpoint_id": config.get("configurable", {}).get("checkpoint_id", str(self._version + 1))
                }
            }

    def get_tuple(self, config: Dict[str, Any]) -> Optional[Tuple[StateSnapshot, ...]]:
        """获取状态快照元组"""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        
        state = self.load(thread_id, checkpoint_id)
        if not state:
            return None
            
        # 创建状态快照
        snapshot = StateSnapshot(
            values=state,
            next=(),  # 下一个节点名称
            config=config,
            metadata=CheckpointMetadata(
                version=checkpoint_id or str(self._version + 1),
                parent_version=None,
                created_at=datetime.now().isoformat()
            ),
            created_at=datetime.now().isoformat(),
            parent_config=None,
            tasks=()  # 任务列表
        )
        
        return (snapshot,)

# 单例模式
_instance = None

def get_db_instance(db_path=None):
    """获取数据库单例"""
    global _instance
    if _instance is None:
        _instance = AgentDatabase(db_path)
    return _instance

if __name__ == "__main__":
    # 测试代码
    db = AgentDatabase()
    
    # 保存测试数据
    db.persist(
        thread_id="test_thread_1",
        checkpoint_id="checkpoint_1",
        state={"messages": [{"role": "user", "content": "你好"}]},
        config={"metadata": {"user_id": "test_user"}}
    )
    
    # 读取测试数据
    state = db.get_state("test_thread_1")
    print("读取状态:", state)
    
    # 列出会话
    threads = db.list_threads()
    print("会话列表:", threads) 