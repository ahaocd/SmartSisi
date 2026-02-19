#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一打断管理器
负责处理所有类型的用户打断请求，与现有优先级系统集成
"""

import time
import threading
from utils import util

class SisiInterruptManager:
    """SmartSisi统一打断管理器"""
    
    def __init__(self):
        self.interrupt_lock = threading.Lock()
        
        # 打断优先级定义（基于现有TTS优先级系统）
        self.PRIORITY_LEVELS = {
            "emergency_stop": 7,      # 紧急停止
            "immediate_interrupt": 6,  # 立即打断
            "high_priority": 5,       # 高优先级打断
            "normal_interrupt": 4,    # 普通打断
            "queue_after_current": 3, # 排队等待
            "low_priority": 2         # 低优先级
        }
        
        # 打断类型映射
        self.INTERRUPT_TYPES = {
            "stop_all": "emergency_stop",
            "music_change": "high_priority", 
            "busy_response": "normal_interrupt",
            "normal_request": "queue_after_current"
        }
    
    def register_qa_interrupt(self, interrupt_result):
        """
        注册QA系统的打断请求
        
        Args:
            interrupt_result (dict): QA系统返回的打断结果
            
        Returns:
            bool: 是否成功处理打断
        """
        if not interrupt_result.get("should_interrupt"):
            return False
        
        try:
            with self.interrupt_lock:
                interrupt_type = interrupt_result.get("interrupt_type", "normal_request")
                priority = self._get_priority_for_type(interrupt_type)
                
                util.log(1, f"[打断管理器] 注册QA打断: 类型={interrupt_type}, 优先级={priority}")
                
                # 执行打断处理
                return self._execute_interrupt(
                    response_text=interrupt_result.get("response", ""),
                    action=interrupt_result.get("action", ""),
                    priority=priority,
                    interrupt_type=interrupt_type
                )
                
        except Exception as e:
            util.log(2, f"[打断管理器] 注册QA打断失败: {str(e)}")
            return False
    
    def _get_priority_for_type(self, interrupt_type):
        """根据打断类型获取优先级"""
        priority_key = self.INTERRUPT_TYPES.get(interrupt_type, "normal_interrupt")
        return self.PRIORITY_LEVELS.get(priority_key, 4)
    
    def _execute_interrupt(self, response_text, action, priority, interrupt_type):
        """
        执行打断操作
        
        Args:
            response_text (str): 响应文本
            action (str): 执行动作
            priority (int): 优先级
            interrupt_type (str): 打断类型
            
        Returns:
            bool: 是否成功执行
        """
        try:
            # 1. 处理特殊打断类型
            if interrupt_type == "stop_current":
                return self._handle_stop_interrupt()
            
            # 2. 处理音乐换歌打断
            elif interrupt_type == "music_change":
                return self._handle_music_change_interrupt(response_text, action, priority)
            
            # 3. 处理忙碌响应打断
            elif interrupt_type == "busy_response":
                return self._handle_busy_response_interrupt(response_text, priority)
            
            # 4. 处理普通打断
            else:
                return self._handle_normal_interrupt(response_text, action, priority)
                
        except Exception as e:
            util.log(2, f"[打断管理器] 执行打断失败: {str(e)}")
            return False
    
    def _handle_stop_interrupt(self):
        """处理停止打断"""
        try:
            from core import sisi_booter
            
            if hasattr(sisi_booter, 'sisi_core'):
                # 清空音频队列
                if hasattr(sisi_booter.sisi_core, 'sound_query'):
                    while not sisi_booter.sisi_core.sound_query.empty():
                        try:
                            sisi_booter.sisi_core.sound_query.get_nowait()
                        except:
                            break
                
                # 停止当前播放
                sisi_booter.sisi_core.speaking = False
                sisi_booter.sisi_core.chatting = False
                
                util.log(1, f"[打断管理器] 停止打断执行完成")
                return True
                
        except Exception as e:
            util.log(2, f"[打断管理器] 停止打断失败: {str(e)}")
            return False
    
    def _handle_music_change_interrupt(self, response_text, action, priority):
        """处理音乐换歌打断"""
        try:
            # 1. 先发送响应
            self._inject_high_priority_tts(response_text, priority)
            
            # 2. 清除当前音乐队列中的音乐文件
            self._clear_music_from_queue()
            
            # 3. 触发新的音乐选择
            if action == "motor_control.py":
                from scheduler.thread_manager import MyThread
                MyThread(target=self._trigger_music_script, args=[action]).start()
            
            util.log(1, f"[打断管理器] 音乐换歌打断执行完成")
            return True
            
        except Exception as e:
            util.log(2, f"[打断管理器] 音乐换歌打断失败: {str(e)}")
            return False
    
    def _handle_busy_response_interrupt(self, response_text, priority):
        """处理忙碌响应打断"""
        try:
            # 直接发送忙碌响应，不影响当前任务
            self._inject_high_priority_tts(response_text, priority)
            
            util.log(1, f"[打断管理器] 忙碌响应打断执行完成")
            return True
            
        except Exception as e:
            util.log(2, f"[打断管理器] 忙碌响应打断失败: {str(e)}")
            return False
    
    def _handle_normal_interrupt(self, response_text, action, priority):
        """处理普通打断"""
        try:
            # 发送响应
            self._inject_high_priority_tts(response_text, priority)
            
            # 执行相关动作
            if action and action.endswith('.py'):
                from scheduler.thread_manager import MyThread
                MyThread(target=self._trigger_script, args=[action]).start()
            
            util.log(1, f"[打断管理器] 普通打断执行完成")
            return True
            
        except Exception as e:
            util.log(2, f"[打断管理器] 普通打断失败: {str(e)}")
            return False
    
    def _inject_high_priority_tts(self, text, priority):
        """注入高优先级TTS到音频队列"""
        try:
            from core import sisi_booter
            
            if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'sp'):
                # 生成TTS音频
                audio_file = sisi_booter.sisi_core.sp.to_sample(text, "normal")
                if audio_file and hasattr(sisi_booter.sisi_core, 'sound_query'):
                    # 使用高优先级插入队列
                    sisi_booter.sisi_core.sound_query.put((priority, audio_file, False))
                    util.log(1, f"[打断管理器] 高优先级TTS已注入: {text[:30]}..., 优先级: {priority}")
                    return True
                    
        except Exception as e:
            util.log(2, f"[打断管理器] 注入高优先级TTS失败: {str(e)}")
            return False
    
    def _clear_music_from_queue(self):
        """清除音频队列中的音乐文件"""
        try:
            from core import sisi_booter
            
            if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'sound_query'):
                queue = sisi_booter.sisi_core.sound_query
                non_music_items = []
                
                # 取出所有非音乐文件
                while not queue.empty():
                    item = queue.get()
                    audio_file = str(item[1]) if len(item) > 1 else ""
                    if not ('music_' in audio_file or 'random_generation_music' in audio_file):
                        non_music_items.append(item)
                
                # 重新放入非音乐文件
                for item in non_music_items:
                    queue.put(item)
                
                util.log(1, f"[打断管理器] 已清除音频队列中的音乐文件")
                
        except Exception as e:
            util.log(2, f"[打断管理器] 清除音乐文件失败: {str(e)}")
    
    def _trigger_script(self, script_name):
        """触发脚本执行"""
        try:
            if script_name == "motor_control.py":
                import motor_control
                motor_control.main()
            else:
                util.log(1, f"[打断管理器] 未知脚本: {script_name}")
                
        except Exception as e:
            util.log(2, f"[打断管理器] 触发脚本失败: {str(e)}")
    
    def _trigger_music_script(self, script_name):
        """触发音乐脚本执行"""
        self._trigger_script(script_name)

# 全局实例
_interrupt_manager_instance = None

def get_interrupt_manager():
    """获取打断管理器实例"""
    global _interrupt_manager_instance
    if _interrupt_manager_instance is None:
        _interrupt_manager_instance = SisiInterruptManager()
    return _interrupt_manager_instance