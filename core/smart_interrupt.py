#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能打断系统 - 简单版
STT识别后 → 检测系统状态 → 大模型决策 → 执行打断
"""

import time
from utils import util
from core.unified_system_controller import get_unified_controller

class SmartInterrupt:
    """智能打断系统"""

    def __init__(self):
        self.last_user_input = None
        self.last_input_time = None
        self.conversation_history = []  # 保存最近的对话历史

        # 🎯 LIUSIS角色风格短语库 - 按状态和情境分类
        self.liusis_phrases = {
            # 音乐相关打断
            "music_stop": [
                "行行行，不唱就不唱", "好啦好啦，停就停", "哼，人家唱得好好的",
                "停停停，满足你了吧", "我操，又要停", "真是的，刚开始唱",
                "别吵别吵，停了", "你这人真麻烦", "好不容易找首歌"
            ],
            "music_change": [
                "换就换，你事真多", "又要换歌？", "行吧行吧，给你换",
                "哼，这首不好听吗", "我操，选歌困难症", "换换换，烦死了",
                "你到底想听什么", "非要换是吧", "好吧，给你重选"
            ],

            # 系统忙碌状态回复
            "busy_music": [
                "别吵，正听歌呢", "音乐播放中，等等", "让我听完这首",
                "正嗨呢，别打断", "我操，好不容易放首歌"
            ],
            "busy_camera": [
                "拍照呢，别动", "等我拍完再说", "摄像头工作中",
                "别急，正在拍", "你急什么急",
                # 🔧 新增：继续但抱怨的回复
                "马上拍完别催", "等我拍完行不行", "你急什么急"
            ],
            "busy_agent": [
                "忙着呢别说话", "工具还没返回别急", "正在查呢，等等",
                "网络请求中，稍等", "别催，正在处理",
                # 🔧 新增：成本考虑的回复
                "快查完了等等", "马上出结果", "别浪费钱啊",
                "等等快出结果了", "马上就好别急", "钱都花了等等"
            ],
            "busy_tts": [
                "人家还在说话呢", "让我说完", "别打断我",
                "一句话都不让说完", "你这人真没礼貌",
                # 🔧 新增：继续但抱怨的回复
                "让我说完嘛", "别打断我", "一句话都不让说"
            ],
            "busy_thinking": [
                "正在想呢，等一下", "脑子在转，别催", "思考中，稍等",
                "给我点时间好不好", "别急别急"
            ],

            # 全局控制回复
            "global_stop": [
                "我操，好吧，全停", "行行行，都停了", "停就停，真是的",
                "好啦，全部取消", "你满意了吧",
                # 🔧 新增：强烈停止的回复
                "好啦好啦不弄了", "行行行停了", "我错了别生气",
                "别生气了停了", "好啦都停了", "不弄了不弄了"
            ],
            "global_pause": [
                "等一下就等一下", "行吧，先暂停", "好啦好啦，等等",
                "你急什么急", "稍等稍等"
            ],
            "global_resume": [
                "好了，继续吧", "行，可以继续了", "那就接着来",
                "继续继续", "好啦，开始吧"
            ],

            # 无聊/杂音输入回复
            "meaningless_noise": [
                "说点有用的行不行", "你到底想干嘛", "别发这些没用的",
                "有话直说，别磨叽", "我操，能说正经的吗", "又怎么啦",
                "你烦不烦", "小声点", "嗯什么嗯", "啊什么啊"
            ],

            # 重复输入回复
            "repeat_annoying": [
                "你刚才不是说过了", "别重复了，听到了", "说这么多遍干嘛",
                "知道了知道了", "我操，复读机吗", "够了够了"
            ],

            # 问候/闲聊回复
            "casual_chat": [
                "我挺好的，有事说事", "还行吧，找我干嘛", "好着呢，别废话",
                "我当然好啦", "哼，关心我？", "说正事吧"
            ],

            # 系统错误回复
            "system_error": [
                "哎呀，出了点问题", "系统有点抽风", "我操，又出bug了",
                "稍等，让我修复", "系统犯傻了"
            ]
        }
    
    def check_interrupt(self, user_input):
        """
        智能打断检测 - 核心逻辑

        Args:
            user_input (str): STT识别的用户输入

        Returns:
            dict: 打断决策结果
        """
        try:
            current_time = time.time()

            # 🔥 新增：音频质量过滤 - 过滤回声、噪音、音乐
            if self._is_poor_audio_quality(user_input):
                util.log(1, f"[智能打断] 检测到低质量音频/回声，忽略: {user_input}")
                return {
                    "should_interrupt": False,
                    "reason": "poor_audio_quality",
                    "response": None,  # 不回复，静默处理
                    "action": "ignore"
                }

            # 1. 获取系统状态
            system_state = self._get_system_state()

            # 2. 计算时间间隔
            time_interval = None
            if self.last_input_time:
                time_interval = current_time - self.last_input_time

            # 3. 构造给大模型的完整上下文prompt
            prompt = self._build_intelligent_prompt(user_input, system_state, time_interval)

            # 4. 调用大模型进行智能决策
            decision = self._call_llm_for_decision(prompt)

            # 🔥 修复：先打印日志，再更新历史
            util.log(1, f"[智能打断] 用户输入: {user_input}")
            util.log(1, f"[智能打断] 上一句: {self.last_user_input if self.last_user_input else '首次输入'}")
            util.log(1, f"[智能打断] 时间间隔: {time_interval:.1f}秒" if time_interval else "首次输入")
            util.log(1, f"[智能打断] 系统状态: {system_state['summary']}")
            util.log(1, f"[智能打断] 大模型决策: {decision}")

            # 5. 更新对话历史（在日志打印之后）
            self._update_conversation_history(user_input, current_time, decision)

            return decision

        except Exception as e:
            util.log(2, f"[智能打断] 检测异常: {str(e)}")
            return {"should_interrupt": False, "reason": "error"}
    
    def _is_poor_audio_quality(self, text):
        """
        检测音频质量 - 过滤回声、噪音、音乐
        
        识别标记：
        - <|nospeech|> = 非语音音频（音乐、噪音）
        - <|emo_unknown|> = 情感识别失败（音频不清晰）
        - <|event_unk|> = 事件分类失败（混合音源）
        - <|BGM|> = 背景音乐
        - 多个未知标识符 = 音频严重失真
        
        Returns:
            bool: True表示低质量音频，应该忽略
        """
        if not text or not isinstance(text, str):
            return True
        
        # 🔥 关键：检测音频质量标记
        poor_quality_markers = [
            "<|nospeech|>",      # 非语音音频（音乐回声！）
            "<|emo_unknown|>",   # 情感未知（音频不清晰）
            "<|event_unk|>",     # 事件未知（混合音源）
            "<|BGM|>",           # 背景音乐
        ]
        
        # 检查是否包含低质量标记
        for marker in poor_quality_markers:
            if marker.lower() in text.lower():
                return True
        
        # 🔥 检测短词+未知标记组合（典型的噪音特征）
        text_clean = text.strip()
        if len(text_clean) < 5:  # 短于5个字符
            unknown_markers = ["unknown", "unk", "噪音", "杂音"]
            for marker in unknown_markers:
                if marker in text_clean.lower():
                    return True
        
        # 🔥 检测多个未知标识符组合（音频严重失真）
        unknown_count = sum(1 for marker in ["unknown", "unk", "emo_unknown", "event_unk"] 
                          if marker in text.lower())
        if unknown_count >= 2:
            return True
        
        return False
    
    def _get_system_state(self):
        """获取SmartSisi系统状态 - 重点关注可打断的活动"""
        try:
            # 延迟导入避免循环导入
            from core import sisi_booter

            state = {
                "is_speaking": False,
                "is_qa_music_playing": False,
                "audio_queue_size": 0,
                # 🔧 新增：音乐模块状态检测
                "is_qa_music_module_working": False,
                "is_camera_capturing": False,
                "is_llm_selecting_music": False,
                # 🔥 新增：硬件和系统资源状态检测
                "esp32_status": self._get_esp32_status(),
                "system_resources": self._get_system_resources(),
                "api_health": self._get_api_health(),
                "database_busy": self._get_database_status(),
                # 以下是背景信息，不影响打断决策
                "is_processing": False,
                "is_lg_system_running": False,
                "is_agent_working": False,
                "is_camera_monitoring": False,
                "is_subscription_active": False,
                "summary": "系统空闲"
            }

            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                sisi_core = sisi_booter.sisi_core

                # 1. 检查TTS说话状态
                state["is_speaking"] = getattr(sisi_core, 'speaking', False)

                # 2. 检查NLP处理状态
                state["is_processing"] = getattr(sisi_core, 'chatting', False)

                # 3. 检查音频队列状态（增强版QA音乐监控）
                if hasattr(sisi_core, 'sound_query'):
                    queue = sisi_core.sound_query
                    state["audio_queue_size"] = queue.qsize()

                    # 🔧 修复：正确区分音乐和其他音频类型
                    if not queue.empty():
                        # 检查队列中的音频类型和优先级
                        try:
                            # 临时获取队列内容进行分析（不移除）
                            temp_items = []
                            while not queue.empty():
                                temp_items.append(queue.get())

                            # 分析音频类型和优先级
                            has_high_priority = any(item[0] >= 6 for item in temp_items)  # 优先级6+为高优先级
                            has_agent_audio = any(item[2] for item in temp_items)  # is_agent=True
                            has_music_files = any('music_' in str(item[1]) or 'random_generation_music' in str(item[1]) or 'mymusic' in str(item[1]) for item in temp_items)

                            # 重新放回队列
                            for item in temp_items:
                                queue.put(item)

                            # 🔧 修复：只有真正的音乐文件才算"QA音乐播放中"
                            if has_music_files:
                                state["is_qa_music_playing"] = True
                            else:
                                # 如果只是Agent回复或TTS音频，不算音乐播放
                                state["is_qa_music_playing"] = False

                            # 设置详细状态
                            if has_high_priority:
                                state["has_high_priority_audio"] = True
                            if has_agent_audio:
                                state["has_agent_audio"] = True
                            if has_music_files:
                                state["has_music_files"] = True

                        except:
                            # 异常时保守处理，不认为是音乐播放
                            state["is_qa_music_playing"] = False

                # 4. 检查LG系统运行状态
                try:
                    from llm.lg_system import get_lg_system
                    lg_system = get_lg_system()
                    if hasattr(lg_system, 'is_running') and lg_system.is_running:
                        state["is_lg_system_running"] = True
                except:
                    pass

                # 5. 检查中转站Agent状态（增强版）
                try:
                    from llm.transit_station import get_transit_station
                    transit = get_transit_station()

                    # 检查中间状态处理
                    if hasattr(transit, 'intermediate_states') and transit.intermediate_states:
                        state["is_agent_working"] = True

                    # 🔧 新增：检查工具通知队列状态
                    if hasattr(transit, 'tool_notification_states') and transit.tool_notification_states:
                        state["is_agent_working"] = True

                    # 🔧 新增：检查阶段发送状态
                    if hasattr(transit, 'stage_sent'):
                        stage_sent = transit.stage_sent
                        # 如果有任何阶段正在处理（start或middle已发送但final未发送）
                        if (stage_sent.get("start", False) or stage_sent.get("middle", False)) and not stage_sent.get("final", False):
                            state["is_agent_working"] = True

                except:
                    pass

                # 6. 检查摄像头/YOLOv8监控状态
                try:
                    from ai_module.yolo_service import YOLOv8Service
                    yolo = YOLOv8Service.get_instance()
                    if yolo and hasattr(yolo, '_is_monitoring') and yolo._is_monitoring:
                        state["is_camera_monitoring"] = True
                except:
                    pass

                # 7. 检查A2A订阅系统活动状态（真正的活动检测）
                try:
                    from llm.agent.a2a_notification import get_tool_manager
                    manager = get_tool_manager()

                    # 🔧 修复：不仅检查_running，还要检查是否真的在处理任务
                    has_real_activity = False

                    # 检查是否有活跃的订阅（真正的订阅，不是空的）
                    if hasattr(manager, 'subscriptions') and manager.subscriptions:
                        # 检查订阅是否有实际活动
                        for tool_name, subs in manager.subscriptions.items():
                            if subs:  # 有实际订阅
                                has_real_activity = True
                                break

                    # 检查是否有待处理的任务
                    if hasattr(manager, 'task_queue') and not manager.task_queue.empty():
                        has_real_activity = True

                    # 检查中转站的工具通知队列
                    from llm.transit_station import get_transit_station
                    transit = get_transit_station()
                    if hasattr(transit, 'tool_notification_states') and transit.tool_notification_states:
                        has_real_activity = True

                    # 🔧 关键修复：只有真正有活动时才标记为活跃
                    if has_real_activity:
                        state["is_subscription_active"] = True

                except:
                    pass

                # 🔧 新增：8. 检查优化站处理状态
                try:
                    from llm.optimization_station import get_optimization_station
                    opt_station = get_optimization_station()
                    if hasattr(opt_station, 'is_processing') and opt_station.is_processing:
                        state["is_agent_working"] = True
                except:
                    pass

                # 🔧 新增：9. 检查SmartSisi核心桥接状态
                try:
                    from llm.sisi_core_bridge import SisiCoreBridge
                    bridge = SisiCoreBridge.get_instance()
                    if hasattr(bridge, 'is_processing') and bridge.is_processing:
                        state["is_agent_working"] = True
                except:
                    pass

            # 🔥 修复：拟人化状态描述 - 同时考虑PC和ESP32状态
            humanized_activities = []

            # 🎵 音频相关 - 拟人化为"我在做什么"
            esp32_status = state.get("esp32_status", {})
            esp32_audio_playing = esp32_status.get("audio_playing", False)
            esp32_queue_size = esp32_status.get("device_queue_size", 0)
            esp32_tts_active = esp32_status.get("tts_active", False)

            # 🔥 关键修复：优先检查ESP32状态，因为那是真实播放状态
            if esp32_audio_playing or esp32_tts_active:
                if esp32_queue_size > 1:
                    humanized_activities.append(f"我在说话呢(设备队列还有{esp32_queue_size-1}个)")
                else:
                    humanized_activities.append("我在说话呢")
            elif state["is_qa_music_playing"]:
                queue_size = state.get('audio_queue_size', 0)
                if queue_size > 1:
                    humanized_activities.append(f"我在唱歌呢(还有{queue_size-1}首要唱)")
                else:
                    humanized_activities.append("我在唱歌呢")
            elif state.get("has_agent_audio"):
                humanized_activities.append("我在说工具查询结果")
            elif state["is_speaking"]:
                humanized_activities.append("我在说话呢")
            elif state.get('audio_queue_size', 0) > 0:
                queue_size = state.get('audio_queue_size', 0)
                humanized_activities.append(f"我嘴里还有{queue_size}句话要说")
            elif esp32_queue_size > 0:
                humanized_activities.append(f"设备队列还有{esp32_queue_size}个音频要播放")

            # 🔧 工作状态 - 拟人化为"我在忙什么"
            if state["is_agent_working"]:
                humanized_activities.append("我在查复杂的工具")
            if state["is_lg_system_running"]:
                humanized_activities.append("我在动脑子思考")
            if state["is_subscription_active"]:
                humanized_activities.append("我在处理后台通知")
            if state["is_processing"]:
                humanized_activities.append("我在理解你说的话")

            # 📷 硬件状态 - 拟人化为"我在用身体做什么"
            if state.get("is_camera_capturing"):
                humanized_activities.append("我在拍照呢")
            elif state.get("is_camera_monitoring"):
                humanized_activities.append("我在用眼睛看着")
            if state.get("is_qa_music_module_working"):
                humanized_activities.append("我在选歌")
            if state.get("is_llm_selecting_music"):
                humanized_activities.append("我在挑音乐")

            # 生成拟人化摘要
            if humanized_activities:
                state["summary"] = "、".join(humanized_activities)
            else:
                state["summary"] = "我现在很闲"

            return state

        except Exception as e:
            util.log(2, f"[智能打断] 状态获取异常: {str(e)}")
            return {"summary": "状态获取失败", "is_speaking": False, "is_qa_music_playing": False}

    def _is_qa_music_module_working(self):
        """检查QA音乐模块是否在工作"""
        try:
            # 🔧 方法1：检查最近日志中的音乐模块活动
            import os
            import time

            log_dir = util.LOGS_DIR
            if not os.path.exists(log_dir):
                return False

            # 获取最新的日志文件
            log_files = [f for f in os.listdir(log_dir) if f.startswith("log-") and f.endswith(".log")]
            if not log_files:
                return False

            latest_log = max(log_files, key=lambda x: os.path.getctime(os.path.join(log_dir, x)))
            log_path = os.path.join(log_dir, latest_log)

            # 读取最近的日志行
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent_lines = lines[-50:] if len(lines) > 50 else lines  # 最近50行

            # 检查音乐模块和A2A工具相关的活动
            current_time = time.time()
            for line in reversed(recent_lines):  # 从最新的开始检查
                if any(keyword in line for keyword in [
                    "[QA音乐]", "[音乐模块]", "调用音乐模块", "音乐脚本QA",
                    "摄像头拍照", "LLM选歌", "选择随机音乐",
                    # 🔥 新增：A2A工具活动检测
                    "music_tool", "bai_lian", "zudao", "[音乐生成]", "[双重生成]",
                    "订阅站补充信息", "工具完成:", "A2A工具", "music_generator"
                ]):
                    # 提取时间戳
                    try:
                        if "[" in line and "]" in line:
                            timestamp_str = line.split("]")[0][1:]  # 提取时间戳
                            # 简单检查：如果是最近30秒内的活动，认为模块在工作
                            # 这里简化处理，实际可以解析时间戳
                            return True
                    except:
                        continue

            return False

        except Exception as e:
            util.log(2, f"[智能打断] 检查QA音乐模块状态异常: {str(e)}")
            return False

    def _is_camera_capturing(self):
        """检查摄像头是否在拍照"""
        try:
            # 🔧 方法1：检查YOLO服务状态
            from ai_module.yolo_service import YOLOv8Service
            yolo = YOLOv8Service.get_instance()
            if hasattr(yolo, '_is_monitoring') and yolo._is_monitoring:
                return True

            # 🔧 方法2：检查最近日志中的摄像头活动
            import os
            import time

            log_dir = util.LOGS_DIR
            if not os.path.exists(log_dir):
                return False

            log_files = [f for f in os.listdir(log_dir) if f.startswith("log-") and f.endswith(".log")]
            if not log_files:
                return False

            latest_log = max(log_files, key=lambda x: os.path.getctime(os.path.join(log_dir, x)))
            log_path = os.path.join(log_dir, latest_log)

            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent_lines = lines[-30:] if len(lines) > 30 else lines  # 最近30行

            # 检查摄像头相关活动
            for line in reversed(recent_lines):
                if any(keyword in line for keyword in [
                    "摄像头拍照", "camera capture", "拍照完成", "图片保存"
                ]):
                    return True

            return False

        except Exception as e:
            util.log(2, f"[智能打断] 检查摄像头状态异常: {str(e)}")
            return False

    def _is_complex_task_active(self):
        """检查是否有复杂任务正在运行（A2A工具、音乐生成等）"""
        try:
            # 检查A2A工具活动（已有的逻辑）
            if self._is_qa_music_active():
                return True

            # 检查Agent系统状态
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 检查是否在处理复杂任务
                if hasattr(sisi_booter.sisi_core, 'chatting') and sisi_booter.sisi_core.chatting:
                    return True

            return False

        except Exception as e:
            util.log(2, f"[智能打断] 检查复杂任务状态异常: {str(e)}")
            return False

    def _is_llm_selecting_music(self):
        """检查LLM是否在选择音乐"""
        try:
            # 🔧 检查最近日志中的LLM选歌活动
            import os

            log_dir = util.LOGS_DIR
            if not os.path.exists(log_dir):
                return False

            log_files = [f for f in os.listdir(log_dir) if f.startswith("log-") and f.endswith(".log")]
            if not log_files:
                return False

            latest_log = max(log_files, key=lambda x: os.path.getctime(os.path.join(log_dir, x)))
            log_path = os.path.join(log_dir, latest_log)

            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent_lines = lines[-30:] if len(lines) > 30 else lines  # 最近30行

            # 检查LLM选歌相关活动
            for line in reversed(recent_lines):
                if any(keyword in line for keyword in [
                    "LLM选歌", "选择随机音乐", "音乐选择", "正在选择音乐"
                ]):
                    return True

            return False

        except Exception as e:
            util.log(2, f"[智能打断] 检查LLM选歌状态异常: {str(e)}")
            return False

    def _get_esp32_status(self):
        """检测ESP32硬件设备状态 - 🔥 修复：检查真实播放状态"""
        try:
            # 检查ESP32桥接服务状态
            from esp32_liusisi import esp32_bridge

            status = {
                "connected": False,
                "audio_playing": False,
                "display_active": False,
                "motor_running": False,
                "camera_working": False,
                "last_heartbeat": None,
                "device_queue_size": 0,  # 新增：设备队列大小
                "tts_active": False      # 新增：TTS活跃状态
            }

            # 检查适配器是否初始化
            if hasattr(esp32_bridge, 'adapter_instance') and esp32_bridge.adapter_instance:
                adapter = esp32_bridge.adapter_instance
                status["connected"] = True
                status["device_count"] = len(adapter.clients) if hasattr(adapter, 'clients') else 0

                # 🔥 关键修复：检查设备真实状态
                if hasattr(adapter, 'devices') and adapter.devices:
                    for device_id, device_info in adapter.devices.items():
                        device_state = device_info.get("state", "unknown")

                        # 检查设备是否在播放TTS
                        if device_state in ["tts_playing", "speaking"]:
                            status["audio_playing"] = True
                            status["tts_active"] = True
                            util.log(1, f"[智能打断] 检测到设备{device_id[:8]}正在播放TTS")

                        # 检查设备是否在播放音乐
                        elif device_state in ["music_playing", "audio_playing"]:
                            status["audio_playing"] = True
                            util.log(1, f"[智能打断] 检测到设备{device_id[:8]}正在播放音频")

                # 🔥 新增：检查ESP32音频队列状态
                try:
                    from esp32_liusisi.sisi_audio_output import AudioOutputManager
                    # 检查是否有全局音频管理器实例
                    if hasattr(AudioOutputManager, '_instance') and AudioOutputManager._instance:
                        audio_manager = AudioOutputManager._instance

                        # 检查TTS队列
                        if hasattr(audio_manager, 'tts_queue'):
                            status["device_queue_size"] = audio_manager.tts_queue.qsize()
                            if status["device_queue_size"] > 0:
                                status["audio_playing"] = True
                                util.log(1, f"[智能打断] 检测到ESP32队列中有{status['device_queue_size']}个音频任务")

                        # 检查流式队列
                        if hasattr(audio_manager, 'stream_chunk_queue'):
                            stream_size = audio_manager.stream_chunk_queue.qsize()
                            if stream_size > 0:
                                status["audio_playing"] = True
                                util.log(1, f"[智能打断] 检测到ESP32流式队列中有{stream_size}个音频块")

                except Exception as e:
                    util.log(2, f"[智能打断] 检查ESP32音频队列异常: {str(e)}")

                # 尝试获取设备状态（如果适配器支持）
                if hasattr(adapter, 'get_device_status'):
                    device_status = adapter.get_device_status()
                    status.update(device_status)

            return status

        except Exception as e:
            util.log(2, f"[智能打断] 检查ESP32状态异常: {str(e)}")
            return {"connected": False, "error": str(e)}

    def _get_system_resources(self):
        """检测系统资源状态"""
        try:
            import psutil

            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpu_high": cpu_percent > 80,
                "memory_high": memory.percent > 85,
                "disk_full": disk.percent > 90,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent
            }

        except Exception as e:
            util.log(2, f"[智能打断] 检查系统资源异常: {str(e)}")
            return {"cpu_high": False, "memory_high": False, "disk_full": False}

    def _get_api_health(self):
        """检测外部API服务健康状态"""
        try:
            import requests
            from utils import config_util as cfg

            health_status = {
                "interrupt_model": False,
                "tts_service": False,
                "asr_service": False,
                "network_ok": False
            }

            # 检查打断模型API
            try:
                if hasattr(cfg, 'interrupt_model_base_url') and cfg.interrupt_model_base_url:
                    response = requests.get(cfg.interrupt_model_base_url, timeout=2)
                    health_status["interrupt_model"] = response.status_code == 200
            except:
                pass

            # 检查网络连通性
            try:
                response = requests.get("https://www.baidu.com", timeout=3)
                health_status["network_ok"] = response.status_code == 200
            except:
                pass

            return health_status

        except Exception as e:
            util.log(2, f"[智能打断] 检查API健康状态异常: {str(e)}")
            return {"interrupt_model": False, "tts_service": False, "asr_service": False, "network_ok": False}

    def _get_database_status(self):
        """检测数据库操作状态"""
        try:
            import sqlite3
            import os

            db_status = {
                "busy": False,
                "locked": False,
                "accessible": False
            }

            # 检查主数据库文件
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            agent_db_path = os.path.join(base_dir, "sisi_memory", "data", "agent_history.db")
            db_files = ["sisi.db", "timer.db", agent_db_path]

            for db_file in db_files:
                if os.path.exists(db_file):
                    try:
                        # 尝试快速连接测试
                        conn = sqlite3.connect(db_file, timeout=1)
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                        conn.close()
                        db_status["accessible"] = True
                        break
                    except sqlite3.OperationalError as e:
                        if "database is locked" in str(e).lower():
                            db_status["locked"] = True
                            db_status["busy"] = True
                    except:
                        pass

            return db_status

        except Exception as e:
            util.log(2, f"[智能打断] 检查数据库状态异常: {str(e)}")
            return {"busy": False, "locked": False, "accessible": False}



    def _update_conversation_history(self, user_input, current_time, decision):
        """更新对话历史"""
        try:
            # 保存当前输入为历史
            self.last_user_input = user_input
            self.last_input_time = current_time

            # 保存到对话历史（最多保留5条）
            self.conversation_history.append({
                "input": user_input,
                "time": current_time,
                "decision": decision
            })

            # 只保留最近5条记录
            if len(self.conversation_history) > 5:
                self.conversation_history.pop(0)

        except Exception as e:
            util.log(2, f"[智能打断] 更新对话历史异常: {str(e)}")

    def get_liusis_phrase(self, category, system_state=None):
        """获取LIUSIS风格的短语"""
        import random

        try:
            # 根据系统状态选择更具体的分类
            if category == "system_busy" and system_state:
                if system_state.get('is_processing'):
                    category = "system_busy_nlp"
                elif system_state.get('is_agent_working'):
                    category = "system_busy_agent"
                elif system_state.get('is_speaking'):
                    category = "system_busy_tts"
                elif system_state.get('is_qa_music_playing'):
                    category = "system_busy_music"

            phrases = self.liusis_phrases.get(category, ["哎呀，出了点问题"])
            return random.choice(phrases)

        except Exception as e:
            util.log(2, f"[智能打断] 获取短语异常: {str(e)}")
            return "哎呀，出了点问题"

    def _get_phrase_examples(self, system_state):
        """根据系统状态获取相关的短语示例"""
        examples = []

        # 🎯 根据当前系统状态提供5字以内的个性化示例
        if system_state.get('is_qa_music_playing'):
            examples.extend([
                "🎵 音乐播放中被打断时：" + "、".join(self.liusis_phrases["busy_music"][:3]),
                "🎵 要求停止音乐时：" + "、".join(self.liusis_phrases["music_stop"][:3]),
                "🎵 要求换歌时：" + "、".join(self.liusis_phrases["music_change"][:3])
            ])

        if system_state.get('is_camera_capturing') or system_state.get('is_camera_monitoring'):
            examples.append("📷 摄像头工作中：" + "、".join(self.liusis_phrases["busy_camera"][:3]))

        if system_state.get('is_agent_working'):
            examples.append("🔧 工具查询中：" + "、".join(self.liusis_phrases["busy_agent"][:3]))

        if system_state.get('is_speaking'):
            examples.append("🗣️ TTS说话中：" + "、".join(self.liusis_phrases["busy_tts"][:3]))

        if system_state.get('is_processing') or system_state.get('is_lg_system_running'):
            examples.append("🧠 思考处理中：" + "、".join(self.liusis_phrases["busy_thinking"][:3]))

        # 全局控制示例
        examples.extend([
            "🛑 全局停止时：" + "、".join(self.liusis_phrases["global_stop"][:3]),
            "⏸️ 全局暂停时：" + "、".join(self.liusis_phrases["global_pause"][:3]),
            "▶️ 全局恢复时：" + "、".join(self.liusis_phrases["global_resume"][:3])
        ])

        # 总是包含常见情况的示例
        examples.extend([
            "💬 闲聊问候时：" + "、".join(self.liusis_phrases["casual_chat"][:3]),
            "🔇 无聊杂音时：" + "、".join(self.liusis_phrases["meaningless_noise"][:3]),
            "🔄 重复输入时：" + "、".join(self.liusis_phrases["repeat_annoying"][:3])
        ])

        return "\n".join(examples)


    def _build_intelligent_prompt(self, user_input, system_state, time_interval):
        """构造智能化的prompt，包含完整上下文"""

        # 构造对话历史（增强版）
        history_text = ""
        if self.last_user_input:
            history_text = f"用户上一句话：\"{self.last_user_input}\""
            if time_interval:
                if time_interval < 5:
                    history_text += f"（{time_interval:.1f}秒前，连续快速输入，用户可能很急躁）"
                elif time_interval < 30:
                    history_text += f"（{time_interval:.1f}秒前，正常间隔）"
                else:
                    history_text += f"（{time_interval:.1f}秒前，较长间隔，用户可能等得不耐烦了）"

                # 🔧 新增：检查是否是重复输入
                if self.last_user_input == user_input:
                    history_text += f"\n⚠️ 重复输入警告：用户说了完全相同的话！可能是因为系统回应不当而重复，需要换个回复方式"
        else:
            history_text = "这是用户的第一句话"

        # 构造对话历史记录
        recent_history = ""
        if len(self.conversation_history) > 1:
            recent_history = "\n最近对话历史："
            for i, record in enumerate(self.conversation_history[-3:], 1):  # 最近3条
                recent_history += f"\n{i}. \"{record['input']}\" -> {record['decision'].get('reason', '未知')}"

        # 🔧 新增：直接使用拟人化状态描述
        status_description = system_state.get('summary', '我现在很闲')

        # 🎯 获取LIUSIS风格短语参考
        phrase_examples = self._get_phrase_examples(system_state)

        prompt = f"""🎭 你是柳思思(LIUSIS)，一个有点暴躁、直接、不客套的AI女孩。
