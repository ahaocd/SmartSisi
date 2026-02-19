#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
音频累积管理器
功能：管理20次音频分析累积，触发动态大模型中枢抽取，管理缓存清理
"""

import json
import time
import logging
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import pickle

from utils import config_util as cfg
from .audio_humanized_analyzer import get_audio_humanized_analyzer, AudioAnalysisResult
from .music_humanized_processor import get_music_humanized_processor, MusicProcessResult

@dataclass
class AccumulationBatch:
    """累积批次数据"""
    batch_id: str                           # 批次ID
    audio_analysis: AudioAnalysisResult     # 音频人性化分析结果
    music_results: List[MusicProcessResult] # 音乐处理结果列表
    raw_audio_contexts: List[Dict[str, Any]] # 原始音频上下文
    timestamp: float                        # 批次时间戳
    processed: bool = False                 # 是否已被动态中枢处理

class AudioAccumulationManager:
    """音频累积管理器"""
    
    def __init__(self, cache_dir: str = None):
        self.logger = logging.getLogger(__name__)
        if not cache_dir:
            base_cache = cfg.cache_root or "cache_data"
            cache_dir = str(Path(base_cache) / "audio_accumulation")
        
        # 累积配置 - 🔧 修复阈值匹配问题
        self.batch_size = 3          # 3次分析一批（匹配音频收集器）
        self.max_batches = 4         # 最多保存4批 (4*3=12次)
        self.hub_trigger_count = 1   # 1批后触发动态中枢抽取 (1*3=3次音频)
        
        # 存储
        self.current_contexts: List[Dict[str, Any]] = []  # 当前累积的音频上下文
        self.accumulated_batches: List[AccumulationBatch] = []  # 累积的批次
        self.music_queue: List[Dict[str, Any]] = []  # 音乐识别队列
        
        # 缓存管理
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "accumulation_state.pkl"
        
        # 组件
        self.audio_analyzer = get_audio_humanized_analyzer()
        self.music_processor = get_music_humanized_processor()
        
        # 线程锁
        self.lock = threading.Lock()
        
        # 加载缓存状态
        self._load_cache_state()
        
        self.logger.info(f"✅ 音频累积管理器初始化完成 - 批次大小: {self.batch_size}, 最大批次: {self.max_batches}")
    
    def add_audio_context(self, audio_context: Dict[str, Any]) -> Optional[str]:
        """
        添加音频上下文
        要求：audio_context 内含 'voiceprint.identity'（owner/stranger, user_id, username）
        """
        with self.lock:
            try:
                # 轻量校验并打印身份摘要，方便追溯
                try:
                    identity = audio_context.get('voiceprint', {}).get('identity', {}) if isinstance(audio_context, dict) else {}
                    label = identity.get('label'); uid = identity.get('user_id'); uname = identity.get('username')
                    if label and uid is not None:
                        self.logger.info(f"🧭 [累积管理器] 身份={label}, user_id={uid}, username={uname}")
                except Exception:
                    pass

                self.current_contexts.append(audio_context)
                self.logger.info(f"✅ [累积管理器] 音频上下文已添加: {len(self.current_contexts)}/{self.batch_size}")

                # 检查是否达到批次大小
                if len(self.current_contexts) >= self.batch_size:
                    batch_id = self._process_batch()
                    self._save_cache_state()
                    return batch_id

                return None

            except Exception as e:
                self.logger.error(f"❌ 添加音频上下文失败: {e}")
                return None
    
    def add_music_recognition(self, acrcloud_result: Dict[str, Any], audio_context: Dict[str, Any] = None) -> None:
        """
        添加音乐识别结果
        
        Args:
            acrcloud_result: ACRCloud识别结果
            audio_context: 相关的音频上下文
        """
        with self.lock:
            try:
                music_data = {
                    'acrcloud_result': acrcloud_result,
                    'audio_context': audio_context,
                    'timestamp': time.time()
                }
                self.music_queue.append(music_data)
                self.logger.info(f"🎵 添加音乐识别结果 - 队列长度: {len(self.music_queue)}")
                
            except Exception as e:
                self.logger.error(f"❌ 添加音乐识别结果失败: {e}")
    
    def _process_separated_batch(self) -> str:
        """处理分离式批次 - 🔥 新的分离处理逻辑"""

        batch_id = f"separated_batch_{int(time.time())}_{len(self.accumulated_batches)}"

        try:
            # 🎯 分离式处理：合并所有类型的数据进行分析
            all_contexts = []

            # 收集所有类型的上下文
            if hasattr(self, 'separated_contexts'):
                for data_type, contexts in self.separated_contexts.items():
                    all_contexts.extend(contexts)
                    self.logger.info(f"📊 收集{data_type}: {len(contexts)}个上下文")

            # 兼容传统格式
            all_contexts.extend(self.current_contexts)

            if not all_contexts:
                self.logger.warning("⚠️ 没有可处理的音频上下文")
                return batch_id

            # 1. 进行音频人性化分析（使用所有可用数据）
            self.logger.info(f"🧠 开始处理分离式批次 {batch_id} - {len(all_contexts)}个音频上下文")
            audio_analysis = self.audio_analyzer.analyze_accumulated_audio(all_contexts)

            # 🔍 调试：检查音频分析结果
            self.logger.info(f"🔍 [调试] 音频分析结果类型: {type(audio_analysis)}")
            if hasattr(audio_analysis, 'situation_description'):
                self.logger.info(f"🔍 [调试] 情况描述: {audio_analysis.situation_description}")
            else:
                self.logger.warning(f"⚠️ [调试] 音频分析结果缺少situation_description属性")

            # 2. 清空已处理的数据
            if hasattr(self, 'separated_contexts'):
                for data_type in self.separated_contexts:
                    processed_count = len(self.separated_contexts[data_type])
                    self.separated_contexts[data_type] = []
                    self.logger.info(f"🗑️ 已清空{data_type}: {processed_count}个上下文")

            self.current_contexts = []

            return self._complete_batch_processing(batch_id, audio_analysis, all_contexts)

        except Exception as e:
            self.logger.error(f"❌ 分离式批次处理失败: {e}")
            return batch_id

    def _process_batch(self) -> str:
        """处理传统批次 - 保持向后兼容"""

        batch_id = f"batch_{int(time.time())}_{len(self.accumulated_batches)}"

        try:
            # 1. 进行音频人性化分析
            self.logger.info(f"🧠 开始处理传统批次 {batch_id} - {len(self.current_contexts)}个音频上下文")
            audio_analysis = self.audio_analyzer.analyze_accumulated_audio(self.current_contexts)

            # 🔍 调试：检查音频分析结果
            self.logger.info(f"🔍 [调试] 音频分析结果类型: {type(audio_analysis)}")
            self.logger.info(f"🔍 [调试] 是否为None: {audio_analysis is None}")
            if hasattr(audio_analysis, 'situation_description'):
                self.logger.info(f"🔍 [调试] 情况描述: {audio_analysis.situation_description}")
            if hasattr(audio_analysis, '__dataclass_fields__'):
                self.logger.info(f"🔍 [调试] 是dataclass: True")
            else:
                self.logger.warning(f"⚠️ [调试] 不是dataclass: {type(audio_analysis)}")

            return self._complete_batch_processing(batch_id, audio_analysis, self.current_contexts)

        except Exception as e:
            self.logger.error(f"❌ 传统批次处理失败: {e}")
            return batch_id

    def _complete_batch_processing(self, batch_id: str, audio_analysis, contexts_list) -> str:
        """完成批次处理的通用逻辑"""

        try:
            # 2. 处理相关的音乐识别结果
            music_results = []
            processed_music_indices = []

            for i, music_data in enumerate(self.music_queue):
                # 检查音乐识别时间是否在当前批次时间范围内
                music_time = music_data['timestamp']
                batch_start_time = min(ctx.get('timestamp', time.time()) for ctx in self.current_contexts)
                batch_end_time = max(ctx.get('timestamp', time.time()) for ctx in self.current_contexts)

                if batch_start_time <= music_time <= batch_end_time + 30:  # 30秒容差
                    music_result = self.music_processor.process_music_recognition(
                        music_data['acrcloud_result'],
                        music_data['audio_context']
                    )
                    music_results.append(music_result)
                    processed_music_indices.append(i)

            # 移除已处理的音乐识别结果
            for i in reversed(processed_music_indices):
                self.music_queue.pop(i)

            # 3. 创建累积批次
            batch = AccumulationBatch(
                batch_id=batch_id,
                audio_analysis=audio_analysis,
                music_results=music_results,
                raw_audio_contexts=self.current_contexts.copy(),
                timestamp=time.time()
            )

            # 4. 添加到累积批次列表
            self.accumulated_batches.append(batch)

            # 5. 清空当前上下文
            self.current_contexts.clear()

            # 6. 检查是否需要清理旧批次
            if len(self.accumulated_batches) > self.max_batches:
                removed_batch = self.accumulated_batches.pop(0)
                self.logger.info(f"🗑️ 清理旧批次: {removed_batch.batch_id}")

            # 7. 检查是否触发动态中枢抽取
            if len(self.accumulated_batches) >= self.hub_trigger_count:
                self._trigger_dynamic_hub_extraction()

            self.logger.info(f"✅ 批次处理完成 {batch_id} - 音频分析置信度: {audio_analysis.confidence:.2f}, 音乐结果: {len(music_results)}个")
            return batch_id

        except Exception as e:
            self.logger.error(f"❌ 批次处理失败: {e}")
            # 清空当前上下文避免数据积压
            self.current_contexts.clear()
            return batch_id
    
    def _trigger_dynamic_hub_extraction(self) -> None:
        """触发动态大模型中枢抽取 - 真正调用动态中枢"""

        try:
            self.logger.info(f"🎯 触发动态大模型中枢抽取 - {len(self.accumulated_batches)}个批次")

            # 标记所有批次为已处理
            for batch in self.accumulated_batches:
                batch.processed = True

            # 🔥 真正调用动态大模型中枢 - 同时抽取音频+记忆+RAG
            from sisi_brain.dynamic_context_hub import get_dynamic_context_hub

            hub = get_dynamic_context_hub()

            # 准备音频批次数据 (已经过专门模型处理)
            audio_batches = []
            for batch in self.accumulated_batches:
                # 🔧 修复asdict()错误：强制确保数据类型一致性
                try:
                    # 检查audio_analysis是否为AudioAnalysisResult类型
                    from sisi_brain.audio_humanized_analyzer import AudioAnalysisResult

                    if isinstance(batch.audio_analysis, AudioAnalysisResult):
                        audio_analysis_dict = asdict(batch.audio_analysis)
                        self.logger.info(f"✅ 批次{len(audio_batches)+1}: AudioAnalysisResult正确转换")
                    elif hasattr(batch.audio_analysis, '__dataclass_fields__'):
                        audio_analysis_dict = asdict(batch.audio_analysis)
                        self.logger.info(f"✅ 批次{len(audio_batches)+1}: dataclass正确转换")
                    elif isinstance(batch.audio_analysis, dict):
                        # 如果已经是字典，直接使用
                        audio_analysis_dict = batch.audio_analysis
                        self.logger.warning(f"⚠️ 批次{len(audio_batches)+1}: audio_analysis已是dict类型")
                    else:
                        # 尝试转换为字典
                        audio_analysis_dict = batch.audio_analysis.__dict__ if hasattr(batch.audio_analysis, '__dict__') else {}
                        self.logger.error(f"❌ 批次{len(audio_batches)+1}: audio_analysis类型异常: {type(batch.audio_analysis)}")

                    # 确保必要字段存在，避免N/A值
                    required_fields = ['situation_description', 'location_guess', 'sound_analysis', 'people_analysis', 'music_analysis', 'confidence']
                    for field in required_fields:
                        if field not in audio_analysis_dict or audio_analysis_dict[field] is None:
                            if field == 'confidence':
                                audio_analysis_dict[field] = 0.5
                            elif field in ['sound_analysis']:
                                audio_analysis_dict[field] = []
                            else:
                                audio_analysis_dict[field] = f"批次{len(audio_batches)+1}数据收集中"

                    music_results_list = []
                    for music in batch.music_results:
                        if hasattr(music, '__dataclass_fields__'):
                            music_results_list.append(asdict(music))
                        else:
                            music_results_list.append(music.__dict__ if hasattr(music, '__dict__') else {})

                    batch_data = {
                        'audio_analysis': audio_analysis_dict,
                        'music_results': music_results_list,
                        'raw_audio_contexts': batch.raw_audio_contexts,
                        'timestamp': batch.timestamp
                    }
                    audio_batches.append(batch_data)

                except Exception as e:
                    self.logger.error(f"❌ 批次数据转换失败: {e}")
                    self.logger.error(f"❌ audio_analysis类型: {type(batch.audio_analysis)}")
                    self.logger.error(f"❌ audio_analysis内容: {batch.audio_analysis}")

                    # 🎯 使用真实数据的回退策略，而不是空数据
                    if hasattr(batch.audio_analysis, 'situation_description'):
                        # 如果有属性但转换失败，手动构建字典
                        audio_analysis_dict = {
                            'situation_description': getattr(batch.audio_analysis, 'situation_description', '数据转换失败'),
                            'location_guess': getattr(batch.audio_analysis, 'location_guess', '未知位置'),
                            'sound_analysis': getattr(batch.audio_analysis, 'sound_analysis', ['音频处理异常']),
                            'people_analysis': getattr(batch.audio_analysis, 'people_analysis', '人员分析失败'),
                            'music_analysis': getattr(batch.audio_analysis, 'music_analysis', '音乐分析失败'),
                            'confidence': getattr(batch.audio_analysis, 'confidence', 0.1),
                            'timestamp': getattr(batch.audio_analysis, 'timestamp', time.time())
                        }
                    else:
                        # 完全失败时的最小数据
                        audio_analysis_dict = {
                            'situation_description': f'批次数据转换异常: {str(e)}',
                            'location_guess': '数据处理失败',
                            'sound_analysis': ['系统异常'],
                            'people_analysis': '无法分析',
                            'music_analysis': '无法分析',
                            'confidence': 0.05,
                            'timestamp': time.time()
                        }

                    batch_data = {
                        'audio_analysis': audio_analysis_dict,
                        'music_results': [],
                        'raw_audio_contexts': batch.raw_audio_contexts,
                        'timestamp': batch.timestamp
                    }
                    audio_batches.append(batch_data)

            # 🧠 通过信息管道抽取记忆库和RAG数据 (避免重复代码)
            memory_data, rag_data = self._extract_memory_and_rag_via_pipeline()

            # 🔥 关键修复：传递完整的音频人性化分析结果给动态中枢
            self.logger.info(f"🔥 [关键传递] 开始传递音频人性化分析结果给动态中枢")
            self.logger.info(f"🔥 [关键传递] 音频批次数量: {len(audio_batches)}")

            # 🔍 详细检查每个批次的数据完整性
            valid_batches = []
            for i, batch in enumerate(audio_batches):
                audio_analysis = batch.get('audio_analysis', {})
                situation_desc = audio_analysis.get('situation_description', '')

                if situation_desc and situation_desc != '数据收集中':
                    self.logger.info(f"✅ [关键传递] 批次{i+1}: 有效数据 - {situation_desc[:50]}...")
                    valid_batches.append(batch)
                else:
                    self.logger.warning(f"⚠️ [关键传递] 批次{i+1}: 数据不完整 - {situation_desc}")
                    # 为不完整的批次补充基础数据
                    if not situation_desc:
                        audio_analysis['situation_description'] = f"批次{i+1}音频数据处理中"
                        audio_analysis['location_guess'] = "数据收集环境"
                        audio_analysis['confidence'] = 0.3
                    valid_batches.append(batch)

                self.logger.info(f"🔥 [关键传递] 批次{i+1}: 音频分析字段数={len(audio_analysis)}, 音乐结果={len(batch['music_results'])}个")

            # 使用验证后的批次数据
            audio_batches = valid_batches

            # 调用动态中枢生成上下文 - 综合分析三个数据源
            dynamic_context = hub.extract_and_generate_context(
                audio_batches=audio_batches,
                memory_data=memory_data,  # 真正的记忆数据
                rag_data=rag_data,       # 真正的RAG数据
                current_user_input=""    # 🔧 修复：添加current_user_input参数避免environment变量未定义错误
            )

            self.logger.info(f"🔥 [关键传递] 动态中枢接收完成，生成上下文置信度: {dynamic_context.confidence:.2f}")

            self.logger.info(f"✅ 动态中枢抽取完成 - 置信度: {dynamic_context.confidence:.2f}")
            self.logger.info(f"📝 音频摘要: {dynamic_context.audio_summary[:100]}...")
            self.logger.info(f"💭 交互建议: {dynamic_context.interaction_suggestions[:100]}...")

            # 保存抽取结果到文件（可选）
            extraction_file = self.cache_dir / f"hub_extraction_{int(time.time())}.json"
            with open(extraction_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'dynamic_context': asdict(dynamic_context),
                    'extraction_time': time.time(),
                    'total_audio_contexts': sum(len(batch.raw_audio_contexts) for batch in self.accumulated_batches),
                    'total_music_results': sum(len(batch.music_results) for batch in self.accumulated_batches)
                }, f, ensure_ascii=False, indent=2, default=str)

            self.logger.info(f"📤 动态中枢抽取结果已保存: {extraction_file}")

            # 🔧 修复：不立即清空，保留数据供前脑系统使用
            # 只标记为已处理，但保留数据
            self.logger.info(f"✅ 动态中枢抽取完成，保留{len(self.accumulated_batches)}个批次供前脑系统使用")

        except Exception as e:
            self.logger.error(f"❌ 动态中枢抽取失败: {e}")
            # 🔧 修复：失败时也保留数据，供前脑系统使用
            self.logger.info(f"⚠️ 抽取失败，但保留{len(self.accumulated_batches)}个批次供前脑系统使用")

    def _extract_memory_and_rag_via_pipeline(self) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """通过信息管道抽取记忆和RAG数据 - 避免重复代码"""
        try:
            # 导入信息管道
            from sisi_brain.sisi_info_pipeline import get_sisi_pipeline

            pipeline = get_sisi_pipeline()

            # 从累积的音频上下文中提取查询信息
            all_speakers = set()
            all_texts = []

            for batch in self.accumulated_batches:
                for context in batch.raw_audio_contexts:
                    # 统一从 voiceprint.identity 取 user_id
                    vid = (context.get('voiceprint', {}) or {}).get('identity', {}) if isinstance(context, dict) else {}
                    speaker_id = (vid or {}).get('user_id', 'unknown')
                    text = context.get('text', '')
                    if speaker_id != 'unknown':
                        all_speakers.add(speaker_id)
                    if text:
                        all_texts.append(text)

            # 构建综合查询
            query = " ".join(all_texts[:5]) if all_texts else "音频环境分析"
            main_speaker = list(all_speakers)[0] if all_speakers else "unknown"

            # 🔥 使用信息管道收集记忆和RAG信息 (避免重复代码)
            import asyncio

            # 异步收集记忆和RAG信息
            try:
                loop = asyncio.get_running_loop()
                memory_task = loop.create_task(pipeline.collector.collect_memory_info(query, main_speaker))
                rag_task = loop.create_task(pipeline.collector.collect_rag_info(query, main_speaker))

                memory_data = loop.run_until_complete(memory_task)
                rag_data = loop.run_until_complete(rag_task)
            except RuntimeError:
                # 如果没有运行的事件循环，创建新的
                memory_data = asyncio.run(pipeline.collector.collect_memory_info(query, main_speaker))
                rag_data = asyncio.run(pipeline.collector.collect_rag_info(query, main_speaker))

            self.logger.info(f"🧠📚 通过信息管道抽取完成: 记忆系统={memory_data.get('memory_system', 'unknown')}, RAG系统={rag_data.get('rag_system', 'unknown')}")

            return memory_data, rag_data

        except Exception as e:
            self.logger.error(f"❌ 通过信息管道抽取失败: {e}")

            # 返回空数据
            empty_memory = {
                'relevant_memories': [],
                'memory_context': '记忆系统暂时不可用',
                'available': False,
                'error': str(e)
            }

            empty_rag = {
                'relevant_documents': [],
                'context_score': 0.0,
                'retrieved_knowledge': 'RAG系统暂时不可用',
                'available': False,
                'error': str(e)
            }

            return empty_memory, empty_rag
    
    def _save_cache_state(self) -> None:
        """保存缓存状态"""
        try:
            state_data = {
                'current_contexts': self.current_contexts,
                'accumulated_batches': [asdict(batch) for batch in self.accumulated_batches],
                'music_queue': self.music_queue,
                'timestamp': time.time()
            }
            
            with open(self.cache_file, 'wb') as f:
                pickle.dump(state_data, f)
                
        except Exception as e:
            self.logger.error(f"❌ 保存缓存状态失败: {e}")
    
    def _load_cache_state(self) -> None:
        """加载缓存状态"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'rb') as f:
                    state_data = pickle.load(f)
                
                self.current_contexts = state_data.get('current_contexts', [])
                self.music_queue = state_data.get('music_queue', [])
                
                # 重建累积批次对象
                batch_dicts = state_data.get('accumulated_batches', [])
                self.accumulated_batches = []
                for batch_dict in batch_dicts:
                    # 重建对象
                    batch = AccumulationBatch(**batch_dict)
                    self.accumulated_batches.append(batch)
                
                self.logger.info(f"📂 加载缓存状态成功 - 当前上下文: {len(self.current_contexts)}, 累积批次: {len(self.accumulated_batches)}")
                
        except Exception as e:
            self.logger.error(f"❌ 加载缓存状态失败: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        with self.lock:
            return {
                'current_contexts_count': len(self.current_contexts),
                'accumulated_batches_count': len(self.accumulated_batches),
                'music_queue_count': len(self.music_queue),
                'next_batch_progress': f"{len(self.current_contexts)}/{self.batch_size}",
                'hub_trigger_progress': f"{len(self.accumulated_batches)}/{self.hub_trigger_count}",
                'cache_dir': str(self.cache_dir)
            }
    
    def clear_cache(self) -> None:
        """清空所有缓存"""
        with self.lock:
            self.current_contexts.clear()
            self.accumulated_batches.clear()
            self.music_queue.clear()
            
            # 删除缓存文件
            if self.cache_file.exists():
                self.cache_file.unlink()
            
            self.logger.info("🗑️ 已清空所有音频累积缓存")

# 全局实例
_audio_accumulation_manager = None

def get_audio_accumulation_manager() -> AudioAccumulationManager:
    """获取音频累积管理器实例"""
    global _audio_accumulation_manager
    if _audio_accumulation_manager is None:
        _audio_accumulation_manager = AudioAccumulationManager()
    return _audio_accumulation_manager

if __name__ == "__main__":
    # 测试代码
    manager = get_audio_accumulation_manager()
    
    # 模拟添加音频上下文
    for i in range(12):  # 测试12个上下文 (会产生2个批次)
        test_context = {
            'audio_type': 'music' if i % 3 == 0 else 'speech',
            'confidence': 0.8,
            'features': {'test': f'feature_{i}'},
            'timestamp': time.time() + i
        }
        
        batch_id = manager.add_audio_context(test_context)
        if batch_id:
            print(f"✅ 触发批次处理: {batch_id}")
        
        time.sleep(0.1)
    
    # 查看状态
    status = manager.get_status()
    print(f"📊 管理器状态: {json.dumps(status, indent=2, ensure_ascii=False)}")
