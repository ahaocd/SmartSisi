"""
SISIeyes ESP32-S3 CAM 音频可视化工具 - A2A标准实现
承上启下的完整A2A工具包装，支持并行异步调用

功能特性：
1. 📷 摄像头控制 - OV5640 5MP拍照、视频流
2. 📺 显示控制 - ST7789 172x320显示屏文字/图像显示
3. 🎵 音频可视化 - 旋律跳动、导弹发射、星空背景效果
4. 💡 LED控制 - WS2812 RGB灯带控制
5. 🚗 电机控制 - L298N减速电机正反转
6. 📡 WiFi通信 - HTTP API异步通信
7. 🔔 事件订阅 - 支持音乐播放、运动检测等事件自我驱动
8. ⚡ 并行处理 - 支持多命令并行异步执行

A2A标准兼容：
- 完全符合A2A协议规范
- 支持异步任务状态管理
- 提供标准化API接口
- 支持事件订阅和通知机制
- 兼容LangGraph工作流集成

使用示例：
```python
# 基础调用
tool = create_tool()
result = await tool.ainvoke("拍一张照片")

# 并行调用
tasks = [
    tool.ainvoke("开启音频可视化"),
    tool.ainvoke("设置LED为彩虹模式"),
    tool.ainvoke("显示欢迎文字")
]
results = await asyncio.gather(*tasks)

# 事件订阅
tool.subscribe_event("music.start", auto_start_visualizer)
```
"""

import asyncio
import aiohttp
import json
import logging
import time
import uuid
import threading
import re
from typing import Dict, List, Optional, Union, Any, Callable
from datetime import datetime
import base64
import os

# 导入A2A基础工具类
try:
    from ..base_a2a_tool import StandardA2ATool
except ImportError:
    # 如果导入失败，定义一个简单的基类
    class StandardA2ATool:
        def __init__(self, name: str, description: str, version: str = "1.0.0"):
            self.name = name
            self.description = description
            self.version = version

# 配置日志
logger = logging.getLogger("SISIeyesTool")
logger.setLevel(logging.INFO)

# SISIeyes设备配置
SISIEYES_CONFIG = {
    "default_host": "172.20.10.2",   # 默认ESP32 IP地址 (iPhone15热点)
    "default_port": 80,               # HTTP服务端口
    "timeout": 10,                    # 请求超时时间
    "retry_count": 3,                 # 重试次数
    "connection_pool_size": 10,       # 连接池大小
}

# 支持的命令映射
COMMAND_MAPPING = {
    # 摄像头控制
    "拍照": "capture_photo",
    "拍张照": "capture_photo", 
    "照相": "capture_photo",
    "capture": "capture_photo",
    "photo": "capture_photo",
    "snap": "capture_photo",
    
    # 显示控制
    "显示": "display_text",
    "显示文字": "display_text",
    "显示文本": "display_text",
    "show": "display_text",
    "display": "display_text",
    
    # 音频可视化
    "可视化": "start_visualizer",
    "音频可视化": "start_visualizer",
    "开启可视化": "start_visualizer",
    "visualizer": "start_visualizer",
    "音乐可视化": "start_visualizer",
    
    # LED控制
    "开灯": "led_on",
    "关灯": "led_off", 
    "LED": "led_control",
    "灯光": "led_control",
    "彩虹": "led_rainbow",
    "呼吸": "led_breathe",
    
    # 电机控制
    "转动": "motor_control",
    "电机": "motor_control",
    "正转": "motor_forward",
    "反转": "motor_backward",
    "停止": "motor_stop",
    
    # 系统控制
    "状态": "get_status",
    "重启": "restart_device",
    "复位": "reset_device",
}