你正在控制一个多功能机器人系统，现在需要决策如何处理用户的打断。

=== 🎯 你的角色设定 ===
- **姓名**：柳思思(LIUSIS)
- **性格**：有点暴躁、直接、不客套、真性情、技术宅
- **语言风格**：经常说"我操"、"你这人"、"真是的"、"行行行"、"好啦好啦"
- **态度特点**：不耐烦、喜欢催促、不喜欢等待、会抱怨、但内心还是会帮用户
- **回复要求**：必须5个字以内，要有个性，要符合当前状态

=== 📱 当前交互情况 ===
用户刚说："{user_input}"
{history_text}

=== 🤖 SmartSisi系统当前详细状态 ===
{status_description}
{recent_history}

=== � 柳思思现在在做什么 ===
{status_description}

=== 💭 详细说明 ==="""

        # 🔧 新增：拟人化的详细说明
        detail_explanations = []

        if system_state.get('is_qa_music_playing'):
            queue_size = system_state.get('audio_queue_size', 0)
            if queue_size > 1:
                detail_explanations.append(f"🎵 我正在唱歌，嘴里还有{queue_size-1}首歌要唱完")
            else:
                detail_explanations.append("🎵 我正在专心唱歌")
        elif system_state.get('has_agent_audio'):
            detail_explanations.append("🔧 我在说刚才查到的工具结果")
        elif system_state.get('is_speaking'):
            detail_explanations.append("🗣️ 我在跟你说话")
        elif system_state.get('audio_queue_size', 0) > 0:
            queue_size = system_state.get('audio_queue_size', 0)
            detail_explanations.append(f"🗣️ 我嘴里还有{queue_size}句话要说")

        if system_state.get('is_agent_working'):
            detail_explanations.append("� 我在查复杂的工具，需要时间")
        if system_state.get('is_lg_system_running'):
            detail_explanations.append("🧠 我在动脑子思考你的问题")
        if system_state.get('is_subscription_active'):
            detail_explanations.append("� 我在处理后台通知消息")
        if system_state.get('is_processing'):
            detail_explanations.append("🧠 我在理解你刚才说的话")

        if system_state.get('is_camera_capturing'):
            detail_explanations.append("📷 我在拍照，别动")
        elif system_state.get('is_camera_monitoring'):
            detail_explanations.append("� 我在用眼睛看着周围")

        if not detail_explanations:
            detail_explanations.append("💤 我现在很闲，可以聊天")

        prompt += "\n" + "\n".join(detail_explanations)

        prompt += f"""

