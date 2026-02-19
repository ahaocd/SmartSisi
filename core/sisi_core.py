# 负责处理交互流程：文本输入、语音与文本输出、情绪状态更新与展示
import math
import os
import time
import socket
import wave
import requests
import platform
import json
import re
import concurrent.futures
from pydub import AudioSegment
from queue import Queue
import sounddevice as sd
import soundfile as sf

# 适配模型相关依赖
import numpy as np
# import sisi_booter  # 移到函数内部以避免循环导入
from core import wsa_server
from core.interact import Interact
from tts.tts_voice import EnumVoice
from scheduler.thread_manager import MyThread
from tts import tts_voice
from utils import util, config_util
from qa import qa_service
from utils import config_util as cfg
# 已移除 content_db，统一使用 Mem0 记忆系统
from llm import nlp_rasa
from llm import liusisi
from llm import nlp_lingju
from llm import nlp_ollama_api
from llm import nlp_coze
from llm.agent import agentss
from llm import nlp_llm_stream
from core import stream_manager
# member_db 已移除，统一使用 Mem0 记忆系统
# from core import member_db
import threading
import functools
import cv2
import base64
import random
from core import shared_state
from ai_module.templates import COMMAND_TEMPLATES, DIALOGUE_TEMPLATES
import inspect

# 智能音频收集系统
from core.smart_audio_collector import get_audio_collector

# 监控系统已迁移到 main.py 统一管理
MONITOR_AVAILABLE = False

# Windows 平台特定导入（当前未启用）
# LipSyncGenerator = None
# if platform.system() == "Windows":
#     try:
#         import sys
#         sys.path.append("test/ovr_lipsync")
#         from test_olipsync import LipSyncGenerator
#         util.log(1, "唇形同步模块导入成功")
#     except ImportError:
#         util.log(1, "唇形同步模块导入失败，将不支持唇形同步功能")

# 加载配置
cfg.load_config()
if cfg.tts_module == 'gptsovits':
    from tts.gptsovits import Speech
elif cfg.tts_module == 'gptsovits_v3':
    from tts.gptsovits_v3 import Speech
elif cfg.tts_module == 'siliconflow':
    from tts.siliconflow_tts import Speech
else:
    from tts.siliconflow_tts import Speech

# 导入 LLM 模块
from llm import liusisi
from llm import nlp_llm_stream

# 创建模型映射
modules = {
    "liusisi": liusisi,
    "nlp_lingju": nlp_lingju,
    "nlp_rasa": nlp_rasa,
    "nlp_agentss": agentss,
    "nlp_ollama_api": nlp_ollama_api,
    "nlp_coze": nlp_coze,
    "nlp_llm_stream": nlp_llm_stream,
    "nlp_agent": agentss
}

# 全局变量定义
_timer = None
recording = False
noise_amount = 0
auto_play_thread = None
auto_play_running = False
last_request_time = 0  # 自动播放上次请求时间

# 全局实例
_sisi_core_instance = None

# 导入统一音频队列管理器
from utils.stream_sentence import AudioPriorityQueue

def get_sisi_core():
    """获取 SisiCore 实例。"""
    global _sisi_core_instance
    return _sisi_core_instance

