#!/usr/bin/env python3
"""
🎵 ACRCloud音乐识别分析器
集成您的ACRCloud配置，实现音乐识别和大模型交叉验证

功能：
1. 音乐识别 - 歌名、艺术家、专辑
2. 大模型交叉验证 - 音乐理解和情感分析
3. 动态提示词生成 - 基于音乐内容的个性化建议
4. 缓存机制 - 避免重复识别
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
import base64
import hmac
from dataclasses import dataclass, asdict

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from utils import config_util as cfg
from utils import util
from utils.config_util import load_config

def setup_music_logger():
    logger = logging.getLogger('acrcloud_music')
    logger.setLevel(logging.INFO)
    
    log_dir = Path(util.ensure_log_dir("brain"))
    
    handler = logging.FileHandler(log_dir / "acrcloud_music.log", encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [音乐识别] %(message)s')
    handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger

music_logger = setup_music_logger()

@dataclass
class MusicInfo:
    """🎵 音乐信息数据结构"""
    song_name: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    duration: Optional[int] = None
    release_date: Optional[str] = None
    confidence: float = 0.0
    acr_id: Optional[str] = None
    
@dataclass
class MusicAnalysis:
    """🧠 音乐分析结果"""
    basic_info: MusicInfo
    emotional_analysis: Dict[str, Any]
    musical_elements: Dict[str, Any]
    cultural_context: Dict[str, Any]
    recommendations: List[str]
    dynamic_prompts: List[str]

class ACRCloudMusicAnalyzer:
    """🎵 ACRCloud音乐识别分析器"""
    
    def __init__(self):
        # 加载配置
        load_config()

        # 直接从system.conf读取ACRCloud配置
        from utils.config_util import system_config

        # ACRCloud配置 - 修复配置读取方式
        self.host = system_config.get('key', 'acrcloud_host', fallback='identify-cn-north-1.acrcloud.cn')
        self.access_key = system_config.get('key', 'acrcloud_access_key', fallback='')
        self.access_secret = system_config.get('key', 'acrcloud_access_secret', fallback='')
        self.timeout = int(system_config.get('key', 'acrcloud_timeout', fallback='10'))
        self.enabled = system_config.get('key', 'acrcloud_enabled', fallback='true').lower() == 'true'

        # 大模型配置 - 使用您现有的音乐LLM配置
        self.llm_api_key = system_config.get('key', 'music_llm_api_key', fallback=system_config.get('key', 'brain_llm_api_key', fallback=''))
        self.llm_api_url = system_config.get('key', 'music_llm_api_url', fallback=system_config.get('key', 'brain_llm_api_url', fallback=''))
        self.llm_model = system_config.get('key', 'music_llm_model', fallback=system_config.get('key', 'brain_llm_model', fallback='o3'))
        
        # 缓存配置
        base_cache = Path(cfg.cache_root) if getattr(cfg, "cache_root", None) else (Path(__file__).parent.parent / "cache_data")
        self.cache_dir = base_cache / "music_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 统计信息
        self.daily_requests = 0
        self.max_daily_requests = 5000  # FreeTrial限制

        # 🎯 批量处理配置 - 解决您提到的问题
        self.batch_size = 3  # 收集3段音乐片段后发送识别
        self.pending_segments = []  # 待处理的音频片段队列
        self.last_batch_time = time.time()
        self.batch_timeout = 30  # 30秒超时，避免等待过久

        music_logger.info(f"🎵 ACRCloud音乐分析器初始化完成")
        music_logger.info(f"   📡 服务器: {self.host}")
        music_logger.info(f"   🔑 Access Key: {self.access_key[:10]}..." if self.access_key else "   🔑 Access Key: 未配置")
        music_logger.info(f"   📊 每日限制: {self.max_daily_requests}次")
        music_logger.info(f"   🎯 批量处理: 收集{self.batch_size}段后识别")
        music_logger.info(f"   ✅ 配置状态: {'已配置' if self.is_configured() else '未配置'}")

    def is_configured(self) -> bool:
        """检查ACRCloud是否正确配置"""
        return bool(self.host and self.access_key and self.access_secret and self.enabled)
    
    def _generate_signature(self, method: str, uri: str, access_key: str, data_type: str, signature_version: str, timestamp: str) -> str:
        """生成ACRCloud API签名"""
        string_to_sign = f"{method}\n{uri}\n{access_key}\n{data_type}\n{signature_version}\n{timestamp}"
        return base64.b64encode(
            hmac.new(
                self.access_secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha1
            ).digest()
        ).decode('utf-8')
    
    def _get_audio_fingerprint(self, audio_file_path: str) -> Optional[str]:
        """获取音频指纹（简化版）"""
        try:
            with open(audio_file_path, 'rb') as f:
                audio_data = f.read()
            
            # 生成文件哈希作为缓存键
            file_hash = hashlib.md5(audio_data).hexdigest()
            return file_hash
        except Exception as e:
            music_logger.error(f"❌ 获取音频指纹失败: {e}")
            return None
    
    def _check_cache(self, audio_fingerprint: str) -> Optional[MusicInfo]:
        """检查缓存中的音乐信息"""
        cache_file = self.cache_dir / f"{audio_fingerprint}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                
                # 检查缓存是否过期（24小时）
                cache_time = cached_data.get('timestamp', 0)
                if time.time() - cache_time < 24 * 3600:
                    music_logger.info(f"📁 使用缓存的音乐信息: {cached_data.get('song_name', '未知')}")
                    return MusicInfo(**cached_data.get('music_info', {}))
                    
            except Exception as e:
                music_logger.warning(f"⚠️ 读取缓存失败: {e}")
        
        return None
    
    def _save_cache(self, audio_fingerprint: str, music_info: MusicInfo):
        """保存音乐信息到缓存"""
        cache_file = self.cache_dir / f"{audio_fingerprint}.json"
        
        cache_data = {
            'timestamp': time.time(),
            'music_info': asdict(music_info),
            'song_name': music_info.song_name
        }
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            music_logger.info(f"💾 音乐信息已缓存: {music_info.song_name}")
        except Exception as e:
            music_logger.error(f"❌ 保存缓存失败: {e}")
    
    async def identify_music(self, audio_file_path: str) -> Optional[MusicInfo]:
        """🎵 识别音乐"""
        
        if not self.enabled:
            music_logger.warning("⚠️ ACRCloud音乐识别已禁用")
            return None
        
        if self.daily_requests >= self.max_daily_requests:
            music_logger.warning(f"⚠️ 已达到每日识别限制: {self.max_daily_requests}")
            return None
        
        # 检查缓存
        audio_fingerprint = self._get_audio_fingerprint(audio_file_path)
        if audio_fingerprint:
            cached_info = self._check_cache(audio_fingerprint)
            if cached_info:
                return cached_info
        
        try:
            music_logger.info(f"🎵 开始识别音乐: {Path(audio_file_path).name}")
            
            # 准备请求数据
            timestamp = str(int(time.time()))
            signature = self._generate_signature(
                "POST", "/v1/identify", self.access_key, 
                "audio", "1", timestamp
            )
            
            # 读取音频文件 - 你的10秒录音片段完全符合ACRCloud要求
            with open(audio_file_path, 'rb') as f:
                audio_data = f.read()

            # 🔧 修复：按照官方文档格式构建请求
            # 官方文档要求：files格式为 ('sample', ('filename', file_object, 'audio/mpeg'))
            files = [
                ('sample', (os.path.basename(audio_file_path), audio_data, 'audio/wav'))
            ]

            # 🔧 修复：添加缺失的sample_bytes参数
            sample_bytes = len(audio_data)
            data = {
                'access_key': self.access_key,
                'sample_bytes': str(sample_bytes),  # 官方文档要求的参数
                'data_type': 'audio',
                'signature_version': '1',
                'signature': signature,
                'timestamp': str(timestamp)  # 转换为字符串
            }
            
            # 发送请求
            url = f"https://{self.host}/v1/identify"
            response = requests.post(url, files=files, data=data, timeout=self.timeout)
            
            self.daily_requests += 1
            music_logger.info(f"📊 今日识别次数: {self.daily_requests}/{self.max_daily_requests}")
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status', {}).get('code') == 0:
                    # 解析识别结果
                    metadata = result.get('metadata', {})
                    music_list = metadata.get('music', [])
                    
                    if music_list:
                        music_data = music_list[0]
                        
                        # 🔧 修复编码问题：确保中文字符正确显示
                        def fix_encoding(text):
                            if not text:
                                return text
                            try:
                                # 如果是乱码，尝试修复编码
                                if isinstance(text, str):
                                    # 检测是否为UTF-8编码错误导致的乱码
                                    if any(ord(char) > 127 for char in text):
                                        # 尝试重新编码
                                        try:
                                            # 先编码为latin-1再解码为utf-8
                                            fixed = text.encode('latin-1').decode('utf-8')
                                            return fixed
                                        except (UnicodeDecodeError, UnicodeEncodeError):
                                            # 如果修复失败，返回原文本
                                            return text
                                return text
                            except Exception:
                                return text or ''

                        music_info = MusicInfo(
                            song_name=fix_encoding(music_data.get('title')),
                            artist=', '.join([fix_encoding(artist.get('name', '')) for artist in music_data.get('artists', [])]),
                            album=fix_encoding(music_data.get('album', {}).get('name')),
                            genre=', '.join([fix_encoding(genre) for genre in music_data.get('genres', [])]),
                            duration=music_data.get('duration_ms'),
                            release_date=music_data.get('release_date'),
                            confidence=music_data.get('score', 0) / 100.0,
                            acr_id=music_data.get('acrid')
                        )
                        
                        music_logger.info(f"✅ 识别成功: {music_info.song_name} - {music_info.artist}")
                        
                        # 保存到缓存
                        if audio_fingerprint:
                            self._save_cache(audio_fingerprint, music_info)
                        
                        return music_info
                    else:
                        music_logger.warning("⚠️ 未找到匹配的音乐")
                else:
                    error_msg = result.get('status', {}).get('msg', '未知错误')
                    music_logger.error(f"❌ ACRCloud识别失败: {error_msg}")
            else:
                music_logger.error(f"❌ API请求失败: {response.status_code}")
                
        except Exception as e:
            music_logger.error(f"❌ 音乐识别异常: {e}")
        
        return None

    async def llm_cross_validate(self, music_info: MusicInfo, audio_features: Dict[str, Any] = None) -> Dict[str, Any]:
        """🧠 大模型交叉验证和深度分析"""

        if not music_info or not music_info.song_name:
            return {}

        try:
            music_logger.info(f"🧠 开始大模型分析: {music_info.song_name}")

            # 构建分析提示词
            prompt = f"""
