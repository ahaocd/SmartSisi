"""
情感音乐生成工具 - A2A标准实现

基于Suno API的情感音乐生成工具，能够根据用户指令、对话历史、时间、日期、心情状态等
自动生成定制化提示词，然后生成符合用户情感需求的音乐作品。

特点：
1. 情感分析：分析用户对话历史和当前状态，提取情感关键词
2. 智能提示词：根据分析结果生成定制化音乐提示词
3. 高质量生成：通过Suno API生成专业级音乐作品
4. 自动下载：支持音乐自动下载功能（注意：自动播放功能已暂时禁用）
5. A2A标准：完全符合A2A协议标准
6. 随机主题：支持从多种Phonk音乐主题中随机选择
7. 灵感模式：支持使用随机主题和情绪生成独特音乐

## 🚀 **一键工作流 - 推荐使用**

**最简单的调用方式**：
```
from music_tool import create_music_now

# 一条命令搞定：生成→轮询→下载（自动播放已暂时禁用）
result = create_music_now("创作一首女声Phonk音乐")
```

**完整自动化工作流**：
1. ⚡ 自动生成音乐（默认女声Phonk风格）
2. ⏳ 自动轮询等待完成
3. ⬇️ 自动下载所有音频文件
4. 📊 返回完整结果信息

## 大模型使用指南

作为大语言模型，您可以通过以下方式调用这个工具来为用户生成音乐：

1. 基本调用方式：
```
from llm.a2a.tools.sisimusic.music_tool import run_music_workflow

# 生成音乐（会自动等待完成）
result = run_music_workflow("创作一首伤感的女声Phonk音乐")
```

2. 适用场景：
   - 用户请求生成特定情绪的音乐（如"我想听伤感的音乐"）
   - 用户想要特定风格的背景音乐（如"来点Phonk风格的音乐"）
   - 用户表达情绪需要音乐安抚（如"我今天很难过，想听点音乐"）
   - 用户只想听音乐而不指定风格（系统会随机主题和情绪）

3. 默认行为：
   - 随机主题：从赛车、蒸汽波、犯罪等Phonk常见主题中选择
   - 随机情绪：不再固定使用"伤感"，会随机选择不同情绪
   - 使用英文技术参数：如"cowbell rhythm"等专业音乐术语
   - 自动下载生成的音频文件（注：自动播放功能已暂时禁用）
   - 返回音乐文件路径和旁白文本供后续处理

4. 工作流程：
   - 接收用户请求 → 分析情感 → 生成提示词 → 调用API → 下载音频 → 生成旁白

5. 返回信息：
   - 音频文件路径：result.get("completion_result", {}).get("result", {}).get("downloaded_files", [])[0]
   - 旁白文本：result.get("summary", "")

注意：此工具需要有效的API密钥才能正常工作，生成过程可能需要数十秒到数分钟不等。
空查询时，系统会随机选择主题和情绪，而不再固定使用"伤感"情绪。
"""

