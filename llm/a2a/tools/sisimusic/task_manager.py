#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Suno 任务管理工具
提供统一的任务轮询、下载和状态管理功能
"""

import os
import time
import logging
import datetime
import requests
from typing import Dict, Any, List, Optional, Tuple

# 配置logger
logger = logging.getLogger("task_manager")
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class TaskManager:
    """
    Suno API 任务管理类，提供统一的任务处理功能
    """
    
    @staticmethod
    def poll_task(api, task_id: str, 
                  callbacks: Optional[Dict] = None,
                  wait_seconds: int = 5, 
                  max_attempts: int = 60) -> Dict[str, Any]:
        """
        轮询任务状态直到完成或失败
        
        Args:
            api: SunoAPI实例
            task_id: 任务ID
            callbacks: 回调函数字典，包含 on_success, on_failure, on_progress
            wait_seconds: 轮询间隔（秒）
            max_attempts: 最大轮询次数
            
        Returns:
            Dict: 任务结果信息
        """
        if callbacks is None:
            callbacks = {}
        
        on_success = callbacks.get('on_success')
        on_failure = callbacks.get('on_failure')
        on_progress = callbacks.get('on_progress')
        
        logger.info(f"开始轮询任务状态: {task_id}")
        
        for attempt in range(max_attempts):
            logger.info(f"轮询次数 {attempt+1}/{max_attempts}")
            
            response = api.fetch_task(task_id)
            if not response:
                logger.error("获取任务状态失败，将在稍后重试")
                time.sleep(wait_seconds)
                continue
                
            status = response.get('data', {}).get('status', '')
            progress = response.get('data', {}).get('progress', '0%')
            
            logger.info(f"当前状态: {status}, 进度: {progress}")
            
            # 调用进度回调
            if on_progress:
                on_progress(status, progress, attempt)
            
            # 检查任务是否已完成
            if status == 'SUCCESS':
                logger.info("任务已成功完成！")
                
                # 提取任务结果数据
                result = {
                    "status": "COMPLETED",
                    "raw_response": response,
                    "data_items": response.get('data', {}).get('data', [])
                }
                
                # 调用成功回调
                if on_success:
                    on_success(result)
                    
                return result
                
            elif status == 'FAILED':
                fail_reason = response.get('data', {}).get('fail_reason', '未知错误')
                logger.error(f"任务失败: {fail_reason}")
                
                result = {
                    "status": "FAILED",
                    "error": fail_reason,
                    "raw_response": response
                }
                
                # 调用失败回调
                if on_failure:
                    on_failure(result)
                    
                return result
                
            # 继续等待
            logger.info(f"任务仍在进行中，{wait_seconds}秒后重新检查...")
            time.sleep(wait_seconds)
        
        # 如果达到最大尝试次数仍未完成
        logger.warning(f"达到最大轮询次数 ({max_attempts})，停止轮询")
        
        result = {
            "status": "TIMEOUT",
            "error": "任务超时，请稍后手动查询结果"
        }
        
        # 调用失败回调
        if on_failure:
            on_failure(result)
            
        return result
    
    @staticmethod
    def poll_task_status(task_id: str, suno_task_id: str, api, update_callback, 
                         wait_seconds: int = 5, max_attempts: int = 60):
        """
        轮询Suno任务状态（与MusicGeneratorTool兼容的接口）
        
        Args:
            task_id: 本地任务ID
            suno_task_id: Suno API任务ID
            api: SunoAPI实例
            update_callback: 任务状态更新回调函数
            wait_seconds: 轮询间隔秒数
            max_attempts: 最大轮询次数
        """
        logger.info(f"[音乐生成] 开始轮询任务状态 ({suno_task_id}), 本地任务ID: {task_id}")
        
        for attempt in range(max_attempts):
            logger.info(f"[音乐生成] 轮询次数 {attempt+1}/{max_attempts}, 任务ID: {suno_task_id}")
            
            try:
                response = api.fetch_task(suno_task_id)
                
                if not response:
                    logger.error(f"[音乐生成] 获取任务状态失败，将在{wait_seconds}秒后重试")
                    time.sleep(wait_seconds)
                    continue
                    
                status = response.get('data', {}).get('status', '')
                progress = response.get('data', {}).get('progress', '0%')
                
                logger.info(f"[音乐生成] 当前状态: {status}, 进度: {progress}, 任务ID: {suno_task_id}")
                
                # 检查任务是否已完成
                if status == 'SUCCESS':
                    logger.info(f"[音乐生成] 任务已成功完成! 任务ID: {suno_task_id}")
                    
                    # 获取音乐文件链接
                    data_items = response.get('data', {}).get('data', [])
                    
                    # 获取所有音频URL
                    audio_video_pairs = TaskManager.get_all_audio_urls(data_items)
                    logger.info(f"[音乐生成] 找到音频URL数量: {len(audio_video_pairs)}")
                    
                    # 下载所有音乐文件
                    downloaded_files = []
                    music_urls = []
                    video_urls = []
                    
                    # 提取情感类型
                    emotion_type = "伤感"  # 默认情感
                    
                    if audio_video_pairs:
                        try:
                            # 下载所有音频文件
                            for i, (audio_url, video_url) in enumerate(audio_video_pairs):
                                if audio_url:
                                    # 下载并重命名文件
                                    file_path = TaskManager.download_audio(api, audio_url, emotion_type)
                                    if file_path:
                                        downloaded_files.append(file_path)
                                        music_urls.append(audio_url)
                                    if video_url:
                                        video_urls.append(video_url)
                        
                            # 生成音乐旁白
                            narration = ""
                            if downloaded_files:
                                narration = TaskManager.generate_music_narration(downloaded_files[0])
                        
                            # 构建结果
                            result = {
                                "status": "SUCCESS",
                                "music_urls": music_urls,
                                "video_urls": video_urls,
                                "downloaded_files": downloaded_files,
                                "narration": narration,
                                "raw_response": response
                            }
                            
                            # 更新任务状态
                            update_callback(task_id, "COMPLETED", result)
                            
                            # 只播放第一个音频文件
                            if downloaded_files:
                                try:
                                    logger.info(f"[音乐生成] 开始播放音频: {downloaded_files[0]}")
                                    import os
                                    if os.name == 'nt':  # Windows系统
                                        os.system(f'start {downloaded_files[0]}')
                                    elif os.name == 'posix':  # Linux/Mac系统
                                        os.system(f'open {downloaded_files[0]}')
                                    logger.info("[音乐生成] 音频播放指令已发送")
                                    logger.info(f"[音乐生成] 音乐旁白: {narration}")
                                except Exception as e:
                                    logger.error(f"[音乐生成] 播放音频失败: {str(e)}")
                        
                        except Exception as e:
                            logger.error(f"[音乐生成] 下载音频文件失败: {str(e)}")
                    
                    break
                    
                elif status == 'FAILED':
                    fail_reason = response.get('data', {}).get('fail_reason', '未知错误')
                    logger.error(f"[音乐生成] 任务失败: {fail_reason}")
                    
                    update_callback(task_id, "FAILED", {
                        "error": fail_reason,
                        "raw_response": response
                    })
                    
                    break
                
                # 继续等待
                logger.info(f"[音乐生成] 任务仍在进行中，{wait_seconds}秒后重新检查...")
                time.sleep(wait_seconds)
            except Exception as e:
                logger.error(f"[音乐生成] 轮询任务状态时发生错误: {str(e)}")
                time.sleep(wait_seconds)
        
        # 如果达到最大尝试次数仍未完成
        logger.warning(f"[音乐生成] 达到最大轮询次数 ({max_attempts})，任务{suno_task_id}可能仍在处理中")
        
        update_callback(task_id, "TIMEOUT", {
            "error": "任务处理超时，但可能仍在后台进行，请稍后手动查询结果",
            "suno_task_id": suno_task_id
        })
    
    @staticmethod
    def download_audio(api, audio_url: str, 
                       emotion_type: str = "伤感",
                       output_dir: Optional[str] = None) -> str:
        """
        下载音频文件并重命名为符合Sisi TTS标准的格式
        
        Args:
            api: SunoAPI实例
            audio_url: 音频URL
            emotion_type: 情感类型（用于文件命名）
            output_dir: 输出目录，如果为None则使用Sisi samples目录
            
        Returns:
            str: 下载的文件路径，如果下载失败则返回空字符串
        """
        try:
            logger.info(f"[音乐下载] 开始下载音频: {audio_url}")
            
            # **修复：使用Sisi的samples目录，符合TTS标准**
            if not output_dir:
                # 获取SmartSisi根目录的samples目录
                import os
                current_dir = os.path.dirname(os.path.abspath(__file__))
                sisi_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
                samples_dir = os.path.join(sisi_root, "samples")
                
                # 确保samples目录存在
                if not os.path.exists(samples_dir):
                    os.makedirs(samples_dir)
                output_dir = samples_dir
            
            # 生成符合Sisi TTS标准的时间戳（Unix时间戳）
            import time
            timestamp = int(time.time())
            
            try:
                # 下载音频文件
                logger.info(f"[音乐下载] 从URL下载: {audio_url}")
                
                # 直接下载到指定目录，使用Sisi TTS标准命名
                import requests
                from urllib.parse import urlparse
                
                # 获取原始文件扩展名
                parsed_url = urlparse(audio_url)
                original_ext = os.path.splitext(parsed_url.path)[1] or '.mp3'
                
                # **关键修复：使用Sisi TTS标准命名格式，而不是phonk前缀**
                new_filename = f"output_{timestamp}{original_ext}"
                new_file_path = os.path.join(output_dir, new_filename)
                
                # 下载文件
                response = requests.get(audio_url, stream=True)
                if response.status_code == 200:
                    with open(new_file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    logger.info(f"[音乐下载] ✅ 音频已保存到Sisi标准目录: samples/{new_filename}")
                    logger.info(f"[音乐下载] 📁 完整路径: {new_file_path}")
                    
                    # **重要：如果是mp3文件，尝试转换为wav格式以完全符合Sisi标准**
                    if original_ext.lower() == '.mp3':
                        try:
                            wav_filename = f"output_{timestamp}.wav"
                            wav_file_path = os.path.join(output_dir, wav_filename)
                            
                            # 使用ffmpeg或pydub转换格式
                            try:
                                import subprocess
                                # 尝试使用ffmpeg转换
                                result = subprocess.run([
                                    'ffmpeg', '-i', new_file_path, '-ar', '22050', '-ac', '1', wav_file_path, '-y'
                                ], capture_output=True, text=True, timeout=30)
                                
                                if result.returncode == 0:
                                    logger.info(f"[音乐下载] 🎵 已转换为WAV格式: {wav_filename}")
                                    # 删除原始mp3文件，只保留wav
                                    os.remove(new_file_path)
                                    return wav_file_path
                                else:
                                    logger.warning(f"[音乐下载] ffmpeg转换失败，保留mp3格式")
                                    
                            except (subprocess.TimeoutExpired, FileNotFoundError):
                                logger.warning(f"[音乐下载] ffmpeg不可用，尝试使用pydub转换")
                                
                                try:
                                    from pydub import AudioSegment
                                    # 使用pydub转换
                                    audio = AudioSegment.from_mp3(new_file_path)
                                    audio.export(wav_file_path, format="wav")
                                    logger.info(f"[音乐下载] 🎵 已使用pydub转换为WAV格式: {wav_filename}")
                                    # 删除原始mp3文件
                                    os.remove(new_file_path)
                                    return wav_file_path
                                except ImportError:
                                    logger.warning(f"[音乐下载] pydub不可用，保留mp3格式")
                                except Exception as e:
                                    logger.error(f"[音乐下载] pydub转换失败: {str(e)}")
                        except Exception as e:
                            logger.error(f"[音乐下载] 音频格式转换失败: {str(e)}")
                    
                    return new_file_path
                else:
                    logger.error(f"[音乐下载] 下载失败: HTTP {response.status_code}")
                    return ""
                    
            except Exception as e:
                logger.error(f"[音乐下载] 下载过程出错: {str(e)}")
                return ""
                
        except Exception as e:
            logger.error(f"[音乐下载] 下载音频文件失败: {str(e)}")
            return ""
    
    @staticmethod
    def get_all_audio_urls(data_items: List[Dict]) -> List[Tuple[str, str]]:
        """
        从API返回的数据项中获取所有音频URL
        
        Args:
            data_items: API返回的数据项列表
            
        Returns:
            List[Tuple[str, str]]: 多个(音频URL, 视频URL)的列表，若不存在则为空列表
        """
        if not data_items or len(data_items) == 0:
            return []
        
        # 获取所有音频文件URL
        audio_video_pairs = []
        for item in data_items:
            audio_url = item.get('audio_url', '')
            video_url = item.get('video_url', '')
            if audio_url:  # 只添加有音频URL的项
                audio_video_pairs.append((audio_url, video_url))
        
        return audio_video_pairs
    
    @staticmethod
    def get_best_audio_url(data_items: List[Dict]) -> Tuple[str, str]:
        """
        从API返回的数据项中获取最优质的音频URL
        
        Args:
            data_items: API返回的数据项列表
            
        Returns:
            Tuple[str, str]: (音频URL, 视频URL)，若不存在则为空字符串
        """
        if not data_items or len(data_items) == 0:
            return "", ""
        
        # 只取第一个音频文件（通常质量最好的一个）
        first_item = data_items[0]
        audio_url = first_item.get('audio_url', '')
        video_url = first_item.get('video_url', '')
        
        return audio_url, video_url
    
    @staticmethod
    def extract_emotion_from_prompt(prompt: str) -> str:
        """
        从提示词中提取情感类型
        
        Args:
            prompt: 提示词
            
        Returns:
            str: 情感类型
        """
        if not prompt:
            return "伤感"  # 默认情感
            
        if "伤感" in prompt:
            return "伤感"
        elif "快乐" in prompt:
            return "快乐"
        elif "舞曲" in prompt:
            return "舞曲"
        elif "电音" in prompt:
            return "电音"
        else:
            return "伤感"  # 默认情感
    
    @staticmethod
    def generate_music_narration(file_path: str) -> str:
        """
        为播放的音乐生成旁白介绍，并通过中转站发送到优化站进行人性化优化
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            str: 生成的基础旁白文本
        """
        # 从文件路径提取文件名
        import os
        import random
        
        file_name = os.path.basename(file_path)
        
        # 判断情感类型
        emotion_type = "伤感"  # 默认情感
        if "伤感" in file_name:
            emotion_type = "伤感"
        elif "快乐" in file_name:
            emotion_type = "快乐"
        elif "舞曲" in file_name:
            emotion_type = "舞曲"
        elif "phonk" in file_name.lower():
            emotion_type = "Phonk"
        
        # 根据情感类型选择不同的描述词
        emotions = {
            "伤感": ["伤感", "情绪化", "沉浸式", "氛围感强烈", "忧郁中带着希望"],
            "快乐": ["欢快", "活力四射", "令人振奋", "愉悦", "轻松愉快"],
            "舞曲": ["动感", "节奏感强", "电子律动", "派对氛围", "令人想舞动"],
            "Phonk": ["深沉", "低音澎湃", "电子迷幻", "节奏感强烈", "独特风格"]
        }
        
        adjectives = ["动人", "打动人心", "令人陶醉", "精心制作", "独特风格", "引人入胜"]
        
        # 随机选择描述词
        emotion = random.choice(emotions.get(emotion_type, emotions["伤感"]))
        adjective = random.choice(adjectives)
        
        # 获取当前时间
        import datetime
        now = datetime.datetime.now()
        time_desc = "早晨" if 5 <= now.hour < 12 else "下午" if 12 <= now.hour < 18 else "晚上"
        
        # 添加等待时间的友好提示
        waiting_phrases = [
            "等了这么久，终于生成好了",
            "虽然等待了一会儿，不过值得",
            "网络有点慢，不过总算完成了",
            "这个花了点时间，希望你会喜欢",
            "我知道生成有点慢，感谢你的耐心等待",
            "创作需要灵感和时间，总算完成了",
            "系统有点慢，不过好东西值得等待",
            "音乐创作不易，感谢你的耐心",
            "终于等来了，希望你喜欢这首",
            "等待是值得的，这首曲子终于完成"
        ]
        
        waiting_phrase = random.choice(waiting_phrases)
        
        # 构建基础旁白模板（将被优化站进一步优化）
        basic_templates = [
            f"{waiting_phrase}，这是一首{emotion}的{emotion_type}音乐",
            f"{waiting_phrase}，为你准备的{adjective}的{emotion_type}风格作品",
            f"{waiting_phrase}，为你创作的{emotion}音乐已经准备好了",
            f"{waiting_phrase}，这首{emotion_type}音乐带着{emotion}的韵味"
        ]
        
        # 生成基础旁白
        basic_narration = random.choice(basic_templates)
        
        # 🔄 **关键改动：通过中转站发送到优化站进行人性化优化**
        try:
            # ❌ 删除重复的旁白发送逻辑，由music_tool.py统一处理
            # 只保留音乐文件路径记录
            logger.info(f"[音乐下载] 音乐文件已保存: {os.path.basename(file_path)}")
            
        except Exception as e:
            logger.error(f"[音乐下载] 处理音乐文件时出错: {str(e)}")
        
        # 返回基础旁白（优化后的旁白将通过Agent系统播放）
        return basic_narration

