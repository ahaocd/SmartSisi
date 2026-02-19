#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
音频人性化分析器
功能：5次音频累积后进行人性化分析描述
分析内容：现在什么情况、可能的地方、有什么声音、哪些人、哪些音乐
"""

import json
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class AudioAnalysisResult:
    """音频分析结果"""
    situation_description: str  # 情况描述
    location_guess: str        # 地点猜测
    sound_analysis: List[str]  # 声音分析
    people_analysis: str       # 人员分析
    music_analysis: str        # 音乐分析
    confidence: float          # 置信度
    timestamp: float           # 时间戳

class AudioHumanizedAnalyzer:
    """音频人性化分析器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 🔧 使用统一配置系统
        try:
            from utils.config_util import load_config
            config = load_config()
            
            self.api_key = config.get('audio_humanized_api_key', '')
            self.base_url = config.get('audio_humanized_base_url', '')
            self.model = config.get('audio_humanized_model', 'Qwen/Qwen3-8B')
            self.temperature = float(config.get('audio_humanized_temperature', '0.6'))
            self.max_tokens = int(config.get('audio_humanized_max_tokens', '2000'))
            
            self.logger.info(f"✅ 音频人性化分析器初始化完成 - 模型: {self.model}")
            
        except Exception as e:
            self.logger.error(f"❌ 配置加载失败: {e}")
            # 备用配置
            self.api_key = '910663e20c4a49b286f27009dde10497.qYauy3JahUXDed7C'
            self.base_url = 'https://open.bigmodel.cn/api/paas/v4/'
            self.model = 'GLM-4.5-Flash'
            self.temperature = 0.6
            self.max_tokens = 2000
    
    def analyze_accumulated_audio(self, audio_contexts: List[Dict[str, Any]]) -> AudioAnalysisResult:
        """
        分析累积的音频上下文

        Args:
            audio_contexts: 累积的3次音频上下文数据

        Returns:
            AudioAnalysisResult: 人性化分析结果
        """
        try:
            self.logger.info(f"🧠 开始分析{len(audio_contexts)}个累积音频上下文")

            # 🎯 临时绕过API调用，直接使用智能回退分析
            if not self.api_key or len(self.api_key) < 10:
                self.logger.warning("⚠️ API密钥无效，直接使用智能回退分析")
                fallback_result = self._create_fallback_result(audio_contexts)
                self.logger.info(f"🛡️ 使用智能回退结果: {fallback_result.situation_description}")
                return fallback_result

            # 构建分析提示词
            analysis_prompt = self._build_analysis_prompt(audio_contexts)

            # 调用大模型进行分析
            analysis_result = self._call_llm_analysis(analysis_prompt)

            # 解析分析结果
            parsed_result = self._parse_analysis_result(analysis_result)

            self.logger.info(f"✅ 音频人性化分析完成 - 置信度: {parsed_result.confidence:.2f}")
            return parsed_result

        except Exception as e:
            self.logger.error(f"❌ 音频人性化分析失败: {e}")
            # 🔧 API失败时，返回识别到的数据，去除空数据
            fallback_result = self._create_data_aligned_result(audio_contexts)
            self.logger.info(f"🛡️ 使用数据对齐结果: {fallback_result.situation_description}")
            return fallback_result
    
    def _build_analysis_prompt(self, audio_contexts: List[Dict[str, Any]]) -> str:
        """构建分析提示词"""
        
        # 整理音频数据 - 🔧 修复数据格式问题
        audio_summary = []
        for i, context in enumerate(audio_contexts, 1):
            audio_type = context.get('audio_type', 'unknown')
            confidence = float(context.get('confidence', 0.0))  # 确保是float
            features = context.get('features', {})
            
            # 🔧 修复时间戳处理 - 支持字符串和数字
            timestamp = context.get('timestamp', time.time())
            if isinstance(timestamp, str):
                try:
                    # 尝试解析ISO格式时间戳
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = dt.timestamp()
                except:
                    timestamp = time.time()
            elif not isinstance(timestamp, (int, float)):
                timestamp = time.time()
            
            audio_summary.append(f"""
第{i}次检测 (时间: {time.strftime('%H:%M:%S', time.localtime(float(timestamp)))}):
- 音频类型: {audio_type}
- 置信度: {confidence:.2f}
- 特征: {json.dumps(features, ensure_ascii=False, indent=2)}
""")
        
        prompt = f"""
你是一个专业的音频环境分析师，具有丰富的声学分析和环境感知经验。
请基于以下5次连续的音频检测数据，进行人性化的环境分析描述。

=== 音频检测数据 ===
{''.join(audio_summary)}

=== 分析要求 ===
请从以下5个维度进行详细分析：

1. **情况描述**: 根据音频数据推测当前的整体情况和环境状态
2. **地点猜测**: 基于声音特征推测可能的地点或场所类型
3. **声音分析**: 详细分析检测到的各种声音及其特征
4. **人员分析**: 推测环境中的人数、活动状态、交流情况
5. **音乐分析**: 分析是否有音乐播放，音乐类型和特征

请以JSON格式返回分析结果：
{{
    "situation_description": "详细的情况描述",
    "location_guess": "地点猜测",
    "sound_analysis": ["声音1", "声音2", "声音3"],
    "people_analysis": "人员分析",
    "music_analysis": "音乐分析",
    "confidence": 0.85
}}
"""
        return prompt
    
    def _call_llm_analysis(self, prompt: str) -> str:
        """调用大模型进行分析"""

        # 🔥 详细日志：检查配置
        self.logger.info(f"🔥 [API调用] 开始调用GLM-4.5-Flash")
        self.logger.info(f"🔥 [API调用] API密钥: {self.api_key[:10]}...{self.api_key[-5:] if len(self.api_key) > 15 else '短密钥'}")
        self.logger.info(f"🔥 [API调用] Base URL: {self.base_url}")
        self.logger.info(f"🔥 [API调用] 模型: {self.model}")

        if not self.api_key:
            raise Exception("API密钥未配置")

        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

        self.logger.info(f"🔥 [API调用] 请求URL: {self.base_url}/chat/completions")
        self.logger.info(f"🔥 [API调用] 请求数据: {str(data)[:200]}...")

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=20  # 🔧 修改超时时间到20秒
            )

            self.logger.info(f"🔥 [API调用] 响应状态码: {response.status_code}")
            self.logger.info(f"🔥 [API调用] 响应头: {dict(response.headers)}")

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                self.logger.info(f"🔥 [API调用] 成功！返回内容长度: {len(content)}")
                self.logger.info(f"🔥 [API调用] 返回内容预览: {content[:100]}...")
                return content
            else:
                error_text = response.text
                self.logger.error(f"🔥 [API调用] 失败！状态码: {response.status_code}")
                self.logger.error(f"🔥 [API调用] 错误响应: {error_text}")
                raise Exception(f"API调用失败: {response.status_code} - {error_text}")

        except requests.exceptions.Timeout:
            self.logger.error(f"🔥 [API调用] 超时！20秒内未响应")
            raise Exception("API调用超时")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"🔥 [API调用] 连接错误: {e}")
            raise Exception(f"API连接失败: {e}")
        except Exception as e:
            self.logger.error(f"🔥 [API调用] 未知错误: {e}")
            raise
    
    def _parse_analysis_result(self, analysis_text: str) -> AudioAnalysisResult:
        """解析分析结果"""
        
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
            
            return AudioAnalysisResult(
                situation_description=result_data.get('situation_description', ''),
                location_guess=result_data.get('location_guess', ''),
                sound_analysis=result_data.get('sound_analysis', []),
                people_analysis=result_data.get('people_analysis', ''),
                music_analysis=result_data.get('music_analysis', ''),
                confidence=float(result_data.get('confidence', 0.5)),
                timestamp=time.time()
            )
            
        except Exception as e:
            self.logger.error(f"❌ 解析分析结果失败: {e}")
            self.logger.error(f"❌ 原始分析文本: {analysis_text[:200]}...")
            # 确保返回AudioAnalysisResult类型
            return self._create_fallback_result([])
    
    def _create_fallback_result(self, audio_contexts: List[Dict[str, Any]] = None) -> AudioAnalysisResult:
        """🛡️ 基于原始数据创建智能回退结果"""

        if not audio_contexts:
            # 🔥 修复：返回基于真实数据的基础分析
            return AudioAnalysisResult(
                situation_description="未检测到音频活动",
                location_guess="环境信息不足",
                sound_analysis=["静音"],
                people_analysis="无人员活动检测",
                music_analysis="无音乐检测",
                confidence=0.1,  # 低置信度，表示数据不足
                timestamp=time.time()
            )

        try:
            # 🎯 基于原始音频上下文数据进行智能分析
            self.logger.info(f"🛡️ 开始基于{len(audio_contexts)}个原始音频上下文创建回退分析")

            # 统计音频类型
            audio_types = []
            confidences = []
            timestamps = []
            features_list = []

            for i, context in enumerate(audio_contexts):
                # 🔧 修复数据格式问题 - 支持多种数据源
                audio_type = 'unknown'
                confidence = 0.0

                # 方法1：直接从context获取
                if 'audio_type' in context:
                    audio_type = context.get('audio_type', 'unknown')
                    confidence = float(context.get('confidence', 0.0))

                # 方法2：从features中获取（SmartAudioCollector格式）
                elif 'features' in context and isinstance(context['features'], dict):
                    features = context['features']
                    if 'audio_type' in features:
                        audio_type = features.get('audio_type', 'unknown')
                        confidence = float(features.get('confidence', 0.0))

                # 方法3：从嵌套结构中获取
                elif isinstance(context, dict):
                    # 检查是否有嵌套的音频分析结果
                    for key, value in context.items():
                        if isinstance(value, dict) and 'audio_type' in value:
                            audio_type = value.get('audio_type', 'unknown')
                            confidence = float(value.get('confidence', 0.0))
                            break

                # 🔍 调试：记录数据格式
                self.logger.info(f"🔍 [回退分析] 批次{i+1}: audio_type={audio_type}, confidence={confidence:.2f}")
                self.logger.info(f"🔍 [回退分析] 原始数据: {str(context)[:200]}...")

                timestamp = context.get('timestamp', time.time())
                features = context.get('features', {})

                audio_types.append(audio_type)
                confidences.append(confidence)
                timestamps.append(timestamp)
                features_list.append(features)

            # 分析音频类型分布
            speech_count = audio_types.count('speech')
            music_count = audio_types.count('music')
            noise_count = audio_types.count('noise')
            silence_count = audio_types.count('silence')

            # 计算平均置信度
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            # 🎯 基于数据生成情况描述
            if speech_count >= len(audio_contexts) * 0.6:
                situation_description = f"检测到{speech_count}次语音活动，推测为对话或交流环境，持续时间约{len(audio_contexts)*10}秒"
                location_guess = "室内对话场所（办公室、会议室或家庭环境）"
                people_analysis = f"推测有{max(1, speech_count//2)}人参与对话，交流较为活跃"
            elif music_count >= len(audio_contexts) * 0.4:
                situation_description = f"检测到{music_count}次音乐播放，推测为娱乐或休闲环境"
                location_guess = "娱乐场所或个人休闲空间"
                people_analysis = f"音乐环境，可能有{max(1, (speech_count + music_count)//3)}人在场"
            elif silence_count >= len(audio_contexts) * 0.5:
                situation_description = f"环境较为安静，检测到{silence_count}次静音，可能为专注工作或休息环境"
                location_guess = "安静的室内环境（图书馆、办公室或卧室）"
                people_analysis = "环境安静，人员活动较少"
            else:
                situation_description = f"混合音频环境，包含语音({speech_count}次)、音乐({music_count}次)、噪音({noise_count}次)"
                location_guess = "复杂的室内环境，可能为多功能场所"
                people_analysis = f"多样化环境，推测有{max(1, len(set(audio_types)))}种不同活动"

            # 🎯 生成声音分析
            sound_analysis = []
            if speech_count > 0:
                sound_analysis.append(f"语音活动: {speech_count}次，平均置信度{sum(c for i, c in enumerate(confidences) if audio_types[i] == 'speech')/max(1, speech_count):.2f}")
            if music_count > 0:
                sound_analysis.append(f"音乐检测: {music_count}次，可能为背景音乐或主动播放")
            if noise_count > 0:
                sound_analysis.append(f"环境噪音: {noise_count}次，环境可能较为嘈杂")
            if silence_count > 0:
                sound_analysis.append(f"静音时段: {silence_count}次，环境整体较为安静")

            if not sound_analysis:
                sound_analysis = ["检测到音频活动，但类型不明确"]

            # 🎯 生成音乐分析
            if music_count > 0:
                music_analysis = f"检测到{music_count}次音乐活动，可能为背景音乐或娱乐播放，建议关注用户音乐偏好"
            else:
                music_analysis = "未检测到明显的音乐活动，环境以语音或静音为主"

            # 🎯 计算回退置信度（基于原始数据质量）
            fallback_confidence = min(0.7, max(0.3, avg_confidence * 0.8))  # 回退置信度略低于原始数据

            self.logger.info(f"🛡️ 回退分析完成 - 语音:{speech_count}, 音乐:{music_count}, 静音:{silence_count}, 置信度:{fallback_confidence:.2f}")

            return AudioAnalysisResult(
                situation_description=situation_description,
                location_guess=location_guess,
                sound_analysis=sound_analysis,
                people_analysis=people_analysis,
                music_analysis=music_analysis,
                confidence=fallback_confidence,
                timestamp=time.time()
            )

        except Exception as e:
            self.logger.error(f"❌ 智能回退分析失败: {e}")
            # 最终回退到基础结果
            return AudioAnalysisResult(
                situation_description="音频分析遇到技术问题，使用基础环境推测",
                location_guess="室内环境",
                sound_analysis=["检测到音频信号"],
                people_analysis="无法确定具体人员情况",
                music_analysis="音频分析功能暂时不可用",
                confidence=0.2,
                timestamp=time.time()
            )

    def _create_data_aligned_result(self, audio_contexts: List[Dict[str, Any]]) -> AudioAnalysisResult:
        """🔧 数据对齐方法：去除空数据，返回识别到的数据"""
        if not audio_contexts:
            return AudioAnalysisResult(
                situation_description="",
                location_guess="",
                sound_analysis=[],
                people_analysis="",
                music_analysis="",
                confidence=0.0,
                timestamp=time.time()
            )

        # 收集所有有效数据
        situation_parts = []
        sound_analysis = []
        speakers = []
        music_detected = False
        total_confidence = 0.0
        valid_count = 0

        for i, context in enumerate(audio_contexts):
            audio_type = context.get('audio_type', '')
            confidence = context.get('confidence', 0.0)
            features = context.get('features', {})

            # 🔥 详细日志：检查每个上下文数据
            self.logger.info(f"🔥 [数据对齐] 上下文{i+1}: audio_type='{audio_type}', confidence={confidence}")
            self.logger.info(f"🔥 [数据对齐] 上下文{i+1}: features keys={list(features.keys())}")

            # 🔧 修复：即使audio_type为空，也尝试从features中提取数据
            if not audio_type and features:
                # 尝试从YAMNet结果中获取音频类型
                yamnet = features.get('yamnet_result', {})
                if yamnet.get('top_class'):
                    audio_type = yamnet['top_class']
                    confidence = yamnet.get('confidence', 0.5)
                    self.logger.info(f"🔧 [数据修复] 从YAMNet获取: {audio_type}, {confidence}")

            # 🔧 修复：降低跳过条件，只跳过完全无效的数据
            if not audio_type and confidence <= 0 and not features:
                self.logger.warning(f"⚠️ [数据对齐] 跳过完全无效的上下文{i+1}")
                continue

            valid_count += 1
            total_confidence += confidence

            # 收集音频类型
            situation_parts.append(f"检测到{audio_type}")
            sound_analysis.append(f"{audio_type}: {confidence:.2f}")

            # 处理SenseVoice数据
            sensevoice = features.get('sensevoice_result', {})
            if sensevoice:
                text = sensevoice.get('text', '').strip()
                speaker = sensevoice.get('speaker_id', '')
                has_bgm = sensevoice.get('has_bgm', False)

                if text:
                    situation_parts.append(f"识别文本: {text[:20]}...")
                if speaker and speaker not in speakers:
                    speakers.append(speaker)
                if has_bgm:
                    music_detected = True

            # 处理YAMNet数据
            yamnet = features.get('yamnet_result', {})
            if yamnet:
                top_class = yamnet.get('top_class', '')
                if top_class:
                    sound_analysis.append(f"YAMNet: {top_class}")

        # 生成结果
        avg_confidence = total_confidence / valid_count if valid_count > 0 else 0.0

        situation_description = " | ".join(situation_parts) if situation_parts else ""
        location_guess = "语音交互环境" if speakers else "音频检测环境"
        people_analysis = f"{len(speakers)}人" if speakers else ""
        music_analysis = "检测到背景音乐" if music_detected else ""

        return AudioAnalysisResult(
            situation_description=situation_description,
            location_guess=location_guess,
            sound_analysis=sound_analysis,
            people_analysis=people_analysis,
            music_analysis=music_analysis,
            confidence=avg_confidence,
            timestamp=time.time()
        )




# 全局实例
_audio_humanized_analyzer = None

def get_audio_humanized_analyzer() -> AudioHumanizedAnalyzer:
    """获取音频人性化分析器实例"""
    global _audio_humanized_analyzer
    if _audio_humanized_analyzer is None:
        _audio_humanized_analyzer = AudioHumanizedAnalyzer()
    return _audio_humanized_analyzer