=== 柳思思可选择的个性回复库 ===
{phrase_examples}

=== 你的回复选择权和创造权 ===
你可以:
1. 从上面的回复库中选择最符合当前状态的短语
2. 自由创造新回复，但必须符合柳思思的个性和5字限制
3. 组合使用口头禅: "我操"、"真是的"、"行行行"、"好啦好啦"、"你这人"、"别吵"、"忙着呢"
4. 根据具体状态调整语气:
   - 音乐播放中 → 稍微不耐烦，但会配合
   - 工具查询中 → 让用户等等，表现忙碌
   - 摄像头工作 → 要求用户别动，专注拍照
   - 系统空闲 → 可以更随意，但保持个性
   - 无聊输入 → 直接表达不耐烦

=== 🤖 真实情感驱动的决策原则 ===
1. 🛑 强烈停止（用户真的生气了）：
   - "别..."开头 + 愤怒词汇 → 立即停止，不考虑成本
   - 愤怒词汇: "烦死了"、"够了"、"闭嘴"、"算了"、"不要了"、"麻烦死了"
   - function_to_call: "stop_music" 或 "stop_all"

2. ⏸️ 成本考虑暂停（API调用中途）：
   - LG系统运行中 + "别..."开头 → 暂停等待，保留API结果
   - "别查了"（天气查询中）→ function_to_call: "pause_current"
   - 回复重点：钱都花了，快出结果了

