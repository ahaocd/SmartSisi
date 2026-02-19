#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Suno API - 完全按照官方文档标准实现
支持灵感模式、自定义模式，符合官方API格式
"""

import requests
import json
import time
import logging

# 配置logger
logger = logging.getLogger("suno_api")

class SunoAPI:
    """Suno API客户端 - 按照官方文档标准实现"""
    
    def __init__(self, api_key=None, base_url=None):
        """
        初始化Suno API客户端
        
        Args:
            api_key: API密钥
            base_url: API基础URL
        """
        if not api_key or not base_url:
            from config import API_KEY, BASE_URL, DEFAULT_MODEL
            self.api_key = api_key or API_KEY
            self.base_url = base_url or BASE_URL
            self.default_model = DEFAULT_MODEL
        else:
            self.api_key = api_key
            self.base_url = base_url
            self.default_model = "chirp-auk"
            
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        logger.info(f"[SunoAPI] 初始化完成，使用官方API: {self.base_url}")
    
    def _make_request(self, endpoint, data):
        """
        发送请求到Suno API
        
        Args:
            endpoint: API端点
            data: 请求数据
            
        Returns:
            dict: API响应
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.info(f"[SunoAPI] 发送请求到: {url}")
            logger.info(f"[SunoAPI] 请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            response = self.session.post(url, json=data, timeout=30)
            
            logger.info(f"[SunoAPI] 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"[SunoAPI] 请求成功")
                return {"code": "success", "data": response_data}
            else:
                try:
                    error_data = response.json()
                    logger.error(f"[SunoAPI] 请求失败: {error_data}")
                    return {"code": "error", "message": str(error_data)}
                except:
                    logger.error(f"[SunoAPI] 请求失败: {response.text}")
                    return {"code": "error", "message": response.text}
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[SunoAPI] 请求异常: {error_msg}")
            return {"code": "error", "message": error_msg}
    
    def _make_get_request(self, endpoint):
        """
        发送GET请求到Suno API
        
        Args:
            endpoint: API端点
            
        Returns:
            dict: API响应
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.info(f"[SunoAPI] 发送GET请求到: {url}")
            
            response = self.session.get(url, timeout=30)
            
            logger.info(f"[SunoAPI] 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"[SunoAPI] GET请求成功")
                return {"code": "success", "data": response_data}
            else:
                try:
                    error_data = response.json()
                    logger.error(f"[SunoAPI] GET请求失败: {error_data}")
                    return {"code": "error", "message": str(error_data)}
                except:
                    logger.error(f"[SunoAPI] GET请求失败: {response.text}")
                    return {"code": "error", "message": response.text}
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[SunoAPI] GET请求异常: {error_msg}")
            return {"code": "error", "message": error_msg}
    
    def _make_post_request(self, endpoint, data):
        """
        发送POST请求到Suno API
        
        Args:
            endpoint: API端点
            data: 请求数据
                
        Returns:
            dict: API响应
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.info(f"[SunoAPI] 发送POST请求到: {url}")
            logger.info(f"[SunoAPI] 请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = self.session.post(url, json=data, headers=headers, timeout=30)
            
            logger.info(f"[SunoAPI] 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"[SunoAPI] 请求成功")
                return {"code": "success", "data": response_data}
            else:
                try:
                    error_data = response.json()
                    logger.error(f"[SunoAPI] 请求失败: {error_data}")
                    return {"code": "error", "message": str(error_data)}
                except:
                    logger.error(f"[SunoAPI] 请求失败: {response.text}")
                    return {"code": "error", "message": response.text}
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[SunoAPI] 请求异常: {error_msg}")
            return {"code": "error", "message": error_msg}
    
    def generate_music_inspiration(self, description, make_instrumental=False, mv=None):
        """
        灵感模式生成音乐 - 按照官方文档场景一格式
        
        Args:
            description (str): 灵感描述
            make_instrumental (bool): 是否生成纯音乐
            mv (str): 模型版本，支持 chirp-v4, chirp-v3-0, chirp-v3-5, chirp-auk
            
        Returns:
            dict: API响应，包含clips数组和id
        """
        if mv is None:
            mv = self.default_model
            
        # 完全按照官方文档场景一：灵感模式的格式
        data = {
            "gpt_description_prompt": description,
            "make_instrumental": make_instrumental,
            "mv": mv
        }
        
        logger.info(f"[SunoAPI] 灵感模式生成: {description}")
        return self._make_request("/suno/generate", data)
    
    def generate_music_custom(self, lyrics, title, tags, make_instrumental=False, mv=None):
        """
        自定义模式生成音乐 - 按照官方文档场景二格式
        
        Args:
            lyrics (str): 歌词内容
            title (str): 歌曲标题
            tags (str): 风格标签（多个风格用空格分开）
            make_instrumental (bool): 是否生成纯音乐
            mv (str): 模型版本
            
        Returns:
            dict: API响应，包含task_id和状态信息
        """
        if mv is None:
            mv = self.default_model
            
        # 完全按照官方文档自定义创作模式格式构建
        data = {
            "prompt": lyrics,
            "mv": mv,
            "title": title,
            "tags": tags,
            "generation_type": "TEXT"
        }
        
        # 如果是纯音乐，可以清空prompt
        if make_instrumental:
            data["prompt"] = ""
        
        logger.info(f"[SunoAPI] 自定义模式生成: {title}")
        return self._make_request("/suno/submit/music", data)  # 使用正确的端点
    
    def generate_phonk_optimized(self, query, lyrics=None, title=None, mv=None):
        """
        优化的Phonk音乐生成
        
        Args:
            query (str): 用户查询
            lyrics (str): 可选的歌词
            title (str): 可选的标题
            mv (str): 模型版本
            
        Returns:
            dict: API响应
        """
        if mv is None:
            mv = self.default_model
            
        if lyrics and title:
            # 如果有歌词和标题，使用自定义模式
            tags = "drift phonk, memphis rap, 808, cowbell, heavy bass, distorted samples, electronic, female vocals"
            return self.generate_music_custom(lyrics, title, tags, mv=mv)
        else:
            # 否则使用灵感模式，构建专业的Phonk描述
            phonk_description = f"创作TWISTED风格的Drift Phonk音乐，具有明显的808重低音、骚铃节奏、Memphis采样、侧链压缩效果、女声说唱元素。主题：{query}"
            return self.generate_music_inspiration(phonk_description, mv=mv)
    
    def fetch_task(self, task_response_or_clips):
        """
        获取歌曲任务结果 - 按照官方文档查询格式
        
        Args:
            task_response_or_clips: 任务响应数据或task IDs
            
        Returns:
            dict: 歌曲数据数组
        """
        # 提取task_ids
        task_ids = []
        
        if isinstance(task_response_or_clips, dict):
            # 如果是任务响应，尝试提取ID
            if 'data' in task_response_or_clips:
                data = task_response_or_clips['data']
                if isinstance(data, str):
                    task_ids = [data]  # 单个任务ID
                elif isinstance(data, list):
                    task_ids = data  # ID列表
                elif isinstance(data, dict) and 'task_id' in data:
                    task_ids = [data['task_id']]
        elif isinstance(task_response_or_clips, str):
            # 如果是字符串，直接作为ID使用
            task_ids = [task_response_or_clips]
        elif isinstance(task_response_or_clips, list):
            # 如果是列表，直接使用
            task_ids = task_response_or_clips
            
        if not task_ids:
            logger.error("[SunoAPI] 无法提取任务ID")
            return {"code": "error", "message": "无法提取任务ID"}
        
        logger.info(f"[SunoAPI] 获取任务结果: {task_ids}")
        
        # 按照官方文档格式查询 - 使用POST /suno/fetch 接口
        request_data = {"ids": task_ids}
        return self._make_post_request("/suno/fetch", request_data)
    
    def test_connection(self):
        """
        测试API连接 - 发送更详细的请求
        
        Returns:
            dict: 连接测试结果
        """
        try:
            # 使用更详细的音乐描述进行连接测试
            test_data = {
                "gpt_description_prompt": "创作一首轻松愉快的流行音乐，适合午后的阳光",
                "make_instrumental": False,
                "mv": self.default_model
            }
            
            response = self._make_request("/suno/generate", test_data)
            
            if response.get("code") == "success":
                return {"status": "OK", "message": "API连接正常"}
            else:
                return {"status": "ERROR", "message": response.get("message", "连接测试失败")}
                
        except Exception as e:
            return {"status": "ERROR", "message": f"连接测试异常: {str(e)}"}
