#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
音乐仿真拟人处理器
功能：整理ACRCloud音乐识别结果，进行人性化描述和情感分析
"""

import json
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import configparser
import requests

@dataclass
class MusicProcessResult:
    """音乐处理结果"""
    song_info: Dict[str, Any]      # 歌曲信息
    emotional_analysis: str        # 情感分析
    scene_description: str         # 场景描述
    user_mood_guess: str          # 用户心情猜测
    interaction_suggestion: str    # 交互建议
    confidence: float             # 置信度
    timestamp: float              # 时间戳

class MusicHumanizedProcessor:
    """音乐仿真拟人处理器"""
    
    def __init__(self, config_path: str = "system.conf"):
        self.logger = logging.getLogger(__name__)
        self.config = configparser.ConfigParser()
        self.config.read(config_path, encoding='utf-8')
        
        # 从配置文件读取音乐偏好分析配置
        self.api_key = self.config.get('key', 'music_preference_analysis_api_key', fallback='')
        self.base_url = self.config.get('key', 'music_preference_analysis_base_url', fallback='https://api.siliconflow.cn/v1')
        self.model = self.config.get('key', 'music_preference_analysis_model', fallback='Qwen/Qwen3-30B-A3B')
        self.temperature = float(self.config.get('key', 'music_preference_analysis_temperature', fallback='0.4'))
        self.max_tokens = int(self.config.get('key', 'music_preference_analysis_max_tokens', fallback='2000'))
        
        self.logger.info(f"✅ 音乐仿真拟人处理器初始化完成 - 模型: {self.model}")
    
    def process_music_recognition(self, acrcloud_result: Dict[str, Any], audio_context: Dict[str, Any] = None) -> MusicProcessResult:
        """
        处理ACRCloud音乐识别结果
        
        Args:
            acrcloud_result: ACRCloud识别结果
            audio_context: 音频上下文信息
            
        Returns:
            MusicProcessResult: 处理后的音乐分析结果
        """
        try:
            self.logger.info(f"🎵 开始处理音乐识别结果")
            
            # 提取歌曲基本信息
            song_info = self._extract_song_info(acrcloud_result)
            
            # 构建分析提示词
            analysis_prompt = self._build_music_analysis_prompt(song_info, audio_context)
            
            # 调用大模型进行分析
            analysis_result = self._call_llm_analysis(analysis_prompt)
            
            # 解析分析结果
            parsed_result = self._parse_music_analysis(analysis_result, song_info)
            
            self.logger.info(f"✅ 音乐仿真拟人处理完成 - 歌曲: {song_info.get('title', 'Unknown')}")
            return parsed_result
            
        except Exception as e:
            self.logger.error(f"❌ 音乐仿真拟人处理失败: {e}")
            return self._create_fallback_result(acrcloud_result)
    
    def _extract_song_info(self, acrcloud_result: Dict[str, Any]) -> Dict[str, Any]:
        """提取歌曲基本信息"""
        
        song_info = {}
        
        if 'metadata' in acrcloud_result and 'music' in acrcloud_result['metadata']:
            music_data = acrcloud_result['metadata']['music'][0] if acrcloud_result['metadata']['music'] else {}
            
            song_info = {
                'title': music_data.get('title', 'Unknown'),
                'artist': music_data.get('artists', [{}])[0].get('name', 'Unknown') if music_data.get('artists') else 'Unknown',
                'album': music_data.get('album', {}).get('name', 'Unknown'),
                'release_date': music_data.get('release_date', 'Unknown'),
                'duration': music_data.get('duration_ms', 0) // 1000,
                'genre': music_data.get('genres', [{}])[0].get('name', 'Unknown') if music_data.get('genres') else 'Unknown',
                'label': music_data.get('label', 'Unknown'),
                'acrid': music_data.get('acrid', ''),
                'score': acrcloud_result.get('status', {}).get('msg', 'Success')
            }
        else:
            song_info = {
                'title': 'Unknown',
                'artist': 'Unknown',
                'album': 'Unknown',
                'release_date': 'Unknown',
                'duration': 0,
                'genre': 'Unknown',
                'label': 'Unknown',
                'acrid': '',
                'score': 'No Match'
            }
        
        return song_info
    
    def _build_music_analysis_prompt(self, song_info: Dict[str, Any], audio_context: Dict[str, Any] = None) -> str:
        """构建音乐分析提示词"""
        
        context_info = ""
        if audio_context:
            context_info = f"""
=== 音频环境上下文 ===
- 检测时间: {time.strftime('%H:%M:%S', time.localtime(audio_context.get('timestamp', time.time())))}
- 音频质量: {audio_context.get('confidence', 0.0):.2f}
- 环境特征: {json.dumps(audio_context.get('features', {}), ensure_ascii=False)}
"""
        
        prompt = f"""
你是一个专业的音乐情感分析师和人机交互专家，具有丰富的音乐心理学和用户行为分析经验。
请基于以下音乐识别结果，进行深度的人性化分析和交互建议。

