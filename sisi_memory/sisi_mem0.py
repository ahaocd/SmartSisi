#!/usr/bin/env python3
"""
🧠 Sisi记忆系统 - 基于Mem0 
功能：
- 用户级记忆：个人偏好、习惯
- 会话级记忆：对话上下文  
- 智能体记忆：学习模式

为您的三个模块提供记忆支持：
- 快速响应模块
- 优化站
- 订阅站
"""

import os
import sys
import json
import time
import logging
import threading
import requests
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

# 设置日志
def setup_sisi_memory_logger():
    logger = logging.getLogger('sisi_memory')
    logger.setLevel(logging.INFO)
    
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    handler = logging.FileHandler(log_dir / "sisi_memory.log", encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [Sisi记忆] %(message)s')
    handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger

sisi_memory_logger = setup_sisi_memory_logger()

# 🌍 定位和天气缓存机制 - 1小时缓存
_location_cache = {}
_weather_cache = {}
CACHE_DURATION = 3600  # 1小时 = 3600秒
TENCENT_MAP_KEY = "JNLBZ-Q3TKQ-OEG54-2WPCV-U4AOK-RSFWT"

def _is_cache_valid(cache_time: float) -> bool:
    """检查缓存是否有效（1小时内）"""
    return time.time() - cache_time < CACHE_DURATION

def _get_location_info() -> Dict[str, Any]:
    """获取当前位置信息（带缓存）"""
    cache_key = "current_location"

    # 检查缓存
    if cache_key in _location_cache:
        cache_data, cache_time = _location_cache[cache_key]
        if _is_cache_valid(cache_time):
            return cache_data

    try:
        # 调用腾讯地图API获取位置
        url = "https://apis.map.qq.com/ws/location/v1/ip"
        params = {"key": TENCENT_MAP_KEY}

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == 0:
            result = data.get("result", {})
            location = result.get("location", {})
            ad_info = result.get("ad_info", {})

            location_info = {
                "country": ad_info.get("nation", "中国"),
                "region": ad_info.get("province", ""),
                "city": ad_info.get("city", ""),
                "district": ad_info.get("district", ""),
                "lat": location.get("lat", 0),
                "lon": location.get("lng", 0)
            }

            # 存储到缓存
            _location_cache[cache_key] = (location_info, time.time())
            return location_info
        else:
            return {"city": "未知位置", "region": "", "country": "中国"}

    except Exception as e:
        sisi_memory_logger.error(f"获取位置信息失败: {e}")
        return {"city": "未知位置", "region": "", "country": "中国"}

def _get_weather_info(city: str) -> str:
    """获取天气信息（带缓存）"""
    cache_key = f"weather_{city}"

    # 检查缓存
    if cache_key in _weather_cache:
        cache_data, cache_time = _weather_cache[cache_key]
        if _is_cache_valid(cache_time):
            return cache_data

    try:
        # 简化的天气信息
        weather_info = "晴朗"  # 默认天气

        # 存储到缓存
        _weather_cache[cache_key] = (weather_info, time.time())
        return weather_info

    except Exception as e:
        sisi_memory_logger.error(f"获取天气信息失败: {e}")
        return "未知天气"

class SisiMemorySystem:
    """🧠 Sisi记忆系统 - 基于Mem0 - 真正的单例模式"""

    _instance = None
    _initialized = False
    _lock = threading.Lock()

    def __new__(cls):
        """确保只创建一个实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # 双重检查锁定
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """只初始化一次 - 防止重复初始化"""
        if not SisiMemorySystem._initialized:
            with SisiMemorySystem._lock:
                if not SisiMemorySystem._initialized:  # 双重检查锁定
                    sisi_memory_logger.info("🔄 开始初始化Sisi记忆系统（单例模式）")
                    self.mem0_client = None
                    self.config = self._load_config()
                    self._initialize_mem0()
                    SisiMemorySystem._initialized = True
                    sisi_memory_logger.info("🧠 Sisi记忆系统初始化完成（单例模式）")
        else:
            sisi_memory_logger.info("♻️ 复用已初始化的Sisi记忆系统实例")
    
    def _load_config(self) -> Dict:
        """基于官方文档的正确配置加载 - 使用前脑系统配置"""
        import os
        import configparser

        # 读取前脑系统配置
        config_parser = configparser.ConfigParser()
        config_parser.read("system.conf", encoding='utf-8')

        # 直接读取配置文件（只使用 memory_llm_*）
        memory_api_key = config_parser.get('key', 'memory_llm_api_key', fallback='').strip()
        memory_base_url = config_parser.get('key', 'memory_llm_base_url', fallback='').strip()
        memory_model = config_parser.get('key', 'memory_llm_model', fallback='').strip()

        if not memory_api_key or not memory_base_url or not memory_model:
            raise RuntimeError("Missing memory_llm_* in system.conf")

        # 设置API密钥到环境变量 (官方文档要求)
        os.environ["OPENAI_API_KEY"] = memory_api_key

        # 配置mem0使用本地存储，与现有sisi.db协同工作
        config = {
            "vector_store": {
                "provider": "chroma",  # 使用本地Chroma向量数据库
                "config": {
                    "collection_name": "sisi_memories",
                    "path": str(Path(__file__).parent / "data" / "chroma_db")
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": memory_api_key,
                    "model": memory_model,
                    "temperature": 0.1,
                    "openai_base_url": memory_base_url
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "api_key": memory_api_key,
                    "model": config_parser.get('key', 'memory_embedding_model', fallback='BAAI/bge-large-zh-v1.5'),
                    "openai_base_url": memory_base_url
                }
            },
            "history_db_path": str(Path(__file__).parent / "data" / "sisi_memory_history.db"),
            "version": "v1.1",
            # 🕐 时区配置 - 使用中国时区
            "timezone": "Asia/Shanghai",
            # 🎯 自定义事实提取提示词 - 专为SISI系统设计
            "custom_fact_extraction_prompt": """你是SISI智能记忆系统组件，管理碧潭飘雪与AI助手（柳思思/柳叶）的对话记忆。

## 身份与参与者
- 用户：使用 speaker_id 标识（可含真实姓名，若未知则保留 speaker_id）
- Agent：可能是 柳思思 或 柳叶（用 mode 标注）
- 环境：前脑系统（音频/环境/音乐检测）

## 记忆提取目标（避免臆测）
仅在原文“明确表达或可验证”时记录事实；不凭空生成具体时间/地点/关系。对不确定信息用“未确认”标注或跳过。
## 记忆提取任务
从对话中提取关键信息，必须保留：
1. **说话人身份** - 可能的角色关系
2. **具体对话内容** - 原始语句和话题表达
3. **重要事实** - 个人信息、偏好、计划、状态变化
4. **时间上下文** - 对话发生的可能的时间和场景

5. **环境信息** - 可能的音频环境、音乐、背景声音

必须保留：
1. 说话人（speaker）与 Agent 模式（mode）
2. 原话要点（尽量引用，不要改变语义）
3. 重要事实（偏好/计划/状态变化），附置信度(0~1)与可验证性
4. 时间上下文（使用系统时间戳；未明确给出具体日期时，不生成具体日期断言）
5. 情感/环境（仅当对话中有直接线索）

## 严格规则
- 不臆造精确日期/地点/人物关系；无依据则标注“未确认”或省略。
- 若出现口误/更正，以最新陈述为准，并说明“更正”。
- 对“玩笑/夸张/假设”，标注为“语气/假设”，不当作事实。
- 输出简洁、可检索，避免文学化长段。

## 输出格式（facts为数组）
每条 fact 建议包含：time、speaker、mode、content、emotion/env(可选)、confidence、verifiable

{"facts": [
  "[time][speaker=user1][mode=sisi][content=\"我喜欢喝咖啡\"（原话）][confidence=0.9][verifiable=true]",
  "[time][speaker=user1][mode=liuye][content=\"我想周末去爬山\"（计划，未确认）][confidence=0.6][verifiable=false]"
]}

## 示例
输入: "张三：我都失业了，你不知道吗"
输出: {"facts": ["[time][speaker=张三][mode=sisi][content=\"我都失业了\"（原话）][confidence=0.9][verifiable=true]"]}

输入: "系统环境感知: 安静环境，置信度0.8"
输出: {"facts": ["[time][speaker=system][mode=sisi][content=\"安静环境\"（感知）][confidence=0.8][verifiable=false]"]}
""",
            # 🔄 自定义记忆更新提示词 - 智能合并相似记忆
            "custom_update_memory_prompt": """你是SISI记忆更新管理器，负责决定如何处理新的记忆信息。

## 更新策略
1. **ADD** - 添加全新的记忆信息
2. **UPDATE** - 更新现有记忆的内容
3. **DELETE** - 删除过时或错误的记忆
4. **NONE** - 不做任何操作

## 判断规则
- 相同身份的相似对话内容 → UPDATE
- 完全不同的新信息 → ADD
- 明确纠正错误信息 → UPDATE或DELETE
- 重复的相同信息 → NONE
- 状态变化信息 → UPDATE (如：失业→就业)

## 身份一致性
- 碧潭飘雪 = user1 = 主用户
- 柳思思 = AI助手
- 系统环境感知 = 环境数据

## 输出格式
{{"action": "ADD/UPDATE/DELETE/NONE", "reason": "操作原因"}}
"""
        }

        # ✅ 强制收紧 Mem0 抽取/更新提示词（减少 Invalid JSON + 降低“复述型垃圾记忆”）
        # 说明：这里覆盖上面历史遗留的长 prompt，避免大改动导致冲突。
        config["custom_fact_extraction_prompt"] = (
            "你是 SISI 的长期记忆抽取器。\n"
            "只允许输出严格 JSON，禁止输出任何额外文字/解释/Markdown。\n\n"
            "只抽取两类长期记忆：\n"
            "- fact：稳定偏好/约束/身份/计划/纠错（可长期复用）\n"
            "- episode：重要事件（低频，非偏好）\n\n"
            "严格禁止：寒暄/客套/安慰；逐句复述或“我们刚才聊了……”这种二次转述；推测/脑补/编造。\n\n"
            "输出格式（没有就返回空数组）：\n"
            "{\"facts\":[\"...\", ...]}\n\n"
            "每条必须遵守模板（必须包含 kind）：\n"
            "[kind=fact|episode][speaker=...][mode=sisi|liuye]"
            "[content=\"...\"][confidence=0.0-1.0][verifiable=true|false]\n\n"
            "规则：最多 6 条；content <= 120 字；纠错/禁令/约束必须作为 kind=fact。"
        )
        config["custom_update_memory_prompt"] = (
            "你是 SISI 的记忆更新决策器。\n"
            "只允许输出严格 JSON，禁止输出任何额外文字。\n\n"
            "目标：减少“垃圾记忆”，优先维护稳定事实（fact）。\n"
            "原则：寒暄/客套/逐句复述→NONE；纠错/禁令/稳定偏好变化→UPDATE；明显重复→NONE；一次性重要事件→ADD。\n\n"
            "输出格式：\n"
            "{\"action\":\"ADD|UPDATE|DELETE|NONE\",\"reason\":\"...\"}"
        )

        # 确保目录存在 - 统一使用sisi_memory目录下的data子目录
        memory_data_dir = Path(__file__).parent / "data"
        memory_data_dir.mkdir(exist_ok=True)

        chroma_db_dir = memory_data_dir / "chroma_db"
        chroma_db_dir.mkdir(exist_ok=True)

        sisi_memory_logger.info(f"✅ mem0配置加载成功 - 使用本地Chroma向量数据库")
        sisi_memory_logger.info(f"📁 向量数据库路径: {chroma_db_dir}")
        sisi_memory_logger.info(f"📁 历史数据库路径: {config['history_db_path']}")
        return config
    
    def _initialize_mem0(self):
        """基于官方文档的正确初始化 - 防止重复初始化"""
        if self.mem0_client is not None:
            sisi_memory_logger.info("♻️ Mem0客户端已存在，跳过重复初始化")
            return

        try:
            # 🔥 强制使用项目中的mem0，不是系统安装的mem0
            import sys
            from pathlib import Path

            # 添加项目mem0路径到sys.path最前面
            mem0_path = str(Path(__file__).parent / "mem0")
            if mem0_path not in sys.path:
                sys.path.insert(0, mem0_path)
                sisi_memory_logger.info(f"✅ 添加项目mem0路径: {mem0_path}")

            from mem0 import Memory

            sisi_memory_logger.info("🔄 正在创建Mem0客户端（使用项目mem0）...")

            # 使用兼容的初始化方式，避免 @runtime_checkable 错误
            if self.config:
                try:
                    # 使用自定义配置
                    self.mem0_client = Memory.from_config(self.config)
                    sisi_memory_logger.info("✅ Mem0客户端初始化成功（自定义配置）")
                except Exception as config_error:
                    sisi_memory_logger.warning(f"⚠️ 自定义配置失败，尝试简化配置: {config_error}")
                    try:
                        # 使用简化配置，只保留向量数据库
                        simple_config = {
                            "vector_store": {
                                "provider": "chroma",
                                "config": {
                                    "collection_name": "sisi_memories",
                                    "path": str(Path(__file__).parent / "data" / "chroma_db")
                                }
                            }
                        }
                        self.mem0_client = Memory.from_config(simple_config)
                        sisi_memory_logger.info("✅ Mem0客户端初始化成功（简化配置）")
                    except Exception as simple_error:
                        sisi_memory_logger.warning(f"⚠️ 简化配置也失败，使用默认配置: {simple_error}")
                        # 最后尝试默认配置
                        self.mem0_client = Memory()
                        sisi_memory_logger.info("✅ Mem0客户端初始化成功（默认配置）")
            else:
                # 使用默认配置
                self.mem0_client = Memory()
                sisi_memory_logger.info("✅ Mem0客户端初始化成功（默认配置）")

            # 🔥 移除测试数据，避免污染生产环境
            sisi_memory_logger.info("✅ Mem0客户端初始化完成，跳过测试数据添加")

        except ImportError:
            sisi_memory_logger.error("❌ Mem0未安装，请运行: pip install mem0ai")
            self.mem0_client = None
        except Exception as e:
            sisi_memory_logger.error(f"❌ Mem0初始化失败: {e}")
            sisi_memory_logger.error(f"   配置: {self.config}")
            # 🔥 最后的兜底方案：创建一个模拟的记忆客户端
            sisi_memory_logger.warning("🔄 尝试创建模拟记忆客户端...")
            try:
                self.mem0_client = self._create_fallback_client()
                sisi_memory_logger.info("✅ 模拟记忆客户端创建成功")
            except:
                self.mem0_client = None

    def _create_fallback_client(self):
        """创建模拟记忆客户端作为兜底方案"""
        class FallbackMemoryClient:
            def __init__(self):
                self.memories = []
                sisi_memory_logger.info("🔄 初始化模拟记忆客户端")

            def add(self, text, user_id=None, **kwargs):
                memory = {
                    "id": len(self.memories),
                    "text": text,
                    "user_id": user_id,
                    "timestamp": time.time()
                }
                self.memories.append(memory)
                sisi_memory_logger.info(f"📝 模拟记忆已添加: {text[:50]}...")
                return {"message": "Memory added successfully"}

            def search(self, query, user_id=None, limit=5, **kwargs):
                # 简单的文本匹配搜索
                results = []
                for memory in self.memories:
                    if user_id and memory.get("user_id") != user_id:
                        continue
                    if query.lower() in memory["text"].lower():
                        results.append({
                            "memory": memory["text"],
                            "score": 0.8,
                            "id": memory["id"]
                        })
                        if len(results) >= limit:
                            break
                sisi_memory_logger.info(f"🔍 模拟搜索'{query}': 找到{len(results)}条结果")
                return results

            def get_all(self, user_id=None, **kwargs):
                if user_id:
                    return [m for m in self.memories if m.get("user_id") == user_id]
                return self.memories

        return FallbackMemoryClient()
    

    def add_sisi_memory(self, text: str, speaker_id: str, response: str = "", speaker_info: dict = None) -> bool:
        """Add a memory item to Mem0.

        vNext `speaker_id` format:
        - shared::{canonical_user_id}
        - {persona}::{canonical_user_id}  where persona in (sisi, liuye)
        """
        if not self.mem0_client:
            return False

        try:
            if not isinstance(text, str):
                try:
                    text = json.dumps(text, ensure_ascii=False)
                except Exception:
                    text = str(text)

            si = speaker_info or {}

            scope = "persona"
            persona = (si.get("mode") or "sisi").strip().lower()
            canonical_user_id = ""

            if isinstance(speaker_id, str) and "::" in speaker_id:
                prefix, rest = speaker_id.split("::", 1)
                prefix = (prefix or "").strip().lower()
                rest = (rest or "").strip()
                if prefix == "shared":
                    scope = "shared"
                    canonical_user_id = rest
                elif prefix in ("sisi", "liuye"):
                    scope = "persona"
                    persona = prefix
                    canonical_user_id = rest
                else:
                    canonical_user_id = rest
            else:
                canonical_user_id = str(speaker_id or "")

            user_name = si.get("real_name") or si.get("username") or (canonical_user_id or "???")

            location_info = _get_location_info()
            city = location_info.get("city", "未知")
            region = location_info.get("region", "")
            weather = _get_weather_info(city)
            current_time = time.strftime("%Y-%m-%d %H:%M", time.localtime())
            location_str = f"{region}{city}" if region else city

            conversation_text = f"[{current_time}] [地点: {location_str}] [天气: {weather}] {user_name}: {text}"
            if response:
                conversation_text += f"\nassistant: {response}"

            messages = [{"role": "user", "content": conversation_text}]

            metadata = {
                "category": "chat",
                "persona": persona,
                "mode": persona,
                "scope": scope,
                "canonical_user_id": canonical_user_id,
                "role": ("owner" if si.get("role") == "owner" else "stranger"),
                "role_type": si.get("role_type", ""),
                "identity_real_name": si.get("real_name", ""),
                "identity_username": si.get("username", ""),
                "identity_speaker_id": si.get("speaker_id", ""),
                "identity_confidence": float(si.get("confidence", 0.0) or 0.0),
            }

            self.mem0_client.add(messages, user_id=speaker_id, metadata=metadata)
            sisi_memory_logger.info(f"[mem0] add ok user_id={speaker_id} scope={scope} persona={persona}")
            return True

        except Exception as e:
            sisi_memory_logger.error(f"[mem0] add failed user_id={speaker_id} error={e}")
            return False
    def search_sisi_memory(self, query: str, speaker_id: str, limit: int = 5) -> List[Dict]:
        """搜索Sisi记忆
        vNext：speaker_id 应传入 `shared::{canonical_user_id}` 或 `{persona}::{canonical_user_id}`。
        """
        if not self.mem0_client:
            return []

        try:
            start_time = time.time()
            results = self.mem0_client.search(
                query=query,
                user_id=speaker_id,
                limit=limit
            )
            search_time = time.time() - start_time

            # Mem0 可能返回字典格式 {'results': [...]}
            if isinstance(results, dict) and 'results' in results:
                actual_results = results['results']
                sisi_memory_logger.info(f"🔍 记忆搜索完成: {len(actual_results)}条 ({search_time:.3f}s)")
                return actual_results
            else:
                sisi_memory_logger.info(f"🔍 记忆搜索完成: {len(results)}条 ({search_time:.3f}s)")
                return results

        except Exception as e:
            sisi_memory_logger.error(f"❌ 搜索Sisi记忆失败: {e}")
            return []

    @staticmethod
    def _extract_memory_text_and_kind(memory: Any) -> tuple[str, str]:
        """
        返回 (text, kind)。
        kind 优先级：metadata.memory_kind > 文本标签 [kind=...] > 默认 fact
        """
        text = ""
        kind = "fact"
        try:
            if isinstance(memory, dict):
                raw = memory.get("memory") or memory.get("content") or memory.get("data") or ""
                if not isinstance(raw, str):
                    try:
                        raw = json.dumps(raw, ensure_ascii=False)
                    except Exception:
                        raw = str(raw)
                text = raw.strip()
                meta = memory.get("metadata") or {}
                if isinstance(meta, dict):
                    mk = (meta.get("memory_kind") or meta.get("kind") or "").strip().lower()
                    if mk in ("fact", "episode"):
                        kind = mk
            else:
                text = str(memory).strip()

            if text:
                m = re.search(r"\\[kind=(fact|episode)\\]", text, flags=re.IGNORECASE)
                if m:
                    kind = m.group(1).lower()
        except Exception:
            pass
        return text, kind

    def rerank_sisi_memories(self, query: str, memories: List[Dict], top_n: int = 3) -> List[Dict]:
        """
        LLM rerank（OpenAI-compatible）。
        - 仅用于后台（前脑/动态中枢），不应该在前台实时链路调用。
        - 失败时保持原始顺序。
        """
        if not memories:
            return []

        try:
            llm_cfg = (((self.config or {}).get("llm") or {}).get("config") or {})
            base_url = (llm_cfg.get("openai_base_url") or "").rstrip("/")
            api_key = llm_cfg.get("api_key") or ""
            model = llm_cfg.get("model") or "Qwen/Qwen2.5-14B-Instruct"

            if not base_url or not api_key:
                return memories

            # 组装候选（截断避免 prompt 过长）
            candidates = []
            for i, mem in enumerate(memories[:20]):
                text, kind = self._extract_memory_text_and_kind(mem)
                if not text:
                    continue
                if not isinstance(text, str):
                    text = str(text)
                text = text.replace("\n", " ").strip()
                if len(text) > 180:
                    text = text[:180] + "…"
                candidates.append({"idx": i, "kind": kind, "text": text})

            if len(candidates) <= 1:
                return memories

            system_prompt = (
                "你是检索重排器（reranker）。"
                "只输出严格 JSON，不要输出任何额外文字。"
            )
            user_prompt = (
                "给定 query 与候选记忆列表，请按与 query 的相关性从高到低给出排序索引。\n"
                "规则：\n"
                "- 与 query 无关的排到最后\n"
                "- 同等相关时，kind=fact 优先于 kind=episode\n"
                "- 不要把寒暄/复述型内容排前\n\n"
                f"query: {query}\n\n"
                f"candidates: {json.dumps(candidates, ensure_ascii=False)}\n\n"
                "输出 JSON 格式：{\"ranking\":[idx1, idx2, ...]}（可只给出你确信的前10个，其余将保持原顺序追加）"
            )

            url = f"{base_url}/chat/completions"
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.0,
                    "max_tokens": 300,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            content = (
                (data.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            ranking_obj = json.loads(content)
            ranking = ranking_obj.get("ranking") or []
            if not isinstance(ranking, list):
                return memories

            # 将 ranking 映射回原 memories 索引（候选 idx 指向 memories 的 i）
            seen = set()
            ordered = []
            for idx in ranking:
                if not isinstance(idx, int):
                    continue
                if idx < 0 or idx >= len(memories):
                    continue
                if idx in seen:
                    continue
                seen.add(idx)
                ordered.append(memories[idx])

            # 追加剩余
            for i, mem in enumerate(memories):
                if i not in seen:
                    ordered.append(mem)

            return ordered

        except Exception as e:
            sisi_memory_logger.warning(f"[mem0] rerank_failed error={e}")
            return memories
    
    def generate_sisi_memory_context(self, query: str, speaker_id: str) -> str:
        """
        为三个模块生成长期记忆上下文（Mem0）。

        vNext 规则：
        - 输入 speaker_id 可以是 shared::{canonical_user_id} 或 {persona}::{canonical_user_id}
        - 检索时组合 shared + 当前 persona（并保留 provenance）
        """

        def _parse_user_key(s: str) -> tuple[str, str]:
            if isinstance(s, str) and "::" in s:
                a, b = s.split("::", 1)
                return (a or "").strip().lower(), (b or "").strip()
            return "", str(s or "").strip()

        prefix, canonical_user_id = _parse_user_key(speaker_id)
        persona = prefix if prefix in ("sisi", "liuye") else ""

        user_ids: list[tuple[str, str]] = []
        if prefix == "shared":
            user_ids = [("shared", speaker_id)]
        elif persona and canonical_user_id:
            user_ids = [("shared", f"shared::{canonical_user_id}"), (persona, f"{persona}::{canonical_user_id}")]
        else:
            user_ids = [("persona", speaker_id)]

        buckets: dict[str, list[Any]] = {}
        for label, uid in user_ids:
            try:
                buckets[label] = self.search_sisi_memory(query, uid, limit=3) or []
            except Exception:
                buckets[label] = []

        if not any(buckets.values()):
            return "无相关记忆"

        def _format_items(items: list[Any]) -> list[str]:
            out: list[str] = []
            for m in items:
                if isinstance(m, dict):
                    raw = m.get("memory") or m.get("content") or ""
                    if not isinstance(raw, str):
                        try:
                            raw = json.dumps(raw, ensure_ascii=False)
                        except Exception:
                            raw = str(raw)
                    raw = raw.strip()
                    if not raw:
                        continue
                    raw = raw[:120]
                    cleaned = format_memory_item(raw, source="长期记忆")
                    if cleaned:
                        out.append(cleaned)
                else:
                    s = str(m).strip()
                    if not s:
                        continue
                    cleaned = format_memory_item(s[:120], source="长期记忆")
                    if cleaned:
                        out.append(cleaned)
            return out

        parts: list[str] = []
        shared_items = _format_items(buckets.get("shared") or [])
        persona_items = _format_items(buckets.get(persona) or buckets.get("persona") or [])

        if shared_items:
            parts.extend(shared_items)
        if persona_items:
            parts.extend(persona_items)

        return "\n".join(parts).strip()
    
    def is_available(self) -> bool:
        """检查Sisi记忆系统是否可用"""
        return self.mem0_client is not None

    # ==================== 🔥 用户管理功能扩展 ====================

    def add_user(self, user_id: str, name: str = "", email: str = "", metadata: dict = None) -> bool:
        """
        添加用户到记忆系统

        Args:
            user_id (str): 用户唯一标识符
            name (str): 用户姓名
            email (str): 用户邮箱
            metadata (dict): 用户元数据（角色、权限等）

        Returns:
            bool: 添加成功返回True，失败返回False
        """
        if not self.mem0_client:
            sisi_memory_logger.error("❌ Mem0客户端未初始化")
            return False

        try:
            # 构建用户注册记忆
            user_info = {
                "user_id": user_id,
                "name": name,
                "email": email,
                "registered_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                **(metadata or {})
            }

            # 添加用户注册记忆（mem0会自动创建用户）
            registration_message = f"用户 {name or user_id} 已注册到系统"
            if email:
                registration_message += f"，邮箱: {email}"

            result = self.mem0_client.add(
                registration_message,
                user_id=user_id,
                metadata=user_info
            )

            sisi_memory_logger.info(f"✅ 用户添加成功: {user_id} ({name})")
            return True

        except Exception as e:
            sisi_memory_logger.error(f"❌ 添加用户失败: {user_id} - {e}")
            return False

    def get_user_info(self, user_id: str) -> Optional[Dict]:
        """
        获取用户信息

        Args:
            user_id (str): 用户ID

        Returns:
            dict: 用户信息字典，包含name, email, metadata等
        """
        if not self.mem0_client:
            return None

        try:
            # 搜索用户注册记忆
            memories = self.mem0_client.search(
                query="用户注册",
                user_id=user_id,
                limit=1
            )

            if isinstance(memories, dict) and 'results' in memories:
                results = memories['results']
            else:
                results = memories

            if results:
                # 从记忆的metadata中提取用户信息
                memory = results[0]
                if isinstance(memory, dict) and 'metadata' in memory:
                    user_info = memory['metadata']
                    sisi_memory_logger.info(f"✅ 获取用户信息: {user_id}")
                    return user_info

            sisi_memory_logger.warning(f"⚠️ 用户信息未找到: {user_id}")
            return None

        except Exception as e:
            sisi_memory_logger.error(f"❌ 获取用户信息失败: {user_id} - {e}")
            return None

    def get_all_users(self) -> List[Dict]:
        """
        获取所有用户列表

        Returns:
            list: 用户列表，每个元素包含用户基本信息
        """
        if not self.mem0_client:
            return []

        try:
            # mem0 开源版本没有直接的用户列表接口
            # 通过获取所有记忆来提取用户信息
            try:
                all_memories = self.mem0_client.get_all()
                user_ids = set()

                # 从记忆中提取用户ID
                if isinstance(all_memories, list):
                    for memory in all_memories:
                        if isinstance(memory, dict) and 'user_id' in memory:
                            user_ids.add(memory['user_id'])

                # 构造用户列表
                users = []
                for user_id in user_ids:
                    users.append({
                        'user_id': user_id,
                        'name': user_id,
                        'created_at': None,
                        'metadata': {}
                    })

                sisi_memory_logger.info(f"✅ 获取用户列表: {len(users)}个用户")
                return users

            except Exception as inner_e:
                # 如果获取记忆失败，返回空列表
                sisi_memory_logger.warning(f"⚠️ 无法从记忆中提取用户: {inner_e}")
                return []

        except Exception as e:
            sisi_memory_logger.error(f"❌ 获取用户列表失败: {e}")
            return []

    def update_user(self, user_id: str, name: str = None, email: str = None, metadata: dict = None) -> bool:
        """
        更新用户信息

        Args:
            user_id (str): 用户ID
            name (str): 新的用户姓名
            email (str): 新的用户邮箱
            metadata (dict): 新的用户元数据

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        if not self.mem0_client:
            return False

        try:
            # 获取当前用户信息
            current_info = self.get_user_info(user_id)
            if not current_info:
                sisi_memory_logger.error(f"❌ 用户不存在: {user_id}")
                return False

            # 更新用户信息
            updated_info = current_info.copy()
            if name is not None:
                updated_info['name'] = name
            if email is not None:
                updated_info['email'] = email
            if metadata is not None:
                updated_info.update(metadata)

            updated_info['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')

            # 添加更新记忆
            update_message = f"用户 {updated_info.get('name', user_id)} 信息已更新"
            result = self.mem0_client.add(
                update_message,
                user_id=user_id,
                metadata=updated_info
            )

            sisi_memory_logger.info(f"✅ 用户信息更新成功: {user_id}")
            return True

        except Exception as e:
            sisi_memory_logger.error(f"❌ 更新用户信息失败: {user_id} - {e}")
            return False

    def delete_user(self, user_id: str) -> bool:
        """
        删除用户及其所有记忆

        Args:
            user_id (str): 用户ID

        Returns:
            bool: 删除成功返回True，失败返回False
        """
        if not self.mem0_client:
            return False

        try:
            # 使用mem0的delete_users方法删除用户及其所有记忆
            result = self.mem0_client.delete_users(user_id=user_id)

            sisi_memory_logger.info(f"✅ 用户删除成功: {user_id}")
            return True

        except Exception as e:
            sisi_memory_logger.error(f"❌ 删除用户失败: {user_id} - {e}")
            return False

    def user_exists(self, user_id: str) -> bool:
        """
        检查用户是否存在

        Args:
            user_id (str): 用户ID

        Returns:
            bool: 用户存在返回True，不存在返回False
        """
        user_info = self.get_user_info(user_id)
        return user_info is not None

    def get_user_memory_count(self, user_id: str) -> int:
        """
        获取用户的记忆数量

        Args:
            user_id (str): 用户ID

        Returns:
            int: 记忆数量
        """
        if not self.mem0_client:
            return 0

        try:
            # 获取用户所有记忆
            memories = self.mem0_client.get_all(user_id=user_id)

            if isinstance(memories, list):
                count = len(memories)
            elif isinstance(memories, dict) and 'results' in memories:
                count = len(memories['results'])
            else:
                count = 0

            sisi_memory_logger.info(f"✅ 用户记忆数量: {user_id} - {count}条")
            return count

        except Exception as e:
            sisi_memory_logger.error(f"❌ 获取用户记忆数量失败: {user_id} - {e}")
            return 0

def format_memory_item(raw: str, source: str) -> str:
    text = (raw or "").strip()
    content = re.search(r"\[content=\"(.*?)\"\]", text)
    if content:
        return content.group(1).strip()
    cleaned = re.sub(r"\[[^\]]+\]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def get_sisi_memory_system() -> SisiMemorySystem:
    """获取Sisi记忆系统实例 - 真正的单例模式"""
    # 🔥 直接调用SisiMemorySystem()，它内部已经实现了单例模式
    # 无论调用多少次，都会返回同一个实例，且只初始化一次
    return SisiMemorySystem()

def add_sisi_interaction_memory(text: str, speaker_id: str, response: str = "", speaker_info: dict = None) -> bool:
    """便捷函数：添加Sisi交互记忆 - 异步后台处理"""
    try:
        import threading

        def _async_add_memory():
            """异步添加记忆的内部函数"""
            try:
                sisi_memory = get_sisi_memory_system()
                if sisi_memory and sisi_memory.is_available():
                    success = sisi_memory.add_sisi_memory(text, speaker_id, response, speaker_info)
                    if success:
                        sisi_memory_logger.info(f"🔄 异步记忆存储成功: {speaker_id}")
                    else:
                        sisi_memory_logger.error(f"❌ 异步记忆存储失败: {speaker_id}")
                else:
                    sisi_memory_logger.error("❌ 记忆系统不可用")
            except Exception as e:
                sisi_memory_logger.error(f"❌ 异步记忆存储异常: {e}")

        # 🚀 启动后台线程进行记忆存储
        thread = threading.Thread(target=_async_add_memory, daemon=True)
        thread.start()

        # 立即返回True，不等待存储完成
        sisi_memory_logger.info(f"🚀 记忆存储已提交后台处理: {speaker_id}")
        return True

    except Exception as e:
        sisi_memory_logger.error(f"❌ 启动异步记忆存储失败: {e}")
        return False

def get_sisi_memory_context(query: str, speaker_id: str) -> str:
    """便捷函数：获取Sisi记忆上下文 - 自动切换到可用的记忆系统"""
    sisi_memory = get_sisi_memory_system()

    # 如果mem0不可用，返回无记忆
    if not sisi_memory.is_available():
        sisi_memory_logger.error("❌ mem0不可用，无法获取记忆上下文")
        return "无相关Sisi记忆"

    return sisi_memory.generate_sisi_memory_context(query, speaker_id)

# ==================== 🔥 简化的便捷函数 ====================
# 直接使用类方法，不需要重复的便捷函数

def run_complete_test():
    """运行完整的测试套件"""
    print("🚀 开始运行完整的Sisi记忆系统测试套件")
    print("="*80)

    # 测试基础记忆功能
    test_sisi_memory()

    # 测试用户管理功能
    user_test_result = test_sisi_user_management()

# 最终结果
    print("\n" + "="*80)
    print("🏁 测试套件完成")
    print("="*80)

    if user_test_result:
        print("🎉 所有测试通过！Sisi记忆系统用户管理功能正常")
        return True
    else:
        print("⚠️ 部分测试失败，请检查系统配置")
        return False

if __name__ == "__main__":
    # 运行完整测试套件
    run_complete_test()