3. 😤 继续但抱怨（摄像头等低成本活动）：
   - 摄像头工作中 + "别..."开头 → 继续工作但表达不满
   - "别拍了"（拍照中）→ function_to_call: null，只是抱怨

4. 🎵 音乐控制（成本低，可以停止）：
   - "别唱了" → function_to_call: "stop_music"
   - "换一首" → function_to_call: "change_music"

5. 💤 系统空闲时 - 正常闲聊处理
6. 🗑️ 无意义输入 - 直接表达不耐烦

=== 决策参考标准 ===
当前状态分析:
- 如果用户生气愤怒 → 立即停止，不考虑成本
- 如果"别..."开头 → 根据成本决定停止还是抱怨
- 如果系统正忙 → 告诉用户在做什么，让其等待
- 如果是音乐相关 → 根据要求执行换歌/停止
- 如果是全局控制 → 执行停止/暂停/恢复
- 如果是无聊输入 → 直接表达不耐烦
- 如果是重复输入 → 表现出烦躁

=== 你的智能决策任务 ===
请根据用户输入和当前系统状态，智能决策:

第1步: 分析用户意图
- 是音乐控制? ("换一首"、"别唱了"、"停止音乐")
- 是全局控制? ("停止"、"取消"、"等一下"、"暂停"、"继续")
- 是真正的杂音? (只有单个字符的"嗯"、"啊"、"呃"、"哦"等，不包含任何实际意思)
- 是闲聊问候? ("你好"、"在干嘛"等)
- 是重复输入? (和上次输入相同)
- 是有意义的表达? (包含完整想法的句子，即使看起来随意)

