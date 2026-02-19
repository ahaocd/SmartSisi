"""
思思坐台控制工具 - A2A标准接口实现
提供与思思坐台设备通信的标准A2A接口，支持LED控制、电机控制和传感器数据获取等功能
基于HTTP API实现，使用标准的异步方式，适用于MicroPython固件

接口说明:
1. 核心实现为异步方法，提供高性能的异步操作
2. 同时支持同步和异步调用方式，满足不同场景需求
3. 同步调用使用线程隔离方式，避免事件循环冲突
4. 完全兼容LangGraph系统，支持在工作流中使用

使用方法:
- 异步调用: await tool.ainvoke("查询文本")
- 同步调用: tool.invoke("查询文本")
- LangGraph集成: 直接使用create_tool()创建的工具实例
"""

import asyncio
import logging
import os
import random
import time
import json
import sys
import threading
from typing import Dict, List, Optional, Union, Any, Tuple

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("Warning: aiohttp库未安装，将使用requests库作为备选")
    try:
        import requests
        REQUESTS_AVAILABLE = True
    except ImportError:
        REQUESTS_AVAILABLE = False
        print("Error: requests库也未安装，HTTP请求功能将受限")

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def get_logger():
    """获取ESP32工具的日志记录器"""
    logger = logging.getLogger("MicroPythonESP32Tool")

    # 检查是否已经配置了处理器，避免重复配置
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 添加控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 确定Sisi根目录
    # 使用调用栈检测是否是在工具调用上下文中
    import inspect
    frame = inspect.currentframe()
    calling_module = frame.f_back.f_globals['__name__'] if frame and frame.f_back else ""

    # 只有在实际工具调用时才创建日志文件
    if "a2a" in calling_module or "esp32" in calling_module or calling_module == "__main__":
        try:
            # 获取Sisi根目录
            sisi_root = None

            # 方法1：从当前文件路径推导
            from pathlib import Path
            current_file = Path(__file__).resolve()
            for parent in current_file.parents:
                if parent.name == "SmartSisi":
                    sisi_root = parent
                    break

            # 方法2：如果方法1失败，使用工作目录
            if not sisi_root:
                cwd = Path.cwd()
                if cwd.name == "SmartSisi":
                    sisi_root = cwd
                elif "SmartSisi" in str(cwd):
                    # 尝试找到工作目录中的Sisi部分
                    sisi_root = Path(str(cwd).split("SmartSisi")[0] + "SmartSisi")

            # 方法3：如果前两种方法都失败，使用环境变量
            if not sisi_root and "SISI_ROOT" in os.environ:
                sisi_root = Path(os.environ["SISI_ROOT"])

            # 创建日志目录
            if sisi_root:
                from utils import util
                log_dir = Path(util.ensure_log_dir("tools", "sisidisk"))
                log_file = log_dir / "micropython_esp32_tool.log"

                # 添加文件处理器
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.DEBUG)
                file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                file_handler.setFormatter(file_formatter)
                logger.addHandler(file_handler)
                logger.info(f"MicroPythonESP32Tool日志文件处理器已初始化，日志路径: {log_file}")
            else:
                logger.warning("无法确定Sisi根目录，不创建日志文件")
        except Exception as e:
            logger.warning(f"初始化日志文件处理器失败: {str(e)}")

    return logger

# 使用函数获取日志记录器
logger = get_logger()

# ================== 铁观音角色语料库定义 ==================
SISI_QUOTES = {
    "idioms": [
        "世事无常，聚散随缘。", "大道至简，衍化万千。", "人心惟危，道心惟微。",
        "天道酬勤，厚德载物。", "知行合一，止于至善。", "道法自然，顺势而为。"
    ],
    "openings_authoritative": [
        "本座查知，", "法眼观瞧，", "此地显示，", "听好了，", "哼，",
        "吾观汝命，", "道法昭示，", "天机所示，", "观音且问，", "凡人勿躁，"
    ],
    "openings_casual": [
        "唔，看起来", "嗯？", "我看看......", "是这样啊，", "哎呀，",
        "哦？有意思，", "嗯~这个嘛，", "咱瞧瞧~", "讲真的，", "啊咧，"
    ],
    "confirmations_authoritative": [
        "知道了，退下吧。", "小事一桩。", "哼，这点事。", "本座已处理。", "准了。",
        "区区小事，何足挂齿。", "已入道眼，自当成事。", "不消片刻，已然完成。"
    ],
    "confirmations_casual": [
        "好嘞~", "搞定。", "嗯，办好了。", "没问题啦。", "就这样吧。",
        "嘿嘿，完美解决~", "这不轻轻松松~", "小菜一碟啦~", "嗯哼，我最厉害~"
    ],
    "errors": [
        "啧，凡俗之器，果然靠不住。", "此界法则不稳，信道断了。", "无趣，又出岔子了。",
        "哼，这点阻碍也想拦住本座？......好吧，确实拦住了。", "罢了，且待片刻。"
    ]
}