=== 识别的歌曲信息 ===
- 歌曲名称: {song_info.get('title', 'Unknown')}
- 艺术家: {song_info.get('artist', 'Unknown')}
- 专辑: {song_info.get('album', 'Unknown')}
- 发行日期: {song_info.get('release_date', 'Unknown')}
- 时长: {song_info.get('duration', 0)}秒
- 风格: {song_info.get('genre', 'Unknown')}
- 唱片公司: {song_info.get('label', 'Unknown')}
{context_info}

=== 分析要求 ===
请从以下5个维度进行深入分析：

1. **情感分析**: 分析这首歌的情感色彩、情绪表达、心理暗示
2. **场景描述**: 推测用户播放这首歌的可能场景和环境
3. **用户心情猜测**: 基于歌曲选择推测用户当前的心理状态和情绪
4. **交互建议**: 提供与用户互动的建议，包括话题、回应方式、情感支持
5. **个性化洞察**: 分析用户的音乐偏好和可能的性格特征

=== 输出格式 ===
请以JSON格式输出分析结果：
{{
    "emotional_analysis": "详细的情感分析",
    "scene_description": "场景描述和环境推测",
    "user_mood_guess": "用户心情和心理状态分析",
    "interaction_suggestion": "具体的交互建议和话题推荐",
    "personality_insights": "用户个性化洞察",
    "confidence": 0.85
}}

请确保分析结果具有温暖、理解、共情的人性化特质，体现出对用户情感的深度理解。
"""
        
        return prompt
    
    def _call_llm_analysis(self, prompt: str) -> str:
        """调用大模型进行分析"""
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
                {
                    'role': 'system',
                    'content': '你是一个专业的音乐情感分析师，擅长从音乐选择中洞察用户的情感状态和心理需求。'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }
        
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"API调用失败: {response.status_code} - {response.text}")
    
    def _parse_music_analysis(self, analysis_text: str, song_info: Dict[str, Any]) -> MusicProcessResult:
        """解析音乐分析结果"""
        
        try:
            # 尝试解析JSON
            if '```json' in analysis_text:
                json_start = analysis_text.find('```json') + 7
                json_end = analysis_text.find('```', json_start)
                json_text = analysis_text[json_start:json_end].strip()
            else:
                # 寻找JSON对象
                start = analysis_text.find('{')
                end = analysis_text.rfind('}') + 1
                json_text = analysis_text[start:end]
            
            result_data = json.loads(json_text)
            
            return MusicProcessResult(
                song_info=song_info,
                emotional_analysis=result_data.get('emotional_analysis', ''),
                scene_description=result_data.get('scene_description', ''),
                user_mood_guess=result_data.get('user_mood_guess', ''),
                interaction_suggestion=result_data.get('interaction_suggestion', ''),
                confidence=float(result_data.get('confidence', 0.5)),
                timestamp=time.time()
            )
            
        except Exception as e:
            self.logger.error(f"❌ 解析音乐分析结果失败: {e}")
            return self._create_fallback_result(song_info)
    
    def _create_fallback_result(self, song_info_or_acrcloud: Dict[str, Any]) -> MusicProcessResult:
        """创建备用分析结果"""
        
        # 如果传入的是ACRCloud结果，先提取歌曲信息
        if 'metadata' in song_info_or_acrcloud:
            song_info = self._extract_song_info(song_info_or_acrcloud)
        else:
            song_info = song_info_or_acrcloud
        
        return MusicProcessResult(
            song_info=song_info,
            emotional_analysis="音乐分析暂时不可用，但我听到了美妙的音乐",
            scene_description="用户正在享受音乐时光",
            user_mood_guess="用户心情应该不错，在听音乐放松",
            interaction_suggestion="可以和用户聊聊这首歌，或者推荐类似的音乐",
            confidence=0.3,
            timestamp=time.time()
        )

# 全局实例
_music_humanized_processor = None

def get_music_humanized_processor() -> MusicHumanizedProcessor:
    """获取音乐仿真拟人处理器实例"""
    global _music_humanized_processor
    if _music_humanized_processor is None:
        _music_humanized_processor = MusicHumanizedProcessor()
    return _music_humanized_processor

if __name__ == "__main__":
    # 测试代码
    processor = get_music_humanized_processor()
    
    # 模拟ACRCloud识别结果
    test_acrcloud_result = {
        'status': {'msg': 'Success', 'code': 0},
        'metadata': {
            'music': [{
                'title': '稻香',
                'artists': [{'name': '周杰伦'}],
                'album': {'name': '魔杰座'},
                'release_date': '2008-10-15',
                'duration_ms': 223000,
                'genres': [{'name': 'Pop'}],
                'label': '杰威尔音乐',
                'acrid': 'test123'
            }]
        }
    }
    
    result = processor.process_music_recognition(test_acrcloud_result)
    print(f"🎵 音乐处理结果:")
    print(f"歌曲信息: {result.song_info}")
    print(f"情感分析: {result.emotional_analysis}")
    print(f"场景描述: {result.scene_description}")
    print(f"心情猜测: {result.user_mood_guess}")
    print(f"交互建议: {result.interaction_suggestion}")
    print(f"置信度: {result.confidence:.2f}")