# 🚀 一键工作流函数 - 推荐使用
def create_music_now(query: str = "创作一首女声Phonk音乐", wait_timeout: int = 300) -> dict:
    """
    🎵 一键音乐生成工作流 - 最简单的使用方式
    
    输入文本命令，自动完成：生成→轮询→下载→播放
    
    Args:
        query: 音乐生成指令，例如："创作一首女声Phonk音乐"
        wait_timeout: 最大等待时间（秒），默认5分钟
        
    Returns:
        dict: 完整结果
        {
            "status": "SUCCESS|FAILED|TIMEOUT",
            "downloaded_files": ["文件路径1", "文件路径2"],
            "played_file": "播放的文件路径",
            "narration": "AI旁白文本",
            "duration": "总耗时秒数",
            "clips_info": "歌曲详细信息"
        }
    """
    import time
    import uuid
    
    print(f"🎵 一键音乐生成启动")
    print(f"📝 指令: {query}")
    print(f"⏰ 最大等待: {wait_timeout}秒")
    print("="*50)
    
    start_time = time.time()
    
    try:
        # 创建工具实例
        generator = get_music_tool_instance()
        
        # 启动双重生成任务
        task = generator.run(
            query=query,
            emotion_state="伤感",  # 默认情感
            mode="dual_generation_with_selective_play"
        )
        
        task_id = task.get('task_id')
        if not task_id:
            return {
                "status": "FAILED",
                "error": "任务创建失败",
                "duration": time.time() - start_time
            }
        
        print(f"✅ 任务已提交: {task_id}")
        print(f"🎼 Phonk提示词: {task.get('phonk_prompt', '')[:100]}...")
        print(f"🎵 预期生成: {task.get('expected_clips', 0)} 首")
        
        # 轮询等待完成
        print(f"\n⏳ 开始轮询等待完成...")
        
        elapsed = 0
        check_interval = 10  # 每10秒检查一次
        
        while elapsed < wait_timeout:
            state = generator.get_task_state(task_id)
            status = state.get('status')
            
            print(f"⏱️  {elapsed}s/{wait_timeout}s - 状态: {status}")
            
            if status == "COMPLETED":
                result_data = state.get('result', {})
                downloaded_files = result_data.get('downloaded_files', [])
                played_file = result_data.get('played_file', '')
                narration = result_data.get('narration', '')
                
                end_time = time.time()
                duration = round(end_time - start_time, 1)
                
                print(f"\n🎉 音乐生成完成！")
                print(f"📁 下载文件数: {len(downloaded_files)}")
                print(f"🎵 播放文件: {played_file.split('/')[-1] if played_file else '无'}")
                print(f"⏱️  总耗时: {duration}秒")
                
                return {
                    "status": "SUCCESS",
                    "downloaded_files": downloaded_files,
                    "played_file": played_file,
                    "narration": narration,
                    "duration": duration,
                    "clips_info": result_data.get('phonk_clips', []),
                    "query": query
                }
                
            elif status == "FAILED":
                error = state.get('result', {}).get('error', '未知错误')
                print(f"\n❌ 任务失败: {error}")
                
                return {
                    "status": "FAILED",
                    "error": error,
                    "duration": time.time() - start_time
                }
            
            time.sleep(check_interval)
            elapsed += check_interval
        
        # 超时
        print(f"\n⚠️ 等待{wait_timeout}秒超时")
        print("💡 音乐可能仍在生成中，请稍后检查samples目录")
        
        return {
            "status": "TIMEOUT",
            "error": f"等待{wait_timeout}秒超时",
            "duration": time.time() - start_time,
            "task_id": task_id
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ 工作流执行失败: {error_msg}")
        
        return {
            "status": "FAILED",
            "error": error_msg,
            "duration": time.time() - start_time
        }

# 🎯 ESP32设备集成函数
def send_music_to_device(file_path: str, device_ip: str = None) -> bool:
    """
    发送音乐到ESP32设备播放
    
    Args:
        file_path: 音乐文件路径
        device_ip: ESP32设备IP地址
        
    Returns:
        bool: 发送成功/失败
    """
    try:
        if not device_ip:
            # 尝试从环境变量或配置文件获取
            import os
            device_ip = os.getenv("ESP32_IP", "192.168.1.100")
        
        import requests
        
        # 方法1: 发送文件URL
        esp32_url = f"http://{device_ip}/play_audio"
        
        with open(file_path, 'rb') as f:
            files = {'audio': f}
            response = requests.post(esp32_url, files=files, timeout=10)
            
            if response.status_code == 200:
                print(f"✅ 音乐已发送到ESP32设备: {device_ip}")
                return True
            else:
                print(f"❌ ESP32设备响应错误: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ 发送到ESP32设备失败: {str(e)}")
        return False

import os
import json
import time
import uuid
import logging
import requests
import datetime
import threading  # 添加threading导入
from typing import Dict, Any, Optional, List, Union, Literal
from pydantic import BaseModel
import re
import random
from SmartSisi.llm.agent import a2a_notification # 导入a2a通知模块
from SmartSisi.llm.agent.a2a_task_manager import get_instance as get_task_manager, TaskState # 导入
from SmartSisi.llm.transit_station import TransitStation # 新增导入 for TransitStation
import asyncio
import traceback  # 新增：导入traceback模块
from utils import util

# 配置logger - 避免重复日志
logger = logging.getLogger("music_generator")
# 只设置日志级别，不添加handler避免重复
logger.setLevel(logging.INFO)
# 防止日志向上传播造成重复
logger.propagate = False

# 获取当前目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 指定sisimusic目录路径
SISIMUSIC_DIR = os.path.join(CURRENT_DIR, "sisimusic")

# 在顶部导入部分添加随机模板模块导入（在导入SunoAPI之前）
import sys
sys.path.append(SISIMUSIC_DIR)
try:
    # 修复导入路径：sys.path.append后直接导入模块名
    from music_integration import get_enhanced_music_params
    random_template_available = True
    logger.info("成功导入随机模板模块")
except ImportError as e:
    random_template_available = False
    logger.error(f"导入随机模板模块失败: {str(e)}，将使用内置模板")

try:
    from suno_api import SunoAPI
    from config import API_KEY, BASE_URL, SAVE_DIR
    from task_manager import TaskManager
    logger.info("成功导入Suno API和相关模块")
except ImportError as e:
    logger.error(f"导入Suno API失败: {str(e)}")
    raise ImportError(f"无法导入Suno API模块，请确保sisimusic目录存在: {str(e)}")

# A2A标准响应格式
class ResponseFormat(BaseModel):
    """标准A2A响应格式"""
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str

# 情感关键词映射
EMOTION_KEYWORDS = {
    "伤感": [
        "思念", "离别", "孤独", "悲伤", "迷茫", "遗憾", "忧郁", "心碎", "怀念", 
        "凄凉", "流泪", "失落", "沉默", "痛苦", "酸楚", "惆怅", "寂寞"
    ],
    "快乐": [
        "喜悦", "快乐", "幸福", "开心", "兴奋", "欢笑", "愉悦", "欢乐", "满足", 
        "雀跃", "欣喜", "轻松", "朝气", "活力", "灿烂", "热情"
    ],
    "舞曲": [
        "动感", "节奏", "电音", "迪斯科", "夜店", "狂欢", "派对", "舞池", "律动",
        "嗨曲", "蹦迪", "躁动", "活力", "摇摆", "劲爆", "涌动"
    ],
    "女声": [
        "柔美", "空灵", "温婉", "甜美", "高亢", "婉转", "轻柔", "明亮", "细腻",
        "深情", "委婉", "娇柔", "磁性", "抒情", "动人"
    ],
    "朋克": [
        "叛逆", "反抗", "嘶吼", "噪音", "失真", "愤怒", "尖锐", "原始", "直接", 
        "粗糙", "高能", "冲击", "颠覆", "暴躁", "不羁", "鼓点", "吉他"
    ],
    "Phonk": [
        "复古", "采样", "低沉", "压抑", "节拍", "808", "Memphis", "慢速", "阴暗",
        "嘻哈", "trap", "低保真", "失真", "合成器", "怀旧", "VHS", "夜晚", "城市",
        "骚铃", "重低音", "侧链压缩", "Drift", "变调", "车载", "TWISTED风格", 
        "扭曲采样", "强烈冲击感", "空间感", "老式录音带", "中速BPM"
    ]
}

# 在EMOTION_KEYWORDS字典后添加PHONK_THEMES常量
PHONK_THEMES = [
    "夜间公路", "霓虹都市", "高速追逐", "漂移赛车", "城市夜景",     # 汽车/公路相关 (移除地下车库)
    "蒸汽波", "复古电子", "未来怀旧", "赛博朋克", "电子梦境",       # 蒸汽波/复古未来
    "午夜追逐", "城市阴影", "霓虹夜色", "街头文化", "都市节拍",     # 城市/街头 (移除黑帮犯罪)
    "电子幻境", "数字迷雾", "虚拟世界", "音波冲击", "节拍空间",     # 科技/音乐
    "深夜电台", "都市迷离", "午夜思念", "雨后街道", "霓虹反思"      # 情感/氛围
]

# 预设音乐风格定义
PRESET_STYLES = {
    "伤感女孩说唱Phonk": {
        "name": "伤感女孩说唱Phonk",
        "description": "DJ REMIX风格的Hardcore Phonk，带有攻击性女孩说唱元素，强烈的电音特征，明显的turntable效果和bass drops",
        "tags": "DJ phonk remix, hardcore phonk, aggressive bass, turntable scratches, female rap, 808 trap, club banger, breakbeats, bass drops, remix energy",
        "prompt_template": """创作一首DJ REMIX风格的Hardcore Phonk音乐，时长约45-60秒。

核心DJ特征：
- 明显的turntable scratches和record stop效果
- 攻击性808 bass配合重击breakbeats
- 强烈的bass drops和build-ups
- BPM 120-150高能节奏
- 重度sidechain compression产生pumping效果

女声特色：
- 攻击性女声说唱带Memphis口音和态度
- 声音经过大量autotune和失真处理
- 快速说唱delivery配合重型808模式
- 人声切片用作打击乐元素

音乐结构：
- 爆炸性开场配合DJ scratches
- 层次分明的build-up到bass drop
- 戏剧性速度变化和break sections
- 高潮部分的情感强度爆发

音效处理：
- 骚铃(cowbell)节奏配合唱盘效果
- 压缩动态范围获得最大冲击力
- 重度混响和延迟营造空间感
- 俱乐部就绪混音配合有力低频响应

情感表达：
- 黑暗都市夜生活氛围
- 攻击性忧郁和叛逆悲伤
- 在重型节拍下的情感释放

用户提示词: {user_query}
"""
    },
    "DJ Hardcore Phonk": {
        "name": "DJ Hardcore Phonk",
        "description": "极端硬核DJ Phonk，专注turntable技巧和club demolition效果",
        "tags": "hardcore DJ phonk, extreme bass, turntable mastery, club destroyer, aggressive remix, breakbeat fury",
        "prompt_template": """创作一首极端硬核DJ Phonk，专注于club demolition效果。

DJ技巧重点：
- 专业级turntable scratches和cuts
- 连续bass drops和trap elements  
- 极端立体声声像效果
- BPM 140-160超高能节奏

硬核元素：
- 破坏性808 bass和sub-bass
- 攻击性hi-hat连发模式
- 失真主音合成器配合aggressive filtering
- 压缩到极限的动态范围

用户提示词: {user_query}
"""
    }
    # 可以添加更多预设风格...
}

class MusicGeneratorTool:
    """音乐生成工具实现，符合A2A标准"""
    
    # 单例实例
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, api_key: str = None, *args, **kwargs):
        """确保只创建一个实例"""
        with cls._instance_lock:
            if cls._instance is None:
                logger.info("[MusicTool] 创建音乐工具单例实例")
                cls._instance = super(MusicGeneratorTool, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, api_key: str = None, *args, **kwargs):
        """初始化音乐生成工具"""
        # 避免重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            logger.info("[MusicTool] 使用现有音乐工具实例")
            return
            
        self.name = "music_generator"
        self.description = "基于Suno API的情感音乐生成工具，可根据用户情感状态生成定制化音乐"
        self.version = "1.0.0"
        self.task_states = {}  # 存储任务状态
        self.api = SunoAPI(api_key=API_KEY, base_url=BASE_URL)
        # 默认风格设置为伤感电音女孩Phonk
        self.default_style = "phonk"
        self.default_preset = "伤感女孩说唱Phonk"  # 设置默认预设风格
        # 支持的预设风格
        self.preset_styles = PRESET_STYLES
        
        # 🔥 新增：订阅机制初始化
        self.subscription_id = None
        self.last_subscription_time = 0
        self.is_subscribed = False
        
        # 标记为已初始化
        self._initialized = True
        
        # 自动启动订阅（延迟启动避免循环依赖）
        import threading
        threading.Timer(2.0, self._initialize_subscription).start()
        
        logger.info("[MusicTool] 音乐工具实例初始化完成")

    def _initialize_subscription(self):
        """初始化订阅机制 - 延迟启动避免循环依赖"""
        try:
            # 检查是否已经订阅过
            if hasattr(self, 'is_subscribed') and self.is_subscribed:
                logger.info("[MusicTool] 已订阅过音乐事件，跳过重复订阅")
                return
                
            # 注册到A2A工具管理器
            from SmartSisi.llm.agent.a2a_notification import get_tool_manager
            manager = get_tool_manager()
            
            # 确保工具管理器运行
            if not manager._running:
                manager.start()
                time.sleep(1)
            
            # 注册工具实例
            manager.register_tool("music_tool", self)
            logger.info("[MusicTool] 已注册到A2A工具管理器")
            
            # 订阅音乐生成完成事件（自己订阅自己的事件）
            subscription_result = self._subscribe_to_music_events()
            
            if subscription_result:
                self.is_subscribed = True
                logger.info("[MusicTool] 音乐事件订阅完成")
            
        except Exception as e:
            logger.error(f"[MusicTool] 初始化订阅机制失败: {str(e)}")

    def _subscribe_to_music_events(self):
        """订阅音乐生成完成事件"""
        try:
            from SmartSisi.llm.agent.a2a_notification import subscribe
            
            # 订阅音乐完成事件
            subscription_id = subscribe("music_tool", "event.music_completed", self._handle_music_completed)
            
            # 保存订阅ID
            self.subscription_id = subscription_id
            logger.info(f"[MusicTool] 订阅音乐完成事件，订阅ID: {subscription_id}")
            
            return subscription_id
            
        except Exception as e:
            logger.error(f"[MusicTool] 订阅音乐事件失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _handle_music_completed(self, task):
        """处理音乐生成完成任务"""
        try:
            logger.info(f"[MusicTool] 收到音乐完成事件: {task}")
            
            # 提取任务参数
            params = task.get("params", {})
            task_id = params.get("task_id")
            narration_text = params.get("narration_text")
            music_file_path = params.get("music_file_path")
            
            logger.info(f"[MusicTool] 处理音乐完成: 任务ID={task_id}, 旁白={narration_text[:50] if narration_text else 'None'}...")
            
            # 发送音乐旁白到中转站
            if narration_text and music_file_path:
                # 获取中转站并发送旁白
                self._send_music_narration_via_subscription_sync(narration_text, music_file_path, task_id)
                
        except Exception as e:
            logger.error(f"[MusicTool] 处理音乐完成任务失败: {str(e)}")

    def _send_music_narration_via_subscription_sync(self, narration_text, music_file_path, task_id):
        """通过订阅机制发送音乐旁白（同步版本）"""
        try:
            # 获取中转站实例
            from SmartSisi.llm.transit_station import get_transit_station
            transit = get_transit_station()
            
            if transit:
                # 构建音乐旁白通知
                music_notification = {
                    "source": "music_tool",
                    "content_type": "music_narration_result",
                    "for_optimization": True,
                    "is_tool_notification": True,
                    "content": {
                        "narration_text": narration_text,
                        "music_file_path": music_file_path,
                        "task_id": task_id,
                        "via_subscription": True  # 标记通过订阅机制发送
                    },
                    "metadata": {
                        "music_file": music_file_path,
                        "optimization_type": "music_narration",
                        "subscription_delivery": True
                    },
                    "timestamp": time.time()
                }
                
                # 发送到中转站
                success = transit.add_tool_notification(music_notification)
                
                if success:
                    logger.info(f"[MusicTool] ✅ 通过订阅机制成功发送音乐旁白")
                    logger.info(f"[MusicTool] 旁白: {narration_text[:50]}...")
                    logger.info(f"[MusicTool] 音乐: {music_file_path}")
                else:
                    logger.error(f"[MusicTool] ❌ 通过订阅机制发送音乐旁白失败")
                    
            else:
                logger.error(f"[MusicTool] 无法获取中转站实例")
                
        except Exception as e:
            logger.error(f"[MusicTool] 发送音乐旁白异常: {str(e)}")

    def _send_music_completion_event(self, task_id, narration_text, music_file_path):
        """发送音乐生成完成事件到A2A系统"""
        try:
            from SmartSisi.llm.agent.a2a_notification import send_task
            
            # 构建任务参数
            event_params = {
                "task_id": task_id,
                "narration_text": narration_text, 
                "music_file_path": music_file_path,
                "timestamp": time.time(),
                "status": "completed"
            }
            
            # 发送给自己的订阅者
            task_id = send_task("music_tool", "music_tool", "event.music_completed", event_params)
            
            logger.info(f"[MusicTool] 已发送音乐完成事件，任务ID: {task_id}")
            
        except Exception as e:
            logger.error(f"[MusicTool] 发送音乐完成事件失败: {str(e)}")
    
    def run(self, query: str, task_id: str = None, history: List[Dict] = None, time_info: Dict = None, emotion_state: str = None,
            mode: str = "dual_generation_with_selective_play", lyrics: str = None, title: str = None, tags: str = None):
        """
        运行音乐生成任务
        
        Args:
            query: 用户查询
            task_id: 任务ID，如果为空则自动生成
            history: 对话历史
            time_info: 时间信息
            emotion_state: 情感状态
            mode: 生成模式，默认"dual_generation_with_selective_play"(生成两首，下载两个，播放一个)
            lyrics: 自定义模式歌词内容
            title: 自定义模式歌曲标题
            tags: 自定义模式风格标签
            
        Returns:
            Dict: 任务信息
        """
        # 生成任务ID
        if not task_id:
            task_id = str(uuid.uuid4())
            
        # 初始化任务状态
        self.task_states[task_id] = {
            "status": "CREATED",
            "query": query,
            "result": None
        }
        
        # 修正：双重生成模式 - 利用Suno API默认生成2首歌的特性
        if mode == "dual_generation_with_selective_play":
            try:
                logger.info(f"[音乐生成] 双重生成模式：灵感模式和自定义模式并行生成")
                
                # 更新任务状态
                self.update_task_state(task_id, "PROCESSING", {"mode": "dual_generation_parallel", "query": query})
                
                # 🔧 修复：分别为两种模式生成不同的参数
                inspiration_params = None
                custom_params = None
                
                # 🎵 判断是否有自定义内容
                has_custom_content = lyrics and title
                
                if has_custom_content:
                    # 🔧 模式1：自定义模式 - 使用用户提供的歌词和标题
                    logger.info(f"[音乐生成] 检测到自定义内容，使用自定义模式")
                    
                    # 兼容增强版工具：不使用新增的参数
                    custom_description = self._generate_enhanced_phonk_prompt(query, emotion_state or "舞曲")
                    
                    custom_params = {
                        "lyrics": lyrics,
                        "title": title,
                        "tags": tags or "DJ phonk remix, hardcore phonk, aggressive bass, turntable scratches, female rap, 808 trap",
                        "mv": "chirp-auk"
                    }
                    
                    # 🔧 模式2：灵感模式 - 不用自定义内容，使用随机/增强模板
                    inspiration_description = self._generate_enhanced_phonk_prompt(query, emotion_state or "舞曲")
                    
                    inspiration_params = {
                        "description": inspiration_description,
                        "make_instrumental": False,
                        "mv": "chirp-auk"
                    }
                    
                    logger.info(f"[音乐生成] 双重模式: 自定义='{title}' + 灵感='{inspiration_description[:50]}...'")
                    
                else:
                    # 🔧 只使用灵感模式 - 系统自动生成所有内容
                    logger.info(f"[音乐生成] 无自定义内容，仅使用灵感模式")
                    inspiration_description = self._generate_enhanced_phonk_prompt(query, emotion_state or "舞曲")
                    
                    inspiration_params = {
                        "description": inspiration_description,
                        "make_instrumental": False,
                        "mv": "chirp-auk"
                    }
                    
                    logger.info(f"[音乐生成] 仅灵感模式: '{inspiration_description[:50]}...'")
                
                # 🚀 调用API生成音乐
                if custom_params:
                    # 同时使用两种模式
                    logger.info(f"[音乐生成] 启动自定义模式: {custom_params['title']}")
                    response = self.api.generate_music_custom(
                        lyrics=custom_params["lyrics"],
                        title=custom_params["title"],
                        tags=custom_params["tags"],
                        mv=custom_params["mv"]
                    )
                else:
                    # 只使用灵感模式
                    logger.info(f"[音乐生成] 启动灵感模式")
                    response = self.api.generate_music_inspiration(
                        description=inspiration_params["description"],
                        make_instrumental=inspiration_params["make_instrumental"],
                        mv=inspiration_params["mv"]
                    )
                
                if not response or response.get('code') != 'success':
                    error_msg = response.get('message', 'API调用失败') if response else 'API响应为空'
                    logger.error(f"[音乐生成] 灵感模式生成失败: {error_msg}")
                    self.update_task_state(task_id, "FAILED", {"error": error_msg})
                    return {"status": "FAILED", "error": error_msg}
                
                suno_data = response.get('data')
                if not suno_data:
                    error_msg = "未能获取Suno任务数据"
                    logger.error(f"[音乐生成] {error_msg}")
                    self.update_task_state(task_id, "FAILED", {"error": error_msg})
                    return {"status": "FAILED", "error": error_msg}
                
                # 从返回数据中提取clips信息
                clips = []
                if isinstance(suno_data, dict):
                    if 'clips' in suno_data:
                        clips = suno_data['clips']
                    elif 'id' in suno_data:
                        clips = [{"id": suno_data['id']}]
                else:
                    clips = [{"id": str(suno_data)}]
                
                if not clips:
                    error_msg = "未能从API响应中提取歌曲信息"
                    logger.error(f"[音乐生成] {error_msg}")
                    self.update_task_state(task_id, "FAILED", {"error": error_msg})
                    return {"status": "FAILED", "error": error_msg}
                
                logger.info(f"[音乐生成] 主要模式启动成功，获得{len(clips)}首歌曲")
                
                # 保存任务信息
                task_info = {
                    "inspiration_params": inspiration_params,
                    "custom_params": custom_params,
                    "clips": clips,
                    "suno_response": suno_data,
                    "expected_clips": len(clips)
                }
                self.task_states[task_id]["task_info"] = task_info
                
                # 启动任务处理
                import threading
                thread = threading.Thread(
                    target=self._handle_dual_clips_from_single_api,
                    args=(task_id, suno_data)
                )
                thread.daemon = True
                thread.start()
                
                # 构建返回消息
                active_description = ""
                if custom_params:
                    active_description = f"自定义: '{custom_params['title']}' + 灵感模式"
                else:
                    active_description = inspiration_params["description"][:50] + "..."
                
                return {
                    "status": "PROCESSING",
                    "task_id": task_id,
                    "message": f"增强DJ remix Phonk生成已启动：{active_description}，获得{len(clips)}首歌曲",
                    "phonk_features": "turntable scratches, aggressive bass, breakbeats, DJ effects",
                    "mode_used": "自定义+灵感双重模式" if custom_params else "仅灵感模式",
                    "custom_title": custom_params["title"] if custom_params else "系统自动生成（包括歌词）",
                    "expected_clips": len(clips),
                    "mode_explanation": "使用自定义歌词和灵感描述生成两种不同风格" if custom_params else "仅使用灵感模式，系统自动生成歌词"
                }
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"[音乐生成] 双重生成模式运行期间发生错误: {error_msg}")
                import traceback
                logger.error(f"[音乐生成] 错误详情: {traceback.format_exc()}")
                
                self.update_task_state(task_id, "FAILED", {"error": error_msg})
                return {"status": "FAILED", "error": error_msg}
        
        # 简化模式：直接使用sisimusic的功能
        elif mode == "simple_dual":
            # 简化双重生成：生成两首歌，只播放第一首
            try:
                logger.info(f"[音乐生成] 简化双重生成模式：使用4.5版本")
                
                # 使用随机主题和情绪
                random_theme = random.choice(PHONK_THEMES)
                emotions = ["舞曲", "快乐", "忧郁", "孤独", "愤怒", "狂躁", "神秘", "平静", "期待"]
                random_emotion = random.choice(emotions)
                
                logger.info(f"[音乐生成] 随机选择了灵感主题: {random_theme} 和情绪: {random_emotion}")
                
                # 任务1：灵感模式（会播放）
                description_prompt = f"{random_theme} {random_emotion} female vocals phonk"
                logger.info(f"[音乐生成] 灵感模式参数: {description_prompt}")
                response1 = self.api.generate_music_inspiration(description_prompt)
                
                if response1 and response1.get('code') == 'success':
                    suno_task_id1 = response1.get('data')
                    
                    # 使用TaskManager处理（会自动播放）
                    import threading
                    thread1 = threading.Thread(
                        target=TaskManager.poll_task_status,
                        args=(task_id + "_play", suno_task_id1, self.api, self.update_task_state)
                    )
                    thread1.daemon = True
                    thread1.start()
                    
                    # 任务2：优化Phonk（静默下载）
                    time.sleep(2)
                    response2 = self.api.generate_phonk_optimized(query, lyrics, title)
                    
                    if response2 and response2.get('code') == 'success':
                        suno_task_id2 = response2.get('data')
                        
                        # 静默处理（不播放）
                        thread2 = threading.Thread(
                            target=self._simple_silent_download,
                            args=(suno_task_id2,)
                        )
                        thread2.daemon = True
                        thread2.start()
                    
                    # 🎯 LG系统兼容格式：返回COMPLETED状态阻止循环调用
                    lg_compatible_result = {
                        "status": "COMPLETED",  # 改为COMPLETED，让LG系统认为任务已完成
                        "result": "正在为您创作音乐，这需要大约2分钟时间。AI正在精心调配旋律、和声和节奏，请稍等片刻...",
                        "task_id": task_id,
                        "async_mode": True,  # 标记为异步模式
                        "notification_via": "TransitStation",  # 通过TransitStation通知完成
                        "original_status": "PROCESSING"  # 保留原始状态信息
                    }
                    return lg_compatible_result
                else:
                    return {"status": "FAILED", "error": "生成失败"}
                    
            except Exception as e:
                return {"status": "FAILED", "error": str(e)}
                
        elif mode == "phonk_optimized":
            # 优化Phonk模式：使用专门的Phonk生成方法
            try:
                # 添加简单日志
                logger.info(f"[音乐生成] 开始调用优化Phonk API生成音乐")
                
                # 更新任务状态
                self.update_task_state(task_id, "PROCESSING", {"mode": "phonk_optimized", "query": query})
                
                # 调用优化的Phonk生成方法
                response = self.api.generate_phonk_optimized(query, lyrics, title)
                
                # 检查API响应
                if not response:
                    self.update_task_state(task_id, "FAILED", {"error": "API响应为空"})
                    return {"status": "FAILED", "error": "API响应为空"}
                    
                # 检查任务是否创建成功
                if response.get('code') == 'success':
                    suno_task_id = response.get('data')
                    
                    if not suno_task_id:
                        self.update_task_state(task_id, "FAILED", {"error": "未能获取任务ID"})
                        return {"status": "FAILED", "error": "未能获取任务ID"}
                        
                    # 保存任务ID
                    self.task_states[task_id]["suno_task_id"] = suno_task_id
                    
                    logger.info(f"[音乐生成] 优化Phonk任务已创建 ({suno_task_id})")
                    
                    # 启动后台线程轮询任务状态
                    import threading
                    task_manager = TaskManager()
                    thread = threading.Thread(
                        target=task_manager.poll_task_status,
                        args=(task_id, suno_task_id, self.api, self.update_task_state)
                    )
                    thread.daemon = True
                    thread.start()
                    
                    # 🎯 LG系统兼容格式：返回COMPLETED状态阻止循环调用
                    lg_compatible_result = {
                        "status": "COMPLETED",  # 改为COMPLETED，让LG系统认为任务已完成
                        "result": "正在为您创作phonk风格的音乐，这需要大约2分钟时间。AI正在精心调配旋律、和声和节奏，请稍等片刻...",
                        "task_id": task_id,
                        "suno_task_id": suno_task_id,
                        "mode": "phonk_optimized",
                        "async_mode": True,  # 标记为异步模式
                        "notification_via": "TransitStation",  # 通过TransitStation通知完成
                        "original_status": "PROCESSING"  # 保留原始状态信息
                    }
                    return lg_compatible_result
                else:
                    error = response.get('message', '')
                    logger.error(f"[音乐生成] 创建优化Phonk任务失败: {error}")
                    
                    self.update_task_state(task_id, "FAILED", {"error": error if error else "未知错误"})
                    return {"status": "FAILED", "error": error if error else "API创建任务失败"}
                    
            except Exception as e:
                error_msg = str(e)
                # 记录详细错误
                import traceback
                logger.error(f"[音乐生成] 优化Phonk模式运行期间发生错误: {error_msg}")
                logger.error(f"[音乐生成] 错误详情: {traceback.format_exc()}")
                
                self.update_task_state(task_id, "FAILED", {"error": error_msg})
                return {"status": "FAILED", "error": error_msg}
                
        elif mode == "inspiration":
            # 灵感模式：使用随机主题和情绪
            random_theme = random.choice(PHONK_THEMES)
            emotions = ["舞曲", "快乐", "忧郁", "孤独", "愤怒", "狂躁", "神秘", "平静", "期待"]
            random_emotion = random.choice(emotions)
            
            logger.info(f"[音乐生成] 随机选择了灵感主题: {random_theme} 和情绪: {random_emotion}")
            
            # 构建灵感模式参数
            description_prompt = f"{random_theme} {random_emotion} female vocals phonk"
            
            # 记录提示词
            self.task_states[task_id]["prompt"] = description_prompt
            
            try:
                # 添加简单日志
                logger.info(f"[音乐生成] 开始调用Suno API生成音乐，使用灵感主题: {random_theme}")
                
                # 更新任务状态
                self.update_task_state(task_id, "PROCESSING", {"prompt": description_prompt})
                
                # 调用API生成音乐 - 直接传递字符串而不是字典
                response = self.api.generate_music_inspiration(description_prompt)
                
                # 记录API响应结果
                if response:
                    logger.info(f"[音乐生成] API响应成功: {response.get('code', 'unknown')}")
                else:
                    logger.error("[音乐生成] API响应为空")
                
                # 检查API响应
                if not response:
                    self.update_task_state(task_id, "FAILED", {"error": "API响应为空"})
                    return {"status": "FAILED", "error": "API响应为空"}
                    
                # 检查任务是否创建成功
                if response.get('code') == 'success':
                    suno_task_id = response.get('data')
                    
                    if not suno_task_id:
                        self.update_task_state(task_id, "FAILED", {"error": "未能获取任务ID"})
                        return {"status": "FAILED", "error": "未能获取任务ID"}
                        
                    # 保存任务ID
                    self.task_states[task_id]["suno_task_id"] = suno_task_id
                    
                    logger.info(f"[音乐生成] 任务已创建 ({suno_task_id})")
                    
                    # 启动后台线程轮询任务状态
                    import threading
                    task_manager = TaskManager()
                    thread = threading.Thread(
                        target=task_manager.poll_task_status,
                        args=(task_id, suno_task_id, self.api, self.update_task_state)
                    )
                    thread.daemon = True
                    thread.start()
                    
                    # 🎯 LG系统兼容格式：返回COMPLETED状态阻止循环调用
                    lg_compatible_result = {
                        "status": "COMPLETED",  # 改为COMPLETED，让LG系统认为任务已完成
                        "result": f"正在为您创作{random_theme}风格的音乐，这需要大约2分钟时间。AI正在精心调配旋律、和声和节奏，请稍等片刻...",
                        "task_id": task_id,
                        "suno_task_id": suno_task_id,
                        "prompt": description_prompt,
                        "theme": random_theme,
                        "emotion": random_emotion,
                        "async_mode": True,  # 标记为异步模式
                        "notification_via": "TransitStation",  # 通过TransitStation通知完成
                        "original_status": "PROCESSING"  # 保留原始状态信息
                    }
                    return lg_compatible_result
                else:
                    error = response.get('message', '')
                    logger.error(f"[音乐生成] 创建任务失败: {error}")
                    
                    self.update_task_state(task_id, "FAILED", {"error": error if error else "未知错误"})
                    return {"status": "FAILED", "error": error if error else "API创建任务失败"}
                    
            except Exception as e:
                error_msg = str(e)
                # 记录详细错误
                import traceback
                logger.error(f"[音乐生成] 运行期间发生错误: {error_msg}")
                logger.error(f"[音乐生成] 错误详情: {traceback.format_exc()}")
                
                self.update_task_state(task_id, "FAILED", {"error": error_msg})
                return {"status": "FAILED", "error": error_msg}
        
        elif mode == "custom":
            # 自定义模式：使用提供的参数
            if not title:
                title = f"我的{emotion_state or '伤感'}音乐"
                
            # 默认使用Phonk风格标签
            if not tags:
                tags = "phonk, female vocals, emotional, electronic"
                
            # 如果没有提供歌词，从查询生成简单歌词
            if not lyrics:
                lyrics = self._generate_simple_lyrics(query, emotion_state)
                
            try:
                # 更新任务状态
                self.update_task_state(task_id, "PROCESSING", {
                    "mode": "custom",
                    "title": title,
                    "tags": tags,
                    "lyrics": lyrics
                })
                
                # 调用API生成音乐
                response = self.api.generate_music_custom(
                    lyrics=lyrics,
                    title=title,
                    tags=tags,
                    make_instrumental=False
                )
                
                # 检查API响应
                if not response:
                    self.update_task_state(task_id, "FAILED", {"error": "API响应为空"})
                    return {"status": "FAILED", "error": "API响应为空"}
                    
                # 检查任务是否创建成功
                if response.get('code') == 'success':
                    suno_task_id = response.get('data')
                    
                    if not suno_task_id:
                        self.update_task_state(task_id, "FAILED", {"error": "未能获取任务ID"})
                        return {"status": "FAILED", "error": "未能获取任务ID"}
                        
                    # 保存任务ID
                    self.task_states[task_id]["suno_task_id"] = suno_task_id
                    
                    logger.info(f"[音乐生成] 任务已创建 ({suno_task_id})")
                    
                    # 启动后台线程轮询任务状态
                    import threading
                    task_manager = TaskManager()
                    thread = threading.Thread(
                        target=task_manager.poll_task_status,
                        args=(task_id, suno_task_id, self.api, self.update_task_state)
                    )
                    thread.daemon = True
                    thread.start()
                    
                    # 🎯 LG系统兼容格式：返回COMPLETED状态阻止循环调用
                    lg_compatible_result = {
                        "status": "COMPLETED",  # 改为COMPLETED，让LG系统认为任务已完成
                        "result": f"正在为您创作《{title}》，这需要大约2分钟时间。AI正在精心调配旋律、和声和节奏，请稍等片刻...",
                        "task_id": task_id,
                        "suno_task_id": suno_task_id,
                        "mode": "custom",
                        "title": title,
                        "tags": tags,
                        "lyrics": lyrics,
                        "async_mode": True,  # 标记为异步模式
                        "notification_via": "TransitStation",  # 通过TransitStation通知完成
                        "original_status": "PROCESSING"  # 保留原始状态信息
                    }
                    return lg_compatible_result
                else:
                    error = response.get('message', '未知错误')
                    logger.error(f"[音乐生成] 创建任务失败: {error}")
                    
                    self.update_task_state(task_id, "FAILED", {"error": error})
                    return {"status": "FAILED", "error": error}
                    
            except Exception as e:
                error_msg = str(e)
                # 记录详细错误
                import traceback
                logger.error(f"[音乐生成] 运行期间发生错误: {error_msg}")
                logger.error(f"[音乐生成] 错误详情: {traceback.format_exc()}")
                
                self.update_task_state(task_id, "FAILED", {"error": error_msg})
                return {"status": "FAILED", "error": error_msg}
        
        else:
            error_msg = f"不支持的模式: {mode}"
            logger.error(f"[音乐生成] {error_msg}")
            self.update_task_state(task_id, "FAILED", {"error": error_msg})
            return {"status": "FAILED", "error": error_msg}
    
    def _play_audio(self, file_path: str):
        """
        播放音频文件并生成旁白（暂时禁用自动播放）
        
        Args:
            file_path: 音频文件路径
        """
        try:
            # 注释掉自动播放代码
            """
            # 播放音频
            import os
            if os.name == 'nt':  # Windows系统
                os.system(f'start {file_path}')
            elif os.name == 'posix':  # Linux/Mac系统
                os.system(f'open {file_path}')
            """
            logger.info(f"[音乐生成] 自动播放功能已禁用，文件路径: {file_path}")
            
            # 生成旁白 - 通过TaskManager的正确流程
            
            # 生成旁白 - 通过TaskManager的正确流程
            narration = TaskManager.generate_music_narration(file_path)
            logger.info(f"[音乐生成] 音乐旁白: {narration}")
            return narration
            
        except Exception as e:
            logger.error(f"[音乐生成] 播放音频失败: {str(e)}")
            return ""
    
    def _generate_music_prompt(self, query: str, history: List[Dict] = None, time_info: Dict = None, emotion_state: str = None) -> str:
        """
        生成音乐提示词 - 优化Phonk特征
        
        Args:
            query: 用户查询
            history: 对话历史
            time_info: 时间信息
            emotion_state: 指定的情感状态
            
        Returns:
            str: 提示词
        """
        # 如果查询为空或非常简短，优先使用随机模板
        if not query or len(query.strip()) < 5:
            if random_template_available:
                try:
                    # 随机选择情绪
                    emotions = ["舞曲", "快乐", "忧郁", "孤独", "愤怒", "狂躁", "神秘", "平静", "期待"]
                    random_emotion = random.choice(emotions)
                    logger.info(f"[音乐生成] 随机选择了情绪: {random_emotion}")
                    
                    # 使用随机模板
                    enhanced_params = get_enhanced_music_params(
                        query="随机Phonk音乐",
                        history=history,
                        time_info=time_info,
                        emotion_state=random_emotion,  # 使用随机情绪而非硬编码"伤感"
                        include_fortune=True
                    )
                    logger.info(f"[音乐生成] 空查询使用随机模板生成提示词")
                    # 返回随机生成的提示词
                    return enhanced_params["prompt"]
                except Exception as e:
                    logger.error(f"[音乐生成] 使用随机模板失败: {str(e)}，回退到默认预设")

        # 如果随机模板不可用或失败，使用默认预设
        logger.info(f"[音乐生成] 使用默认预设: {self.default_preset}")
        preset_style = self.preset_styles.get(self.default_preset)
        if preset_style:
            return preset_style["prompt_template"].format(user_query="自动生成默认风格")
        
        # 检查是否是请求使用预设风格
        preset_style = None
        for style_name, style_info in self.preset_styles.items():
            if style_name in query or "伤感女孩说唱Phonk" in query or "伤感女孩说唱" in query or "女孩说唱Phonk" in query:
                preset_style = style_info
                logger.info(f"[音乐生成] 使用预设风格: {style_name}")
                break
        
        # 如果没有匹配到特定预设但查询没有明确风格指示，优先使用随机模板
        if not preset_style and not any(style in query.lower() for style in ["舞曲", "摇滚", "古典", "流行", "电子", "爵士"]):
            if random_template_available:
                try:
                    # 使用随机模板
                    enhanced_params = get_enhanced_music_params(
                        query=query,
                        history=history,
                        time_info=time_info,
                        emotion_state=emotion_state or "伤感",
                        include_fortune=True
                    )
                    logger.info(f"[音乐生成] 未检测到明确风格，使用随机模板")
                    return enhanced_params["prompt"]
                except Exception as e:
                    logger.error(f"[音乐生成] 使用随机模板失败: {str(e)}，回退到默认预设")
            
            logger.info(f"[音乐生成] 未检测到明确风格，使用默认预设: {self.default_preset}")
            preset_style = self.preset_styles.get(self.default_preset)
                
        # 如果匹配到了预设风格，使用预设模板
        if preset_style:
            return preset_style["prompt_template"].format(user_query=query)
        
        # 原有代码逻辑保持不变...
        # 分析情感状态
        if not emotion_state:
            emotion_state = self._analyze_emotion(query, history)
        
        # 获取当前时间信息
        if not time_info:
            now = datetime.datetime.now()
            time_info = {
                "time": now.strftime("%H:%M"),
                "date": now.strftime("%Y-%m-%d"),
                "weekday": now.strftime("%A"),
                "hour": now.hour,
                "period": "早晨" if 5 <= now.hour < 12 else "下午" if 12 <= now.hour < 18 else "晚上"
            }
        
        # 强化Phonk特征的提示词生成
        phonk_core_elements = [
            "Distinctive cowbell rhythm",  # 明显的骚铃节奏
            "Strong 808 heavy bass",  # 强烈的808重低音
            "Memphis style sampling",  # Memphis风格采样
            "Sidechain compression effect",  # 侧链压缩效果
            "Distorted vocal samples",  # 失真的vocal samples
            "Pitch-shifted processing",  # 变调处理
            "Medium BPM (70-90)",  # 中速BPM (70-90)
            "Lo-fi texture",  # 低保真(Lo-fi)质感
            "VHS vintage noise"  # VHS复古噪音
        ]
        
        # 随机选择3-4个核心元素
        selected_elements = random.sample(phonk_core_elements, min(4, len(phonk_core_elements)))
        
        # 时间影响
        time_mood = ""
        if time_info["period"] == "早晨":
            time_mood = "Morning confusion, nostalgia in the mist, with urban coldness"  # 初醒的迷茫，薄雾中的思念，带有都市冷漠感
        elif time_info["period"] == "下午":
            time_mood = "Afternoon melancholy, loneliness in sunlight, lost in urban rhythm"  # 午后的惆怅，阳光下的孤寂，城市节奏中的失落
        else:  # 晚上
            time_mood = "Late night insomnia, wandering under neon lights, urban night loneliness"  # 深夜的失眠，霓虹灯下的彷徨，都市夜晚的孤独感
        
        # 构建强化Phonk特征的提示词
        prompt = f"""Create a TWISTED style Drift Phonk track with distinctive Phonk features:

[Core Phonk Elements - Must Include]:
- {selected_elements[0]} and {selected_elements[1]}
- {selected_elements[2]} with {selected_elements[3]}
- Strong electronic rhythm with powerful impact throughout
- Strong spatial reverb and delay effects

[Female Vocal Features]:
- Emotional female rap style with strong expression
- Voice processed with pitch shift and delay, with electronic texture
- Emotional release and intensity over heavy bass rhythm

[Music Structure]:
- Clear intro build-up (establishing Phonk atmosphere)
- Explosion in chorus section (808 bass + cowbell + female rap)
- Strong rhythmic impact and driving feel

[Emotional Atmosphere]:
- {time_mood}
- Urban night-time loneliness and lost feelings
- Finding emotional outlet in electronic psychedelia

[User Description]: {query}

Note: Music must have obvious Phonk style identifiers, not just regular electronic dance music."""
        
        logger.info(f"[音乐生成] 生成强化Phonk提示词")
        return prompt
    
    def _analyze_emotion(self, query: str, history: List[Dict] = None) -> str:
        """
        分析用户情感状态
        
        Args:
            query: 用户查询
            history: 对话历史
            
        Returns:
            str: 情感状态
        """
        # 分析查询中的情感关键词
        emotions = ["伤感", "快乐", "舞曲", "忧郁", "孤独", "愤怒", "狂躁", "神秘", "平静"]
        
        for emotion, keywords in EMOTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query:
                    return emotion
        
        # 如果没有明确情感，随机选择一个情感
        random_emotion = random.choice(emotions)
        logger.info(f"[情感分析] 未检测到明确情感，随机选择情感: {random_emotion}")
        return random_emotion
        
    def _generate_simple_lyrics(self, query: str, emotion_state: str = None) -> str:
        """
        从查询和情感状态生成简单的歌词
        
        Args:
            query: 用户查询
            emotion_state: 情感状态
            
        Returns:
            str: 生成的简单歌词
        """
        # 优先使用随机模板
        if random_template_available:
            try:
                # 随机选择情绪
                emotions = ["舞曲", "快乐", "忧郁", "孤独", "愤怒", "狂躁", "神秘", "平静", "期待"]
                random_emotion = random.choice(emotions)
                logger.info(f"[歌词生成] 随机选择了情绪: {random_emotion}")
                
                # 使用随机模板
                enhanced_params = get_enhanced_music_params(
                    query=query,
                    emotion_state=random_emotion,  # 使用随机情绪
                    include_fortune=True
                )
                logger.info(f"[歌词生成] 使用随机模板生成歌词")
                # 返回随机生成的歌词
                return enhanced_params["lyrics"]
            except Exception as e:
                logger.error(f"[歌词生成] 使用随机模板失败: {str(e)}，回退到内置模板")
        
        # 确保有情感状态
        if not emotion_state:
            emotion_state = self._analyze_emotion(query)
            
        # 根据情感类型选择不同的歌词模板
        emotion_lyrics = {
            "伤感": [
                "无尽的夜 我独自徘徊\n思念如潮水 心碎难释怀\n回忆里的画面 一幕幕闪现\n你的笑容 已成为过去",
                "城市的灯光 照不亮心中的迷茫\n时间带走了一切 却带不走思念\n泪水落下 只剩下孤独与伤感\n这条路 我只能一个人走到尽头"
            ],
            "快乐": [
                "阳光照耀 心情舞动\n快乐的节拍 传递着幸福\n生活虽有起伏 但我心中有你\n每一天 都是新的开始",
                "张开双臂 拥抱这世界\n快乐如花绽放 生命充满希望\n让我们一起 创造美好回忆\n在这美丽时光 尽情歌唱"
            ],
            "舞曲": [
                "节奏跳动 身体随之律动\n灯光闪烁 汗水挥洒舞台\n释放压力 忘记一切烦恼\n今晚 让我们尽情狂欢",
                "舞动青春 跟随心跳的节奏\n音乐响起 忘记所有烦忧\n这一刻 只属于我们的时空\n让激情 点燃整个夜晚"
            ]
        }
        
        # 获取对应情感的歌词模板
        lyric_templates = emotion_lyrics.get(emotion_state, emotion_lyrics["伤感"])
        
        # 随机选择一个模板
        import random
        lyrics = random.choice(lyric_templates)
        
        # 在歌词中融入用户查询的关键词（如果可能）
        # 这里简化处理，实际应用可能需要更复杂的NLP处理
        if len(query) > 10:
            # 尝试提取名词或形容词作为歌词中的元素
            import re
            key_words = re.findall(r'[\w\u4e00-\u9fff]{2,4}', query)
            if key_words and len(key_words) > 0:
                # 选择最长的词（可能是最有意义的）
                key_word = max(key_words, key=len)
                # 将用户关键词加入到歌词的某个位置
                lyrics_lines = lyrics.split('\n')
                if len(lyrics_lines) >= 3:
                    lyrics_lines[2] += f" {key_word}的记忆"
                    lyrics = '\n'.join(lyrics_lines)
        
        return lyrics
    
    def _generate_enhanced_phonk_prompt(self, query: str, emotion_state: str = "伤感", use_custom_template: bool = False, custom_lyrics: str = None, custom_title: str = None) -> str:
        """
        生成强化Phonk特征的专业提示词 - 支持自定义和随机模板
        
        Args:
            query: 用户查询
            emotion_state: 情感状态
            use_custom_template: 是否使用自定义模板
            custom_lyrics: 自定义歌词（用于自定义模式）
            custom_title: 自定义标题（用于自定义模式）
            
        Returns:
            str: 强化Phonk特征的提示词
        """
        # 🔧 修复：只有在非自定义模式下才使用随机模板
        if random_template_available and not use_custom_template:
            try:
                # 使用传入的emotion_state，不要随机覆盖
                logger.info(f"[Phonk生成] 使用随机模板，情绪: {emotion_state}")
                
                # 使用随机模板
                enhanced_params = get_enhanced_music_params(
                    query=query,
                    emotion_state=emotion_state,  # 使用传入的情绪，不要随机覆盖
                    include_fortune=True
                )
                logger.info(f"[Phonk生成] 随机模板生成提示词成功")
                # 返回随机生成的提示词
                return enhanced_params["prompt"]
            except Exception as e:
                logger.error(f"[Phonk生成] 使用随机模板失败: {str(e)}，回退到自定义模板")
        
        # 🔥 自定义模板：用户指定的内容
        if use_custom_template and custom_lyrics and custom_title:
            # 为自定义内容生成相应的提示词
            custom_prompt = f"Create a DJ remix phonk track titled '{custom_title}' with these lyrics: {custom_lyrics[:200]}. Add aggressive 808 bass, cowbell rhythms, and DJ scratches."
            logger.info(f"[Phonk生成] 使用自定义模板: {custom_title}")
            return custom_prompt
        
        # 🔥 增强版核心Phonk元素 - 加入DJ remix和强节奏感（内置回退模板）
        enhanced_phonk_elements = [
            "aggressive 808 bass with heavy distortion and sub-bass",
            "sharp cowbell rhythm with turntable scratch effects", 
            "DJ remix style with breakbeats and hard-hitting drums",
            "Memphis vocal chops with extreme pitch shift",
            "sidechain compression creating pumping effect",
            "BPM 120-150 for energetic DJ remix feel"
        ]
        
        # 🔥 情感描述加强版 - 更适合DJ remix风格
        enhanced_emotional_descriptions = {
            "伤感": "melancholic urban vibes, emotional depth with DJ energy",
            "愤怒": "high energy intensity, powerful bass, aggressive remix style", 
            "孤独": "introspective beats, solitary nightlife, deep urban atmosphere",
            "忧郁": "moody basslines, contemplative rhythms, atmospheric depth",
            "狂躁": "explosive energy, dynamic intensity, high-tempo remix power",
            "舞曲": "club energy, dance floor power, party atmosphere with DJ skills",
            "快乐": "uplifting energy, euphoric vibes, celebratory club atmosphere",
            "神秘": "underground atmosphere, mysterious club vibes, dark ambient remix"
        }
        
        emotion_desc = enhanced_emotional_descriptions.get(emotion_state, "intense emotional expression with DJ remix energy")
        
        # 从用户查询中提取关键主题
        theme_keywords = self._extract_theme_keywords(query)
        
        # 🚀 构建超强化Phonk提示词 - 专注DJ remix特征 (缩短版本)
        enhanced_phonk_prompt = f"""HARDCORE DJ PHONK with female vocals: 808 bass, cowbell, scratches, Memphis rap, BPM 130, heavy compression, aggressive filtering. {emotion_desc}. Theme: {theme_keywords}. Tags: phonk,DJ,808,cowbell,Memphis,aggressive,female vocals"""

        logger.info(f"[Phonk生成] 内置模板提示词已生成，长度: {len(enhanced_phonk_prompt)}字符")
        return enhanced_phonk_prompt
    
    def _extract_theme_keywords(self, query: str) -> str:
        """
        从用户查询中提取主题关键词
        
        Args:
            query: 用户查询
            
        Returns:
            str: 提取的关键词
        """
        if not query or len(query.strip()) < 3:
            # 随机返回一个默认主题
            default_themes = [
                "night drive", "urban vibes", "street feeling", 
                "cyber dreams", "neon lights", "midnight thoughts"
            ]
            return random.choice(default_themes)
        
        # 简单的关键词提取逻辑
        import re
        keywords = re.findall(r'[\w\u4e00-\u9fff]{2,8}', query)
        
        # 过滤常用词
        filter_words = {"音乐", "歌曲", "创作", "生成", "播放", "下载", "首", "一", "的", "了", "在", "是", "有", "我"}
        keywords = [k for k in keywords if k not in filter_words and len(k) >= 2]
        
        if keywords:
            result = ", ".join(keywords[:3])  # 最多取3个关键词，英文逗号分隔
            return result
        else:
            # 随机返回英文主题
            default_themes = [
                "night drive", "urban vibes", "street feeling", 
                "cyber dreams", "neon lights", "midnight thoughts"
            ]
            return random.choice(default_themes)
    
    def _handle_dual_clips_from_single_api(self, task_id: str, suno_data):
        """
        处理单次API调用返回的多个clips（双重生成核心逻辑）
        
        Args:
            task_id: 内部任务ID
            suno_data: Suno API返回的数据
        """
        try:
            logger.info(f"[双重生成] 开始处理任务 {task_id}")
            
            # 等待并获取所有clips的完整信息
            max_wait_time = 300  # 延长到5分钟，因为Suno生成确实很慢
            check_interval = 15   # 延长检查间隔到15秒，减少API调用频率
            elapsed_time = 0
            
            all_clips_ready = False
            final_clips = []
            
            # 提取任务ID
            task_ids = []
            if isinstance(suno_data, str):
                task_ids = [suno_data]  # 直接是任务ID
            elif isinstance(suno_data, dict):
                # 从响应数据中提取任务ID
                if 'id' in suno_data:
                    task_ids = [suno_data['id']]
                elif isinstance(suno_data, dict) and 'task_id' in suno_data:
                    task_ids = [suno_data['task_id']]
            
            if not task_ids:
                logger.error(f"[双重生成] 无法从响应中提取任务ID: {suno_data}")
                self.update_task_state(task_id, "FAILED", {"error": "无法提取任务ID"})
                return
                
            logger.info(f"[双重生成] 提取到任务ID: {task_ids}")
            
            # 🔥 使用测试文件中成功的轮询方式
            while elapsed_time < max_wait_time and not all_clips_ready:
                logger.info(f"[双重生成] 检查任务状态，已等待{elapsed_time}秒 (最大等待{max_wait_time}秒)")
                
                # 直接HTTP请求，模仿测试文件的成功做法
                ready_clips = []
                for suno_task_id in task_ids:
                    try:
                        # 使用与测试文件相同的请求方式
                        import requests
                        url = f"{BASE_URL}/suno/feed/{suno_task_id}"
                        headers = {
                            "Authorization": f"Bearer {API_KEY}",
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        }
                        
                        response = requests.get(url, headers=headers, timeout=30)
                        
                        if response.status_code == 200:
                            response_data = response.json()
                            
                            # 处理响应数据（与测试文件逻辑一致）
                            if isinstance(response_data, list) and len(response_data) > 0:
                                clips = response_data
                                
                                # 检查所有片段
                                for i, clip in enumerate(clips):
                                    status = clip.get("status", "unknown")
                                    audio_url = clip.get("audio_url", "")
                                    title = clip.get("title", f"音乐片段{i+1}")
                                    
                                    logger.info(f"[双重生成] 片段 {i+1} ({title}): 状态={status}")
                                    
                                    # 🔥 关键修改：使用测试文件的宽松检查条件
                                    if audio_url:  # 只要有音频URL就认为可用
                                        clip_info = {
                                            'id': suno_task_id,
                                            'audio_url': audio_url,
                                            'title': title,
                                            'status': status
                                        }
                                        ready_clips.append(clip_info)
                                        logger.info(f"[双重生成] 找到可下载音频! URL: {audio_url}")
                                
                        else:
                            logger.warning(f"[双重生成] HTTP请求失败: {response.status_code}")
                            
                    except Exception as e:
                        logger.error(f"[双重生成] 查询任务 {suno_task_id} 失败: {str(e)}")
                
                # 检查是否有足够的clips就绪
                if len(ready_clips) >= 1:
                    final_clips = ready_clips
                    all_clips_ready = True
                    logger.info(f"[双重生成] 成功获得 {len(ready_clips)} 首音乐")
                    break
                else:
                    logger.info(f"[双重生成] 当前就绪任务: {len(ready_clips)}，继续等待...")
                    time.sleep(check_interval)
                    elapsed_time += check_interval
            
            if not final_clips:
                error_msg = f"等待{max_wait_time}秒超时或所有任务生成失败"
                logger.error(f"[双重生成] {error_msg}")
                self.update_task_state(task_id, "FAILED", {"error": error_msg})
                return
                
            # 下载所有音频
            logger.info(f"[双重生成] 开始下载 {len(final_clips)} 首音乐")
            downloaded_files = []
            
            for i, clip in enumerate(final_clips):
                try:
                    audio_url = clip.get('audio_url')
                    clip_id = clip.get('id', f'task_{i}')
                    title = clip.get('title', f'Music_{i+1}')
                    
                    if audio_url:
                        # 生成文件名，区分不同的任务
                        filename_prefix = f"music_{i+1}_{clip_id[:8]}"
                        local_path = self._download_audio(audio_url, filename_prefix)
                        
                        if local_path and os.path.exists(local_path):
                            downloaded_files.append(local_path)
                            logger.info(f"[双重生成] 成功下载音乐 {i+1}: {local_path}")
                        else:
                            logger.warning(f"[双重生成] 下载失败音乐 {i+1}")
                    else:
                        logger.warning(f"[双重生成] 任务 {i+1} 没有音频URL")
                        
                except Exception as e:
                    logger.error(f"[双重生成] 下载任务 {i+1}时出错: {str(e)}")
            
            if not downloaded_files:
                error_msg = "所有音频下载失败"
                logger.error(f"[双重生成] {error_msg}")
                self.update_task_state(task_id, "FAILED", {"error": error_msg})
                return
            
            # 🔥 修复：优先播放自定义音乐，而不是第一首下载成功的
            played_file = ""
            narration = ""

            if downloaded_files:
                # 🎯 智能选择：优先选择自定义音乐
                selected_file = None

                # 1. 优先查找自定义音乐（通常包含用户指定的标题关键词）
                if has_custom_content and title:
                    for file_path in downloaded_files:
                        # 检查文件名是否包含自定义标题的关键词
                        if any(keyword in os.path.basename(file_path).lower()
                               for keyword in title.lower().split() if len(keyword) > 2):
                            selected_file = file_path
                            logger.info(f"[双重生成] 🎯 选择自定义音乐: {selected_file}")
                            break

                # 2. 如果没找到自定义音乐，使用第一首
                if not selected_file:
                    selected_file = downloaded_files[0]
                    logger.info(f"[双重生成] 使用第一首音乐: {selected_file}")

                try:
                    # 暂时禁用播放功能，只生成旁白
                    narration = self._play_audio(selected_file)  # _play_audio已修改为不自动播放
                    played_file = selected_file
                    logger.info(f"[双重生成] 音乐已下载，暂不自动播放: {selected_file}")
                except Exception as e:
                    logger.error(f"[双重生成] 处理失败: {str(e)}")
                    narration = f"音乐已下载但处理失败: {str(e)}"
            
            # 更新任务完成状态
            result_data = {
                "downloaded_files": downloaded_files,
                "played_file": played_file,
                "total_files": len(downloaded_files),
                "narration": narration,
                "phonk_clips": final_clips,
                "download_summary": f"成功下载{len(downloaded_files)}首音乐，播放其中第1首",
                "task_ids": [clip.get('id') for clip in final_clips]
            }
            
            self.update_task_state(task_id, "COMPLETED", result_data)
            logger.info(f"[双重生成] 任务 {task_id} 完成，下载了{len(downloaded_files)}首音乐")
            
        except Exception as e:
            error_msg = f"音乐处理异常: {str(e)}"
            logger.error(f"[双重生成] {error_msg}")
            import traceback
            logger.error(f"[双重生成] 详细错误: {traceback.format_exc()}")
            self.update_task_state(task_id, "FAILED", {"error": error_msg})
    
    def _simple_silent_download(self, suno_task_id: str):
        """
        简化的静默下载（使用sisimusic的TaskManager）
        """
        try:
            # 直接使用TaskManager的poll_task方法
            callbacks = {
                'on_success': lambda result: logger.info(f"静默下载完成"),
                'on_failure': lambda result: logger.warning(f"静默下载失败")
            }
            
            TaskManager.poll_task(
                api=self.api,
                task_id=suno_task_id,
                callbacks=callbacks,
                wait_seconds=5,
                max_attempts=60
            )
        except Exception as e:
            logger.error(f"静默下载异常: {str(e)}")
    
    def _handle_dual_generation(self, task_id: str, inspiration_task_id: str, custom_task_id: str = None):
        """
        处理双重音乐生成任务：等待两个任务完成，下载两个文件，只播放其中一个
        
        Args:
            task_id: 主任务ID
            inspiration_task_id: 灵感模式任务ID（将被播放）
            custom_task_id: 自定义模式任务ID（静默下载，可为None）
        """
        try:
            logger.info(f"[双重生成] 开始管理双重任务: 灵感({inspiration_task_id}) + 自定义({custom_task_id})")
            
            # 设置最大等待时间
            max_wait_time = 180  # 3分钟
            wait_interval = 5    # 每5秒检查一次
            elapsed_time = 0
            
            inspiration_completed = False
            custom_completed = (custom_task_id is None)  # 如果没有自定义任务，视为已完成
            inspiration_result = None
            custom_result = None
            
            # 等待两个任务完成
            while elapsed_time < max_wait_time and not (inspiration_completed and custom_completed):
                # 检查灵感模式任务状态
                if not inspiration_completed:
                    try:
                        fetch_result = self.api.fetch_task(inspiration_task_id)
                        if fetch_result and fetch_result.get('code') == 'success':
                            data = fetch_result.get('data', [])
                            if data and len(data) > 0:
                                song = data[0]
                                status = song.get('status', '')
                                state = song.get('state', '')
                                
                                if status == 'complete' and state == 'succeeded':
                                    inspiration_completed = True
                                    inspiration_result = song
                                    logger.info(f"[双重生成] 灵感模式任务完成")
                                elif state == 'failed':
                                    inspiration_completed = True
                                    logger.error(f"[双重生成] 灵感模式任务失败")
                    except Exception as e:
                        logger.error(f"[双重生成] 检查灵感模式任务状态失败: {str(e)}")
                
                # 检查自定义模式任务状态
                if not custom_completed and custom_task_id:
                    try:
                        fetch_result = self.api.fetch_task(custom_task_id)
                        if fetch_result and fetch_result.get('code') == 'success':
                            data = fetch_result.get('data', [])
                            if data and len(data) > 0:
                                song = data[0]
                                status = song.get('status', '')
                                state = song.get('state', '')
                                
                                if status == 'complete' and state == 'succeeded':
                                    custom_completed = True
                                    custom_result = song
                                    logger.info(f"[双重生成] 自定义模式任务完成")
                                elif state == 'failed':
                                    custom_completed = True
                                    logger.error(f"[双重生成] 自定义模式任务失败")
                    except Exception as e:
                        logger.error(f"[双重生成] 检查自定义模式任务状态失败: {str(e)}")
                
                # 如果两个任务都完成了，提前退出循环
                if inspiration_completed and custom_completed:
                    break
                
                # 等待下一次检查
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                logger.info(f"[双重生成] 等待任务完成中... 已耗时{elapsed_time}秒")
            
            # 处理结果
            downloaded_files = []
            played_file = None
            narration = ""
            
            # 处理灵感模式结果（下载并播放）
            if inspiration_result:
                audio_url = inspiration_result.get('audio_url', '')
                title = inspiration_result.get('title', 'inspiration_music')
                
                if audio_url:
                    try:
                        # 下载灵感模式音乐
                        downloaded_file = self._download_audio(audio_url, f"inspiration_{title}")
                        if downloaded_file:
                            downloaded_files.append(downloaded_file)
                            played_file = downloaded_file
                            
                            # 注释掉播放灵感模式音乐的代码
                            # self._play_audio(downloaded_file)
                            
                            # 生成旁白
                            narration = TaskManager.generate_music_narration(downloaded_file)
                            
                            logger.info(f"[双重生成] 灵感模式音乐已下载（暂不自动播放）: {downloaded_file}")
                    except Exception as e:
                        logger.error(f"[双重生成] 下载/处理灵感模式音乐失败: {str(e)}")
            
            # 处理自定义模式结果（仅下载）
            if custom_result:
                audio_url = custom_result.get('audio_url', '')
                title = custom_result.get('title', 'custom_phonk')
                
                if audio_url:
                    try:
                        # 下载自定义模式音乐（不播放）
                        downloaded_file = self._download_audio(audio_url, f"custom_{title}")
                        if downloaded_file:
                            downloaded_files.append(downloaded_file)
                            logger.info(f"[双重生成] 自定义模式音乐已下载（未播放）: {downloaded_file}")
                    except Exception as e:
                        logger.error(f"[双重生成] 下载自定义模式音乐失败: {str(e)}")
            
            # 更新最终任务状态
            final_result = {
                "downloaded_files": downloaded_files,
                "played_file": played_file,
                "narration": narration,
                "inspiration_result": inspiration_result,
                "custom_result": custom_result,
                "total_files": len(downloaded_files)
            }
            
            self.update_task_state(task_id, "COMPLETED", final_result)
            
            logger.info(f"[双重生成] 任务完成，下载了{len(downloaded_files)}个文件，播放了灵感模式音乐")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[双重生成] 处理双重任务失败: {error_msg}")
            import traceback
            logger.error(f"[双重生成] 错误详情: {traceback.format_exc()}")
            
            self.update_task_state(task_id, "FAILED", {"error": error_msg})
    
    def _download_audio(self, audio_url: str, filename_prefix: str = "music") -> str:
        """
        下载音频文件，使用音乐专用的命名格式
        
        Args:
            audio_url: 音频文件URL
            filename_prefix: 文件名前缀（将被忽略，使用音乐专用格式）
            
        Returns:
            str: 下载的文件路径，失败返回None
        """
        try:
            import requests
            import os
            from urllib.parse import urlparse
            
            # 确保保存目录存在
            save_dir = SAVE_DIR
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            
            # **音乐专用命名格式：music_YYYYMMDD_HHMMSS_randomID.wav**
            import time
            import random
            from datetime import datetime
            
            # 生成时间戳和随机ID
            now = datetime.now()
            date_str = now.strftime("%Y%m%d")
            time_str = now.strftime("%H%M%S")
            random_id = random.randint(1000, 9999)
            
            # 获取原始文件扩展名
            parsed_url = urlparse(audio_url)
            original_ext = os.path.splitext(parsed_url.path)[1] or '.mp3'
            
            # 🎵 使用音乐专用命名格式：music_日期_时间_随机ID.扩展名
            temp_filename = f"music_{date_str}_{time_str}_{random_id}{original_ext}"
            temp_filepath = os.path.join(save_dir, temp_filename)
            
            # 下载文件
            logger.info(f"[音频下载] 开始下载音乐文件: {audio_url}")
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(temp_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # **强制转换为WAV格式以确保ESP32兼容性**
            final_filepath = temp_filepath
            if original_ext.lower() == '.mp3':
                try:
                    wav_filename = f"music_{date_str}_{time_str}_{random_id}.wav"
                    wav_filepath = os.path.join(save_dir, wav_filename)
                    
                    # 尝试使用ffmpeg转换
                    import subprocess
                    result = subprocess.run([
                        'ffmpeg', '-i', temp_filepath, '-ar', '22050', '-ac', '1', wav_filepath, '-y'
                    ], capture_output=True, text=True, timeout=30)
                    
                    if result.returncode == 0:
                        logger.info(f"[音频下载] 已转换为WAV格式: {wav_filename}")
                        # 删除原始mp3文件
                        os.remove(temp_filepath)
                        final_filepath = wav_filepath
                    else:
                        logger.warning(f"[音频下载] ffmpeg转换失败，保留原格式")
                        
                except Exception as e:
                    logger.error(f"[音频下载] 格式转换失败: {str(e)}")
            
            logger.info(f"[音频下载] 音乐文件下载完成: {final_filepath}")
            return final_filepath
            
        except Exception as e:
            logger.error(f"[音频下载] 音乐文件下载失败: {str(e)}")
            return None
    
    def create_task(self, query: str):
        """
        创建新任务
        
        Args:
            query: 用户查询
            
        Returns:
            Dict: 包含任务ID的字典
        """
        task_id = str(uuid.uuid4())
        self.update_task_state(task_id, "CREATED", None)
        return {"task_id": task_id}
    
    
    
    def update_task_state(self, task_id: str, status: str, result: Any = None):
        """
        更新任务状态 - 修复：当任务完成时自动发送到中转站
        
        Args:
            task_id: 任务ID
            status: 任务状态
            result: 任务结果
        """
        self.task_states[task_id] = {
            "status": status,
            "result": result,
            "update_time": datetime.datetime.now().isoformat()
        }
        logger.info(f"[音乐生成] 更新任务状态: {task_id} -> {status}")
        
        # 🔥 关键修复：当任务完成时，发送到中转站触发工具专属优化
        if status == "COMPLETED" and result:
            try:
                from SmartSisi.llm.transit_station import get_transit_station
                transit = get_transit_station()
                
                # 生成音乐完成旁白
                narration = result.get("narration", "")
                played_file = result.get("played_file", "")
                total_files = result.get("total_files", 0)
                
                # 构建完成通知文本
                if not narration and total_files > 0:
                    narration = f"已成功生成{total_files}首音乐，请欣赏！"
                elif not narration:
                    narration = "音乐生成完成！"
                
                # 发送到中转站，标记为工具完成通知
                completion_state = {
                    "content": narration,
                    "source": f"工具完成:music_generator",
                    "timestamp": int(time.time() * 1000),
                    "is_final": True,  # 标记为最终状态
                    "tool_type": "music_generator",  # 工具类型
                    "task_id": task_id,
                    "music_file": played_file if played_file else "",
                    "metadata": {
                        "total_files": total_files,
                        "completion_type": "music_generation"
                    }
                }
                
                transit.add_intermediate_state(completion_state)
                logger.info(f"[音乐生成] 已发送完成通知到中转站: {narration[:50]}...")
                
                # 同时发送旧的事件通知（兼容性）
                self._send_music_completion_event(task_id, narration, played_file)
                
            except Exception as e:
                logger.error(f"[音乐生成] 发送完成通知到中转站失败: {str(e)}")
                import traceback
                logger.error(f"[音乐生成] 详细错误: {traceback.format_exc()}")
    
    def get_task_state(self, task_id: str):
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务状态信息
        """
        state = self.task_states.get(task_id)
        if not state:
            return {"status": "NOT_FOUND", "message": f"任务 {task_id} 不存在"}
            
        return {
            "task_id": task_id,
            "status": state["status"],
            "result": state["result"],
            "update_time": state["update_time"]
        }
    
    def health_check(self):
        """
        健康状态检查
        
        Returns:
            Dict: 健康状态
        """
        return {"status": "ok", "version": self.version}
    
    def get_metadata(self):
        """
        获取工具元数据 - A2A标准卡片格式
        
        Returns:
            Dict: 工具元数据
        """
        return {
            "tool_name": self.name,
            "tool_version": self.version,
            "tool_description": self.description,
            "developer": "SiliconFlow",
            "capabilities": self.get_capabilities(),
            "examples": self.get_examples(),
            "auth_config": {"type": "none"},
            "tool_card": {
                "title": "情感音乐生成工具",
                "description": "根据情感状态生成定制化音乐",
                "inputs": [
                    {
                        "name": "query",
                        "description": "用户的音乐生成请求",
                        "type": "string",
                        "required": True
                    },
                    {
                        "name": "emotion_state",
                        "description": "指定的情感状态，如不提供则自动分析",
                        "type": "string",
                        "required": False
                    }
                ],
                "outputs": [
                    {
                        "name": "task_id",
                        "description": "任务ID",
                        "type": "string"
                    },
                    {
                        "name": "status",
                        "description": "任务状态",
                        "type": "string"
                    },
                    {
                        "name": "message",
                        "description": "任务消息",
                        "type": "string"
                    }
                ]
            }
        }
    
    def handle_a2a_request(self, request: Dict):
        """
        处理A2A标准请求
        
        Args:
            request: A2A标准请求
            
        Returns:
            Dict: A2A标准响应
        """
        req_type = request.get("type", "")
        
        if req_type == "health_check":
            return {"status": "completed", "data": self.health_check()}
            
        elif req_type == "metadata":
            return {"status": "completed", "data": self.get_metadata()}
            
        elif req_type == "invoke":
            params = request.get("params", {})
            query = params.get("query", "")
            task_id = params.get("task_id")
            emotion_state = params.get("emotion_state", "neutral")
            # 修复：如果是neutral，改为None让系统自动分析
            if emotion_state == "neutral":
                emotion_state = None
            history = params.get("history", [])
            time_info = params.get("time_info")
            # 新增：支持直接指定预设风格
            preset_style = params.get("preset_style")
            
            if not query and not preset_style:
                return {
                    "status": "input_required",
                    "message": "请提供音乐生成请求或预设风格名称"
                }
            
            # 如果指定了预设风格，将其添加到查询中
            if preset_style and preset_style in self.preset_styles:
                if query:
                    query = f"{preset_style}：{query}"
                else:
                    query = preset_style
                
            result = self.run(query, task_id, history, time_info, emotion_state)
            
            return {
                "status": "completed" if result.get("status") != "FAILED" else "error",
                "data": result,
                "message": result.get("message", "")
            }
            
        elif req_type == "get_task":
            task_id = request.get("task_id")
            
            if not task_id:
                return {
                    "status": "input_required",
                    "message": "请提供任务ID"
                }
                
            state = self.get_task_state(task_id)
            
            return {
                "status": "completed",
                "data": state
            }
            
        elif req_type == "list_presets":
            # 新增：列出所有预设风格
            presets_info = {}
            for name, info in self.preset_styles.items():
                presets_info[name] = {
                    "name": info["name"],
                    "description": info["description"],
                    "tags": info["tags"]
                }
            
            return {
                "status": "completed",
                "data": {
                    "presets": presets_info
                }
            }
            
        else:
            return {
                "status": "error",
                "message": f"不支持的请求类型: {req_type}"
            }
    
    def get_capabilities(self):
        """
        获取工具能力列表
        
        Returns:
            List: 能力描述列表
        """
        # 构建预设风格列表
        preset_styles_text = ", ".join([f"'{name}'" for name in self.preset_styles.keys()])
        
        return [
            "根据用户指令生成定制化音乐",
            "分析用户情感状态并创作相应风格的音乐",
            f"支持预设音乐风格（{preset_styles_text}）快速生成",
            "支持女声、说唱、电音等音乐元素",
            "支持TWISTED风格的Drift Phonk音乐生成",
            "支持自动下载和播放生成的音乐",
            "提供音乐生成进度和状态追踪"
        ]
    
    def get_examples(self):
        """
        获取工具示例列表
        
        Returns:
            List: 示例列表
        """
        return [
            {
                "input": {"query": "生成一首伤感舞曲"},
                "output": {"task_id": "12345", "status": "RUNNING", "message": "音乐生成任务已提交，请稍后查询结果"}
            },
            {
                "input": {"query": "创作一首表达思念和孤独的伤感女声舞曲", "emotion_state": "伤感"},
                "output": {"task_id": "67890", "status": "RUNNING", "message": "音乐生成任务已提交，请稍后查询结果"}
            }
        ]
    
    def process_with_langgraph(self, query: str, state: Dict[str, Any] = None):
        """
        与LangGraph集成处理
        
        Args:
            query: 用户查询
            state: 当前状态
            
        Returns:
            Dict: 更新后的状态
        """
        if state is None:
            state = {}
            
        # 提取历史对话和时间信息
        history = state.get("history", [])
        time_info = {
            "time": datetime.datetime.now().strftime("%H:%M"),
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "weekday": datetime.datetime.now().strftime("%A"),
            "hour": datetime.datetime.now().hour
        }
        
        # 运行音乐生成
        result = self.run(query, history=history, time_info=time_info)
        
        # 更新状态
        state["music_result"] = result
        
        return state

def create_tool():
    """
    创建工具实例
    
    Returns:
        MusicGeneratorTool: 工具实例
    """
    return MusicGeneratorTool()

def create_music_workflow(llm):
    """
    创建音乐生成工作流图
    
    Args:
        llm: 语言模型实例
        
    Returns:
        StateGraph: 构建好的工作流图实例
    """
    from langchain.graphs.graph import StateGraph
    from langchain.prompts import PromptTemplate
    from langchain.graphs.state_graph import END
    
    # 创建工作流图
    workflow = StateGraph("情感音乐生成工作流")
    
    # 创建音乐生成工具实例
    music_tool = get_music_tool_instance()
    
    # 提示词分析节点
    def analyze_request(state):
        """分析用户请求并提取情感信息"""
        query = state.get("query", "")
        
        # 使用LLM分析请求中的情感
        template = """
        分析用户请求中的情感状态和音乐偏好：
        
        用户请求：{query}
        
        请提取以下信息：
        1. 主要情感状态（如伤感、快乐、平静等）
        2. 音乐类型偏好（如流行、古典、电子等）
        3. 特殊偏好（如女声、男声、纯音乐等）
        
        以JSON格式输出：
        {{
          "emotion": "情感状态",
          "music_type": "音乐类型",
          "preferences": ["特殊偏好1", "特殊偏好2"]
        }}
        """
        
        prompt = PromptTemplate.from_template(template)
        analysis_input = prompt.format(query=query)
        analysis_result = llm.predict(analysis_input)
        
        try:
            # 解析LLM输出的JSON
            import json
            analysis = json.loads(analysis_result)
            state["analysis"] = analysis
            
        except json.JSONDecodeError:
            # 如果JSON解析失败，使用默认设置
            state["analysis"] = {
                "emotion": "伤感",
                "music_type": "流行",
                "preferences": ["女声", "舞曲"]
            }
        
        return state
    
    # 生成音乐节点
    def generate_music(state):
        """根据分析生成音乐"""
        query = state.get("query", "")
        analysis = state.get("analysis", {})
        
        # 根据分析结果调整查询
        emotion = analysis.get("emotion", "伤感")
        music_type = analysis.get("music_type", "流行")
        preferences = analysis.get("preferences", ["女声"])
        
        # 创建新的提示词
        enhanced_query = f"创作一首{emotion}的{music_type}音乐"
        if "女声" in preferences:
            enhanced_query += "，使用女声演唱"
        
        # 调用音乐生成工具
        result = music_tool.run(enhanced_query)
        state["music_result"] = result
        
        return state
    
    # 生成结果总结节点
    def summarize_results(state):
        """总结音乐生成结果"""
        music_result = state.get("music_result", {})
        
        # 如果有错误，报告错误
        if music_result.get("status") == "FAILED":
            state["summary"] = f"音乐生成失败：{music_result.get('error', '未知错误')}"
            return state
        
        # 生成友好的总结
        state["summary"] = f"""
        音乐生成任务已提交，任务ID：{music_result.get('task_id')}
        
        音乐将根据您的情感状态和偏好生成。生成完成后会自动播放。
        
        提示词：{music_result.get('message', '').replace('音乐生成任务已提交，请稍后查询结果。提示词：', '')}
        """
        
        return state
    
    # 添加节点
    workflow.add_node("分析请求", analyze_request)
    workflow.add_node("生成音乐", generate_music)
    workflow.add_node("总结结果", summarize_results)
    
    # 设置边
    workflow.add_edge("分析请求", "生成音乐")
    workflow.add_edge("生成音乐", "总结结果")
    workflow.add_edge("总结结果", END)
    
    # 设置入口节点
    workflow.set_entry_point("分析请求")
    
    # 编译工作流
    return workflow.compile()

def run_music_workflow(query: str, history: List[Dict] = None, time_info: Dict = None, emotion_state: str = None):
    """
    运行音乐生成工作流，等待直到完成
    
    Args:
        query: 用户查询
        history: 对话历史
        time_info: 时间信息
        emotion_state: 情感状态
        
    Returns:
        Dict: 结果信息
    """
    # 初始化生成器
    generator = get_music_tool_instance()
    
    # 启动任务
    task = generator.run(query, history=history, time_info=time_info, emotion_state=emotion_state)
    task_id = task.get('task_id')
    
    if not task_id:
        return {
            "status": "FAILED",
            "error": "未能创建任务"
        }
    
    # 如果任务已经完成或失败，直接返回
    if task.get('status') in ["COMPLETED", "FAILED"]:
        return {
            "status": task.get('status'),
            "completion_result": task.get('result', {}),
            "error": task.get('error', None)
        }
    
    # 等待任务完成
    logger.info(f"[音乐生成] 等待任务完成: {task_id}")
    
    # 设置最大等待时间
    max_wait_time = 120  # 最大等待2分钟
    wait_interval = 2    # 每次检查间隔
    elapsed_time = 0
    
    # 循环等待任务完成
    while elapsed_time < max_wait_time:
        # 查询任务状态
        task_state = generator.get_task_state(task_id)
        status = task_state.get('status')
        
        # 检查任务是否已完成
        if status == "COMPLETED":
            result = task_state.get('result', {})
            
            # 提取音乐文件路径
            file_paths = result.get('downloaded_files', [])
            
            # 生成旁白
            narration = ""
            if file_paths:
                narration = TaskManager.generate_music_narration(file_paths[0])
            
            return {
                "status": "COMPLETED",
                "completion_result": result,
                "summary": narration
            }
        elif status == "FAILED":
            return {
                "status": "FAILED",
                "error": task_state.get('result', {}).get('error', '未知错误')
            }
        
        # 等待下一次检查
        time.sleep(wait_interval)
        elapsed_time += wait_interval
    
    # 如果超时
    return {
        "status": "TIMEOUT",
        "error": "等待任务完成超时"
    }

# 添加模块级invoke函数供A2A服务器调用
def invoke(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    A2A协议的入口点。音乐工具采用混合模式：
    - 立即返回进行中状态，让LG生成合适的三句话
    - 异步生成完成后通过TransitStation发送第四句话（旁白）
    """
    request_id = str(uuid.uuid4())
    logger.info(f"[Request:{request_id}] Music tool invoked.")

    query = params.get("query", "创作一首女声Phonk音乐")
    task_id_from_params = params.get("task_id")
    history = params.get("history", [])
    time_info = params.get("time_info", {})
    emotion_state = params.get("emotion_state", "neutral")
    source_info = params.get("source_info", {})
    user_id = source_info.get("user_id", "unknown_user")
    client_id = source_info.get("client_id", "unknown_client")

    final_task_id: str
    if task_id_from_params and isinstance(task_id_from_params, str) and task_id_from_params.strip():
        final_task_id = task_id_from_params
    else:
        final_task_id = str(uuid.uuid4())

    logger.info(f"[Request:{request_id}] 音乐生成任务ID: {final_task_id}")
    
    # 启动异步音乐生成任务
    asyncio.create_task(_async_music_generation_and_notify(
        query=query,
        task_id=final_task_id,
        history=history,
        time_info=time_info,
        emotion_state=emotion_state,
        user_id=user_id,
        client_id=client_id,
        request_id=request_id
    ))

    # 🎯 LG系统兼容格式：返回COMPLETED状态阻止循环调用
    lg_compatible_result = {
        "task_id": final_task_id,
        "status": "COMPLETED",  # 改为COMPLETED，让LG系统认为任务已完成
        "message": f"OK 搞定了 等等哈！{emotion_state}风格的音乐正在准备中，大约需要2分钟时间。",
        "progress": "音乐创作中",
        "estimated_time": "约2分钟",
        "async_mode": True,  # 标记为异步模式
        "notification_via": "TransitStation"  # 通过TransitStation通知完成
    }

    # 返回字典格式，符合A2A系统期望
    return lg_compatible_result

async def _async_music_generation_and_notify(
    query: str,
    task_id: str,
    history: Optional[List[Dict]],
    time_info: Optional[Dict],
    emotion_state: Optional[str],
    user_id: Optional[str],
    client_id: Optional[str],
    request_id: Optional[str],
    suno_params: Optional[Dict[str, Any]] = None
):
    # 使用 request_id 进行日志记录，如果存在
    import random  # 添加random模块导入
    log_request_id = request_id if request_id else task_id 
    logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Starting asynchronous music generation.")
    music_generator = get_music_tool_instance()
    
    task_manager_instance = get_task_manager()
    
    # 首先注册任务到任务管理器
    try:
        await task_manager_instance.create_task(task_id, query, client_id)  # 修复方法签名
        logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Task registered successfully.")
    except Exception as e:
        logger.error(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Failed to register task: {str(e)}")
        # 如果注册失败，尝试更新状态
        try:
            await task_manager_instance.update_task_status(task_id, TaskState.WORKING, "音乐生成中...")
        except Exception as e2:
            logger.error(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Failed to update task status: {str(e2)}")

    generation_result = None
    error_message = None
    music_file = None
    music_title = None
    music_image = None
    narration_text = None
    final_status = TaskState.FAILED  # 确保使用TaskState枚举
    status_message = "音乐生成任务初始化失败"
    start_time = asyncio.get_event_loop().time()

    # 在函数内部根据传入参数生成 theme_keywords 和 emotion_for_prompt
    theme_keywords = music_generator._extract_theme_keywords(query)
    # 如果 emotion_state 明确传入，则使用它；否则尝试从 query 和 history 分析
    emotion_for_prompt = emotion_state if emotion_state and emotion_state != "neutral" else music_generator._analyze_emotion(query, history)
    if not emotion_for_prompt or emotion_for_prompt == "neutral": # 如果分析后仍然没有，给一个默认值
        emotion_for_prompt = "舞曲"  # 修改：默认使用舞曲而不是动感
    
    try:
        logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Generating music prompt for query: {query}")
        # 修复方法名：使用正确的方法名 _generate_music_prompt
        music_prompt = music_generator._generate_music_prompt(
            query=query,
            history=history,
            time_info=time_info,
            emotion_state=emotion_for_prompt
        )
        logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Generated music prompt: {music_prompt}")

        # 更新任务状态为正在生成
        await task_manager_instance.update_task_status(task_id, TaskState.WORKING, "正在调用Suno API生成音乐...")

        generation_result = await asyncio.to_thread(
            music_generator.run,  # 使用现有的run方法
            query,
            task_id=task_id,
            history=history,
            time_info=time_info,
            emotion_state=emotion_for_prompt
        )

        # 🔥 修复状态判断逻辑：PROCESSING状态表示成功启动
        if generation_result and generation_result.get("status") in ["success", "PROCESSING"]:
            logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Music generation successfully started: {generation_result.get('status')}")
            
            # PROCESSING状态意味着任务已启动，轮询线程会处理后续工作
            if generation_result.get("status") == "PROCESSING":
                logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Task is PROCESSING, background thread will handle completion")
                final_status = TaskState.WORKING
                status_message = "音乐生成任务已成功启动，后台处理中..."
                # 不设置具体的音乐文件和旁白，让轮询线程处理
            else:
                # 如果直接返回success状态，按原逻辑处理
                music_file = generation_result.get("output_file")
                music_title = generation_result.get("title", "为你生成的音乐")
                music_image = generation_result.get("image_url")

                if music_file and os.path.exists(music_file):
                    logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Music generated successfully: {music_file}")
                    final_status = TaskState.COMPLETED
                    status_message = "音乐生成成功"
                    
                    # 创建等待提示短语库
                    waiting_phrases = [
                        "让您久等了，",
                        "感谢您的耐心等待，",
                        "经过一段时间的创作，",
                        "AI创作需要一点时间，不过总算完成了，",
                        "虽然网络有点慢，但是好作品值得等待，",
                        "音乐创作不易，感谢您的耐心，",
                        "创作过程花了点时间，希望您会喜欢，",
                        "辛苦等待了两分钟，不过成果很值得，",
                        "总算完成了这首作品，感谢您的等待，",
                        "系统有点慢，但好的音乐需要时间打磨，"
                    ]
                    waiting_phrase = random.choice(waiting_phrases)
                    
                    # 构建旁白 (narration_text)
                    if emotion_for_prompt and theme_keywords:
                        narration_text = f"{waiting_phrase}为你创作的关于'{theme_keywords}'的{emotion_for_prompt}风格音乐《{music_title}》已经准备就绪，一起沉浸其中吧！"
                    elif theme_keywords:
                        narration_text = f"{waiting_phrase}关于'{theme_keywords}'的音乐《{music_title}》已为你奏响，请欣赏。"
                    else:
                        narration_text = f"{waiting_phrase}音乐《{music_title}》已为你生成，一同聆听这美妙的旋律吧。"
                else:
                    error_message = "音乐文件生成后未找到或无效。"
                    logger.error(f"[Request:{log_request_id}] [music_tool-async:{task_id}] {error_message} File path: {music_file}")
                    status_message = error_message
        else:
            error_message = generation_result.get("message", "音乐生成失败，未返回有效结果。") if generation_result else "音乐生成调用未返回任何结果。"
            logger.error(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Music generation failed: {error_message}")
            status_message = f"音乐生成接口调用失败: {error_message}"

    except Exception as e:
        error_message = f"音乐生成过程中发生意外错误: {str(e)}"
        logger.error(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Exception during music generation: {traceback.format_exc()}")
        final_status = TaskState.FAILED
        status_message = error_message
    finally:
        logger.info(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Asynchronous task completed in {asyncio.get_event_loop().time() - start_time:.2f} seconds.")
        # 更新最终任务状态
        try:
            await task_manager_instance.update_task_status(task_id, final_status, status_message)
        except Exception as e_update:
            logger.error(f"[Request:{log_request_id}] [music_tool-async:{task_id}] Failed to update final task status: {str(e_update)}")

    # 构建任务结果
    task_result = {
        "task_id": task_id,
        "status": final_status.value if hasattr(final_status, 'value') else str(final_status),
        "message": status_message,
        "timestamp": time.time(),
    }

    if final_status == TaskState.COMPLETED and music_file:
        task_result["result"] = {
            "music_url": music_file,
            "title": music_title,
            "narration_text": narration_text
        }
        if music_image:
            task_result["result"]["image_url"] = music_image
    elif error_message:
        task_result["error"] = error_message

    return task_result

# 使用原始版本避免日志重复
has_enhanced_version = False
logger.info("使用原始音乐生成工具，避免重复日志")

# 全局工具实例获取函数
def get_music_tool_instance():
    """获取音乐工具的单例实例"""
    return MusicGeneratorTool()

if __name__ == "__main__":
    # 🚀 一键工作流测试
    print("🎵 音乐工具一键测试")
    print("=" * 50)
    
    import sys
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "创作一首深夜城市氛围的女声Phonk音乐"
    
    print(f"使用方法: python music_tool.py [音乐指令]")
    print(f"示例: python music_tool.py 创作一首女声Phonk音乐")
    print()
    
    # 运行一键工作流
    result = create_music_now(query, wait_timeout=180)  # 3分钟超时
    
    print()
    print("=" * 50)
    print("🎉 测试完成！")
    
    if result["status"] == "SUCCESS":
        print("✅ 成功生成并播放音乐")
        print(f"📁 文件数量: {len(result.get('downloaded_files', []))}")
        print(f"🎵 播放文件: {result.get('played_file', '').split('/')[-1] if result.get('played_file') else '无'}")
        print(f"⏱️ 总耗时: {result.get('duration', 0)}秒")
        
        # 询问是否发送到ESP32设备
        try:
            choice = input("\n是否发送到ESP32设备播放？(y/n): ").strip().lower()
            if choice == 'y' and result.get('played_file'):
                esp32_ip = input("请输入ESP32设备IP (回车使用默认): ").strip() or None
                send_music_to_device(result['played_file'], esp32_ip)
        except:
            pass
            
    elif result["status"] == "TIMEOUT":
        print("⚠️ 生成超时，但任务可能仍在进行中")
        print("💡 请稍后检查 SmartSisi/samples 目录")
    else:
        print(f"❌ 生成失败: {result.get('error', '未知错误')}")
        
    print()
    print("📋 工具功能说明:")
    print("  1. 一键工作流: create_music_now('指令')")
    print("  2. 发送到设备: send_music_to_device(文件路径)")
    print("  3. 文件保存位置: E:\liusisi\SmartSisi\samples\\")
    print("  4. 支持格式: MP3 (自动播放)")
    print("  5. ESP32集成: HTTP API发送")

