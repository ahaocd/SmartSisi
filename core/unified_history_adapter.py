"""
统一历史适配器 - 使用本地 SQLite 数据库存储对话历史。

注意：WebUI/open-webui 已移除，不再依赖 webui/backend/data/webui.db。
"""

import os
import sys
import sqlite3
import json
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

SISI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SISI_ROOT, "data")
SISI_DB_PATH = os.path.join(DATA_DIR, "sisi_history.db")

@dataclass
class UnifiedHistoryItem:
    """统一历史项"""
    user_input: str
    system_response: str
    timestamp: float
    speaker_id: str  # 用户ID（声纹识别/WebUI用户）
    voiceprint_info: Optional[Dict] = None
    chat_id: Optional[str] = None
    # 新增字段
    ai_system: str = "sisi"  # AI系统：sisi 或 liuye
    user_role: str = "user"  # 用户角色：admin/user/stranger
    input_source: str = "voice"  # 输入来源：voice/webui/api

class UnifiedHistoryAdapter:
    """统一历史适配器 - 读写本地 SQLite 数据库"""
    
    _instance = None
    
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.db_path = SISI_DB_PATH
        self._ensure_sisi_table()
        print(f"[统一历史] ✅ 初始化完成，数据库: {self.db_path}")
    
    @classmethod
    def get_instance(cls) -> 'UnifiedHistoryAdapter':
        """获取单例"""
        if cls._instance is None:
            cls._instance = UnifiedHistoryAdapter()
        return cls._instance
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_sisi_table(self):
        """确保SISI专用历史表存在，并升级旧表结构"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sisi_history'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                # 检查并添加缺失的列
                cursor.execute("PRAGMA table_info(sisi_history)")
                existing_columns = {row[1] for row in cursor.fetchall()}
                
                new_columns = [
                    ("speaker_name", "TEXT"),
                    ("user_role", "TEXT DEFAULT 'user'"),
                    ("ai_system", "TEXT DEFAULT 'sisi'"),
                    ("input_source", "TEXT DEFAULT 'voice'"),
                ]
                
                for col_name, col_type in new_columns:
                    if col_name not in existing_columns:
                        try:
                            cursor.execute(f"ALTER TABLE sisi_history ADD COLUMN {col_name} {col_type}")
                            print(f"[统一历史] ✅ 添加新列: {col_name}")
                        except Exception as e:
                            print(f"[统一历史] ⚠️ 添加列{col_name}失败: {e}")
            else:
                # 创建SISI专用历史表（与WebUI chat表并存）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sisi_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_input TEXT NOT NULL,
                        system_response TEXT NOT NULL,
                        speaker_id TEXT DEFAULT 'stranger',
                        speaker_name TEXT,
                        user_role TEXT DEFAULT 'user',
                        ai_system TEXT DEFAULT 'sisi',
                        input_source TEXT DEFAULT 'voice',
                        voiceprint_info TEXT,
                        timestamp REAL NOT NULL,
                        chat_id TEXT,
                        created_at INTEGER DEFAULT (strftime('%s', 'now'))
                    )
                """)
            
            # 创建索引（如果不存在）
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sisi_history_speaker 
                ON sisi_history(speaker_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sisi_history_timestamp 
                ON sisi_history(timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sisi_history_ai_system 
                ON sisi_history(ai_system)
            """)
            
            conn.commit()
            conn.close()
            print("[统一历史] ✅ SISI历史表已就绪")
            
        except Exception as e:
            print(f"[统一历史] ❌ 创建表失败: {e}")
    
    def add_interaction(
        self, 
        user_input: str, 
        system_response: str, 
        speaker_id: str = "stranger",
        voiceprint_info: Optional[Dict] = None,
        chat_id: Optional[str] = None,
        ai_system: str = "sisi",
        user_role: str = "user",
        input_source: str = "voice",
        speaker_name: Optional[str] = None
    ) -> bool:
        """
        添加交互记录到统一历史
        
        Args:
            user_input: 用户输入
            system_response: 系统回复
            speaker_id: 说话人ID（声纹识别的用户ID）
            voiceprint_info: 声纹信息（可选）
            chat_id: WebUI的chat_id（可选）
            ai_system: AI系统标识 - "sisi" 或 "liuye"
            user_role: 用户角色 - "admin"/"user"/"stranger"
            input_source: 输入来源 - "voice"/"webui"/"api"
            speaker_name: 说话人名字（如"碧潭飘雪"）
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            voiceprint_json = json.dumps(voiceprint_info, ensure_ascii=False) if voiceprint_info else None
            
            # 从voiceprint_info提取名字
            if not speaker_name and voiceprint_info:
                speaker_name = voiceprint_info.get('real_name') or voiceprint_info.get('name')
            
            cursor.execute("""
                INSERT INTO sisi_history 
                (user_input, system_response, speaker_id, speaker_name, user_role, 
                 ai_system, input_source, voiceprint_info, timestamp, chat_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_input[:500],
                system_response[:500],
                speaker_id,
                speaker_name,
                user_role,
                ai_system,
                input_source,
                voiceprint_json,
                time.time(),
                chat_id
            ))
            
            conn.commit()
            conn.close()
            
            # 更清晰的日志
            name_display = speaker_name or speaker_id
            print(f"[统一历史] ✅ [{ai_system}] {name_display}({user_role}): {user_input[:30]}...")
            return True
            
        except Exception as e:
            print(f"[统一历史] ❌ 添加失败: {e}")
            return False
    
    def get_recent_history(
        self, 
        speaker_id: Optional[str] = None, 
        limit: int = 10,
        ai_system: Optional[str] = None
    ) -> List[UnifiedHistoryItem]:
        """
        获取最近的历史记录
        
        Args:
            speaker_id: 可选，按说话人过滤
            limit: 返回数量限制
            ai_system: 可选，按AI系统过滤（sisi/liuye）
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 构建查询
            query = """
                SELECT user_input, system_response, timestamp, speaker_id, 
                       voiceprint_info, chat_id, ai_system, user_role, input_source,
                       speaker_name
                FROM sisi_history
                WHERE 1=1
            """
            params = []
            
            if speaker_id:
                query += " AND speaker_id = ?"
                params.append(speaker_id)
            
            if ai_system:
                query += " AND ai_system = ?"
                params.append(ai_system)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            items = []
            for row in rows:
                voiceprint = json.loads(row['voiceprint_info']) if row['voiceprint_info'] else None
                item = UnifiedHistoryItem(
                    user_input=row['user_input'],
                    system_response=row['system_response'],
                    timestamp=row['timestamp'],
                    speaker_id=row['speaker_id'],
                    voiceprint_info=voiceprint,
                    chat_id=row['chat_id'] if 'chat_id' in row.keys() else None,
                    ai_system=row['ai_system'] if 'ai_system' in row.keys() else 'sisi',
                    user_role=row['user_role'] if 'user_role' in row.keys() else 'user',
                    input_source=row['input_source'] if 'input_source' in row.keys() else 'voice'
                )
                items.append(item)
            
            return items
            
        except Exception as e:
            print(f"[统一历史] ❌ 获取历史失败: {e}")
            return []
    
    def get_context_for_llm(self, speaker_id: Optional[str] = None, max_items: int = 5, ai_system: Optional[str] = None) -> str:
        """
        获取用于LLM的上下文字符串
        格式清晰标注：谁说的、AI是谁回复的
        
        Args:
            speaker_id: 可选，按说话人过滤
            max_items: 最大条目数
            ai_system: 可选，按AI系统过滤
        """
        try:
            # 获取当前系统模式
            current_ai = ai_system
            if not current_ai:
                try:
                    from llm.liusisi import get_current_system_mode
                    current_ai = get_current_system_mode()
                except:
                    current_ai = "sisi"
            
            items = self.get_recent_history(speaker_id, max_items, ai_system=None)  # 获取所有系统的历史
            
            if not items:
                return "无相关上下文"
            
            # 反转顺序，让最早的在前面
            items = list(reversed(items))
            
            context_parts = []
            for i, item in enumerate(items):
                # 确定用户显示名
                if hasattr(item, 'voiceprint_info') and item.voiceprint_info:
                    user_name = item.voiceprint_info.get('real_name') or item.speaker_id
                else:
                    user_name = item.speaker_id
                
                # 用户角色标注
                role_tag = ""
                if hasattr(item, 'user_role'):
                    if item.user_role == "admin":
                        role_tag = "[管理员]"
                    elif item.user_role == "stranger":
                        role_tag = "[陌生人]"
                
                # AI系统标注
                ai_name = "思思" if item.ai_system == "sisi" else "柳叶"
                
                # 输入来源
                source_tag = ""
                if hasattr(item, 'input_source') and item.input_source == "webui":
                    source_tag = "[WebUI]"
                
                user_text = item.user_input[:60]
                response_text = item.system_response[:60]
                
                context_parts.append(f"{user_text}... {response_text}...")
            
            return " | ".join(context_parts)
            
        except Exception as e:
            print(f"[统一历史] ❌ 获取LLM上下文失败: {e}")
            return "上下文获取失败"
    
    def get_history_count(self, speaker_id: Optional[str] = None) -> int:
        """获取历史记录数量"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if speaker_id:
                cursor.execute(
                    "SELECT COUNT(*) FROM sisi_history WHERE speaker_id = ?", 
                    (speaker_id,)
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM sisi_history")
            
            count = cursor.fetchone()[0]
            conn.close()
            return count
            
        except Exception as e:
            print(f"[统一历史] ❌ 获取数量失败: {e}")
            return 0
    
    def clear_old_history(self, max_age_hours: int = 24 * 7):
        """清理过期历史（默认保留7天）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cutoff_time = time.time() - (max_age_hours * 3600)
            cursor.execute(
                "DELETE FROM sisi_history WHERE timestamp < ?",
                (cutoff_time,)
            )
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            print(f"[统一历史] 🧹 已清理 {deleted} 条过期记录")
            return deleted
            
        except Exception as e:
            print(f"[统一历史] ❌ 清理失败: {e}")
            return 0


# ========== 兼容性接口（替代simple_context_cache） ==========

_adapter_instance = None

def get_unified_history_adapter() -> UnifiedHistoryAdapter:
    """获取统一历史适配器单例"""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = UnifiedHistoryAdapter()
    return _adapter_instance

def add_interaction_context(
    user_input: str, 
    system_response: str, 
    speaker_id: str = "stranger",
    voiceprint_info: Optional[Dict] = None,
    ai_system: str = "sisi",
    user_role: str = "user",
    input_source: str = "voice",
    speaker_name: Optional[str] = None
):
    """
    兼容接口：添加交互上下文
    替代 simple_context_cache.add_interaction_context
    
    Args:
        user_input: 用户输入
        system_response: AI回复
        speaker_id: 用户ID
        voiceprint_info: 声纹信息
        ai_system: AI系统 - "sisi" 或 "liuye"
        user_role: 用户角色 - "admin"/"user"/"stranger"
        input_source: 来源 - "voice"/"webui"/"api"
        speaker_name: 用户名字
    """
    adapter = get_unified_history_adapter()
    adapter.add_interaction(
        user_input, system_response, speaker_id, voiceprint_info,
        ai_system=ai_system, user_role=user_role, 
        input_source=input_source, speaker_name=speaker_name
    )

def get_context_for_llm(speaker_id: Optional[str] = None, ai_system: Optional[str] = None) -> str:
    """
    兼容接口：获取用于LLM的上下文
    替代 simple_context_cache.get_context_for_llm
    """
    adapter = get_unified_history_adapter()
    return adapter.get_context_for_llm(speaker_id, ai_system=ai_system)

# 额外的兼容函数
def get_simple_context_cache():
    """兼容接口：返回适配器实例（模拟SimpleContextCache）"""
    return get_unified_history_adapter()
