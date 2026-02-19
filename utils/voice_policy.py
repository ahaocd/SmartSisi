#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的TTS音色策略：
- 根据系统模式（liuye/sisi）切换音色
- 同步Core中的Speech实例与流式引擎
"""

from typing import Optional
from utils import util, config_util as cfg

# 记录启动时默认音色，便于从柳叶切回思思
_original_silicon_voice: Optional[str] = None


def _ensure_original_cached():
    global _original_silicon_voice
    if _original_silicon_voice is None:
        _original_silicon_voice = getattr(cfg, "sisi_voice_uri", None) or getattr(cfg, "siliconflow_voice_type", None)


def _sync_core_instance_voice():
    """同步当前音色到 Core.TTS 实例与流式引擎"""
    try:
        from core import sisi_booter
        core = getattr(sisi_booter, "sisi_core", None)
        if core and hasattr(core, "sp") and core.sp:
            try:
                core.sp.voice_type = getattr(cfg, "siliconflow_voice_type", None)
            except Exception:
                pass
            if hasattr(core.sp, "streaming_opus_tts") and core.sp.streaming_opus_tts:
                try:
                    core.sp.streaming_opus_tts.voice_uri = getattr(cfg, "siliconflow_voice_type", None)
                except Exception:
                    pass
            util.log(1, "[VoicePolicy] 已同步Core.TTS实例音色")
    except Exception as e:
        util.log(2, f"[VoicePolicy] 同步Core实例音色失败: {e}")


def apply_voice_for_mode(mode: str):
    """根据模式设置音色：liuye→柳叶音色；其它→思思默认音色"""
    _ensure_original_cached()
    try:
        if mode == "liuye":
            liuye_voice = getattr(cfg, "liuye_voice_uri", None)
            if liuye_voice:
                cfg.siliconflow_voice_type = liuye_voice
                util.log(1, f"[VoicePolicy] 切到柳叶：系统TTS音色→{liuye_voice}")
            else:
                util.log(2, "[VoicePolicy] 柳叶音色未配置，保留当前音色")
        else:
            global _original_silicon_voice
            if getattr(cfg, "sisi_voice_uri", None):
                _original_silicon_voice = cfg.sisi_voice_uri
            if _original_silicon_voice is not None:
                cfg.siliconflow_voice_type = _original_silicon_voice
                cfg.sisi_voice_uri = _original_silicon_voice
                util.log(1, f"[VoicePolicy] 切回思思：系统TTS音色→{_original_silicon_voice}")
        _sync_core_instance_voice()
    except Exception as e:
        util.log(2, f"[VoicePolicy] 应用音色策略失败: {e}")


def restore_default_voice():
    """显式恢复默认音色并同步实例"""
    _ensure_original_cached()
    try:
        global _original_silicon_voice
        if _original_silicon_voice is not None:
            cfg.siliconflow_voice_type = _original_silicon_voice
            util.log(1, f"[VoicePolicy] 恢复默认音色→{_original_silicon_voice}")
        _sync_core_instance_voice()
    except Exception as e:
        util.log(2, f"[VoicePolicy] 恢复默认音色失败: {e}")