"""
SmartSisi核心桥接模块 - 基于LangGraph设计理念实现进程间通信
允许A2A服务器进程与主程序中的SmartSisi核心通信
"""
import os
import json
import time
import logging
import threading
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

# 配置日志
logger = logging.getLogger("SisiCoreBridge")
logger.setLevel(logging.INFO)

# 确保日志处理器只添加一次
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'))
    logger.addHandler(console_handler)

class SisiCoreBridge:
    """SmartSisi核心桥接，允许不同进程访问SmartSisi核心"""

    _instance = None
    _lock = threading.RLock()
    _sisi_core_instance = None  # 静态变量，存储SmartSisi核心实例

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def register_sisi_core(cls, sisi_core):
        """注册SmartSisi核心实例"""
        with cls._lock:
            cls._sisi_core_instance = sisi_core
            logger.info(f"SmartSisi核心实例已注册到SmartSisi核心桥接模块，实例ID: {id(sisi_core)}")

            # 如果实例已经创建，更新实例的sisi_core属性
            if cls._instance:
                cls._instance.sisi_core = sisi_core
                cls._instance.is_server = True

                # 更新SmartSisi核心状态
                cls._instance._update_core_status(True)

            return True

    def __init__(self):
        """初始化SmartSisi核心桥接"""
        # 确定基础目录
        self.sisi_root = self._get_sisi_root()

        # 设置桥接目录和文件
        self.bridge_dir = self.sisi_root / "resources" / "bridge"
        self.notification_dir = self.bridge_dir / "notifications"
        self.status_file = self.bridge_dir / "sisi_core_status.json"

        # 确保目录存在
        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        self.notification_dir.mkdir(parents=True, exist_ok=True)

        # 是否是服务端（SmartSisi核心所在进程）
        self.is_server = False
        self.sisi_core = None
        self.server_thread = None
        self.running = False

        # 生成唯一实例ID
        self.instance_id = str(uuid.uuid4())

        # 尝试检查SmartSisi核心状态
        self._check_core_status()

        logger.info(f"SmartSisi核心桥接初始化完成，实例ID: {self.instance_id}, 根目录: {self.sisi_root}")

    def _check_core_status(self):
        """检查SmartSisi核心状态并尝试连接"""
        try:
            # 检查状态文件是否存在
            if self.status_file.exists():
                # 读取状态文件
                with open(self.status_file, "r", encoding="utf-8") as f:
                    status = json.load(f)

                # 检查状态是否有效
                if status.get("is_active", False) and time.time() - status.get("timestamp", 0) < 30:
                    logger.info(f"检测到活跃的SmartSisi核心，实例ID: {status.get('instance_id')}")
                    # 标记为已连接
                    self.is_core_active_cached = True
                    return True

            # 状态文件不存在或状态无效
            logger.info("未检测到活跃的SmartSisi核心，等待SmartSisi核心注册")
            self.is_core_active_cached = False
            return False
        except Exception as e:
            logger.error(f"检查SmartSisi核心状态异常: {str(e)}")
            self.is_core_active_cached = False
            return False

    def _get_sisi_root(self) -> Path:
        """获取Sisi根目录"""
        # 方法1：从当前文件路径推导
        current_file = Path(__file__).resolve()
        for parent in current_file.parents:
            if parent.name == "SmartSisi":
                return parent

        # 方法2：使用工作目录
        cwd = Path.cwd()
        if cwd.name == "SmartSisi":
            return cwd
        elif "SmartSisi" in str(cwd):
            # 尝试找到工作目录中的Sisi部分
            return Path(str(cwd).split("SmartSisi")[0] + "SmartSisi")

        # 方法3：使用环境变量（SISI_ROOT）
        if "SISI_ROOT" in os.environ:
            return Path(os.environ["SISI_ROOT"])

        # 默认返回当前目录
        logger.warning("无法确定Sisi根目录，使用当前目录")
        return Path.cwd()

    def start_server(self, sisi_core):
        """启动服务端，处理通知"""
        with self._lock:
            if self.server_thread is not None and self.server_thread.is_alive():
                logger.warning("SmartSisi核心桥接服务端已在运行")
                return

            self.is_server = True
            self.sisi_core = sisi_core
            self.running = True

            # 更新SmartSisi核心状态
            self._update_core_status(True)

            # 启动服务线程
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()

            logger.info("SmartSisi核心桥接服务端已启动")

    def stop_server(self):
        """停止服务端"""
        with self._lock:
            self.running = False
            if self.server_thread is not None:
                self.server_thread.join(timeout=2)

            # 更新SmartSisi核心状态
            self._update_core_status(False)

            logger.info("SmartSisi核心桥接服务端已停止")

    def _server_loop(self):
        """服务端循环，处理通知"""
        while self.running:
            try:
                # 检查通知目录
                notification_files = list(self.notification_dir.glob("*.json"))

                for notification_path in notification_files:
                    # 读取通知
                    try:
                        with open(notification_path, "r", encoding="utf-8") as f:
                            notification = json.load(f)

                        # 处理通知
                        self._handle_notification(notification)

                        # 删除通知
                        notification_path.unlink()
                        logger.info(f"已处理并删除通知: {notification_path.name}")
                    except Exception as e:
                        logger.error(f"处理通知异常: {str(e)}")

                # 休眠一段时间
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"服务端循环异常: {str(e)}")
                time.sleep(1)

    def _handle_notification(self, notification: Dict[str, Any]):
        """处理通知"""
        try:
            # 提取通知内容
            content = notification.get("content")
            source = notification.get("source")
            is_intermediate = notification.get("is_intermediate", False)
            metadata = notification.get("metadata", {})

            # 调用SmartSisi核心处理通知
            if self.sisi_core and hasattr(self.sisi_core, "agent_callback"):
                # 使用agent_callback方法处理通知
                self.sisi_core.agent_callback(
                    content,
                    "normal",  # 默认风格
                    is_intermediate=is_intermediate,
                    metadata=metadata
                )
                logger.info(f"已处理通知: 来源={source}, 内容长度={len(content) if content else 0}")
            else:
                logger.error("SmartSisi核心没有agent_callback方法")
        except Exception as e:
            logger.error(f"处理通知异常: {str(e)}")

    def _update_core_status(self, is_active: bool):
        """更新SmartSisi核心状态"""
        try:
            status = {
                "is_active": is_active,
                "timestamp": time.time(),
                "instance_id": self.instance_id
            }

            with open(self.status_file, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False)

            logger.info(f"已更新SmartSisi核心状态: {'活跃' if is_active else '不活跃'}")
        except Exception as e:
            logger.error(f"更新SmartSisi核心状态异常: {str(e)}")

    def is_core_active(self) -> bool:
        """检查SmartSisi核心是否活跃"""
        # 如果是服务端，直接返回True
        if self.is_server:
            return True

        # 首先检查静态变量中的SmartSisi核心实例
        if self.__class__._sisi_core_instance:
            logger.info(f"检测到静态变量中的SmartSisi核心实例，实例ID: {id(self.__class__._sisi_core_instance)}")
            return True

        # 尝试从sisi_booter获取已有实例
        try:
            import sys
            if 'sisi_booter' in sys.modules:
                from core import sisi_booter
                if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                    logger.info("检测到sisi_booter中的SmartSisi实例")
                    # 更新静态变量
                    self.__class__._sisi_core_instance = sisi_booter.sisi_core
                    return True
        except Exception as e:
            logger.debug(f"从sisi_booter获取SmartSisi实例失败: {str(e)}")

        # 尝试从core.sisi_booter获取已有实例
        try:
            from core import sisi_booter as core_sisi_booter
            if hasattr(core_sisi_booter, 'sisi_core') and core_sisi_booter.sisi_core:
                logger.info("检测到core.sisi_booter中的SmartSisi实例")
                # 更新静态变量
                self.__class__._sisi_core_instance = core_sisi_booter.sisi_core
                return True
        except Exception as e:
            logger.debug(f"从core.sisi_booter获取SmartSisi实例失败: {str(e)}")

        # 尝试从全局中转站获取
        try:
            # 确保llm在导入路径中
            import sys
            sisi_root = self._get_sisi_root()
            llm_path = os.path.join(sisi_root, "llm")
            if llm_path not in sys.path:
                sys.path.append(llm_path)

            # 导入全局中转站
            from llm.transit_station import get_transit_station
            transit = get_transit_station()
            if transit and hasattr(transit, 'sisi_core') and transit.sisi_core:
                logger.info("检测到全局中转站中的SmartSisi实例")
                # 更新静态变量
                self.__class__._sisi_core_instance = transit.sisi_core
                return True
        except Exception as e:
            logger.debug(f"从全局中转站获取SmartSisi实例失败: {str(e)}")

        # 如果有缓存的状态，先检查缓存是否过期
        if hasattr(self, 'is_core_active_cached') and hasattr(self, 'last_check_time'):
            # 如果上次检查时间在30秒内，直接返回缓存的状态
            if time.time() - getattr(self, 'last_check_time', 0) < 30:
                return self.is_core_active_cached

        # 缓存过期或不存在，重新检查
        try:
            if not self.status_file.exists():
                self.is_core_active_cached = False
                self.last_check_time = time.time()
                return False

            with open(self.status_file, "r", encoding="utf-8") as f:
                status = json.load(f)

            # 检查状态是否过期（超过30秒）
            is_active = status.get("is_active", False) and time.time() - status.get("timestamp", 0) <= 30

            # 更新缓存
            self.is_core_active_cached = is_active
            self.last_check_time = time.time()

            return is_active
        except Exception as e:
            logger.error(f"检查SmartSisi核心状态异常: {str(e)}")
            self.is_core_active_cached = False
            self.last_check_time = time.time()
            return False

    def send_notification(self, content, source, is_intermediate=False, metadata=None):
        """发送通知到SmartSisi核心"""
        if metadata is None:
            metadata = {}

        # 首先尝试使用静态变量中的SmartSisi核心实例
        if self.__class__._sisi_core_instance:
            try:
                # 直接使用静态变量中的SmartSisi核心实例
                logger.info(f"使用静态变量中的SmartSisi核心实例，实例ID: {id(self.__class__._sisi_core_instance)}")
                self.__class__._sisi_core_instance.agent_callback(
                    content,
                    "normal",  # 默认风格
                    is_intermediate=is_intermediate,
                    metadata=metadata
                )
                logger.info(f"直接处理通知: 来源={source}, 内容长度={len(content) if content else 0}")
                return True
            except Exception as e:
                logger.error(f"使用静态变量中的SmartSisi核心实例处理通知异常: {str(e)}")
                # 失败时继续尝试其他方法

        # 尝试直接从sisi_booter获取SmartSisi核心实例
        try:
            import sys
            if 'sisi_booter' in sys.modules:
                from core import sisi_booter
                if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                    # 直接使用SmartSisi核心实例
                    logger.info(f"检测到sisi_booter中的SmartSisi实例，直接使用")
                    sisi_booter.sisi_core.agent_callback(
                        content,
                        "normal",  # 默认风格
                        is_intermediate=is_intermediate,
                        metadata=metadata
                    )
                    logger.info(f"直接处理通知: 来源={source}, 内容长度={len(content) if content else 0}")
                    return True
        except Exception as e:
            logger.error(f"直接使用sisi_booter.sisi_core处理通知异常: {str(e)}")
            # 失败时继续尝试其他方法

        # 如果是服务端，直接处理通知
        if self.is_server and self.sisi_core:
            try:
                # 使用agent_callback方法处理通知
                self.sisi_core.agent_callback(
                    content,
                    "normal",  # 默认风格
                    is_intermediate=is_intermediate,
                    metadata=metadata
                )
                logger.info(f"直接处理通知: 来源={source}, 内容长度={len(content) if content else 0}")
                return True
            except Exception as e:
                logger.error(f"直接处理通知异常: {str(e)}")
                # 失败时回退到文件通知

        try:
            # 创建通知
            notification = {
                "content": content,
                "source": source,
                "is_intermediate": is_intermediate,
                "metadata": metadata,
                "timestamp": time.time(),
                "id": str(uuid.uuid4())
            }

            # 保存通知到文件
            notification_path = os.path.join(self.notification_dir, f"notify_{int(time.time() * 1000)}.json")
            with open(notification_path, "w", encoding="utf-8") as f:
                json.dump(notification, f, ensure_ascii=False)

            logger.info(f"已发送通知: 来源={source}, 内容长度={len(content) if content else 0}")
            return True
        except Exception as e:
            logger.error(f"发送通知异常: {str(e)}")
            return False

# 便捷函数，获取单例实例
def get_bridge():
    """获取SmartSisi核心桥接实例"""
    bridge = SisiCoreBridge.get_instance()

    # 如果静态变量中没有SmartSisi核心实例，尝试从sisi_booter获取
    if not SisiCoreBridge._sisi_core_instance:
        try:
            import sys
            if 'sisi_booter' in sys.modules:
                from core import sisi_booter
                if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                    logger.info(f"get_bridge: 从sisi_booter获取SmartSisi核心实例，实例ID: {id(sisi_booter.sisi_core)}")
                    SisiCoreBridge.register_sisi_core(sisi_booter.sisi_core)
        except Exception as e:
            logger.error(f"get_bridge: 从sisi_booter获取SmartSisi核心实例失败: {str(e)}")

    return bridge
