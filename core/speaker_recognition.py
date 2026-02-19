#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 SISI声纹识别系统 - 唯一实现

核心功能：
- SISISpeakerRecognition：基于3D-Speaker的声纹识别引擎  
- SpeakerManager：兼容接口
- 工厂函数：get_sisi_speaker_recognition() / get_speaker_manager()

使用说明：
- 这是声纹系统的唯一实现文件
- 所有声纹相关功能都通过这个模块访问
- 支持声纹注册、识别、用户档案管理
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# 🔧 在导入torchaudio之前设置FFmpeg路径
def _setup_ffmpeg():
    """设置FFmpeg路径，解决torchcodec找不到DLL的问题"""
    ffmpeg_paths = [
        # BtbN FFmpeg 7.1 GPL Shared (带DLL，兼容torchcodec 0.9.1)
        r"C:\Users\senlin\AppData\Local\Microsoft\WinGet\Packages\BtbN.FFmpeg.GPL.Shared.7.1_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-n7.1.3-22-g40b336e650-win64-gpl-shared-7.1\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\ffmpeg\bin",
    ]
    for ffmpeg_bin in ffmpeg_paths:
        if os.path.exists(ffmpeg_bin):
            current_path = os.environ.get('PATH', '')
            if ffmpeg_bin not in current_path:
                os.environ['PATH'] = ffmpeg_bin + ';' + current_path
            os.environ['FFMPEG_BINARY'] = os.path.join(ffmpeg_bin, "ffmpeg.exe")
            print(f"[SISI声纹] ✅ FFmpeg路径已配置: {ffmpeg_bin}")
            return True
    print("[SISI声纹] ⚠️ 未找到FFmpeg，torchaudio可能无法正常工作")
    return False

_setup_ffmpeg()

import numpy as np
import torch
import torchaudio


from utils import config_util as cfg