作为音乐分析专家，请深度分析这首歌曲：

🎵 基本信息：
- 歌名：{music_info.song_name}
- 艺术家：{music_info.artist}
- 专辑：{music_info.album}
- 类型：{music_info.genre}
- 发行时间：{music_info.release_date}

请从以下维度进行分析，返回JSON格式：

{{
  "emotional_analysis": {{
    "primary_emotion": "主要情感（如：欢快、忧伤、激昂等）",
    "emotional_intensity": "情感强度（1-10）",
    "mood_description": "情绪描述（详细）",
    "target_audience": "目标听众群体"
  }},
  "musical_elements": {{
    "rhythm_style": "节奏风格",
    "melody_characteristics": "旋律特点",
    "instrumentation": "主要乐器",
    "vocal_style": "演唱风格"
  }},
  "cultural_context": {{
    "cultural_background": "文化背景",
    "lyrical_themes": "歌词主题",
    "social_significance": "社会意义"
  }},
  "recommendations": [
    "相似风格歌曲1",
    "相似风格歌曲2",
    "相似风格歌曲3"
  ],
  "dynamic_prompts": [
    "基于这首歌为用户生成的个性化建议1",
    "基于这首歌为用户生成的个性化建议2",
    "基于这首歌为用户生成的个性化建议3"
  ]
}}

