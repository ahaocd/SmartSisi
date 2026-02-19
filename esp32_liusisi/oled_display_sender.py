#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s3cam_display_sender.py - ESP32-S3 CAM显示发送器
# 支持文本交互日志、歌词显示、旋律动画发送到S3-CAM设备

import requests
import json
import time
import logging
import re
import os
from typing import Optional, List, Dict, Any

class S3CAMDisplaySender:
    """ESP32-S3 CAM显示发送器 - 支持歌词、旋律动画、文本交互"""

    def __init__(self, display_ip: str = "172.20.10.2", display_port: int = 80):
        """
        初始化S3-CAM显示发送器

        Args:
            display_ip: S3-CAM设备IP地址
            display_port: HTTP API端口，默认80
        """
        self.display_ip = display_ip
        self.display_port = display_port
        self.base_url = f"http://{display_ip}:{display_port}"

        # 设置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # 歌词和音乐状态
        self.current_lyrics = []
        self.music_start_time = 0
        self.is_music_playing = False

        # 🎯 分层显示数据
        self.display_layers = {
            "foreground": {  # 表层显示（不透明）
                "user_speech": "",
                "sisi_response": "",
                "current_song": "",
                "system_status": ""
            },
            "background": {  # 背景层显示（透明）
                "component_logs": {},  # 每个组件最多2条日志
                "error_logs": []       # 所有错误日志
            }
        }

        # 组件日志计数器
        self.component_log_count = {}
        self.max_logs_per_component = 2

    def add_component_log(self, component: str, message: str, is_error: bool = False):
        """
        添加组件日志到背景层

        Args:
            component: 组件名称 (如 "音乐模块", "语音识别", "TTS")
            message: 日志消息
            is_error: 是否为错误日志
        """
        timestamp = int(time.time() * 1000)
        log_entry = {
            "timestamp": timestamp,
            "message": message,
            "is_error": is_error
        }

        if is_error:
            # 错误日志直接添加到错误列表
            self.display_layers["background"]["error_logs"].append(log_entry)
            # 保持错误日志数量在合理范围内
            if len(self.display_layers["background"]["error_logs"]) > 10:
                self.display_layers["background"]["error_logs"] = \
                    self.display_layers["background"]["error_logs"][-10:]
        else:
            # 普通日志按组件限制数量
            if component not in self.display_layers["background"]["component_logs"]:
                self.display_layers["background"]["component_logs"][component] = []
                self.component_log_count[component] = 0

            # 添加新日志
            self.display_layers["background"]["component_logs"][component].append(log_entry)
            self.component_log_count[component] += 1

            # 保持每个组件最多2条日志
            if self.component_log_count[component] > self.max_logs_per_component:
                self.display_layers["background"]["component_logs"][component] = \
                    self.display_layers["background"]["component_logs"][component][-self.max_logs_per_component:]
                self.component_log_count[component] = self.max_logs_per_component

    def update_foreground_display(self, user_speech: str = None, sisi_response: str = None,
                                 current_song: str = None, system_status: str = None):
        """
        更新表层显示内容

        Args:
            user_speech: 用户说话内容
            sisi_response: SmartSisi回复内容
            current_song: 当前播放歌曲名
            system_status: 系统状态变化
        """
        if user_speech is not None:
            self.display_layers["foreground"]["user_speech"] = user_speech
        if sisi_response is not None:
            self.display_layers["foreground"]["sisi_response"] = sisi_response
        if current_song is not None:
            self.display_layers["foreground"]["current_song"] = current_song
        if system_status is not None:
            self.display_layers["foreground"]["system_status"] = system_status

        # 发送更新后的分层显示数据
        self.send_layered_display_data()

    def send_layered_display_data(self) -> bool:
        """
        发送分层显示数据到S3-CAM设备
        """
        try:
            data = {
                "type": "layered_display",
                "foreground": self.display_layers["foreground"],
                "background": self.display_layers["background"],
                "timestamp": int(time.time() * 1000)
            }

            # 使用正确的API接口 - SISIeyes只支持 /display/text
            # 组合所有前景文本内容
            text_content = ""
            fg = data["foreground"]
            if fg.get("user_speech"):
                text_content += f"{fg['user_speech']}\n"
            if fg.get("sisi_response"):
                text_content += f"{fg['sisi_response']}\n"
            if fg.get("current_song"):
                text_content += f"{fg['current_song']}\n"
            if fg.get("system_status"):
                text_content += f"{fg['system_status']}\n"

            # 限制文本长度，避免SISIeyes崩溃
            safe_text = text_content.strip()[:100]  # 限制100字符
            if len(text_content.strip()) > 100:
                safe_text += "..."

            response = requests.post(
                f"{self.base_url}/display/text",
                data=safe_text,  # 发送安全长度的文本
                headers={'Content-Type': 'text/plain; charset=utf-8'},
                timeout=1  # 🔥 缩短超时从5秒到1秒，避免阻塞主流程
            )

            if response.status_code == 200:
                self.logger.info("✅ 分层显示数据发送成功")
                return True
            else:
                self.logger.error(f"❌ 分层显示数据发送失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.info(f"ℹ️ 显示设备未连接或发送失败: {e}")
            return False

    def test_connection(self) -> bool:
        """测试与S3-CAM设备的连接"""
        try:
            response = requests.get(f"{self.base_url}/", timeout=3)
            self.logger.info(f"✅ S3-CAM设备连接成功: {self.display_ip}")
            return True
        except Exception as e:
            self.logger.error(f"❌ S3-CAM设备连接失败: {e}")
            return False

    def parse_lrc_lyrics(self, lrc_content: str) -> List[Dict[str, Any]]:
        """
        解析LRC歌词文件内容

        Args:
            lrc_content: LRC文件内容

        Returns:
            歌词时间轴列表 [{"time": 毫秒, "text": "歌词"}, ...]
        """
        lyrics = []
        lines = lrc_content.strip().split('\n')

        for line in lines:
            # 匹配时间戳格式 [mm:ss.xx]
            match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2})\](.*)', line)
            if match:
                minutes, seconds, centiseconds, text = match.groups()
                # 转换为毫秒
                timestamp = int(minutes) * 60000 + int(seconds) * 1000 + int(centiseconds) * 10
                lyrics.append({
                    "time": timestamp,
                    "text": text.strip()
                })

        # 按时间排序
        lyrics.sort(key=lambda x: x["time"])
        self.logger.info(f"✅ 解析歌词完成: {len(lyrics)} 行")
        return lyrics

    def load_lyrics_from_file(self, music_file_path: str) -> List[Dict[str, Any]]:
        """
        从音乐文件路径加载对应的歌词文件

        Args:
            music_file_path: 音乐文件路径

        Returns:
            歌词时间轴列表
        """
        try:
            # 获取音乐文件名（不含扩展名）
            base_name = os.path.splitext(os.path.basename(music_file_path))[0]
            music_dir = os.path.dirname(music_file_path)

            # 查找对应的LRC文件
            lrc_file = None
            for ext in ['.lrc', '.LRC']:
                potential_lrc = os.path.join(music_dir, base_name + ext)
                if os.path.exists(potential_lrc):
                    lrc_file = potential_lrc
                    break

            if lrc_file:
                with open(lrc_file, 'r', encoding='utf-8') as f:
                    lrc_content = f.read()
                self.logger.info(f"✅ 加载歌词文件: {os.path.basename(lrc_file)}")
                return self.parse_lrc_lyrics(lrc_content)
            else:
                self.logger.warning(f"⚠️  未找到歌词文件: {base_name}.lrc")
                return []

        except Exception as e:
            self.logger.error(f"❌ 加载歌词文件失败: {e}")
            return []
            
    def send_lyrics_data(self, lyrics: List[Dict[str, Any]], music_duration: float = 0) -> bool:
        """
        发送歌词数据到S3-CAM设备

        Args:
            lyrics: 歌词时间轴列表
            music_duration: 音乐总时长（秒）
        """
        try:
            data = {
                "type": "lyrics_data",
                "lyrics": lyrics,
                "duration": music_duration,
                "timestamp": int(time.time() * 1000)
            }

            response = requests.post(
                f"{self.base_url}/lyrics/update",
                json=data,
                timeout=5
            )

            if response.status_code == 200:
                self.logger.info(f"✅ 歌词数据发送成功: {len(lyrics)} 行歌词")
                self.current_lyrics = lyrics
                return True
            else:
                self.logger.error(f"❌ 歌词数据发送失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 歌词数据发送异常: {e}")
            return False

    def start_music_sync(self, start_timestamp: int = None) -> bool:
        """
        开始音乐同步播放

        Args:
            start_timestamp: 音乐开始时间戳（毫秒），None则使用当前时间
        """
        if start_timestamp is None:
            start_timestamp = int(time.time() * 1000)

        try:
            data = {
                "type": "music_sync_start",
                "start_timestamp": start_timestamp
            }

            response = requests.post(
                f"{self.base_url}/music/sync_start",
                json=data,
                timeout=5
            )

            if response.status_code == 200:
                self.logger.info(f"✅ 音乐同步开始: {start_timestamp}")
                self.music_start_time = start_timestamp
                self.is_music_playing = True
                return True
            else:
                self.logger.error(f"❌ 音乐同步开始失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 音乐同步开始异常: {e}")
            return False

    def stop_music_sync(self) -> bool:
        """停止音乐同步播放"""
        try:
            data = {"type": "music_sync_stop"}

            response = requests.post(
                f"{self.base_url}/music/sync_stop",
                json=data,
                timeout=5
            )

            if response.status_code == 200:
                self.logger.info("✅ 音乐同步停止")
                self.is_music_playing = False
                return True
            else:
                self.logger.error(f"❌ 音乐同步停止失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 音乐同步停止异常: {e}")
            return False

    def send_melody_animation_config(self, style: str = "rockets", intensity: str = "medium") -> bool:
        """
        发送旋律动画配置

        Args:
            style: 动画风格 (rockets/stars/waves/particles)
            intensity: 动画强度 (low/medium/high)
        """
        try:
            data = {
                "type": "melody_animation_config",
                "style": style,
                "intensity": intensity
            }

            response = requests.post(
                f"{self.base_url}/animation/config",
                json=data,
                timeout=5
            )

            if response.status_code == 200:
                self.logger.info(f"✅ 旋律动画配置发送成功: {style} - {intensity}")
                return True
            else:
                self.logger.error(f"❌ 旋律动画配置发送失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 旋律动画配置发送异常: {e}")
            return False

    def send_emotion(self, emotion: str, intensity: float = 50.0) -> bool:
        """
        发送情感到0.96寸OLED显示屏
        
        Args:
            emotion: 情感类型 (happy/sad/angry/neutral等)
            intensity: 情感强度 (0-100)
        """
        # 情感映射 - 适配小屏幕显示
        emotion_map = {
            "happy": "开心",
            "sad": "难过", 
            "angry": "生气",
            "excited": "兴奋",
            "confused": "困惑",
            "surprised": "惊讶",
            "neutral": "平静",
            "thinking": "思考",
            "love": "喜爱",
            "fear": "害怕"
        }
        
        display_emotion = emotion_map.get(emotion, emotion)
        
        try:
            data = {
                "emotion": display_emotion,
                "intensity": intensity
            }
            
            response = requests.post(
                f"{self.base_url}/show_sisi_emotion",
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                self.logger.info(f"✅ 情感发送成功: {display_emotion} ({intensity}%)")
                return True
            else:
                self.logger.error(f"❌ 情感发送失败: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 情感发送异常: {e}")
            return False
    
    def send_sisi_interaction_log(self, message: str, message_type: str = "user", username: str = "User") -> bool:
        """
        发送SmartSisi交互日志到S3-CAM设备（使用分层显示）

        Args:
            message: 消息内容
            message_type: 消息类型 (user/sisi/system)
            username: 用户名
        """
        try:
            # 🎯 更新表层显示内容 - 直接显示文本，不加前缀
            if message_type == "user":
                self.update_foreground_display(user_speech=message)  # 直接显示用户消息
                # 添加到背景日志
                self.add_component_log("用户交互", f"用户说话: {message[:50]}...")
            elif message_type == "sisi":
                self.update_foreground_display(sisi_response=message)  # 直接显示SmartSisi回复
                # 添加到背景日志
                self.add_component_log("SmartSisi回复", f"回复内容: {message[:50]}...")
            elif message_type == "system":
                self.update_foreground_display(system_status=message)
                # 添加到背景日志
                self.add_component_log("系统状态", message)

            self.logger.info(f"✅ SmartSisi交互日志更新成功: [{message_type}] {message[:30]}...")
            return True

        except Exception as e:
            self.logger.error(f"❌ SmartSisi交互日志更新异常: {e}")
            # 错误日志添加到背景
            self.add_component_log("SmartSisi交互", f"日志更新失败: {str(e)}", is_error=True)
            return False

    def send_text_message(self, message: str, username: str = "User") -> bool:
        """
        发送文本消息到S3-CAM设备（兼容旧接口）

        Args:
            message: 消息内容
            username: 用户名
        """
        # 转发到SmartSisi交互日志
        return self.send_sisi_interaction_log(message, "user", username)
    
    def send_audio_spectrum_data(self, spectrum_data: list, intensity: int = 128) -> bool:
        """
        发送音频频谱数据到SISIeyes进行可视化

        Args:
            spectrum_data: 8个频段的数据列表 [低频, 中低频, 中频, 中高频, 高频, 超高频, 冲击波, 爆炸] (0-255)
            intensity: 音频强度 (0-255)
        """
        try:
            # 🔥 确保数据格式正确 - 支持8个频段
            if len(spectrum_data) < 8:
                spectrum_data = spectrum_data + [0] * (8 - len(spectrum_data))
            elif len(spectrum_data) > 8:
                spectrum_data = spectrum_data[:8]

            # 格式化为逗号分隔的字符串
            audio_data_str = ",".join([str(int(val)) for val in spectrum_data])

            # 🔥 保存最新的频谱数据供sisidesk使用
            self.last_spectrum_data = spectrum_data[:8]

            # 发送到SISIeyes的音频数据接口
            response = requests.post(
                f"{self.base_url}/cmd",
                data=f"audiodata:{audio_data_str}",
                headers={'Content-Type': 'text/plain'},
                timeout=2
            )

            if response.status_code == 200:
                self.logger.info(f"🎵 音频频谱数据发送成功: audiodata:{audio_data_str}")  # 改为info级别，确保显示
                return True
            else:
                self.logger.warning(f"⚠️  音频频谱数据发送失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 音频频谱数据发送异常: {e}")
            return False

    def send_sisidesk_audio_data(self, intensity: int = 128, spectrum_data: list = None) -> bool:
        """
        发送音频强度数据到sisidesk设备的LED环

        Args:
            intensity: 音频强度 (30-255)
            spectrum_data: 8频段真实音频数据，如果提供则优先使用
        """
        try:
            # 确保强度在有效范围内
            intensity = max(30, min(255, intensity))

            # sisidesk设备的IP地址 (固定IP，避免冲突)
            sisidesk_url = "http://172.20.10.5"

            # 🔥 修复：优先使用传入的真实频谱数据
            if spectrum_data and len(spectrum_data) >= 8:
                # 使用传入的真实8频段数据
                spectrum_str = ",".join([str(int(val)) for val in spectrum_data[:8]])
                self.last_spectrum_data = spectrum_data[:8]  # 保存最新数据
                self.logger.debug(f"🎵 使用真实频谱数据: {spectrum_data[:4]}...")
            elif hasattr(self, 'last_spectrum_data') and self.last_spectrum_data:
                # 使用之前保存的数据
                spectrum_str = ",".join([str(int(val)) for val in self.last_spectrum_data[:8]])
                self.logger.debug(f"🎵 使用缓存频谱数据: {self.last_spectrum_data[:4]}...")
            else:
                # 🚨 最后才使用模拟数据
                spectrum_str = f"{intensity},128,128,128,128,128,128,128"
                self.logger.warning(f"⚠️ 使用模拟数据，强度: {intensity}")

            response = requests.post(
                f"{sisidesk_url}/api/audio/spectrum?data={spectrum_str}",
                timeout=2
            )

            if response.status_code == 200:
                self.logger.debug(f"🎵 sisidesk音频数据发送成功: intensity={intensity}")
                return True
            else:
                self.logger.warning(f"⚠️  sisidesk音频数据发送失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"❌ sisidesk音频数据发送异常: {e}")
            return False

    def send_system_status(self, cpu_percent: float, memory_percent: float) -> bool:
        """
        发送系统状态到0.96寸OLED显示屏
        
        Args:
            cpu_percent: CPU使用率
            memory_percent: 内存使用率
        """
        try:
            data = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent
            }
            
            response = requests.post(
                f"{self.base_url}/show_system_status",
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                self.logger.info(f"✅ 系统状态发送成功: CPU {cpu_percent}%, 内存 {memory_percent}%")
                return True
            else:
                self.logger.error(f"❌ 系统状态发送失败: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 系统状态发送异常: {e}")
            return False
    
    def set_display_mode(self, mode: int) -> bool:
        """
        设置显示模式
        
        Args:
            mode: 显示模式 (1=情感, 2=文本, 3=系统, 4=时钟)
        """
        mode_names = {1: "情感", 2: "文本", 3: "系统", 4: "时钟"}
        
        try:
            data = {"mode": mode}
            
            response = requests.post(
                f"{self.base_url}/set_display_mode",
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                mode_name = mode_names.get(mode, f"模式{mode}")
                self.logger.info(f"✅ 显示模式切换成功: {mode_name}")
                return True
            else:
                self.logger.error(f"❌ 显示模式切换失败: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 显示模式切换异常: {e}")
            return False

    def trigger_photo_effect(self) -> bool:
        """
        触发拍照特效（电机运动+LED效果+拍照+显示照片）

        Returns:
            bool: 特效启动成功返回True
        """
        try:
            # 发送拍照特效命令
            response = requests.post(
                f"{self.base_url}/cmd",
                data="photo_effect",
                headers={"Content-Type": "text/plain"},
                timeout=10
            )

            if response.status_code == 200:
                self.logger.info("✅ 拍照特效启动成功")
                return True
            else:
                self.logger.error(f"❌ 拍照特效启动失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"❌ 拍照特效启动异常: {e}")
            return False

    def send_complete_music_data(self, music_file_path: str, animation_style: str = "rockets") -> bool:
        """
        发送完整的音乐数据（歌词+动画配置+同步开始）使用分层显示

        Args:
            music_file_path: 音乐文件路径
            animation_style: 动画风格
        """
        try:
            song_name = os.path.splitext(os.path.basename(music_file_path))[0]

            # 🎯 更新表层显示 - 当前播放歌曲（不显示"开始播放"文字）
            self.update_foreground_display(
                current_song=f"♪ {song_name}",
                system_status=""  # 空字符串，不显示状态文字
            )

            # 1. 加载歌词
            lyrics = self.load_lyrics_from_file(music_file_path)

            # 2. 发送歌词数据
            if lyrics:
                if not self.send_lyrics_data(lyrics):
                    self.add_component_log("音乐模块", f"歌词数据发送失败: {song_name}", is_error=True)
                    return False
                self.add_component_log("音乐模块", f"歌词加载成功: {len(lyrics)}行")
            else:
                self.logger.warning("⚠️  没有歌词数据，仅发送动画配置")
                self.add_component_log("音乐模块", f"无歌词文件: {song_name}")

            # 3. 配置旋律动画
            if not self.send_melody_animation_config(animation_style, "high"):
                self.add_component_log("音乐模块", f"动画配置失败: {animation_style}", is_error=True)
                return False
            self.add_component_log("音乐模块", f"动画配置: {animation_style}")

            # 4. 🎬 启动拍照特效（电机+LED+拍照+显示）
            if not self.trigger_photo_effect():
                self.add_component_log("音乐模块", "拍照特效启动失败", is_error=True)
                # 不返回False，继续播放音乐
            else:
                self.add_component_log("音乐模块", "拍照特效已启动")

            # 5. 开始同步播放
            if not self.start_music_sync():
                self.add_component_log("音乐模块", "同步播放启动失败", is_error=True)
                return False

            # 6. 立即发送初始音频频谱数据，启动动画 - 8个频段
            import random
            initial_spectrum = [
                random.randint(120, 255),   # 低频：高强度启动
                random.randint(140, 255),   # 中低频
                random.randint(160, 255),   # 中频
                random.randint(180, 255),   # 中高频
                random.randint(200, 255),   # 高频：爆炸性
                random.randint(170, 255),   # 超高频：闪电
                random.randint(190, 255),   # 冲击波：导弹
                random.randint(220, 255)    # 爆炸：星空
            ]
            self.send_audio_spectrum_data(initial_spectrum, 200)  # 高强度
            self.logger.info(f"🎵 发送初始8频段音频数据启动动画: {initial_spectrum}")

            self.logger.info(f"✅ 完整音乐数据发送成功: {song_name}")
            return True

        except Exception as e:
            self.logger.error(f"❌ 发送完整音乐数据异常: {e}")
            self.add_component_log("音乐模块", f"数据发送异常: {str(e)}", is_error=True)
            return False

# SmartSisi系统集成类
class SisiS3CAMIntegration:
    """SmartSisi系统与ESP32-S3 CAM设备集成"""

    def __init__(self, display_ip: str = "192.168.1.100"):
        self.sender = S3CAMDisplaySender(display_ip)
        self.logger = logging.getLogger(__name__)

    def on_sisi_emotion_change(self, emotion: str, intensity: float):
        """SmartSisi情感变化回调"""
        self.sender.send_emotion(emotion, intensity)

    def on_sisi_user_message(self, message: str, username: str = "User"):
        """SmartSisi用户消息回调 - 更新表层显示"""
        self.sender.send_sisi_interaction_log(message, "user", username)

    def on_sisi_response(self, message: str):
        """SmartSisi回复消息回调 - 更新表层显示"""
        self.sender.send_sisi_interaction_log(message, "sisi", "SmartSisi")

    def on_sisi_system_message(self, message: str):
        """SmartSisi系统消息回调 - 更新表层显示"""
        self.sender.send_sisi_interaction_log(message, "system", "System")

    def on_sisi_music_start(self, music_file_path: str, animation_style: str = "rockets"):
        """SmartSisi音乐开始回调 - 仅更新表层显示，避免重复调用"""
        song_name = os.path.splitext(os.path.basename(music_file_path))[0]
        # 只更新显示，不重复发送音乐数据
        self.sender.update_foreground_display(
            current_song=f"♪ {song_name}",
            system_status=""
        )
        self.sender.add_component_log("音乐模块", f"开始播放: {song_name}")

    def on_sisi_music_stop(self):
        """SmartSisi音乐停止回调 - 更新表层显示"""
        self.sender.stop_music_sync()
        # 更新表层显示状态 - 不显示"停止播放"文字
        self.sender.update_foreground_display(
            current_song="",
            system_status=""  # 空字符串，不显示状态文字
        )

    def on_sisi_system_update(self, cpu: float, memory: float):
        """SmartSisi系统状态更新回调"""
        self.sender.send_system_status(cpu, memory)

# 测试函数
def test_s3cam_display():
    """测试ESP32-S3 CAM显示功能"""
    print("🧪 开始测试ESP32-S3 CAM显示功能...")

    # 请根据实际IP地址修改
    sender = S3CAMDisplaySender("192.168.1.100")

    # 测试连接
    if not sender.test_connection():
        print("❌ 无法连接到S3-CAM设备，请检查IP地址和网络")
        return False

    # 测试SmartSisi交互日志
    print("💬 测试SmartSisi交互日志...")
    sender.send_sisi_interaction_log("你好，我想听首歌", "user", "用户")
    time.sleep(2)
    sender.send_sisi_interaction_log("好的，我为您播放一首音乐", "sisi", "SmartSisi")
    time.sleep(2)

    # 测试旋律动画配置
    print("🎵 测试旋律动画配置...")
    sender.send_melody_animation_config("rockets", "high")
    time.sleep(2)

    # 测试歌词数据（模拟）
    print("📝 测试歌词数据...")
    test_lyrics = [
        {"time": 0, "text": "当坊间最善舞的女儿死了"},
        {"time": 5000, "text": "京城就该有一场大雪"},
        {"time": 10000, "text": "飘泊的雪 摇曳回风"},
        {"time": 15000, "text": "诗意灵魂 更迭情人"}
    ]
    sender.send_lyrics_data(test_lyrics, 30.0)
    time.sleep(2)

    # 测试音乐同步
    print("🎶 测试音乐同步...")
    sender.start_music_sync()
    time.sleep(5)
    sender.stop_music_sync()

    # 测试情感显示
    print("😊 测试情感显示...")
    sender.send_emotion("happy", 80.0)
    time.sleep(3)

    print("✅ 测试完成！")
    return True

def test_music_file_integration():
    """测试音乐文件集成功能"""
    print("🎵 测试音乐文件集成功能...")

    sender = S3CAMDisplaySender("192.168.1.100")

    # 测试音乐文件路径（请根据实际路径修改）
    test_music_file = r"E:\liusisi\SmartSisi\qa\mymusic\九万字.wav"

    if os.path.exists(test_music_file):
        print(f"🎵 测试音乐文件: {os.path.basename(test_music_file)}")
        success = sender.send_complete_music_data(test_music_file, "rockets")
        if success:
            print("✅ 音乐文件集成测试成功！")
        else:
            print("❌ 音乐文件集成测试失败")
    else:
        print(f"⚠️  测试音乐文件不存在: {test_music_file}")
        print("💡 请修改test_music_file路径为实际的音乐文件路径")

if __name__ == "__main__":
    print("选择测试模式:")
    print("1. 基础显示功能测试")
    print("2. 音乐文件集成测试")

    choice = input("请输入选择 (1/2): ").strip()

    if choice == "1":
        test_s3cam_display()
    elif choice == "2":
        test_music_file_integration()
    else:
        print("运行所有测试...")
        test_s3cam_display()
        print("\n" + "="*50 + "\n")
        test_music_file_integration()