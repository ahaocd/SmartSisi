"""
状态中转站 - 连接LangGraph工具中间状态与最终输出
作为LangGraph和sisi_core之间的桥梁
"""
import time
import logging
import traceback
import json
import re
import hashlib
import pickle
import os
import platform
from typing import Dict, List, Any, Optional, Union, Tuple
import uuid
import threading

from utils import util
from utils import config_util

# 配置日志
logger = logging.getLogger(__name__)

# 全局单例变量和锁
_GLOBAL_TRANSIT_LOCK = threading.RLock()  # 线程锁
_GLOBAL_TRANSIT_INSTANCE = None

# 跨进程共享的文件锁路径
_TRANSIT_LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "transit_lock")
_TRANSIT_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "transit_instance.pkl")

# 确保目录存在
os.makedirs(os.path.dirname(_TRANSIT_LOCK_FILE), exist_ok=True)

# 跨平台文件锁实现
if platform.system() != 'Windows':
    import fcntl
    def acquire_lock(f):
        fcntl.flock(f, fcntl.LOCK_EX)
    def release_lock(f):
        fcntl.flock(f, fcntl.LOCK_UN)
else:
    import msvcrt
    def acquire_lock(f):
        # Windows文件锁
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        except IOError:
            # 如果锁被占用，等待后重试
            time.sleep(0.1)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    def release_lock(f):
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except IOError:
            pass  # 忽略解锁错误

