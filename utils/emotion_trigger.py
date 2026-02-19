#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情感触发器 - 检测方括号中的英文单词并触发硬件控制脚本
统一处理所有LLM模型的情感触发需求
"""

import re
import requests
import threading
import json
import os
import time
from utils import util

def _load_music_playlist_to_triggers():
    """
    动态加载音乐播放列表到情感触发器映射
    从music_playlist.json读取歌单并生成触发器配置
    🔥 支持别名(aliases)，让大模型可以用不同名字触发同一首歌
    """
    try:
        playlist_path = os.path.join(os.path.dirname(__file__), '..', 'qa', 'music_playlist.json')
        playlist_path = os.path.abspath(playlist_path)

        if not os.path.exists(playlist_path):
            util.log(2, f"[情感触发器] 音乐播放列表文件不存在: {playlist_path}")
            return {}

        with open(playlist_path, 'r', encoding='utf-8') as f:
            playlist_data = json.load(f)

        mymusic = playlist_data.get('mymusic', {})
        music_triggers = {}

        for song_name, song_info in mymusic.items():
            description = song_info.get('description', f'播放{song_name}')
            # 取描述的前20个字符作为简短描述
            short_desc = description[:20] + ('...' if len(description) > 20 else '')
            
            # 🔥 支持自定义audio_file（用于文件名特殊的歌曲）
            audio_file = song_info.get('audio_file', f"{song_name}.wav")
            if not audio_file.startswith('qa/'):
                audio_file = f"qa/mymusic/{audio_file}"

            trigger_config = {
                "type": "music_play",
                "song_name": song_name,
                "audio_file": audio_file,
                "description": f"播放{song_name} - {short_desc}"
            }
            
            # 添加主名称
            music_triggers[song_name] = trigger_config
            
            # 🔥 添加别名支持 - 让大模型可以用不同名字触发同一首歌
            aliases = song_info.get('aliases', [])
            for alias in aliases:
                music_triggers[alias] = trigger_config
                util.log(1, f"[情感触发器] 添加别名: {alias} -> {song_name}")

        util.log(1, f"[情感触发器] 成功加载{len(music_triggers)}首歌曲到触发器映射(含别名)")
        return music_triggers

    except Exception as e:
        util.log(2, f"[情感触发器] 加载音乐播放列表失败: {str(e)}")
        return {}

# 情感单词映射到硬件控制脚本
EMOTION_TRIGGER_MAP = {
    # 眼睛亮30秒 (思考中)
    "THINKING": {
        "url": "http://172.20.10.2/cmd",  # SISIeyes设备
        "method": "POST",
        "data": "led:FF69B4",  # 粉红色LED
        "description": "48号LED粉红色亮30秒 - 表示正在思考"
    },

    # 电机摆动 (不情愿)
    "RELUCTANT": {
        "url": "http://172.20.10.5/api/stepper/swing",  # sisidesk设备
        "method": "GET",
        "data": None,
        "description": "步进电机摆动 - 表示不情愿但还是会回答"
    },

    # 音响系统控制（每次调用自动10秒）
    "AUDIO_ON": {
        "url": "http://172.20.10.5/api/motor/forward",  # sisidesk设备正转10秒
        "method": "GET",
        "data": None,
        "description": "减速电机正转10秒 - 调用音响系统"
    },

    "AUDIO_OFF": {
        "url": "http://172.20.10.5/api/motor/backward",  # sisidesk设备反转10秒
        "method": "GET",
        "data": None,
        "description": "减速电机反转10秒 - 关闭音响系统"
    },

    # 音效触发器 - 直接使用音效名称作为标记
    "南无阿弥陀佛_电音DJ音效": {
        "type": "sound_effect",
        "audio_file": "qa/sound_effects/南无阿弥陀佛 remix音效.wav",
        "description": "播放南无阿弥陀佛电音DJ音效"
    },

    # 大悲咒完整版音乐
    "大悲咒remix": {
        "type": "sound_effect",
        "audio_file": "qa/mymusic/大悲咒remix.wav",
        "description": "播放完整大悲咒电音remix"
    },

    # 音乐控制功能
    "换一首": {
        "type": "music_control",
        "action": "change_music",
        "description": "换一首音乐"
    },

    "随机播放": {
        "type": "music_control",
        "action": "random_music",
        "description": "随机播放音乐"
    },

    "停止音乐": {
        "type": "music_control",
        "action": "stop_music",
        "description": "停止当前音乐"
    },

    # 指定歌曲播放（移除硬编码，改由播放列表动态加载）

    # 动态加载歌单 - 从music_playlist.json自动生成
    **_load_music_playlist_to_triggers(),

    # 系统切换触发器（显式命令优先）
    "切到柳叶": {
        "type": "system_switch",
        "action": "switch_to_liuye",
        "description": "切换到柳叶系统"
    },
    "切到思思": {
        "type": "system_switch",
        "action": "switch_to_sisi",
        "description": "切换回思思系统"
    },
    "让柳叶说话": {
        "type": "system_switch",
        "action": "switch_to_liuye",
        "description": "切换到柳叶系统"
    },
    "让思思说话": {
        "type": "system_switch",
        "action": "switch_to_sisi",
        "description": "切换回思思系统"
    },
    "强制切到柳叶": {
        "type": "system_switch",
        "action": "switch_to_liuye",
        "description": "切换到柳叶系统",
        "force": True
    },
    "强制切到思思": {
        "type": "system_switch",
        "action": "switch_to_sisi",
        "description": "切换回思思系统",
        "force": True
    },
    # ✅ LLM 标记触发（与系统提示一致）
    "柳叶": {
        "type": "system_switch",
        "action": "switch_to_liuye",
        "description": "切换到柳叶系统（标记触发）"
    },
    "妹妹": {
        "type": "system_switch",
        "action": "switch_to_liuye",
        "description": "切换到柳叶系统（标记触发）"
    },
    "思思": {
        "type": "system_switch",
        "action": "switch_to_sisi",
        "description": "切换回思思系统（标记触发）"
    },
    "姐姐": {
        "type": "system_switch",
        "action": "switch_to_sisi",
        "description": "切换回思思系统（标记触发）"
    },

    # LangGraph / 复杂任务触发标记（仅作为上下文信号，不执行硬件动作）
    "执行复杂任务": {
        "type": "lg_trigger",
        "observation": "复杂任务请求",
        "description": "触发LG复杂工具流程"
    },

}

# 🔧 添加全局切换状态跟踪，防止重复切换
_last_switch_time = 0
_switch_cooldown = 3.0  # 3秒冷却时间，防止快速重复切换
_last_tts_skip_time = 0  # 上次设置TTS跳过的时间
_original_silicon_voice = None  # 记录系统默认音色，便于从柳叶切回时恢复

def detect_intelligent_mode_switch(text):
    """
    检测AI回答中的智能模式切换标记

    Args:
        text: AI回答文本

    Returns:
        dict: 包含切换信息的字典
    """
    try:
        from sisi_memory.context_kernel import get_flag

        if not get_flag("intelligent_mode_switch_enabled", False):
            return {"switched": False}
    except Exception:
        return {"switched": False}

    global _last_switch_time
    import time

    current_time = time.time()

    # 防止短时间内重复切换
    if current_time - _last_switch_time < _switch_cooldown:
        util.log(1, f"[智能切换] 切换冷却中，跳过重复切换请求")
        return {"switched": False}

    # 检测切换到柳叶的标记
    if text.startswith("姐姐"):
        from llm.liusisi import set_system_mode, get_current_system_mode
        current_mode = get_current_system_mode()
        if current_mode == "sisi":
            set_system_mode("liuye")
            _last_switch_time = current_time
            util.log(1, f"[智能切换] 检测到'姐姐'标记，切换到柳叶模式")
            return {"switched": True, "mode": "liuye", "trigger": "姐姐"}

    # 检测切换到思思的标记
    if text.startswith("柳思思"):
        from llm.liusisi import set_system_mode, get_current_system_mode
        current_mode = get_current_system_mode()
        if current_mode == "liuye":
            set_system_mode("sisi")
            _last_switch_time = current_time
            util.log(1, f"[智能切换] 检测到'柳思思'标记，切换到思思模式")
            return {"switched": True, "mode": "sisi", "trigger": "柳思思"}

    return {"switched": False}

def extract_emotion_tags(text):
    """
    提取文本中的 {TAG} 标记，并返回清理后的文本（不执行任何触发）

    Returns:
        tuple(list[str], str): (tags, clean_text)
    """
    if not text:
        return [], text
    emotion_pattern = re.compile(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}')
    tags = emotion_pattern.findall(text)
    clean_text = emotion_pattern.sub('', text).strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return tags, clean_text

def detect_and_trigger_emotions(text, is_ai_response=False):
    """
    检测文本中的情感触发词并执行对应的硬件控制

    Args:
        text: 要检测的文本
        is_ai_response: 是否为AI回复（True=AI回复，False=用户输入）

    Returns:
        tuple: (清理后的文本, 检测到的触发词列表)
    """
    if not text:
        return text, []
    
    # 提取所有大括号中的内容（支持中文、英文、下划线、数字）
    emotions, clean_text = extract_emotion_tags(text)
    triggered_emotions = []

    debug = False
    try:
        from sisi_memory.context_kernel import get_flag

        debug = get_flag("debug_emotion_trigger", False)
    except Exception:
        debug = False

    if debug:
        util.log(1, f"[情感触发] 输入文本: {text}")
        util.log(1, f"[情感触发] 检测到的情感标记: {emotions}")
    
    # 检测并触发情感动作
    for emotion in emotions:
        if debug:
            util.log(1, f"[情感触发] 检查情感标记: {emotion}")
        if emotion in EMOTION_TRIGGER_MAP:
            triggered_emotions.append(emotion)
            trigger_config = EMOTION_TRIGGER_MAP[emotion]
            if debug:
                util.log(1, f"[情感触发] 命中触发器: {emotion} -> {trigger_config}")

            # 检查触发类型
            trigger_type = trigger_config.get("type")

            if trigger_type == "sound_effect":
                # 音效类型，添加到音频队列
                threading.Thread(
                    target=_execute_sound_effect,
                    args=(emotion, trigger_config),
                    daemon=True
                ).start()
                util.log(1, f"[情感触发] ✅ 检测到音效触发: {emotion}")
            elif trigger_type == "music_control":
                # 音乐控制，异步执行
                threading.Thread(
                    target=_execute_music_control,
                    args=(emotion, trigger_config),
                    daemon=True
                ).start()
                util.log(1, f"[情感触发] ✅ 检测到音乐控制: {emotion}")
            elif trigger_type == "music_play":
                # 🎵 音乐播放，异步执行
                threading.Thread(
                    target=_execute_music_play,
                    args=(emotion, trigger_config),
                    daemon=True
                ).start()
                util.log(1, f"[情感触发] ✅ 检测到音乐播放标记: {emotion}")
            elif trigger_type == "medical_control":
                # 🏥 医疗包控制，异步执行
                threading.Thread(
                    target=_execute_medical_control,
                    args=(emotion, trigger_config),
                    daemon=True
                ).start()
                util.log(1, f"[情感触发] ✅ 检测到医疗包控制: {emotion}")
            elif trigger_type == "medical_sister":
                # 🩺 医疗包妹妹对话，异步执行
                threading.Thread(
                    target=_execute_medical_sister_call,
                    args=(emotion, trigger_config),
                    daemon=True
                ).start()
                util.log(1, f"[情感触发] ✅ 检测到医疗包妹妹调用: {emotion}")
            elif trigger_type == "system_switch":
                # 🔄 系统切换，异步执行
                threading.Thread(
                    target=_execute_system_switch,
                    args=(emotion, trigger_config),
                    daemon=True
                ).start()
                util.log(1, f"[情感触发] ✅ 检测到系统切换: {emotion}")
            elif trigger_type in ("lg_trigger", "tool_context"):
                # 仅作为工具触发上下文标记，不执行硬件动作
                util.log(1, f"[情感触发] 🧭 工具触发标记: {emotion}")
            else:
                # 普通硬件控制，异步执行
                threading.Thread(
                    target=_execute_emotion_trigger,
                    args=(emotion, trigger_config),
                    daemon=True
                ).start()
                util.log(1, f"[情感触发] ✅ 检测到硬件触发: {emotion}")
        else:
            util.log(2, f"[情感触发-调试] ❌ 未找到匹配的触发器: {emotion}")
    
    # clean_text 已由 extract_emotion_tags 处理
    
    # 🔥 修复：不再在文本后面追加"正在演唱"文字
    # 音乐播放状态改为通过WebSocket事件通知前端显示唱片机动画
    # 这样可以避免文本中出现重复的"正在演唱"，并且唱片机可以在音乐结束后正确隐藏
    music_songs = []
    for emotion in triggered_emotions:
        trigger_config = EMOTION_TRIGGER_MAP.get(emotion, {})
        if trigger_config.get("type") == "music_play":
            song_name = trigger_config.get("song_name", emotion)
            music_songs.append(song_name)
    
    # 🎵 不再追加文本，只记录日志
    if music_songs:
        util.log(1, f"[情感触发] 🎵 检测到音乐播放: {music_songs}，通过WebSocket通知前端")
    
    if triggered_emotions:
        util.log(1, f"[情感触发] 触发的情感: {triggered_emotions}")
        util.log(1, f"[情感触发] 清理后文本: {clean_text}")
    
    return clean_text, triggered_emotions

def _execute_emotion_trigger(emotion, trigger_config):
    """
    执行具体的情感触发动作
    
    Args:
        emotion: 情感词
        trigger_config: 触发配置字典
    """
    try:
        url = trigger_config["url"]
        method = trigger_config["method"]
        data = trigger_config["data"]
        description = trigger_config["description"]
        
        util.log(1, f"[情感触发] 执行 {emotion}: {description}")
        
        if method == "GET":
            response = requests.get(url, timeout=3)
        elif method == "POST":
            if data:
                response = requests.post(url, data=data, timeout=3)
            else:
                response = requests.post(url, timeout=3)
        else:
            util.log(2, f"[情感触发] 不支持的HTTP方法: {method}")
            return
        
        if response.status_code == 200:
            util.log(1, f"[情感触发] ✅ {emotion}: 命令执行成功")
        else:
            util.log(2, f"[情感触发] ❌ {emotion}: HTTP {response.status_code}")
            
    except requests.exceptions.Timeout:
        util.log(1, f"[情感触发] ⏰ {emotion}: 硬件请求超时（正常）")
    except requests.exceptions.ConnectionError:
        util.log(1, f"[情感触发] ℹ️ {emotion}: 硬件未连接（正常）")
    except Exception as e:
        util.log(2, f"[情感触发] ❌ {emotion}: {str(e)}")

def add_emotion_trigger(emotion_word, url, method="GET", data=None, description=""):
    """
    添加新的情感触发器
    
    Args:
        emotion_word: 情感单词 (大写)
        url: 控制URL
        method: HTTP方法 ("GET" 或 "POST")
        data: POST数据 (可选)
        description: 描述信息
    """
    EMOTION_TRIGGER_MAP[emotion_word.upper()] = {
        "url": url,
        "method": method.upper(),
        "data": data,
        "description": description
    }
    util.log(1, f"[情感触发] 添加新触发器: {emotion_word} -> {description}")

def get_supported_emotions():
    """获取所有支持的情感触发词列表"""
    return list(EMOTION_TRIGGER_MAP.keys())

def get_emotion_description(emotion_word):
    """获取情感触发词的描述"""
    emotion = emotion_word.upper()
    if emotion in EMOTION_TRIGGER_MAP:
        return EMOTION_TRIGGER_MAP[emotion]["description"]
    return "未知情感触发词"

def _execute_medical_control(emotion, trigger_config):
    """
    执行医疗包控制操作 - 已废弃，保留兼容性

    Args:
        emotion: 触发的情感词
        trigger_config: 触发器配置
    """
    try:
        action = trigger_config.get("action", "unknown")
        util.log(1, f"[医疗包控制] 操作已废弃: {action}")
        # 医疗包相关功能已整合到柳叶系统中

    except Exception as e:
        util.log(2, f"[医疗包控制] 执行异常: {str(e)}")

def _execute_medical_sister_call(emotion, trigger_config):
    """
    执行医疗包妹妹调用操作 - 已废弃，保留兼容性

    Args:
        emotion: 触发的情感词
        trigger_config: 触发器配置
    """
    try:
        action = trigger_config.get("action", "unknown")
        util.log(1, f"[医疗包妹妹] 操作已废弃: {action}")
        # 妹妹调用功能已整合到柳叶系统切换中

    except Exception as e:
        util.log(2, f"[医疗包妹妹] 执行异常: {str(e)}")

def _execute_system_switch(emotion, trigger_config):
    """
    执行系统切换操作

    Args:
        emotion: 触发的情感词
        trigger_config: 触发器配置
    """
    global _last_switch_time, _last_tts_skip_time
    import time

    try:
        current_time = time.time()

        force = bool(trigger_config.get("force"))
        if (not force) and (current_time - _last_switch_time < _switch_cooldown):
            util.log(1, f"[系统切换] 切换冷却中，跳过重复切换请求 (剩余: {_switch_cooldown - (current_time - _last_switch_time):.1f}秒)")
            return

        action = trigger_config.get("action", "unknown")
        util.log(1, f"[系统切换] 执行操作: {action} (触发词: {emotion})")

        _last_switch_time = current_time

        if action == "switch_to_liuye":
            # 🔥 修复：清空队列中思思的TTS，避免声音重叠
            try:
                from core import sisi_booter
                if hasattr(sisi_booter, 'sisi_core'):
                    sisi_core = sisi_booter.sisi_core
                    # 清空音频队列（思思的TTS）
                    cleared_count = 0
                    while not sisi_core.sound_query.empty():
                        try:
                            sisi_core.sound_query.get_nowait()
                            cleared_count += 1
                        except:
                            break
                    
                    if cleared_count > 0:
                        util.log(1, f"[系统切换] 清空了 {cleared_count} 个思思的TTS，避免重叠")
            except Exception as e:
                util.log(2, f"[系统切换] 清空队列失败: {e}")
            
            # 切换到柳叶系统
            from llm.liusisi import set_system_mode
            set_system_mode("liuye")

            # 根源修复：统一系统TTS音色映射到柳叶音色（不改TTS实现，切换配置与实例）
            try:
                from utils.voice_policy import apply_voice_for_mode
                apply_voice_for_mode('liuye')
            except Exception as e:
                util.log(2, f"[系统切换] 柳叶音色映射失败: {e}")

            # 🚀 启动柳叶监控系统
            try:
                from evoliu.liuye_frontend.intelligent_liuye import get_intelligent_liuye
                liuye_instance = get_intelligent_liuye()
                # 监控系统已移除 - 简化为Flash 2.0交互+TTS+QwenCLI
                util.log(1, f"[系统切换] ✅ 已切换到柳叶系统")
                
                # 🔥 新增：柳叶打招呼（使用高优先级，确保优先播放）
                import random
                greetings = ["我在的~", "到！", "在了在了~", "随时在线哦！", "有何指教呀？", "嘻嘻，我来啦！"]
                greeting = random.choice(greetings)
                
                # 触发柳叶说话（通过Core系统，使用高优先级）
                try:
                    from core import sisi_booter
                    if hasattr(sisi_booter, 'sisi_core'):
                        # 🔥 关键修复：创建柳叶委托的interact对象
                        from core.interact import Interact
                        liuye_interact = Interact(
                            interleaver="liuye",  # 标记为柳叶委托
                            interact_type=2,
                            data={"user": "System", "text": greeting}
                        )
                        
                        # 🔥 关键修复：使用高优先级（priority=7），确保柳叶打招呼优先播放
                        sisi_booter.sisi_core.process_audio_response(
                            text=greeting,
                            username="User",
                            priority=7,  # 高优先级，确保优先播放
                            interact=liuye_interact  # 传入柳叶委托标识
                        )
                        util.log(1, f"[系统切换] 柳叶打招呼（高优先级+委托标识）: {greeting}")
                except Exception as e:
                    util.log(2, f"[系统切换] 柳叶打招呼失败: {e}")
                    
            except Exception as e:
                util.log(2, f"[系统切换] 柳叶系统启动失败: {str(e)}")

        elif action == "switch_to_sisi":
            # set skip marker to avoid duplicate TTS on mode switch
            try:
                from core import sisi_booter
                if hasattr(sisi_booter, "sisi_core"):
                    sisi_booter.sisi_core._skip_next_tts = True
                    import time as _time
                    sisi_booter.sisi_core._skip_tts_timestamp = _time.time()
            except Exception as e:
                util.log(2, "[system_switch] skip marker failed (ignored): %s" % (str(e)))

            # stop liuye monitoring
            try:
                from evoliu.liuye_frontend.intelligent_liuye import get_intelligent_liuye
                liuye_instance = get_intelligent_liuye()
                liuye_instance.stop_monitoring()
                util.log(1, "[system_switch] liuye monitoring stopped")
            except Exception as e:
                util.log(2, "[system_switch] liuye monitoring stop failed: %s" % (str(e)))

            # switch back to sisi
            from llm.liusisi import set_system_mode
            set_system_mode("sisi")
            util.log(1, "[system_switch] switched back to sisi")

            # restore default voice for sisi
            try:
                from utils.voice_policy import apply_voice_for_mode
                apply_voice_for_mode("sisi")
            except Exception as e:
                util.log(2, "[system_switch] restore voice failed: %s" % (str(e)))

        else:
            util.log(2, f"[系统切换] 未知操作: {action}")

    except Exception as e:
        util.log(2, f"[系统切换] 执行异常: {str(e)}")

# 工具函数
def is_liuye_mode_active():
    """检查是否处于柳叶模式"""
    try:
        from llm.liusisi import get_current_system_mode
        return get_current_system_mode() == "liuye"
    except:
        return False

# 提示词模板 - 用于告诉LLM如何使用情感触发词
EMOTION_PROMPT_TEMPLATE = """
情感触发指南：
你可以在对话中使用以下大括号标记来触发硬件动作，这些标记不会被语音读出：