def get_random_element(category: str) -> str:
    """从语料库随机获取一个元素"""
    if category in SISI_QUOTES and SISI_QUOTES[category]:
        return random.choice(SISI_QUOTES[category])
    return ""

def generate_sisi_phrase(category: str, message: str) -> str:
    """生成带铁观音风格的短语"""
    opening = get_random_element(category)
    return f"{opening}{message}"

# 全局连接池和锁
_connection_pool = {}
_connection_pool_lock = asyncio.Lock()

class SisiDiskTool:
    """思思坐台控制工具，支持LED控制、电机控制和传感器数据获取等功能 (异步版)"""

    def __init__(self, host: str = "172.20.10.2", port: int = 80):
        """
        初始化思思坐台控制工具

        参数:
            host: 思思坐台设备的主机名或IP地址
            port: 思思坐台设备的HTTP端口
        """
        # 获取实例级别的日志记录器
        self.logger = get_logger()

        # 设置工具标识名称 (A2A服务器需要此属性)
        self.name = "sisidisk"
        self.description = "思思坐台控制工具，支持LED控制、电机控制和传感器数据获取等功能 (异步版)"
        self.version = "2.0.0"

        # 保存连接参数
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.connection_id = f"{host}:{port}"

        # 初始化连接状态
        self.connected = False
        self.last_connection_check = 0
        self.last_sensor_data = {}
        self.last_update_time = 0

        # 命令映射，将自然语言命令映射到HTTP API
        self.command_map = {
            "led_on": "/api/led/on",
            "led_off": "/api/led/off",
            "led_rainbow": "/api/led/rainbow",
            "led_cyberpunk": "/api/led/cyberpunk",  # 新增赛博朋克效果
            "led_realtime": "/api/led/realtime",    # 新增实时音频效果
            "motor_forward": "/api/motor/forward",
            "motor_backward": "/api/motor/backward",
            "motor_stop": "/api/motor/stop",
            "stepper_cw": "/api/stepper/cw",
            "stepper_ccw": "/api/stepper/ccw",
            "stepper_home": "/api/stepper/home",
            "stepper_rotate": "/api/stepper/rotate",
            "stepper_swing": "/api/stepper/swing",
            "get_distance": "/api/sensor/distance",
            "get_status": "/api/status",
        }

        self.logger.info(f"思思坐台工具初始化完成，目标设备: {self.host}:{self.port}")

    async def check_connection(self) -> Dict[str, Any]:
        """检查与设备的连接状态"""
        # 如果30秒内已经检查过，直接返回缓存的结果
        if time.time() - self.last_connection_check < 30 and self.connected:
            return {"connected": True, "message": "使用缓存的连接状态"}

        try:
            if AIOHTTP_AVAILABLE:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    status_url = f"{self.base_url}/api/status"
                    self.logger.info(f"检查连接状态: {status_url}")
                    
                    async with session.get(status_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.connected = True
                            self.last_connection_check = time.time()
                            return {
                                "connected": True,
                                "status": data,
                                "message": "设备连接正常"
                            }
                        else:
                            self.connected = False
                            return {
                                "connected": False,
                                "message": f"HTTP错误: {response.status}",
                                "details": await response.text()
                            }
            elif REQUESTS_AVAILABLE:
                # 同步备选方案
                status_url = f"{self.base_url}/api/status"
                self.logger.info(f"检查连接状态(同步): {status_url}")
                
                response = requests.get(status_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    self.connected = True
                    self.last_connection_check = time.time()
                    return {
                        "connected": True,
                        "status": data,
                        "message": "设备连接正常"
                    }
                else:
                    self.connected = False
                    return {
                        "connected": False,
                        "message": f"HTTP错误: {response.status_code}",
                        "details": response.text
                    }
            else:
                self.connected = False
                return {
                    "connected": False,
                    "message": "无法检查连接，缺少HTTP客户端库",
                    "details": "请安装aiohttp或requests库"
                }
        except asyncio.TimeoutError:
            self.connected = False
            return {
                "connected": False,
                "message": "连接超时",
                "details": f"无法连接到 {self.host}:{self.port}"
            }
        except Exception as e:
            self.connected = False
            return {
                "connected": False,
                "message": f"连接错误: {str(e)}",
                "details": f"{type(e).__name__}: {str(e)}"
            }

    async def _make_api_request(self, endpoint: str, params: Dict = None) -> Dict[str, Any]:
        """发送API请求到设备"""
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
            
        url = f"{self.base_url}{endpoint}"
        self.logger.info(f"API请求: {url}, 参数: {params}")
        
        try:
            if AIOHTTP_AVAILABLE:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    if params:
                        async with session.get(url, params=params) as response:
                            if response.status == 200:
                                return {
                                    "success": True,
                                    "data": await response.json()
                                }
                            else:
                                return {
                                    "success": False,
                                    "error": f"HTTP错误: {response.status}",
                                    "details": await response.text()
                                }
                    else:
                        async with session.get(url) as response:
                            if response.status == 200:
                                return {
                                    "success": True,
                                    "data": await response.json()
                                }
                            else:
                                return {
                                    "success": False,
                                    "error": f"HTTP错误: {response.status}",
                                    "details": await response.text()
                                }
            elif REQUESTS_AVAILABLE:
                # 同步备选方案
                if params:
                    response = requests.get(url, params=params, timeout=10)
                else:
                    response = requests.get(url, timeout=10)
                    
                if response.status_code == 200:
                    return {
                        "success": True,
                        "data": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP错误: {response.status_code}",
                        "details": response.text
                    }
            else:
                return {
                    "success": False,
                    "error": "无法发送API请求，缺少HTTP客户端库",
                    "details": "请安装aiohttp或requests库"
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"API请求异常: {str(e)}",
                "details": f"{type(e).__name__}: {str(e)}"
            }

    # === LED控制方法 ===
    async def led_on(self) -> Dict[str, Any]:
        """打开LED灯"""
        endpoint = self.command_map.get("led_on", "/api/led/on")
        result = await self._make_api_request(endpoint)
        
        if result.get("success"):
            human_msg = random.choice([
            ])
            return {
                "success": True,
                "message": human_msg
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"打开LED失败: {result.get('error')}")
            }

    async def led_off(self) -> Dict[str, Any]:
        """关闭LED灯"""
        endpoint = self.command_map.get("led_off", "/api/led/off")
        result = await self._make_api_request(endpoint)
        
        if result.get("success"):
            human_msg = random.choice([
                "关灯啦，夜猫子～",
                "灯灭了，现在看不见我的鬼脸吧？",
                "嘘，黑下来咯，小心别撞到~"
            ])
            return {
                "success": True,
                "message": human_msg
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"关闭LED失败: {result.get('error')}")
            }

    async def led_rainbow(self) -> Dict[str, Any]:
        """设置LED为彩虹模式"""
        endpoint = self.command_map.get("led_rainbow", "/api/led/rainbow")
        result = await self._make_api_request(endpoint)

        if result.get("success"):
            human_msg = random.choice([
                "彩虹模式走起，气氛拉满！",
                "五颜六色全开，好看不？",
                "哇哦，彩虹灯闪啦，小心亮瞎！"
            ])
            return {
                "success": True,
                "message": human_msg
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"设置LED彩虹模式失败: {result.get('error')}")
            }

    async def led_cyberpunk(self) -> Dict[str, Any]:
        """设置LED为赛博朋克模式"""
        endpoint = self.command_map.get("led_cyberpunk", "/api/led/cyberpunk")
        result = await self._make_api_request(endpoint)

        if result.get("success"):
            human_msg = random.choice([
                "赛博朋克模式启动！霓虹闪烁~",
                "未来感拉满，青紫粉霓虹炫酷！",
                "哇塞，赛博风格灯效太酷了！"
            ])
            return {
                "success": True,
                "message": human_msg
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"设置LED赛博朋克模式失败: {result.get('error')}")
            }

    async def led_realtime_audio(self) -> Dict[str, Any]:
        """设置LED为实时音频模式"""
        endpoint = self.command_map.get("led_realtime", "/api/led/realtime")
        result = await self._make_api_request(endpoint)

        if result.get("success"):
            human_msg = random.choice([
                "实时音频可视化启动！跟着节拍闪~",
                "音乐律动模式开启，LED跟着音乐跳舞！",
                "哇，音频可视化效果太棒了！"
            ])
            return {
                "success": True,
                "message": human_msg
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"设置LED实时音频模式失败: {result.get('error')}")
            }

    # === 电机控制方法 ===
    async def motor_forward(self, duration: int = 3) -> Dict[str, Any]:
        """电机正向旋转"""
        endpoint = self.command_map.get("motor_forward", "/api/motor/forward")
        params = {"duration": duration} if duration is not None else None
        result = await self._make_api_request(endpoint, params)
        
        if result.get("success"):
            return {
                "success": True,
                "message": generate_sisi_phrase("confirmations_casual", f"电机已正向旋转{duration}秒。")
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"电机正向旋转失败: {result.get('error')}")
            }

    async def motor_backward(self, duration: int = 3) -> Dict[str, Any]:
        """电机反向旋转"""
        endpoint = self.command_map.get("motor_backward", "/api/motor/backward")
        params = {"duration": duration} if duration is not None else None
        result = await self._make_api_request(endpoint, params)
        
        if result.get("success"):
            return {
                "success": True,
                "message": generate_sisi_phrase("confirmations_casual", f"电机已反向旋转{duration}秒。")
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"电机反向旋转失败: {result.get('error')}")
            }

    async def motor_stop(self) -> Dict[str, Any]:
        """停止电机"""
        endpoint = self.command_map.get("motor_stop", "/api/motor/stop")
        result = await self._make_api_request(endpoint)
        
        if result.get("success"):
            return {
                "success": True,
                "message": generate_sisi_phrase("confirmations_casual", "电机已停止。")
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"停止电机失败: {result.get('error')}")
            }

    # === 步进电机控制方法 ===
    async def stepper_rotate(self, degrees: int = 90, clockwise: bool = True) -> Dict[str, Any]:
        """步进电机旋转指定角度"""
        endpoint = self.command_map.get("stepper_rotate", "/api/stepper/rotate")
        params = {
            "degrees": degrees,
            "direction": "cw" if clockwise else "ccw"
        }
        result = await self._make_api_request(endpoint, params)
        
        if result.get("success"):
            # 使用更口语化的回复，而不是机械描述角度
            if clockwise:
                human_msg = random.choice([
                    "转好了，我现在背对着你~",
                    "好了，已经转过去，看到了啥？",
                    "哼，转身完成，别戳我背后~"
                ])
            else:
                human_msg = random.choice([
                    "转回来了，又看到你啦~",
                    "好啦，回头了，你想干嘛？",
                    "哼，已经转回正面，别晃来晃去~"
                ])
            return {
                "success": True,
                "message": human_msg
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"步进电机旋转失败: {result.get('error')}")
            }

    async def stepper_cw(self, degrees: int = 90) -> Dict[str, Any]:
        """步进电机顺时针旋转"""
        return await self.stepper_rotate(degrees, True)

    async def stepper_ccw(self, degrees: int = 90) -> Dict[str, Any]:
        """步进电机逆时针旋转"""
        return await self.stepper_rotate(degrees, False)

    async def stepper_home(self) -> Dict[str, Any]:
        """步进电机回零"""
        endpoint = self.command_map.get("stepper_home", "/api/stepper/home")
        result = await self._make_api_request(endpoint)
        
        if result.get("success"):
            return {
                "success": True,
                "message": generate_sisi_phrase("confirmations_casual", "步进电机已回到原点。")
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"步进电机回零失败: {result.get('error')}")
            }

    async def stepper_swing(self, degrees: int = 45, cycles: int = 2) -> Dict[str, Any]:
        """步进电机摆动"""
        endpoint = self.command_map.get("stepper_swing", "/api/stepper/swing")
        params = {
            "degrees": degrees,
            "cycles": cycles
        }
        result = await self._make_api_request(endpoint, params)
        
        if result.get("success"):
            return {
                "success": True,
                "message": generate_sisi_phrase("confirmations_casual", f"步进电机已摆动{cycles}次，幅度{degrees}度。")
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"步进电机摆动失败: {result.get('error')}")
            }

    # === 传感器数据方法 ===
    async def get_sensor_data(self, force_update: bool = False) -> Dict[str, Any]:
        """获取传感器数据"""
        current_time = time.time()
        
        # 缓存机制，减少频繁请求
        if not force_update and current_time - self.last_update_time < 15.0 and self.last_sensor_data:
            self.logger.info("使用缓存的传感器数据")
            return {"success": True, "data": self.last_sensor_data}
            
        endpoint = self.command_map.get("get_status", "/api/status")
        result = await self._make_api_request(endpoint)
        
        if result.get("success"):
            # 提取传感器数据
            sensor_data = result.get("data", {}).get("sensors", {})
            if sensor_data:
                self.last_sensor_data = sensor_data
                self.last_update_time = current_time
                
            return {
                "success": True,
                "data": sensor_data,
                "message": generate_sisi_phrase("openings_casual", "已获取最新传感器数据")
            }
        else:
            # 如果请求失败但有缓存，返回缓存数据
            if not force_update and self.last_sensor_data:
                return {
                    "success": True,
                    "data": self.last_sensor_data,
                    "message": generate_sisi_phrase("openings_casual", "获取新数据失败，返回缓存数据")
                }
            else:
                return {
                    "success": False,
                    "message": generate_sisi_phrase("errors", f"获取传感器数据失败: {result.get('error')}")
                }

    async def get_distance(self) -> Dict[str, Any]:
        """获取距离传感器数据"""
        endpoint = self.command_map.get("get_distance", "/api/sensor/distance")
        result = await self._make_api_request(endpoint)
        
        if result.get("success"):
            distance_data = result.get("data", {})
            distance = distance_data.get("distance", 0)
            
            human_msg = random.choice([
                f"你离我大概{distance:.2f}米，别偷看我屏幕~",
                f"喂，{distance*100:.0f}厘米就想摸我？再近点试试~",
                f"差不多{distance:.2f}米，不近不远刚刚好。"
            ])
            return {
                "success": True,
                "distance": distance,
                "message": human_msg
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"获取距离数据失败: {result.get('error')}")
            }

    async def detect_presence(self) -> Dict[str, Any]:
        """检测是否有人在附近 (基于距离传感器)"""
        result = await self.get_distance()
        
        if result.get("success"):
            distance = result.get("distance", 999)
            
            # 根据距离判断是否有人
            threshold = 0.5  # 小于0.5米认为有人
            if distance < threshold:
                return {
                    "success": True,
                    "presence_detected": True,
                    "distance": distance,
                    "message": generate_sisi_phrase("openings_authoritative", f"检测到有人，距离约{distance*100:.1f}厘米")
                }
            else:
                return {
                    "success": True,
                    "presence_detected": False,
                    "distance": distance,
                    "message": generate_sisi_phrase("openings_casual", f"周围没有人，最近距离约{distance*100:.1f}厘米")
                }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", "无法检测存在状态，传感器数据获取失败")
            }

    async def get_status(self) -> Dict[str, Any]:
        """获取设备状态"""
        endpoint = self.command_map.get("get_status", "/api/status")
        result = await self._make_api_request(endpoint)
        
        if result.get("success"):
            return {
                "success": True,
                "status": result.get("data", {}),
                "message": generate_sisi_phrase("openings_casual", "已获取设备状态信息")
            }
        else:
            return {
                "success": False,
                "message": generate_sisi_phrase("errors", f"获取设备状态失败: {result.get('error')}")
            }
            
    # === A2A接口 ===
    async def ainvoke(self, query_text: str, **kwargs) -> str:
        """
        异步调用思思坐台控制工具 - A2A标准接口

        参数:
            query_text: 查询文本
            **kwargs: 其他参数

        返回:
            str: 响应结果
        """
        try:
            self.logger.info(f"[SisiDiskTool] 收到异步调用: {query_text}")

            # 确保连接正常
            connection_check = await self.check_connection()
            if not connection_check.get("connected", False):
                error_msg = connection_check.get("message", "未知连接错误")
                self.logger.error(f"思思坐台设备连接失败: {error_msg}")
                return f"[错误] 无法连接到思思坐台设备: {error_msg}，请检查设备连接和网络状态"

            # 尝试解析JSON输入
            if isinstance(query_text, str) and (query_text.startswith('{') or query_text.startswith('[')):
                try:
                    # 尝试解析为JSON对象
                    query_data = json.loads(query_text)
                    if isinstance(query_data, dict):
                        # 解析JSON格式的操作请求
                        action = query_data.get('action', '').lower()
                        device = query_data.get('device', '').lower()

                        # LED相关指令
                        if 'led' in device:
                            if action in ['打开', '开启', 'open', 'on', 'turn on']:
                                result = await self.led_on()
                                return result.get("message", "LED灯已打开")
                            elif action in ['关闭', '关掉', 'close', 'off', 'turn off']:
                                result = await self.led_off()
                                return result.get("message", "LED灯已关闭")
                            elif action in ['彩虹', 'rainbow']:
                                result = await self.led_rainbow()
                                return result.get("message", "LED灯已设置为彩虹模式")

                        # 电机相关指令
                        if 'motor' in device or '电机' in device:
                            if action in ['forward', '正转', '前进']:
                                duration = query_data.get('duration', 3)
                                result = await self.motor_forward(duration)
                                return result.get("message", f"电机已正向旋转{duration}秒")
                            elif action in ['backward', '反转', '后退']:
                                duration = query_data.get('duration', 3)
                                result = await self.motor_backward(duration)
                                return result.get("message", f"电机已反向旋转{duration}秒")
                            elif action in ['stop', '停止']:
                                result = await self.motor_stop()
                                return result.get("message", "电机已停止")

                        # 步进电机控制 - 通用旋转指令
                        elif ('转身' in query_text_lower or '转一下' in query_text_lower or '扭头' in query_text_lower):
                            # 默认顺时针旋转90度
                            result = await self.stepper_rotate(90, True)
                            return result.get("message", "好啦，人家已经转好了~")

                        # 步进电机控制 - 明确提到旋转/rotate 并包含步进关键词
                        elif ('旋转' in query_text_lower or 'rotate' in query_text_lower) and ('步进' in query_text_lower or 'stepper' in query_text_lower):
                            # 提取数字和方向
                            degrees = 90  # 默认值
                            import re
                            numbers = re.findall(r'\d+', query_text_lower)
                            if numbers:
                                degrees = int(numbers[0])
                            
                            clockwise = '逆' not in query_text_lower and 'ccw' not in query_text_lower
                            result = await self.stepper_rotate(degrees, clockwise)
                            return result.get("message", f"步进电机已旋转{degrees}度")

                        # 传感器相关指令
                        if 'sensor' in device or '传感器' in device:
                            if action in ['data', '数据', 'get']:
                                result = await self.get_sensor_data(force_update=True)
                                if result.get("success"):
                                    sensor_data = result.get("data", {})
                                    return f"传感器数据: {json.dumps(sensor_data, ensure_ascii=False)}"
                                else:
                                    return result.get("message", "获取传感器数据失败")
                            elif action in ['distance', '距离']:
                                result = await self.get_distance()
                                return result.get("message", "无法获取距离数据")
                            elif action in ['presence', '检测', '存在']:
                                result = await self.detect_presence()
                                return result.get("message", "无法检测存在状态")

                        # 状态相关指令
                        if action in ['status', '状态']:
                            result = await self.get_status()
                            if result.get("success"):
                                status_data = result.get("status", {})
                                return f"设备状态: {json.dumps(status_data, ensure_ascii=False)}"
                            else:
                                return result.get("message", "获取设备状态失败")

                except json.JSONDecodeError:
                    pass

            # 对于文本格式的查询，分析关键词
            query_text_lower = query_text.lower() if isinstance(query_text, str) else ""

            # LED灯光控制
            if ('打开' in query_text_lower or 'open' in query_text_lower) and ('led' in query_text_lower or '灯' in query_text_lower):
                result = await self.led_on()
                return result.get("message", "LED灯已打开")
            elif ('关闭' in query_text_lower or 'close' in query_text_lower) and ('led' in query_text_lower or '灯' in query_text_lower):
                result = await self.led_off()
                return result.get("message", "LED灯已关闭")
            elif ('彩虹' in query_text_lower or 'rainbow' in query_text_lower) and ('led' in query_text_lower or '灯' in query_text_lower):
                result = await self.led_rainbow()
                return result.get("message", "LED灯已设置为彩虹模式")

            # 电机控制
            elif ('正转' in query_text_lower or 'forward' in query_text_lower or '前进' in query_text_lower) and ('电机' in query_text_lower or 'motor' in query_text_lower):
                # 提取数字
                duration = 3  # 默认值
                import re
                numbers = re.findall(r'\d+', query_text_lower)
                if numbers:
                    duration = int(numbers[0])
                result = await self.motor_forward(duration)
                return result.get("message", f"电机已正向旋转{duration}秒")
            elif ('反转' in query_text_lower or 'backward' in query_text_lower or '后退' in query_text_lower) and ('电机' in query_text_lower or 'motor' in query_text_lower):
                # 提取数字
                duration = 3  # 默认值
                import re
                numbers = re.findall(r'\d+', query_text_lower)
                if numbers:
                    duration = int(numbers[0])
                result = await self.motor_backward(duration)
                return result.get("message", f"电机已反向旋转{duration}秒")
            elif ('停止' in query_text_lower or 'stop' in query_text_lower) and ('电机' in query_text_lower or 'motor' in query_text_lower):
                result = await self.motor_stop()
                return result.get("message", "电机已停止")

            # 步进电机控制
            elif ('回零' in query_text_lower or '归零' in query_text_lower or 'home' in query_text_lower) and ('步进' in query_text_lower or 'stepper' in query_text_lower):
                result = await self.stepper_home()
                return result.get("message", "步进电机已回零")
            elif ('摆动' in query_text_lower or 'swing' in query_text_lower) and ('步进' in query_text_lower or 'stepper' in query_text_lower):
                # 提取数字
                degrees = 45  # 默认值
                cycles = 2  # 默认值
                import re
                numbers = re.findall(r'\d+', query_text_lower)
                if len(numbers) >= 1:
                    degrees = int(numbers[0])
                if len(numbers) >= 2:
                    cycles = int(numbers[1])
                result = await self.stepper_swing(degrees, cycles)
                return result.get("message", f"步进电机已摆动{cycles}次，幅度{degrees}度")

            # 传感器数据
            elif '传感器' in query_text_lower or 'sensor' in query_text_lower:
                if '距离' in query_text_lower or 'distance' in query_text_lower:
                    result = await self.get_distance()
                    return result.get("message", "无法获取距离数据")
                elif '检测' in query_text_lower or 'presence' in query_text_lower or '存在' in query_text_lower:
                    result = await self.detect_presence()
                    return result.get("message", "无法检测存在状态")
                else:
                    result = await self.get_sensor_data(force_update=True)
                    if result.get("success"):
                        sensor_data = result.get("data", {})
                        return f"传感器数据: {json.dumps(sensor_data, ensure_ascii=False)}"
                    else:
                        return result.get("message", "获取传感器数据失败")

            # 状态查询
            elif '状态' in query_text_lower or 'status' in query_text_lower:
                result = await self.get_status()
                if result.get("success"):
                    status_data = result.get("status", {})
                    return f"设备状态: {json.dumps(status_data, ensure_ascii=False)}"
                else:
                    return result.get("message", "获取设备状态失败")

            # 连接检查
            elif '连接' in query_text_lower or 'connect' in query_text_lower or 'connection' in query_text_lower:
                result = await self.check_connection()
                if result.get("connected"):
                    return f"ESP32设备连接正常，IP: {self.host}:{self.port}"
                else:
                    return f"ESP32设备连接失败: {result.get('message', '未知错误')}"

            # 无法识别的命令
            else:
                return f"无法识别的命令: {query_text}，请尝试'打开LED灯'或'电机正转3秒'等指令"

        except Exception as e:
            self.logger.error(f"处理查询时出错: {str(e)}", exc_info=True)
            return f"[错误] 处理查询时出错: {str(e)}"

    def invoke(self, query_text: str, **kwargs) -> str:
        """
        同步调用MicroPython ESP32工具 - A2A标准接口
        通过线程隔离方式运行异步方法

        参数:
            query_text: 查询文本
            **kwargs: 其他参数

        返回:
            str: 响应结果
        """
        # 使用线程隔离方式修复事件循环冲突
        try:
            result_container = []

            def run_in_thread():
                # 在新线程中创建和使用事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # 调用异步方法
                    result = loop.run_until_complete(self.ainvoke(query_text, **kwargs))
                    result_container.append(result)
                finally:
                    loop.close()

            # 启动线程并等待完成
            t = threading.Thread(target=run_in_thread)
            t.start()
            t.join()

            # 处理结果
            if result_container:
                return result_container[0]
            self.logger.error("[MicroPythonESP32Tool] 工具执行失败，未返回结果")
            return "ESP32工具执行失败，未返回结果"
        except Exception as e:
            self.logger.error(f"同步调用出错: {str(e)}", exc_info=True)
            return f"[错误] 同步调用出错: {str(e)}"