class SisiCore:
    def __init__(self, com=None):
        # 基础初始化
        self.lock = threading.Lock()
        self.mood = 0.0
        self.old_mood = 0.0
        self.item_index = 0
        self.X = np.array([1, 0, 0, 0, 0, 0, 0, 0]).reshape(1, -1)
        self.W = np.array([0.0, 0.6, 0.1, 0.7, 0.3, 0.0, 0.0, 0.0]).reshape(-1, 1)
        self.wsParam = None
        self.wss = None
        self.sp = Speech()

        # 存储最近一次音频上下文，供前脑系统复用
        self.latest_audio_context = None
        self._interaction_count_by_user = {}
        self._last_submitted_brain_task_id_by_user = {}
        self._last_injected_brain_task_id_by_user = {}
        self.speaking = False
        self.chatting = False  # 聊天处理中标记
        self.__running = True

        # 初始化用户 ID，用于调用 NLP/Agent 模型
        self.user_id = 0

        # 初始化播放相关
        print("[初始化] 开始初始化音频系统...")
        # 这里使用标准 Queue 作为播放队列
        from queue import Queue
        self.sound_query = Queue()  # 使用标准队列
        self.speaking = False  # 说话状态标记
        
        print("[初始化] 音频队列已创建")

        # 连接语音合成服务
        self.sp.connect()
        print("[初始化] 语音合成服务已连接")

        # 启动播放线程
        print("[初始化] 正在启动播放线程...")
        self.__play_thread = MyThread(target=self.__play_sound)
        self.__play_thread.start()
        print("[初始化] 播放线程已启动")

        # 初始化智能音频收集系统
        input_mode = "device_only"
        try:
            source_cfg = cfg.config.get("source", {}) if isinstance(cfg.config, dict) else {}
            input_mode = str(source_cfg.get("input_mode", "device_only") or "device_only").strip().lower()
        except Exception:
            input_mode = "device_only"

        if input_mode == "device_only":
            self.audio_collector = None
            print("[初始化] device_only 模式，跳过本机音频收集器")
        else:
            print("[初始化] 正在启动智能音频收集系统...")
            try:
                self.audio_collector = get_audio_collector()
                self.audio_collector.start_collection()
                print("[初始化] 智能音频收集系统已启动")
            except Exception as e:
                print(f"[初始化] 智能音频收集系统启动失败: {str(e)}")
                self.audio_collector = None

        # 鍏朵粬鍒濆鍖?
        self.timer = None
        self._last_text = None
        self._last_text_time = 0  # 娣诲姞鏈€鍚庝竴娆℃枃鏈椂闂?
        self._text_interval = 1  # 淇敼涓?绉?
        self._last_spoken_text = None
        self._last_observation_key = None
        self._last_response_key = None
        self._last_camera_time = 0.0
        self._last_queue_check = 0.0

        # 注册到中转站
        try:
            from llm.transit_station import get_transit_station
            transit = get_transit_station()
            transit.register_sisi_core(self)
            util.log(1, "[SmartSisi核心] 已注册到中转站")
        except Exception as e:
            util.log(2, f"[SmartSisi核心] 注册到中转站失败: {str(e)}")

        # 注册到 SmartSisi 核心桥接
        try:
            from llm.sisi_core_bridge import get_bridge
            bridge = get_bridge()
            bridge.start_server(self)
            util.log(1, "[SmartSisi核心] 已注册到SmartSisi核心桥接")
        except Exception as e:
            util.log(2, f"[SmartSisi核心] 注册到SmartSisi核心桥接失败: {str(e)}")

        print("[初始化] SisiCore 初始化完成")



    # 绠€鍗曠殑TTS杞崲鏂规硶
    def do_tts(self, text, style=None, is_agent=False, priority=1, interact=None):
        """
        鏂囨湰杞闊冲鐞?

        Args:
            text (str): 要转换的文本
            style (str, optional): TTS 风格
            is_agent (bool, optional): 是否来自 Agent 生成
            priority (int, optional): 优先级，数值越大优先级越高
            interact (Interact, optional): 交互对象

        Returns:
            str: 生成的音频文件路径或 None
        """
        try:
            # 检查是否需要跳过本次 TTS（避免跨轮次残留标记）
            if hasattr(self, '_skip_next_tts') and self._skip_next_tts:
                # 检查标记时间戳，超过 3 秒视为过期
                skip_timestamp = getattr(self, '_skip_tts_timestamp', 0)
                import time as _time
                if (_time.time() - skip_timestamp) > 3.0:
                    util.log(1, f"[TTS] 检测到过期跳过标记（{_time.time()-skip_timestamp:.1f}秒前），已清理并继续播放")
                    self._skip_next_tts = False
                else:
                    util.log(1, f"[TTS] 检测到跳过标记，跳过本次 TTS 生成: {text[:30]}...")
                    self._skip_next_tts = False  # 清理标记
                    return None

            # 如果没有提供交互对象，则创建默认对象
            if interact is None:
                from core.interact import Interact
                interact = Interact(
                    interleaver="tts",
                    interact_type=2,  # 透传模式
                    data={"user": "User", "text": text}
                )

            # 使用统一队列架构处理 TTS
            util.log(1, "[TTS] 使用统一队列架构处理 TTS")

            # 调用 TTS 生成音频文件
            audio_file = self.sp.to_sample(text, style)

            if audio_file:
                util.log(1, f"[TTS] 音频处理完成: {audio_file}")

                # 检查是否为流式播放完成标记
                if audio_file == "STREAMING_COMPLETED":
                    util.log(1, "[TTS] 设备流式播放完成，不进行额外播放")
                    # 流式播放已完成，不需要额外处理
                    return audio_file
                elif audio_file and os.path.exists(audio_file):
                    # TTS 引擎已完成实时播放，这里只返回文件路径
                    return audio_file
                else:
                    util.log(1, f"[TTS] 文件不存在或无效: {audio_file}")
                    return audio_file
            else:
                util.log(2, "[TTS] 音频处理失败")
                return None
        except Exception as e:
            util.log(2, f"[TTS] 音频生成失败: {str(e)}")
            return None

    def process_audio_response(self, text, username="User", interact=None,
                             priority=1, style=None, is_agent=False, display_text=None, send_to_web=True):
        """
        统一处理音频响应的方法，供各模块调用。

        Args:
            text (str): 要播放的文本
            username (str): 用户名，默认 "User"
            interact (Interact): 交互对象，为 None 时创建默认对象
            priority (int): 播放优先级，数值越大优先级越高
            style (str): 语音风格
            is_agent (bool): 是否来自 Agent 回答
            display_text (str): 前端显示文本（可包含控制标记）
            send_to_web (bool): 是否推送到前端（流式 TTS 分段时可关闭）

        Returns:
            str: 音频文件路径或 None
        """
        try:
            if display_text is None:
                display_text = text

            # 检查当前系统模式，避免重复 TTS 处理
            from llm.liusisi import get_current_system_mode
            current_mode = get_current_system_mode()
            if current_mode == "liuye":
                # 仅当来自柳叶委托调用时执行统一 TTS；否则跳过以避免重复播放
                util.log(1, "[TTS] 柳叶模式统一走系统 TTS（OPUS 单通道）")
                try:
                    interleaver_name = getattr(interact, 'interleaver', '') if interact is not None else ''
                except Exception:
                    interleaver_name = ''
                if interleaver_name != 'liuye':
                    util.log(1, "[TTS] 柳叶后置阶段检测到非委托调用，前置流程已播放，跳过重复TTS")
                    return None

            # 重复播放抑制：3秒内相同文本直接跳过
            try:
                import time as _time
                last_ts = getattr(self, '_last_text_time', 0.0)
                last_txt = getattr(self, '_last_spoken_text', None)
                now_ts = _time.time()
                if last_txt == text and (now_ts - last_ts) < 3.0:
                    util.log(1, "[TTS] 检测到3秒内相同文本，跳过重复播放")
                    return None
                # 记录本次文本与时间
                self._last_spoken_text = text
                self._last_text_time = now_ts
            except Exception:
                pass

            # 如果未提供交互对象，则创建默认交互对象
            if interact is None:
                from core.interact import Interact

                # 获取最新音频文件路径
                import glob
                import os
                cache_root = cfg.cache_root or "cache_data"
                temp_audio_files = glob.glob(os.path.join(cache_root, "input_*.wav"))
                if not temp_audio_files:
                    temp_audio_files = glob.glob(os.path.join(cache_root, "tmp*.wav"))
                if temp_audio_files:
                    audio_path = max(temp_audio_files, key=os.path.getmtime)
                else:
                    audio_path = os.path.join(cache_root, "input.wav")

                interact = Interact(
                    interleaver="tts",
                    interact_type=2,  # 透传模式
                    data={"user": username, "text": text, "audio_path": audio_path}
                )

                # 同时设置交互对象的音频属性
                interact.audio_file = audio_path

            # 记忆写入由后台异步处理，不阻塞 TTS 生成
            uid = 1
            content_id = 0

            # 发送到 Web 端
            if send_to_web:
                try:
                    web_instance = wsa_server.get_web_instance()
                    if web_instance and hasattr(web_instance, 'is_connected') and web_instance.is_connected(username):
                        try:
                            from llm.liusisi import get_current_system_mode
                            reply_type = (get_current_system_mode() or "sisi").strip().lower()
                            if reply_type not in ("sisi", "liuye"):
                                reply_type = "sisi"
                        except Exception:
                            reply_type = "sisi"
                        response_msg = {
                            "panelReply": {
                                "type": reply_type,
                                "content": display_text,
                                "username": username,
                                "uid": uid,
                                "id": content_id
                            },
                            "Username": username
                        }
                        web_instance.add_cmd(response_msg)
                except Exception as e:
                    util.log(2, f"[TTS] Web端发送失败: {e}")

            # 生成 TTS 音频并进入播放流程
            audio_file = self.do_tts(text, style, is_agent, priority, interact)

            return audio_file
        except Exception as e:
            util.log(2, f"[TTS] 统一处理音频响应失败: {str(e)}")
            import traceback
            util.log(2, f"[TTS] 详细错误: {traceback.format_exc()}")
            return None

    def send_panel_reply(
        self,
        text,
        username="User",
        reply_type=None,
        is_intermediate=True,
        phase="stream",
        attachments=None,
    ):
        """仅发送前端展示消息，不触发TTS。"""
        try:
            if not (text or "").strip():
                return False
            web_instance = wsa_server.get_web_instance()
            if web_instance and hasattr(web_instance, 'is_connected') and web_instance.is_connected(username):
                if not reply_type:
                    try:
                        from llm.liusisi import get_current_system_mode
                        reply_type = (get_current_system_mode() or "sisi").strip().lower()
                        if reply_type not in ("sisi", "liuye"):
                            reply_type = "sisi"
                    except Exception:
                        reply_type = "sisi"
                response_msg = {
                    "panelReply": {
                        "type": reply_type,
                        "content": text,
                        "username": username,
                        "uid": 1,
                        "id": int(time.time() * 1000),
                        "is_intermediate": bool(is_intermediate),
                        "phase": phase
                    },
                    "Username": username
                }
                if isinstance(attachments, list) and attachments:
                    response_msg["panelReply"]["attachments"] = attachments
                web_instance.add_cmd(response_msg)
                return True
        except Exception as e:
            util.log(2, f"[TTS] Web端发送失败(only-ui): {e}")
        return False

    # 大语言模型回复处理
    def handle_chat_message(self, text, brain_prompts=None, interact=None):
        """处理用户聊天消息。

        Args:
            text: 用户输入文本
            brain_prompts: 前脑系统生成的动态提示词

        Returns:
            Tuple: (响应文本, 语气类型)
        """


        # 标记当前处于聊天处理中
        self.chatting = True

        try:
            # 记录处理开始时间
            start_time = time.time()

            from llm.liusisi import get_current_system_mode
            current_mode = (get_current_system_mode() or "sisi").strip().lower()

            if current_mode == "liuye":
                # 路由到柳叶系统处理
                util.log(1, f"[系统路由] 当前模式: {current_mode}，路由到柳叶系统")
                return self._process_with_liuye(text, brain_prompts, interact=interact)
            else:
                # 路由到 SmartSisi 主系统处理
                util.log(1, f"[系统路由] 当前模式: {current_mode}，路由到SmartSisi系统")

            if not brain_prompts:
                try:
                    from core.brain_async_processor import get_latest_brain_result
                    from sisi_memory.context_kernel import namespaced_user_id

                    user_key = namespaced_user_id("sisi", str(getattr(self, "current_user_id", None) or "default_user"))
                    brain_result = get_latest_brain_result(user_key)
                    if brain_result and brain_result.success:
                        brain_prompts = {
                            "dynamic_prompt": brain_result.dynamic_prompt,
                            "environment_analysis": brain_result.environment_analysis,
                            "memory_context": brain_result.memory_context,
                            "brain_timestamp": brain_result.created_at.isoformat() if getattr(brain_result, "created_at", None) else "",
                            "brain_task_id": brain_result.task_id,
                        }
                        util.log(1, f"[前脑系统] cache_hit task_id={brain_result.task_id}")
                    else:
                        brain_prompts = {}
                except Exception as e:
                    util.log(2, f"[前脑系统] cache_read_failed error={e}")
                    brain_prompts = {}

            # 导入 NLP 模块处理
            from llm import liusisi

            # 构建声纹身份信息
            speaker_info = {
                "real_name": getattr(self, "current_user_identity", "陌生人"),
                "username": getattr(self, "current_user_id", "default_user"),
                "speaker_id": getattr(self, "current_user_id", "default_user"),
                "confidence": getattr(self, "current_confidence", 0.0),
            }



            # 先用 NLP 模块快速处理，获取初步回复，并传入脑系统上下文
            mode_switched = False
            try:
                mode_switched = liusisi.consume_mode_switch_flag()
            except Exception:
                mode_switched = False

            llm_override = None
            try:
                if hasattr(interact, "data") and isinstance(interact.data, dict):
                    candidate = interact.data.get("llm_override")
                    if isinstance(candidate, dict):
                        llm_override = candidate
            except Exception:
                llm_override = None

            if llm_override:
                try:
                    liusisi.set_llm_override(llm_override)
                except Exception:
                    pass
            question_input = text
            try:
                if hasattr(interact, "data") and isinstance(interact.data, dict):
                    mm_parts = interact.data.get("llm_user_content_parts")
                    if isinstance(mm_parts, list) and mm_parts:
                        question_input = {
                            "text": text,
                            "llm_user_content_parts": mm_parts,
                        }
            except Exception:
                question_input = text

            try:
                nlp_text, nlp_style = liusisi.question(
                    question_input,
                    self.user_id,
                    brain_prompts=brain_prompts,
                    speaker_info=speaker_info,
                    mode_switched=mode_switched,
                )
            finally:
                if llm_override:
                    try:
                        liusisi.clear_llm_override()
                    except Exception:
                        pass

            try:
                from sisi_memory.context_kernel import enforce_attribution

                nlp_text = enforce_attribution(
                    persona=(getattr(self, "current_persona", None) or "sisi").strip().lower(),
                    user_input=text,
                    assistant_text=nlp_text,
                )
            except Exception:
                pass

            # 记录 NLP 处理完成
            util.log(1, f"[SmartSisi核心] NLP处理完成，耗时: {time.time() - start_time:.2f}秒")

            # 输出 NLP 快速响应结果
            util.log(1, f"[SmartSisi核心] NLP快速响应: {nlp_text[:50]}...")
            
            # 仅当流式层已实际播报过，才标记为已处理，避免误跳过后置 TTS
            if hasattr(self, 'current_interact'):
                try:
                    skip_flag = bool(getattr(self, '_skip_next_tts', False))
                    skip_ts = float(getattr(self, '_skip_tts_timestamp', 0) or 0)
                    skip_fresh = skip_flag and (time.time() - skip_ts) <= 3.0
                except Exception:
                    skip_flag = False
                    skip_fresh = False

                if skip_fresh:
                    self.current_interact.nlp_processed = True
                    util.log(1, "[SmartSisi核心] 检测到流式已播报，标记 nlp_processed，Core层跳过重复TTS")
                elif skip_flag:
                    self._skip_next_tts = False
                    util.log(1, "[SmartSisi核心] 检测到过期 skip 标记，已清理，后置 TTS 继续执行")

            
            # LG 触发检测（由触发标签驱动）
            lg_triggered = False
            try:
                import re
                from utils import emotion_trigger as et

                tag_matches = re.findall(r'\{([^{}]+)\}', nlp_text or "")
                for tag in tag_matches:
                    cfg = et.EMOTION_TRIGGER_MAP.get(tag) or et.EMOTION_TRIGGER_MAP.get((tag or "").lower())
                    if cfg and cfg.get("type") == "lg_trigger":
                        lg_triggered = True
                        break
            except Exception as _e:
                util.log(2, f"[LG] tag parse failed: {_e}")
                lg_triggered = False

            if lg_triggered:
                try:
                    from llm.agent.langgraph_adapter import get_instance
                    langgraph = get_instance()

                    # Inject recent history as tool context
                    observation = ""
                    try:
                        from sisi_memory.chat_history import build_prompt_context, format_messages_as_text

                        canonical_user_id = str(getattr(self, "current_user_id", None) or "default_user")
                        ctx = build_prompt_context(
                            user_id=canonical_user_id,
                            current_mode="sisi",
                            query_text=text or "",
                            include_other=False,
                        )
                        recent_text = format_messages_as_text(ctx.recent_messages)
                        if recent_text:
                            observation = ("Task is already in recent dialog; use context below.\n"
                                           "Recent:\n" + recent_text)
                    except Exception as _he:
                        util.log(2, f"[LG] history load failed: {_he}")

                    util.log(1, "[SmartSisi] Detected LG trigger, starting LangGraph")
                    MyThread(
                        target=langgraph.process_query,
                        args=(text, self.user_id, ""),
                        kwargs={"observation": observation} if observation else None,
                        name="LangGraphThread"
                    ).start()
                except Exception as _le:
                    util.log(2, f"[LG] start failed: {_le}")
                    self.chatting = False
            else:
                # no LG trigger, end chatting
                self.chatting = False

            return nlp_text, nlp_style

        except Exception as e:
            # NLP 处理异常时，记录错误并返回可读提示
            util.log(2, f"[SmartSisi核心] NLP处理异常: {str(e)}")
            error_message = f"处理您的请求时出现问题: {str(e)}"
            self.chatting = False
            return error_message, "normal"

    def _process_with_liuye(self, text: str, brain_prompts=None, interact=None) -> tuple:
        """使用柳叶系统处理用户输入。"""
        try:
            util.log(1, f"[柳叶处理] 开始处理用户输入: {text[:30]}...")

            canonical_user_id = str(getattr(self, "current_user_id", None) or "default_user")

            mode_switched = False
            try:
                from llm import liusisi

                mode_switched = liusisi.consume_mode_switch_flag()
            except Exception:
                mode_switched = False

            handoff_messages = []
            if mode_switched:
                try:
                    from sisi_memory.chat_history import build_handoff_messages

                    handoff_messages = build_handoff_messages(user_id=canonical_user_id, mode="sisi", turns=2)
                except Exception:
                    handoff_messages = []

            # 导入柳叶智能体
            from evoliu.liuye_frontend.intelligent_liuye import get_intelligent_liuye
            liuye_instance = get_intelligent_liuye()

            liuye_input = text
            liuye_llm_override = None
            try:
                if hasattr(interact, "data") and isinstance(interact.data, dict):
                    mm_parts = interact.data.get("llm_user_content_parts")
                    if isinstance(mm_parts, list) and mm_parts:
                        liuye_input = {
                            "text": text,
                            "llm_user_content_parts": mm_parts,
                        }
                    override = interact.data.get("llm_override")
                    if isinstance(override, dict):
                        liuye_llm_override = override
            except Exception:
                liuye_input = text
                liuye_llm_override = None

            # Use persona-aware identity and brain prompts.
            liuye_response = liuye_instance._process_user_input_sync(
                liuye_input,
                speaker_id=canonical_user_id,
                brain_prompts=brain_prompts if isinstance(brain_prompts, dict) else None,
                handoff_messages=handoff_messages,
                llm_override=liuye_llm_override,
            )

            try:
                from sisi_memory.context_kernel import enforce_attribution

                liuye_response = enforce_attribution(persona="liuye", user_input=text, assistant_text=liuye_response)
            except Exception:
                pass

            util.log(1, f"[柳叶处理] 柳叶回复: {liuye_response[:50]}...")

            # 将对话结果发送到 Web 界面（如果可用）
            self._send_to_web_interface(text, liuye_response)

            # 重置聊天处理中状态
            self.chatting = False
            util.log(1, "[柳叶处理] 处理完成，chatting 状态已重置")

            return liuye_response, "gentle"

        except Exception as e:
            util.log(2, f"[柳叶处理] 处理异常: {str(e)}")
            error_message = f"柳叶处理您的请求时出现问题: {str(e)}"
            # 异常时也要重置 chatting 状态
            self.chatting = False
            util.log(1, "[柳叶处理] 异常处理完成，chatting 状态已重置")
            return error_message, "normal"

    def _send_to_web_interface(self, user_input: str, liuye_response: str):
        """发送对话到 Web 界面。"""
        try:
            # 柳叶 Web 面板推送当前默认关闭，避免无效日志噪音
            util.log(1, "[柳叶处理] 跳过Web界面发送（未启用）")
            return

        except Exception as e:
            util.log(2, f"[Web发送] 发送到Web界面异常: {e}")

    # 语音消息处理：检查是否命中问答
    def __get_answer(self, interact, text="", observation=""):
        """检查是否命中 Q&A。"""
        try:
            # 全局问答
            answer, type = qa_service.QAService().question('qa', text)
            if answer is not None:
                # 只输出命中成功的简洁日志
                util.log(1, "[QA] 命中回答")
                return answer, type
            return None, None
        except Exception as e:
            util.log(1, f"[错误] QA匹配异常: {str(e)}")
            return None, None


    # 语音消息处理
    def __process_interact(self, interact: Interact):
        """处理交互消息。"""
        if not self.__running:
            return

        try:
            mode_switched = False
            # 重置状态
            self.speaking = False
            current_time = time.time()
            self._last_camera_time = current_time

            # 保存当前交互对象，供后续流程使用
            self.current_interact = interact

            # 校验交互对象完整性
            if not interact or not hasattr(interact, 'data') or not interact.data:
                util.log(1, "无效的交互数据")
                return 'error'

            # 优先处理自动播放透传消息，避免被普通语音流程拦截
            if interact.interleaver == "auto_play":  # 自动播放回调
                auto_play_text = interact.data.get("text", "") if interact.data else ""
                util.log(1, f"[SmartSisi核心] 处理自动播放内容: {auto_play_text[:50]}...")
                
                # 从 interact 对象获取 tone（style）
                tone = None
                if hasattr(interact, 'data') and isinstance(interact.data, dict):
                    tone = interact.data.get('tone')

                # 解析自动播放内容
                actual_text_to_speak = auto_play_text
                try:
                    # 尝试解析 JSON，自动播放服务传入内容可能是 JSON 字符串
                    play_data = json.loads(auto_play_text)
                    if isinstance(play_data, dict) and 'text' in play_data:
                        actual_text_to_speak = play_data.get('text')
                        # 如果 JSON 中有 tone，也一并使用
                        if not tone and 'tone' in play_data:
                            tone = play_data.get('tone') 
                except json.JSONDecodeError:
                    # 解析失败时，默认 auto_play_text 本身就是要播报文本
                    util.log(1, "[SmartSisi核心] 自动播放文本不是JSON，直接使用原始文本")
                except TypeError:
                     util.log(2, "[SmartSisi核心] 自动播放文本为None或非字符串，无法处理")
                     return

                if actual_text_to_speak:
                    util.log(1, f"[SmartSisi核心-自动播放] 使用标准TTS流程处理自动播放: {actual_text_to_speak[:30]}...")
                    
                    # 使用标准 TTS 流程，不直接调用 SisiAdapter
                    # 通过 do_tts() -> notify_tts_event() -> SisiAdapter 完成分发
                    audio_file_path = self.do_tts(actual_text_to_speak, tone, is_agent=False, priority=0, interact=interact)
                    
                    if audio_file_path:
                        util.log(1, f"[SmartSisi核心-自动播放] 自动播放音频已通过标准流程生成: {audio_file_path}")
                        util.log(1, "[SmartSisi核心-自动播放] 设备播放将通过标准TTS事件通知机制处理")
                    else:
                        util.log(2, "[SmartSisi核心-自动播放] 音频生成失败")
                else:
                    util.log(2, "[SmartSisi核心] 自动播放未提取到有效文本，无法执行TTS")

            elif interact.interact_type == 1:  # 语音输入模式
                msg = interact.data.get("msg", "")
                username = interact.data.get("user", "User")
                cleaned_msg = msg.strip('。，！？.,:;!?')

                # 简化日志输出
                util.log(1, f"[交互] 用户: {username}, 消息: {cleaned_msg}")

                if cleaned_msg:  # 仅处理非空消息
                    # 无论系统忙闲，都先执行基础过滤
                    from core.smart_interrupt import get_smart_interrupt
                    smart_interrupt = get_smart_interrupt()
                    
                    # 第一层过滤：音频质量过滤（回声、噪音）
                    if smart_interrupt._is_poor_audio_quality(cleaned_msg):
                        util.log(1, f"[过滤] 检测到低质量音频输入，忽略: {cleaned_msg}")
                        return
                    
                    # 第二层过滤：无意义短输入
                    if len(cleaned_msg) <= 2 and cleaned_msg in ["嗯", "啊", "呃", "哦", "额"]:
                        util.log(1, f"[过滤] 检测到单字噪声词，忽略: {cleaned_msg}")
                        return

                    # Lightweight command intent routing with hard whitelist gate.
                    try:
                        from ai_module.commands.intent_map import (
                            build_client_control_event,
                            resolve_intent_from_text,
                            validate_intent_execution,
                        )

                        intent_env = resolve_intent_from_text(cleaned_msg, source="voice")
                        can_execute, deny_reason = validate_intent_execution(intent_env, cleaned_msg)
                        intent_name = str((intent_env or {}).get("intent") or "").strip()

                        if can_execute and intent_name == "interrupt_output":
                            self._stop_all_systems()
                            self._stop_current_tasks()
                            try:
                                self._execute_interrupt_function("stop_music")
                            except Exception:
                                pass
                            self.process_audio_response(
                                text=str(intent_env.get("ack") or "好的，已停止当前输出。"),
                                username=username,
                                interact=interact,
                                priority=7,
                            )
                            return

                        if can_execute and intent_name:
                            ws_event = build_client_control_event(intent_env, username=username)
                            pushed = False
                            if ws_event:
                                try:
                                    wsa_server.get_web_instance().add_cmd(ws_event)
                                    pushed = True
                                except Exception as ws_err:
                                    util.log(2, f"[intent] push_control_intent_failed: {ws_err}")
                            if pushed:
                                ack_text = str(intent_env.get("ack") or "").strip()
                                if ack_text:
                                    self.process_audio_response(
                                        text=ack_text,
                                        username=username,
                                        interact=interact,
                                        priority=6,
                                    )
                                return
                        elif intent_name:
                            util.log(1, f"[intent] denied intent={intent_name} reason={deny_reason}")
                    except Exception as intent_err:
                        util.log(2, f"[intent] voice_route_check_failed: {intent_err}")
                    
                    # 智能打断系统：交由统一模型决策
                    # 检测 SmartSisi 是否正在运行
                    is_sisi_running = self._is_sisi_running()

                    if not is_sisi_running:
                        # SmartSisi 完全空闲，按正常对话流程处理
                        util.log(1, f"[智能打断] SmartSisi系统空闲，正常对话: {cleaned_msg}")
                        # 直接继续正常流程
                    else:
                        # SmartSisi 正在运行，交由大模型决策是否打断
                        util.log(1, f"[智能打断] SmartSisi系统运行中，交给大模型决策: {cleaned_msg}")
                        try:

                            # 交给大模型进行打断决策
                            decision = smart_interrupt.check_interrupt(cleaned_msg)

                            if decision.get("is_meaningless"):
                                # 无意义输入，忽略
                                util.log(1, f"[智能打断] 大模型判定为无意义输入，忽略: {cleaned_msg}")
                                return

                            elif decision.get("should_interrupt"):
                                # 大模型决定打断
                                util.log(1, f"[智能打断] 大模型决定打断: {decision['reason']}")

                                # 立即播报大模型给出的打断短语
                                if decision.get("response_text"):
                                    self.process_audio_response(
                                        text=decision["response_text"],
                                        username=username,
                                        interact=interact,
                                        priority=7  # 最高优先级
                                    )

                                # 停止所有系统活动
                                self._stop_all_systems()

                                # 根据决策决定是否重新开始流程
                                if decision.get("restart_full_flow"):
                                    util.log(1, "[智能打断] 重新开始完整流程")
                                    pass  # 继续执行后续正常流程
                                else:
                                    util.log(1, "[智能打断] 打断完成，不重新开始")
                                    return

                            else:
                                # 大模型决定不打断，继续后续判断
                                util.log(1, f"[智能打断] 大模型决定不打断: {decision['reason']}")

                                # 检查是否属于无意义输入
                                if decision.get("is_meaningless"):
                                    util.log(1, "[智能打断] 输入无意义，系统不干预，继续正常流程")
                                    pass  # 继续执行后续正常流程
                                else:
                                    # 有效输入：设置待播报状态短语，先显示用户输入
                                    if decision.get("response_text"):
                                        util.log(1, f"[智能打断] 设置待处理状态短语: {decision['response_text']}")

                                        # 将状态短语暂存，在用户输入展示后再输出
                                        self._pending_interrupt_response = decision["response_text"]
                                        util.log(1, "[智能打断] 先显示用户输入到前端，再输出状态短语")
                                    else:
                                        util.log(1, "[智能打断] 有效输入但无状态短语，继续正常流程")
                                        pass  # 继续执行后续正常流程

                        except Exception as e:
                            util.log(2, f"[智能打断] 大模型决策异常: {str(e)}")
                            # 异常时降级为正常对话流程，不中断主流程
                            util.log(1, "[智能打断] 打断系统异常，降级为正常对话模式")
                            # 继续执行正常流程（不 return）

                    # 记录用户问题
                    self.write_to_file(util.LOGS_DIR, "asr_result.txt", cleaned_msg)

                    # 记忆由前脑系统后台处理，主流程仅保留轻量上下文
                    uid = 1

                    # 优先使用 ASR_server 提供的声纹识别结果，避免重复处理
                    audio_context = interact.data.get('audio_context', {})
                    voiceprint_result = audio_context.get('voiceprint', {})

                    # 获取音频路径供前脑系统复用
                    current_audio_path = (
                        interact.data.get('audio_path') or
                        getattr(interact, 'audio_file', None) or
                        getattr(interact, 'audio_path', None)
                    )

                    # 存储主交互的音频上下文，供前脑系统复用
                    self.latest_audio_context = {
                        'audio_path': current_audio_path,
                        'text': cleaned_msg,
                        'audio_context': audio_context,
                        'voiceprint_result': voiceprint_result,
                        'timestamp': time.time(),
                        'source': 'main_interaction'
                    }

                    # 使用 ASR_server 的声纹识别结果（基于 3D-Speaker）
                    # 优先信任 ASR_server 的统一身份对象：audio_context.voiceprint.identity
                    identity_obj = None
                    if isinstance(voiceprint_result, dict):
                        identity_obj = voiceprint_result.get('identity')

                    if isinstance(identity_obj, dict) and identity_obj.get('label') == 'owner':
                        identified_user = (
                            identity_obj.get('user_id') or
                            identity_obj.get('username') or
                            voiceprint_result.get('speaker_id', 'stranger')
                        )
                        real_name = (
                            identity_obj.get('username') or
                            identity_obj.get('display_name') or
                            voiceprint_result.get('real_name') or
                            '已注册用户',
                        )
                        confidence = float(identity_obj.get('confidence', voiceprint_result.get('confidence', 0.0)))
                        print(f"[声纹] 使用ASR统一身份对象: {real_name} (置信度 {confidence:.3f})")
                    else:
                        try:
                            from core.speaker_recognition import get_sisi_speaker_recognition
                            _rec = get_sisi_speaker_recognition()
                            _sim_thr = getattr(_rec, 'similarity_threshold', 0.45)
                        except Exception:
                            _sim_thr = 0.45

                        if (
                            voiceprint_result and
                            voiceprint_result.get('speaker_id') and
                            voiceprint_result.get('speaker_id') != 'unknown' and
                            voiceprint_result.get('confidence', 0.0) >= _sim_thr
                        ):
                            identified_user = voiceprint_result.get('username') or voiceprint_result.get('speaker_id', 'stranger')
                            confidence = voiceprint_result.get('confidence', 0.0)
                            real_name = voiceprint_result.get('real_name') or '未知用户'
                            print(f"[声纹] SISI-3D识别成功: {real_name} (置信度 {confidence:.3f})")
                        else:
                            print(f"[声纹] 未识别到注册用户，使用陌生人身份")
                            identified_user = "stranger"
                            real_name = "陌生人"

                    # === Persona-aware canonical identity ===
                    try:
                        from llm.liusisi import get_current_system_mode
                        current_persona = (get_current_system_mode() or "sisi").strip().lower()
                    except Exception:
                        current_persona = "sisi"

                    try:
                        from sisi_memory.context_kernel import resolve_canonical_user_id
                        canonical_user_id, _id_dbg = resolve_canonical_user_id(
                            voiceprint_user_id=identified_user if identified_user not in (None, "", "stranger") else None,
                            speaker_id=voiceprint_result.get("speaker_id") if isinstance(voiceprint_result, dict) else None,
                            fallback="default_user",
                        )
                    except Exception:
                        canonical_user_id = "default_user"

                    self.current_user_identity = real_name
                    self.current_user_external_id = identified_user
                    self.current_user_id = canonical_user_id
                    self.user_id = canonical_user_id
                    self.current_persona = current_persona

                    if hasattr(interact, "data") and isinstance(interact.data, dict):
                        interact.data["canonical_user_id"] = canonical_user_id
                        interact.data["persona"] = current_persona
                        interact.data["user_external_id"] = identified_user

                    # 记忆系统已在声纹识别中处理
                    uid = 1  # 记忆系统不依赖传统用户ID
                    content_id = 0
                    web_instance = wsa_server.get_web_instance()
                    if web_instance and hasattr(web_instance, 'is_connected') and web_instance.is_connected(username):
                        # 发送用户输入消息
                        user_msg = {
                            "panelReply": {
                                "type": "member",
                                "content": cleaned_msg,
                                "username": username,
                                "uid": uid,
                                "id": content_id
                            },
                            "Username": username
                        }
                        web_instance.add_cmd(user_msg)

                        # 发送“思考中”状态
                        web_instance.add_cmd({
                            "panelMsg": "鎬濊€冧腑...",
                            "agent_status": "thinking",
                            "Username": username
                        })

                    # 检查是否有待输出的智能打断状态短语
                    # 在用户输入展示后，再输出该状态短语
                    if hasattr(self, '_pending_interrupt_response'):
                        pending_response = getattr(self, '_pending_interrupt_response')
                        if pending_response:
                            util.log(1, f"[智能打断] 延迟输出状态短语: {pending_response}")
                            self.process_audio_response(
                                text=pending_response,
                                username=username,
                                interact=interact,
                                priority=6  # 高优先级，先播报状态短语
                            )
                            # 清理待处理响应
                            self._pending_interrupt_response = None
                            util.log(1, "[智能打断] 状态短语已输出，本轮结束，等待当前任务完成")
                            return

                    # 先尝试从 QA 库中获取回答
                    qa_answer, qa_type = self.__get_answer(interact, cleaned_msg)

                    if qa_answer:
                        # QA 命中成功，优先播放 QA 回答
                        self.__process_response(qa_answer, username, interact)


                        
                        # 检查 QA 答案是否触发音乐相关流程
                        # 若包含 {RELUCTANT}，视为音乐相关 QA
                        is_music_qa = qa_answer and '{RELUCTANT}' in qa_answer
                        
                        if is_music_qa:
                            util.log(1, f"[QA音乐] 检测到音乐脚本QA（脚本: {qa_type}），调用音乐模块")
                            try:
                                # 调用音乐模块获取预设句子
                                from llm.nlp_music import question as music_question
                                music_response = music_question(cleaned_msg)
                                
                                if music_response:
                                    util.log(1, f"[QA音乐] 音乐模块返回: {music_response}")
                                    # 处理音乐模块回复（可能包含 [RANDOM] 标记）
                                    self.__process_response(music_response, username, interact)

                                    return f"{qa_answer} {music_response}"
                                else:
                                    util.log(2, "[QA音乐] 音乐模块返回为空")
                            except Exception as e:
                                util.log(2, f"[QA音乐] 调用音乐模块失败: {str(e)}")
                        
                        return qa_answer

                    # 前脑系统信息收集：在处理聊天消息前补全上下文
                    try:
                        util.log(1, f"[前脑系统] 开始信息收集和处理...")

                        # 使用前脑系统（sisi_brain/real_brain_system.py）
                        try:
                            from sisi_brain.real_brain_system import get_real_brain_system

                            # 获取前脑系统实例
                            brain_system = get_real_brain_system()

                            util.log(1, f"[前脑系统] 启动前脑系统（当前轮次: {brain_system.current_round + 1}）")

                            # 按优先级获取音频路径
                            audio_path = interact.data.get('audio_path', '')

                            # 如果未提供 audio_path，则按优先级回退
                            if not audio_path:
                                # 1. 优先读取 interact.audio_file
                                if hasattr(interact, 'audio_file') and interact.audio_file:
                                    audio_path = interact.audio_file
                                    util.log(1, f"[前脑系统] 使用interact.audio_file: {audio_path}")
                                elif hasattr(interact, 'data') and interact.data.get('audio_file'):
                                    audio_path = interact.data.get('audio_file')
                                    util.log(1, f"[前脑系统] 使用interact.data.audio_file: {audio_path}")
                                else:
                                    # 2. 查找最新录音文件
                                    import glob
                                    import os

                                    # 查找最新的临时音频文件
                                    cache_root = cfg.cache_root or "cache_data"
                                    temp_audio_files = glob.glob(os.path.join(cache_root, "input_*.wav"))
                                    if not temp_audio_files:
                                        temp_audio_files = glob.glob(os.path.join(cache_root, "tmp*.wav"))
                                    if temp_audio_files:
                                        # 按修改时间排序，取最新文件
                                        audio_path = max(temp_audio_files, key=os.path.getmtime)
                                        util.log(1, f"[前脑系统] 使用最新临时音频: {audio_path}")
                                    else:
                                        # 3. 查找 input.wav
                                        input_wav = os.path.join(cache_root, "input.wav")
                                        if os.path.exists(input_wav):
                                            audio_path = input_wav
                                            util.log(1, f"[前脑系统] 使用input.wav: {audio_path}")
                                        else:
                                            # 4. 最后兜底：使用默认路径
                                            audio_path = os.path.join(cache_root, "default.wav")
                                            util.log(1, f"[前脑系统] 未找到音频文件，使用默认路径: {audio_path}")

                            # Brain task is fire-and-forget; prompt injection uses cached results from previous turns.
                            try:
                                from core.brain_async_processor import (
                                    ensure_brain_processor_started,
                                    get_latest_brain_result,
                                    submit_brain_task_fire_and_forget,
                                )
                                from sisi_memory.context_kernel import namespaced_user_id, normalize_persona

                                ensure_brain_processor_started()

                                persona = normalize_persona(getattr(self, "current_persona", None) or "sisi")
                                canonical_user_id = (
                                    interact.data.get("canonical_user_id")
                                    if hasattr(interact, "data") and isinstance(interact.data, dict)
                                    else None
                                ) or getattr(self, "current_user_id", None) or "default_user"
                                user_key = namespaced_user_id(persona, str(canonical_user_id))
                                print(f"[前脑系统] 使用用户标识: {user_key}")

                                n = int(self._interaction_count_by_user.get(user_key, 0)) + 1
                                self._interaction_count_by_user[user_key] = n

                                current_task_id = submit_brain_task_fire_and_forget(audio_path, cleaned_msg, user_key)
                                if current_task_id:
                                    util.log(1, f"[前脑系统] task_submitted task_id={current_task_id}")
                                    self._last_submitted_brain_task_id_by_user[user_key] = current_task_id

                                inject_allowed = n >= 2
                                cached = get_latest_brain_result(user_key)
                                last_injected = self._last_injected_brain_task_id_by_user.get(user_key)

                                if inject_allowed and cached and cached.success:
                                    if cached.task_id and cached.task_id != current_task_id and cached.task_id != last_injected:
                                        brain_prompts = {
                                            "environment_analysis": cached.environment_analysis,
                                            "memory_context": cached.memory_context,
                                            "dynamic_prompt": cached.dynamic_prompt,
                                            "brain_timestamp": cached.created_at.isoformat() if getattr(cached, "created_at", None) else "",
                                            "brain_task_id": cached.task_id,
                                        }
                                        self._last_injected_brain_task_id_by_user[user_key] = cached.task_id
                                        util.log(1, f"[前脑系统] cache_hit task_id={cached.task_id}")
                                    else:
                                        brain_prompts = {}
                                        util.log(1, "[前脑系统] cache_skip")
                                else:
                                    brain_prompts = {}
                                    util.log(1, "[前脑系统] cache_miss")

                            except Exception as e:
                                util.log(2, f"[前脑系统] error={str(e)}")
                                brain_prompts = {}

                        except Exception as e:
                            util.log(2, f"[前脑系统] 前脑处理失败: {str(e)}")
                            brain_prompts = {}

                        # 将前脑结果保存到 interact 对象中，供后续流程使用
                        interact.data['brain_prompts'] = brain_prompts

                    except Exception as e:
                        util.log(2, f"[前脑系统] 信息收集失败: {str(e)}")
                        # 前脑系统失败不影响主流程
                        interact.data['brain_prompts'] = {}

                    # 非观察命令处理：将 brain_prompts 传给大模型
                    text, style = self.handle_chat_message(cleaned_msg, brain_prompts, interact=interact)
                    interact.data['tone'] = style

                    # Event journal is the single source of "who said what" across personas.
                    try:
                        from sisi_memory.context_kernel import JournalTurn, UserKey, append_turn as append_journal_turn, normalize_persona

                        persona = None
                        canonical_user_id = None
                        external_id = None
                        if hasattr(interact, "data") and isinstance(interact.data, dict):
                            persona = interact.data.get("persona")
                            canonical_user_id = interact.data.get("canonical_user_id")
                            external_id = interact.data.get("user_external_id")

                        persona = normalize_persona(persona or getattr(self, "current_persona", None) or "sisi")
                        canonical_user_id = str(canonical_user_id or getattr(self, "current_user_id", None) or "default_user")

                        user_key = UserKey(persona=persona, canonical_user_id=canonical_user_id)

                        append_journal_turn(
                            JournalTurn(
                                user_key=user_key,
                                user_text=cleaned_msg or "",
                                assistant_text=text or "",
                                source="voice",
                                meta={
                                    "user_external_id": external_id or "",
                                    "mode_switched": bool(mode_switched),
                                    "speaker_name": (locals().get("real_name") or getattr(self, "current_user_identity", "") or ""),
                                    "speaker_role": (locals().get("voiceprint_result") or {}).get("role", ""),
                                    "voiceprint_confidence": float(locals().get("confidence") or 0.0),
                                    "voiceprint_speaker_id": (locals().get("voiceprint_result") or {}).get("speaker_id", "") or (locals().get("identified_user") or ""),
                                },
                            )
                        )
                    except Exception as e:
                        util.log(2, f"[History] write_failed error={e}")

                    return self.__process_response(text, username, interact)

                return cleaned_msg

            elif interact.interact_type == 2:  # 透传模式
                username = interact.data.get("user", "User")

                # 透传模式使用轻量处理
                uid = 1

                if interact.data.get("text"):
                    text = interact.data.get("text", "")
                    # 清理文本中的空字符
                    text = text.encode('utf-8', errors='ignore').decode('utf-8').replace('\x00', '')
                    # 使用 __process_response 处理响应，避免重复调用 say
                    return self.__process_response(text, username, interact)



        except Exception as e:
            util.log(1, f"[错误] 交互处理异常: {str(e)}")
            import traceback
            util.log(1, f"[错误] 异常堆栈: {traceback.format_exc()}")
            # 仅在 interact 有效时尝试播报错误提示
            if interact and hasattr(interact, 'data') and interact.data:
                self.say(interact, "抱歉，我这里遇到了一些问题。")
            return 'error'

    # 记录问答日志
    def write_to_file(self, path, filename, content):
        if not os.path.exists(path):
            os.makedirs(path)
        full_path = os.path.join(path, filename)
        with open(full_path, 'w', encoding='utf-8') as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

    # 触发语音交互
    def on_interact(self, interact: Interact):
        """处理交互事件。"""
        try:
            # 检查是否为自动播放服务触发
            is_triggered_by_auto_play = hasattr(interact, 'interleaver') and interact.interleaver == "auto_play"

            if not is_triggered_by_auto_play:
                # 重置自动播放计时器（仅非自动播放触发时）
                try:
                    reset_auto_play_timer()
                except Exception as e:
                    util.log(4, f"[调试] 重置计时器失败: {str(e)}")
            else:
                util.log(1, "[SmartSisi核心] on_interact 由自动播放触发，跳过 reset_auto_play_timer")

            # 处理交互
            result = self.__process_interact(interact)

            # 如果是开场白，优先播放
            if isinstance(result, dict) and result.get("opening_first"):
                opening_text = result.get("opening")
                if opening_text:
                    # 立即播放开场白
                    interact.data['tone'] = 'lyrical'  # 开场白使用抒情语气
                    self.say(interact, opening_text)

                    # 等待开场白播放完成
                    wait_start = time.time()
                    max_wait_time = 5.0  # 最长等待 5 秒
                    while self.speaking and (time.time() - wait_start < max_wait_time):
                        time.sleep(0.1)

                    # 超时仍在播放时，强制继续
                    if self.speaking and time.time() - wait_start >= max_wait_time:
                        util.log(1, "[警告] 等待播放完成超时，强制继续")
                        self.speaking = False

                    # 继续处理其他内容
                    scene_text = result.get("scene")
                    ending_text = result.get("ending")
                    if scene_text:
                        interact.data['tone'] = 'gentle'  # 场景描述使用温和语气
                        self.say(interact, scene_text)
                    if ending_text:
                        interact.data['tone'] = 'gentle'  # 结束语使用温和语气
                        self.say(interact, ending_text)

            return result
        except Exception as e:
            util.log(1, f"[错误] 交互处理异常: {str(e)}")
            return None

    # 发送情绪状态
    def __send_mood(self):
         while self.__running:
            time.sleep(3)
            if wsa_server.get_instance().is_connected("User"):
                if  self.old_mood != self.mood:
                    content = {'Topic': 'Unreal', 'Data': {'Key': 'mood', 'Value': self.mood}}
                    wsa_server.get_instance().add_cmd(content)
                    self.old_mood = self.mood

                    # 监控功能已迁移到独立监控系统

    # TODO: 评估是否重构该流程
    # 更新情绪
    def __update_mood(self, interact):
        try:
            # 获取消息内容
            text = interact.data.get('msg', '')
            if not text:
                return

            # 情绪识别能力已移除：保持中性情绪，不调用外部情感接口
            self.mood = 0.0

            # 记录情绪变化
            emoji_map = {
                (-1.0, -0.5): "angry",     # 生气
                (-0.5, -0.1): "lyrical",   # 抒情
                (-0.1, 0.1): "calm",       # 平静
                (0.1, 0.5): "assistant",   # 助手态
                (0.5, 1.0): "cheerful"     # 开心
            }

            # 找到对应情绪标签
            emoji = "gentle"  # 默认标签
            for (lower, upper), e in emoji_map.items():
                if lower <= self.mood < upper:
                    emoji = e
                    break

            util.log(1, f"[情绪] 标签={emoji} 数值={self.mood:.2f}")
        except Exception as e:
            util.log(1, f"更新情绪值时出错: {str(e)}")

    # 获取不同情绪对应的语音风格
    def __get_mood_voice(self):
        try:
            voice_type = cfg.config["attribute"]["voice"]
            if not voice_type:
                util.log(1, "[voice] style=gentle")
                return "gentle"

            mood = self.mood
            style = "gentle"

            if mood < -0.5:
                style = "angry"
                util.log(1, "[voice] style=angry")
            elif mood < -0.1:
                style = "lyrical"
                util.log(1, "[voice] style=lyrical")
            elif mood < 0.1:
                style = "calm"
                util.log(1, "[voice] style=calm")
            elif mood < 0.5:
                style = "assistant"
                util.log(1, "[voice] style=assistant")
            else:
                style = "cheerful"
                util.log(1, "[voice] style=cheerful")

            return style
        except Exception as e:
            util.log(1, "[voice] style=gentle (fallback)")
            return "gentle"

    # 语气标记过滤函数（当前保留原文）
    def __filter_mood_tags(self, text):
        # 当前不再过滤表情或语气符号，保留原文本
        print(f"[Core] 情绪标签过滤前文本: {text}")
        # 历史过滤逻辑保留说明：return text.replace(... )
        return text



    # 合成语音
    def say(self, interact, text):
        """
        使用语音合成器生成声音并播放。

        Args:
            interact: 交互对象
            text: 要合成的文本

        Returns:
            音频文件路径或 None
        """
        try:
            if not text:
                return None



            # 检查当前系统模式，避免重复 TTS 处理
            from llm.liusisi import get_current_system_mode
            current_mode = get_current_system_mode()
            if current_mode == "liuye":
                util.log(1, "[TTS-say] 柳叶模式统一走系统TTS（OPUS单通道）")

            # 检查文本是否已在上游处理过（如 agent_callback）
            already_processed = False
            if hasattr(interact, 'text_processed') and interact.text_processed:
                already_processed = True
                util.log(1, "[TTS] 文本已预处理，跳过过滤步骤")

            # 过滤思考标签，仅在未预处理时执行
            if not already_processed:
                original_length = len(text)

                # 过滤 <thinking> 标签内容
                import re
                filtered_text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)

                # 如果包含 <answer> 标签，仅保留标签内文本
                answer_match = re.search(r'<answer>(.*?)</answer>', filtered_text, flags=re.DOTALL)
                if answer_match:
                    filtered_text = answer_match.group(1).strip()

                # 若过滤后文本有变化，记录日志
                if len(filtered_text) != original_length:
                    util.log(1, f"[TTS] 过滤后文本长度: {len(filtered_text)}/{original_length}")
                    text = filtered_text

            util.log(1, f"[TTS] 生成语音: {text[:100]}...")

            # 文本分段，避免过长内容导致超时
            max_segment_length = 200  # 最大分段长度
            segments = []

            # 分段处理文本
            if len(text) > max_segment_length:
                # 按标点符号分段
                import re
                segments = re.split(r'([。！？.!?\n])', text)
                temp_segment = ""
                final_segments = []

                # 重组分段，确保每段不会过长
                for i in range(0, len(segments), 2):
                    if i+1 < len(segments):
                        current = segments[i] + segments[i+1]
                    else:
                        current = segments[i]

                    if len(temp_segment) + len(current) <= max_segment_length:
                        temp_segment += current
                    else:
                        if temp_segment:
                            final_segments.append(temp_segment)
                        temp_segment = current

                if temp_segment:
                    final_segments.append(temp_segment)

                segments = final_segments
            else:
                segments = [text]

            def _esp32_connected():
                try:
                    from esp32_liusisi.sisi.adapter import get_adapter_instance
                    adapter = get_adapter_instance()
                    return bool(adapter and getattr(adapter, 'clients', None) and len(adapter.clients) > 0)
                except Exception:
                    return False

            if not _esp32_connected():
                try:
                    from utils.pc_stream_queue import get_pc_stream_queue
                    from utils.emotion_trigger import EMOTION_TRIGGER_MAP
                    import re
                    import os as _os
                    import threading as _threading

                    def _split_text_for_tts(src):
                        if not src:
                            return []
                        if len(src) <= max_segment_length:
                            return [src]
                        parts = re.split('([\u3002\uff01\uff1f.!?\n])', src)
                        tmp = ''
                        out = []
                        for i in range(0, len(parts), 2):
                            current = parts[i]
                            if i + 1 < len(parts):
                                current = current + parts[i + 1]
                            if len(tmp) + len(current) <= max_segment_length:
                                tmp += current
                            else:
                                if tmp:
                                    out.append(tmp)
                                tmp = current
                        if tmp:
                            out.append(tmp)
                        return out

                    def _build_items(src_text):
                        pattern = re.compile(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}')
                        items = []
                        last = 0
                        for m in pattern.finditer(src_text):
                            before = src_text[last:m.start()]
                            for seg in _split_text_for_tts(before):
                                if seg.strip():
                                    items.append(('tts', seg))
                            name = m.group(1)
                            cfg = EMOTION_TRIGGER_MAP.get(name)
                            if cfg and cfg.get('type') in ['sound_effect', 'music_play']:
                                audio_file = cfg.get('audio_file')
                                if audio_file:
                                    if not _os.path.isabs(audio_file):
                                        audio_file = _os.path.abspath(audio_file)
                                    if _os.path.exists(audio_file):
                                        items.append(('audio', audio_file))
                            last = m.end()
                        tail = src_text[last:]
                        for seg in _split_text_for_tts(tail):
                            if seg.strip():
                                items.append(('tts', seg))
                        return items

                    pc_queue = get_pc_stream_queue()
                    items = _build_items(text)
                    if not items:
                        return None

                    max_prefetch = 2
                    sem = _threading.Semaphore(max_prefetch)
                    audio_files = []

                    def _run_tts(seg_text, sink):
                        sem.acquire()
                        try:
                            file_path = self.sp.to_sample(seg_text, pc_stream_sink=sink, skip_effects=True)
                            if file_path:
                                audio_files.append(file_path)
                        finally:
                            sem.release()
                            try:
                                sink.finish()
                            except Exception:
                                pass

                    def _run_audio(file_path, sink):
                        sem.acquire()
                        try:
                            pc_queue.stream_wav_file_to_sink(file_path, sink)
                        finally:
                            sem.release()
                            try:
                                sink.finish()
                            except Exception:
                                pass

                    self.speaking = True

                    threads = []
                    for item in items:
                        sink = pc_queue.enqueue_stream(label=item[0])
                        if item[0] == 'tts':
                            t = _threading.Thread(target=_run_tts, args=(item[1], sink), daemon=True)
                        else:
                            t = _threading.Thread(target=_run_audio, args=(item[1], sink), daemon=True)
                        t.start()
                        threads.append(t)

                    def _wait_idle():
                        pc_queue.wait_until_idle(timeout=30.0)
                        self.speaking = False

                    _threading.Thread(target=_wait_idle, daemon=True).start()

                    for t in threads:
                        t.join()

                    return audio_files[0] if audio_files else None
                except Exception as e:
                    util.log(2, f"[TTS] PC流式队列处理失败: {str(e)}")

            # 生成并处理每个分段
            audio_files = []
            for segment in segments:
                if not segment.strip():
                    continue

                # 生成音频
                audio_file = self.sp.to_sample(segment)
                if audio_file:
                    audio_files.append(audio_file)

                    # 处理音频输出
                    self.__process_output_audio(audio_file, interact, segment)

                    # say 方法生成的音频也通过统一播放线程转发到设备端
                    util.log(1, f"[TTS-say] 音频将通过播放线程统一发送到ESP32设备: {segment[:30]}...")

            return audio_files[0] if audio_files else None

        except Exception as e:
            util.log(2, f"[TTS] 生成语音失败: {str(e)}")
            import traceback
            util.log(2, f"[TTS] 详细错误: {traceback.format_exc()}")
            return None

    # 发送消息
    def send_message(self, text, interact=None):
        """发送文本消息。

        Args:
            text: 要发送的文本消息
            interact: 交互对象，为 None 时使用默认交互
        """
        try:
            # 直接使用统一的 process_audio_response
            username = "System"
            if interact and hasattr(interact, 'data') and interact.data.get("user"):
                username = interact.data.get("user")

            # 调用统一方法
            result = self.process_audio_response(
                text=text,
                username=username,
                interact=interact,
                priority=1  # 默认优先级
            )

            util.log(1, f"[系统] 消息已发送: {text}")
            return bool(result)
        except Exception as e:
            util.log(1, f"[错误] 消息发送失败: {str(e)}")
            return False

    # 下载 WAV
    def download_wav(self, url, save_directory, filename):
        try:
            # 发起 HTTP GET 请求获取 WAV 文件内容
            response = requests.get(url, stream=True)
            response.raise_for_status()  # 检查请求是否成功

            # 确保保存目录存在
            if not os.path.exists(save_directory):
                os.makedirs(save_directory)

            # 构建保存路径
            save_path = os.path.join(save_directory, filename)

            # 保存 WAV 文件内容到指定文件
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)

            return save_path
        except requests.exceptions.RequestException as e:
            print(f"[Error] Failed to download file: {e}")
            return None


    # 面板播放声音
    def __play_sound(self):
        """播放音频队列中的音频，支持优先级。"""
        while self.__running:
            try:
                # 仅在当前未播放音频时，从队列取出新音频
                if not self.speaking and not self.sound_query.empty():
                    # 限制单次处理数量，避免队列过度堆积
                    audio_items = []
                    max_items = 5  # 闄愬埗鏈€澶у鐞嗘暟閲?
                    count = 0
                    while not self.sound_query.empty() and count < max_items:
                        audio_items.append(self.sound_query.get())
                        count += 1

                    # 按优先级排序（数值越大优先级越高）
                    audio_items.sort(key=lambda x: x[0], reverse=True)

                    # 记录优先级信息用于调试
                    priorities = [item[0] for item in audio_items]
                    sources = ["Agent" if item[2] else "NLP" for item in audio_items]
                    util.log(1, f"[TTS] 音频队列排序后: priorities={priorities}, sources={sources}")

                    # 获取最高优先级和最低优先级
                    if not audio_items:
                        continue

                    highest_priority = audio_items[0][0]
                    lowest_priority = audio_items[-1][0] if len(audio_items) > 1 else highest_priority

                    # 检查队列中是否有“最终结果”优先级
                    # 不硬编码优先级值，按跨度比较判断
                    has_final_result = False
                    has_middle_result = False

                    # 计算优先级跨度
                    priority_span = highest_priority - lowest_priority

                    # 若优先级跨度>=2，说明队列中有不同阶段内容
                    if priority_span >= 2:
                        has_final_result = True  # 最高优先级视为最终结果
                        # 检查是否存在中间优先级
                        mid_priorities = [p for p in priorities if p != highest_priority and p != lowest_priority]
                        has_middle_result = len(mid_priorities) > 0

                    # 待播放音频项
                    to_play = []

                    # 若存在最终结果且跨度足够大，仅播放最终结果与起始阶段音频
                    if has_final_result and priority_span >= 2:
                        # 添加最高优先级项（最终结果）
                        to_play.append(audio_items[0])

                        # 若有起始阶段（最低优先级），可一起播放
                        if len(audio_items) > 1 and (highest_priority - lowest_priority) >= 2:
                            to_play.append(audio_items[-1])

                        # 输出详细日志
                        middle_count = len(audio_items) - len(to_play)
                        if middle_count > 0:
                            util.log(1, f"[TTS] 检测到最终结果（priority={highest_priority}），跳过{middle_count}个中间结果，播放{len(to_play)}个音频")
                    else:
                        # 无明显最终结果时，播放全部音频
                        to_play = audio_items

                    # 按优先级顺序播放
                    for item in to_play:
                        # 兼容新旧格式：(priority, audio_path, is_agent, original_text, process_flag)
                        liuye_processed = False
                        if len(item) >= 5:
                            priority, audio_file, is_agent, original_text, process_flag = item
                            liuye_processed = (process_flag == "liuye_processed")
                        elif len(item) >= 4:
                            priority, audio_file, is_agent, original_text = item
                        else:
                            priority, audio_file, is_agent = item
                            original_text = f"优先级{priority}音频"  # 兼容旧格式
                        try:
                            # 设置说话状态
                            self.speaking = True

                            # 检查是否为音乐文件，需要触发音乐可视化链路
                            # 包含 music_ 或 random_generation_music 的文件视为音乐
                            is_music_file = audio_file and ('music_' in audio_file or 'random_generation_music' in audio_file)
                            
                            # Unified routing: output fan-out is handled in PCStreamQueue.
                            # Do not bypass queue with direct Android socket sending here.
                            if liuye_processed:
                                util.log(1, f"[TTS] liuye_processed skip_device_route: {original_text[:30]}...")

                            # 音乐播放前先启动实时音频分析
                            if is_music_file:
                                util.log(1, "[音乐] 检测到音乐文件，先启动音频分析再播放")

                            # 启动实时音频分析（播放前）
                            util.log(1, f"[TTS] 准备播放音频: {audio_file}, priority={priority}, source={'Agent' if is_agent else 'NLP'}")
                            if is_music_file:
                                try:
                                    from .realtime_audio_analyzer import RealtimeAudioAnalyzer

                                    util.log(1, f"[音乐分析] 启动实时分析: {audio_file}")

                                    # 创建实时分析器
                                    self.file_analyzer = RealtimeAudioAnalyzer(sample_rate=22050, chunk_size=1024)
                                    self.latest_spectrum_data = [128] * 8  # 初始化默认值

                                    # 设置频谱数据回调
                                    callback_count = 0
                                    def spectrum_callback(spectrum_data):
                                        nonlocal callback_count
                                        self.latest_spectrum_data = spectrum_data
                                        callback_count += 1
                                        # 每100次回调记录一次日志
                                        if callback_count % 100 == 0:
                                            util.log(1, f"[音乐分析] 收到实时频谱数据: {spectrum_data}")

                                    self.file_analyzer.set_spectrum_callback(spectrum_callback)

                                    # 加载音频文件
                                    util.log(1, f"[音乐分析] 正在加载音频文件: {audio_file}")
                                    if self.file_analyzer.load_audio_file(audio_file):
                                        util.log(1, "[音乐分析] 音频加载成功，启动实时分析")
                                        # 启动实时分析（与播放同步）
                                        if self.file_analyzer.start_realtime_analysis(update_interval=0.1):
                                            util.log(1, "[音乐分析] 实时分析已启动")
                                        else:
                                            util.log(2, "[音乐分析] 启动失败，回退到模拟数据")
                                            self.file_analyzer = None
                                    else:
                                        util.log(2, "[音乐分析] 音频加载失败，回退到模拟数据")
                                        self.file_analyzer = None

                                except Exception as e_file:
                                    util.log(2, f"[音乐分析] 实时分析失败: {str(e_file)}")
                                    import traceback
                                    util.log(2, f"[音乐分析] 详细错误: {traceback.format_exc()}")
                                    self.file_analyzer = None
                                    self.latest_spectrum_data = [128] * 8

                                util.log(1, f"[音乐可视化] 系统已启动: {audio_file}")

                            # 播放音频（音乐文件在后续播放循环中处理）
                            if not is_music_file:
                                # 非音乐文件统一走 PC 流式队列
                                try:
                                    from utils.pc_stream_queue import get_pc_stream_queue
                                    pc_queue = get_pc_stream_queue()
                                    pc_queue.enqueue_wav_file(audio_file, label="tts")
                                    pc_queue.wait_until_idle(timeout=60.0)
                                    util.log(1, f"[TTS] 非音乐文件播放完成: {audio_file}")
                                except Exception as e_play:
                                    util.log(2, f"[TTS] 非音乐文件播放失败: {str(e_play)}")
                            else:
                                util.log(1, f"[音乐] 文件将通过播放循环处理: {audio_file}")

                            # 等待播放完成，并在音乐播放期间发送频谱数据
                            if is_music_file:
                                # 启动音乐播放
                                util.log(1, f"[音乐] 开始播放音乐文件: {audio_file}")

                                try:
                                    pc_queue = None
                                    # 检查文件是否存在
                                    if not os.path.exists(audio_file):
                                        util.log(2, f"[音乐] 音频文件不存在: {audio_file}")
                                        return

                                    try:
                                        music_title = os.path.splitext(os.path.basename(audio_file))[0]
                                        wsa_server.get_web_instance().add_cmd({
                                            "music_event": "start",
                                            "music_file": audio_file,
                                            "music_title": music_title
                                        })
                                    except Exception:
                                        pass
                                    from utils.pc_stream_queue import get_pc_stream_queue
                                    pc_queue = get_pc_stream_queue()
                                    pc_queue.enqueue_wav_file(audio_file, label="music")
                                    util.log(1, f"[音乐] 音乐文件已加入PC流式队列: {audio_file}")

                                except Exception as e_play:
                                    util.log(2, f"[音乐] 播放失败: {str(e_play)}")
                                    return

                                # 音乐播放期间发送实时频谱数据到 SISIeyes
                                import random
                                frame_count = 0
                                util.log(1, "[音乐] 开始播放循环")

                                while pc_queue and not pc_queue.is_idle():
                                    time.sleep(0.02)  # 20ms 间隔
                                    frame_count += 1

                                    # 每帧发送频谱数据到两个设备
                                    if True:  # 不跳帧发送
                                        # 每200帧记录一次日志
                                        if frame_count % 200 == 0:
                                            util.log(1, f"[音乐] frame={frame_count} 发送频谱数据")

                                        try:
                                            from esp32_liusisi import esp32_bridge
                                            adapter_instance = getattr(esp32_bridge, 'adapter_instance', None)

                                            # print(f"[DEBUG] 音乐播放中，frame_count={frame_count}, adapter_exists={adapter_instance is not None}")

                                            if adapter_instance and hasattr(adapter_instance, 's3cam_sender'):
                                                # 获取真实音频文件频谱数据
                                                spectrum_data = None

                                                # 优先使用真实音频分析数据
                                                if hasattr(self, 'file_analyzer') and self.file_analyzer and self.file_analyzer.is_analyzing:
                                                    # 使用最新实时分析数据
                                                    spectrum_data = getattr(self, 'latest_spectrum_data', None)
                                                    if spectrum_data and len(spectrum_data) == 8:
                                                        pass
                                                    else:
                                                        util.log(2, f"[音乐] 实时频谱数据无效: {spectrum_data}")
                                                        spectrum_data = None

                                                # 若无真实数据，则使用模拟数据
                                                if spectrum_data is None:
                                                    current_time = time.time()

                                                    # 节拍模拟（120 BPM）
                                                    beat_time = (current_time * 2.0) % (60.0 / 120.0 * 4)  # 4拍循环
                                                    beat_phase = beat_time / (60.0 / 120.0 * 4) * 2 * math.pi

                                                    # 强拍和弱拍
                                                    strong_beat = abs(math.sin(beat_phase)) ** 2  # 强拍
                                                    weak_beat = abs(math.sin(beat_phase * 2)) ** 1.5  # 弱拍

                                                    # 旋律起伏
                                                    melody = 0.7 + 0.3 * math.sin(current_time * 0.1)

                                                    # 8频段音乐能量分布
                                                    base_levels = [20, 18, 15, 12, 10, 8, 5, 3]  # 基础强度
                                                    beat_impacts = [1.0, 0.8, 0.6, 0.4, 0.3, 0.2, 0.1, 0.05]  # 节拍冲击

                                                    spectrum_data = []
                                                    for i in range(8):
                                                        # 基础强度 + 节拍冲击 + 旋律变化 + 随机扰动
                                                        base = base_levels[i]
                                                        beat_effect = beat_impacts[i] * strong_beat * 200  # 节拍冲击增强
                                                        melody_effect = melody * 50  # 旋律变化增强
                                                        random_effect = (random.random() - 0.5) * 40  # 随机扰动增强

                                                        value = base + beat_effect + melody_effect + random_effect
                                                        spectrum_data.append(int(value))

                                                    util.log(1, f"[音乐] 使用模拟频谱数据: {spectrum_data}")

                                                # 确保数据在合理范围内（0~255）
                                                spectrum_data = [max(0, min(255, val)) for val in spectrum_data]

                                                # 同时发送到 SISIeyes 和 sisidesk
                                                adapter_instance.s3cam_sender.send_audio_spectrum_data(spectrum_data)

                                                # sisidesk 实时响应：使用加权平均聚焦中低频
                                                weights = [3, 2, 2, 1, 1, 0.5, 0.3, 0.2]  # 8频段权重
                                                weighted_sum = sum(spectrum_data[i] * weights[i] for i in range(8))
                                                total_weight = sum(weights)
                                                weighted_avg = int(weighted_sum / total_weight)
                                                # 映射到 0-255 范围，确保强度有明显变化
                                                enhanced_intensity = max(30, min(255, weighted_avg))
                                                sisidesk_success = adapter_instance.s3cam_sender.send_sisidesk_audio_data(enhanced_intensity, spectrum_data)

                                                # 每250帧记录一次日志
                                                if frame_count % 250 == 0:
                                                    util.log(1, f"[音乐] 已发送频谱数据到SISIeyes: {spectrum_data}")
                                                    if sisidesk_success:
                                                        print(f"[DEBUG] sisidesk实时发送成功，强度={enhanced_intensity}")
                                                    else:
                                                        print(f"[DEBUG] sisidesk发送失败，强度={enhanced_intensity}")

                                                # 每20帧打印一次 sisidesk 状态
                                                if frame_count % 20 == 0 and sisidesk_success:
                                                    print(f"[DEBUG] sisidesk实时: 强度={enhanced_intensity}(加权={weighted_avg}), 频谱={spectrum_data[:3]}...")

                                        except Exception as e_spectrum:
                                            # 静默处理频谱发送错误，不影响音乐播放
                                            pass

                                        except Exception as e_send:
                                            # 静默处理发送异常
                                            pass

                                    # 播放循环结束
                                util.log(1, f"[音乐] 播放循环结束，总帧数={frame_count}")

                            # 音乐播放结束时，停止文件分析并通知设备
                            if is_music_file:
                                try:
                                    wsa_server.get_web_instance().add_cmd({
                                        "music_event": "stop",
                                        "music_file": audio_file
                                    })
                                except Exception:
                                    pass

                                # 前端唱片机动效已移除，不再推送相关通知
                                util.log(1, "[音乐播放] 唱片机动效已移除，跳过通知")
                                
                                # 停止实时音频分析器
                                try:
                                    if hasattr(self, 'file_analyzer') and self.file_analyzer:
                                        self.file_analyzer.stop_analysis()
                                        util.log(1, "[音乐分析] 实时分析器已停止")
                                except Exception as e_stop:
                                    util.log(2, f"[音乐分析] 停止实时分析器失败: {str(e_stop)}")

                                util.log(1, "[音乐] 播放结束，停止可视化")

                                try:
                                    from esp32_liusisi import esp32_bridge
                                    adapter_instance = getattr(esp32_bridge, 'adapter_instance', None)

                                    if adapter_instance and hasattr(adapter_instance, 's3cam_integration'):
                                        # 停止 SISIeyes 音乐可视化
                                        adapter_instance.s3cam_integration.on_sisi_music_stop()
                                        util.log(1, "[音乐] 已通知SISIeyes停止音乐可视化")

                                        # 关闭 sisidesk LED
                                        if hasattr(adapter_instance, 's3cam_sender'):
                                            # 发送关闭指令
                                            import requests
                                            try:
                                                requests.post("http://172.20.10.5/api/led/off", timeout=2)
                                                util.log(1, "[音乐] 已关闭sisidesk LED音频可视化")
                                            except:
                                                pass

                                        # 音乐结束后触发 AUDIO_OFF 全局动作
                                        try:
                                            from utils.emotion_trigger import detect_and_trigger_emotions
                                            audio_off_text = "音乐结束{AUDIO_OFF}"
                                            detect_and_trigger_emotions(audio_off_text)
                                            util.log(1, "[QA音乐] 音乐结束动作已触发：{AUDIO_OFF}")
                                        except Exception as e:
                                            util.log(2, f"[QA音乐] {AUDIO_OFF}动作触发异常: {e}")

                                except Exception as e_stop:
                                    util.log(2, f"[音乐] 通知设备停止可视化失败: {str(e_stop)}")

                            # 清除说话状态
                            self.speaking = False

                            # 重置共享状态（基于音频类型）
                            is_auto_play_audio = (priority == 0)  # 浼樺厛绾?鏄嚜鍔ㄦ挱鏀?
                            if is_auto_play_audio:
                                with shared_state.auto_play_lock:
                                    shared_state.is_auto_playing = False
                                    # can_auto_play 鍦╝uto_play_loop涓鐞嗭紝杩欓噷涓嶉噸澶嶈缃?
                                util.log(1, "[TTS] 自动播放音频播放完成，已重置 is_auto_playing")
                            else:
                                util.log(1, "[TTS] 普通音频播放完成")

                            # 不额外延迟，直接进入下一轮循环

                        except Exception as e:
                            util.log(2, f"[TTS] 播放音频失败: {str(e)}")
                            self.speaking = False
                            
                            # 异常时也要重置共享状态
                            is_auto_play_audio = (priority == 0)
                            if is_auto_play_audio:
                                with shared_state.auto_play_lock:
                                    shared_state.is_auto_playing = False
                                    shared_state.can_auto_play = True
                            continue

                # 缩短循环间隔，提升响应速度
                time.sleep(0.01)

            except Exception as e:
                util.log(2, f"[TTS] 音频播放线程异常: {str(e)}")
                time.sleep(1)  # 发生错误时拉长等待，避免高频报错

    def __is_send_remote_device_audio(self, interact=None):
        target_user = None
        if interact is not None:
            try:
                target_user = interact.data.get("user")
            except Exception:
                target_user = None

        try:
            from utils.android_output_hub import get_android_output_hub

            return get_android_output_hub().has_output_device(target_user=target_user)
        except Exception:
            return False

    # 处理响应消息
    def __process_response(self, text, username, interact, frame=None):
        print(f"[Core] 处理响应文本: {text}")
        print(f"[Core] 用户名: {username}, 交互类型: {interact}")
        """处理响应消息"""
        try:
            if not text:
                util.log(1, "[错误] 响应文本为空")
                return None

            # 馃幍 鏂板锛氭娴嬪苟澶勭悊鐗规畩鎷彿鏍囪
            audio_trigger = None
            raw_text = text
            display_text = raw_text
            tts_text = raw_text
            
            # 馃敟 鍒犻櫎Core灞傜殑{}闊充箰鏍囪妫€娴?- NLP灞傚凡缁忓鐞嗕簡锛岄伩鍏嶉噸澶嶆挱鏀?
            # {}鏍囪鐢盢LP灞傜殑detect_and_trigger_emotions缁熶竴澶勭悊
            
            # 妫€娴嬬壒娈婃嫭鍙锋牸寮忥細鍙鐞哰RANDOM]锛屽叾浠栨柟鎷彿鐣欑粰emotion_trigger澶勭悊
            import re
            if re.search(r'\[RANDOM\]', raw_text):
                # 鍙鐞哰RANDOM]鏍囪锛岃皟鐢ㄩ殢鏈洪煶棰戦€夋嫨
                from llm.nlp_music import get_random_audio_file
                audio_trigger = get_random_audio_file()
                tts_text = re.sub(r'\[RANDOM\]', '', raw_text).strip()  # 鍙Щ闄RANDOM]鎷彿
                util.log(1, f"[特殊括号] 检测到[RANDOM]标记，随机选择音频: {audio_trigger}")

            # 妫€娴嬮煶涔愭枃浠惰矾寰勬牸寮忥細[鏂囦欢璺緞.mp3] 鎴?[鏂囦欢璺緞.wav]
            elif re.search(r'\[[^]]*\.(mp3|wav|flac|m4a)\]', raw_text, re.IGNORECASE):
                music_match = re.search(r'\[([^]]*\.(mp3|wav|flac|m4a))\]', raw_text, re.IGNORECASE)
                if music_match:
                    audio_trigger = music_match.group(1)  # 闊充箰鏂囦欢璺緞
                    tts_text = re.sub(r'\[[^]]*\.(mp3|wav|flac|m4a)\]', '', raw_text, flags=re.IGNORECASE).strip()
                    util.log(1, f"[特殊括号] 检测到音频文件路径: {audio_trigger}")
            
            # 妫€娴嬫棫鏍煎紡|RANDOM_AUDIO:璺緞锛堜繚鎸佸吋瀹规€э級
            elif "|RANDOM_AUDIO:" in raw_text:
                parts = raw_text.split("|RANDOM_AUDIO:", 1)
                if len(parts) == 2:
                    tts_text = parts[0].strip()  # 鐢ㄤ簬TTS鐨勬枃鏈?
                    audio_trigger = parts[1].strip()  # 闊抽鏂囦欢璺緞
                    util.log(1, f"[音频触发] 检测到旧格式标记: 文本='{display_text}', 音频='{audio_trigger}'")
            
            # 浣跨敤澶勭悊鍚庣殑TTS鏂囨湰杩涜鍚庣画澶勭悊锛屾樉绀烘枃鏈繚鐣欏師鏍?
            try:
                # 馃敡 TTS涓嶈鍑簕}鎺у埗鏍囪锛屼絾鍓嶇淇濈暀鍘熸枃鏄剧ず
                tts_text = re.sub(r'\{[A-Za-z0-9_\u4e00-\u9fff]+\}', '', tts_text).strip()
                tts_text = re.sub(r'\s+', ' ', tts_text).strip()
            except Exception:
                pass
            text = tts_text

            # 娓呯悊鏂囨湰涓殑鐗规畩瀛楃锛屼絾淇濈暀琛ㄦ儏绗﹀彿
            text = text.encode('utf-8').decode('utf-8').replace('\x00', '')
            text = text.strip()

            # 杩囨护鎺夊彲鑳藉瓨鍦ㄧ殑妯″瀷鏍囪
            text = self.__filter_model_tags(text)

            # 馃殌 绉婚櫎绠€鍗曚笂涓嬫枃缂撳瓨锛屼繚鎸佺郴缁熺畝娲?
            print(f"[SmartSisi核心] ✅ 响应处理完成")

            # 馃敟 **鏍规湰淇锛氭鏌ユ煶鍙舵ā寮忥紝閬垮厤閲嶅TTS澶勭悊**
            from llm.liusisi import get_current_system_mode
            current_mode = get_current_system_mode()

            # 馃敟 淇锛氭鏌ユ槸鍚﹀凡缁忔湁Agent鍥炶皟澶勭悊TTS锛岄伩鍏嶉噸澶?
            has_agent_callback = hasattr(interact, 'agent_callback_processed') and interact.agent_callback_processed

            # 澶勭悊璇煶鍚堟垚 - 鍙湪闈濶LP鍝嶅簲鏃剁敓鎴怲TS
            print(f"[Core] 🔰 开始TTS处理")
            audio_result = None  # 馃敟 淇锛氬垵濮嬪寲audio_result鍙橀噺
            
            if current_mode == "liuye":
                # 缁熶竴绛栫暐锛氭煶鍙舵ā寮忎篃璧扮郴缁烼TS锛圤PUS鍗曢€氳矾锛夛紝閬垮厤鏌冲彾渚TS澶辫触瀵艰嚧鏃犲０
                util.log(1, "[TTS] 柳叶模式统一走系统TTS（OPUS单通路）")
                print(f"[Core] 🚀 调用process_audio_response")
                audio_result = self.process_audio_response(
                    text=text,
                    username=username,
                    interact=interact,
                    priority=5,
                    display_text=display_text
                )
                print(f"[Core] ✅ TTS处理完成: {audio_result}")
            elif has_agent_callback:
                print(f"[Core] 🔥 检测到Agent回调已处理TTS，跳过重复处理")
            elif (config_util.config["interact"]["playSound"] or wsa_server.get_web_instance().is_connected(username) or self.__is_send_remote_device_audio(interact)) and not getattr(interact, 'nlp_processed', False):
                print(f"[Core] 🚀 调用process_audio_response")
                # **淇锛氫娇鐢ㄧ粺涓€鐨刾rocess_audio_response鏂规硶锛岀‘淇滶SP32璁惧閫氱煡**
                audio_result = self.process_audio_response(
                    text=text,
                    username=username,
                    interact=interact,
                    priority=5,  # 馃敟 NLP蹇€熷洖澶嶆渶楂樹紭鍏堢骇锛岀‘淇濆厛鎾斁
                    display_text=display_text
                )
                print(f"[Core] ✅ TTS处理完成: {audio_result}")
            else:
                print(f"[Core] ⏭️ 跳过TTS处理")
                
                # 馃幍 闊充箰鏂囦欢涔熻蛋鐩村彂ESP32妯″紡
                if audio_trigger and os.path.exists(audio_trigger):
                    util.log(1, f"[音频触发] 直发音乐文件到ESP32: {audio_trigger}")

                    # 鐩村彂闊充箰鏂囦欢鍒癊SP32璁惧
                    if self.sp._check_esp32_connection():
                        music_result = self.sp._send_music_file_direct(audio_trigger)
                        if music_result:
                            util.log(1, f"[音频触发] ✅ 音乐文件直发成功")
                        else:
                            util.log(2, f"[音频触发] ❌ 音乐文件直发失败")
                    else:
                        util.log(2, f"[音频触发] 无ESP32设备，音乐不可用")
                elif audio_trigger:
                    util.log(2, f"[音频触发] 音频文件不存在: {audio_trigger}")
                
                if audio_result:
                    return text

            return text

        except Exception as e:
            util.log(1, f"[错误] 响应处理异常: {str(e)}")
            import traceback
            util.log(1, traceback.format_exc())
            return None

    # 杈撳嚭闊抽澶勭悊
    def __process_output_audio(self, file_url, interact, text):
        """澶勭悊闊抽杈撳嚭"""
        try:
            # 1. 鍩烘湰妫€鏌?
            if not os.path.exists(file_url):
                util.log(1, f"[错误] 音频文件不存在: {file_url}")
                return

            # 2. 妫€鏌ユ槸鍚︽槸寮€鍦虹櫧
            is_opening = False
            for command_type, statements in COMMAND_TEMPLATES.items():
                if isinstance(statements, list):
                    if any(text.startswith(statement) for statement in statements):
                        is_opening = True
                        break
                elif isinstance(statements, dict):
                    for scene_statements in statements.values():
                        if any(text.startswith(statement) for statement in scene_statements):
                            is_opening = True
                            break

            # 3. 澶勭悊寮€鍦虹櫧缂撳瓨
            if is_opening:
                cache_dir = './samples'
                if not os.path.exists(cache_dir):
                    os.makedirs(cache_dir)

                cache_file = os.path.join(cache_dir, f'opening_{hash(text)}_opening.wav')
                util.log(1, f"[Debug] 开场白缓存文件: {cache_file}")

                if os.path.exists(cache_file):
                    util.log(1, f"[Debug] 使用开场白缓存: {cache_file}")
                    file_url = cache_file
                else:
                    try:
                        import shutil
                        shutil.copy2(file_url, cache_file)
                        util.log(1, f"[Debug] 创建开场白缓存: {cache_file}")
                        file_url = cache_file
                    except Exception as e:
                        util.log(1, f"[错误] 创建开场白缓存失败: {str(e)}")

            # 4. 璁＄畻闊抽闀垮害锛堜粎鐢ㄤ簬璁板綍锛屼笉鍐嶇敤浜庨槦鍒楀厓绱狅級
            try:
                audio = AudioSegment.from_wav(file_url)
                audio_length = len(audio) / 1000.0
                util.log(1, f"[Debug] 音频长度: {audio_length}秒")
            except Exception as e:
                audio_length = 3.0
                util.log(1, f"[Debug] 音频长度估算: {audio_length}秒(计算失败: {str(e)})")

            # 5. 璁剧疆浼樺厛绾?
            # 纭畾鏄惁涓鸿嚜鍔ㄦ挱鏀?
            is_auto_play = getattr(interact, 'interleaver', None) == 'auto_play'
            # 纭畾浼樺厛绾?- 寮€鍦虹櫧楂樹紭鍏堢骇锛岃嚜鍔ㄦ挱鏀句綆浼樺厛绾?
            priority = 0  # 榛樿鏈€浣庝紭鍏堢骇
            if is_opening:
                priority = 2  # 寮€鍦虹櫧浣跨敤楂樹紭鍏堢骇
            elif not is_auto_play:
                priority = 1  # 鏅€氬唴瀹逛娇鐢ㄦ爣鍑嗕紭鍏堢骇

            # 纭畾鏄惁涓篴gent鍝嶅簲
            is_agent = getattr(interact, 'interleaver', None) == 'agent_callback'



            # 6. 娣诲姞鍒版挱鏀鹃槦鍒?- 浣跨敤涓巇o_tts鐩稿悓鐨勬牸寮忥細(priority, file_url, is_agent)
            self.sound_query.put((priority, file_url, is_agent))
            util.log(1, f"[TTS] 音频已添加到队列: {file_url}, 优先级: {priority}, 来源: {'Agent' if is_agent else 'NLP'}")

            # 7. 鏇存柊鐘舵€?- 淇锛氫笉瑕佽缃畇elf.speaking闃绘鎾斁绾跨▼
            # 绉婚櫎 self.speaking = True锛岄伩鍏嶉樆姝㈡挱鏀剧嚎绋嬪伐浣?
            if is_auto_play:
                shared_state.can_auto_play = False
                shared_state.is_auto_playing = True

        except Exception as e:
            util.log(1, f"[错误] 音频处理失败: {str(e)}")
            import traceback
            util.log(1, f"[错误] 异常堆栈: {traceback.format_exc()}")

            # 閲嶇疆鐘舵€?
            self.speaking = False
            if is_auto_play:
                with shared_state.auto_play_lock:
                    shared_state.is_auto_playing = False
                    shared_state.can_auto_play = True
                    util.log(1, "[自动播放] 紧急状态重置: is_auto_playing=False, can_auto_play=True")

    # 鍚姩鏍稿績鏈嶅姟
    def start(self):
        """鍚姩鏍稿績鏈嶅姟"""
        # 鍙惎鍔ㄦ儏缁彂閫佺嚎绋嬶紝鎾斁绾跨▼宸插湪鍒濆鍖栨椂鍚姩
        threading.Timer(0.0, self.__send_mood).start()

    # 鍋滄鏍稿績鏈嶅姟
    def stop(self):
        self.__running = False
        self.speaking = False
        self.sp.close()
        wsa_server.get_web_instance().add_cmd({"panelMsg": "", "agent_status": "idle"})
        content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': ""}}
        wsa_server.get_instance().add_cmd(content)

    def stop_speaking(self):
        """鍋滄褰撳墠璇磋瘽/鎾斁浠诲姟锛屼笉鍏抽棴鏍稿績鏈嶅姟銆?"""
        try:
            util.log(1, "[ESP32 Abort] stop_speaking requested")
            self._stop_current_tasks()
        except Exception as e:
            util.log(2, f"[ESP32 Abort] stop_speaking failed: {str(e)}")
            # 淇濆簳锛氳嚦灏戞竻鐞嗙姸鎬侊紝閬垮厤涓婂眰寮傚父瀵艰嚧杩炴帴鏂紑
            self.speaking = False
            self.chatting = False

    def _stop_current_tasks(self):
        """鍋滄褰撳墠浠诲姟"""
        try:
            util.log(1, f"[鏅鸿兘鎵撴柇] 鍋滄褰撳墠浠诲姟")

            # 鍋滄褰撳墠璇磋瘽
            self.speaking = False

            # 鍋滄褰撳墠澶勭悊
            self.chatting = False

            # 娓呯┖闊抽闃熷垪
            if hasattr(self, 'sound_query'):
                while not self.sound_query.empty():
                    try:
                        self.sound_query.get_nowait()
                    except:
                        break

            # 关键修复：清空 ESP32 设备音频队列（打断残留音频）
            try:
                from esp32_liusisi.sisi_audio_output import AudioOutputManager
                audio_manager = AudioOutputManager.get_instance()
                if audio_manager:
                    audio_manager.clear_queues()
                    util.log(1, "[智能打断] ✅ 已清空ESP32设备音频队列")
            except Exception as e:
                util.log(2, f"[智能打断] 清空ESP32队列失败: {str(e)}")

        except Exception as e:
            util.log(2, f"[智能打断] 停止任务异常: {str(e)}")

    def _execute_interrupt_function(self, function_name):
        """执行打断指定的函数。"""
        try:
            util.log(1, f"[智能打断] 执行函数: {function_name}")

            if function_name == "stop_music":
                from core.unified_system_controller import get_unified_controller
                get_unified_controller().stop_music()
                util.log(1, "[智能打断] 已停止音乐")

            elif function_name == "change_music":
                # 鎹㈡瓕 - 鍏堝仠姝㈠啀璋冪敤闊充箰鎺у埗
                from core.unified_system_controller import get_unified_controller
                get_unified_controller().stop_music()
                self._call_motor_control_script()
                util.log(1, "[智能打断] 已换歌")

            elif function_name == "motor_control":
                # 鐩存帴璋冪敤闊充箰鎺у埗
                self._call_motor_control_script()
                util.log(1, "[智能打断] 已调用音乐控制")

        except Exception as e:
            util.log(2, f"[智能打断] 执行函数异常: {str(e)}")

    def _call_motor_control_script(self):
        """调用音乐控制脚本。"""
        try:
            import subprocess
            import os

            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qa", "motor_control.py")
            if os.path.exists(script_path):
                subprocess.run(["python", script_path], check=False)
                util.log(1, "[智能打断] 音乐控制脚本已调用")
            else:
                util.log(2, f"[智能打断] 音乐控制脚本不存在: {script_path}")
        except Exception as e:
            util.log(2, f"[智能打断] 调用音乐控制脚本异常: {str(e)}")

    def _is_sisi_running(self):
        """检测 SmartSisi 是否正在运行任何活动。"""
        try:
            # 妫€鏌ヤ换浣曟椿鍔ㄧ姸鎬?
            is_running = (
                self.speaking or  # TTS璇磋瘽
                self.chatting or  # NLP澶勭悊
                (hasattr(self, 'sound_query') and not self.sound_query.empty())  # 闊抽闃熷垪
            )

            # 妫€鏌gent绯荤粺锛堝氨鏄疞G绯荤粺锛?
            try:
                # Agent绯荤粺杩愯鐘舵€侀€氳繃chatting鍒ゆ柇
                if self.chatting:
                    is_running = True
            except:
                pass

            # 妫€鏌gent宸ュ叿
            try:
                from llm.transit_station import get_transit_station
                transit = get_transit_station()
                if hasattr(transit, 'intermediate_states') and transit.intermediate_states:
                    is_running = True
            except:
                pass

            # 妫€鏌2A璁㈤槄绯荤粺锛堢湡姝ｇ殑娲诲姩妫€娴嬶級
            try:
                from llm.agent.a2a_notification import get_tool_manager
                manager = get_tool_manager()

                # 馃敡 淇锛氭鏌ユ槸鍚︽湁鐪熸鐨勬椿鍔紝涓嶄粎浠呮槸_running鐘舵€?
                has_real_activity = False

                # 妫€鏌ユ槸鍚︽湁娲昏穬鐨勮闃咃紙鐪熸鐨勮闃咃紝涓嶆槸绌虹殑锛?
                if hasattr(manager, 'subscriptions') and manager.subscriptions:
                    for tool_name, subs in manager.subscriptions.items():
                        if subs:  # 鏈夊疄闄呰闃?
                            has_real_activity = True
                            break

                # 妫€鏌ユ槸鍚︽湁寰呭鐞嗙殑浠诲姟
                if hasattr(manager, 'task_queue') and not manager.task_queue.empty():
                    has_real_activity = True

                if has_real_activity:
                    is_running = True
            except:
                pass

            return is_running

        except Exception as e:
            util.log(2, f"[智能打断] 检测Sisi运行状态异常: {str(e)}")
            return False

    def _stop_all_systems(self):
        """Stop all systems (unified path)."""
        try:
            util.log(1, "[interrupt] stop_all_systems")
            from core.unified_system_controller import get_unified_controller
            get_unified_controller().stop_all_activities()
        except Exception as e:
            util.log(2, f"[interrupt] stop_all_systems failed: {str(e)}")

    def pre_check_command(self, text):
        """
        命令预检测，识别是否包含特定命令关键词。

        Args:
            text (str): 用户输入文本。

        Returns:
            tuple: (命令类型, 预处理后的文本)
        """
        # 浣跨敤缁熶竴鐨勫懡浠ゆ娴嬫ā鍧?
        from ai_module.commands.long_term_commands import check_command_trigger

        # 璁板綍鍘熷鏂囨湰
        original_text = text

        # 浣跨敤缁熶竴鐨勫懡浠ゆ娴嬪嚱鏁?
        command_type = check_command_trigger(text)
        if command_type == "鐩戞帶":
            # 瑙嗚/鐩戞帶鑳藉姏宸蹭笅绾匡紝蹇界暐璇ュ懡浠?
            command_type = None

        # 娌℃湁璇嗗埆鍒扮壒娈婂懡浠わ紝杩斿洖鍘熷鏂囨湰
        return None, original_text

    def __filter_model_tags(self, text):
        """过滤模型标签，确保 TTS 不会读出这些标记。"""
        if not text:
            return text

        # 瀹氫箟闇€瑕佽繃婊ょ殑妯″瀷鏍囪
        model_tags = [
            "[NLP-7B]", "[Agent-O3]", "[Agent-O3閿欒]",
            "[LLM]", "[Agent]", "[GPT]", "[AI]"
        ]

        # 绉婚櫎鎵€鏈夋ā鍨嬫爣璁?
        cleaned_text = text
        for tag in model_tags:
            cleaned_text = cleaned_text.replace(tag, "").strip()

        # 璁板綍鏄惁杩涜浜嗚繃婊?
        if cleaned_text != text:
            util.log(1, f"[过滤] 移除了模型标记: {text[:30]} -> {cleaned_text[:30]}")

        return cleaned_text

    def agent_callback(self, agent_result, agent_style, is_intermediate=False, metadata=None):
        """处理 Agent 结果回调。

        Args:
            agent_result: Agent 处理结果。
            agent_style: 语音风格。
            is_intermediate: 是否为中间状态。
            metadata: 包含节点与状态信息的元数据。
        """
        # 璁板綍璋冭瘯淇℃伅
        util.log(1, f"[SmartSisi核心] 收到回调: is_intermediate={is_intermediate}, metadata={metadata}")

        # 鍒濆鍖栭樁娈垫爣璇?
        is_start_phase = False   # 寮€濮嬮樁娈?
        is_middle_phase = False  # 涓棿闃舵
        is_final_phase = False   # 鏈€缁堥樁娈?
        is_notification_phase = False  # 馃敟 淇锛氬垵濮嬪寲璁㈤槄绔欒ˉ鍏呬俊鎭樁娈垫爣璇?

        # 浠巑etadata涓幏鍙栬妭鐐圭被鍨嬪拰鐘舵€佷俊鎭?
        if metadata:
            # 鎻愬彇鑺傜偣绫诲瀷鍜岀姸鎬?
            node_type = metadata.get('node_type', '')
            state = metadata.get('state', '')
            phase = metadata.get('phase', '')
            source_tool = metadata.get('source_tool', '')
            is_tool_notification = metadata.get('is_tool_notification', False)

            # 馃敟 淇锛氬垹闄ゅ己鍒惰缃伐鍏烽€氱煡涓篺inal闃舵鐨勯€昏緫锛岃phase='notification'姝ｅ父澶勭悊
            # 娉ㄩ噴鎺夊師鏉ョ殑寮哄埗璁剧疆閫昏緫
            # if is_tool_notification and source_tool:
            #     is_final_phase = True
            #     util.log(1, f"[SmartSisi核心] 检测到工具二次返回结果: {source_tool}")

            # 浠嶭angGraph鑺傜偣绫诲瀷涓瘑鍒樁娈?
            if node_type:
                is_start_phase = node_type in ['agent', 'thinking', 'input_received']
                is_middle_phase = node_type in ['tool_calling', 'tool_execution', 'observation', 'tool_result']
                is_final_phase = node_type in ['output', 'final_response', 'complete', 'end']

            # 浠嶢2A鐘舵€佷腑璇嗗埆闃舵
            elif state:
                if state in ['submitted', 'accepted', 'working']:
                    is_start_phase = True
                elif state in ['input-required', 'tool_execution']:
                    is_middle_phase = True
                elif state in ['completed', 'canceled', 'failed']:
                    is_final_phase = True

            # 鐩存帴浠庨樁娈垫爣璇嗕腑鑾峰彇
            elif phase:
                is_start_phase = phase == 'start'
                is_middle_phase = phase == 'middle'
                is_final_phase = phase == 'final'
                is_notification_phase = phase == 'notification'  # 馃敟 淇锛氬崟鐙瘑鍒闃呯珯琛ュ厖淇℃伅
                is_error_phase = phase == 'error'  # 馃敟 鏂板锛氶敊璇樁娈佃瘑鍒?

        # 鏍规嵁闃舵璁剧疆浼樺厛绾?- 纭繚璁㈤槄绔欒ˉ鍏呬俊鎭湪LG绯荤粺final涔嬪悗
        priority = 1  # 榛樿浼樺厛绾?
        if is_start_phase:
            priority = 1  # 寮€濮嬮樁娈典紭鍏堢骇杈冧綆
        elif is_middle_phase:
            priority = 2  # 涓棿闃舵浼樺厛绾т腑绛?
        elif is_final_phase:
            priority = 3  # LG绯荤粺鏈€缁堥樁娈典紭鍏堢骇鏈€楂?
        elif is_notification_phase:
            priority = 2  # 馃敟 淇锛氳闃呯珯琛ュ厖淇℃伅浼樺厛绾ф洿浣庯紙鏁板瓧瓒婂ぇ浼樺厛绾ц秺楂橈級锛岀‘淇濆湪LG绯荤粺final涔嬪悗鎾斁
        elif is_error_phase:
            priority = 4  # 馃敟 鏂板锛氶敊璇樁娈典紭鍏堢骇鏈€楂橈紝纭繚閿欒淇℃伅鍙婃椂鎾斁

        # 确定阶段类型用于日志记录
        phase_type = "未知"
        if is_start_phase:
            phase_type = "开始阶段"
        elif is_middle_phase:
            phase_type = "中间阶段"
        elif is_final_phase:
            phase_type = "最终阶段"
        elif is_notification_phase:
            phase_type = "订阅站补充信息"
        elif is_error_phase:
            phase_type = "错误阶段"

        # 记录状态类型
        util.log(1, f"[SmartSisi核心] 阶段识别: {phase_type}, 设置优先级: {priority}")

        # 检查 agent_result 是否为 None
        if agent_result is None:
            util.log(1, "[SmartSisi核心] 警告: 收到None类型的结果")
            agent_result = ""

        # 记录接收结果
        util.log(1, f"[SmartSisi核心] {phase_type}内容: {agent_result[:100]}...")

        # 缁熶竴澶勭悊鏂囨湰 - 鎻愬彇<answer>鏍囩鍐呭
        original_text = agent_result
        processed_text = agent_result

        # 过滤<thinking>标签内容
        import re
        processed_text = re.sub(r'<thinking>.*?</thinking>', '', processed_text, flags=re.DOTALL)

        # 如果有<answer>标签，只保留标签内内容
        answer_match = re.search(r'<answer>(.*?)</answer>', processed_text, flags=re.DOTALL)
        if answer_match:
            processed_text = answer_match.group(1).strip()
            util.log(1, f"[SmartSisi核心] 提取<answer>标签内容: {processed_text[:100]}...")

        # 存储结果到数据库
        username = "User"  # 用户名
        uid = 1            # 鐢ㄦ埛ID

        # 馃 绯荤粺鍥炲宸查€氳繃Mem0璁板繂绯荤粺澶勭悊锛屾棤闇€浼犵粺鏁版嵁搴撳瓨鍌?
        content_id = 0

        # 鍙戦€佸鐞嗗悗鐨勬枃鏈埌鍓嶇鏄剧ず
        if wsa_server.get_web_instance().is_connected("User"):
            try:
                from llm.liusisi import get_current_system_mode
                reply_type = (get_current_system_mode() or "sisi").strip().lower()
                if reply_type not in ("sisi", "liuye"):
                    reply_type = "sisi"
            except Exception:
                reply_type = "sisi"
            response_msg = {
                "panelReply": {
                    "type": reply_type,
                    "content": processed_text,  # 浣跨敤澶勭悊鍚庣殑鏂囨湰
                    "username": username,
                    "uid": uid,
                    "id": content_id,
                    "is_intermediate": is_intermediate,  # 淇濈暀鏍囪浠ヤ究鍓嶇鍖哄垎鏄剧ず
                    "phase": phase_type  # 娣诲姞闃舵鏍囪瘑锛屼究浜庡墠绔鐞?
                },
                "Username": username
            }
            wsa_server.get_web_instance().add_cmd(response_msg)

        # 鍙鐗瑰畾闃舵杩涜TTS
        should_tts = is_final_phase or is_start_phase or is_middle_phase or is_notification_phase or is_error_phase  # 馃敟 淇锛氬寘鍚闃呯珯琛ュ厖淇℃伅鍜岄敊璇樁娈?

        # 执行TTS（使用处理后的文本）
        if should_tts:
            # 创建一个临时交互对象，用于标记文本已处理
            from core.interact import Interact
            temp_interact = Interact(
                interleaver="agent_callback",
                interact_type=2,  # 透传模式
                data={"user": username, "text": processed_text}
            )

            # 标记文本已处理，避免在say方法中重复过滤
            temp_interact.text_processed = True

            # 修复：标记Agent回调已处理TTS，避免重复
            temp_interact.agent_callback_processed = True

            # 使用阶段计算出的优先级执行TTS
            narration_audio_file = self.do_tts(
                processed_text,
                agent_style,
                is_agent=True,
                priority=priority,
                interact=temp_interact,
            )
            util.log(1, f"[SmartSisi核心] 执行{phase_type}的TTS，优先级: {priority}")

            # --- BEGIN MODIFICATION ---
            # 澶勭悊闊充箰宸ュ叿鐨勬渶缁堢粨鏋滐紝纭繚鏃佺櫧涔嬪悗鎾斁闊充箰
            # 馃敟 淇锛歮usic_tool鐨勭粨鏋滃湪notification闃舵锛屼笉鏄痜inal闃舵
            if (is_final_phase or is_notification_phase) and metadata and metadata.get("source_tool") == "music_tool":
                music_file_to_play = metadata.get("music_file_path")
                if music_file_to_play and os.path.exists(music_file_to_play):
                    util.log(1, f"[SmartSisi核心] 检测到 music_tool 的最终结果，准备播放关联音乐文件: {music_file_to_play}")
                    
                    # 馃敟 淇锛氶煶涔愭枃浠朵娇鐢ㄦ瘮鏃佺櫧鏇翠綆鐨勪紭鍏堢骇锛岀‘淇濆湪鏃佺櫧涔嬪悗鎾斁
                    # 鏃佺櫧浼樺厛绾ф槸3锛岄煶涔愪紭鍏堢骇璁句负2锛岃繖鏍烽煶涔愪細鍦ㄦ梺鐧戒箣鍚庢挱鏀?
                    music_priority = 2
                    
                    # 娣诲姞闊充箰鍒版挱鏀鹃槦鍒楋紝鍖呭惈绌烘枃鏈紙闊充箰鏂囦欢涓嶉渶瑕佹枃鏈級
                    self.sound_query.put((music_priority, music_file_to_play, True, ""))
                    util.log(1, f"[SmartSisi核心-音乐] 音乐已添加到播放队列: {music_file_to_play}, 优先级: {music_priority}")
                    
                    # 馃敟 鍏抽敭淇锛氶煶涔愭枃浠朵笉绔嬪嵆閫氱煡ESP32锛岃€屾槸鍦ㄩ煶棰戞挱鏀剧嚎绋嬩腑澶勭悊
                    # 閫氳繃闊抽鎾斁闃熷垪鐨勯『搴忔潵纭繚姝ｇ‘鐨勬挱鏀炬椂搴?
                    # 鍥犳杩欓噷鍒犻櫎绔嬪嵆閫氱煡ESP32鐨勪唬鐮侊紝鏀逛负閫氳繃__play_sound鏂规硶澶勭悊
                    util.log(1, "[SmartSisi核心-音乐] ✅ 音乐文件已加入播放队列，将按优先级顺序播放")
                elif music_file_to_play:
                    util.log(2, f"[SmartSisi核心-音乐] music_tool 提供了音乐文件路径，但文件不存在: {music_file_to_play}")
                else:
                    util.log(2, "[SmartSisi核心-音乐] music_tool 的最终结果元数据中缺少 music_file_path")
            # --- END MODIFICATION ---
        else:
            util.log(1, f"[SmartSisi核心] 跳过非关键阶段的TTS: {processed_text[:30]}...")

        # 鍙湁鍦ㄦ渶缁堢粨鏋滄椂鎵嶉噸缃甤hatting鐘舵€?
        if is_final_phase:
            self.chatting = False



            # 馃毃 淇锛歛gent_callback涓病鏈塱nteract鍙橀噺锛屼娇鐢╰emp_interact
            # 鏀堕泦鐢ㄦ埛鐗瑰緛鏁版嵁
            user_characteristics = self._analyze_user_characteristics(temp_interact, processed_text)

            # 璁板綍鍒扮洃鎺х郴缁?
            monitor_data = {
                "timestamp": time.time(),
                "interaction_type": "agent_callback",
                "user_input": processed_text,
                "user_name": temp_interact.data.get("user", "Unknown"),
                "user_characteristics": user_characteristics,
                "system_state": {
                    "mood": getattr(self, 'mood', 'normal'),
                    "speaking": self.speaking,
                    "chatting": getattr(self, 'chatting', False)
                }
            }

            # 馃敡 鐩戞帶鍔熻兘宸茶縼绉诲埌鐙珛鐩戞帶绯荤粺

    def _analyze_user_characteristics(self, interact, user_input):
        """分析用户特征。"""
        characteristics = {}

        try:
            # 1. 璇煶鐗圭偣鍒嗘瀽
            if interact.interact_type == 1:  # 璇煶杈撳叆
                characteristics["input_method"] = "voice"
                characteristics["text_length"] = len(user_input)
                characteristics["has_punctuation"] = any(p in user_input for p in "。，！？.,:;!?")

            # 2. 鎯呯华鐘舵€佸垎鏋愶紙鍩轰簬鐜版湁鐨勬儏缁郴缁燂級
            if hasattr(self, 'mood'):
                characteristics["current_mood"] = self.mood

            # 3. 浜や簰妯″紡鍒嗘瀽
            characteristics["interaction_frequency"] = self._calculate_interaction_frequency()
            characteristics["session_duration"] = self._calculate_session_duration()

            # 4. 鍐呭鐗瑰緛鍒嗘瀽
            characteristics["question_type"] = self._classify_question_type(user_input)
            characteristics["complexity_level"] = self._assess_complexity(user_input)

            # 5. 鏃堕棿鐗瑰緛
            current_hour = time.localtime().tm_hour
            characteristics["time_of_day"] = self._classify_time_period(current_hour)

            return characteristics

        except Exception as e:
            util.log(2, f"[SmartSisi监控] 用户特征分析失败: {e}")
            return {}

    # 杈呭姪鏂规硶
    def _calculate_interaction_frequency(self):
        """璁＄畻浜や簰棰戠巼"""
        # 杩欓噷鍙互鍩轰簬鍘嗗彶浜や簰璁板綍璁＄畻
        return 1.0  # 绠€鍖栧疄鐜?

    def _calculate_session_duration(self):
        """璁＄畻浼氳瘽鎸佺画鏃堕棿"""
        # 鍩轰簬浼氳瘽寮€濮嬫椂闂磋绠?
        return time.time() - getattr(self, '_session_start_time', time.time())

    def _assess_complexity(self, text):
        """璇勪及鏂囨湰澶嶆潅搴?"""
        # 绠€鍖栧疄鐜?
        return len(text.split()) / 10.0

    def _classify_time_period(self, hour):
        """鍒嗙被鏃堕棿娈?"""
        if 6 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"

    def _classify_question_type(self, text):
        """鍒嗙被闂绫诲瀷"""
        if "?" in text or "？" in text:
            return "question"
        elif any(word in text for word in ["请", "帮", "能否", "可以"]):
            return "request"
        else:
            return "statement"

    def _assess_complexity(self, text):
        """璇勪及澶嶆潅搴?"""
        word_count = len(text.split())
        if word_count < 5:
            return "simple"
        elif word_count < 15:
            return "medium"
        else:
            return "complex"

    def _classify_time_period(self, hour):
        """鍒嗙被鏃堕棿娈?"""
        if 6 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"