{THINKING} - 当你正在思考时使用，会让眼睛亮起30秒
{RELUCTANT} - 当你不情愿但还是会回答时使用，会让设备摆动表示不情愿
{AUDIO_ON} - 调用音响系统（减速电机正转）
{AUDIO_OFF} - 关闭音响系统（减速电机反转）
{南无阿弥陀佛_电音DJ音效} - 当有人需要洗涤心灵时使用，播放南无阿弥陀佛电音DJ音效

使用示例：
- "好吧{RELUCTANT}，我来帮你查一下这个问题。"
- "让我想想{THINKING}，这个问题比较复杂。"
- "开始播放音乐{AUDIO_ON}。"
- "音乐结束了{AUDIO_OFF}。"

注意：只在语境合适时使用，不要频繁使用。
"""

def should_use_chunked_processing(text):
    """
    检查文本是否包含音效标记，需要使用分块处理

    Args:
        text: 输入文本

    Returns:
        bool: 是否需要分块处理
    """
    if not text:
        return False

    emotion_pattern = re.compile(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}')
    emotions = emotion_pattern.findall(text)

    # 检查是否包含音效标记或音乐播放标记
    for emotion in emotions:
        if emotion in EMOTION_TRIGGER_MAP:
            trigger_config = EMOTION_TRIGGER_MAP[emotion]
            trigger_type = trigger_config.get("type")
            # 音效类型和音乐播放类型都需要分块处理
            if trigger_type in ["sound_effect", "music_play"]:
                util.log(1, f"[情感触发] 检测到{trigger_type}标记，需要分块处理: {emotion}")
                return True

    return False

def _execute_sound_effect(emotion, trigger_config):
    """
    执行音效播放 - 插队到设备通路
    """
    try:
        audio_file = trigger_config.get("audio_file")
        description = trigger_config.get("description", "播放音效")

        if not audio_file:
            util.log(2, f"[音效触发] {emotion}: 未指定音效文件")
            return

        # 构建完整文件路径
        import os
        if not os.path.isabs(audio_file):
            full_audio_path = os.path.abspath(audio_file)
        else:
            full_audio_path = audio_file
        util.log(1, f"[音效触发] 音效文件路径: {full_audio_path}")
        if not os.path.exists(full_audio_path):
            util.log(2, f"[音效触发] ❌ {emotion}: 音效文件不存在 - {full_audio_path}")
            return

        # 新：帧级插入，不打断主流
        try:
            from esp32_liusisi.sisi_audio_output import AudioOutputManager
            from esp32_liusisi.opus_helper import OpusConvertor
            aom = AudioOutputManager.get_instance()
            if not aom:
                util.log(2, f"[音效触发] ⚠️ 设备通路不可用，跳过")
                return
            conv = OpusConvertor(debug=False)
            frames, _dur = conv.audio_to_opus_frames(full_audio_path)
            if frames:
                aom.add_opus_frames(frames, label=f"effect:{emotion}", is_final=False)
                util.log(1, f"[音效触发] ✅ {emotion}: 已帧级插入，帧数={len(frames)}")
            else:
                util.log(2, f"[音效触发] ❌ {emotion}: 转帧失败")
        except Exception as e:
            util.log(2, f"[音效触发] 转帧或入队失败: {str(e)}")
        
        # 旧：暂停/插队/恢复（已弃用）
        # try:
        #     from esp32_liusisi.sisi_audio_output import AudioOutputManager
        #     aom = AudioOutputManager.get_instance()
        #     if aom:
        #         aom.pause_streaming()
        #         aom.add_tts_task("sound_effect", full_audio_path, priority=7)
        #         aom.wait_until_idle(timeout=5.0)
        #         aom.resume_streaming()
        # except Exception:
        #     pass

    except Exception as e:
        util.log(2, f"[音效触发] 执行 {emotion} 失败: {str(e)}")

def _execute_music_control(emotion, trigger_config):
    """
    执行音乐控制功能

    Args:
        emotion: 情感词
        trigger_config: 触发配置字典
    """
    try:
        action = trigger_config.get("action")
        description = trigger_config.get("description", "音乐控制")

        util.log(1, f"[音乐控制] 执行 {emotion}: {description}")

        # 导入音乐控制模块
        from core import sisi_booter

        if action == "change_music":
            # 换一首音乐
            if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'change_music'):
                sisi_booter.sisi_core.change_music()
                util.log(1, f"[音乐控制] ✅ {emotion}: 已切换音乐")
            else:
                util.log(2, f"[音乐控制] ❌ {emotion}: 换歌功能不可用")

        elif action == "random_music":
            # 随机播放
            if hasattr(sisi_booter, 'sisi_core') and hasattr(sisi_booter.sisi_core, 'random_music'):
                sisi_booter.sisi_core.random_music()
                util.log(1, f"[音乐控制] ✅ {emotion}: 已开始随机播放")
            else:
                util.log(2, f"[音乐控制] ❌ {emotion}: 随机播放功能不可用")

        elif action == "stop_music":
            # 停止音乐 - 使用正确的方法名
            if hasattr(sisi_booter, 'sisi_core'):
                # 方法1：直接停止pygame音频
                try:
                    import pygame
                    if pygame.mixer.get_init():
                        pygame.mixer.stop()
                        util.log(1, f"[音乐控制] ✅ {emotion}: 已停止pygame音频")
                except Exception as e:
                    util.log(2, f"[音乐控制] pygame停止失败: {str(e)}")

                # 方法2：清空音频队列
                try:
                    if hasattr(sisi_booter.sisi_core, 'sound_query'):
                        while not sisi_booter.sisi_core.sound_query.empty():
                            sisi_booter.sisi_core.sound_query.get_nowait()
                        util.log(1, f"[音乐控制] ✅ {emotion}: 已清空音频队列")
                except Exception as e:
                    util.log(2, f"[音乐控制] 清空队列失败: {str(e)}")
            else:
                util.log(2, f"[音乐控制] ❌ {emotion}: sisi_booter不可用")
        else:
            util.log(2, f"[音乐控制] ❌ {emotion}: 未知动作 - {action}")

    except Exception as e:
        util.log(2, f"[音乐控制] 执行 {emotion} 失败: {str(e)}")

# 🎵 音乐OPUS帧缓存 - 避免重复转换
_music_opus_cache = {}

# 🔥 磁盘缓存目录
import os as _os
_OPUS_CACHE_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'cache_data', 'music_cache', 'opus_music')

def _get_opus_cache_path(audio_file):
    """获取OPUS缓存文件路径"""
    import hashlib
    # 用文件路径+修改时间生成唯一key
    mtime = _os.path.getmtime(audio_file) if _os.path.exists(audio_file) else 0
    cache_key = hashlib.md5(f"{audio_file}:{mtime}".encode()).hexdigest()
    return _os.path.join(_OPUS_CACHE_DIR, f"{cache_key}.opus_cache")

def _load_opus_from_disk(audio_file):
    """从磁盘加载OPUS缓存"""
    try:
        import pickle
        cache_path = _get_opus_cache_path(audio_file)
        if _os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        util.log(2, f"[OPUS缓存] 读取失败: {e}")
    return None

def _save_opus_to_disk(audio_file, frames):
    """保存OPUS缓存到磁盘"""
    try:
        import pickle
        _os.makedirs(_OPUS_CACHE_DIR, exist_ok=True)
        cache_path = _get_opus_cache_path(audio_file)
        with open(cache_path, 'wb') as f:
            pickle.dump(frames, f)
        util.log(1, f"[OPUS缓存] 💾 已持久化到磁盘: {_os.path.basename(audio_file)}")
    except Exception as e:
        util.log(2, f"[OPUS缓存] 保存失败: {e}")

def _execute_music_play(emotion, trigger_config):
    """
    执行指定音乐播放 - 插队到设备通路或PC本地播放
    🔥 优化：添加OPUS帧缓存，支持磁盘持久化
    """
    global _music_opus_cache
    
    try:
        song_name = trigger_config.get("song_name")
        audio_file = trigger_config.get("audio_file")
        description = trigger_config.get("description", "播放音乐")

        util.log(1, f"[音乐播放] 执行 {emotion}: {description}")

        if not audio_file:
            util.log(2, f"[音乐播放] ❌ {emotion}: 未指定音频文件")
            return

        import os
        if not os.path.isabs(audio_file):
            audio_file = os.path.abspath(audio_file)
        if not os.path.exists(audio_file):
            util.log(2, f"[音乐播放] ❌ {emotion}: 音乐文件不存在 - {audio_file}")
            return

        def _send_music_event(ev, file_path=None, title=None):
            try:
                from core import wsa_server
                web_instance = wsa_server.get_web_instance()
                if not web_instance:
                    return
                payload = {"music_event": ev}
                if file_path:
                    payload["music_file"] = file_path
                if title:
                    payload["music_title"] = title
                web_instance.add_cmd(payload)
            except Exception:
                pass

        # 🔥 检查是否有ESP32设备连接（使用和TTS相同的检测逻辑）
        has_esp32_device = False
        try:
            # 方法1：通过esp32_bridge模块获取adapter
            try:
                from esp32_liusisi import sisi_adapter as esp32_bridge
                adapter = getattr(esp32_bridge, 'adapter_instance', None)
                if adapter and hasattr(adapter, 'clients') and adapter.clients:
                    # 检查是否有活跃的设备连接
                    for client_id in adapter.clients:
                        websocket = adapter.clients.get(client_id)
                        if websocket and not getattr(websocket, 'closed', False):
                            has_esp32_device = True
                            util.log(1, f"[音乐播放] 检测到ESP32设备连接，使用设备播放模式")
                            break
            except Exception:
                pass
            
            # 方法2：通过sisi_adapter模块直接获取
            if not has_esp32_device:
                try:
                    from esp32_liusisi import sisi_adapter
                    adapter = sisi_adapter.get_adapter_instance()
                    if adapter and hasattr(adapter, 'clients') and adapter.clients:
                        has_esp32_device = True
                        util.log(1, f"[音乐播放] 检测到ESP32设备连接（方法2），使用设备播放模式")
                except Exception:
                    pass
        except Exception as e:
            util.log(2, f"[音乐播放] ESP32设备检测失败: {e}")
        
        # 尝试通过ESP32设备播放（仅当有设备连接时）
        if has_esp32_device:
            try:
                from esp32_liusisi.sisi_audio_output import AudioOutputManager
                from esp32_liusisi.opus_helper import OpusConvertor
                aom = AudioOutputManager.get_instance()
                if aom:
                    frames = None
                    cache_key = audio_file
                    
                    # 🔥 优先级：内存缓存 > 磁盘缓存 > 实时转换
                    if cache_key in _music_opus_cache:
                        frames = _music_opus_cache[cache_key]
                        util.log(1, f"[音乐播放] ⚡ 使用内存缓存: {song_name}, 帧数={len(frames)}")
                    else:
                        # 尝试从磁盘加载
                        disk_frames = _load_opus_from_disk(audio_file)
                        if disk_frames:
                            frames = disk_frames
                            _music_opus_cache[cache_key] = frames
                            util.log(1, f"[音乐播放] ⚡ 从磁盘加载: {song_name}, 帧数={len(frames)}")
                        else:
                            # 实时转换并缓存
                            conv = OpusConvertor(debug=False)
                            frames, _dur = conv.audio_to_opus_frames(audio_file)
                            if frames:
                                _music_opus_cache[cache_key] = frames
                                _save_opus_to_disk(audio_file, frames)
                                util.log(1, f"[音乐播放] 💾 已缓存OPUS帧: {song_name}, 帧数={len(frames)}")
                    
                    if frames:
                        # 🔥 关键修复：使用暂停/恢复机制插入音乐
                        util.log(1, f"[音乐播放] 🎵 暂停流式TTS，准备插入音乐: {song_name}")
                        
                        # 1. 暂停流式TTS推进
                        aom.pause_streaming()
                        
                        # 2. 插入音乐OPUS帧
                        _send_music_event("start", audio_file, song_name)
                        aom.add_opus_frames(frames, label=f"music:{song_name}", is_final=False)
                        util.log(1, f"[音乐播放] ✅ {emotion}: 已帧级插入 - {song_name}, 帧数={len(frames)}")
                        
                        # 3. 恢复流式TTS推进
                        aom.resume_streaming()
                        util.log(1, f"[音乐播放] 🎵 恢复流式TTS推进")

                        # 估算持续时间后发送stop
                        try:
                            if _dur:
                                duration = float(_dur)
                            else:
                                duration = len(frames) * 0.02
                            threading.Thread(
                                target=lambda: (time.sleep(max(0.1, duration)), _send_music_event("stop", audio_file, song_name)),
                                daemon=True
                            ).start()
                        except Exception:
                            pass
                        
                        return  # ✅ 设备播放成功，直接返回
                    else:
                        util.log(2, f"[音乐播放] ❌ {emotion}: 转帧失败 - {song_name}")
            except Exception as e:
                util.log(1, f"[音乐播放] ESP32设备播放失败，fallback到PC模式: {str(e)}")
        else:
            util.log(1, f"[音乐播放] 无ESP32设备连接，使用PC播放模式")

        # 🔥 PC模式：使用pygame播放音乐（不弹出外部播放器）
        try:
            util.log(1, f"[音乐播放] 🎵 PC模式播放: {song_name} ({audio_file})")
            
            # 使用pygame播放音频
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            _send_music_event("start", audio_file, song_name)
            util.log(1, f"[音乐播放] ✅ pygame播放启动: {song_name}")

            def _watch_music_stop():
                try:
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.1)
                    _send_music_event("stop", audio_file, song_name)
                except Exception:
                    pass
            threading.Thread(target=_watch_music_stop, daemon=True).start()
            
        except Exception as pc_err:
            util.log(2, f"[音乐播放] pygame播放失败: {str(pc_err)}")
            # Fallback: 使用系统默认播放器
            try:
                import subprocess
                import platform
                system = platform.system()
                
                if system == "Windows":
                    os.startfile(audio_file)
                    _send_music_event("start", audio_file, song_name)
                    util.log(1, f"[音乐播放] ✅ Windows播放器启动: {song_name}")
                elif system == "Darwin":
                    subprocess.Popen(["afplay", audio_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    _send_music_event("start", audio_file, song_name)
                    util.log(1, f"[音乐播放] ✅ macOS播放启动: {song_name}")
                else:
                    for player in ["mpv", "ffplay", "aplay", "paplay"]:
                        try:
                            subprocess.Popen([player, audio_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            _send_music_event("start", audio_file, song_name)
                            util.log(1, f"[音乐播放] ✅ Linux播放启动({player}): {song_name}")
                            break
                        except FileNotFoundError:
                            continue
                try:
                    import wave
                    with wave.open(audio_file, "rb") as wf:
                        duration = wf.getnframes() / float(wf.getframerate())
                    threading.Thread(
                        target=lambda: (time.sleep(max(0.1, duration)), _send_music_event("stop", audio_file, song_name)),
                        daemon=True
                    ).start()
                except Exception:
                    pass
            except Exception as fallback_err:
                util.log(2, f"[音乐播放] Fallback播放失败: {str(fallback_err)}")

    except Exception as e:
        util.log(2, f"[音乐播放] 执行 {emotion} 失败: {str(e)}")


# ============== 音乐预加载功能 ==============

def preload_music_opus_cache(song_names=None, background=True):
    """
    预加载音乐的OPUS帧到缓存，减少首次播放延迟
    
    Args:
        song_names: 要预加载的歌曲名列表，None表示加载所有
        background: 是否在后台线程执行
    
    🔥 优化原理：
    - OPUS转换是CPU密集型操作（50秒音乐约需20秒转换）
    - 预加载后，播放时直接使用缓存，实现秒播
    - 🆕 支持磁盘持久化，重启后无需重新转换
    """
    global _music_opus_cache
    
    def _do_preload():
        try:
            from esp32_liusisi.opus_helper import OpusConvertor
            conv = OpusConvertor(debug=False)
            
            # 获取要预加载的歌曲
            if song_names:
                songs_to_load = song_names
            else:
                # 加载所有音乐触发器
                songs_to_load = [
                    name for name, config in EMOTION_TRIGGER_MAP.items()
                    if config.get("type") == "music_play"
                ]
            
            util.log(1, f"[音乐预加载] 🚀 开始预加载 {len(songs_to_load)} 首歌曲...")
            
            loaded_count = 0
            from_disk_count = 0
            for song_name in songs_to_load:
                if song_name not in EMOTION_TRIGGER_MAP:
                    continue
                    
                config = EMOTION_TRIGGER_MAP[song_name]
                if config.get("type") != "music_play":
                    continue
                
                audio_file = config.get("audio_file", "")
                if not audio_file:
                    continue
                
                # 构建完整路径
                if not os.path.isabs(audio_file):
                    audio_file = os.path.abspath(audio_file)
                
                # 检查是否已在内存缓存
                if audio_file in _music_opus_cache:
                    util.log(1, f"[音乐预加载] ⏭️ 跳过已缓存: {song_name}")
                    continue
                
                # 🆕 尝试从磁盘加载
                disk_frames = _load_opus_from_disk(audio_file)
                if disk_frames:
                    _music_opus_cache[audio_file] = disk_frames
                    loaded_count += 1
                    from_disk_count += 1
                    util.log(1, f"[音乐预加载] ⚡ 从磁盘加载: {song_name} ({len(disk_frames)}帧)")
                    continue
                
                # 检查文件是否存在
                if not os.path.exists(audio_file):
                    util.log(2, f"[音乐预加载] ❌ 文件不存在: {song_name} -> {audio_file}")
                    continue
                
                # 转换并缓存
                util.log(1, f"[音乐预加载] 🔄 正在转换: {song_name}...")
                frames, duration = conv.audio_to_opus_frames(audio_file)
                
                if frames:
                    _music_opus_cache[audio_file] = frames
                    # 🆕 保存到磁盘
                    _save_opus_to_disk(audio_file, frames)
                    loaded_count += 1
                    util.log(1, f"[音乐预加载] ✅ 已缓存: {song_name} ({len(frames)}帧, {duration:.1f}秒)")
                else:
                    util.log(2, f"[音乐预加载] ❌ 转换失败: {song_name}")
            
            util.log(1, f"[音乐预加载] 🎉 预加载完成: {loaded_count}/{len(songs_to_load)} 首 (磁盘加载:{from_disk_count}首)")
            
        except Exception as e:
            util.log(2, f"[音乐预加载] ❌ 预加载失败: {str(e)}")
    
    if background:
        threading.Thread(target=_do_preload, daemon=True).start()
        util.log(1, "[音乐预加载] 🔄 后台预加载已启动...")
    else:
        _do_preload()


def get_music_cache_status():
    """获取音乐缓存状态"""
    global _music_opus_cache
    return {
        "cached_count": len(_music_opus_cache),
        "cached_files": list(_music_opus_cache.keys()),
        "total_frames": sum(len(frames) for frames in _music_opus_cache.values())
    }
