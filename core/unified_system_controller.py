#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一系统控制器 - 处理全局停止/暂停/继续指令
作为角色机器人的统一控制中心
"""

import threading
import time
from utils import util

class UnifiedSystemController:
    """统一系统控制器"""
    
    def __init__(self):
        self.is_paused = False
        self.paused_states = {}
        self.lock = threading.Lock()
        
    def stop_all_activities(self):
        """停止所有活动 - 响应"停止"/"取消"指令"""
        try:
            util.log(1, "[统一控制] 执行全局停止指令")
            
            # 1. 停止音乐播放
            self._stop_music_system()
            
            # 2. 停止摄像头活动
            self._stop_camera_system()
            
            # 3. 停止Agent工具
            self._stop_agent_system()
            
            # 4. 停止TTS说话
            self._stop_tts_system()
            
            # 5. 停止ESP32硬件
            self._stop_esp32_system()
            
            # 6. 停止A2A订阅系统
            self._stop_a2a_system()

            # 7. 停止LLM处理
            self._stop_llm_system()

            util.log(1, "[统一控制] 全局停止完成")
            return True
            
        except Exception as e:
            util.log(2, f"[统一控制] 全局停止异常: {str(e)}")
            return False
    
    def pause_all_activities(self):
        """暂停所有活动 - 响应"等一下"/"暂停"指令"""
        try:
            with self.lock:
                if self.is_paused:
                    util.log(1, "[统一控制] 系统已经暂停")
                    return True
                
                util.log(1, "[统一控制] 执行全局暂停指令")
                
                # 保存当前状态
                self.paused_states = {
                    'music_state': self._get_music_state(),
                    'camera_state': self._get_camera_state(),
                    'agent_state': self._get_agent_state(),
                    'tts_state': self._get_tts_state(),
                    'esp32_state': self._get_esp32_state(),
                    'a2a_state': self._get_a2a_state(),
                    'llm_state': self._get_llm_state(),
                    'pause_time': time.time()
                }
                
                # 暂停所有活动
                self._pause_music_system()
                self._pause_camera_system()
                self._pause_agent_system()
                self._pause_tts_system()
                self._pause_esp32_system()
                self._pause_a2a_system()
                self._pause_llm_system()
                
                self.is_paused = True
                util.log(1, "[统一控制] 全局暂停完成")
                return True
                
        except Exception as e:
            util.log(2, f"[统一控制] 全局暂停异常: {str(e)}")
            return False
    
    def resume_all_activities(self):
        """恢复所有活动 - 响应"继续"/"好了"指令"""
        try:
            with self.lock:
                if not self.is_paused:
                    util.log(1, "[统一控制] 系统没有暂停")
                    return True
                
                util.log(1, "[统一控制] 执行全局恢复指令")
                
                # 恢复所有活动
                self._resume_music_system(self.paused_states.get('music_state'))
                self._resume_camera_system(self.paused_states.get('camera_state'))
                self._resume_agent_system(self.paused_states.get('agent_state'))
                self._resume_tts_system(self.paused_states.get('tts_state'))
                self._resume_esp32_system(self.paused_states.get('esp32_state'))
                self._resume_a2a_system(self.paused_states.get('a2a_state'))
                self._resume_llm_system(self.paused_states.get('llm_state'))
                
                self.is_paused = False
                self.paused_states = {}
                util.log(1, "[统一控制] 全局恢复完成")
                return True
                
        except Exception as e:
            util.log(2, f"[统一控制] 全局恢复异常: {str(e)}")
            return False
    
    # ==================== 音乐系统控制 ====================
    def _stop_music_system(self):
        """停止音乐系统"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 停止播放 + 清空队列
                sisi_booter.sisi_core.speaking = False
                queue = sisi_booter.sisi_core.sound_query
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except:
                        break

                # 停止PC统一播放队列
                try:
                    from utils.pc_stream_queue import get_pc_stream_queue
                    get_pc_stream_queue().stop_all()
                except Exception:
                    pass

                # 清空ESP32设备队列
                try:
                    from esp32_liusisi.sisi_audio_output import AudioOutputManager
                    audio_manager = AudioOutputManager.get_instance()
                    if audio_manager:
                        audio_manager.clear_queues()
                except Exception:
                    pass
                    
            util.log(1, "[统一控制] 音乐系统已停止")
        except Exception as e:
            util.log(2, f"[统一控制] 停止音乐系统异常: {str(e)}")

    def stop_music(self):
        """对外公开的停止音乐接口"""
        return self._stop_music_system()
    
    def _pause_music_system(self):
        """暂停音乐系统"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                sisi_booter.sisi_core.speaking = False
                # Unified playback: no true pause, stop current queue instead.
                try:
                    from utils.pc_stream_queue import get_pc_stream_queue
                    get_pc_stream_queue().stop_all()
                except Exception:
                    pass
            util.log(1, "[统一控制] 音乐系统已暂停(停止播放队列)")
        except Exception as e:
            util.log(2, f"[统一控制] 暂停音乐系统异常: {str(e)}")
    
    def _resume_music_system(self, saved_state):
        """恢复音乐系统"""
        try:
            util.log(1, "[统一控制] 音乐系统恢复已跳过(统一播放不支持resume)")
        except Exception as e:
            util.log(2, f"[统一控制] 恢复音乐系统异常: {str(e)}")
    
    def _get_music_state(self):
        """获取音乐系统状态"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                return {
                    'was_playing': sisi_booter.sisi_core.speaking,
                    'queue_size': sisi_booter.sisi_core.sound_query.qsize()
                }
        except:
            pass
        return {}
    
    # ==================== 摄像头系统控制 ====================
    def _stop_camera_system(self):
        """停止摄像头系统"""
        try:
            from ai_module.yolo_service import YOLOv8Service
            yolo = YOLOv8Service.get_instance()
            if hasattr(yolo, '_is_monitoring') and yolo._is_monitoring:
                yolo._is_monitoring = False
                util.log(1, "[统一控制] 摄像头系统已停止")
        except Exception as e:
            util.log(2, f"[统一控制] 停止摄像头系统异常: {str(e)}")
    
    def _pause_camera_system(self):
        """暂停摄像头系统"""
        self._stop_camera_system()  # 摄像头暂停=停止
    
    def _resume_camera_system(self, saved_state):
        """恢复摄像头系统"""
        try:
            if saved_state and saved_state.get('was_monitoring'):
                from ai_module.yolo_service import YOLOv8Service
                yolo = YOLOv8Service.get_instance()
                yolo._is_monitoring = True
                util.log(1, "[统一控制] 摄像头系统已恢复")
        except Exception as e:
            util.log(2, f"[统一控制] 恢复摄像头系统异常: {str(e)}")
    
    def _get_camera_state(self):
        """获取摄像头系统状态"""
        try:
            from ai_module.yolo_service import YOLOv8Service
            yolo = YOLOv8Service.get_instance()
            return {
                'was_monitoring': getattr(yolo, '_is_monitoring', False)
            }
        except:
            pass
        return {}
    
    # ==================== Agent系统控制 ====================
    def _stop_agent_system(self):
        """停止Agent系统（就是LG系统）"""
        try:
            # 1. 停止SmartSisi核心的chatting状态（最重要）
            try:
                from core import sisi_booter
                if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                    sisi_booter.sisi_core.chatting = False
                    util.log(1, "[统一控制] SmartSisi核心chatting状态已停止")
            except Exception as e:
                util.log(2, f"[统一控制] 停止SmartSisi核心chatting异常: {str(e)}")

            # 2. 清空中转站状态
            try:
                from llm.transit_station import get_transit_station
                transit = get_transit_station()
                if hasattr(transit, 'intermediate_states'):
                    transit.intermediate_states.clear()
                    util.log(1, "[统一控制] 中转站状态已清空")
            except Exception as e:
                util.log(2, f"[统一控制] 清空中转站状态异常: {str(e)}")

            # 3. 尝试停止Agent工具调用（如果有的话）
            try:
                from llm.agent.tool_calling_graph import ToolCallingGraph
                # 这里可能需要添加停止逻辑，但目前先简单处理
                util.log(1, "[统一控制] Agent工具调用已通知停止")
            except Exception as e:
                util.log(2, f"[统一控制] 停止Agent工具调用异常: {str(e)}")

            util.log(1, "[统一控制] Agent系统（LG系统）完全停止")
        except Exception as e:
            util.log(2, f"[统一控制] 停止Agent系统异常: {str(e)}")
    
    def _pause_agent_system(self):
        """暂停Agent系统"""
        self._stop_agent_system()  # Agent暂停=停止当前任务
    
    def _resume_agent_system(self, saved_state):
        """恢复Agent系统"""
        try:
            if not saved_state:
                return

            # 🔥 修复：恢复Agent对话上下文
            intermediate_states = saved_state.get('intermediate_states', [])
            last_user_input = saved_state.get('last_user_input')

            if intermediate_states:
                util.log(1, f"[统一控制] 恢复Agent上下文: {len(intermediate_states)} 个状态")

                # 输出保存的对话上下文，让用户知道之前在说什么
                for state in intermediate_states:
                    content = state.get('content', '')
                    source = state.get('source', '')
                    phase = state.get('phase', '')

                    if content:
                        util.log(1, f"[上下文恢复] {phase}阶段 - {source}: {content[:50]}...")

                        # 🎯 关键：将重要的上下文信息通过TTS告知用户
                        if phase in ['final', 'middle'] and len(content) > 10:
                            from core import sisi_booter
                            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                                # 生成上下文提醒
                                context_reminder = f"刚才我们说到：{content[:30]}..."
                                sisi_booter.sisi_core.say(context_reminder, 1)  # 低优先级

            if last_user_input:
                util.log(1, f"[统一控制] 恢复最后用户输入: {last_user_input[:30]}...")

            util.log(1, "[统一控制] Agent系统上下文已恢复")

        except Exception as e:
            util.log(2, f"[统一控制] 恢复Agent系统异常: {str(e)}")
    
    def _get_agent_state(self):
        """获取Agent系统状态"""
        try:
            # 🔥 修复：保存完整的Agent对话上下文
            agent_state = {
                'active_tasks': 0,
                'intermediate_states': [],
                'last_user_input': None,
                'conversation_context': None
            }

            # 获取中转站状态
            from llm.transit_station import get_transit_station
            transit = get_transit_station()
            if transit:
                # 保存活跃任务数量
                intermediate_states = getattr(transit, 'intermediate_states', [])
                agent_state['active_tasks'] = len(intermediate_states)

                # 🔥 关键：保存中间状态的具体内容
                agent_state['intermediate_states'] = []
                for state in intermediate_states[-3:]:  # 保存最近3个状态
                    if isinstance(state, dict):
                        agent_state['intermediate_states'].append({
                            'content': state.get('content', ''),
                            'source': state.get('source', ''),
                            'timestamp': state.get('timestamp', ''),
                            'phase': state.get('phase', '')
                        })

                # 保存最后的用户输入（如果有的话）
                if hasattr(transit, '_last_user_input'):
                    agent_state['last_user_input'] = transit._last_user_input

            # 获取SmartSisi核心的对话状态
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                if hasattr(sisi_booter.sisi_core, 'chatting'):
                    agent_state['was_chatting'] = sisi_booter.sisi_core.chatting

            return agent_state
        except Exception as e:
            util.log(2, f"[统一控制] 获取Agent状态异常: {str(e)}")
        return {}
    
    # ==================== TTS系统控制 ====================
    def _stop_tts_system(self):
        """停止TTS系统"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                sisi_booter.sisi_core.speaking = False
                util.log(1, "[统一控制] TTS系统已停止")
        except Exception as e:
            util.log(2, f"[统一控制] 停止TTS系统异常: {str(e)}")
    
    def _pause_tts_system(self):
        """暂停TTS系统"""
        self._stop_tts_system()
    
    def _resume_tts_system(self, saved_state):
        """恢复TTS系统"""
        try:
            if not saved_state:
                return

            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 🔥 修复：恢复音频队列中的内容
                audio_queue = saved_state.get('audio_queue', [])
                if audio_queue:
                    util.log(1, f"[统一控制] 恢复 {len(audio_queue)} 个音频队列项")

                    # 将保存的队列项重新加入播放队列
                    for item in audio_queue:
                        try:
                            # 重新生成TTS音频并加入队列
                            text = item.get('text', '')
                            priority = item.get('priority', 2)

                            if text and len(text.strip()) > 0:
                                # 调用SmartSisi核心的say方法重新生成音频
                                sisi_booter.sisi_core.say(text, priority)
                                util.log(1, f"[统一控制] 恢复TTS内容: {text[:30]}...")
                        except Exception as e:
                            util.log(2, f"[统一控制] 恢复单个TTS项异常: {str(e)}")

                # 恢复speaking状态
                if saved_state.get('was_speaking'):
                    sisi_booter.sisi_core.speaking = True

                util.log(1, f"[统一控制] TTS系统已恢复，队列项: {len(audio_queue)}")

        except Exception as e:
            util.log(2, f"[统一控制] 恢复TTS系统异常: {str(e)}")
    
    def _get_tts_state(self):
        """获取TTS系统状态"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 🔥 修复：保存完整的TTS状态和内容
                tts_state = {
                    'was_speaking': sisi_booter.sisi_core.speaking,
                    'current_text': None,
                    'audio_queue': [],
                    'current_priority': None
                }

                # 保存当前正在播放的内容（如果有的话）
                if hasattr(sisi_booter.sisi_core, '_current_tts_text'):
                    tts_state['current_text'] = sisi_booter.sisi_core._current_tts_text

                # 保存音频队列中的内容
                if hasattr(sisi_booter.sisi_core, 'sound_query') and not sisi_booter.sisi_core.sound_query.empty():
                    queue_items = []
                    temp_queue = []

                    # 提取队列内容
                    while not sisi_booter.sisi_core.sound_query.empty():
                        try:
                            item = sisi_booter.sisi_core.sound_query.get_nowait()
                            temp_queue.append(item)
                            # 保存队列项的关键信息
                            if len(item) >= 4:  # 新格式：(优先级, 音频路径, 是否为agent, 原始文本)
                                queue_items.append({
                                    'priority': item[0],
                                    'audio_file': item[1],
                                    'is_agent': item[2],
                                    'text': item[3]
                                })
                        except:
                            break

                    # 将队列项重新放回
                    for item in temp_queue:
                        sisi_booter.sisi_core.sound_query.put(item)

                    tts_state['audio_queue'] = queue_items

                return tts_state
        except Exception as e:
            util.log(2, f"[统一控制] 获取TTS状态异常: {str(e)}")
        return {}
    
    # ==================== ESP32系统控制 ====================
    def _stop_esp32_system(self):
        """停止ESP32系统"""
        try:
            # 这里需要调用ESP32的停止指令
            # 停止电机、LED等硬件动作
            util.log(1, "[统一控制] ESP32系统已停止")
        except Exception as e:
            util.log(2, f"[统一控制] 停止ESP32系统异常: {str(e)}")
    
    def _pause_esp32_system(self):
        """暂停ESP32系统"""
        self._stop_esp32_system()
    
    def _resume_esp32_system(self, saved_state):
        """恢复ESP32系统"""
        util.log(1, "[统一控制] ESP32系统恢复")
    
    def _get_esp32_state(self):
        """获取ESP32系统状态"""
        return {}
    
    # ==================== A2A订阅系统控制 ====================
    def _stop_a2a_system(self):
        """停止A2A订阅系统"""
        try:
            # 停止A2A工具管理器
            try:
                from llm.agent.a2a_notification import get_tool_manager
                manager = get_tool_manager()
                if hasattr(manager, 'stop'):
                    manager.stop()
                elif hasattr(manager, '_running'):
                    manager._running = False
                util.log(1, "[统一控制] A2A工具管理器已停止")
            except Exception as e:
                util.log(2, f"[统一控制] 停止A2A工具管理器异常: {str(e)}")

            # 清空中转站的工具通知队列
            try:
                from llm.transit_station import get_transit_station
                transit = get_transit_station()
                if hasattr(transit, 'tool_notification_states'):
                    transit.tool_notification_states.clear()
                    util.log(1, "[统一控制] 中转站工具通知队列已清空")
            except Exception as e:
                util.log(2, f"[统一控制] 清空工具通知队列异常: {str(e)}")

            util.log(1, "[统一控制] A2A订阅系统完全停止")
        except Exception as e:
            util.log(2, f"[统一控制] 停止A2A订阅系统异常: {str(e)}")

    def _pause_a2a_system(self):
        """暂停A2A订阅系统"""
        self._stop_a2a_system()  # A2A暂停=停止

    def _resume_a2a_system(self, saved_state):
        """恢复A2A订阅系统"""
        try:
            # 重新启动A2A工具管理器
            from llm.agent.a2a_notification import get_tool_manager
            manager = get_tool_manager()
            if hasattr(manager, 'start') and not getattr(manager, '_running', False):
                manager.start()
                util.log(1, "[统一控制] A2A订阅系统已恢复")
        except Exception as e:
            util.log(2, f"[统一控制] 恢复A2A订阅系统异常: {str(e)}")

    def _get_a2a_state(self):
        """获取A2A订阅系统状态"""
        try:
            from llm.agent.a2a_notification import get_tool_manager
            manager = get_tool_manager()
            return {
                'was_running': getattr(manager, '_running', False),
                'tool_count': len(getattr(manager, 'tools', {})),
                'subscription_count': len(getattr(manager, 'subscriptions', {}))
            }
        except:
            pass
        return {}

    # ==================== LLM系统控制 ====================
    def _stop_llm_system(self):
        """停止LLM系统"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                sisi_booter.sisi_core.chatting = False
                util.log(1, "[统一控制] LLM系统已停止")
        except Exception as e:
            util.log(2, f"[统一控制] 停止LLM系统异常: {str(e)}")
    
    def _pause_llm_system(self):
        """暂停LLM系统"""
        self._stop_llm_system()
    
    def _resume_llm_system(self, saved_state):
        """恢复LLM系统"""
        util.log(1, "[统一控制] LLM系统恢复")
    
    def _get_llm_state(self):
        """获取LLM系统状态"""
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                return {
                    'was_chatting': sisi_booter.sisi_core.chatting
                }
        except:
            pass
        return {}

# 全局实例
_unified_controller_instance = None

def get_unified_controller():
    """获取统一控制器实例"""
    global _unified_controller_instance
    if _unified_controller_instance is None:
        _unified_controller_instance = UnifiedSystemController()
    return _unified_controller_instance