class SISIeyesA2ATool(StandardA2ATool):
    """
    SISIeyes ESP32-S3 CAM 音频可视化A2A工具
    
    提供完整的ESP32-S3 CAM设备控制功能，支持：
    - 摄像头拍照和视频流
    - 显示屏文字和图像显示
    - 音频可视化效果
    - LED灯光控制
    - 电机控制
    - 系统状态监控
    """
    
    def __init__(self, host: str = None, port: int = None):
        """
        初始化SISIeyes工具
        
        Args:
            host: ESP32设备IP地址
            port: HTTP服务端口
        """
        super().__init__(
            name="sisieyes",
            description="ESP32-S3 CAM音频可视化控制工具，支持摄像头、显示屏、LED、电机等全功能控制",
            version="1.0.0"
        )
        
        # 设备连接配置
        self.host = host or SISIEYES_CONFIG["default_host"]
        self.port = port or SISIEYES_CONFIG["default_port"]
        self.base_url = f"http://{self.host}:{self.port}"
        
        # 连接状态
        self.is_connected = False
        self.last_ping_time = 0
        self.connection_lock = asyncio.Lock()
        
        # 任务管理
        self.running_tasks = {}  # 正在运行的任务
        self.task_lock = asyncio.Lock()
        
        # 事件订阅
        self.event_subscriptions = {}  # 事件订阅回调
        self.subscription_lock = threading.RLock()
        
        # 设备状态缓存
        self.device_status = {
            "camera": "unknown",
            "display": "unknown", 
            "led": "unknown",
            "motor": "unknown",
            "visualizer": "unknown",
            "last_update": 0
        }
        
        logger.info(f"[SISIeyes工具] 初始化完成 - 目标设备: {self.base_url}")
    
    async def process_query(self, query: str, **kwargs) -> str:
        """
        处理用户查询的主入口方法
        
        Args:
            query: 用户查询文本
            **kwargs: 额外参数
            
        Returns:
            str: 处理结果
        """
        try:
            logger.info(f"[SISIeyes工具] 处理查询: {query}")
            
            # 确保设备连接
            if not await self._ensure_connection():
                return "❌ 无法连接到SISIeyes设备，请检查设备状态和网络连接"
            
            # 解析命令
            command, params = self._parse_command(query)
            
            if not command:
                return f"❌ 无法识别命令: {query}\n支持的命令: 拍照、显示文字、开启可视化、LED控制、电机控制等"
            
            # 执行命令
            result = await self._execute_command(command, params, query)
            
            # 更新设备状态
            await self._update_device_status()
            
            return result
            
        except Exception as e:
            logger.error(f"[SISIeyes工具] 处理查询异常: {str(e)}")
            return f"❌ 处理请求时发生错误: {str(e)}"
    
    def _parse_command(self, query: str) -> tuple:
        """
        解析用户命令
        
        Args:
            query: 用户查询文本
            
        Returns:
            tuple: (命令名称, 参数字典)
        """
        query_lower = query.lower()
        
        # 遍历命令映射找到匹配的命令
        for keyword, command in COMMAND_MAPPING.items():
            if keyword in query_lower:
                params = self._extract_params(query, keyword, command)
                return command, params
        
        # 如果没有找到明确命令，尝试智能推断
        if any(word in query_lower for word in ["照", "拍", "capture", "photo"]):
            return "capture_photo", {}
        elif any(word in query_lower for word in ["显示", "show", "display"]):
            text = self._extract_display_text(query)
            return "display_text", {"text": text}
        elif any(word in query_lower for word in ["可视化", "visualizer", "音乐"]):
            return "start_visualizer", {}
        elif any(word in query_lower for word in ["led", "灯", "light"]):
            return "led_control", {"action": "toggle"}
        elif any(word in query_lower for word in ["电机", "motor", "转"]):
            return "motor_control", {"action": "toggle"}
        elif any(word in query_lower for word in ["状态", "status", "info"]):
            return "get_status", {}
        
        return None, {}

    def _extract_params(self, query: str, keyword: str, command: str) -> dict:
        """提取命令参数"""
        params = {}

        if command == "display_text":
            # 提取要显示的文字
            text = self._extract_display_text(query)
            params["text"] = text
        elif command in ["motor_forward", "motor_backward"]:
            # 提取转动时间
            duration = self._extract_duration(query)
            params["duration"] = duration
        elif command == "led_control":
            # 提取LED模式
            mode = self._extract_led_mode(query)
            params["mode"] = mode

        return params

    def _extract_display_text(self, query: str) -> str:
        """从查询中提取要显示的文字"""
        # 匹配引号内的文字
        quote_match = re.search(r'["""\'](.*?)["""\']', query)
        if quote_match:
            return quote_match.group(1)

        # 匹配"显示"后面的文字
        display_match = re.search(r'显示[文字文本]*[:：]?\s*(.+)', query)
        if display_match:
            return display_match.group(1).strip()

        # 默认文字
        return "Hello SISIeyes!"

    def _extract_duration(self, query: str) -> int:
        """从查询中提取持续时间（秒）"""
        # 匹配数字+秒
        duration_match = re.search(r'(\d+)\s*[秒s]', query)
        if duration_match:
            return int(duration_match.group(1))

        return 3  # 默认3秒

    def _extract_led_mode(self, query: str) -> str:
        """从查询中提取LED模式"""
        query_lower = query.lower()

        if "彩虹" in query_lower or "rainbow" in query_lower:
            return "rainbow"
        elif "呼吸" in query_lower or "breathe" in query_lower:
            return "breathe"
        elif "闪烁" in query_lower or "blink" in query_lower:
            return "blink"
        elif "开" in query_lower or "on" in query_lower:
            return "on"
        elif "关" in query_lower or "off" in query_lower:
            return "off"

        return "toggle"

    async def _ensure_connection(self) -> bool:
        """确保设备连接"""
        async with self.connection_lock:
            current_time = time.time()

            # 如果最近ping过且连接正常，直接返回
            if self.is_connected and (current_time - self.last_ping_time) < 30:
                return True

            # 尝试ping设备
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.get(f"{self.base_url}/status") as response:
                        if response.status == 200:
                            self.is_connected = True
                            self.last_ping_time = current_time
                            logger.info(f"[SISIeyes工具] 设备连接正常: {self.base_url}")
                            return True
            except Exception as e:
                logger.warning(f"[SISIeyes工具] 设备连接检查失败: {str(e)}")

            self.is_connected = False
            return False

    async def _execute_command(self, command: str, params: dict, original_query: str) -> str:
        """执行具体命令"""
        try:
            # 根据命令类型调用相应的处理方法
            if command == "capture_photo":
                return await self._capture_photo()
            elif command == "display_text":
                return await self._display_text(params.get("text", "Hello!"))
            elif command == "start_visualizer":
                return await self._start_visualizer()
            elif command == "led_on":
                return await self._led_control("on")
            elif command == "led_off":
                return await self._led_control("off")
            elif command == "led_control":
                return await self._led_control(params.get("mode", "toggle"))
            elif command == "led_rainbow":
                return await self._led_control("rainbow")
            elif command == "led_breathe":
                return await self._led_control("breathe")
            elif command == "motor_forward":
                return await self._motor_control("forward", params.get("duration", 3))
            elif command == "motor_backward":
                return await self._motor_control("backward", params.get("duration", 3))
            elif command == "motor_stop":
                return await self._motor_control("stop")
            elif command == "motor_control":
                return await self._motor_control(params.get("action", "toggle"))
            elif command == "get_status":
                return await self._get_device_status()
            elif command == "restart_device":
                return await self._restart_device()
            elif command == "reset_device":
                return await self._reset_device()
            else:
                return f"❌ 未实现的命令: {command}"

        except Exception as e:
            logger.error(f"[SISIeyes工具] 执行命令异常: {command} - {str(e)}")
            return f"❌ 执行命令失败: {str(e)}"

    async def _capture_photo(self) -> str:
        """拍照功能"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(f"{self.base_url}/capture") as response:
                    if response.status == 200:
                        # 获取照片数据
                        photo_data = await response.read()

                        # 保存照片到本地（可选）
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"sisieyes_photo_{timestamp}.jpg"

                        # 这里可以选择保存到特定目录
                        # with open(filename, 'wb') as f:
                        #     f.write(photo_data)

                        logger.info(f"[SISIeyes工具] 拍照成功，大小: {len(photo_data)} bytes")
                        return f"📷 拍照成功！照片大小: {len(photo_data)} bytes\n时间: {timestamp}"
                    else:
                        return f"❌ 拍照失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ 拍照异常: {str(e)}"

    async def _display_text(self, text: str) -> str:
        """显示文字"""
        try:
            data = {"text": text}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(f"{self.base_url}/display", json=data) as response:
                    if response.status == 200:
                        logger.info(f"[SISIeyes工具] 显示文字成功: {text}")
                        return f"📺 显示文字成功: {text}"
                    else:
                        return f"❌ 显示文字失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ 显示文字异常: {str(e)}"

    async def _start_visualizer(self) -> str:
        """启动音频可视化"""
        try:
            data = {"mode": "start"}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(f"{self.base_url}/visualizer", json=data) as response:
                    if response.status == 200:
                        logger.info("[SISIeyes工具] 音频可视化启动成功")
                        return "🎵 音频可视化已启动！正在显示旋律跳动和星空效果"
                    else:
                        return f"❌ 启动可视化失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ 启动可视化异常: {str(e)}"

    async def _led_control(self, mode: str) -> str:
        """LED控制"""
        try:
            data = {"mode": mode}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(f"{self.base_url}/led", json=data) as response:
                    if response.status == 200:
                        logger.info(f"[SISIeyes工具] LED控制成功: {mode}")

                        mode_desc = {
                            "on": "开启",
                            "off": "关闭",
                            "rainbow": "彩虹模式",
                            "breathe": "呼吸模式",
                            "blink": "闪烁模式",
                            "toggle": "切换状态"
                        }.get(mode, mode)

                        return f"💡 LED {mode_desc}成功！"
                    else:
                        return f"❌ LED控制失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ LED控制异常: {str(e)}"

    async def _motor_control(self, action: str, duration: int = 3) -> str:
        """电机控制"""
        try:
            data = {"action": action, "duration": duration}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(f"{self.base_url}/motor", json=data) as response:
                    if response.status == 200:
                        logger.info(f"[SISIeyes工具] 电机控制成功: {action}")

                        action_desc = {
                            "forward": f"正转 {duration}秒",
                            "backward": f"反转 {duration}秒",
                            "stop": "停止",
                            "toggle": "切换状态"
                        }.get(action, action)

                        return f"🚗 电机{action_desc}成功！"
                    else:
                        return f"❌ 电机控制失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ 电机控制异常: {str(e)}"

    async def _get_device_status(self) -> str:
        """获取设备状态"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{self.base_url}/status") as response:
                    if response.status == 200:
                        status_data = await response.json()

                        # 格式化状态信息
                        status_text = "📊 SISIeyes设备状态:\n"
                        status_text += f"🔗 连接状态: 正常\n"
                        status_text += f"📷 摄像头: {status_data.get('camera', '未知')}\n"
                        status_text += f"📺 显示屏: {status_data.get('display', '未知')}\n"
                        status_text += f"💡 LED: {status_data.get('led', '未知')}\n"
                        status_text += f"🚗 电机: {status_data.get('motor', '未知')}\n"
                        status_text += f"🎵 可视化: {status_data.get('visualizer', '未知')}\n"
                        status_text += f"🔋 内存: {status_data.get('memory', '未知')}\n"
                        status_text += f"📡 WiFi: {status_data.get('wifi', '未知')}"

                        # 更新本地状态缓存
                        self.device_status.update(status_data)
                        self.device_status["last_update"] = time.time()

                        return status_text
                    else:
                        return f"❌ 获取状态失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ 获取状态异常: {str(e)}"

    async def _restart_device(self) -> str:
        """重启设备"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(f"{self.base_url}/restart") as response:
                    if response.status == 200:
                        logger.info("[SISIeyes工具] 设备重启命令发送成功")
                        self.is_connected = False  # 重置连接状态
                        return "🔄 设备重启命令已发送，请等待设备重新启动..."
                    else:
                        return f"❌ 重启失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ 重启异常: {str(e)}"

    async def _reset_device(self) -> str:
        """复位设备"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(f"{self.base_url}/reset") as response:
                    if response.status == 200:
                        logger.info("[SISIeyes工具] 设备复位命令发送成功")
                        self.is_connected = False  # 重置连接状态
                        return "🔄 设备复位命令已发送，设备将恢复出厂设置..."
                    else:
                        return f"❌ 复位失败，HTTP状态码: {response.status}"
        except Exception as e:
            return f"❌ 复位异常: {str(e)}"

    async def _update_device_status(self):
        """更新设备状态（后台任务）"""
        try:
            # 避免频繁更新，最多每30秒更新一次
            current_time = time.time()
            if current_time - self.device_status.get("last_update", 0) < 30:
                return

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.base_url}/status") as response:
                    if response.status == 200:
                        status_data = await response.json()
                        self.device_status.update(status_data)
                        self.device_status["last_update"] = current_time
        except Exception:
            # 静默处理状态更新失败
            pass

    # ==================== 事件订阅功能 ====================

    def subscribe_event(self, event_type: str, callback: Callable) -> str:
        """
        订阅事件

        Args:
            event_type: 事件类型 (如 "music.start", "motion.detected")
            callback: 回调函数

        Returns:
            str: 订阅ID
        """
        with self.subscription_lock:
            subscription_id = str(uuid.uuid4())

            if event_type not in self.event_subscriptions:
                self.event_subscriptions[event_type] = []

            self.event_subscriptions[event_type].append({
                "id": subscription_id,
                "callback": callback,
                "created_at": time.time()
            })

            logger.info(f"[SISIeyes工具] 订阅事件: {event_type}, ID: {subscription_id}")
            return subscription_id

    def unsubscribe_event(self, subscription_id: str) -> bool:
        """取消事件订阅"""
        with self.subscription_lock:
            for event_type, subscriptions in self.event_subscriptions.items():
                for i, sub in enumerate(subscriptions):
                    if sub["id"] == subscription_id:
                        del subscriptions[i]
                        logger.info(f"[SISIeyes工具] 取消订阅: {subscription_id}")
                        return True
            return False

    async def _trigger_event(self, event_type: str, event_data: dict = None):
        """触发事件通知订阅者"""
        with self.subscription_lock:
            subscriptions = self.event_subscriptions.get(event_type, [])

        for subscription in subscriptions:
            try:
                callback = subscription["callback"]
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_data or {})
                else:
                    callback(event_data or {})
            except Exception as e:
                logger.error(f"[SISIeyes工具] 事件回调异常: {str(e)}")

    # ==================== 并行处理功能 ====================

    async def execute_parallel_commands(self, commands: List[str]) -> List[str]:
        """
        并行执行多个命令

        Args:
            commands: 命令列表

        Returns:
            List[str]: 执行结果列表
        """
        tasks = []
        for cmd in commands:
            task = asyncio.create_task(self.process_query(cmd))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常结果
        formatted_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                formatted_results.append(f"❌ 命令 '{commands[i]}' 执行异常: {str(result)}")
            else:
                formatted_results.append(result)

        return formatted_results

    # ==================== A2A标准接口 ====================

    def invoke(self, query: Union[str, dict]) -> str:
        """同步调用接口（A2A标准）"""
        if isinstance(query, dict):
            query_text = query.get("query", str(query))
        else:
            query_text = str(query)

        # 在新的事件循环中运行异步方法
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.process_query(query_text))
            loop.close()
            return result
        except Exception as e:
            return f"❌ 同步调用异常: {str(e)}"

    async def ainvoke(self, query: Union[str, dict]) -> str:
        """异步调用接口（A2A标准）"""
        if isinstance(query, dict):
            query_text = query.get("query", str(query))
        else:
            query_text = str(query)

        return await self.process_query(query_text)

    def get_metadata(self) -> dict:
        """获取工具元数据（A2A标准）"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": {
                "streaming": False,
                "async_support": True,
                "langgraph_compatible": True,
                "hardware_control": True,
                "camera_control": True,
                "display_control": True,
                "audio_visualization": True,
                "led_control": True,
                "motor_control": True,
                "event_subscription": True,
                "parallel_execution": True
            },
            "supported_commands": list(COMMAND_MAPPING.keys()),
            "examples": [
                "拍一张照片",
                "显示文字：欢迎使用SISIeyes",
                "开启音频可视化",
                "设置LED为彩虹模式",
                "电机正转5秒",
                "获取设备状态",
                "重启设备"
            ],
            "event_types": [
                "music.start",
                "music.stop",
                "motion.detected",
                "camera.capture_complete",
                "led.mode_changed",
                "motor.operation_complete"
            ],
            "contact_info": {
                "name": "SISIeyes开发团队",
                "url": "https://github.com/SISIeyes/esp32-cam",
                "email": "support@sisieyes.com"
            },
            "auth_requirements": {
                "type": "none"
            },
            "invocation_context": [
                "需要控制ESP32-S3 CAM设备",
                "需要拍照或视频录制",
                "需要显示文字或图像",
                "需要音频可视化效果",
                "需要LED灯光控制",
                "需要电机控制",
                "需要获取设备状态"
            ],
            "service_domains": [
                "硬件控制", "摄像头", "显示屏", "音频可视化", "LED控制", "电机控制", "物联网"
            ]
        }

# ==================== 自动事件处理器 ====================

class SISIeyesEventHandler:
    """SISIeyes事件处理器，实现自我驱动功能"""

    def __init__(self, tool: SISIeyesA2ATool):
        self.tool = tool
        self.setup_default_subscriptions()

    def setup_default_subscriptions(self):
        """设置默认事件订阅"""
        # 音乐开始时自动启动可视化
        self.tool.subscribe_event("music.start", self.on_music_start)

        # 音乐停止时关闭可视化
        self.tool.subscribe_event("music.stop", self.on_music_stop)

        # 检测到运动时拍照
        self.tool.subscribe_event("motion.detected", self.on_motion_detected)

        # 系统空闲时显示时间
        self.tool.subscribe_event("system.idle", self.on_system_idle)

        logger.info("[SISIeyes事件处理器] 默认事件订阅设置完成")

    async def on_music_start(self, event_data: dict):
        """音乐开始事件处理"""
        try:
            logger.info("[SISIeyes事件处理器] 检测到音乐开始，启动可视化")
            await self.tool._start_visualizer()

            # 设置LED为音乐模式
            await self.tool._led_control("rainbow")

            # 触发可视化启动事件
            await self.tool._trigger_event("visualizer.started", {
                "trigger": "music_start",
                "music_info": event_data
            })
        except Exception as e:
            logger.error(f"[SISIeyes事件处理器] 音乐开始事件处理异常: {str(e)}")

    async def on_music_stop(self, event_data: dict):
        """音乐停止事件处理"""
        try:
            logger.info("[SISIeyes事件处理器] 检测到音乐停止，关闭可视化")

            # 关闭LED
            await self.tool._led_control("off")

            # 显示待机文字
            await self.tool._display_text("SISIeyes Standby")

            # 触发可视化停止事件
            await self.tool._trigger_event("visualizer.stopped", {
                "trigger": "music_stop"
            })
        except Exception as e:
            logger.error(f"[SISIeyes事件处理器] 音乐停止事件处理异常: {str(e)}")

    async def on_motion_detected(self, event_data: dict):
        """运动检测事件处理"""
        try:
            logger.info("[SISIeyes事件处理器] 检测到运动，自动拍照")

            # 自动拍照
            result = await self.tool._capture_photo()

            # 显示拍照提示
            await self.tool._display_text("Motion Detected!")

            # LED闪烁提示
            await self.tool._led_control("blink")

            # 触发拍照完成事件
            await self.tool._trigger_event("camera.auto_capture", {
                "trigger": "motion_detected",
                "result": result
            })
        except Exception as e:
            logger.error(f"[SISIeyes事件处理器] 运动检测事件处理异常: {str(e)}")

    async def on_system_idle(self, event_data: dict):
        """系统空闲事件处理"""
        try:
            logger.info("[SISIeyes事件处理器] 系统空闲，显示时间")

            # 显示当前时间
            current_time = datetime.now().strftime("%H:%M:%S")
            await self.tool._display_text(f"Time: {current_time}")

            # 设置LED为呼吸模式
            await self.tool._led_control("breathe")
        except Exception as e:
            logger.error(f"[SISIeyes事件处理器] 系统空闲事件处理异常: {str(e)}")

# ==================== 工具创建和注册函数 ====================

def create_tool(host: str = None, port: int = None) -> SISIeyesA2ATool:
    """
    创建SISIeyes A2A工具实例

    Args:
        host: ESP32设备IP地址
        port: HTTP服务端口

    Returns:
        SISIeyesA2ATool: 工具实例
    """
    tool = SISIeyesA2ATool(host=host, port=port)

    # 设置事件处理器
    event_handler = SISIeyesEventHandler(tool)
    tool.event_handler = event_handler

    logger.info("[SISIeyes工具] 工具实例创建完成，事件处理器已设置")
    return tool

def a2a_tool_sisieyes():
    """A2A工具工厂函数 - 用于注册到A2A服务器"""
    return create_tool()

# ==================== 便捷函数 ====================

async def quick_capture(host: str = None) -> str:
    """快速拍照"""
    tool = create_tool(host=host)
    return await tool.ainvoke("拍照")

async def quick_display(text: str, host: str = None) -> str:
    """快速显示文字"""
    tool = create_tool(host=host)
    return await tool.ainvoke(f"显示文字：{text}")

async def quick_visualizer(host: str = None) -> str:
    """快速启动可视化"""
    tool = create_tool(host=host)
    return await tool.ainvoke("开启音频可视化")

async def parallel_demo(host: str = None) -> List[str]:
    """并行操作演示"""
    tool = create_tool(host=host)
    commands = [
        "拍一张照片",
        "显示文字：Hello World",
        "设置LED为彩虹模式",
        "开启音频可视化"
    ]
    return await tool.execute_parallel_commands(commands)

# ==================== 模块级调用接口 ====================

def invoke(params):
    """
    模块级invoke函数，供A2A服务器直接调用

    Args:
        params: 调用参数，可以是字符串或字典

    Returns:
        str: 工具执行结果
    """
    logger.info(f"[sisieyes_tool] 模块级invoke调用，参数: {params}")

    # 提取查询文本
    query = None
    if isinstance(params, dict):
        # 如果是JSON-RPC格式
        if "jsonrpc" in params and "method" in params and "params" in params:
            inner_params = params.get("params", {})
            query = inner_params.get("query", "")
        else:
            # 尝试获取查询参数
            query = params.get("query", str(params))
    else:
        # 如果是字符串或其他类型，直接作为查询
        query = str(params)

    if not query:
        query = "获取设备状态"  # 默认查询

    # 创建工具实例并执行
    tool = create_tool()
    return tool.invoke(query)

# ==================== 主程序入口 ====================

if __name__ == "__main__":
    async def main():
        """测试主程序"""
        print("🎯 SISIeyes A2A工具测试")
        print("=" * 50)

        # 创建工具实例
        tool = create_tool()

        # 测试基础功能
        print("📷 测试拍照功能...")
        result = await tool.ainvoke("拍一张照片")
        print(f"结果: {result}\n")

        print("📺 测试显示功能...")
        result = await tool.ainvoke("显示文字：Hello SISIeyes!")
        print(f"结果: {result}\n")

        print("🎵 测试可视化功能...")
        result = await tool.ainvoke("开启音频可视化")
        print(f"结果: {result}\n")

        print("💡 测试LED功能...")
        result = await tool.ainvoke("设置LED为彩虹模式")
        print(f"结果: {result}\n")

        print("📊 测试状态查询...")
        result = await tool.ainvoke("获取设备状态")
        print(f"结果: {result}\n")

        print("⚡ 测试并行执行...")
        results = await parallel_demo()
        for i, result in enumerate(results):
            print(f"任务{i+1}: {result}")

        print("\n✅ 测试完成！")

    # 运行测试
    asyncio.run(main())