class TransitStation:
    """状态中转站 - 处理LangGraph结果并集成到sisi_core"""

    @classmethod
    def get_instance(cls):
        """获取中转站单例实例 - 使用文件锁确保跨进程同步"""
        global _GLOBAL_TRANSIT_INSTANCE, _GLOBAL_TRANSIT_LOCK

        with _GLOBAL_TRANSIT_LOCK:
            if _GLOBAL_TRANSIT_INSTANCE is None:
                # 尝试从文件加载现有实例
                try:
                    # 确保目录存在
                    os.makedirs(os.path.dirname(_TRANSIT_LOCK_FILE), exist_ok=True)

                    # 获取文件锁
                    with open(_TRANSIT_LOCK_FILE, 'w+') as lock_file:
                        acquire_lock(lock_file)

                        try:
                            # 检查是否已有序列化的实例
                            if os.path.exists(_TRANSIT_DATA_FILE) and os.path.getsize(_TRANSIT_DATA_FILE) > 0:
                                with open(_TRANSIT_DATA_FILE, 'rb') as f:
                                    # 尝试反序列化
                                    transit_data = pickle.load(f)
                                    session_id = transit_data.get('session_id')
                                    sisi_core_exists = transit_data.get('has_sisi_core', False)

                                    util.log(1, f"[全局中转站] 从文件加载实例数据: 会话ID={session_id}, SmartSisi核心状态={sisi_core_exists}")

                                    # 创建新实例但使用已存在的会话ID
                                    _GLOBAL_TRANSIT_INSTANCE = cls()
                                    _GLOBAL_TRANSIT_INSTANCE.session_id = session_id

                                    # 其他状态通过正常初始化设置
                                    util.log(1, f"[全局中转站] 会话ID继承: {session_id}")
                            else:
                                # 无现有实例，创建新实例
                                _GLOBAL_TRANSIT_INSTANCE = cls()
                                util.log(1, f"[全局中转站] 创建全新实例，会话ID: {_GLOBAL_TRANSIT_INSTANCE.session_id}")

                            # 记录这个实例的内存地址，便于调试
                            instance_id = id(_GLOBAL_TRANSIT_INSTANCE)

                            # 保存实例信息到文件
                            transit_data = {
                                'session_id': _GLOBAL_TRANSIT_INSTANCE.session_id,
                                'has_sisi_core': _GLOBAL_TRANSIT_INSTANCE._sisi_core is not None,
                                'timestamp': time.time(),
                                'instance_id': instance_id  # 添加实例ID用于跟踪
                            }

                            with open(_TRANSIT_DATA_FILE, 'wb') as f:
                                pickle.dump(transit_data, f)

                            util.log(1, f"[全局中转站] 实例已持久化到文件，实例ID: {instance_id}")

                        finally:
                            # 释放文件锁
                            release_lock(lock_file)

                except Exception as e:
                    # 文件操作失败时，回退到普通单例模式
                    util.log(2, f"[全局中转站] 文件持久化失败，使用内存单例: {str(e)}")
                    _GLOBAL_TRANSIT_INSTANCE = cls()

            return _GLOBAL_TRANSIT_INSTANCE

    def __init__(self):
        """初始化中转站实例"""
        self.session_id = str(uuid.uuid4())
        self.intermediate_states = []  # 中间状态集合
        self.tool_notification_states = []  # 工具主动通知队列
        self._sisi_core = None  # SmartSisi核心实例

        # 🔧 新增：存储优化后的内容供UI获取
        self.optimized_contents = {
            "start": None,
            "middle": None,
            "final": None
        }

        # 🔧 新增：LG阶段文本快照（无SisiCore时也可用）
        self.lg_snapshot = {
            "start": None,
            "middle": None,
            "final": None
        }

        # 阶段发送状态跟踪
        self.stage_sent = {
            "start": False,
            "middle": False,
            "final": False,
            "error": False  # 🔥 新增：错误阶段标记
        }

        # 已处理内容哈希集合，按阶段分类
        self.processed_hashes = {
            "start": set(),
            "middle": set(),
            "final": set(),
            "error": set()  # 🔥 新增：错误阶段哈希集合
        }

        # 已处理通知ID集合 - 避免重复处理通知
        self.processed_notification_ids = set()

        # 添加处理锁 - 确保线程安全
        self.notification_lock = threading.RLock()

        # 处理线程控制
        self._stop_notification = False
        self._thread_started = False
        self._notification_thread = None



        util.log(1, f"[全局中转站] 初始化完成 (会话ID: {self.session_id})")

        # 自动启动通知监控线程
        self._start_notification_thread()

    @property
    def sisi_core(self):
        """SmartSisi核心的getter方法"""
        return self._sisi_core

    @sisi_core.setter
    def sisi_core(self, core):
        """SmartSisi核心的setter方法，添加验证"""
        global _GLOBAL_TRANSIT_LOCK

        with _GLOBAL_TRANSIT_LOCK:
            if core is not None:
                self._sisi_core = core
                util.log(1, f"[全局中转站] SmartSisi核心已注册，核心ID: {id(core)} (会话ID: {self.session_id})")

                # 更新文件中的状态
                try:
                    with open(_TRANSIT_LOCK_FILE, 'w+') as lock_file:
                        acquire_lock(lock_file)
                        try:
                            transit_data = {
                                'session_id': self.session_id,
                                'has_sisi_core': True,
                                'timestamp': time.time()
                            }
                            with open(_TRANSIT_DATA_FILE, 'wb') as f:
                                pickle.dump(transit_data, f)
                        finally:
                            release_lock(lock_file)
                except Exception as e:
                    util.log(2, f"[全局中转站] 更新SmartSisi核心状态文件失败: {str(e)}")
            else:
                util.log(2, f"[全局中转站] 警告: 尝试注册空的SmartSisi核心实例 (会话ID: {self.session_id})")

    def register_sisi_core(self, sisi_core):
        """注册SmartSisi核心实例，注册后立即验证，返回True/False"""
        global _GLOBAL_TRANSIT_LOCK

        with _GLOBAL_TRANSIT_LOCK:
            if sisi_core is None:
                util.log(2, f"[全局中转站] 错误: 尝试注册空的SmartSisi核心")
                return False  # 返回失败状态

            # 记录当前SmartSisi核心状态
            old_core_id = id(self._sisi_core) if self._sisi_core else None
            new_core_id = id(sisi_core)

            # 设置SmartSisi核心
            self._sisi_core = sisi_core

            # 更新文件中的状态
            try:
                os.makedirs(os.path.dirname(_TRANSIT_LOCK_FILE), exist_ok=True)
                with open(_TRANSIT_LOCK_FILE, 'w+') as lock_file:
                    acquire_lock(lock_file)
                    try:
                        transit_data = {
                            'session_id': self.session_id,
                            'has_sisi_core': True,
                            'timestamp': time.time(),
                            'instance_id': id(self),
                            'sisi_core_id': new_core_id
                        }
                        with open(_TRANSIT_DATA_FILE, 'wb') as f:
                            pickle.dump(transit_data, f)
                        util.log(1, f"[全局中转站] SmartSisi核心状态已更新到文件 (核心ID: {new_core_id})")
                    finally:
                        release_lock(lock_file)
            except Exception as e:
                util.log(2, f"[全局中转站] 更新SmartSisi核心状态文件失败: {str(e)}")
                return False  # 返回失败状态
            # 验证注册是否成功
            if self._sisi_core is sisi_core:
                util.log(1, f"[全局中转站] SmartSisi核心注册验证成功 (核心ID: {new_core_id})")
                return True
            else:
                util.log(2, f"[全局中转站] SmartSisi核心注册验证失败 (核心ID: {new_core_id})")
                return False

    def _start_notification_thread(self):
        """启动通知处理线程"""
        if self._thread_started:
            return  # 防止重复启动

        self._notification_thread = threading.Thread(target=self._process_pending_notifications)
        self._notification_thread.daemon = True
        self._notification_thread.start()
        self._thread_started = True
        util.log(1, f"[中转站] 通知处理线程已启动 (会话ID: {self.session_id})")

    def _process_pending_notifications(self):
        """持续处理队列中的通知"""
        util.log(1, f"[中转站] 通知处理线程开始运行 (会话ID: {self.session_id})")

        # 记录未注册SmartSisi核心的次数，避免重复日志
        no_sisi_core_count = 0
        last_log_time = 0

        while not self._stop_notification:
            try:
                # 使用锁保护队列访问
                notifications_to_process = []
                with self.notification_lock:
                    # 只有当通知队列不为空时处理
                    if len(self.tool_notification_states) > 0:
                        # 🔥 修复：优先从SmartSisi核心桥接获取SmartSisi核心状态，而不依赖中转站实例
                        has_sisi_core_via_bridge = False
                        try:
                            from llm.sisi_core_bridge import SisiCoreBridge
                            # 检查桥接模块的静态变量
                            if SisiCoreBridge._sisi_core_instance:
                                has_sisi_core_via_bridge = True
                                util.log(1, f"[中转站] 通过SmartSisi核心桥接检测到SmartSisi核心实例，ID: {id(SisiCoreBridge._sisi_core_instance)}")
                        except Exception as bridge_err:
                            util.log(2, f"[中转站] 检查SmartSisi核心桥接异常: {str(bridge_err)}")
                        
                        # 记录线程中的SmartSisi核心状态 - 优先显示桥接状态
                        has_sisi_core_local = self.sisi_core is not None
                        if has_sisi_core_via_bridge:
                            util.log(1, f"[中转站] 发现{len(self.tool_notification_states)}条通知待处理，SmartSisi核心状态：已注册(通过桥接)")
                        elif has_sisi_core_local:
                            util.log(1, f"[中转站] 发现{len(self.tool_notification_states)}条通知待处理，SmartSisi核心状态：已注册(本地)")
                        else:
                            util.log(1, f"[中转站] 发现{len(self.tool_notification_states)}条通知待处理，SmartSisi核心状态：未注册")

                        # 复制需要处理的通知
                        for notification in self.tool_notification_states:
                            # 为每个通知生成唯一ID
                            # 🔥 修复：只使用内容hash作为通知ID，避免对象id导致重复
                            # 计算内容哈希作为唯一标识
                            import hashlib
                            content_to_hash = json.dumps(notification["content"], sort_keys=True)
                            content_hash = hashlib.md5(content_to_hash.encode('utf-8')).hexdigest()
                            notification_id = f"music_notification_{content_hash}"

                            # 跳过已处理的通知
                            if notification_id in self.processed_notification_ids:
                                util.log(1, f"[中转站] 跳过已处理通知ID: {notification_id}")
                                continue

                            notifications_to_process.append((notification, notification_id))

                        if not notifications_to_process:
                            util.log(1, f"[中转站] 所有通知已处理，队列中无新通知")
                            # 清空队列避免重复检查
                            self.tool_notification_states = []

                # 如果没有需要处理的通知，继续等待
                if not notifications_to_process:
                    time.sleep(2)
                    continue

                # 🔥 修复：确保每次调用前检查一遍SmartSisi核心状态，优先使用桥接模块
                sisi_core_id_local = id(self.sisi_core) if self.sisi_core else None
                sisi_core_id_bridge = None
                try:
                    from llm.sisi_core_bridge import SisiCoreBridge
                    if SisiCoreBridge._sisi_core_instance:
                        sisi_core_id_bridge = id(SisiCoreBridge._sisi_core_instance)
                except:
                    pass
                
                util.log(1, f"[中转站] 通知处理线程SmartSisi核心状态 - 本地ID: {sisi_core_id_local}, 桥接ID: {sisi_core_id_bridge}")

                # 🔥 新增：在处理订阅站通知前，检查LG系统和TTS状态
                should_wait = self._should_wait_for_lg_completion()
                if should_wait:
                    util.log(1, f"[中转站] 检测到LG系统或TTS正在运行，延迟处理订阅站通知")
                    time.sleep(2)  # 等待2秒后重新检查
                    continue

                # 延迟导入，避免循环依赖
                from llm.nlp_rasa import process_tool_notifications_with_transit

                # 调用处理函数处理收集的通知
                util.log(1, f"[中转站] LG系统和TTS已完成，开始处理{len(notifications_to_process)}条订阅站通知")

                # 将通知列表传递给处理函数
                result = process_tool_notifications_with_transit(self, [n[0] for n in notifications_to_process])

                # 标记已处理的通知
                with self.notification_lock:
                    for _, notification_id in notifications_to_process:
                        self.processed_notification_ids.add(notification_id)

                    # 清理队列 - 移除已处理的通知
                    self.tool_notification_states = [
                        n for n in self.tool_notification_states
                        if n["content"] not in [notification[0]["content"] for notification in notifications_to_process]
                    ]

                    # 定期清理已处理ID集合，避免无限增长
                    if len(self.processed_notification_ids) > 1000:
                        # 只保留最近500个
                        self.processed_notification_ids = set(list(self.processed_notification_ids)[-500:])

                # 🔥 精确修复：增强处理结果日志
                status = "✅ 成功" if result else "❌ 失败"
                util.log(1, f"[中转站] {status} 处理{len(notifications_to_process)}条通知，队列中剩余{len(self.tool_notification_states)}条")

                if result:
                    util.log(1, f"[中转站] 🎉 订阅站补充信息已成功发送到优化站处理")

                # 重置计数器
                no_sisi_core_count = 0

            except Exception as e:
                util.log(2, f"[中转站] 处理待处理通知失败: {str(e)}")
                import traceback
                util.log(2, f"[中转站] 详细错误: {traceback.format_exc()}")

            # 休眠一段时间再检查
            time.sleep(2)

        util.log(1, f"[中转站] 通知处理线程已停止 (会话ID: {self.session_id})")

    def _should_wait_for_lg_completion(self):
        """检查是否应该等待LG系统完成"""
        try:
            from core import sisi_booter

            # 检查LG系统是否还在运行
            lg_system_running = False
            if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'chatting'):
                lg_system_running = sisi_booter.sisi_core.chatting

            # 检查TTS是否还在播放
            tts_playing = False
            has_high_priority_audio = False

            if hasattr(sisi_booter, 'sisi_core'):
                # 检查是否正在播放音频
                if hasattr(sisi_booter.sisi_core, 'speaking'):
                    tts_playing = sisi_booter.sisi_core.speaking

                # 检查音频队列是否还有高优先级内容（LG系统final结果）
                if hasattr(sisi_booter.sisi_core, 'sound_query') and not sisi_booter.sisi_core.sound_query.empty():
                    queue = sisi_booter.sisi_core.sound_query
                    temp_items = []

                    # 临时取出所有音频检查优先级
                    while not queue.empty():
                        item = queue.get()
                        temp_items.append(item)
                        if item[0] >= 3:  # 优先级3或更高（final阶段）
                            has_high_priority_audio = True

                    # 恢复队列
                    for item in temp_items:
                        queue.put(item)

                    # 如果有任何音频在队列中，认为TTS还在处理
                    if temp_items:
                        tts_playing = True

            # 如果LG系统运行中或TTS播放中或有高优先级音频，则需要等待
            should_wait = lg_system_running or tts_playing or has_high_priority_audio

            if should_wait:
                util.log(1, f"[中转站] 等待LG系统完成: LG运行({lg_system_running}), TTS播放({tts_playing}), 高优先级音频({has_high_priority_audio})")

            return should_wait

        except Exception as e:
            util.log(2, f"[中转站] 检测LG系统状态异常: {str(e)}")
            return False  # 异常时不等待，避免阻塞



    def _detect_complex_tool(self):
        """检测是否为复杂工具 - 动态检测而非硬编码"""
        try:
            # 🔥 修复：动态检测复杂工具特征
            # 1. 检查最近状态中是否有复杂工具的特征
            recent_states = self.intermediate_states[-10:] if len(self.intermediate_states) > 10 else self.intermediate_states
            
            # 复杂工具特征：
            # - 继承StandardA2ATool的工具（zudao, bai_lian_tool）
            # - 有订阅机制的工具（music_tool, bai_lian_tool）
            # - 有异步处理的大型工具（esp32_tool）
            # - A2A协议工具
            
            complex_indicators = [
                # A2A协议相关
                "a2a", "StandardA2ATool", "async def", "subscribe", "notification",
                
                # 大型工具特征
                "music", "zudao", "bai_lian", "bailian", "esp32",
                
                # 复杂状态管理特征  
                "task_manager", "subscription", "workflow", "langgraph",
                
                # 工具特定标识
                "agent", "thinking", "processing", "工具完成"
            ]
            
            for state in recent_states:
                if isinstance(state, dict):
                    # 检查source字段
                    source_str = str(state.get("source", "")).lower()
                    
                    # 检查content字段
                    content_str = str(state.get("content", "")).lower()
                    
                    # 组合检查字符串
                    check_string = f"{source_str} {content_str}"
                    
                    for indicator in complex_indicators:
                        if indicator in check_string:
                            util.log(1, f"[中转站] 检测到复杂工具特征: '{indicator}' in '{check_string[:100]}...'")
                            return True
            
            # 2. 特殊检查：如果有Agent相关状态，通常是复杂工具
            for state in recent_states:
                if isinstance(state, dict):
                    source = str(state.get("source", "")).lower()
                    if "agent" in source or "thinking" in source:
                        util.log(1, f"[中转站] 检测到Agent状态，认为是复杂工具")
                        return True
                        
            util.log(1, f"[中转站] 未检测到复杂工具特征，认为是简单工具")
            return False
            
        except Exception as e:
            util.log(2, f"[中转站] 检测复杂工具异常: {str(e)}")
            # 出错时默认为简单工具
            return False

    def _process_immediate_state(self, state, phase):
        """实时处理状态"""
        # 尝试使用SmartSisi核心桥接
        try:
            from llm.sisi_core_bridge import get_bridge
            bridge = get_bridge()

            # 检查SmartSisi核心是否活跃
            if bridge.is_core_active():
                # 提取状态文本
                from llm.nlp_rasa import extract_text_from_state, call_optimize_api
                state_text = extract_text_from_state(state)

                # 只过滤真正的空字符串或 1 个字符的噪声，允许 2 字以上短句通过
                if not state_text or len(state_text.strip()) < 2:
                    util.log(2, f"[中转站] 状态文本过短或为空，跳过处理")
                    return False

                # 构建优化提示
                if phase == "start":
                    prompt = "优化这段思考过程，使其适合对用户展示："
                elif phase == "middle":
                    # 🎯 音乐工具专属通道：检测Agent的WORKING状态，使用等待专属提示词
                    source_str = str(state.get("source", "")).lower()
                    is_music_working = (
                        ("音乐" in state_text or "music" in source_str or "为您准备" in state_text) and
                        self._is_agent_working_state(state_text, source_str)
                    )
                    
                    util.log(1, f"[中转站] 🔍 Middle阶段检测: state_text='{state_text[:50]}...', source='{source_str}', is_music_working={is_music_working}")
                    
                    if is_music_working:
                        # 音乐工具等待专属通道：获取前面的优化内容并使用等待专属提示词
                        util.log(1, f"[中转站] 🎵 检测到音乐WORKING状态，使用等待专属提示词")
                        
                        # 获取前面的优化内容
                        optimized_contents = {}
                        start_content = None
                        
                        # 从历史状态中查找start内容
                        for hist_state in self.intermediate_states[-10:]:  # 检查最近10条状态
                            hist_source = str(hist_state.get("source", ""))
                            if "思考节点" in hist_source and not start_content:
                                start_content = extract_text_from_state(hist_state)
                                break
                        
                        optimized_contents["start"] = start_content or "思考中..."
                        optimized_contents["middle"] = ""  # middle阶段还没有内容
                        
                        # 使用音乐工具等待专属提示词
                        from llm.nlp_rasa import _get_tool_specific_prompt
                        prompt = _get_tool_specific_prompt("music_waiting", state_text, optimized_contents, None)
                    else:
                        prompt = "优化这段工具结果，提取关键信息给用户："
                else:  # final
                    # 🔥 修复：检查是否涉及音乐工具调用，使用特殊的优化提示
                    if "music" in state_text.lower() and any(keyword in state_text for keyword in ["播放", "音乐", "歌曲"]):
                        prompt = """优化这段关于音乐工具调用的回答，必须严格遵守以下规则：
1. 如果原文提到"已经播放"或"正在播放"音乐，改为"正在准备"或"正在生成"
2. 绝对不要编造具体的歌曲名称、歌手名称或音乐内容
3. 保持等待和期待的语气，不要假装任务已完成
4. 可以说"请稍等片刻"、"马上就好"等等待性表述
优化以下内容："""
                    else:
                        prompt = "优化这段最终回答，确保与之前的对话连贯且保留关键信息："

                # 调用优化API
                util.log(1, f"[中转站] 开始实时优化{phase}阶段内容: {state_text[:50]}...")

                # 确保配置已加载
                from utils import config_util
                config_util.load_config()

                # 获取正确的优化模型名称
                optimize_model = config_util.llm_optimize_model or "gpt-3.5-turbo"

                # 根据内容长度和阶段判断是否需要优化
                # 如果是final阶段，并且内容中包含<answer>标签，处理更加谨慎
                should_optimize = True
                optimized = ""

                # 检查是否包含<answer>标签的最终答案
                if phase == "final" and "<answer>" in state_text:
                    import re
                    answer_match = re.search(r'<answer>(.*?)</answer>', state_text, re.DOTALL)
                    if answer_match:
                        answer_content = answer_match.group(1).strip()
                        # 如果是有结构化答案的内容，对提取出的内容进行优化
                        if answer_content:
                            util.log(1, f"[中转站] 最终阶段检测到<answer>标签，提取内容优化")
                            # 优化提取的内容
                            try:
                                optimized = call_optimize_api(
                                    f"优化这段最终答案，保留所有关键信息尤其是地址、数字等事实：",
                                    answer_content,
                                    optimize_model,
                                    username="User",
                                    phase=phase
                                )
                                # 检查优化是否成功，失败则回退
                                if not optimized or optimized == answer_content:
                                    optimized = answer_content
                                    util.log(1, f"[中转站] 优化API未改变内容或返回为空，使用原始内容")
                            except Exception as e:
                                optimized = answer_content
                                util.log(2, f"[中转站] 优化API调用异常，使用原始内容: {str(e)}")

                            # 将优化后的内容放回answer标签
                            state_text = state_text.replace(f"<answer>{answer_content}</answer>", f"<answer>{optimized}</answer>")
                            should_optimize = False  # 已经优化过了，不需要整体优化

                # 如果上面的特殊处理没有执行，则执行常规优化
                if should_optimize:
                    try:
                        # 🔥 修复：传递None让call_optimize_api使用内部完整角色定义
                        optimized = call_optimize_api(None, state_text, optimize_model, username="User", phase=phase)
                    except Exception as e:
                        util.log(2, f"[中转站] 优化API调用异常: {str(e)}")
                        optimized = state_text  # 出错时使用原始内容

                # 检查优化是否成功
                if not optimized:
                    util.log(2, f"[中转站] {phase}阶段优化API返回为空，使用原文")
                    optimized = state_text
                elif optimized == state_text:
                    util.log(1, f"[中转站] {phase}阶段优化API返回原文，可能未成功调用")
                else:
                    # 最终阶段结果强制检查 - 确保核心信息没有丢失
                    if phase == "final":
                        # 记录优化日志
                        util.log(1, f"[中转站] {phase}阶段优化成功: {optimized[:50]}...")
                    else:
                        util.log(1, f"[中转站] {phase}阶段优化成功: {optimized[:50]}...")

                # 🔧 新增：保存优化后的内容供UI获取
                self.optimized_contents[phase] = optimized
                util.log(1, f"[中转站] 已保存{phase}阶段优化内容供UI获取")

                # 发送到SmartSisi核心桥接
                metadata = {"phase": phase}
                is_intermediate = phase != "final"
                
                bridge.send_notification(
                    optimized,
                    "transit_station",
                    is_intermediate=is_intermediate,
                    metadata=metadata
                )

                # 标记该阶段已处理
                self.stage_sent[phase] = True

                util.log(1, f"[中转站] 已通过SmartSisi核心桥接处理并发送{phase}阶段内容")
                return True
        except Exception as e:
            util.log(2, f"[中转站] 使用SmartSisi核心桥接处理状态异常: {str(e)}")
            # 失败时回退到原有逻辑

        # 回退到原有逻辑
        if not self.sisi_core:
            util.log(1, f"[中转站-{phase}] 未注册SmartSisi核心，直接保存阶段文本供UI读取")
            try:
                from llm.nlp_rasa import extract_text_from_state, extract_answer_tag
                state_text = extract_text_from_state(state)
                util.log(1, f"[中转站-{phase}] extract_text_from_state返回: '{state_text[:100] if state_text else None}'")
                
                # 🔧 独立UI模式：模拟优化站的标签清理逻辑
                # final阶段需要提取<answer>标签内容，如果为空则用middle兜底
                if phase == 'final' and state_text:
                    cleaned_text = extract_answer_tag(state_text)
                    util.log(1, f"[中转站-{phase}] extract_answer_tag清理后: '{cleaned_text[:100] if cleaned_text else '(空)'}'")
                    
                    # 如果<answer>为空，尝试用middle内容兜底
                    if not cleaned_text or len(cleaned_text.strip()) == 0:
                        util.log(2, f"[中转站-{phase}] ⚠️ final内容为空，尝试用middle兜底")
                        middle_text = self.optimized_contents.get('middle', '')
                        if middle_text and len(middle_text.strip()) > 0:
                            cleaned_text = middle_text
                            util.log(1, f"[中转站-{phase}] ✅ 使用middle兜底: '{cleaned_text[:50]}'")
                        else:
                            cleaned_text = "抱歉，我无法生成回复。"
                    
                    state_text = cleaned_text
                
            except Exception as e:
                state_text = str(state.get("content", ""))
                util.log(1, f"[中转站-{phase}] extract失败，使用原始content: '{state_text}', 错误: {e}")

            # 记录到快照与optimized_contents，保证UI可读到三个阶段
            if state_text and len(str(state_text).strip()) > 0:
                self.optimized_contents[phase] = state_text
                self.lg_snapshot[phase] = state_text
                self.stage_sent[phase] = True
                util.log(1, f"[中转站-{phase}] ✅ 已保存! optimized_contents[{phase}]='{state_text[:100]}'")
            else:
                util.log(2, f"[中转站-{phase}] ❌ state_text为空，未保存！原始state: {state}")

            # 仍保留原有队列收集
            self.intermediate_states.append(state)
            return True

        try:
            # 提取状态文本
            from llm.nlp_rasa import extract_text_from_state, call_optimize_api
            state_text = extract_text_from_state(state)

            # 只过滤真正的空字符串或 1 个字符的噪声，允许 2 字以上短句通过
            if not state_text or len(state_text.strip()) < 2:
                util.log(2, f"[中转站] 状态文本过短或为空，跳过处理")
                return False

            # 检查是否有音频正在播放，如果有则等待完成
            if hasattr(self.sisi_core, 'speaking') and self.sisi_core.speaking:
                util.log(1, f"[中转站] 检测到NLP音频正在播放，等待完成后再处理{phase}阶段内容...")
                # 等待当前播放完成
                wait_count = 0
                while self.sisi_core.speaking and wait_count < 300:  # 最多等待30秒
                    time.sleep(0.1)
                    wait_count += 1

                if wait_count >= 300:
                    util.log(2, f"[中转站] 等待NLP音频播放完成超时，强制继续")
                else:
                    util.log(1, f"[中转站] NLP音频播放已完成，继续处理{phase}阶段内容")

            # 构建优化提示
            if phase == "start":
                prompt = "优化这段思考过程，使其适合对用户展示："
            elif phase == "middle":
                prompt = "优化这段工具结果，提取关键信息给用户："
            else:  # final
                # 🔥 修复：检查是否涉及音乐工具调用，使用特殊的优化提示
                if "music" in state_text.lower() and any(keyword in state_text for keyword in ["播放", "音乐", "歌曲"]):
                    prompt = """优化这段关于音乐工具调用的回答，必须严格遵守以下规则：
1. 如果原文提到"已经播放"或"正在播放"音乐，改为"正在准备"或"正在生成"
2. 绝对不要编造具体的歌曲名称、歌手名称或音乐内容
3. 保持等待和期待的语气，不要假装任务已完成
4. 可以说"请稍等片刻"、"马上就好"等等待性表述
优化以下内容："""
                else:
                    prompt = "优化这段最终回答，确保与之前的对话连贯且保留关键信息："

            # 调用优化API
            util.log(1, f"[中转站] 开始实时优化{phase}阶段内容: {state_text[:50]}...")

            # 确保配置已加载
            from utils import config_util
            config_util.load_config()

            # 获取正确的优化模型名称
            optimize_model = config_util.llm_optimize_model or "gpt-3.5-turbo"

            # 根据内容长度和阶段判断是否需要优化
            # 如果是final阶段，并且内容中包含<answer>标签，处理更加谨慎
            should_optimize = True
            optimized = ""

            # 检查是否包含<answer>标签的最终答案
            if phase == "final" and "<answer>" in state_text:
                import re
                answer_match = re.search(r'<answer>(.*?)</answer>', state_text, re.DOTALL)
                if answer_match:
                    answer_content = answer_match.group(1).strip()
                    # 如果是有结构化答案的内容，对提取出的内容进行优化
                    if answer_content:
                        util.log(1, f"[中转站] 最终阶段检测到<answer>标签，提取内容优化")
                        # 优化提取的内容
                        try:
                            optimized = call_optimize_api(
                                f"优化这段最终答案，保留所有关键信息尤其是地址、数字等事实：",
                                answer_content,
                                optimize_model,
                                username="User",
                                phase=phase
                            )
                            # 检查优化是否成功，失败则回退
                            if not optimized or optimized == answer_content:
                                optimized = answer_content
                                util.log(1, f"[中转站] 优化API未改变内容或返回为空，使用原始内容")
                        except Exception as e:
                            optimized = answer_content
                            util.log(2, f"[中转站] 优化API调用异常，使用原始内容: {str(e)}")

                        # 将优化后的内容放回answer标签
                        state_text = state_text.replace(f"<answer>{answer_content}</answer>", f"<answer>{optimized}</answer>")
                        should_optimize = False  # 已经优化过了，不需要整体优化

            # 如果上面的特殊处理没有执行，则执行常规优化
            if should_optimize:
                try:
                    # 🔥 修复：传递None让call_optimize_api使用内部完整角色定义
                    optimized = call_optimize_api(None, state_text, optimize_model, username="User", phase=phase)
                except Exception as e:
                    util.log(2, f"[中转站] 优化API调用异常: {str(e)}")
                    optimized = state_text  # 出错时使用原始内容

            # 检查优化是否成功
            if not optimized:
                util.log(2, f"[中转站] {phase}阶段优化API返回为空，使用原文")
                optimized = state_text
            elif optimized == state_text:
                util.log(1, f"[中转站] {phase}阶段优化API返回原文，可能未成功调用")
            else:
                # 最终阶段结果强制检查 - 确保核心信息没有丢失
                if phase == "final":
                    # 记录优化日志
                    util.log(1, f"[中转站] {phase}阶段优化成功: {optimized[:50]}...")
                else:
                    util.log(1, f"[中转站] {phase}阶段优化成功: {optimized[:50]}...")

            # 发送到SmartSisi核心桥接
            metadata = {"phase": phase}
            is_intermediate = phase != "final"
            
            bridge.send_notification(
                optimized,
                "transit_station",
                is_intermediate=is_intermediate,
                metadata=metadata
            )

            # 标记该阶段已处理
            self.stage_sent[phase] = True

            util.log(1, f"[中转站] 已实时处理并发送{phase}阶段内容到SmartSisi核心")
            return True

        except Exception as e:
            util.log(2, f"[中转站] 实时处理状态异常: {str(e)}")
            import traceback
            util.log(2, f"[中转站] 详细错误: {traceback.format_exc()}")
            return False

    def _process_notification(self, state):
        """处理来自工具的主动通知"""
        if not isinstance(state, dict):
            return state

        # 检查是否为工具主动通知
        if state.get("is_tool_notification", False):
            content_type = state.get("content_type", "text")

            # 根据内容类型处理
            if content_type == "audio":
                self._handle_audio_content(state)
            elif content_type == "image":
                self._handle_image_content(state)
            elif content_type == "event":
                self._handle_event_content(state)

        # 检查事件类型
        util.log(1, f"[中转站调试] 事件状态结构: content_type={state.get('content_type')}, keys={list(state.keys())}")

        return state

    def _handle_audio_content(self, state):
        """处理音频内容"""
        try:
            audio_path = state.get("content")
            if os.path.exists(audio_path):
                # 获取TTS输出目录
                tts_dir = os.path.join(os.getcwd(), "resources", "tts")
                os.makedirs(tts_dir, exist_ok=True)

                # 复制到TTS目录
                filename = os.path.basename(audio_path)
                target_path = os.path.join(tts_dir, filename)

                import shutil
                shutil.copy(audio_path, target_path)

                # 如果有SmartSisi核心，尝试播放
                if hasattr(self, 'sisi_core') and self.sisi_core:
                    # 先播放旁白（如果有）
                    narration = state.get("metadata", {}).get("narration", "")
                    if narration:
                        self.sisi_core.agent_callback(
                            narration,
                            "normal",
                            is_intermediate=True,
                            metadata={"phase": "audio_narration"}
                        )

                    # 通过SmartSisi核心播放音频
                    try:
                        # 调用播放方法（根据您的具体实现可能需要调整）
                        self.sisi_core.play_audio(target_path)
                    except:
                        # 如果没有播放方法，使用系统命令
                        import os
                        if os.name == 'nt':  # Windows
                            os.system(f'start {target_path}')
                        else:  # Linux/Mac
                            os.system(f'open {target_path}')
                else:
                    # 直接使用系统命令播放
                    import os
                    if os.name == 'nt':  # Windows
                        os.system(f'start {target_path}')
                    else:  # Linux/Mac
                        os.system(f'open {target_path}')

                logger.info(f"已处理音频通知: {filename}")

        except Exception as e:
            logger.error(f"处理音频内容时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _handle_image_content(self, state):
        """处理图片内容"""
        try:
            image_path = state.get("content")
            if os.path.exists(image_path):
                # 获取图片输出目录
                image_dir = os.path.join(os.getcwd(), "resources", "images")
                os.makedirs(image_dir, exist_ok=True)

                # 复制到图片目录
                filename = os.path.basename(image_path)
                target_path = os.path.join(image_dir, filename)

                import shutil
                shutil.copy(image_path, target_path)

                # 如果有SmartSisi核心，尝试显示图片
                if hasattr(self, 'sisi_core') and self.sisi_core:
                    # 先显示描述（如果有）
                    description = state.get("metadata", {}).get("description", "")
                    if description:
                        self.sisi_core.agent_callback(
                            description,
                            "normal",
                            is_intermediate=True,
                            metadata={"phase": "image_description"}
                        )

                    # 通过SmartSisi核心显示图片
                    try:
                        # 调用显示方法（根据您的具体实现可能需要调整）
                        self.sisi_core.show_image(target_path)
                    except:
                        # 如果没有显示方法，使用系统命令
                        import os
                        if os.name == 'nt':  # Windows
                            os.system(f'start {target_path}')
                        else:  # Linux/Mac
                            os.system(f'open {target_path}')

                logger.info(f"已处理图片通知: {filename}")

        except Exception as e:
            logger.error(f"处理图片内容时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _handle_event_content(self, state):
        """处理事件内容 - 仅记录不处理，事件应由a2a_notification直接处理"""
        try:
            event_data = state.get("content")
            event_type = None

            # 提取事件类型
            if isinstance(event_data, dict) and "type" in event_data:
                event_type = event_data["type"]

            # 只记录事件，不执行任何处理
            source_tool = state.get("source_tool", "unknown")
            util.log(1, f"[中转站] 已记录事件通知: {event_type or '未知类型'} 来自 {source_tool}")
            util.log(1, f"[中转站] 事件应由a2a_notification模块直接处理，此处仅作记录")

        except Exception as e:
            util.log(2, f"[中转站] 记录事件内容时出错: {str(e)}")
            import traceback
            util.log(2, f"[中转站] 详细错误: {traceback.format_exc()}")

    def add_intermediate_state(self, content, source=None, affect_flow=True, is_notification=False, process_immediately=False):
        """
        添加中间状态到列表 - 同时实时处理关键状态

        Args:
            content: 可以是文本字符串或包含content字段的状态字典
            source: 状态来源标识
            affect_flow: 不再使用但保留参数
            is_notification: 区分普通状态和主动通知
            process_immediately: 是否立即处理通知，不等待监控线程

        Returns:
            bool: 成功添加返回True
        """
        try:
            # 兼容旧工具调用，确保状态标记正确
            if source in ["weather", "timer", "location"] and not isinstance(content, dict):
                # 旧工具需要特殊处理，添加缺失标记
                content = {
                    "content": content,
                    "source_tool": source,
                    "is_tool_notification": False,  # 明确标记非主动通知
                    "for_optimization": True
                }

            # 处理输入content可能是字符串或字典的情况
            if isinstance(content, str):
                content_text = content
                # 构造状态字典
                state = {
                    "content": content,
                    "source": source or "unknown",
                    "timestamp": int(time.time() * 1000),
                    "is_final": False
                }
            elif isinstance(content, dict) and "content" in content:
                content_text = content["content"]
                state = content
                # 确保有来源和时间戳字段
                if "source" not in state:
                    state["source"] = source or "unknown"
                if "timestamp" not in state:
                    state["timestamp"] = int(time.time() * 1000)
            else:
                content_text = str(content)
                state = {
                    "content": content_text,
                    "source": source or "unknown",
                    "timestamp": int(time.time() * 1000),
                    "is_final": False
                }

            # 检查是否为工具主动通知
            if isinstance(state, dict) and state.get("is_tool_notification", False):
                # 工具主动通知处理时使用线程锁保护
                with self.notification_lock:
                    # 如果 content_text 是字典，则序列化为 JSON 字符串以进行哈希
                    if isinstance(content_text, dict):
                        content_to_hash = json.dumps(content_text, sort_keys=True)
                    else:
                        content_to_hash = str(content_text) #确保是字符串

                    # 计算内容哈希作为唯一标识
                    content_hash = hashlib.md5(content_to_hash.encode('utf-8')).hexdigest()
                    notification_id = f"music_notification_{content_hash}"

                    # 检查是否已经处理过
                    if notification_id in self.processed_notification_ids:
                        util.log(1, f"[中转站] 忽略重复通知: {source}")
                        return True

                    # 工具主动通知存入单独队列
                    self.tool_notification_states.append(state)
                    util.log(1, f"[中转站] 添加工具主动通知: {source} - {content_text[:50]}... [通知队列长度:{len(self.tool_notification_states)}]")

                    # 添加详细日志，特别对店铺评价通知
                    if source == "bailian_tool" and state.get("metadata", {}).get("store_names"):
                        store_names = state.get("metadata", {}).get("store_names", [])
                        store_count = state.get("metadata", {}).get("store_count", 0)
                        util.log(1, f"[中转站] 接收到店铺评价汇总通知: {', '.join(store_names[:3])}等{store_count}家店铺, 通知长度:{len(str(content_text))}")

                    # 限制队列长度，避免内存泄漏
                    if len(self.tool_notification_states) > 20:
                        self.tool_notification_states.pop(0)  # 移除最旧的通知

                    # 如果要求立即处理，创建一个临时线程处理当前通知
                    # 避免直接调用_process_pending_notifications造成递归或者线程冲突
                    if process_immediately:
                        util.log(1, f"[中转站] 请求立即处理通知: {source}")

                        # 不再直接调用处理方法，而是设置标记让处理线程提前工作
                        # 确保即使通知被标记为立即处理，也只会由通知处理线程处理一次
                        # 这里不做任何实际处理，只是让通知线程更快地被唤醒
                        pass

                    return True

            # 普通状态正常处理
            self.intermediate_states.append(state)

            # 记录状态添加
            content_text_for_log = ""
            if isinstance(content_text, dict):
                # 优先使用 content 字典中的 'message' 或 'narration_text' 或 'text' 作为主要日志内容
                content_text_for_log = content_text.get('message', content_text.get('narration_text', content_text.get('text', ''))) 
                if not content_text_for_log: # 如果这些都没有，就用整个字典的json字符串
                    try:
                        content_text_for_log = json.dumps(content_text, ensure_ascii=False, default=str)
                    except TypeError:
                        content_text_for_log = str(content_text)
            elif isinstance(content_text, str):
                content_text_for_log = content_text
            else:
                content_text_for_log = str(content_text)
            
            log_message = f"[中转站] 添加状态: {source or '未指定来源'} - {content_text_for_log[:100]}"
            if len(content_text_for_log) > 100:
                log_message += "..."
            util.log(1, log_message)

            # 实时处理关键状态
            source_str = str(source or state.get("source", "")).lower()
            is_final = state.get("is_final", False)

            # 计算该内容的哈希值
            # 如果 content_text 是字典，则序列化为 JSON 字符串以进行哈希
            if isinstance(content_text, dict):
                hashable_content = json.dumps(content_text, sort_keys=True)
            else:
                hashable_content = str(content_text) #确保是字符串
            content_hash = hashlib.md5(hashable_content.encode()).hexdigest()

            # 识别开始阶段 - 🔥 修复：添加对music工具的开始阶段识别
            if (("思考节点" in source_str or "agent" in source_str or "thinking" in source_str) 
                or (source_str.startswith("tool:") and source_str != "tool:final")) and not self.stage_sent["start"]:
                # 🔥 修复：tool:music等工具状态也应该触发开始阶段
                util.log(1, f"[中转站] 检测到开始阶段状态，准备实时处理")
                self._process_immediate_state(state, "start")
                self.processed_hashes["start"].add(content_hash)
                self.stage_sent["start"] = True  # 🔥 修复：确保设置已发送标记

            # 🔥 只在工具结果阶段检测失败，不在LG系统的思考完成或final阶段重复检测
            elif source_str.startswith("tool:") and self._is_tool_failed_state(content_text, source_str, state):
                # 提取工具名称
                tool_name = source_str.split(":")[1] if len(source_str.split(":")) > 1 else "unknown"

                util.log(1, f"[中转站] 🚨 检测到工具失败状态，记录但不立即处理: {tool_name}")
                # 不立即触发error阶段，让LG系统自然处理失败并在final阶段统一输出

            # 🎯 检测Agent的WORKING状态，正常优化为middle阶段
            elif self._is_agent_working_state(content_text, source_str) and not self.stage_sent["middle"]:
                util.log(1, f"[中转站] 🎵 检测到Agent WORKING状态，正常优化为middle阶段")
                self._process_immediate_state(state, "middle")
                self.processed_hashes["middle"].add(content_hash)
                self.stage_sent["middle"] = True

            # 识别中间阶段 - 只有复杂工具才处理中间状态，但排除music工具的COMPLETED状态
            elif (("工具完成" in source_str or "tool" in source_str) and self._detect_complex_tool() and not self._is_music_completed_state(content_text)) and not self.stage_sent["middle"]:
                # 🔥 修复：改善中间阶段检测逻辑
                util.log(1, f"[中转站] 检测到中间阶段状态，准备实时处理")
                self._process_immediate_state(state, "middle")
                self.processed_hashes["middle"].add(content_hash)
                self.stage_sent["middle"] = True  # 🔥 修复：确保设置已发送标记

            # 识别最终阶段 - 🔥 修复：允许Agent最终回答正常进入final阶段
            elif (is_final or "final" in source_str):
                # 检查当前内容是否真的需要跳过 - 只有在完全相同的内容且已经播放过才跳过
                already_processed = content_hash in self.processed_hashes["final"]
                
                # 🔥 修复：即使内容相同，如果是新的工具调用流程，也应该播放最终阶段
                if already_processed and self.stage_sent["final"]:
                    util.log(1, f"[中转站] 该最终阶段内容已处理过，跳过: {content_text[:30]}...")
                    return True
                
                # 🔥 修复：增加详细日志，帮助调试
                if already_processed:
                    util.log(1, f"[中转站] 内容已处理但stage_sent[final]={self.stage_sent['final']}，重新播放最终阶段")

                util.log(1, f"[中转站] 检测到最终阶段状态，准备实时处理")
                self._process_immediate_state(state, "final")
                # 🔥 修复：最终状态处理后重置所有阶段标记，确保下一次工具调用可以正常处理所有阶段
                util.log(1, f"[中转站] 最终状态已实时处理，不触发额外处理")
                
                # 重置所有阶段标记，确保下一次工具调用可以正常处理所有阶段
                self.stage_sent = {
                    "start": False,
                    "middle": False,
                    "final": False,
                    "error": False  # 🔥 新增：重置错误阶段标记
                }
                # 🔥 修复：同时清空已处理哈希，确保下次工具调用可以播放相同内容
                for phase in self.processed_hashes:
                    self.processed_hashes[phase].clear()

                # 🔥 修复：清空intermediate_states列表，避免系统一直显示"中转站处理中"
                # 保留 lg_snapshot 与 optimized_contents，让UI在无SisiCore时也能读取到最终文本
                self.intermediate_states.clear()

                util.log(1, f"[中转站] 重置阶段标记和哈希缓存，清空状态列表，为下一次工具调用做准备")

            # 添加通知处理
            if isinstance(state, dict) and state.get("is_tool_notification", False):
                self._process_notification(state)

            # 检查是否为事件通知
            if state.get("content_type") == "event":
                event_type = "unknown"
                if isinstance(state.get("content"), dict) and "type" in state.get("content"):
                    event_type = state.get("content").get("type")
                util.log(1, f"[中转站] 收到事件状态: {state.get('source_tool')} - {event_type}")
                util.log(1, f"[中转站] 事件应由a2a_notification模块直接处理，此处跳过处理")
                # 不添加到中间状态列表，避免事件被重复处理
                return True

            return True
        except Exception as e:
            util.log(2, f"[中转站] 添加状态异常: {str(e)}")
            import traceback
            util.log(2, f"[中转站] 详细错误: {traceback.format_exc()}")
            return False

    def clear_intermediate_states(self):
        """清空中间状态列表，但保留工具主动通知"""
        count = len(self.intermediate_states)
        self.intermediate_states = []

        # 重置阶段发送状态
        self.stage_sent = {
            "start": False,
            "middle": False,
            "final": False,
            "error": False  # 🔥 新增：重置错误阶段标记
        }

        # 清空所有阶段的已处理内容哈希集合
        for phase in self.processed_hashes:
            self.processed_hashes[phase].clear()

        # 🔧 新增：清空优化内容缓存
        self.optimized_contents = {
            "start": None,
            "middle": None,
            "final": None
        }

        util.log(1, f"[中转站] 已清空中间状态列表 (共{count}条)，保留{len(self.tool_notification_states)}条工具通知")
        return True

    def process_final_result(self, text, interact=None, username="User", play_intermediate=False):
        """
        处理最终结果 - 仅存储不触发动作

        Args:
            text: 最终结果文本
            interact: 交互对象
            username: 用户名
            play_intermediate: 不再使用

        Returns:
            tuple: 返回(原文本, False)
        """
        try:
            # 添加最终结果到中间状态列表
            final_state = {
                "content": text,
                "source": "final_result",
                "timestamp": int(time.time() * 1000),
                "is_final": True,
                "username": username
            }

            # 添加到状态列表 - 仅收集不触发回调
            self.add_intermediate_state(final_state, "final_result", False)
            util.log(1, f"[中转站] 添加最终结果: {text[:50]}...")

            # 直接返回原始文本和未优化标志
            self.clear_intermediate_states()  # 确保调用结束后清理状态

            # 处理工具通知
            util.log(1, f"[中转站] 最终结果处理完成，开始处理工具通知队列")
            self.process_notifications_after_final()

            return (text, False)

        except Exception as e:
            util.log(2, f"[中转站] 处理结果异常: {str(e)}")
            # 返回原始文本和错误标志
            return (text, False)

    def process_a2a_response(self, response_text: str, interact=None, username="User") -> str:
        """
        处理A2A工具响应结果 - 仅存储不触发动作

        Args:
            response_text: A2A工具返回的文本
            interact: 交互对象
            username: 用户名

        Returns:
            str: 处理后的结果
        """
        try:
            util.log(1, f"[中转站] 接收A2A响应: {response_text[:50]}...")

            # 清理内容
            cleaned_content = response_text

            # 提取<answer>标签中的内容(如果有)
            answer_match = re.search(r'<answer>(.*?)</answer>', response_text, re.DOTALL)
            if answer_match:
                extracted_answer = answer_match.group(1).strip()
                # 检查提取的答案是否为空
                if extracted_answer:
                    cleaned_content = extracted_answer
                    util.log(1, f"[中转站] 从<answer>标签提取内容: {cleaned_content[:50]}...")
                else:
                    # 当<answer>标签为空时，尝试从原始响应中提取有用信息
                    util.log(2, f"[中转站] 警告: <answer>标签为空，尝试提取工具结果")

                    # 尝试提取工具结果
                    tool_match = re.search(r'<tool>.*?name:\s*(\w+).*?result:\s*(.*?)\s*<\/tool>', response_text, re.DOTALL)
                    if tool_match:
                        tool_name = tool_match.group(1)
                        tool_result = tool_match.group(2).strip()
                        cleaned_content = f"{tool_result}"
                        util.log(1, f"[中转站] 从工具结果提取内容: {cleaned_content[:50]}...")
                    else:
                        # 如果没有工具结果，从整个响应中去除标签
                        cleaned_content = re.sub(r'<.*?>|name:|input:|result:', '', response_text)
                        cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
                        util.log(1, f"[中转站] 去除所有标签后的内容: {cleaned_content[:50]}...")

            # 添加原始响应到中间状态
            self.add_intermediate_state({
                "content": response_text,
                "source": "a2a_response",
                "timestamp": int(time.time() * 1000),
                "is_final": False,
                "username": username
            })

            # 添加清理后的内容作为最终结果
            final_state = {
                "content": cleaned_content,
                "source": "a2a_final",
                "timestamp": int(time.time() * 1000),
                "is_final": True,
                "username": username
            }
            self.add_intermediate_state(final_state)

            # 直接返回清理后的结果
            return cleaned_content

        except Exception as e:
            util.log(2, f"[中转站] 处理A2A响应异常: {str(e)}")
            # 出错时返回原始文本
            return response_text

    def extract_tool_content(self, data: Dict[str, Any]) -> str:
        """从工具结果中提取内容"""
        try:
            if isinstance(data, dict):
                # 通用工具结果字段提取
                for field in ["result", "content", "message", "response"]:
                    if field in data:
                        return str(data[field])

                # 特殊格式数据处理简化为直接字符串化
                return json.dumps(data, ensure_ascii=False)

            return str(data)

        except Exception as e:
            util.log(2, f"[中转站] 提取工具内容异常: {str(e)}")
            return str(data)

    def get_intermediate_states(self):
        """获取所有中间状态"""
        return self.intermediate_states

    def get_states_by_stage(self, stage=None):
        """
        获取指定阶段的状态

        Args:
            stage: 阶段名称 (start, middle, final)，为None时返回所有

        Returns:
            list: 状态列表
        """
        if stage is None:
            return self.intermediate_states

        result = []
        for state in self.intermediate_states:
            # 检查来源或标记
            source = state.get("source", "").lower()
            is_final = state.get("is_final", False)

            # 根据阶段筛选
            if stage == "final" and is_final:
                result.append(state)
            elif stage == "start" and any(kw in source for kw in ["start", "思考", "thinking"]):
                result.append(state)
            elif stage == "middle" and any(kw in source for kw in ["middle", "工具", "tool"]):
                result.append(state)

        return result

    def add_tool_notification(self, notification):
        """添加工具主动通知到队列"""
        if not isinstance(notification, dict):
            util.log(2, f"[中转站] 工具通知必须是字典类型，收到: {type(notification)}")
            return False

        # 确保通知包含必要字段
        required_fields = ["source", "content"]
        for field in required_fields:
            if field not in notification:
                util.log(2, f"[中转站] 工具通知缺少必要字段: {field}")
                return False

        # 添加时间戳（如果没有）
        if "timestamp" not in notification:
            notification["timestamp"] = time.time()

        # 尝试使用SmartSisi核心桥接直接处理
        try:
            # 如果通知需要立即处理，则尝试通过桥接直接处理
            if notification.get("for_optimization", False):
                from llm.sisi_core_bridge import get_bridge
                bridge = get_bridge()

                # 检查SmartSisi核心是否活跃
                if bridge.is_core_active():
                    # 直接发送到SmartSisi核心
                    content = notification["content"]
                    source = notification["source"]
                    metadata = {"phase": "notification", "source": source}

                    # 发送通知
                    bridge.send_notification(
                        content,
                        source,
                        is_intermediate=False,
                        metadata=metadata
                    )

                    util.log(1, f"[中转站] 已通过SmartSisi核心桥接直接处理工具通知: 来源={source}")
                    return True
        except Exception as e:
            util.log(2, f"[中转站] 通过SmartSisi核心桥接处理工具通知异常: {str(e)}")
            # 失败时回退到队列处理

        # 添加到通知队列
        with self.notification_lock:
            self.tool_notification_states.append(notification)

        util.log(1, f"[中转站] 已添加工具通知到队列: 来源={notification['source']}, 内容长度={len(notification['content']) if isinstance(notification['content'], str) else '非文本'}")

        # 如果通知需要立即处理，则直接处理
        if notification.get("for_optimization", False):
            # 直接处理通知
            self._process_notification(notification)

        return True

    def process_notifications_after_final(self):
        """在最终结果处理后，处理工具通知"""
        try:
            from llm.nlp_rasa import process_tool_notifications_with_transit
            # 传递自身实例，确保优化站能访问通知队列
            return process_tool_notifications_with_transit(self)
        except Exception as e:
            util.log(2, f"[中转站] 处理工具通知异常: {str(e)}")
            return False

    def _is_tool_failed_state(self, content_text, source_str, state):
        """检查是否为工具失败状态 - 更精确的检测，避免误判"""
        try:
            # 检查状态标记
            if isinstance(state, dict) and state.get("tool_failed", False):
                util.log(1, f"[中转站] 检测到工具失败标记: {content_text[:50]}...")
                return True

            # 检查来源是否包含failed标识
            if ":failed" in source_str:
                util.log(1, f"[中转站] 检测到失败来源: {source_str}")
                return True

            # 🔥 更精确的失败关键词检测 - 避免误判正常文本中的"错误"等词
            content_lower = str(content_text).lower()

            # 明确的工具失败模式
            explicit_failure_patterns = [
                "工具执行失败", "任务执行失败", "api调用失败", "请求失败",
                "连接失败", "超时失败", "quota_not_enough", "500 internal server error",
                "处理超时或未返回结果", "工具调用异常", "服务查询失败"
            ]

            # 检查明确的失败模式
            for pattern in explicit_failure_patterns:
                if pattern in content_lower:
                    util.log(1, f"[中转站] 检测到明确失败模式: '{pattern}' in {content_text[:50]}...")
                    return True

            # 检查结构化错误信息 (如: {'error': '...', 'query': '...'})
            if isinstance(state, dict):
                content = state.get("content", {})
                if isinstance(content, dict) and "error" in content:
                    error_msg = str(content.get("error", ""))
                    if error_msg and len(error_msg) > 5:  # 避免空错误信息
                        util.log(1, f"[中转站] 检测到结构化错误信息: {error_msg[:50]}...")
                        return True

            return False
        except Exception as e:
            util.log(2, f"[中转站] 检查失败状态异常: {str(e)}")
            return False



    def _is_agent_working_state(self, content_text, source_str):
        """检查是否为Agent的WORKING状态 - 只检查music工具的status字段"""
        try:
            # music工具返回COMPLETED状态就不是WORKING状态
            if '"status": "COMPLETED"' in str(content_text):
                return False
            return False  # 其他情况都不是WORKING状态
        except:
            return False

    def _is_music_completed_state(self, content_text):
        """检查是否为music工具的COMPLETED状态"""
        try:
            content_str = str(content_text).lower()
            # 检查是否同时包含music和COMPLETED状态
            return '"status": "COMPLETED"' in str(content_text) and "music" in content_str
        except:
            return False

    def _has_active_music_tool(self):
        """检查是否有活跃的音乐工具"""
        try:
            # 检查最近10个状态中是否有音乐工具活动
            recent_states = self.intermediate_states[-10:] if len(self.intermediate_states) > 10 else self.intermediate_states
            
            # 标记：是否检测到音乐工具启动
            has_music_start = False
            # 标记：是否已经收到音乐旁白（表示音乐工具完成）
            has_music_completion = False
            
            for state in recent_states:
                if isinstance(state, dict):
                    source_str = str(state.get("source", "")).lower()
                    content_str = str(state.get("content", "")).lower()
                    
                    # 检查是否有音乐工具启动的标志
                    if ("music" in source_str or "music" in content_str) and any(keyword in content_str for keyword in ["启动", "处理中", "working"]):
                        has_music_start = True
                        util.log(1, f"[中转站] 检测到音乐工具启动标志: {source_str} - {content_str[:50]}...")
                    
                    # 检查是否收到音乐旁白（表示完成）
                    if state.get("content_type") == "music_narration_result" or ("旁白" in content_str and "音乐" in content_str):
                        has_music_completion = True
                        util.log(1, f"[中转站] 检测到音乐完成标志: {source_str} - {content_str[:50]}...")
            
            # 如果有音乐启动但没有完成，说明还在运行
            is_active = has_music_start and not has_music_completion
            
            if is_active:
                util.log(1, f"[中转站] 音乐工具仍在运行中")
            
            return is_active
            
        except Exception as e:
            util.log(2, f"[中转站] 检查活跃音乐工具异常: {str(e)}")
            return False

    def get_optimized_final_content(self):
        """获取优化后的final内容供UI使用"""
        try:
            final_content = self.optimized_contents.get("final")
            if final_content:
                util.log(1, f"[中转站] 返回final优化内容给UI: {final_content[:50]}...")
                return final_content
            else:
                util.log(2, f"[中转站] 未找到final优化内容")
                return None
        except Exception as e:
            util.log(2, f"[中转站] 获取优化内容异常: {str(e)}")
            return None
    
    def get_all_optimized_contents(self):
        """获取所有阶段的优化内容（start/middle/final）"""
        result = {
            "start": self.optimized_contents.get("start") or self.lg_snapshot.get("start"),
            "middle": self.optimized_contents.get("middle") or self.lg_snapshot.get("middle"),
            "final": self.optimized_contents.get("final") or self.lg_snapshot.get("final")
        }
        util.log(1, f"[中转站] get_all_optimized_contents返回: start={result['start'][:50] if result['start'] else None}, middle={result['middle'][:50] if result['middle'] else None}, final={result['final'][:50] if result['final'] else None}")
        return result

    # 🔧 新增：获取LG阶段快照（不依赖SisiCore）
    def get_lg_snapshot(self):
        try:
            return {
                "start": self.lg_snapshot.get("start"),
                "middle": self.lg_snapshot.get("middle"),
                "final": self.lg_snapshot.get("final")
            }
        except Exception:
            return {"start": None, "middle": None, "final": None}

# 优化全局单例获取函数
def get_transit_station():
    """获取中转站全局单例实例 - 使用类方法确保跨进程获取相同实例"""
    global _GLOBAL_TRANSIT_INSTANCE, _GLOBAL_TRANSIT_LOCK

    # 使用类方法获取实例
    return TransitStation.get_instance()