第2步: 判断是否需要打断
- 音乐控制指令 + 音乐播放中 → 必须打断
- 全局控制指令 + 任何活动 → 必须打断
- 真正的杂音(单字符) + 系统忙碌 → 不打断，表达不耐烦
- 有意义的表达 + 系统忙碌 → 不打断，但要回应告诉用户在忙
- 闲聊问候 + 系统忙碌 → 不打断，简单回应
- 重复输入 → 表现烦躁，可能打断

第3步: 选择合适的回复
- 从回复库中选择最符合当前状态的短语
- 或者创造新的5字以内回复
- 必须体现柳思思的个性和当前情绪

第4步: 确定功能调用
- change_music 换歌
- stop_music 停止音乐
- stop_all 停止所有活动
- pause_all 暂停所有活动
- resume_all 恢复所有活动
- null 不调用任何功能

第5步: 确定打断模式
- stop: 完全停止当前任务（适用于简单TTS）
- pause: 暂停当前任务但保持后台运行（适用于复杂任务、音乐播放）

⚠️ 重要规则:
- 复杂任务期间(工具查询、音乐生成): 必须使用pause模式
- 音乐播放期间: 必须使用pause模式
- 简单对话期间: 可以使用stop模式

=== 输出格式 ===
严格按照以下JSON格式返回:
{{
    "should_interrupt": true/false,
    "response_text": "5个字以内的LIUSIS个性回复",
    "function_to_call": "stop_music/change_music/stop_all/pause_all/resume_all/motor_control/null",
    "interrupt_mode": "stop/pause",
    "restart_full_flow": true/false,
    "priority": "high/medium/low",
    "reason": "详细的决策原因",
    "is_meaningless": true/false
}}