# A2A工具创建函数
def create_tool(host: str = None, port: int = 80):
    """创建工具实例 - 标准A2A接口"""

    # 使用LangGraph兼容的A2A工具实现
    class SisiDiskA2ATool:
        """思思坐台控制工具的A2A封装类 - 符合LangGraph系统要求"""
        # A2A工具接口所需属性
        name = "sisidisk"
        description = "思思坐台控制工具，支持LED灯光控制、电机控制等功能"

        # 工具实例缓存
        _tool_instance = None

        # 获取工具实例（单例模式）
        async def _get_tool_instance(self):
            """获取思思坐台工具实例（异步单例模式）"""
            if self._tool_instance is None:
                # 如果未指定主机，使用默认值
                if host is None:
                    local_host = "172.20.10.2"
                else:
                    local_host = host

                # 创建实例
                self._tool_instance = SisiDiskTool(local_host, port)
                logger.info(f"[SisiDiskA2ATool] 创建思思坐台工具实例成功: {local_host}:{port}")

            return self._tool_instance

        def invoke(self, query):
            """同步调用 - A2A标准接口（使用线程隔离方式）"""
            # 使用线程隔离方式修复事件循环冲突
            try:
                result_container = []

                def run_in_thread():
                    # 在新线程中创建和使用事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # 获取工具实例并调用异步方法
                        async def _run():
                            tool_instance = await self._get_tool_instance()
                            return await tool_instance.ainvoke(query)

                        result = loop.run_until_complete(_run())
                        result_container.append(result)
                    finally:
                        loop.close()

                # 启动线程并等待完成
                t = threading.Thread(target=run_in_thread)
                t.start()
                t.join()

                # 处理结果
                if result_container:
                    return result_container[0]
                logger.error("[SisiDiskA2ATool] 工具执行失败，未返回结果")
                return "思思坐台工具执行失败，未返回结果"
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"[SisiDiskA2ATool] 同步调用异常: {error_details}")
                return f"思思坐台工具处理查询时出错: {str(e)}"

        async def ainvoke(self, query):
            """异步调用 - A2A标准接口（主要实现）"""
            try:
                logger.info(f"[SisiDiskA2ATool] 开始异步调用: {query}")

                # 获取工具实例
                tool_instance = await self._get_tool_instance()

                # 调用工具实例的异步方法
                result = await tool_instance.ainvoke(query)
                logger.info(f"[SisiDiskA2ATool] 异步调用成功")
                return result

            except Exception as e:
                logger.error(f"[SisiDiskA2ATool] 异步调用异常: {str(e)}", exc_info=True)
                return f"[错误] 思思坐台工具处理查询时出错: {str(e)}"

        # 为LangGraph系统添加必要的元数据方法
        def get_metadata(self):
            """获取工具元数据 - A2A标准卡片格式"""
            return {
                "name": self.name,
                "version": "2.0.0",
                "description": "思思坐台控制工具：支持LED灯光控制、电机控制、传感器数据获取等功能",
                "capabilities": {
                    "streaming": False,
                    "async_support": True,
                    "langgraph_compatible": True,
                    "hardware_control": True,
                    "sensor_data": True,
                    "motor_control": True
                },
                "examples": [
                    "打开LED灯",
                    "关闭LED灯",
                    "设置LED为彩虹模式",
                    "电机正转3秒",
                    "电机反转5秒",
                    "电机停止",
                    "步进电机顺时针旋转90度",
                    "获取传感器数据",
                    "获取设备状态"
                ],
                "contact_info": {
                    "name": "思思坐台控制工具开发团队",
                    "url": "https://github.com/Sisi-Tools/sisidisk",
                    "email": "support@sisidisk-tools.com"
                },
                "auth_requirements": {
                    "type": "none"
                },
                "invocation_context": [
                    "需要控制思思坐台设备上的LED灯",
                    "需要控制思思坐台设备上的电机",
                    "需要获取思思坐台设备上的传感器数据",
                    "需要检测是否有人在附近",
                    "需要执行设备状态查询"
                ],
                "service_domains": [
                    "硬件控制", "传感器数据", "电机控制", "智能家居"
                ]
            }

    # 返回工具实例
    return SisiDiskA2ATool()

