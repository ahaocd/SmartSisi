#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险者公会监督智能体 - 单文件完整实现
借鉴OpenClaw的Lane机制 + MD文件持久化 + 大模型智能决策
"""

import os
import sys
import json
import time
import asyncio
import logging
import configparser
import threading
import uuid
import websockets
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import util
from utils import config_util as cfg

logger = logging.getLogger(__name__)

# OpenClaw协议版本(从src/gateway/protocol/schema/protocol-schemas.ts)
PROTOCOL_VERSION = 3


class GuildConfig:
    """公会配置管理器 - 从system.conf读取"""
    
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """从system.conf加载配置（仅读取 [key] 分区）"""
        try:
            config_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "SmartSisi",
                "system.conf"
            )

            parser = configparser.ConfigParser()
            parser.read(config_file, encoding='utf-8-sig')
            if parser.has_section("key"):
                util.log(1, "[公会配置] ✅ system.conf加载成功")
                return dict(parser["key"])

            util.log(2, "[公会配置] system.conf未找到[key]分区")
            return {}

        except Exception as e:
            util.log(3, f"[公会配置] system.conf加载失败: {e}")
            return {}
    
    def get_llm_config(self) -> dict:
        """获取大模型配置 - 用于智能决策"""
        return {
            "model": self.config.get("douyin_marketing_text_model", "moonshotai/Kimi-K2-Instruct-0905"),
            "api_key": self.config.get("douyin_marketing_text_api_key", ""),
            "base_url": self.config.get("douyin_marketing_text_base_url", "https://api.siliconflow.cn/v1"),
            "temperature": float(self.config.get("douyin_marketing_text_temperature", "0.4")),
            "max_tokens": int(self.config.get("douyin_marketing_text_max_tokens", "1000"))
        }
    
    def get_openclaw_config(self) -> dict:
        """获取OpenClaw配置"""
        return {
            "ws_url": self.config.get("openclaw_ws_url", "ws://127.0.0.1:18789"),
            "token": self.config.get("openclaw_token", "openclaw-dev-token-104826703")
        }


class MDFileStorage:
    """MD文件存储 - JSON+MD双文件架构"""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 任务目录 - 存储JSON和MD
        self.tasks_dir = self.storage_dir / "tasks"
        self.tasks_dir.mkdir(exist_ok=True)
        
        # 会话目录
        self.sessions_dir = self.storage_dir / "sessions"
        self.sessions_dir.mkdir(exist_ok=True)
        
        # 分析目录
        self.analysis_dir = self.storage_dir / "analysis"
        self.analysis_dir.mkdir(exist_ok=True)
        
        # 任务队列文件(持久化)
        self.queue_file = self.storage_dir / "pending_queue.md"
        
        util.log(1, f"[MD存储] 初始化完成: {self.storage_dir}")
    
    def save_pending_queue(self, queue: List[tuple]):
        """保存待发送任务队列到MD文件"""
        try:
            content = f"# 待发送任务队列\n\n"
            content += f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            if not queue:
                content += "队列为空\n"
            else:
                for task_id, description in queue:
                    content += f"## {task_id}\n"
                    content += f"- 描述: {description}\n"
                    content += f"- 状态: 等待连接\n\n"
            
            self.queue_file.write_text(content, encoding='utf-8')
            
        except Exception as e:
            util.log(3, f"[MD存储] 保存队列失败: {e}")
    
    def load_pending_queue(self) -> List[tuple]:
        """从MD文件加载待发送任务队列"""
        try:
            if not self.queue_file.exists():
                return []
            
            content = self.queue_file.read_text(encoding='utf-8')
            queue = []
            
            # 简单解析MD文件
            lines = content.split('\n')
            current_task_id = None
            current_desc = None
            
            for line in lines:
                if line.startswith('## task_'):
                    current_task_id = line[3:].strip()
                elif line.startswith('- 描述: ') and current_task_id:
                    current_desc = line[6:].strip()
                    queue.append((current_task_id, current_desc))
                    current_task_id = None
                    current_desc = None
            
            return queue
            
        except Exception as e:
            util.log(3, f"[MD存储] 加载队列失败: {e}")
            return []
    
    def clear_pending_queue(self):
        """清空队列文件"""
        try:
            if self.queue_file.exists():
                self.queue_file.unlink()
        except Exception as e:
            util.log(3, f"[MD存储] 清空队列失败: {e}")
    
    def save_task(self, task_id: str, task_data: dict):
        """保存任务 - JSON+MD双文件架构"""
        # 1. 保存完整数据到JSON (包含streams)
        json_file = self.tasks_dir / f"{task_id}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)
        
        # 2. 生成人类可读的MD报告
        md_file = self.tasks_dir / f"{task_id}.md"
        md_content = self._generate_md_report(task_id, task_data)
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        util.log(1, f"[MD存储] 任务已保存: {task_id} (JSON+MD)")
    
    def _generate_md_report(self, task_id: str, task_data: dict) -> str:
        """生成MD报告（从task_data生成）"""
        result = task_data.get('result') or '等待执行'
        result_length = len(result) if result != '等待执行' else 0
        
        # 提取streams信息
        streams = task_data.get('streams', {})
        lifecycle_events = streams.get('lifecycle', [])
        assistant_events = streams.get('assistant', [])
        tool_events = streams.get('tool', [])
        error_events = streams.get('error', [])
        thinking_events = streams.get('thinking', [])
        
        # 提取工具调用和多模态内容
        tool_calls = task_data.get('tool_calls', [])
        images = task_data.get('images', [])
        
        # 生成结果预览
        if result_length > 500:
            result_preview = f"{result[:200]}...\n\n[中间部分]\n{result[result_length//2-50:result_length//2+50]}...\n\n[结尾部分]\n{result[-200:]}"
        else:
            result_preview = result
        
        content = f"""# 任务: {task_id}

## 📊 智能摘要
- **完整长度**: {result_length}字
- **状态**: {task_data.get('status', 'pending')}
- **工具调用**: {len(tool_calls)}次
- **图片**: {len(images)}张
- **错误**: {'是' if task_data.get('error') else '否'}
- **生命周期事件**: {len(lifecycle_events)}个
- **AI输出事件**: {len(assistant_events)}个
- **工具事件**: {len(tool_events)}个
- **思考事件**: {len(thinking_events)}个

## 📝 结果预览
{result_preview}

## 基本信息
- **任务ID**: {task_id}
- **描述**: {task_data.get('description', '')}
- **状态**: {task_data.get('status', 'pending')}
- **创建者**: {task_data.get('created_by', 'liuye')}
- **创建时间**: {datetime.fromtimestamp(task_data.get('created_at', time.time())).strftime('%Y-%m-%d %H:%M:%S')}
- **执行者**: {task_data.get('assigned_to', 'openclaw')}

## 执行信息
- **会话ID**: {task_data.get('openclaw_session_id', '未分配')}
- **错误**: {task_data.get('error') if task_data.get('error') else '无'}

## 🔄 生命周期事件流
{self._format_lifecycle_events(lifecycle_events)}

## 💭 思考过程
{self._format_thinking_events(thinking_events)}

## 🛠️ 工具调用详情
{self._format_tool_events(tool_events)}

## 💬 AI输出流
{self._format_assistant_events(assistant_events)}

## ❌ 错误事件
{self._format_error_events(error_events)}

## 🖼️ 多模态内容
{self._format_images(images)}

## 📈 分析结果
```json
{json.dumps(task_data.get('analysis', {}), ensure_ascii=False, indent=2)}
```