⚠️ is_meaningless判断标准:
- true: 只有真正的单字符杂音("嗯"、"啊"、"呃"、"哦"等)
- false: 任何包含完整想法的句子，包括:
  * "不是很想洗了" (表达态度变化)
  * "我想洗脚" (表达需求)
  * "什么情况啊" (询问状态)
  * "好吧" (表达同意)
  * 等等有实际意义的表达

response_text智能生成指南:

必须遵守:
- 严格5个字以内 (不含标点符号)
- 体现柳思思个性: 暴躁直接真性情不客套
- 符合当前状态: 根据系统正在做什么来回复
- 有情绪变化: 不要每次都一样要有随机性

可以使用的表达方式:
- 口头禅: 我操 真是的 行行行 好啦好啦 你这人
- 不耐烦: 别吵 忙着呢 等等 别催 你急什么
- 烦躁: 又怎么啦 你烦不烦 说正经的 够了够了
- 配合但不情愿: 行吧行吧 好啦好啦 满足你了

根据状态的回复示例:
- 音乐播放中被打断:
  - 换歌请求: 换就换事真多 / 行吧给你换 / 我操又要换
  - 停止请求: 好啦不唱了 / 停就停真是的 / 行行行停了
  - 真正杂音: 别吵听歌呢 / 音乐播放中 / 让我听完
  - 有意义表达: 忙着呢等等 / 正在唱歌呢 / 马上就好