请确保分析准确、深入，特别关注中文歌曲的文化内涵。
"""

            # 调用大模型API
            headers = {
                'Authorization': f'Bearer {self.llm_api_key}',
                'Content-Type': 'application/json'
            }

            payload = {
                'model': self.llm_model,
                'messages': [
                    {
                        'role': 'system',
                        'content': '你是一位专业的音乐分析师，擅长从多个维度深度分析音乐作品的情感、文化和艺术价值。'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'max_tokens': 2000,
                'temperature': 0.7
            }

            response = requests.post(
                f"{self.llm_api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

                # 尝试解析JSON
                try:
                    # 提取JSON部分
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1

                    if json_start >= 0 and json_end > json_start:
                        json_content = content[json_start:json_end]
                        analysis_result = json.loads(json_content)

                        music_logger.info(f"✅ 大模型分析完成: {music_info.song_name}")
                        return analysis_result
                    else:
                        music_logger.warning("⚠️ 大模型返回格式不正确，使用默认分析")

                except json.JSONDecodeError as e:
                    music_logger.warning(f"⚠️ JSON解析失败: {e}")
            else:
                music_logger.error(f"❌ 大模型API调用失败: {response.status_code}")

        except Exception as e:
            music_logger.error(f"❌ 大模型分析异常: {e}")

        # 返回默认分析结果
        return {
            "emotional_analysis": {
                "primary_emotion": "未知",
                "emotional_intensity": 5,
                "mood_description": f"正在分析{music_info.song_name}的情感特征",
                "target_audience": "音乐爱好者"
            },
            "musical_elements": {
                "rhythm_style": music_info.genre or "未知风格",
                "melody_characteristics": "待分析",
                "instrumentation": "待识别",
                "vocal_style": "待分析"
            },
            "cultural_context": {
                "cultural_background": "待分析",
                "lyrical_themes": "待分析",
                "social_significance": "待分析"
            },
            "recommendations": [
                f"与{music_info.song_name}相似的歌曲",
                f"{music_info.artist}的其他作品",
                f"同类型{music_info.genre}歌曲"
            ],
            "dynamic_prompts": [
                f"听到{music_info.song_name}，让我想起了美好的时光",
                f"这首{music_info.song_name}很适合现在的心情",
                f"要不要再听听{music_info.artist}的其他歌曲？"
            ]
        }

    async def comprehensive_music_analysis(self, audio_file_path: str, audio_features: Dict[str, Any] = None) -> Optional[MusicAnalysis]:
        """🎯 综合音乐分析（识别+大模型验证）"""

        music_logger.info(f"🎯 开始综合音乐分析: {Path(audio_file_path).name}")

        # 第一步：ACRCloud音乐识别
        music_info = await self.identify_music(audio_file_path)

        if not music_info:
            music_logger.warning("⚠️ 音乐识别失败，启用回退策略")
            # 🔧 回退策略：生成基础音乐分析
            return await self._generate_fallback_analysis(audio_file_path, audio_features)

        # 第二步：大模型交叉验证和深度分析
        llm_analysis = await self.llm_cross_validate(music_info, audio_features)

        # 第三步：整合分析结果
        comprehensive_result = MusicAnalysis(
            basic_info=music_info,
            emotional_analysis=llm_analysis.get('emotional_analysis', {}),
            musical_elements=llm_analysis.get('musical_elements', {}),
            cultural_context=llm_analysis.get('cultural_context', {}),
            recommendations=llm_analysis.get('recommendations', []),
            dynamic_prompts=llm_analysis.get('dynamic_prompts', [])
        )

        music_logger.info(f"🎯 综合分析完成: {music_info.song_name}")
        music_logger.info(f"   🎭 主要情感: {llm_analysis.get('emotional_analysis', {}).get('primary_emotion', '未知')}")
        music_logger.info(f"   🎼 音乐风格: {llm_analysis.get('musical_elements', {}).get('rhythm_style', '未知')}")
        music_logger.info(f"   💡 动态建议: {len(llm_analysis.get('dynamic_prompts', []))}条")

        return comprehensive_result

    def get_daily_usage_stats(self) -> Dict[str, Any]:
        """📊 获取每日使用统计"""
        return {
            "daily_requests": self.daily_requests,
            "max_daily_requests": self.max_daily_requests,
            "remaining_requests": max(0, self.max_daily_requests - self.daily_requests),
            "usage_percentage": round((self.daily_requests / self.max_daily_requests) * 100, 2)
        }

    # 🎯 新增：批量处理方法 - 解决您提到的问题
    def add_audio_segment(self, audio_file_path: str, audio_features: Dict[str, Any] = None) -> bool:
        """添加音频片段到批量处理队列"""
        try:
            segment_info = {
                "file_path": audio_file_path,
                "features": audio_features or {},
                "timestamp": time.time()
            }

            self.pending_segments.append(segment_info)
            music_logger.info(f"📥 添加音频片段到队列: {Path(audio_file_path).name} (队列长度: {len(self.pending_segments)})")

            # 检查是否需要触发批量处理
            should_process = (
                len(self.pending_segments) >= self.batch_size or  # 达到批量大小
                (time.time() - self.last_batch_time) > self.batch_timeout  # 超时
            )

            if should_process:
                # 异步触发批量处理
                asyncio.create_task(self._process_batch())

            return True

        except Exception as e:
            music_logger.error(f"❌ 添加音频片段失败: {str(e)}")
            return False

    async def _process_batch(self):
        """处理批量音频片段"""
        try:
            if not self.pending_segments:
                return

            # 取出要处理的片段
            segments_to_process = self.pending_segments[:self.batch_size]
            self.pending_segments = self.pending_segments[self.batch_size:]

            music_logger.info(f"🎯 开始批量处理 {len(segments_to_process)} 个音频片段")

            # 并行处理多个片段
            tasks = []
            for segment in segments_to_process:
                task = self.comprehensive_music_analysis(
                    segment["file_path"],
                    segment["features"]
                )
                tasks.append(task)

            # 等待所有识别完成
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    music_logger.error(f"❌ 片段 {i+1} 处理失败: {str(result)}")
                elif result:
                    successful_results.append(result)
                    music_logger.info(f"✅ 片段 {i+1} 识别成功: {result.basic_info.song_name}")

            # 🎯 发送给动态提示词系统
            if successful_results:
                await self._send_to_dynamic_prompts(successful_results)

            self.last_batch_time = time.time()

        except Exception as e:
            music_logger.error(f"❌ 批量处理失败: {str(e)}")

    async def _send_to_dynamic_prompts(self, music_results: List[MusicAnalysis]):
        """发送识别结果给动态提示词系统"""
        try:
            music_logger.info(f"📤 发送 {len(music_results)} 个音乐识别结果给动态提示词系统")

            # 🎯 真正调用累积管理器
            from sisi_brain.audio_accumulation_manager import get_audio_accumulation_manager
            accumulation_manager = get_audio_accumulation_manager()

            for result in music_results:
                music_logger.info(f"   🎵 {result.basic_info.song_name} - {result.basic_info.artist}")
                music_logger.info(f"   🎭 情感: {result.emotional_analysis.get('primary_emotion', '未知')}")
                music_logger.info(f"   💡 建议: {len(result.dynamic_prompts)}条")

                # 转换为累积管理器需要的格式
                music_data = {
                    'song_name': result.basic_info.song_name,
                    'artist': result.basic_info.artist,
                    'emotional_analysis': result.emotional_analysis,
                    'dynamic_prompts': result.dynamic_prompts,
                    'confidence': result.basic_info.confidence,
                    'timestamp': time.time(),
                    'source': 'acrcloud_music_analyzer'
                }

                accumulation_manager.add_music_recognition(music_data)
                music_logger.info(f"✅ 音乐数据已发送: {result.basic_info.song_name}")

        except Exception as e:
            music_logger.error(f"❌ 发送动态提示词失败: {str(e)}")

    def get_batch_status(self) -> Dict[str, Any]:
        """获取批量处理状态"""
        return {
            "pending_segments": len(self.pending_segments),
            "batch_size": self.batch_size,
            "last_batch_time": self.last_batch_time,
            "time_since_last_batch": time.time() - self.last_batch_time,
            "batch_timeout": self.batch_timeout
        }

    async def analyze_music_with_llm(self, music_info) -> Optional[MusicAnalysis]:
        """🧠 使用大模型分析音乐信息"""
        try:
            music_logger.info(f"🧠 开始大模型音乐分析: {music_info.song_name}")

            # 调用comprehensive_music_analysis方法
            return await self.comprehensive_music_analysis(music_info.song_name, {
                'artist': music_info.artist,
                'album': music_info.album,
                'release_date': music_info.release_date,
                'genre': music_info.genre,
                'confidence': music_info.confidence
            })

        except Exception as e:
            music_logger.error(f"❌ 大模型音乐分析失败: {e}")
            return None

# 全局实例
_music_analyzer = None

def get_music_analyzer() -> ACRCloudMusicAnalyzer:
    """获取音乐分析器实例"""
    global _music_analyzer
    if _music_analyzer is None:
        _music_analyzer = ACRCloudMusicAnalyzer()
    return _music_analyzer

async def analyze_music_file(audio_file_path: str, audio_features: Dict[str, Any] = None) -> Optional[MusicAnalysis]:
    """🎵 分析音乐文件的便捷函数"""
    analyzer = get_music_analyzer()
    return await analyzer.comprehensive_music_analysis(audio_file_path, audio_features)

# 在ACRCloudMusicAnalyzer类中添加回退方法
def _add_fallback_method():
    """动态添加回退方法到ACRCloudMusicAnalyzer类"""
    async def _generate_fallback_analysis(self, audio_file_path: str, audio_features: Dict[str, Any] = None) -> Optional[MusicAnalysis]:
        """智能回退音乐分析 - 基于音频特征判断曲风和误触发"""
        try:
            music_logger.info("🔄 启动智能回退分析")

            # 🎯 音频特征分析
            audio_analysis = self._analyze_audio_features(audio_file_path)

            # 🎯 判断是否为误触发
            if audio_analysis['is_false_trigger']:
                music_logger.info("⚠️ 检测到误触发，可能不是音乐")
                return None

            # 🎯 基于特征推测曲风
            genre_analysis = self._predict_genre_from_features(audio_analysis)

            # 创建智能音乐信息
            fallback_info = MusicInfo(
                song_name=f"{genre_analysis['style']}音乐",
                artist="未知艺术家",
                album="未知专辑",
                genre=genre_analysis['genre'],
                duration=audio_analysis.get('duration'),
                release_date=None,
                confidence=genre_analysis['confidence'],
                acr_id="intelligent_fallback"
            )

            # 智能情感分析
            emotional_analysis = {
                "primary_emotion": genre_analysis['emotion'],
                "music_style": genre_analysis['style'],
                "tempo": audio_analysis['tempo'],
                "mood": genre_analysis['mood'],
                "energy_level": audio_analysis['energy'],
                "confidence": genre_analysis['confidence']
            }

            # 智能动态提示词
            prompts = self._generate_intelligent_prompts(genre_analysis, audio_analysis)

            music_logger.info(f"✅ 智能回退分析完成: {genre_analysis['style']} (置信度: {genre_analysis['confidence']:.2f})")

            return MusicAnalysis(
                basic_info=fallback_info,
                emotional_analysis=emotional_analysis,
                dynamic_prompts=prompts,
                confidence=genre_analysis['confidence'],
                analysis_time=time.time()
            )

        except Exception as e:
            music_logger.error(f"❌ 智能回退分析失败: {e}")
            return None

    def _analyze_audio_features(self, audio_file_path: str) -> Dict[str, Any]:
        """分析音频特征"""
        try:
            import librosa
            import numpy as np

            # 加载音频
            y, sr = librosa.load(audio_file_path, sr=22050, duration=10)

            # 🎯 基础特征提取
            # 1. 节拍和节奏
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)

            # 2. 频谱特征
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]

            # 3. MFCC特征
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)

            # 4. 零交叉率
            zcr = librosa.feature.zero_crossing_rate(y)[0]

            # 5. 能量分析
            rms = librosa.feature.rms(y=y)[0]

            # 🎯 误触发检测
            is_false_trigger = self._detect_false_trigger(y, sr, spectral_centroids, zcr, rms)

            return {
                'tempo': self._classify_tempo(tempo),
                'energy': self._classify_energy(np.mean(rms)),
                'brightness': self._classify_brightness(np.mean(spectral_centroids)),
                'rhythm_stability': self._analyze_rhythm_stability(beats),
                'duration': len(y) / sr,
                'is_false_trigger': is_false_trigger,
                'raw_tempo': tempo,
                'raw_features': {
                    'spectral_centroid': np.mean(spectral_centroids),
                    'spectral_rolloff': np.mean(spectral_rolloff),
                    'mfcc_mean': np.mean(mfccs, axis=1),
                    'zcr_mean': np.mean(zcr),
                    'rms_mean': np.mean(rms)
                }
            }

        except Exception as e:
            music_logger.error(f"❌ 音频特征分析失败: {e}")
            return {
                'tempo': '中等',
                'energy': '中等',
                'brightness': '中等',
                'rhythm_stability': '稳定',
                'duration': 10,
                'is_false_trigger': False,
                'raw_tempo': 120
            }

    def _detect_false_trigger(self, y, sr, spectral_centroids, zcr, rms) -> bool:
        """检测是否为误触发"""
        import numpy as np

        # 1. 检查音频长度 - 太短可能是误触发
        if len(y) < sr * 3:  # 少于3秒
            return True

        # 2. 检查能量分布 - 能量太低可能是环境音
        if np.mean(rms) < 0.01:
            return True

        # 3. 检查频谱特征 - 频谱过于单调可能不是音乐
        if np.std(spectral_centroids) < 200:
            return True

        # 4. 检查零交叉率 - 过高可能是噪音
        if np.mean(zcr) > 0.3:
            return True

        return False

    def _predict_genre_from_features(self, audio_analysis: Dict) -> Dict[str, Any]:
        """基于音频特征预测曲风"""
        tempo = audio_analysis['raw_tempo']
        energy = audio_analysis['energy']
        brightness = audio_analysis['brightness']
        rhythm_stability = audio_analysis['rhythm_stability']

        # 🎯 曲风判断逻辑
        if tempo > 140 and energy == '高':
            if brightness == '高':
                return {
                    'genre': '电子音乐',
                    'style': '动感电音',
                    'emotion': 'excited',
                    'mood': '兴奋',
                    'confidence': 0.75
                }
            else:
                return {
                    'genre': '摇滚',
                    'style': '激烈摇滚',
                    'emotion': 'energetic',
                    'mood': '激昂',
                    'confidence': 0.7
                }
        elif tempo > 120 and energy in ['中等', '高']:
            if rhythm_stability == '稳定':
                return {
                    'genre': '流行音乐',
                    'style': '流行歌曲',
                    'emotion': 'happy',
                    'mood': '愉快',
                    'confidence': 0.65
                }
            else:
                return {
                    'genre': '说唱',
                    'style': '节奏说唱',
                    'emotion': 'confident',
                    'mood': '自信',
                    'confidence': 0.6
                }
        elif tempo < 80:
            return {
                'genre': '抒情音乐',
                'style': '慢节奏抒情',
                'emotion': 'calm',
                'mood': '平静',
                'confidence': 0.6
            }
        elif brightness == '低' and energy == '低':
            return {
                'genre': '古典音乐',
                'style': '轻柔古典',
                'emotion': 'peaceful',
                'mood': '宁静',
                'confidence': 0.55
            }
        else:
            return {
                'genre': '轻音乐',
                'style': '背景音乐',
                'emotion': 'neutral',
                'mood': '中性',
                'confidence': 0.4
            }

    def _classify_tempo(self, tempo: float) -> str:
        """分类节拍"""
        if tempo < 60:
            return '很慢'
        elif tempo < 80:
            return '慢'
        elif tempo < 100:
            return '中慢'
        elif tempo < 120:
            return '中等'
        elif tempo < 140:
            return '中快'
        elif tempo < 160:
            return '快'
        else:
            return '很快'

    def _classify_energy(self, rms_mean: float) -> str:
        """分类能量"""
        if rms_mean < 0.02:
            return '低'
        elif rms_mean < 0.05:
            return '中等'
        else:
            return '高'

    def _classify_brightness(self, spectral_centroid: float) -> str:
        """分类亮度"""
        if spectral_centroid < 1500:
            return '低'
        elif spectral_centroid < 3000:
            return '中等'
        else:
            return '高'

    def _analyze_rhythm_stability(self, beats) -> str:
        """分析节奏稳定性"""
        import numpy as np
        if len(beats) < 2:
            return '不稳定'

        intervals = np.diff(beats)
        if np.std(intervals) < 0.1:
            return '很稳定'
        elif np.std(intervals) < 0.2:
            return '稳定'
        else:
            return '不稳定'

    def _generate_intelligent_prompts(self, genre_analysis: Dict, audio_analysis: Dict) -> List[str]:
        """生成智能动态提示词"""
        style = genre_analysis['style']
        mood = genre_analysis['mood']
        tempo = audio_analysis['tempo']

        prompts = [
            f"检测到{style}，节奏{tempo}，氛围{mood}",
            f"这种{genre_analysis['genre']}很适合当前的对话氛围",
        ]

        # 根据曲风添加特定建议
        if genre_analysis['genre'] == '电子音乐':
            prompts.append("可以聊聊电音文化或者夜生活话题")
        elif genre_analysis['genre'] == '摇滚':
            prompts.append("摇滚精神！可以聊聊音乐态度或者青春话题")
        elif genre_analysis['genre'] == '流行音乐':
            prompts.append("流行歌曲总是能引起共鸣，可以聊聊最近的音乐趋势")
        elif genre_analysis['genre'] == '抒情音乐':
            prompts.append("慢节奏很适合深度交流，可以聊聊内心感受")
        elif genre_analysis['genre'] == '古典音乐':
            prompts.append("古典音乐体现了高雅品味，可以聊聊艺术和文化")
        else:
            prompts.append("背景音乐营造了不错的氛围")

        return prompts

    # 动态添加所有回退方法到类
    ACRCloudMusicAnalyzer._generate_fallback_analysis = _generate_fallback_analysis
    ACRCloudMusicAnalyzer._analyze_audio_features = _analyze_audio_features
    ACRCloudMusicAnalyzer._detect_false_trigger = _detect_false_trigger
    ACRCloudMusicAnalyzer._predict_genre_from_features = _predict_genre_from_features
    ACRCloudMusicAnalyzer._classify_tempo = _classify_tempo
    ACRCloudMusicAnalyzer._classify_energy = _classify_energy
    ACRCloudMusicAnalyzer._classify_brightness = _classify_brightness
    ACRCloudMusicAnalyzer._analyze_rhythm_stability = _analyze_rhythm_stability
    ACRCloudMusicAnalyzer._generate_intelligent_prompts = _generate_intelligent_prompts

    music_logger.info("✅ 音乐识别回退方法动态添加完成")

# 执行动态添加
_add_fallback_method()