def start_auto_play_service():
    """启动自动播放服务"""
    global auto_play_thread, auto_play_running

    if auto_play_thread and auto_play_thread.is_alive():
        util.log(1, "[自动播放] 服务已在运行中")
        return

    # 检查配置：优先使用 auto_play 配置，否则使用 source 配置
    auto_play_config = config_util.config.get("auto_play", {})
    source_config = config_util.config.get("source", {})

    enabled = auto_play_config.get("enabled", source_config.get("automatic_player_status", True))
    url = auto_play_config.get("url", source_config.get("automatic_player_url", ""))

    # 读取间隔配置，默认 600 秒（10 分钟）
    try:
        if config_util.system_config and config_util.system_config.has_section("auto_play"):
            interval = int(config_util.system_config.get("auto_play", "interval", fallback="600"))
        else:
            interval = 600
    except Exception:
        interval = 600

    util.log(1, f"[自动播放] 配置检查 enabled={enabled}, url={url}")

    if not enabled:
        util.log(1, "[自动播放] 服务已禁用")
        return

    if not url:
        # 使用默认 URL
        url = "http://127.0.0.1:6000/get_auto_play_item"
        util.log(1, f"[自动播放] 未配置URL，使用默认值: {url}")
    else:
        # 确保 URL 包含完整路径
        if not url.endswith('/get_auto_play_item'):
            url = url.rstrip('/') + '/get_auto_play_item'
        util.log(1, f"[自动播放] 使用配置URL: {url}")

    # 初始化状态
    auto_play_running = True
    with shared_state.auto_play_lock:
        shared_state.is_auto_playing = False
        shared_state.can_auto_play = True

    util.log(1, f"[自动播放] 服务启动成功! URL={url}")

    # 设置最后请求时间为当前时间 - 599 秒，首次检查时将快速触发
    last_request_time = time.time() - 599

    def auto_play_loop():
        nonlocal last_request_time

        # 延迟导入，避免循环导入
        from core import sisi_booter

        # 在循环外导入一次中转站模块，避免在循环内反复导入
        transit_station_module = None
        try:
            from llm import transit_station as ts_module
            transit_station_module = ts_module
            util.log(1, "[自动播放] 中转站模块已加载")
        except ImportError:
            util.log(2, "[自动播放] 警告：无法导入中转站模块，相关检查将跳过")


        while auto_play_running:
            try:
                # 灏濊瘯鎭㈠ can_auto_play 鐘舵€?(鏂板鍔犵殑閫昏緫)
                try:
                    # 妫€鏌ュ墠鍏堣幏鍙栭攣锛岄伩鍏嶇珵鎬佹潯浠?
                    with shared_state.auto_play_lock:
                        # 妫€鏌ョ郴缁熸槸鍚︾┖闂?
                        system_is_idle = True
                        
                        if system_is_idle and hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'chatting') and sisi_booter.sisi_core.chatting:
                            system_is_idle = False
                        
                        if system_is_idle and transit_station_module:
                            try:
                                transit = transit_station_module.get_transit_station()
                                if hasattr(transit, 'intermediate_states') and transit.intermediate_states:
                                    system_is_idle = False
                            except Exception as e_transit_check:
                                util.log(1, f"[自动播放] 检查中转站状态时发生异常: {e_transit_check}")


                        # **淇鍏抽敭闂锛氭仮澶峜an_auto_play鏃堕渶瑕佽€冭檻淇濇姢鏈?*
                        if system_is_idle and not shared_state.can_auto_play:
                            # 妫€鏌ユ槸鍚﹁繕鍦ㄤ繚鎶ゆ湡鍐?
                            current_time_local = time.time()  # 浣跨敤灞€閮ㄥ彉閲忛伩鍏嶅紩鐢ㄩ敊璇?
                            time_since_last = current_time_local - last_request_time
                            if time_since_last >= 0:  # 鍙湁杩囦簡淇濇姢鏈熸墠鎭㈠
                                shared_state.can_auto_play = True
                                util.log(1, f"[自动播放] 系统空闲且超过保护期({time_since_last:.1f}秒)，can_auto_play 已恢复为 True")
                            else:
                                remaining_protection = abs(time_since_last)
                                util.log(1, f"[自动播放] 系统空闲但仍在保护期内，还需等待 {remaining_protection:.1f}秒")
                except Exception as e_recovery:
                    util.log(2, f"[自动播放] 恢复can_auto_play状态时发生异常: {e_recovery}")

                current_time = time.time()

                # 鑾峰彇褰撳墠鏃堕棿鍜岃窛绂讳笂娆¤姹傜殑鏃堕棿
                time_since_last = current_time - last_request_time
                time_until_next = max(0, interval - time_since_last)

                # 降低调试日志频率，每 5 分钟打印一次状态
                if time_until_next > 0 and (int(time_until_next) % 300 == 0 or int(time_until_next) in [300, 180, 60, 30, 10, 5]):
                    util.log(1, f"[自动播放] 下次播放倒计时: {int(time_until_next)}秒")

                # 妫€鏌ョ姸鎬?
                with shared_state.auto_play_lock:
                    can_play = shared_state.can_auto_play
                    is_playing = shared_state.is_auto_playing

                # **淇淇濇姢鏈熼€昏緫锛氬鍔?80绉掔殑浜や簰淇濇姢鏈?*
                time_since_last = current_time - last_request_time
                protection_period = 180  # 3鍒嗛挓淇濇姢鏈?
                time_until_protection_ends = protection_period - time_since_last
                
                # 检查是否还在保护期内
                if time_until_protection_ends > 0:
                    if int(time_until_protection_ends) % 300 == 0:  # 姣?鍒嗛挓鎻愰啋涓€娆?
                        util.log(1, f"[自动播放] 交互保护期中，还需等待 {time_until_protection_ends:.0f}秒")
                    time.sleep(300)  # 淇敼涓?鍒嗛挓寤惰繜锛屽噺灏戞棩蹇楅鐜?
                    continue  # 璺宠繃姝ゆ妫€鏌?
                
                # 濡傛灉鍙互鎾斁涓旇窛涓婃璇锋眰宸茬粡瓒呰繃闂撮殧鏃堕棿涓斾笉鍦ㄤ氦浜掍腑涓旇繃浜嗕繚鎶ゆ湡
                if can_play and not is_playing and time_since_last >= interval:
                    # 妫€鏌gent鍜岀郴缁熸槸鍚︽鍦ㄥ鐞嗕换鍔?
                    agent_is_busy = False
                    system_busy_reasons = []
                    
                    try:
                        # 1. 妫€鏌ヤ腑杞珯鏄惁鏈夋椿鍔ㄧ姸鎬?
                        from llm.transit_station import get_transit_station
                        transit = get_transit_station()

                        if hasattr(transit, 'intermediate_states') and transit.intermediate_states:
                            agent_is_busy = True
                            system_busy_reasons.append("涓浆绔欏鐞嗕腑")

                        # 2. 妫€鏌LP/Agent鑱婂ぉ鐘舵€?
                        if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'chatting') and sisi_booter.sisi_core.chatting:
                            agent_is_busy = True
                            system_busy_reasons.append("NLP/Agent鑱婂ぉ涓?")

                        # 3. 妫€鏌ラ煶棰戦槦鍒楃姸鎬?
                        if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'sound_query') and not sisi_booter.sisi_core.sound_query.empty():
                            agent_is_busy = True
                            queue_size = sisi_booter.sisi_core.sound_query.qsize()
                            system_busy_reasons.append(f"音频队列有{queue_size}个待播放")

                        if agent_is_busy:
                            util.log(1, f"[自动播放] ⏸️ 系统忙碌中，暂停自动播放: {', '.join(system_busy_reasons)}")
                            time.sleep(5)  # 娣诲姞寤惰繜閬垮厤鐤媯寰幆杈撳嚭鏃ュ織
                            continue  # 绔嬪嵆璺宠繃姝ゆ寰幆

                    except Exception as e:
                        util.log(1, f"[自动播放] ⚠️ 检查系统状态出错: {str(e)}")
                        # 鍙戠敓寮傚父鏃惰皑鎱庤捣瑙侊紝鏆傚仠姝ゆ鑷姩鎾斁
                        time.sleep(5)  # 娣诲姞寤惰繜閬垮厤鐤媯寰幆杈撳嚭鏃ュ織
                        continue

                    # 鍙湁褰揳gent娌℃湁鍦ㄥ鐞嗕换鍔℃椂鎵嶆墽琛岃嚜鍔ㄦ挱鏀?
                    if not agent_is_busy:
                        # 閿佸畾鐘舵€?
                        with shared_state.auto_play_lock:
                            # 鍐嶆妫€鏌ョ姸鎬?闃叉閿佹湡闂寸姸鎬佹敼鍙?
                            if shared_state.can_auto_play and not shared_state.is_auto_playing:
                                shared_state.can_auto_play = False

                        try:
                            # 鍙戦€佽姹傝幏鍙栧唴瀹?
                            response = requests.get(url, timeout=10)

                            if response.status_code == 200:
                                data = None
                                try:
                                    data = response.json()

                                    # 妫€鏌ュ搷搴斾腑鏄惁鍖呭惈鎵€闇€瀛楁
                                    if "text" in data:
                                        # **淇鍏抽敭闂锛氫笉鍦ㄨ繖閲岄噸缃甽ast_request_time锛岄伩鍏嶄笌reset_auto_play_timer鍐茬獊**
                                        # last_request_time = current_time  # 娉ㄩ噴鎺夎繖琛岋紝闃叉閲嶇疆鍐茬獊

                                        # 璁剧疆鐘舵€?
                                        with shared_state.auto_play_lock:
                                            shared_state.is_auto_playing = True

                                        # 鎻愬彇鏂囨湰鍐呭
                                        text = data["text"]
                                        tone = data.get("tone", "姝ｅ父")

                                        # 璁板綍鎾斁鍐呭
                                        util.log(1, "[自动播放] 🎵 播放内容")

                                        # 鍒涘缓浜や簰瀵硅薄骞惰缃弬鏁?
                                        interact = Interact("auto_play", 2, {
                                            "user": "auto_play",
                                            "text": text,
                                            "tone": tone
                                        })
                                        interact.interleaver = "auto_play"  # 鐢ㄤ簬鏍囪瘑鑷姩鎾斁

                                        # 鏋勫缓鎾斁鏁版嵁
                                        play_text = {
                                            "text": text,
                                            "tone": tone,
                                            "speed": 1.0,
                                            "gain": -1.0
                                        }

                                        # 姝ｇ‘澶勭悊鑷姩鎾斁娑堟伅鍒癢eb绔?
                                        if hasattr(sisi_booter, 'sisi_core'):
                                            try:
                                                # 娉ㄦ剰锛氫笉鑳界洿鎺ヨ皟鐢ㄥ弻涓嬪垝绾垮紑澶寸殑绉佹湁鏂规硶
                                                util.log(1, f"[自动播放] 📱 将消息作为Sisi消息发送到Web端: {text[:30]}...")

                                                # 浣跨敤涓嶯LP妯″潡鐩稿悓鐨勬暟鎹簱瀛樺偍鏂规硶
                                                # 馃棏锔?member_db 宸插垹闄わ紝浣跨敤榛樿uid
                                                uid = 0  # 榛樿鐢ㄦ埛ID

                                                # 馃毃 绂佺敤瀵硅瘽璁板綍鏁版嵁搴撳啓鍏?
                                                content_id = 0  # 涓嶅啀鍐欏叆瀵硅瘽璁板綍
                                                util.log(1, "[自动播放] ⏭️ 跳过数据库存储")

                                                # 鐩存帴鏋勯€犳秷鎭苟鍙戦€佸埌web瀹炰緥 - 鍗充娇鏁版嵁搴撴搷浣滃け璐ヤ篃缁х画
                                                try:
                                                    if wsa_server.get_web_instance().is_connected("User"):
                                                        try:
                                                            from llm.liusisi import get_current_system_mode
                                                            reply_type = (get_current_system_mode() or "sisi").strip().lower()
                                                            if reply_type not in ("sisi", "liuye"):
                                                                reply_type = "sisi"
                                                        except Exception:
                                                            reply_type = "sisi"
                                                        response_msg = {
                                                            "panelReply": {
                                                                "type": reply_type,
                                                                "content": text,
                                                                "username": "User",
                                                                "uid": uid,
                                                                "id": content_id
                                                            },
                                                            "Username": "User"  # 鍙戦€佺粰User瀹㈡埛绔?
                                                        }
                                                        wsa_server.get_web_instance().add_cmd(response_msg)
                                                        util.log(1, "[自动播放] 📤 消息已发送到Web端")
                                                except Exception as web_err:
                                                    util.log(1, f"[自动播放] ⚠️ Web消息发送失败: {str(web_err)}")

                                                # 鐭殏寤惰繜纭繚娑堟伅澶勭悊瀹屾垚
                                                time.sleep(0.5)
                                            except Exception as e:
                                                util.log(1, f"[自动播放] ⚠️ Web处理异常: {str(e)}")

                                            # 鐙珛try鍧楃‘淇濅竴瀹氫細鎵ц璇煶鎾斁锛屼笉鍙楀墠闈㈠紓甯稿奖鍝?
                                            try:
                                                # 鎾斁璇煶
                                                util.log(1, "[自动播放] 🔊 开始播放语音...")
                                                sisi_booter.sisi_core.on_interact(interact)
                                                
                                                # 鎴愬姛璋冪敤 on_interact 鍚庯紝閲嶇疆鐘舵€佸苟璁剧疆涓嬫鎾斁鏃堕棿
                                                with shared_state.auto_play_lock:
                                                    shared_state.is_auto_playing = False
                                                    util.log(1, "[自动播放] on_interact 调用完成，is_auto_playing 已重置为 False")
                                                    # can_auto_play 鐨勬仮澶嶇敱寰幆椤堕儴鐨勯€昏緫澶勭悊锛岃繖閲屼笉鍐嶉噸澶嶈缃?
                                                    # shared_state.can_auto_play = True

                                                # **淇锛氭纭缃笅娆℃挱鏀炬椂闂?*
                                                last_request_time = current_time
                                                util.log(1, f"[自动播放] ✅ 播放完成，下次播放时间: {time.strftime('%H:%M:%S', time.localtime(current_time + interval))}")

                                            except Exception as play_err:
                                                util.log(1, f"[自动播放] ❌ 语音播放失败: {str(play_err)}")
                                                # 濡傛灉鎾斁澶辫触锛岄噸缃姸鎬?
                                                with shared_state.auto_play_lock:
                                                    shared_state.can_auto_play = True
                                                    shared_state.is_auto_playing = False
                                except ValueError as e:
                                    util.log(1, f"[自动播放] JSON解析错误: {str(e)}")
                                    # 閲嶇疆鐘舵€?
                                    with shared_state.auto_play_lock:
                                        shared_state.can_auto_play = True
                            else:
                                util.log(1, f"[自动播放] 请求失败: {response.status_code}")
                                # 重置状态
                                with shared_state.auto_play_lock:
                                    shared_state.can_auto_play = True

                        except Exception as e:
                            util.log(1, f"[自动播放] 请求异常: {str(e)}")
                            # 重置状态并确保下次能正常计时
                            with shared_state.auto_play_lock:
                                shared_state.can_auto_play = True # 鍏佽涓嬫灏濊瘯
                                shared_state.is_auto_playing = False # 纭繚娌℃湁鍗″湪鎾斁鐘舵€?
                            # 璇锋眰寮傚父鏃朵笉閲嶇疆last_request_time锛岄伩鍏嶅共鎵扮敤鎴蜂氦浜掍繚鎶ゆ湡
                            # last_request_time = current_time # 娉ㄩ噴鎺夛紝閬垮厤涓巖eset_auto_play_timer鍐茬獊

                # 鐩戞祴閿佹鐘舵€?- 濡傛灉瓒呰繃180绉掕繕鏈噸缃紝寮哄埗閲嶇疆鐘舵€?
                # is_playing_now 搴旇鍦ㄥ惊鐜紑濮嬫椂浠?shared_state.is_auto_playing 鑾峰彇
                with shared_state.auto_play_lock: # 鑾峰彇鏈€鏂扮殑 is_auto_playing
                    is_currently_auto_playing_for_timeout_check = shared_state.is_auto_playing

                if is_currently_auto_playing_for_timeout_check and current_time - last_request_time > 180:
                    # 杈撳嚭璇︾粏鏃ュ織锛屽府鍔╄瘖鏂秴鏃跺師鍥?
                    elapsed = current_time - last_request_time
                    util.log(1, f"[自动播放] 检测到超时状态：已播放{elapsed:.1f}秒无响应")

                    # 璁板綍褰撳墠鐘舵€佺敤浜庤瘖鏂?
                    with shared_state.auto_play_lock:
                        util.log(1, f"[自动播放] 当前状态: is_auto_playing={shared_state.is_auto_playing}, can_auto_play={shared_state.can_auto_play}")

                    util.log(1, "[自动播放] 执行超时重置")
                    with shared_state.auto_play_lock:
                        prev_auto_playing = shared_state.is_auto_playing
                        prev_can_auto_play = shared_state.can_auto_play

                        shared_state.is_auto_playing = False
                        shared_state.can_auto_play = True
                        last_request_time = current_time

                        util.log(1, f"[自动播放] 状态已重置: is_auto_playing={prev_auto_playing}->False, can_auto_play={prev_can_auto_play}->True")

            except Exception as e:
                util.log(1, f"[自动播放] 主循环异常: {str(e)}")
                import traceback
                util.log(1, traceback.format_exc())

            # 淇敼鐫＄湢鏃堕棿涓?鍒嗛挓锛屽噺灏戞棩蹇楅鐜?
            time.sleep(300)

    # 鍒涘缓骞跺惎鍔ㄧ嚎绋?
    auto_play_thread = threading.Thread(target=auto_play_loop)
    auto_play_thread.daemon = True
    auto_play_thread.start()

    util.log(1, "[自动播放] 服务已启动")