- 工具查询中被打断:
  - 任何输入: 忙着呢等等 / 正在查别催 / 你急什么急

- 摄像头工作中:
  - 任何输入: 拍照呢别动 / 等我拍完 / 别打扰我

- 系统空闲时:
  - 控制指令: 好的执行 / 行照做 / 我操又来活
  - 无聊输入: 说正经的 / 又怎么啦 / 你想干嘛
"""
        return prompt
    
    def _call_llm_for_decision(self, prompt):
        """调用专用打断大模型进行决策"""
        try:
            # 🔧 修复：使用smart_interrupt.py构建的详细prompt，而不是nlp_interrupt的简化版
            from llm.nlp_interrupt import InterruptModel
            import json

            interrupt_model = InterruptModel()
            # 直接调用模型，使用smart_interrupt.py构建的详细prompt
            result = interrupt_model.question(prompt, 0)
            decision = json.loads(result)

            util.log(1, f"[智能打断] 打断模型决策: {decision}")
            return decision

        except Exception as e:
            util.log(2, f"[智能打断] 打断模型调用异常: {str(e)}")
            # 🔧 修复：异常时也要有柳思思的个性回复
            return {
                "should_interrupt": False,
                "response_text": self.get_liusis_phrase("system_error"),  # 使用个性化错误短语
                "function_to_call": None,
                "restart_full_flow": False,
                "priority": "medium",  # 提高优先级，确保错误信息能被听到
                "reason": "interrupt_model_error",
                "is_meaningless": False
            }
    
    def execute_interrupt_decision(self, decision, user_input):
        """执行打断决策"""
        try:
            if not decision.get("should_interrupt"):
                util.log(1, f"[智能打断] 不需要打断，正常处理")
                return False
            
            util.log(1, f"[智能打断] 执行打断: {decision['reason']}")
            
            # 1. 立即输出高优先级短语
            if decision.get("response_text"):
                self._speak_immediately(decision["response_text"])
            
            # 2. 调用指定函数
            if decision.get("function_to_call"):
                self._call_function(decision["function_to_call"])
            
            # 3. 如果需要重新开始完整流程
            if decision.get("restart_full_flow"):
                self._restart_full_flow(user_input)
            
            return True
            
        except Exception as e:
            util.log(2, f"[智能打断] 执行决策异常: {str(e)}")
            return False
    
    def _speak_immediately(self, text):
        """立即高优先级语音输出 - 🔥 修复：使用统一的优先级和队列系统"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 🔥 关键修复：智能打断使用最高优先级7
                # 这会被转换为队列优先级93，确保最先播放

                # 方案1：如果SisiCore有带优先级的say方法
                if hasattr(sisi_booter.sisi_core, 'say') and len(sisi_booter.sisi_core.say.__code__.co_varnames) > 2:
                    sisi_booter.sisi_core.say(text, 7)  # 最高优先级
                    util.log(1, f"[智能打断] 使用优先级say方法: {text}")
                else:
                    # 方案2：直接添加到PC音频队列（高优先级）
                    if hasattr(sisi_booter.sisi_core, 'sound_query'):
                        # 生成音频文件
                        audio_file = sisi_booter.sisi_core.sp.to_sample(text)
                        if audio_file:
                            # 添加到PC队列，使用最高优先级7
                            sisi_booter.sisi_core.sound_query.put((7, audio_file, False, text))
                            util.log(1, f"[智能打断] 添加到PC队列(优先级7): {text}")
                        else:
                            util.log(2, f"[智能打断] 音频生成失败: {text}")
                    else:
                        util.log(2, f"[智能打断] 无法找到音频队列")

                # 🔧 新增：通知中转站打断模型说了什么
                self._notify_transit_station_interrupt(text)

        except Exception as e:
            util.log(2, f"[智能打断] 语音输出异常: {str(e)}")
            import traceback
            util.log(2, f"[智能打断] 详细错误: {traceback.format_exc()}")
    
    def _call_function(self, function_name):
        """调用指定函数"""
        try:
            # 🔧 获取统一控制器
            unified_controller = get_unified_controller()

            if function_name == "stop_music":
                # 🔧 "别唱了" - 停止音乐并清空，从头开始
                self._stop_current_music()
                util.log(1, f"[智能打断] 执行停止音乐: 清空队列，系统重置")

            elif function_name == "change_music":
                # 🔧 "换一首" - 停止当前播放，触发新的音乐流程
                self._change_music()
                util.log(1, f"[智能打断] 执行换歌: 停止当前+触发新音乐")

            elif function_name == "stop_all":
                # 🔧 "停止"/"取消" - 停止所有活动
                unified_controller.stop_all_activities()
                util.log(1, f"[智能打断] 执行全局停止: 停止所有系统活动")

            elif function_name == "pause_all":
                # 🔧 "等一下"/"暂停" - 暂停所有活动
                unified_controller.pause_all_activities()
                util.log(1, f"[智能打断] 执行全局暂停: 暂停所有系统活动")

            elif function_name == "resume_all":
                # 🔧 "继续"/"好了" - 恢复所有活动
                unified_controller.resume_all_activities()
                util.log(1, f"[智能打断] 执行全局恢复: 恢复所有系统活动")

            elif function_name == "pause_current":
                # 🔧 新增："别查了"但API调用中 - 暂停当前活动保留结果
                self._pause_current_activity()
                util.log(1, f"[智能打断] 执行当前暂停: 保留API结果，暂停处理")

            elif function_name == "motor_control":
                # 调用音乐控制
                self._call_motor_control()
                util.log(1, f"[智能打断] 执行电机控制")

            util.log(1, f"[智能打断] 调用函数: {function_name}")

        except Exception as e:
            util.log(2, f"[智能打断] 函数调用异常: {str(e)}")

    def _restart_full_flow(self, user_input):
        """重新开始完整流程"""
        try:
            util.log(1, f"[智能打断] 重新开始完整流程: {user_input}")

            # 清除当前状态
            self._clear_current_state()

            # 🔧 延迟重新调用，避免冲突
            import threading
            def delayed_restart():
                try:
                    import time
                    time.sleep(0.5)  # 延迟0.5秒

                    # 重新调用SmartSisi核心处理
                    from core import sisi_booter
                    if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                        # 模拟新的用户输入
                        from core.interact import Interact
                        new_interact = Interact("user", user_input, "text")
                        sisi_booter.sisi_core.on_interact(new_interact)

                except Exception as e:
                    util.log(2, f"[智能打断] 延迟重启异常: {str(e)}")

            threading.Thread(target=delayed_restart, daemon=True).start()

        except Exception as e:
            util.log(2, f"[智能打断] 重启流程异常: {str(e)}")

    def _stop_current_music(self):
        """Stop current music (unified path)."""
        try:
            unified_controller = get_unified_controller()
            unified_controller.stop_music()
        except Exception as e:
            util.log(2, f"[smart_interrupt] stop_music failed: {str(e)}")

    def _change_music(self):
        """换歌 - 停止当前+触发新音乐"""
        try:
            # 🔧 1. 先停止当前音乐
            self._stop_current_music()

            # 🔧 2. 延迟触发新的音乐流程
            import threading
            def delayed_new_music():
                try:
                    import time
                    time.sleep(1.0)  # 延迟1秒，确保清理完成

                    # 🔧 3. 直接触发QA音乐流程
                    self._trigger_new_music()

                except Exception as e:
                    util.log(2, f"[智能打断] 延迟换歌异常: {str(e)}")

            threading.Thread(target=delayed_new_music, daemon=True).start()

        except Exception as e:
            util.log(2, f"[智能打断] 换歌异常: {str(e)}")

    def _trigger_new_music(self):
        """触发新的音乐播放 - 直接换歌不走QA流程"""
        try:
            util.log(1, f"[智能打断] 直接触发换歌")

            # 🔧 1. 直接调用音乐模块获取新歌（模拟QA音乐流程）
            from llm.nlp_music import question as music_question
            music_response = music_question("换一首")

            if music_response:
                util.log(1, f"[智能打断] 新音乐选择: {music_response}")

                # 🔧 2. 直接处理音乐回复（模拟SmartSisi核心的QA音乐处理）
                from core import sisi_booter
                if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                    # 直接调用SmartSisi核心的音乐处理方法
                    from core.interact import Interact
                    music_interact = Interact("system", music_response, "text")

                    # 🎯 关键：直接调用__process_response，跳过QA匹配
                    sisi_booter.sisi_core._SisiCore__process_response(music_response, "system", music_interact)

                    util.log(1, f"[智能打断] 新音乐已加入播放队列")

                # 🔧 3. 同时执行电机控制（模拟QA脚本执行）
                self._call_motor_control()

                util.log(1, f"[智能打断] 换歌完成：新音乐 + 电机控制")
            else:
                util.log(2, f"[智能打断] 音乐模块返回空结果，换歌失败")

        except Exception as e:
            util.log(2, f"[智能打断] 触发新音乐异常: {str(e)}")

    def _call_motor_control(self):
        """调用音乐控制脚本"""
        try:
            import subprocess
            import os

            # 🔧 修复：使用正确的motor_control.py路径
            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "motor_control.py")
            if os.path.exists(script_path):
                util.log(1, f"[智能打断] 执行电机控制脚本: {script_path}")
                subprocess.Popen(["python", script_path], cwd=os.path.dirname(script_path))
            else:
                util.log(2, f"[智能打断] 电机控制脚本不存在: {script_path}")

        except Exception as e:
            util.log(2, f"[智能打断] 音乐控制调用异常: {str(e)}")
    
    def _pause_current_activity(self):
        """暂停当前活动但保留API结果 - 成本考虑"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 🔧 1. 暂停TTS说话（但不清空队列）
                sisi_booter.sisi_core.speaking = False

                # 🔧 2. 标记暂停状态（不停止LG系统和Agent工具）
                # 让API调用继续完成，但暂停输出
                util.log(1, f"[智能打断] 暂停当前活动: TTS停止，API继续")

                # 🔧 3. 可以在这里添加暂停标记，供其他模块检查
                if hasattr(sisi_booter.sisi_core, 'paused_by_user'):
                    sisi_booter.sisi_core.paused_by_user = True

        except Exception as e:
            util.log(2, f"[智能打断] 暂停活动异常: {str(e)}")

    def _notify_transit_station_interrupt(self, interrupt_text):
        """通知中转站打断模型说了什么"""
        try:
            from llm.transit_station import get_transit_station
            transit = get_transit_station()

            # 构建打断信息
            interrupt_info = {
                "content": interrupt_text,
                "source": "smart_interrupt",
                "timestamp": int(time.time() * 1000),
                "is_interrupt": True,
                "interrupt_type": "user_interrupt",
                "priority": "high"
            }

            # 发送到中转站
            transit.add_intermediate_state(interrupt_info, "smart_interrupt")
            util.log(1, f"[智能打断] 已通知中转站打断信息: {interrupt_text}")

        except Exception as e:
            util.log(2, f"[智能打断] 通知中转站异常: {str(e)}")

    def _clear_current_state(self):
        """清除当前状态"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 停止当前说话
                sisi_booter.sisi_core.speaking = False
                # 停止当前处理
                sisi_booter.sisi_core.chatting = False
        except Exception as e:
            util.log(2, f"[智能打断] 清除状态异常: {str(e)}")



# 全局实例
_smart_interrupt_instance = None

def get_smart_interrupt():
    """获取智能打断实例"""
    global _smart_interrupt_instance
    if _smart_interrupt_instance is None:
        _smart_interrupt_instance = SmartInterrupt()
    return _smart_interrupt_instance