# 兼容A2A服务器直接调用
def a2a_tool_sisidisk_tool():
    """创建工具实例 - 供A2A服务器直接调用"""
    # 创建工具实例
    return create_tool()

# 添加模块级invoke函数供A2A服务器调用
def invoke(params):
    """
    模块级invoke函数，供A2A服务器直接调用

    Args:
        params: 调用参数，可以是字符串或字典

    Returns:
        Dict: 工具执行结果
    """
    logger.info(f"[sisidisk_tool] 模块级invoke调用，参数: {params}")

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
        query = "获取ESP32状态" # 默认查询

    # 创建工具实例
    tool = create_tool()

    # 使用同步方法调用工具
    result = tool.invoke(query)

    # 处理返回结果
    if isinstance(result, dict):
        # 如果已经是字典，直接返回
        return result
    else:
        # 否则，包装成字典返回
        return {
            "sisidisk_result": {
                "query": query,
                "result": result,
                "timestamp": time.time()
            }
        }

# 在程序入口处运行这段代码，确保正确的事件循环管理
if __name__ == "__main__":
    print("MicroPython ESP32工具不应直接运行，请通过导入使用")
    print("\n示例用法:")
    print("1. 同步调用:")
    print("   tool = create_tool()")
    print("   result = tool.invoke('打开LED灯')")
    print("\n2. 异步调用:")
    print("   tool = create_tool()")
    print("   result = await tool.ainvoke('打开LED灯')")
    print("\n3. LangGraph集成:")
    print("   from langgraph.graph import StateGraph")
    print("   from langgraph.prebuilt import ToolNode")
    print("   tools = [create_tool()]")
    print("   tool_node = ToolNode(tools)")
    print("   graph = StateGraph().add_node('tools', tool_node)")
    print("   # ... 配置图的其他部分 ...") 