# 用户交互时重置自动播放计时器
def reset_auto_play_timer():
    """用户交互时，重置自动播放计时器。"""
    global last_request_time
    current_time = time.time()

    # 璁板綍涔嬪墠鐨勬椂闂达紝鐢ㄤ簬鏃ュ織
    previous_time = last_request_time

    # 保护期应相对于当前时间延长，而不是使用绝对时间
    # 设置保护期为180秒，从当前时间开始计算
    last_request_time = current_time

    # 棰濆璁剧疆鐘舵€佺‘淇濅笉浼氬湪浜や簰鏈熼棿鎾斁
    with shared_state.auto_play_lock:
        if shared_state.is_auto_playing:
            util.log(1, "[自动播放] 检测到用户交互，停止当前自动播放")
            shared_state.is_auto_playing = False
        shared_state.can_auto_play = False  # 暂时禁止自动播放

    # 记录重置时间日志
    util.log(1, f"[自动播放] 计时器已重置: {time.strftime('%H:%M:%S', time.localtime(previous_time))} -> {time.strftime('%H:%M:%S', time.localtime(current_time))}")
    util.log(1, f"[自动播放] 交互保护期启动180秒，保护期结束时间: {time.strftime('%H:%M:%S', time.localtime(current_time + 180))}")

# 鍏抽棴鑷姩鍒犻櫎缂撳瓨鐨勫姛鑳?
# 鍘熸湁鐨勬竻绌虹紦瀛橀€昏緫娉ㄩ噴鎺?
# cache.clear()  # 娓呯┖缂撳瓨

def stop_auto_play_service():
    """停止自动播放服务。"""
    global auto_play_running, auto_play_thread

    auto_play_running = False

    if auto_play_thread and auto_play_thread.is_alive():
        util.log(1, "[自动播放] 正在停止服务...")
        # 绛夊緟绾跨▼缁撴潫
        auto_play_thread.join(timeout=5)
        auto_play_thread = None

    util.log(1, "[自动播放] 服务已停止")