---
*最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return content
    
    def _format_tool_calls(self, tool_calls: list) -> str:
        """格式化工具调用记录"""
        if not tool_calls:
            return "无"
        
        result = ""
        for i, call in enumerate(tool_calls, 1):
            result += f"{i}. **{call.get('name', '未知')}**\n"
            result += f"   - 参数: {json.dumps(call.get('args', {}), ensure_ascii=False)[:100]}...\n"
        return result
    
    def _format_lifecycle_events(self, events: list) -> str:
        """格式化生命周期事件"""
        if not events:
            return "无"
        
        result = ""
        for event in events:
            phase = event.get('phase', '未知')
            ts = event.get('ts', time.time())
            # OpenClaw的ts是毫秒级，需要转换为秒
            ts_sec = ts / 1000 if ts > 10000000000 else ts
            ts_str = datetime.fromtimestamp(ts_sec).strftime('%H:%M:%S')
            result += f"- [{ts_str}] **{phase}** (seq: {event.get('seq', 0)})\n"
        return result
    
    def _format_thinking_events(self, events: list) -> str:
        """格式化思考事件"""
        if not events:
            return "无"
        
        result = ""
        for event in events:
            text = event.get('text', '')
            ts = event.get('ts', time.time())
            ts_sec = ts / 1000 if ts > 10000000000 else ts
            ts_str = datetime.fromtimestamp(ts_sec).strftime('%H:%M:%S')
            result += f"- [{ts_str}] {text[:100]}{'...' if len(text) > 100 else ''}\n"
        return result
    
    def _format_tool_events(self, events: list) -> str:
        """格式化工具事件"""
        if not events:
            return "无"
        
        result = ""
        for i, event in enumerate(events, 1):
            name = event.get('name', '未知')
            ts = event.get('ts', time.time())
            ts_sec = ts / 1000 if ts > 10000000000 else ts
            ts_str = datetime.fromtimestamp(ts_sec).strftime('%H:%M:%S')
            args = json.dumps(event.get('args', {}), ensure_ascii=False)[:100]
            result += f"{i}. [{ts_str}] **{name}**\n"
            result += f"   - 参数: {args}...\n"
            if event.get('result'):
                result += f"   - 结果: {str(event.get('result'))[:100]}...\n"
        return result
    
    def _format_assistant_events(self, events: list) -> str:
        """格式化AI输出事件"""
        if not events:
            return "无"
        
        result = ""
        for i, event in enumerate(events, 1):
            text = event.get('text', '')
            delta = event.get('delta', '')
            ts = event.get('ts', time.time())
            ts_sec = ts / 1000 if ts > 10000000000 else ts
            ts_str = datetime.fromtimestamp(ts_sec).strftime('%H:%M:%S')
            
            if text:
                result += f"{i}. [{ts_str}] 完整输出 ({len(text)}字)\n"
            elif delta:
                result += f"{i}. [{ts_str}] 增量输出: {delta[:50]}...\n"
        
        return result
    
    def _format_error_events(self, events: list) -> str:
        """格式化错误事件"""
        if not events:
            return "无"
        
        result = ""
        for event in events:
            msg = event.get('message', '未知错误')
            code = event.get('code', '')
            ts = event.get('ts', time.time())
            ts_sec = ts / 1000 if ts > 10000000000 else ts
            ts_str = datetime.fromtimestamp(ts_sec).strftime('%H:%M:%S')
            result += f"- [{ts_str}] {code}: {msg}\n"
        return result
    
    def _format_images(self, images: list) -> str:
        """格式化图片记录"""
        if not images:
            return "无"
        
        result = ""
        for i, img in enumerate(images, 1):
            result += f"{i}. {img.get('description', '图片')} ({img.get('size', '未知大小')})\n"
        return result
    
    def load_task(self, task_id: str) -> Optional[dict]:
        """从JSON文件加载任务（完整恢复streams）"""
        json_file = self.tasks_dir / f"{task_id}.json"
        
        if not json_file.exists():
            return None
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            
            util.log(1, f"[MD存储] 任务已加载: {task_id}")
            return task_data
            
        except Exception as e:
            util.log(3, f"[MD存储] 加载任务失败: {e}")
            return None
    
    def load_task_full(self, task_id: str) -> Optional[dict]:
        """加载任务完整结果（包含完整AI输出）"""
        task_data = self.load_task(task_id)
        if not task_data:
            return None
        
        # 从原始存储中读取完整结果
        file_path = self.tasks_dir / f"{task_id}.md"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取完整结果
            task_data["result"] = self._extract_section(content, "## 📝 结果预览", "## 基本信息")
            return task_data
        except Exception as e:
            util.log(3, f"[MD存储] 加载完整结果失败: {e}")
            return task_data
    
    def _extract_section(self, content: str, start_marker: str, end_marker: str) -> str:
        """提取MD文件中的章节内容"""
        try:
            start_idx = content.find(start_marker)
            end_idx = content.find(end_marker, start_idx)
            if start_idx == -1 or end_idx == -1:
                return ""
            return content[start_idx + len(start_marker):end_idx].strip()
        except:
            return ""
    
    def list_tasks(self, status: str = None) -> List[dict]:
        """列出所有任务"""
        tasks = []
        
        for file_path in self.tasks_dir.glob("*.json"):
            task_id = file_path.stem
            task_data = self.load_task(task_id)
            
            if task_data:
                if status is None or task_data.get("status") == status:
                    tasks.append(task_data)
        
        # 按创建时间排序
        tasks.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return tasks
    
    def _extract_field(self, content: str, field_name: str) -> str:
        """从MD内容中提取字段"""
        import re
        pattern = rf'\*\*{field_name}\*\*:\s*(.+?)(?:\n|$)'
        match = re.search(pattern, content)
        return match.group(1).strip() if match else ""
    
    def _parse_tool_calls(self, content: str) -> list:
        """从MD文件解析工具调用记录"""
        try:
            section = self._extract_section(content, "## 🛠️ 工具调用记录", "## 🖼️ 多模态内容")
            if not section or section == "无":
                return []
            
            # 简单解析：每行以数字开头的是一个工具调用
            tool_calls = []
            lines = section.split('\n')
            current_tool = None
            
            for line in lines:
                if line.strip().startswith(tuple('123456789')):
                    # 提取工具名称
                    import re
                    match = re.search(r'\*\*(.+?)\*\*', line)
                    if match:
                        current_tool = {"name": match.group(1), "args": {}}
                        tool_calls.append(current_tool)
            
            return tool_calls
        except:
            return []
    
    def _parse_images(self, content: str) -> list:
        """从MD文件解析图片记录"""
        try:
            section = self._extract_section(content, "## 🖼️ 多模态内容", "## 📈 分析结果")
            if not section or section == "无":
                return []
            
            # 简单解析：每行以数字开头的是一张图片
            images = []
            lines = section.split('\n')
            
            for line in lines:
                if line.strip().startswith(tuple('123456789')):
                    # 提取图片描述和大小
                    import re
                    match = re.search(r'\d+\.\s*(.+?)\s*\((.+?)\)', line)
                    if match:
                        images.append({
                            "description": match.group(1),
                            "size": match.group(2)
                        })
            
            return images
        except:
            return []
    
    def _parse_analysis(self, content: str) -> dict:
        """从MD文件解析分析结果"""
        try:
            section = self._extract_section(content, "## 📈 分析结果", "---")
            if not section:
                return {}
            
            # 提取JSON代码块
            import re
            match = re.search(r'```json\s*(\{.*?\})\s*```', section, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return {}
        except:
            return {}
    
    def save_session(self, session_id: str, session_data: dict):
        """保存会话到MD文件"""
        file_path = self.sessions_dir / f"{session_id}.md"
        
        content = f"""# 会话: {session_id}

## 基本信息
- **会话ID**: {session_id}
- **任务ID**: {session_data.get('task_id', '未关联')}
- **状态**: {session_data.get('status', 'unknown')}
- **时间**: {datetime.fromtimestamp(session_data.get('timestamp', time.time())).strftime('%Y-%m-%d %H:%M:%S')}

## 执行内容
- **输出**: {session_data.get('output', '无')[:200]}...
- **工具调用**: {json.dumps(session_data.get('tool_calls', []), ensure_ascii=False)[:200]}...

---
*记录时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)


class LLMAnalyzer:
    """大模型分析器 - 用于智能决策和分析"""
    
    def __init__(self, config: GuildConfig):
        self.config = config
        self.llm_config = config.get_llm_config()
        self.client = None
        self._init_client()
        
        # 结果缓存(借鉴LangGraph适配器)
        self.result_cache = {}
        self.cache_timeout = 300  # 5分钟
    
    def _init_client(self):
        """初始化OpenAI客户端"""
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.llm_config["api_key"],
                base_url=self.llm_config["base_url"]
            )
            util.log(1, f"[大模型分析器] ✅ 初始化成功: {self.llm_config['model']}")
        except Exception as e:
            util.log(3, f"[大模型分析器] 初始化失败: {e}")
            self.client = None
    
    def analyze_session(self, task: dict, session: dict) -> dict:
        """分析会话 - 使用大模型智能分析"""
        if not self.client:
            util.log(3, "[大模型分析器] [错误] 客户端未初始化")
            return {"error": "大模型客户端未初始化"}
        
        # 检查缓存
        cache_key = f"{task.get('task_id')}:{session.get('session_id')}"
        current_time = time.time()
        
        if cache_key in self.result_cache:
            cached_result, timestamp = self.result_cache[cache_key]
            if current_time - timestamp < self.cache_timeout:
                util.log(1, f"[大模型分析器] [缓存] 使用缓存结果")
                return cached_result
        
        try:
            util.log(1, f"[大模型分析器] [API] 开始调用 - model: {self.llm_config['model']}")
            util.log(1, f"[大模型分析器] [API] 配置: base_url={self.llm_config['base_url']}, key={self.llm_config['api_key'][:20]}...")
            
            prompt = self._build_analysis_prompt(task, session)
            util.log(1, f"[大模型分析器] [提示词] 长度: {len(prompt)}字")
            
            # 添加超时设置（60秒）
            response = self.client.chat.completions.create(
                model=self.llm_config["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=self.llm_config["temperature"],
                max_tokens=self.llm_config["max_tokens"],
                timeout=60.0  # 60秒超时
            )
            
            result_text = response.choices[0].message.content
            util.log(1, f"[大模型分析器] [返回] API返回: {len(result_text)}字")
            util.log(1, f"[大模型分析器] [返回] 内容预览: {result_text[:200]}")
            
            # 尝试解析JSON
            try:
                analysis = json.loads(result_text)
                util.log(1, f"[大模型分析器] [JSON] 解析成功")
            except Exception as json_err:
                util.log(2, f"[大模型分析器] [JSON] 解析失败: {json_err}, 使用文本摘要")
                analysis = {
                    "summary": result_text,
                    "overall_score": 5,
                    "raw_response": result_text
                }
            
            # 缓存结果
            self.result_cache[cache_key] = (analysis, current_time)
            
            util.log(1, f"[大模型分析器] [完成] 分析完成: {analysis.get('summary', '')[:50]}")
            return analysis
            
        except Exception as e:
            util.log(3, f"[大模型分析器] [错误] 分析失败: {type(e).__name__}: {str(e)}")
            import traceback
            util.log(3, f"[大模型分析器] [错误] 堆栈: {traceback.format_exc()}")
            return {"error": str(e), "error_type": type(e).__name__}
    
    def _build_analysis_prompt(self, task: dict, session: dict) -> str:
        """构建分析提示词 - 整合所有streams信息"""
        
        # 获取任务摘要（安全处理None）
        result = task.get('result') or '无'
        result_length = len(result) if result != '无' else 0
        tool_calls = task.get('tool_calls') or []
        images = task.get('images') or []
        
        # 获取streams信息（安全处理None）
        streams = task.get('streams') or {}
        lifecycle_events = streams.get('lifecycle') or []
        assistant_events = streams.get('assistant') or []
        tool_events = streams.get('tool') or []
        error_events = streams.get('error') or []
        thinking_events = streams.get('thinking') or []
        
        # 判断任务复杂度
        is_simple = (
            len(tool_events) == 0 and  # 无工具调用
            len(thinking_events) == 0 and  # 无思考过程
            len(error_events) == 0 and  # 无错误
            result_length < 200  # 输出简短
        )
        
        if is_simple:
            # 简单任务 - 简化提示词
            return f"""你是冒险者公会的监督智能体。分析OpenClaw执行简单任务的情况。

任务: {task.get('description', '未知')}
结果: {result}
耗时: {len(lifecycle_events)}个生命周期事件

请用一句话总结，输出JSON格式：
{{
    "summary": "一句话总结（例如：直接回答，无需工具，结果正确）",
    "score": 0-10,
    "issues": ["问题1", "问题2"] 或 null（无问题时）
}}
"""
        else:
            # 复杂任务 - 详细分析
            return f"""你是冒险者公会的监督智能体，负责分析OpenClaw的工作过程。

## 任务信息
- 描述: {task.get('description', '未知')}
- 结果: {result[:200]}{'...' if result_length > 200 else ''}

## 执行过程
- 生命周期: {self._format_lifecycle_summary(lifecycle_events)}
- 思考过程: {self._format_thinking_summary(thinking_events)}
- 工具调用: {self._format_tool_summary(tool_events)}
- 错误: {self._format_error_summary(error_events)}

## 分析要求
1. 去除冗余信息（重复的事件、无意义的日志）
2. 汇总关键信息（重要的工具调用、思考逻辑、输出内容）
3. 标记遗漏（可能缺失的步骤或信息）

输出JSON格式：
{{
    "summary": "一句话总结OpenClaw的表现",
    "score": 0-10,
    "key_points": ["关键点1", "关键点2"],
    "redundant": ["冗余信息1"] 或 null,
    "missing": ["遗漏的步骤1"] 或 null,
    "issues": ["问题1"] 或 null
}}
"""
    
    def _format_lifecycle_summary(self, events: list) -> str:
        """格式化生命周期摘要"""
        if not events:
            return "无"
        phases = [e.get('phase') for e in events]
        return f"start: {phases.count('start')}次, end: {phases.count('end')}次, complete: {phases.count('complete')}次"
    
    def _format_thinking_summary(self, events: list) -> str:
        """格式化思考摘要"""
        if not events:
            return "无"
        total_text = " ".join([e.get('text', '') for e in events])
        return total_text[:200] + "..." if len(total_text) > 200 else total_text
    
    def _format_tool_summary(self, events: list) -> str:
        """格式化工具摘要"""
        if not events:
            return "无"
        tools = {}
        for e in events:
            name = e.get('name', '未知')
            tools[name] = tools.get(name, 0) + 1
        return ", ".join([f"{name}({count}次)" for name, count in tools.items()])
    
    def _format_error_summary(self, events: list) -> str:
        """格式化错误摘要"""
        if not events:
            return "无"
        return "; ".join([e.get('message', '未知错误') for e in events[:3]])


class GuildAuditLogger:
    """公会操作审计日志（JSONL 持久化）。"""

    def __init__(self, storage_dir: Path):
        self.audit_dir = storage_dir / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(
        self,
        action: str,
        actor: str = "system",
        task_id: str = "",
        result: str = "ok",
        trace_id: str = "",
        correlation_id: str = "",
        detail: Optional[dict] = None,
    ) -> None:
        record = {
            "id": f"audit_{uuid.uuid4().hex[:16]}",
            "time": datetime.now().isoformat(),
            "ts": time.time(),
            "actor": str(actor or "system"),
            "action": str(action or ""),
            "task_id": str(task_id or ""),
            "result": str(result or "ok"),
            "trace_id": str(trace_id or ""),
            "correlation_id": str(correlation_id or ""),
            "detail": detail or {},
        }

        filename = f"audit-{datetime.now().strftime('%Y%m%d')}.jsonl"
        path = self.audit_dir / filename
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


class GuildSupervisorAgent:
    """冒险者公会监督智能体 - 主类(借鉴LangGraph适配器单例模式)
    
    公会管理多个成员:
    - OpenClaw: 第一个成员,擅长网络搜索、浏览器自动化
    - 未来可扩展: Claude Code、Cursor、其他智能体
    """
    
    def __init__(self):
        # 配置
        self.config = GuildConfig()
        
        # MD文件存储
        storage_dir = os.path.join(
            os.path.dirname(__file__),
            "guild_data"
        )
        self.storage = MDFileStorage(storage_dir)
        self.audit = GuildAuditLogger(Path(storage_dir))

        
        # 大模型分析器
        self.analyzer = LLMAnalyzer(self.config)
        
        # 🔥 公会成员配置(可扩展)
        self.guild_members = {
            "openclaw": {
                "name": "OpenClaw",
                "type": "agent",
                "capabilities": [
                    # 文件系统
                    "文件读写编辑", "多文件补丁", 
                    # 运行时
                    "Shell命令执行", "后台进程管理",
                    # 网络
                    "网页搜索(Brave)", "网页内容获取(HTML→Markdown)",
                    # 浏览器
                    "浏览器控制", "页面截图", "UI自动化操作",
                    # 会话管理
                    "多会话管理", "跨会话通信",
                    # 记忆系统
                    "长期记忆(MEMORY.md)", "每日日志(memory/*.md)",
                    # 消息
                    "消息发送", "内联按钮", "投票和反应",
                    # 节点
                    "设备控制(macOS)", "摄像头拍照", "屏幕录制", "位置获取",
                    # 图片分析
                    "图片分析(Qwen3-VL-235B)",
                    # 技能系统(54个可用技能)
                    "天气查询", "音响控制(Sonos)", "任务管理(Things)", 
                    "密码管理(1Password)", "笔记管理(Obsidian/Bear)",
                    "GitHub集成", "Slack/Discord集成", "Spotify播放器"
                ],
                "tools": {
                    "fs": ["read", "write", "edit", "apply_patch"],
                    "runtime": ["exec", "bash", "process"],
                    "web": ["web_search", "web_fetch"],
                    "ui": ["browser", "canvas"],
                    "sessions": ["sessions_list", "sessions_send", "sessions_spawn"],
                    "memory": ["memory_search", "memory_get"],
                    "messaging": ["message"],
                    "nodes": ["nodes", "camera_snap", "screen_record", "location_get"],
                    "image": ["image"]
                },
                "skills": {
                    "installed": 0,
                    "available": 54,
                    "categories": ["天气", "音响", "任务管理", "密码", "笔记", "集成", "音乐"]
                },
                "ws_url": "ws://127.0.0.1:18789",
                "token": "openclaw-dev-token-104826703",
                "status": "active",
                "model": "modelscope/Qwen/Qwen3-Coder-480B-A35B-Instruct",
                "context_window": 200000
            }
            # 未来可以添加更多成员:
            # "claude_code": {
            #     "name": "Claude Code",
            #     "type": "agent",
            #     "capabilities": ["代码生成", "代码审查", "重构"],
            #     "api_url": "...",
            #     "status": "inactive"
            # }
        }
        
        # OpenClaw配置(第一个成员)
        openclaw_config = self.guild_members["openclaw"]
        self.openclaw_ws_url = openclaw_config["ws_url"]
        self.openclaw_token = openclaw_config["token"]

        # 公会上下文目录（用于向成员传递固定上下文）
        self.context_dir = Path(__file__).resolve().parent / "adventurers_guild" / "context"
        # 公会内部目录（不对成员下发）
        self.internal_dir = Path(__file__).resolve().parent / "adventurers_guild" / "internal"
        self._ensure_guild_context_files()
        
        # WebSocket监听器
        self.listener = None
        self.listener_running = False
        self.listener_ready = False  # 新增:标记连接是否就绪
        self._event_loop = None  # 保存事件循环引用
        
        # 任务映射(task_id -> session_id)
        self.task_session_map = {}
        
        # runId映射(runId -> task_id) - 用于没有sessionKey的agent事件
        self.run_task_map = {}
        
        # 待发送任务队列(连接建立前的任务)
        self.pending_tasks = []  # [(task_id, description), ...]
        self._queue_lock = threading.Lock()
        self._dispatching = False
        self.dispatch_policy = "queue_first"  # 先落盘入队，再尝试派发
        self._listener_thread = None
        self._listener_thread_lock = threading.Lock()
        
        # 事件订阅（柳叶回调）和澄清上下文
        self._event_subscribers = {}  # subscriber_id -> callback
        self._subscriber_seq = 0
        self._subscriber_lock = threading.Lock()
        self._pending_clarifications = {}  # task_id -> {"question": str, "asked_at": ts}

        # 启动时把磁盘队列恢复到内存缓存
        self._restore_pending_queue_from_storage()
        
        util.log(1, f"[冒险者公会] ✅ 初始化完成,公会成员: {len(self.guild_members)}个")
        self._audit(
            action="guild_init",
            actor="system",
            result="ok",
            detail={"members": list(self.guild_members.keys())},
        )

    def _new_trace_id(self) -> str:
        return f"trace_{uuid.uuid4().hex[:12]}"

    def _new_correlation_id(self, task_id: str = "") -> str:
        prefix = str(task_id or "guild").replace(" ", "_")
        return f"{prefix}_{uuid.uuid4().hex[:10]}"

    def _audit(
        self,
        action: str,
        actor: str = "system",
        task_id: str = "",
        result: str = "ok",
        trace_id: str = "",
        correlation_id: str = "",
        detail: Optional[dict] = None,
    ) -> None:
        """统一审计打点，任何异常都不影响主流程。"""
        try:
            audit_logger = getattr(self, "audit", None)
            if not audit_logger:
                return
            audit_logger.append(
                action=action,
                actor=actor,
                task_id=task_id,
                result=result,
                trace_id=trace_id,
                correlation_id=correlation_id,
                detail=detail or {},
            )
        except Exception as e:
            util.log(2, f"[冒险者公会] 审计写入失败: {e}")

    def _resolve_task_trace_meta(self, task_data: Optional[dict], task_id: str = "") -> Tuple[str, str]:
        """统一读取/兜底任务trace元数据。"""
        task_data = task_data or {}
        trace_id = str(task_data.get("trace_id") or "").strip()
        correlation_id = str(task_data.get("correlation_id") or "").strip()
        if not trace_id:
            trace_id = self._new_trace_id()
        if not correlation_id:
            correlation_id = self._new_correlation_id(task_id)
        return trace_id, correlation_id

    def _ensure_guild_context_files(self) -> None:
        """确保公会上下文MD文件存在（成员列表/系统概览/路径索引等）"""
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.internal_dir.mkdir(parents=True, exist_ok=True)

        # 自动生成：成员列表 & 路径索引（每次启动更新）
        self._write_members_context()
        self._write_paths_context()

        # 用户可编辑的上下文文件（不存在则生成模板）
        self._ensure_context_file(
            "10_user_env.md",
            "# 用户环境信息（前脑生成）\n"
            "- 说明：由前脑系统或人工维护的用户环境信息。\n"
            "- 设备/系统：\n"
            "- 当前偏好/禁忌：\n"
            "- 近期目标/关注点：\n"
        )
        self._ensure_context_file(
            "20_stack.md",
            "# 智能体结构/技术栈\n"
            "- 说明：SmartSisi 的技术栈与模块边界。\n"
            "- 核心模块：\n"
            "- 主要服务：\n"
            "- 关键依赖：\n"
        )
        self._ensure_context_file(
            "30_system_overview.md",
            "# SISI 系统概览\n"
            "- 目标：\n"
            "- 角色：柳思思 / 柳叶\n"
            "- 运行方式：\n"
        )

    def _ensure_context_file(self, filename: str, content: str) -> None:
        path = self.context_dir / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    def _write_members_context(self) -> None:
        """生成公会成员列表MD（自动覆盖）"""
        target = self.internal_dir / "00_members.md"
        lines = [
            "# 公会成员列表",
            "",
            "（自动生成，请勿手动编辑）",
            ""
        ]
        for member_id, member in self.guild_members.items():
            lines.append(f"## {member.get('name', member_id)}")
            lines.append(f"- ID: {member_id}")
            lines.append(f"- 状态: {member.get('status', 'unknown')}")
            lines.append(f"- 类型: {member.get('type', 'agent')}")
            caps = member.get("capabilities", [])
            if caps:
                lines.append(f"- 能力: {', '.join(caps[:12])}")
            lines.append("")
        target.write_text("\n".join(lines), encoding="utf-8")

    def _write_paths_context(self) -> None:
        """生成系统路径索引MD（自动覆盖）"""
        project_root = Path(__file__).resolve().parent.parent
        try:
            cfg.load_config()
        except Exception:
            pass
        cache_root = Path(cfg.cache_root) if getattr(cfg, "cache_root", None) else (project_root / "cache_data")
        paths = [
            ("项目根目录", str(project_root)),
            ("系统配置", str(project_root / "system.conf")),
            ("运行配置", str(project_root / "config.json")),
            ("系统日志目录", str(project_root / "logs")),
            ("OPUS归档目录", str(project_root / "asr" / "archive")),
            ("临时录音WAV", str(cache_root / "tmp*.wav")),
            ("记忆向量库", str(project_root / "sisi_memory" / "data" / "chroma_db")),
            ("记忆历史库", str(project_root / "sisi_memory" / "data" / "sisi_memory_history.db")),
            ("对话事件流目录", str(project_root / "sisi_memory" / "data" / "chat_history")),
            ("角色摘要目录", str(project_root / "sisi_memory" / "data" / "chat_history" / "<user>" / "summary")),
            ("RVC根目录", r"E:\liusisi\sisi liu\rvc"),
            ("RVC模型目录", r"E:\liusisi\sisi liu\rvc\Applio-main\rvc"),
        ]
        lines = [
            "# 系统路径索引（常用）",
            "",
            "（自动生成，请勿手动编辑）",
            ""
        ]
        for name, path in paths:
            lines.append(f"- {name}: {path}")
        (self.context_dir / "40_paths.md").write_text("\n".join(lines), encoding="utf-8")

    def _build_guild_context(self) -> Tuple[str, List[str]]:
        """合并公会上下文（按文件名排序）"""
        self._write_members_context()
        self._write_paths_context()

        parts: List[str] = []
        used_files: List[str] = []
        allowlist = {
            "10_user_env.md",
            "20_stack.md",
            "30_system_overview.md",
            "40_paths.md"
        }
        for path in sorted(self.context_dir.glob("*.md"), key=lambda p: p.name):
            if path.name not in allowlist:
                continue
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            used_files.append(path.name)
            parts.append(f"## {path.name}\n{text}")
        if not parts:
            return "", []
        header = "【公会上下文】\n（以下为参考背景，不是任务指令；如冲突以【任务】为准）\n"
        context_text = header + "\n\n".join(parts) + "\n【公会上下文结束】"
        return context_text, used_files
    
    def _normalize_pending_queue(self, queue: List[Any]) -> List[Tuple[str, str]]:
        """标准化队列结构并按task_id去重（保留最后一次描述）。"""
        normalized: List[Tuple[str, str]] = []
        latest: Dict[str, str] = {}
        order: List[str] = []

        for item in queue or []:
            task_id = ""
            description = ""
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                task_id = str(item[0] or "").strip()
                description = str(item[1] or "").strip()
            elif isinstance(item, dict):
                task_id = str(item.get("task_id") or "").strip()
                description = str(item.get("description") or "").strip()

            if not task_id:
                continue
            if task_id not in latest:
                order.append(task_id)
            latest[task_id] = description

        for task_id in order:
            normalized.append((task_id, latest[task_id]))
        return normalized

    def _restore_pending_queue_from_storage(self) -> None:
        """把磁盘队列恢复到内存缓存，避免重启后任务丢失。"""
        disk_queue = self.storage.load_pending_queue()
        with self._queue_lock:
            merged = self._normalize_pending_queue(self.pending_tasks + disk_queue)
            self.pending_tasks = merged
            snapshot = list(self.pending_tasks)
        # 规范化后回写，清理历史重复项
        self.storage.save_pending_queue(snapshot)

    def _snapshot_pending_queue(self) -> List[Tuple[str, str]]:
        with self._queue_lock:
            return list(self.pending_tasks)

    def _queue_pending_task(self, task_id: str, description: str) -> None:
        """将任务加入待发送队列（内存缓存 + MD落盘）。"""
        with self._queue_lock:
            self.pending_tasks = [(tid, desc) for tid, desc in self.pending_tasks if tid != task_id]
            self.pending_tasks.append((task_id, description))
            snapshot = list(self.pending_tasks)
        self.storage.save_pending_queue(snapshot)

    def _remove_pending_task(self, task_id: str) -> bool:
        """从待发送队列删除任务并持久化。"""
        changed = False
        with self._queue_lock:
            before = len(self.pending_tasks)
            self.pending_tasks = [(tid, desc) for tid, desc in self.pending_tasks if tid != task_id]
            changed = len(self.pending_tasks) != before
            snapshot = list(self.pending_tasks)
        if changed:
            if snapshot:
                self.storage.save_pending_queue(snapshot)
            else:
                self.storage.clear_pending_queue()
        return changed

    def _clear_pending_task_queue(self) -> None:
        """清空待发送队列（内存 + MD）。"""
        with self._queue_lock:
            self.pending_tasks.clear()
        self.storage.clear_pending_queue()

    def _count_member_active_tasks(self, member_id: str) -> int:
        """统计某个成员当前手上的活（越少越优先）。"""
        active_count = 0
        for status in ("running", "pending", "waiting_clarification"):
            tasks = self.storage.list_tasks(status=status)
            active_count += sum(1 for t in tasks if t.get("assigned_to") == member_id)
        return active_count

    def _select_member_for_task(self, description: str, requested_member_id: str = "auto") -> Tuple[str, dict]:
        """按成员特点和当前负载分配任务。"""
        requested = str(requested_member_id or "auto").strip()
        if requested and requested != "auto" and requested in self.guild_members:
            member = self.guild_members[requested]
            if member.get("status") == "active":
                return requested, {
                    "mode": "manual",
                    "reason": f"用户指定成员: {requested}",
                    "scores": [{"member_id": requested, "score": 999}],
                }

        text = str(description or "")
        lower_text = text.lower()
        candidates = []

        for member_id, member in self.guild_members.items():
            if member.get("status") != "active":
                continue
            capabilities = [str(c or "") for c in member.get("capabilities", [])]
            capability_hits = 0
            for cap in capabilities:
                cap_norm = cap.strip().lower()
                if not cap_norm:
                    continue
                if cap_norm in lower_text or cap in text:
                    capability_hits += 1

            # 通用词轻量加分（防止只靠完整cap字符串匹配）
            keywords = ["代码", "搜索", "网页", "图片", "文件", "自动化", "任务", "分析"]
            keyword_hits = sum(1 for kw in keywords if kw in text)
            load = self._count_member_active_tasks(member_id)

            # 简单可解释评分：能力匹配越多越高，手上任务越少越高
            score = capability_hits * 6 + keyword_hits * 2 - load * 3
            candidates.append({
                "member_id": member_id,
                "score": score,
                "capability_hits": capability_hits,
                "keyword_hits": keyword_hits,
                "load": load,
            })

        if not candidates:
            return "openclaw", {
                "mode": "fallback",
                "reason": "没有可用成员，回退到openclaw",
                "scores": [],
            }

        candidates.sort(key=lambda x: (x["score"], -x["load"]), reverse=True)
        winner = candidates[0]
        reason = (
            f"自动分配给{winner['member_id']}：能力命中{winner['capability_hits']}条，"
            f"关键词命中{winner['keyword_hits']}个，当前负载{winner['load']}个。"
        )
        return winner["member_id"], {
            "mode": "auto",
            "reason": reason,
            "scores": candidates,
        }

    def _schedule_dispatch(self, trigger: str = "auto") -> None:
        """尝试异步派发队列任务（不阻塞主线程）。"""
        if not (self.listener_ready and self._event_loop):
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._dispatch_pending_tasks(trigger=trigger),
                self._event_loop
            )
        except Exception as e:
            util.log(2, f"[冒险者公会] 调度派发任务失败: {e}")

    async def _dispatch_pending_tasks(self, trigger: str = "auto") -> int:
        """批量派发待发送任务。只在连接就绪时工作。"""
        with self._queue_lock:
            if self._dispatching:
                return 0
            self._dispatching = True

        sent_count = 0
        try:
            while self.listener_ready and self.listener:
                snapshot = self._snapshot_pending_queue()
                if not snapshot:
                    break
                task_id, description = snapshot[0]

                task_data = self.storage.load_task(task_id) or {}
                trace_id, correlation_id = self._resolve_task_trace_meta(task_data, task_id)
                status = str(task_data.get("status") or "").strip()
                if status not in ("pending", "running"):
                    # 已经不需要执行了，直接从队列拿掉
                    self._remove_pending_task(task_id)
                    self._audit(
                        action="dispatch_skip",
                        actor="guild",
                        task_id=task_id,
                        result="skipped",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        detail={"reason": f"status={status}"},
                    )
                    continue

                assigned_to = str(task_data.get("assigned_to") or "openclaw").strip()
                if assigned_to != "openclaw":
                    util.log(2, f"[冒险者公会] 暂不支持成员 {assigned_to}，任务保留在待处理状态: {task_id}")
                    self._audit(
                        action="dispatch_blocked",
                        actor="guild",
                        task_id=task_id,
                        result="blocked",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        detail={"assigned_to": assigned_to, "trigger": trigger},
                    )
                    break

                ok = await self._send_task_to_openclaw(task_id, description)
                if not ok:
                    self._audit(
                        action="dispatch_send",
                        actor="guild",
                        task_id=task_id,
                        result="failed",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        detail={"trigger": trigger},
                    )
                    break
                self._remove_pending_task(task_id)
                sent_count += 1
                self._audit(
                    action="dispatch_send",
                    actor="guild",
                    task_id=task_id,
                    result="sent",
                    trace_id=trace_id,
                    correlation_id=correlation_id,
                    detail={"trigger": trigger},
                )

            if sent_count:
                util.log(1, f"[冒险者公会] 队列派发完成: {sent_count}个 (trigger={trigger})")
            return sent_count
        finally:
            with self._queue_lock:
                self._dispatching = False
    
    def _emit_event(self, event: dict) -> None:
        """向柳叶回调和SSE总线发布事件。"""
        if not isinstance(event, dict):
            return
        evt = dict(event)
        task_id = str(evt.get("task_id") or "").strip()
        if task_id and task_id != "guild":
            task_data = self.storage.load_task(task_id) or {}
            trace_id, correlation_id = self._resolve_task_trace_meta(task_data, task_id)
            evt.setdefault("trace_id", trace_id)
            evt.setdefault("correlation_id", correlation_id)
        evt.setdefault("ts", time.time())
        
        callbacks = []
        with self._subscriber_lock:
            callbacks = list(self._event_subscribers.values())
        
        for callback in callbacks:
            def _run(cb=callback):
                try:
                    cb(evt)
                except Exception as e:
                    util.log(3, f"[冒险者公会] 事件回调失败: {e}")
            threading.Thread(target=_run, daemon=True).start()
        
        # 发布到统一事件总线（供SSE等外部订阅）
        try:
            from evoliu.liuye_guild_integration import get_event_bus
            bus = get_event_bus()
            event_type = str(evt.get("type") or "guild")
            bus.publish("guild", evt)
            if event_type != "guild":
                bus.publish(event_type, evt)
        except Exception as e:
            util.log(2, f"[冒险者公会] 事件总线发布失败: {e}")
    
    def subscribe(self, callback: Callable[[dict], None]):
        """订阅公会事件（柳叶接口）。返回取消订阅函数。"""
        if not callable(callback):
            raise TypeError("callback must be callable")
        
        with self._subscriber_lock:
            self._subscriber_seq += 1
            subscriber_id = f"guild_sub_{self._subscriber_seq}"
            self._event_subscribers[subscriber_id] = callback
        
        util.log(1, f"[冒险者公会] 已注册事件订阅: {subscriber_id}")
        
        def _unsubscribe():
            self.unsubscribe(subscriber_id)
        
        return _unsubscribe
    
    def unsubscribe(self, subscriber) -> bool:
        """取消订阅。支持传入订阅ID或原始callback。"""
        with self._subscriber_lock:
            if isinstance(subscriber, str):
                if subscriber in self._event_subscribers:
                    self._event_subscribers.pop(subscriber, None)
                    return True
                return False
            
            # callback方式取消
            target_ids = [sid for sid, cb in self._event_subscribers.items() if cb == subscriber]
            for sid in target_ids:
                self._event_subscribers.pop(sid, None)
            return bool(target_ids)
    
    def ensure_listener_started(self) -> bool:
        """幂等启动监听线程。"""
        with self._listener_thread_lock:
            if self._listener_thread and self._listener_thread.is_alive():
                return True
            
            def run_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.start())
                except Exception as e:
                    util.log(3, f"[冒险者公会] 监听线程异常退出: {e}")
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass
            
            self._listener_thread = threading.Thread(
                target=run_async,
                name="guild-supervisor-listener",
                daemon=True,
            )
            self._listener_thread.start()
            util.log(1, "[冒险者公会] ✅ 监听线程已启动")
            self._audit(action="listener_start", actor="system", result="ok")
            return True
    
    # === 柳叶调用的接口 ===
    
    def submit_task(
        self,
        description: str,
        member_id: str = "auto",
        trace_id: str = "",
        source: str = "liuye",
    ) -> str:
        """柳叶提交任务
        
        Args:
            description: 任务描述
            member_id: 指定成员ID；默认auto表示由公会自动分配
        """
        task_id = f"task_{int(time.time())}_{id(description) % 1000}"
        assigned_member_id, routing = self._select_member_for_task(description, member_id)
        member = self.guild_members.get(assigned_member_id, self.guild_members["openclaw"])
        
        resolved_trace_id = str(trace_id or "").strip() or self._new_trace_id()
        correlation_id = self._new_correlation_id(task_id)

        task_data = {
            "task_id": task_id,
            "description": description,
            "status": "pending",
            "created_by": source or "liuye",
            "created_at": time.time(),
            "assigned_to": assigned_member_id,
            "member_name": member["name"],
            "openclaw_session_id": None,
            "result": None,
            "error": None,
            "analysis": None,
            "tool_calls": [],  # 工具调用记录
            "images": [],  # 图片记录
            "routing": routing,
            "trace_id": resolved_trace_id,
            "correlation_id": correlation_id,
        }
        
        # 保存到MD文件
        self.storage.save_task(task_id, task_data)

        # 队列优先：先入队落盘，再按连接状态尝试派发
        self._queue_pending_task(task_id, description)
        self.ensure_listener_started()
        self._schedule_dispatch(trigger="submit_task")

        util.log(
            1,
            f"[冒险者公会] 任务已入队: {task_id}, 分配给{member['name']} ({routing.get('mode', 'auto')})"
        )
        self._emit_event({
            "type": "progress",
            "task_id": task_id,
            "description": description,
            "progress": f"任务已提交并入队，{routing.get('reason', '等待公会执行')}",
            "status": "pending",
            "assigned_to": assigned_member_id,
            "trace_id": resolved_trace_id,
            "correlation_id": correlation_id,
        })
        self._audit(
            action="submit_task",
            actor=source or "liuye",
            task_id=task_id,
            result="queued",
            trace_id=resolved_trace_id,
            correlation_id=correlation_id,
            detail={
                "assigned_to": assigned_member_id,
                "member_name": member["name"],
                "routing": routing,
            },
        )
        return task_id
    
    def list_members(self) -> List[dict]:
        """列出所有公会成员"""
        members = []
        for member_id, member_info in self.guild_members.items():
            members.append({
                "id": member_id,
                "name": member_info["name"],
                "type": member_info["type"],
                "capabilities": member_info["capabilities"],
                "status": member_info["status"]
            })
        return members
    
    def cancel_task(self, task_id: str) -> bool:
        """柳叶撤销任务"""
        result = self.abort_task(task_id, reason="用户撤销任务")
        return bool(result.get("success"))
    
    def query_task(self, task_id: str, full: bool = False) -> Optional[Dict]:
        """柳叶查询任务
        
        Args:
            task_id: 任务ID
            full: 是否返回完整结果（默认False，只返回摘要）
        """
        if full:
            return self.storage.load_task_full(task_id)
        else:
            return self.storage.load_task(task_id)
    
    def query_status(self) -> dict:
        """柳叶查询公会整体状态"""
        recent_tasks = self.storage.list_tasks()[:10]
        
        if not recent_tasks:
            return {
                "health_score": {"score": 100, "level": "unknown"},
                "recent_tasks": [],
                "statistics": {"total": 0}
            }
        
        total = len(recent_tasks)
        successful = len([t for t in recent_tasks if t.get("status") == "completed"])
        failed = len([t for t in recent_tasks if t.get("status") == "failed"])
        
        success_rate = successful / total
        error_rate = failed / total
        health_score = int((success_rate * 70) + ((1 - error_rate) * 30))
        
        level = "excellent" if health_score >= 90 else "good" if health_score >= 70 else "fair" if health_score >= 50 else "poor"
        
        return {
            "health_score": {
                "score": health_score,
                "level": level,
                "success_rate": success_rate,
                "error_rate": error_rate
            },
            "recent_tasks": recent_tasks[:5],
            "statistics": {
                "total": total,
                "successful": successful,
                "failed": failed,
                "pending": len([t for t in recent_tasks if t.get("status") == "pending"]),
                "running": len([t for t in recent_tasks if t.get("status") == "running"])
            }
        }
    
    def get_status_summary(self) -> dict:
        """获取公会状态摘要（柳叶展示用）。"""
        try:
            members = list(self.guild_members.keys())
            running_tasks = self.storage.list_tasks(status="running")
            pending_tasks = self.storage.list_tasks(status="pending")
            completed_tasks = self.storage.list_tasks(status="completed")
            failed_tasks = self.storage.list_tasks(status="failed")
            failed_tasks += self.storage.list_tasks(status="error")
            failed_tasks += self.storage.list_tasks(status="cancelled")
            failed_tasks += self.storage.list_tasks(status="aborted")
            
            def _format_created_at(ts):
                try:
                    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    return ""
            
            def _format_duration(ts):
                try:
                    return f"{int(time.time() - ts)}s"
                except Exception:
                    return ""
            
            def _short_desc(text):
                text = text or ""
                return (text[:50] + "...") if len(text) > 50 else text
            
            running_tasks_out = [
                {
                    "task_id": t.get("task_id", ""),
                    "description": _short_desc(t.get("description", "")),
                    "member": t.get("assigned_to", "unknown"),
                    "created_at": _format_created_at(t.get("created_at")),
                    "duration": _format_duration(t.get("created_at")),
                }
                for t in running_tasks[:3]
            ]
            
            def _recent(tasks):
                tasks_sorted = sorted(tasks, key=lambda x: x.get("created_at", 0), reverse=True)
                return [
                    {
                        "created_at": _format_created_at(t.get("created_at")),
                        "description": _short_desc(t.get("description", "")),
                    }
                    for t in tasks_sorted[:3]
                ]
            
            return {
                "members": members,
                "running_count": len(running_tasks),
                "pending_count": len(pending_tasks),
                "completed_count": len(completed_tasks),
                "failed_count": len(failed_tasks),
                "running_tasks": running_tasks_out,
                "recent_completed": _recent(completed_tasks),
                "recent_failed": _recent(failed_tasks),
            }
        except Exception as e:
            util.log(3, f"[冒险者公会] 获取状态摘要失败: {e}")
            return {
                "members": [],
                "running_count": 0,
                "pending_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "running_tasks": [],
                "recent_completed": [],
                "recent_failed": [],
            }
    
    def get_members(self) -> list:
        """获取公会成员列表（柳叶展示用）。"""
        try:
            return [
                {
                    "id": member_id,
                    "name": member["name"],
                    "status": member["status"],
                    "capabilities": member["capabilities"][:5],
                }
                for member_id, member in self.guild_members.items()
            ]
        except Exception as e:
            util.log(3, f"[冒险者公会] 获取成员列表失败: {e}")
            return []
    
    def abort_task(self, task_id: str, reason: str = "用户主动停止") -> dict:
        """停止指定任务（同步更新状态 + 尝试下发chat.abort）。"""
        try:
            task_data = self.storage.load_task(task_id)
            if not task_data:
                self._audit(
                    action="abort_task",
                    actor="liuye",
                    task_id=task_id,
                    result="not_found",
                    detail={"reason": reason},
                )
                return {"success": False, "error": "任务不存在"}

            trace_id, correlation_id = self._resolve_task_trace_meta(task_data, task_id)
            task_data["status"] = "aborted"
            task_data["error"] = reason
            self.storage.save_task(task_id, task_data)
            
            # 从待发送队列移除并持久化
            self._remove_pending_task(task_id)
            
            # 停止远端会话
            session_id = self.task_session_map.pop(task_id, None)
            if session_id and self.listener and self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._abort_openclaw_session(session_id),
                    self._event_loop
                )
            
            # 清理run映射
            for run_id, mapped_task_id in list(self.run_task_map.items()):
                if mapped_task_id == task_id:
                    self.run_task_map.pop(run_id, None)
            
            self._pending_clarifications.pop(task_id, None)
            util.log(1, f"[冒险者公会] 任务已停止: {task_id}, reason={reason}")
            self._emit_event({
                "type": "failed",
                "task_id": task_id,
                "description": task_data.get("description", ""),
                "error": reason,
                "status": "aborted",
                "trace_id": trace_id,
                "correlation_id": correlation_id,
            })
            self._audit(
                action="abort_task",
                actor="liuye",
                task_id=task_id,
                result="ok",
                trace_id=trace_id,
                correlation_id=correlation_id,
                detail={"reason": reason},
            )
            return {"success": True, "task_id": task_id}
        except Exception as e:
            util.log(3, f"[冒险者公会] 停止任务失败: {e}")
            self._audit(
                action="abort_task",
                actor="liuye",
                task_id=task_id,
                result="error",
                detail={"reason": reason, "error": str(e)},
            )
            return {"success": False, "error": str(e)}
    
    def answer_clarification(self, task_id: str, answer: str) -> bool:
        """提交澄清回答并继续执行同一任务。"""
        answer_text = str(answer or "").strip()
        if not answer_text:
            return False
        
        task_data = self.storage.load_task(task_id)
        if not task_data:
            self._audit(
                action="answer_clarification",
                actor="liuye",
                task_id=task_id,
                result="not_found",
            )
            return False

        trace_id, correlation_id = self._resolve_task_trace_meta(task_data, task_id)
        question = str(task_data.get("clarifying_question") or "").strip()
        old_desc = str(task_data.get("description") or "").strip()
        if question:
            merged_desc = (
                f"{old_desc}\n\n"
                f"【澄清问题】\n{question}\n\n"
                f"【用户补充】\n{answer_text}"
            ).strip()
        else:
            merged_desc = f"{old_desc}\n\n【用户补充】\n{answer_text}".strip()
        
        task_data["description"] = merged_desc
        task_data["status"] = "pending"
        task_data["clarifying_question"] = ""
        task_data["clarification_answer"] = answer_text
        self.storage.save_task(task_id, task_data)
        self._pending_clarifications.pop(task_id, None)

        # 队列优先：先落盘入队，再调度派发
        self._queue_pending_task(task_id, merged_desc)
        self.ensure_listener_started()
        self._schedule_dispatch(trigger="clarification")
        
        self._emit_event({
            "type": "progress",
            "task_id": task_id,
            "description": old_desc,
            "progress": "已收到补充信息，任务继续执行",
            "status": "pending",
            "trace_id": trace_id,
            "correlation_id": correlation_id,
        })
        self._audit(
            action="answer_clarification",
            actor="liuye",
            task_id=task_id,
            result="ok",
            trace_id=trace_id,
            correlation_id=correlation_id,
            detail={"answer_len": len(answer_text)},
        )
        util.log(1, f"[冒险者公会] 澄清已提交并继续执行: {task_id}")
        return True
    
    def dissolve_guild(self, reason: str = "柳叶强制解散公会") -> dict:
        """强制停止全部任务并清空队列，进入待命状态。"""
        reason_text = str(reason or "柳叶强制解散公会").strip()
        guild_trace_id = self._new_trace_id()
        affected_task_ids = set()
        
        for status in ("running", "pending", "waiting_clarification"):
            for task in self.storage.list_tasks(status=status):
                task_id = str(task.get("task_id") or "").strip()
                if task_id:
                    affected_task_ids.add(task_id)
        
        # 队列中的任务也纳入
        for task_id, _ in self._snapshot_pending_queue():
            if task_id:
                affected_task_ids.add(task_id)
        
        aborted = []
        for task_id in sorted(affected_task_ids):
            ret = self.abort_task(task_id, reason=reason_text)
            if ret.get("success"):
                aborted.append(task_id)
        
        # 清空待发送队列和上下文
        self._clear_pending_task_queue()
        self._pending_clarifications.clear()
        
        # 兜底停止仍在映射中的远端会话
        leftover_sessions = list(self.task_session_map.items())
        for _, session_id in leftover_sessions:
            if session_id and self.listener and self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._abort_openclaw_session(session_id),
                    self._event_loop
                )
        self.task_session_map.clear()
        self.run_task_map.clear()
        
        self._emit_event({
            "type": "progress",
            "task_id": "guild",
            "progress": "公会已解散，全部任务已强制停止，等待新指令",
            "status": "idle",
            "aborted_tasks": aborted,
            "trace_id": guild_trace_id,
            "correlation_id": "guild_dissolve",
        })
        self._audit(
            action="dissolve_guild",
            actor="liuye",
            task_id="guild",
            result="ok",
            trace_id=guild_trace_id,
            correlation_id="guild_dissolve",
            detail={"reason": reason_text, "aborted_tasks": aborted},
        )
        util.log(1, f"[冒险者公会] 已强制解散，停止任务数: {len(aborted)}")
        return {
            "success": True,
            "aborted_count": len(aborted),
            "aborted_tasks": aborted,
            "status": "idle",
        }
    
    # === 内部方法 ===
    
    async def start(self):
        """启动公会监听"""
        util.log(1, "[冒险者公会] 正在启动WebSocket监听...")
        
        try:
            self.listener_running = True
            self._event_loop = asyncio.get_event_loop()  # 保存事件循环
            
            async with websockets.connect(self.openclaw_ws_url) as ws:
                self.listener = ws
                
                # 认证
                await self._authenticate(ws)
                
                # 标记连接就绪
                self.listener_ready = True
                util.log(1, "[冒险者公会] ✅ WebSocket监听已启动")
                self._audit(
                    action="listener_ready",
                    actor="system",
                    result="ok",
                    detail={"ws_url": self.openclaw_ws_url},
                )
                
                # 连接恢复后，先把磁盘队列恢复，再批量派发
                self._restore_pending_queue_from_storage()
                pending_count = len(self._snapshot_pending_queue())
                if pending_count:
                    util.log(1, f"[冒险者公会] 检测到待派发任务: {pending_count}个")
                await self._dispatch_pending_tasks(trigger="listener_ready")
                
                # 持续监听
                while self.listener_running:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(message)
                        await self._handle_message(data)
                    except asyncio.TimeoutError:
                        await self._dispatch_pending_tasks(trigger="heartbeat")
                        continue
                    except Exception as e:
                        util.log(3, f"[冒险者公会] 消息处理失败: {e}")
                        
        except Exception as e:
            util.log(3, f"[冒险者公会] WebSocket连接失败: {e}")
            self._audit(
                action="listener_error",
                actor="system",
                result="error",
                detail={"error": str(e)},
            )
        finally:
            self.listener_running = False
            self.listener_ready = False
            self.listener = None
            self._audit(action="listener_stopped", actor="system", result="ok")
    
    async def _authenticate(self, ws):
        """WebSocket认证 - 完整的OpenClaw协议"""
        # 1. 先接收connect.challenge事件
        challenge_msg = await ws.recv()
        challenge_data = json.loads(challenge_msg)
        
        if challenge_data.get("event") != "connect.challenge":
            raise Exception(f"期望connect.challenge,收到: {challenge_data.get('event')}")
        
        # 2. 从challenge中提取nonce(仅用于device认证,我们用token认证不需要)
        nonce = challenge_data.get("payload", {}).get("nonce")
        util.log(1, f"[冒险者公会] 收到challenge,nonce: {nonce}")
        
        # 3. 发送完整的connect请求(使用token认证,不用device)
        auth_message = {
            "type": "req",
            "id": "auth_guild",
            "method": "connect",
            "params": {
                "minProtocol": PROTOCOL_VERSION,  # 3
                "maxProtocol": PROTOCOL_VERSION,  # 3
                "client": {
                    "id": "gateway-client",  # 必须是OpenClaw定义的固定值
                    "displayName": "Guild Supervisor",
                    "version": "1.0.0",
                    "platform": "linux",  # OpenClaw在WSL上运行
                    "mode": "backend"  # backend模式
                },
                "caps": [],  # 空数组
                "auth": {
                    "token": self.openclaw_token  # 只有token,不要nonce
                },
                "role": "operator",
                "scopes": ["operator.admin"]
            }
        }
        
        await ws.send(json.dumps(auth_message))
        
        # 4. 接收认证响应
        response = await ws.recv()
        response_data = json.loads(response)
        
        if response_data.get("ok"):
            util.log(1, f"[冒险者公会] ✅ 认证成功")
        else:
            error = response_data.get("error", {})
            raise Exception(f"认证失败: {error.get('message', '未知错误')}")
    
    async def _send_task_to_openclaw(self, task_id: str, description: str) -> bool:
        """发送任务给OpenClaw。成功返回True，失败返回False。"""
        try:
            if not self.listener:
                return False

            task_data = self.storage.load_task(task_id)
            if not task_data:
                util.log(2, f"[冒险者公会] 跳过派发，任务不存在: {task_id}")
                return True

            trace_id, correlation_id = self._resolve_task_trace_meta(task_data, task_id)
            status = str(task_data.get("status") or "").strip()
            if status in ("aborted", "cancelled", "failed", "completed"):
                util.log(1, f"[冒险者公会] 跳过派发，任务已结束: {task_id} ({status})")
                return True
            
            # 生成幂等性键(防止重复提交)
            import uuid
            idempotency_key = str(uuid.uuid4())
            
            context_text, context_files = self._build_guild_context()
            full_message = description
            if context_text:
                full_message = f"{context_text}\n\n【任务】\n{description}"

            message = {
                "type": "req",
                "id": f"task_{task_id}",
                "method": "agent",
                "params": {
                    "message": full_message,
                    "sessionId": f"guild_{task_id}",
                    "sessionKey": f"guild_{task_id}",  # 添加sessionKey
                    "idempotencyKey": idempotency_key
                    # 不设置deliver,让OpenClaw正常发送
                }
            }
            
            await self.listener.send(json.dumps(message))
            
            # 更新任务状态
            task_data["status"] = "running"
            task_data["openclaw_session_id"] = f"guild_{task_id}"
            task_data["idempotency_key"] = idempotency_key
            task_data["context_files"] = context_files
            task_data["context_size"] = len(context_text)
            self.storage.save_task(task_id, task_data)
            
            self.task_session_map[task_id] = f"guild_{task_id}"
            
            util.log(1, f"[冒险者公会] 任务已发送: {task_id}")
            self._emit_event({
                "type": "progress",
                "task_id": task_id,
                "description": task_data.get("description", description),
                "progress": "任务已下发给冒险者，开始执行",
                "status": "running",
                "trace_id": trace_id,
                "correlation_id": correlation_id,
            })
            self._audit(
                action="task_sent",
                actor="guild",
                task_id=task_id,
                result="ok",
                trace_id=trace_id,
                correlation_id=correlation_id,
                detail={
                    "session_id": f"guild_{task_id}",
                    "idempotency_key": idempotency_key,
                    "context_files": context_files,
                },
            )
            return True
            
        except Exception as e:
            util.log(3, f"[冒险者公会] 发送任务失败: {e}")
            self._audit(
                action="task_sent",
                actor="guild",
                task_id=task_id,
                result="error",
                detail={"error": str(e)},
            )
            return False
    
    async def _abort_openclaw_session(self, session_id: str):
        """停止OpenClaw会话"""
        try:
            message = {
                "type": "req",
                "id": f"abort_{session_id}",
                "method": "chat.abort",
                "params": {"sessionKey": session_id}
            }
            
            await self.listener.send(json.dumps(message))
            util.log(1, f"[冒险者公会] 已发送停止指令: {session_id}")
            
        except Exception as e:
            util.log(3, f"[冒险者公会] 停止会话失败: {e}")
    
    async def _handle_message(self, data: dict):
        """处理OpenClaw消息 - 借鉴OpenClaw的事件结构"""
        msg_type = data.get("type")
        
        # 1. 处理事件(event)
        if msg_type == "event":
            event_name = data.get("event")
            payload = data.get("payload", {})
            
            util.log(1, f"[冒险者公会] 收到事件: {event_name}")
            
            # 调试: 打印完整payload
            if event_name == "agent":
                util.log(1, f"[冒险者公会] agent事件payload: {json.dumps(payload, ensure_ascii=False)[:200]}")
            
            # agent - 通用agent事件(包含lifecycle/assistant/tool/error stream)
            if event_name == "agent":
                await self._handle_agent_event(payload)
            
            # chat - 聊天事件(可能包含AI的回复)
            elif event_name == "chat":
                await self._handle_chat_event(payload)
            
            # tick - 心跳
            elif event_name == "tick":
                pass  # 忽略心跳
        
        # 2. 处理响应(response)
        elif msg_type == "res":
            req_id = data.get("id")
            ok = data.get("ok")
            
            if ok:
                util.log(1, f"[冒险者公会] 请求成功: {req_id}")
            else:
                error = data.get("error", {})
                util.log(3, f"[冒险者公会] 请求失败: {req_id} - {error.get('message', '未知错误')}")
    
    async def _handle_agent_event(self, payload: dict):
        """处理通用agent事件 - 收集所有stream信息并整合到MD文件"""
        # OpenClaw的agent事件结构: {runId, seq, stream, ts, data, sessionKey(可选)}
        run_id = payload.get("runId")
        stream = payload.get("stream")
        event_data = payload.get("data", {})
        session_key = payload.get("sessionKey")
        seq = payload.get("seq", 0)
        ts = payload.get("ts", time.time())
        
        # 查找task_id
        task_id = None
        if session_key:
            for tid, sid in self.task_session_map.items():
                if sid == session_key:
                    task_id = tid
                    break
        elif run_id:
            task_id = self.run_task_map.get(run_id)
        
        if not task_id:
            util.log(1, f"[冒险者公会] 未找到task_id - stream: {stream}, sessionKey: {session_key}, runId: {run_id}")
            return
        
        # 加载任务数据
        task_data = self.storage.load_task(task_id)
        if not task_data:
            util.log(3, f"[冒险者公会] 任务不存在: {task_id}")
            return
        trace_id, correlation_id = self._resolve_task_trace_meta(task_data, task_id)
        
        # 初始化stream记录
        if "streams" not in task_data:
            task_data["streams"] = {
                "lifecycle": [],
                "assistant": [],
                "tool": [],
                "error": [],
                "thinking": []
            }
        
        util.log(1, f"[冒险者公会] 收集 {stream} 事件 - task: {task_id}, seq: {seq}")
        
        # 根据stream类型收集信息
        if stream == "lifecycle":
            phase = event_data.get("phase")
            task_data["streams"]["lifecycle"].append({
                "seq": seq,
                "ts": ts,
                "phase": phase,
                "runId": run_id,
                "data": event_data
            })
            
            util.log(1, f"[冒险者公会] [lifecycle] phase={phase}, seq={seq}")
            
            # 建立runId映射
            if phase == "start" and run_id and session_key:
                self.run_task_map[run_id] = task_id
                util.log(1, f"[冒险者公会] [runId映射] {run_id} -> {task_id}")
            
            # 更新任务状态
            if phase == "start":
                if task_data.get("status") != "running":
                    task_data["status"] = "running"
                    self._emit_event({
                        "type": "progress",
                        "task_id": task_id,
                        "description": task_data.get("description", ""),
                        "progress": "冒险者已开始执行任务",
                        "status": "running",
                        "trace_id": trace_id,
                        "correlation_id": correlation_id,
                    })
                    self._audit(
                        action="lifecycle_start",
                        actor="openclaw",
                        task_id=task_id,
                        result="ok",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                    )
                util.log(1, f"[冒险者公会] [状态] 任务开始运行")
            elif phase == "end":  # ✅ OpenClaw发送end不是complete
                task_data["status"] = "completed"
                util.log(1, f"[冒险者公会] [完成] 任务完成，准备分析...")
                self._emit_event({
                    "type": "progress",
                    "task_id": task_id,
                    "description": task_data.get("description", ""),
                    "progress": "冒险者执行完成，正在汇总结果",
                    "status": "completed",
                    "trace_id": trace_id,
                    "correlation_id": correlation_id,
                })
                self._audit(
                    action="lifecycle_end",
                    actor="openclaw",
                    task_id=task_id,
                    result="ok",
                    trace_id=trace_id,
                    correlation_id=correlation_id,
                )
                # 先保存当前状态
                self.storage.save_task(task_id, task_data)
                util.log(1, f"[冒险者公会] [保存] 任务状态已保存，启动分析线程...")
                # 🔥 在后台线程中同步分析（避免异步任务丢失）
                import threading
                def analyze_in_thread():
                    util.log(1, f"[冒险者公会] [线程] 分析线程已启动")
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._analyze_and_summarize(task_id))
                    loop.close()
                    util.log(1, f"[冒险者公会] [线程] 分析线程已完成")
                
                thread = threading.Thread(target=analyze_in_thread, daemon=True)
                thread.start()
                util.log(1, f"[冒险者公会] [线程] 分析线程已创建并启动")
                return  # 提前返回，避免重复保存
            elif phase == "error":
                task_data["status"] = "failed"
                self._emit_event({
                    "type": "failed",
                    "task_id": task_id,
                    "description": task_data.get("description", ""),
                    "error": event_data.get("message", "任务执行失败"),
                    "status": "failed",
                    "trace_id": trace_id,
                    "correlation_id": correlation_id,
                })
                self._audit(
                    action="lifecycle_error",
                    actor="openclaw",
                    task_id=task_id,
                    result="error",
                    trace_id=trace_id,
                    correlation_id=correlation_id,
                    detail={"message": event_data.get("message", "任务执行失败")},
                )
                util.log(1, f"[冒险者公会] [错误] 任务失败")
        
        elif stream == "assistant":
            text = event_data.get("text", "")
            delta = event_data.get("delta", "")
            
            task_data["streams"]["assistant"].append({
                "seq": seq,
                "ts": ts,
                "text": text,
                "delta": delta
            })
            
            # 更新最终结果（累积所有text）
            if text:
                task_data["result"] = text
                util.log(1, f"[冒险者公会] ✅ AI输出更新: {len(text)}字")
        
        elif stream == "tool":
            tool_name = event_data.get("name", "")
            tool_args = event_data.get("args", {})
            tool_result = event_data.get("result")
            
            task_data["streams"]["tool"].append({
                "seq": seq,
                "ts": ts,
                "name": tool_name,
                "args": tool_args,
                "result": tool_result
            })
            
            # 更新工具调用记录
            if tool_name:
                if "tool_calls" not in task_data:
                    task_data["tool_calls"] = []
                task_data["tool_calls"].append({
                    "name": tool_name,
                    "args": tool_args,
                    "result": tool_result
                })
                util.log(1, f"[冒险者公会] 🛠️ 工具调用: {tool_name}")
        
        elif stream == "error":
            error_msg = event_data.get("message", "")
            error_code = event_data.get("code", "")
            
            task_data["streams"]["error"].append({
                "seq": seq,
                "ts": ts,
                "message": error_msg,
                "code": error_code,
                "data": event_data
            })
            
            task_data["error"] = error_msg
            task_data["status"] = "failed"
            self._emit_event({
                "type": "failed",
                "task_id": task_id,
                "description": task_data.get("description", ""),
                "error": error_msg or f"stream error: {error_code}",
                "status": "failed",
                "trace_id": trace_id,
                "correlation_id": correlation_id,
            })
            self._audit(
                action="stream_error",
                actor="openclaw",
                task_id=task_id,
                result="error",
                trace_id=trace_id,
                correlation_id=correlation_id,
                detail={"error": error_msg, "code": error_code},
            )
            util.log(3, f"[冒险者公会] ❌ 错误: {error_msg}")
        
        elif stream == "thinking":
            thinking_text = event_data.get("text", "")
            
            task_data["streams"]["thinking"].append({
                "seq": seq,
                "ts": ts,
                "text": thinking_text
            })
            
            util.log(1, f"[冒险者公会] 💭 思考: {thinking_text[:50]}...")
        
        # 保存到MD文件（每次都更新完整信息）
        self.storage.save_task(task_id, task_data)
        util.log(1, f"[冒险者公会] 📝 MD文件已更新: {task_id}")
    
    async def _handle_chat_event(self, payload: dict):
        """处理chat事件 - 提取多模态内容和工具调用"""
        util.log(1, f"[冒险者公会] chat事件payload: {json.dumps(payload, ensure_ascii=False)[:200]}")
        
        session_key = payload.get("sessionKey")
        message_obj = payload.get("message", {})
        
        if not session_key or not message_obj:
            return
        
        # 查找对应任务
        task_id = None
        for tid, sid in self.task_session_map.items():
            if sid == session_key:
                task_id = tid
                break
        
        if not task_id:
            return
        
        # 提取消息内容
        content = message_obj.get("content", [])
        if not isinstance(content, list):
            return
        
        # 解析多模态内容
        tool_calls = []
        images = []
        text_parts = []
        
        for item in content:
            item_type = item.get("type")
            
            if item_type == "text":
                text_parts.append(item.get("text", ""))
            
            elif item_type == "tool_use":
                tool_calls.append({
                    "name": item.get("name"),
                    "args": item.get("input", {})
                })
            
            elif item_type == "image":
                images.append({
                    "url": item.get("source", {}).get("data", "")[:100] + "...",  # 只保留前100字符
                    "description": "图片",
                    "size": f"{len(item.get('source', {}).get('data', ''))} bytes"
                })
        
        # 更新任务数据
        task_data = self.storage.load_task(task_id)
        if not task_data:
            return
        
        # 只在有新内容时更新
        if tool_calls:
            task_data["tool_calls"] = task_data.get("tool_calls", []) + tool_calls
        if images:
            task_data["images"] = task_data.get("images", []) + images
        
        self.storage.save_task(task_id, task_data)
        
        if tool_calls:
            util.log(1, f"[冒险者公会] 提取到{len(tool_calls)}个工具调用")
        if images:
            util.log(1, f"[冒险者公会] 提取到{len(images)}张图片")
    
    async def _analyze_and_summarize(self, task_id: str):
        """分析并汇总任务 - 调用大模型智能分析"""
        try:
            util.log(1, f"[冒险者公会] [分析] 开始分析任务: {task_id}")
            
            # 加载完整任务数据
            task_data = self.storage.load_task(task_id)
            if not task_data:
                util.log(3, f"[冒险者公会] [分析] 任务不存在: {task_id}")
                return
            trace_id, correlation_id = self._resolve_task_trace_meta(task_data, task_id)
            
            result = task_data.get('result') or ''
            streams = task_data.get('streams') or {}
            lifecycle_events = streams.get('lifecycle') or []
            
            util.log(1, f"[冒险者公会] [分析] 任务数据: status={task_data.get('status')}, result_len={len(result)}, lifecycle_events={len(lifecycle_events)}")
            
            # 构建session数据（兼容analyzer接口）
            session_data = {
                "session_id": task_data.get("openclaw_session_id"),
                "status": task_data.get("status"),
                "output": result,
                "tool_calls": task_data.get("tool_calls", []),
                "streams": streams
            }
            
            util.log(1, f"[冒险者公会] [分析] 调用大模型分析器...")
            
            # 调用大模型分析器
            analysis = self.analyzer.analyze_session(task_data, session_data)
            
            util.log(1, f"[冒险者公会] [分析] 分析器返回: {json.dumps(analysis, ensure_ascii=False)[:200]}")
            
            if "error" not in analysis:
                # 保存分析结果
                task_data["analysis"] = analysis
                
                # 若分析器返回澄清问题，则转入澄清状态
                question = str(
                    analysis.get("clarifying_question")
                    or analysis.get("question")
                    or ""
                ).strip()
                need_clarification = bool(analysis.get("need_clarification")) and bool(question)
                if need_clarification:
                    task_data["status"] = "waiting_clarification"
                    task_data["clarifying_question"] = question
                    self._pending_clarifications[task_id] = {
                        "question": question,
                        "asked_at": time.time(),
                    }
                    self.storage.save_task(task_id, task_data)
                    self._emit_event({
                        "type": "clarify",
                        "task_id": task_id,
                        "description": task_data.get("description", ""),
                        "question": question,
                        "status": "waiting_clarification",
                        "trace_id": trace_id,
                        "correlation_id": correlation_id,
                    })
                    self._audit(
                        action="analysis_clarify",
                        actor="guild_analyzer",
                        task_id=task_id,
                        result="need_clarification",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        detail={"question": question},
                    )
                    util.log(1, f"[冒险者公会] [分析] 需要澄清: {task_id}")
                    return
                
                self.storage.save_task(task_id, task_data)
                self._emit_event({
                    "type": "complete",
                    "task_id": task_id,
                    "description": task_data.get("description", ""),
                    "result": task_data.get("result"),
                    "analysis": analysis,
                    "status": task_data.get("status", "completed"),
                    "trace_id": trace_id,
                    "correlation_id": correlation_id,
                })
                self._audit(
                    action="analysis_complete",
                    actor="guild_analyzer",
                    task_id=task_id,
                    result="ok",
                    trace_id=trace_id,
                    correlation_id=correlation_id,
                    detail={"score": analysis.get("score"), "summary": analysis.get("summary", "")[:120]},
                )
                util.log(1, f"[冒险者公会] [分析] 分析完成并保存: {analysis.get('summary', '')[:50]}")
            else:
                util.log(3, f"[冒险者公会] [分析] 分析失败: {analysis.get('error')} (类型: {analysis.get('error_type')})")
                # 即使失败也保存错误信息
                task_data["analysis"] = analysis
                self.storage.save_task(task_id, task_data)
                self._emit_event({
                    "type": "failed",
                    "task_id": task_id,
                    "description": task_data.get("description", ""),
                    "error": analysis.get("error") or "分析失败",
                    "status": task_data.get("status", "failed"),
                    "trace_id": trace_id,
                    "correlation_id": correlation_id,
                })
                self._audit(
                    action="analysis_complete",
                    actor="guild_analyzer",
                    task_id=task_id,
                    result="error",
                    trace_id=trace_id,
                    correlation_id=correlation_id,
                    detail={"error": analysis.get("error"), "error_type": analysis.get("error_type")},
                )
                
        except Exception as e:
            util.log(3, f"[冒险者公会] [分析] 分析异常: {type(e).__name__}: {str(e)}")
            import traceback
            util.log(3, f"[冒险者公会] [分析] 堆栈: {traceback.format_exc()}")
            self._audit(
                action="analysis_exception",
                actor="guild_analyzer",
                task_id=task_id,
                result="error",
                detail={"error": str(e), "error_type": type(e).__name__},
            )
    

    
    def stop(self):
        """停止监听"""
        self.listener_running = False


# === 全局单例(借鉴LangGraph适配器模式) ===

_instance = None
_instance_lock = threading.Lock()


def get_instance() -> GuildSupervisorAgent:
    """获取公会监督器单例"""
    global _instance
    
    with _instance_lock:
        if _instance is None:
            _instance = GuildSupervisorAgent()
            util.log(1, "[冒险者公会] 创建全局单例")
    try:
        _instance.ensure_listener_started()
    except Exception as e:
        util.log(2, f"[冒险者公会] 自动启动监听失败: {e}")
    return _instance


# === 柳叶集成接口 ===

def handle_guild_command(user_input: str) -> Optional[str]:
    """处理公会指令 - 供柳叶调用
    
    返回:
        str: 如果是公会指令,返回回复; 否则返回None
    """
    supervisor = get_instance()
    
    # 1. 查询公会成员
    if any(kw in user_input for kw in ["公会成员", "有哪些成员", "成员列表", "谁在公会"]):
        members = supervisor.list_members()
        
        response = "公会成员列表:\n"
        for i, member in enumerate(members, 1):
            status_emoji = "✅" if member["status"] == "active" else "❌"
            capabilities = "、".join(member["capabilities"])
            response += f"{i}. {status_emoji} {member['name']} - {capabilities}\n"
        
        return response.strip()
    
    # 2. 提交任务(支持指定成员)
    if any(kw in user_input for kw in ["让openclaw", "交给openclaw", "openclaw帮我", "openclaw去"]):
        task_desc = user_input
        for kw in ["让openclaw", "交给openclaw", "openclaw帮我", "openclaw去"]:
            task_desc = task_desc.replace(kw, "").strip()
        
        if not task_desc:
            return "请告诉我要让OpenClaw做什么?"
        
        task_id = supervisor.submit_task(task_desc, member_id="openclaw")
        return f"好的,任务已交给OpenClaw!\n任务ID: {task_id}\n任务内容: {task_desc}\n\n随时问我'任务进度'查看执行情况。"
    
    # 3. 查询状态
    if any(kw in user_input for kw in ["任务进度", "openclaw在做什么", "openclaw状态", "公会状态"]):
        status = supervisor.query_status()
        health = status["health_score"]
        tasks = status["recent_tasks"]
        stats = status["statistics"]
        
        level_desc = {"excellent": "优秀", "good": "良好", "fair": "一般", "poor": "较差", "unknown": "未知"}
        
        response = f"""公会工作状态:
📊 健康评分: {health['score']}/100 ({level_desc.get(health['level'], '未知')})
✅ 成功率: {health['success_rate']*100:.1f}%
❌ 错误率: {health['error_rate']*100:.1f}%

📈 任务统计: 总{stats['total']} | 成功{stats['successful']} | 失败{stats['failed']} | 进行中{stats['running']}

📋 最近任务:
"""
        for i, task in enumerate(tasks[:3], 1):
            status_emoji = {"completed": "✅", "running": "🔄", "failed": "❌", "pending": "⏳", "cancelled": "🚫"}.get(task["status"], "❓")
            member_name = task.get("member_name", task.get("assigned_to", "未知"))
            response += f"{i}. {status_emoji} {task['task_id']} ({member_name}): {task['description'][:30]}...\n"
        
        return response.strip()
    
    # 4. 撤销任务
    if any(kw in user_input for kw in ["撤销任务", "取消任务"]):
        import re
        match = re.search(r'task_\d+', user_input)
        if not match:
            return "请告诉我要撤销哪个任务? (例如: 撤销任务task_001)"
        
        task_id = match.group(0)
        success = supervisor.cancel_task(task_id)
        return f"任务 {task_id} 已{'撤销' if success else '撤销失败'}。"
    
    # 5. 强制解散
    if any(kw in user_input for kw in ["解散公会", "强制停止公会", "全停公会", "停止所有任务"]):
        result = supervisor.dissolve_guild("用户口令触发强制解散")
        if result.get("success"):
            return f"公会已解散，已停止{result.get('aborted_count', 0)}个任务，等待新指令。"
        return "公会解散失败，请稍后重试。"
    
    return None


# === 启动函数 ===

def start_guild_supervisor():
    """启动公会监督器 - 后台线程"""
    supervisor = get_instance()
    supervisor.ensure_listener_started()
    util.log(1, "[冒险者公会] ✅ 后台线程已启动（幂等）")


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    supervisor = get_instance()
    task_id = supervisor.submit_task("搜索Python最佳实践")
    print(f"任务ID: {task_id}")
    
    time.sleep(2)
    status = supervisor.query_status()
    print(f"状态: {status}")


# === 柳叶集成别名函数 ===

def get_guild_instance() -> GuildSupervisorAgent:
    """获取公会实例（柳叶专用别名）"""
    return get_instance()


# 公会柳叶接口已内聚到 GuildSupervisorAgent 主类，移除动态注入。

util.log(1, "[冒险者公会] 模块加载完成，柳叶集成接口已就绪")