class SISISpeakerRecognition:
    """SISI 声纹识别（3D‑Speaker）"""

    def __init__(self):
        self.feature_extractor = None
        self.model = None
        self.speaker_profiles: Dict[str, Dict[str, Any]] = {}
        # 统一根目录，避免不同工作目录导致的相对路径问题（SSOT）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.dirname(current_dir)
        cache_root = cfg.cache_root or os.path.join(self.root_dir, "cache_data")
        self.cache_dir = os.path.join(cache_root, "speaker_profiles")

        # 阈值（余弦相似度）
        self.similarity_threshold = 0.45  # 调整为适合用户的阈值
        self.confidence_threshold = 0.7

        os.makedirs(self.cache_dir, exist_ok=True)
        print(f"[SISI声纹] 📁 声纹档案目录: {self.cache_dir}")
        self._set_random_seeds()
        self._initialize_system()
        self._load_speaker_profiles()

    def _set_random_seeds(self):
        import random
        random.seed(42)
        np.random.seed(42)
        torch.manual_seed(42)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(42)

    def _initialize_system(self) -> bool:
        """初始化 3D‑Speaker 模型与特征前端"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            smartsisi_root = os.path.dirname(current_dir)  # SmartSisi 目录
            speaker_3d_path = os.path.join(smartsisi_root, 'asr', '3D-Speaker')
            
            print(f"[SISI声纹] 🔍 检查3D-Speaker路径: {speaker_3d_path}")
            if not os.path.exists(speaker_3d_path):
                print(f"[SISI声纹] ❌ 3D-Speaker目录不存在: {speaker_3d_path}")
                return False
                
            if speaker_3d_path not in sys.path:
                sys.path.insert(0, speaker_3d_path)
            speakerlab_path = os.path.join(speaker_3d_path, 'speakerlab')
            if speakerlab_path not in sys.path:
                sys.path.append(speakerlab_path)

            print(f"[SISI声纹] 🔍 导入speakerlab模块...")
            from speakerlab.process.processor import FBank
            from speakerlab.models.campplus.DTDNN import CAMPPlus

            # mean_nor=False（与原实现保持一致，避免跨文件差异）
            self.feature_extractor = FBank(n_mels=80, sample_rate=16000, mean_nor=False)
            self.model = CAMPPlus(feat_dim=80, embedding_size=192)

            pretrained_path = os.path.join(speaker_3d_path, "pretrained_models/campplus_cn_common.bin")
            print(f"[SISI声纹] 🔍 检查预训练模型: {pretrained_path}")
            
            if os.path.exists(pretrained_path):
                checkpoint = torch.load(pretrained_path, map_location='cpu')
                self.model.load_state_dict(checkpoint, strict=False)
                self.model.eval()
                print(f"[SISI声纹] ✅ 模型加载成功")
                return True
            else:
                print(f"[SISI声纹] ❌ 预训练模型不存在: {pretrained_path}")
                print(f"[SISI声纹] 💡 请确保已下载campplus_cn_common.bin到pretrained_models目录")
                return False
        except Exception as e:
            print(f"[SISI声纹] ❌ 系统初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _load_speaker_profiles(self):
        """加载说话人档案"""
        try:
            profiles_file = os.path.join(self.cache_dir, "speaker_profiles.json")
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    self.speaker_profiles = json.load(f)
                print(f"[SISI声纹] ✅ 加载 {len(self.speaker_profiles)} 个用户档案")
        except Exception as e:
            print(f"[SISI声纹] ⚠️ 档案加载失败: {e}")
            self.speaker_profiles = {}

    def _save_speaker_profiles(self) -> bool:
        """保存说话人档案"""
        try:
            profiles_file = os.path.join(self.cache_dir, "speaker_profiles.json")
            with open(profiles_file, 'w', encoding='utf-8') as f:
                json.dump(self.speaker_profiles, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[SISI声纹] ❌ 档案保存失败: {e}")
            return False

    def _extract_embedding(self, audio_file: str) -> Optional[np.ndarray]:
        """提取音频特征向量 - 使用soundfile避开torchcodec问题"""
        try:
            if not self.model or not self.feature_extractor:
                print(f"[SISI声纹] ❌ 模型未初始化")
                return None

            # 🔥 使用soundfile加载音频，避开torchcodec
            import soundfile as sf
            audio_data, sample_rate = sf.read(audio_file)
            
            # 转单声道
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)
            
            # 转为torch tensor
            waveform = torch.from_numpy(audio_data).float().unsqueeze(0)
            
            # 重采样到16kHz
            if sample_rate != 16000:
                resampler = torchaudio.transforms.Resample(sample_rate, 16000)
                waveform = resampler(waveform)

            # FBank 期望 torch.Tensor；不转换为 numpy
            features = self.feature_extractor(waveform)
            # FBank 输出 [T, N] (torch.Tensor)，模型期望 [B, T, N]
            features = features.unsqueeze(0)

            with torch.no_grad():
                embedding = self.model(features)
                return embedding.squeeze().numpy()

        except Exception as e:
            print(f"[SISI声纹] ❌ 特征提取失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def register_speaker(self, audio_file: str, username: str, real_name: str, role: str = "user") -> bool:
        try:
            embedding = self._extract_embedding(audio_file)
            if embedding is None:
                return False
            embedding = embedding / np.linalg.norm(embedding)

            speaker_id = f"speaker_{int(time.time() * 1000)}"
            np.save(os.path.join(self.cache_dir, f"{speaker_id}_embedding.npy"), embedding)

            self.speaker_profiles[speaker_id] = {
                "speaker_id": speaker_id,
                "username": username,
                "real_name": real_name,
                "role": role,
                "confidence": 1.0,
                "encounter_count": 1,
                "last_seen": time.time(),
                "familiarity_score": 1.0,
                "is_registered": True,
                "registration_time": datetime.now().isoformat(),
                "audio_file": audio_file,
            }
            return self._save_speaker_profiles()
        except Exception as e:
            print(f"[SISI声纹] ❌ 注册失败: {e}")
            return False

    def identify_speaker(self, audio_file: str) -> Dict[str, Any]:
        """识别说话人"""
        try:
            # 🔍 诊断：检查音频文件
            if not audio_file or audio_file == "None":
                print(f"[SISI声纹] ❌ 音频文件路径无效: {audio_file}")
                return {
                    "speaker_id": "unknown",
                    "confidence": 0.0,
                    "is_registered": False,
                    "error": "invalid_audio_path"
                }
                
            if not os.path.exists(audio_file):
                print(f"[SISI声纹] ❌ 音频文件不存在: {audio_file}")
                return {
                    "speaker_id": "unknown", 
                    "confidence": 0.0,
                    "is_registered": False,
                    "error": "file_not_found"
                }
            
            if not self.speaker_profiles:
                print(f"[SISI声纹] ⚠️ 无已注册用户档案")
                return {
                    "speaker_id": "unknown",
                    "confidence": 0.0,
                    "is_registered": False,
                    "encounter_count": 0,
                    "username": None,
                    "real_name": None,
                    "role": "guest",
                }

            test_embedding = self._extract_embedding(audio_file)
            if test_embedding is None:
                print(f"[SISI声纹] ❌ 特征提取失败: {audio_file}")
                return {"speaker_id": "unknown", "confidence": 0.0, "error": "feature_extraction_failed"}
            test_embedding = test_embedding / np.linalg.norm(test_embedding)

            best_match = None
            best_similarity = 0.0

            for speaker_id, profile in self.speaker_profiles.items():
                embedding_file = os.path.join(self.cache_dir, f"{speaker_id}_embedding.npy")
                if os.path.exists(embedding_file):
                    stored_embedding = np.load(embedding_file)
                    similarity = np.dot(test_embedding, stored_embedding)
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = profile

            if best_match and best_similarity >= self.similarity_threshold:
                # 更新遇见次数
                best_match["encounter_count"] = best_match.get("encounter_count", 0) + 1
                best_match["last_seen"] = time.time()
                best_match["confidence"] = float(best_similarity)
                self._save_speaker_profiles()
                
                return best_match
            else:
                return {
                    "speaker_id": "unknown",
                    "confidence": float(best_similarity),
                    "is_registered": False,
                    "encounter_count": 0,
                    "username": None,
                    "real_name": None,
                    "role": "guest",
                }

        except Exception as e:
            print(f"[SISI声纹] ❌ 识别失败: {e}")
            return {"speaker_id": "unknown", "confidence": 0.0, "error": str(e)}


# 兼容层：旧接口 SpeakerManager
class SpeakerManager:
    """兼容旧系统的声纹管理器接口"""

    def __init__(self):
        self.recognizer = get_sisi_speaker_recognition()

    def identify_speaker(self, audio_file):
        result = self.recognizer.identify_speaker(audio_file)
        if result.get('is_registered', False):
            return result['speaker_id'], result['confidence']
        else:
            return None, result.get('confidence', 0.0)

    def register_speaker(self, speaker_id, username, real_name, role="user"):
        # 兼容旧签名：忽略传入的 speaker_id，需音频另行提供
        print(f"[SpeakerManager] 兼容接口调用: 注册 {real_name}")
        return True

    def get_speaker_info(self, speaker_id):
        for profile in self.recognizer.speaker_profiles.values():
            if profile['speaker_id'] == speaker_id:
                return profile
        return None


# 工厂函数（SSOT）
_sisi_speaker_recognition: Optional[SISISpeakerRecognition] = None
_speaker_manager: Optional[SpeakerManager] = None


def get_sisi_speaker_recognition() -> SISISpeakerRecognition:
    global _sisi_speaker_recognition
    if _sisi_speaker_recognition is None:
        _sisi_speaker_recognition = SISISpeakerRecognition()
    return _sisi_speaker_recognition


def get_speaker_manager() -> SpeakerManager:
    global _speaker_manager
    if _speaker_manager is None:
        _speaker_manager = SpeakerManager()
    return _speaker_manager


# 可选：初始化默认用户（与原实现保持同名，供外部使用）
def initialize_user_profile() -> bool:
    try:
        recognizer = get_sisi_speaker_recognition()
        # 如果已存在"碧潭飘雪"，直接返回
        for profile in recognizer.speaker_profiles.values():
            if profile.get('real_name') == '碧潭飘雪':
                return True
        # 依次尝试两个音频
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_root = cfg.cache_root or os.path.join(root_dir, "cache_data")
        for audio_file in [
            os.path.join(cache_root, "high_quality_voice.wav"),
        ]:
            if os.path.exists(audio_file):
                ok = recognizer.register_speaker(audio_file, "user1", "碧潭飘雪", "user")
                if ok:
                    return True
        return False
    except Exception as e:
        print(f"[SISI声纹] ❌ 初始化用户档案失败: {e}")
        return False


if __name__ == "__main__":
    # 测试代码
    print("🧪 SISI声纹识别系统测试")
    recognizer = get_sisi_speaker_recognition()
    
    # 初始化用户档案
    initialize_user_profile()
    
    # 测试识别
    cache_root = cfg.cache_root or "cache_data"
    test_files = [
        os.path.join(cache_root, "high_quality_voice.wav")
    ]
    
    for test_file in test_files:
        if os.path.exists(test_file):
            result = recognizer.identify_speaker(test_file)
            print(f"识别结果: {result}")
