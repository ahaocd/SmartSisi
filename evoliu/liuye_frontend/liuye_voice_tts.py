#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
柳叶声音TTS
"""

import requests
import json
from pathlib import Path
import os
import threading
import queue
import time
import io
import re
from datetime import datetime

# 尝试导入numpy，如果失败则禁用流式播放
try:
    import numpy
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("⚠️ numpy未安装，流式播放功能将被禁用")
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ openai未安装，无法使用官方流式API。运行: pip install openai")

def clear_proxies():
    """清除代理设置"""
    proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
    for var in proxy_vars:
        if var in os.environ:
            del os.environ[var]
    
    session = requests.Session()
    session.trust_env = False
    session.proxies = {}
    return session

# 使用系统配置工具
import sys
import os

# 添加项目根目录到路径
current_file = os.path.abspath(__file__)  # E:\liusisi\SmartSisi\evoliu\liuye_frontend\liuye_voice_tts.py
frontend_dir = os.path.dirname(current_file)  # E:\liusisi\SmartSisi\evoliu\liuye_frontend
evoliu_dir = os.path.dirname(frontend_dir)  # E:\liusisi\SmartSisi\evoliu
project_root = os.path.dirname(evoliu_dir)  # E:\liusisi\SmartSisi

if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"🔧 项目根目录: {project_root}")

try:
    from utils.config_util import load_config, liuye_tts_api_key, liuye_voice_uri

    # 加载配置
    load_config()

    # 获取柳叶TTS配置
    LIUYE_API_KEY = liuye_tts_api_key
    LIUYE_VOICE_URI = liuye_voice_uri

    # 检查配置是否有效（不要在代码里硬编码密钥）
    if not LIUYE_API_KEY or not LIUYE_VOICE_URI:
        print("⚠️ 系统配置中柳叶TTS配置无效，请在 system.conf 中配置：liuye_tts_api_key / liuye_voice_uri")
        LIUYE_API_KEY = ""
        LIUYE_VOICE_URI = ""
    else:
        print("✅ 从系统配置加载柳叶TTS配置")

    print(f"🎤 音色URI: {LIUYE_VOICE_URI}")

except Exception as e:
    print(f"⚠️ 配置系统加载失败: {e}")
    print("🔄 请在 system.conf 中配置：liuye_tts_api_key / liuye_voice_uri")
    LIUYE_API_KEY = ""
    LIUYE_VOICE_URI = ""

# TTS高级功能配置

# ========== 设备连接与统一音频通路辅助 ==========
def _is_device_connected() -> bool:
    """检测是否有ESP32设备在线（用于设备优先策略）"""
    try:
        import sys
        # 从sisi_booter拿适配器（优先）
        try:
            import sisi_booter
            adapter = getattr(sisi_booter, 'esp32_adapter', None)
            if adapter and getattr(adapter, 'clients', None):
                for _cid, ws in adapter.clients.items():
                    if ws and not getattr(ws, 'closed', False):
                        return True
        except Exception:
            pass

        # 退而求其次：从已加载模块中猜测
        for name, mod in sys.modules.items():
            if not mod:
                continue
            if 'adapter' in name.lower() and hasattr(mod, 'clients'):
                try:
                    clients = getattr(mod, 'clients')
                    if clients:
                        for _cid, ws in clients.items():
                            if ws and not getattr(ws, 'closed', False):
                                return True
                except Exception:
                    continue
    except Exception:
        return False
    return False

def _get_audio_manager():
    """获取统一的AudioOutputManager实例（若不可用返回None）"""
    try:
        from esp32_liusisi.sisi_audio_output import AudioOutputManager
        return AudioOutputManager.get_instance()
    except Exception:
        return None
TTS_EMOTIONS = {
    "高兴": "高兴", "开心": "高兴", "快乐": "高兴", "兴奋": "兴奋",
    "悲伤": "悲伤", "难过": "悲伤", "伤心": "悲伤", "沮丧": "悲伤",
    "愤怒": "愤怒", "生气": "愤怒", "愤慨": "愤怒", "恼火": "愤怒",
    "温柔": "温柔", "轻柔": "温柔", "柔和": "温柔", "亲切": "温柔",
    "激情": "激情", "热情": "激情", "激动": "激情", "澎湃": "激情",
    "沉稳": "沉稳", "稳重": "沉稳", "冷静": "沉稳", "平静": "沉稳",
    "欢快": "欢快", "活泼": "欢快", "轻快": "欢快", "愉悦": "欢快"
}

TTS_SOUND_EFFECTS = {
    "[laughter]": "笑声", "[breathing]": "呼吸声", "[sigh]": "叹气声",
    "[whisper]": "耳语", "[pause]": "停顿", "[speed_up]": "加速",
    "[slow_down]": "减速", "[emphasis]": "强调", "[soft]": "轻声"
}

TTS_DIALECTS = {
    "粤语": "粤语", "广东话": "粤语", "白话": "粤语",
    "四川话": "四川话", "川话": "四川话", "巴蜀话": "四川话",
    "上海话": "上海话", "沪语": "上海话", "上海方言": "上海话",
    "郑州话": "郑州话", "河南话": "郑州话", "中原话": "郑州话",
    "长沙话": "长沙话", "湖南话": "长沙话", "湘语": "长沙话",
    "天津话": "天津话", "津门话": "天津话", "天津方言": "天津话"
}

TTS_LANGUAGES = {
    "英文": "英文", "英语": "英文", "English": "英文",
    "日文": "日语", "日语": "日语", "Japanese": "日语",
    "韩文": "韩语", "韩语": "韩语", "Korean": "韩语"
}

def enhance_text_with_tts_features(text, emotion=None, dialect=None, language=None, sound_effects=None):
    """
    智能增强文本，添加TTS特性标识

    Args:
        text: 原始文本
        emotion: 情感 (如: "高兴", "悲伤")
        dialect: 方言 (如: "粤语", "四川话")
        language: 语言 (如: "英文", "日语")
        sound_effects: 音效列表 (如: ["[laughter]", "[breathing]"])

    Returns:
        增强后的文本
    """
    enhanced_text = text

    # 添加情感控制
    if emotion and emotion in TTS_EMOTIONS:
        emotion_key = TTS_EMOTIONS[emotion]
        enhanced_text = f"你能用{emotion_key}的情感说吗？<|endofprompt|>{enhanced_text}"

    # 添加方言控制
    elif dialect and dialect in TTS_DIALECTS:
        dialect_key = TTS_DIALECTS[dialect]
        enhanced_text = f"请问你能模仿{dialect_key}的口音吗？<|endofprompt|>{enhanced_text}"

    # 添加语言控制
    elif language and language in TTS_LANGUAGES:
        language_key = TTS_LANGUAGES[language]
        enhanced_text = f"请用{language_key}说：<|endofprompt|>{enhanced_text}"

    # 添加音效
    if sound_effects:
        for effect in sound_effects:
            if effect in TTS_SOUND_EFFECTS:
                # 在句子结尾添加音效
                enhanced_text = enhanced_text.replace("。", f"{effect}。")
                enhanced_text = enhanced_text.replace("！", f"{effect}！")
                enhanced_text = enhanced_text.replace("？", f"{effect}？")

    return enhanced_text

def parse_tts_instructions(text):
    """
    解析文本中的TTS指令

    Args:
        text: 包含TTS指令的文本

    Returns:
        dict: 解析出的TTS参数
    """
    instructions = {
        "emotion": None,
        "dialect": None,
        "language": None,
        "sound_effects": [],
        "clean_text": text
    }

    # 检测情感指令
    for emotion_key in TTS_EMOTIONS:
        if emotion_key in text:
            instructions["emotion"] = emotion_key
            break

    # 检测方言指令
    for dialect_key in TTS_DIALECTS:
        if dialect_key in text:
            instructions["dialect"] = dialect_key
            break

    # 检测语言指令
    for language_key in TTS_LANGUAGES:
        if language_key in text:
            instructions["language"] = language_key
            break

    # 检测音效指令
    for effect_key in TTS_SOUND_EFFECTS:
        if effect_key in text:
            instructions["sound_effects"].append(effect_key)

    return instructions

def generate_liuye_voice_smart(text, output_filename=None, **tts_options):
    """
    智能柳叶语音生成 - 自动解析TTS指令

    Args:
        text: 文本内容
        output_filename: 输出文件名
        **tts_options: TTS选项 (emotion, dialect, language, sound_effects等)

    Returns:
        生成的音频文件路径
    """
    # 解析文本中的TTS指令
    instructions = parse_tts_instructions(text)

    # 合并显式参数和解析出的指令
    final_options = {**instructions, **tts_options}

    # 增强文本
    enhanced_text = enhance_text_with_tts_features(
        final_options["clean_text"],
        emotion=final_options.get("emotion"),
        dialect=final_options.get("dialect"),
        language=final_options.get("language"),
        sound_effects=final_options.get("sound_effects")
    )

    print(f"🎭 智能TTS处理:")
    print(f"   原文本: {text}")
    print(f"   增强文本: {enhanced_text}")
    print(f"   情感: {final_options.get('emotion', '无')}")
    print(f"   方言: {final_options.get('dialect', '无')}")
    print(f"   语言: {final_options.get('language', '无')}")
    print(f"   音效: {final_options.get('sound_effects', '无')}")

    # 生成语音
    return generate_liuye_voice_streaming(enhanced_text, output_filename)

def split_text_into_sentences(text):
    """
    智能中文分句 - 基于中文标点符号标准
    停顿时长：句号 > 分号 > 逗号 > 顿号

    优化策略：
    1. 优先按句末点号分句（句号、问号、叹号）- 最长停顿
    2. 其次按分号分句 - 中等停顿
    3. 长句按逗号分句 - 短停顿
    4. 保持自然语音节奏
    """
    # 第一步：按句末点号分句（句号、问号、叹号）
    primary_sentences = re.split(r'([。！？.!?])', text)

    result = []
    current_sentence = ""

    for i in range(0, len(primary_sentences), 2):
        if i < len(primary_sentences):
            sentence_part = primary_sentences[i].strip()
            punctuation = primary_sentences[i+1] if i+1 < len(primary_sentences) else ""

            if sentence_part:
                full_sentence = sentence_part + punctuation

                # 如果句子太长（>50字），按分号或逗号进一步分句
                if len(sentence_part) > 50:
                    # 按分号分句
                    sub_sentences = re.split(r'([；;])', sentence_part)
                    for j in range(0, len(sub_sentences), 2):
                        if j < len(sub_sentences):
                            sub_part = sub_sentences[j].strip()
                            sub_punct = sub_sentences[j+1] if j+1 < len(sub_sentences) else ""

                            if sub_part:
                                # 如果子句还是太长（>30字），按逗号分句
                                if len(sub_part) > 30:
                                    comma_parts = re.split(r'([，,])', sub_part)
                                    for k in range(0, len(comma_parts), 2):
                                        if k < len(comma_parts):
                                            comma_part = comma_parts[k].strip()
                                            comma_punct = comma_parts[k+1] if k+1 < len(comma_parts) else ""

                                            if comma_part:
                                                # 最后一个逗号分句加上原句的标点
                                                if k == len(comma_parts) - 2:
                                                    result.append(comma_part + comma_punct + sub_punct + punctuation)
                                                else:
                                                    result.append(comma_part + comma_punct)
                                else:
                                    # 最后一个分号分句加上原句的标点
                                    if j == len(sub_sentences) - 2:
                                        result.append(sub_part + sub_punct + punctuation)
                                    else:
                                        result.append(sub_part + sub_punct)
                else:
                    result.append(full_sentence)

    # 过滤空句子并确保标点
    final_result = []
    for sentence in result:
        sentence = sentence.strip()
        if sentence:
            # 如果没有标点，添加句号
            if not re.search(r'[。！？；，、.!?;,]$', sentence):
                sentence += '。'
            final_result.append(sentence)

    return final_result

def generate_liuye_voice_optimized_streaming(text, output_dir=None, play_realtime=True):
    """
    修复后的流式播放实现 - 消除噪音问题

    修复内容：
    1. 改用pyaudio + wave.open(response.raw)实现真正的流式播放
    2. 消除pygame.mixer.Sound(buffer=chunk)的噪音问题
    3. 保持低延迟优势
    4. 确保音质正常

    Args:
        text (str): 要转换的文本
        output_dir (str): 输出目录
        play_realtime (bool): 是否实时播放

    Returns:
        list: 生成的文件路径列表
    """
    session = clear_proxies()

    # 创建输出文件夹
    if output_dir is None:
        output_dir = Path("E:/liusisi/SmartSisi/evoliu/liuye_decision_center/data/柳叶语音文件")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 🔥 **移除分句逻辑，直接处理完整文本**
    print(f"🎵 修复后的流式播放 - 无分句处理")
    print(f"📝 完整文本: {text}")

    generated_files = []
    total_start_time = time.time()

    # 🔥 **直接处理完整文本，不进行分句**
    print(f"\n🔊 生成完整文本: {text}")

    sentence_start_time = time.time()

    # 生成完整文本的音频
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"liuye_fixed_{timestamp}.wav"
    output_path = output_dir / output_filename

    # 🔧 优化：使用更快的流式参数，减少延迟
    url = "https://api.siliconflow.cn/v1/audio/speech"
    headers = {"Authorization": f"Bearer {LIUYE_API_KEY}"}

    payload = {
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "input": text,
        "voice": LIUYE_VOICE_URI,
        "response_format": "wav",
        "sample_rate": 16000,  # 与统一链路保持一致
        "gain": -2,
        "stream": True,
        "speed": 1.0
    }

    try:
        # 流式请求
        response = session.post(url, headers=headers, json=payload, stream=True, timeout=60)

        if response.status_code == 200:
            first_chunk_time = None

            # 保存完整音频文件
            with open(output_path, 'wb') as f:
                chunk_count = 0
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        chunk_count += 1
                        f.write(chunk)

                        # 记录首块延迟
                        if first_chunk_time is None:
                            first_chunk_time = time.time()
                            first_chunk_delay = first_chunk_time - sentence_start_time
                            print(f"     ⚡ 首块延迟: {first_chunk_delay:.3f}秒")

            sentence_end_time = time.time()
            sentence_total_time = sentence_end_time - sentence_start_time
            file_size = output_path.stat().st_size

            print(f"     ✅ 完整文本完成: {sentence_total_time:.3f}秒")
            print(f"     📁 文件: {output_path.name} ({file_size} 字节)")
            print(f"     📦 数据块: {chunk_count} 个")

            # 统一：不在此处触发PC本地播放，交由上层决定（设备优先由Core播放）
            if play_realtime:
                print(f"     🎵 已生成完整文本（设备优先，跳过PC即时播放）")

            generated_files.append(str(output_path))

        else:
            print(f"     ❌ 生成失败: {response.status_code}")

    except Exception as e:
        print(f"     ❌ 异常: {e}")

    total_end_time = time.time()
    total_time = total_end_time - total_start_time

    print(f"\n🎉 修复后的流式播放完成!")
    print(f"📊 总耗时: {total_time:.3f}秒")
    print(f"📊 完整文本处理: 1个文件")
    # 不再计算平均每句时间，因为已改为处理完整文本
    print(f"📁 生成文件: {len(generated_files)} 个")

    return generated_files

def _play_audio_stream_optimized(audio_queue, sample_rate):
    return

def generate_liuye_voice_streaming(text, output_filename=None, play_realtime=False):
    """
    柳叶TTS流式播放 - 修复后版本
    实现真正的Adaptive Streaming（自适应流式播放）
    - 消除杂音和爆音问题
    - 边接收HTTP chunks边播放
    - 音质清晰，延迟低（~200ms流式延迟）

    Args:
        text (str): 要转换的文本
        output_filename (str): 输出文件名，如果为None则自动生成
        play_realtime (bool): 是否实时播放

    Returns:
        str: 生成的文件路径，失败返回None
    """
    import struct

    session = clear_proxies()

    # 配置信息
    api_key = LIUYE_API_KEY
    voice_uri = LIUYE_VOICE_URI

    # 创建输出文件夹
    output_dir = Path("E:/liusisi/SmartSisi/evoliu/liuye_decision_center/data/柳叶语音文件")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    if output_filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"liuye_stream_{timestamp}.wav"

    output_path = output_dir / output_filename

    url = "https://api.siliconflow.cn/v1/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}"}

    payload = {
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "input": text,
        "voice": voice_uri,
        "response_format": "wav",
        "sample_rate": 16000,  # 统一为16kHz，交由AudioOutputManager内部编码
        "gain": -2,
        "stream": True
    }

    print(f"🌊 柳叶TTS流式播放")
    print(f"📝 文本: {text}")
    print(f"📁 输出: {output_path}")
    print(f"🔊 实时播放(PC): {'是' if play_realtime else '否'}")

    def parse_wav_header(data):
        """解析WAV文件头"""
        if len(data) < 44 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
            return None

        # 查找fmt chunk
        fmt_pos = data.find(b'fmt ')
        if fmt_pos == -1:
            return None

        fmt_size = struct.unpack('<I', data[fmt_pos+4:fmt_pos+8])[0]
        fmt_data = data[fmt_pos+8:fmt_pos+8+fmt_size]

        if len(fmt_data) < 16:
            return None

        audio_format, channels, sample_rate, byte_rate, block_align, bits_per_sample = struct.unpack('<HHIIHH', fmt_data[:16])

        # 查找data chunk
        data_pos = data.find(b'data')
        if data_pos == -1:
            return None

        audio_data_start = data_pos + 8

        return {
            'channels': channels,
            'sample_rate': sample_rate,
            'bits_per_sample': bits_per_sample,
            'block_align': block_align,
            'audio_data_start': audio_data_start
        }

    try:
        print(f"📡 发送流式请求...")
        request_start_time = time.time()

        response = session.post(url, headers=headers, json=payload, stream=True, timeout=120)

        if response.status_code == 200:
            first_byte_time = time.time()
            first_byte_delay = (first_byte_time - request_start_time) * 1000
            print(f"✅ 首字节延迟: {first_byte_delay:.0f}ms")

            # 尝试导入pyaudio进行真正的流式播放
            try:
                import pyaudio
                PYAUDIO_AVAILABLE = True
            except ImportError:
                PYAUDIO_AVAILABLE = False

            if play_realtime and PYAUDIO_AVAILABLE:
                # 设备优先：若传入要求PC播放才启用；默认False不在PC播放
                print(f"🌊 开始PC端流式播放（仅调试用）...")

                audio_buffer = b""
                complete_audio = b""
                header_parsed = False
                audio_info = None
                p = None
                stream = None
                first_audio_time = None
                chunk_count = 0
                min_buffer_size = 4096  # 4KB缓冲

                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        chunk_count += 1
                        audio_buffer += chunk
                        complete_audio += chunk

                        # 解析WAV头部（只在第一次）
                        if not header_parsed and len(audio_buffer) >= 44:
                            audio_info = parse_wav_header(audio_buffer)
                            if audio_info:
                                print(f"📊 音频参数: {audio_info['sample_rate']}Hz, {audio_info['channels']}声道, {audio_info['bits_per_sample']}bit")

                                # 初始化pyaudio
                                p = pyaudio.PyAudio()
                                format = pyaudio.paInt16 if audio_info['bits_per_sample'] == 16 else pyaudio.paInt24

                                stream = p.open(
                                    format=format,
                                    channels=audio_info['channels'],
                                    rate=audio_info['sample_rate'],
                                    output=True,
                                    frames_per_buffer=1024
                                )

                                header_parsed = True

                                # 跳过WAV头部，获取纯音频数据
                                if len(audio_buffer) > audio_info['audio_data_start']:
                                    pure_audio_data = audio_buffer[audio_info['audio_data_start']:]
                                    audio_buffer = pure_audio_data

                        # 如果头部已解析且有足够的音频数据，开始播放
                        if header_parsed and stream and len(audio_buffer) >= min_buffer_size:
                            if first_audio_time is None:
                                first_audio_time = time.time()
                                first_audio_delay = (first_audio_time - request_start_time) * 1000
                                print(f"🎵 首次播放延迟: {first_audio_delay:.0f}ms")

                            # 按音频帧对齐播放
                            block_align = audio_info['block_align']
                            playable_frames = len(audio_buffer) // block_align
                            playable_bytes = playable_frames * block_align

                            if playable_bytes > 0:
                                stream.write(audio_buffer[:playable_bytes])
                                audio_buffer = audio_buffer[playable_bytes:]

                            if chunk_count % 50 == 0:
                                current_time = time.time()
                                elapsed = current_time - request_start_time
                                print(f"   🌊 流式播放进度: 第{chunk_count}个chunk，已播放 {elapsed:.1f}秒")

                # 播放剩余音频数据
                if header_parsed and stream and len(audio_buffer) > 0:
                    block_align = audio_info['block_align']
                    playable_frames = len(audio_buffer) // block_align
                    playable_bytes = playable_frames * block_align
                    if playable_bytes > 0:
                        stream.write(audio_buffer[:playable_bytes])

                if stream:
                    print(f"✅ 真正的流式播放完成，处理了 {chunk_count} 个HTTP chunks")
                    stream.close()
                if p:
                    p.terminate()

                # 保存完整音频文件
                with open(output_path, 'wb') as f:
                    f.write(complete_audio)

                total_time = time.time() - request_start_time
                print(f"📊 柳叶TTS流式播放总结:")
                print(f"   首字节延迟: {first_byte_delay:.0f}ms")
                if first_audio_time:
                    print(f"   首次播放延迟: {(first_audio_time - request_start_time) * 1000:.0f}ms")
                print(f"   总耗时: {total_time:.2f}秒")
                print(f"   HTTP chunks: {chunk_count}")

            else:
                # 设备优先：改为真正逐块送入统一队列，不再整段累计
                print(f"📦 逐块转交统一音频队列（设备优先，不在PC播放）...")
                header_buffer = bytearray()
                wav_header_parsed = False
                audio_data_start = 0
                chunk_count = 0
                total_bytes = 0

                # 输入WAV参数与转换状态
                in_rate = None
                in_channels = None
                in_width = None  # bytes per sample
                pcm_pending = bytearray()
                ratecv_state = None

                from esp32_liusisi.sisi_audio_output import AudioOutputManager
                aom = AudioOutputManager.get_instance()
                if not aom:
                    print(f"⚠️ 未找到AudioOutputManager实例，无法送入统一队列")
                    # 仍保存文件以便排查
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    return None

                import audioop

                def _push_converted_pcm(pcm_bytes: bytes, is_final: bool = False):
                    nonlocal pcm_pending, ratecv_state, in_channels, in_width, in_rate
                    if not pcm_bytes and not is_final:
                        return
                    pcm_pending.extend(pcm_bytes)
                    if in_channels and in_width and in_rate:
                        frame_size_in = in_channels * in_width
                        # 只处理对齐的整帧，剩余留待下次
                        process_len = (len(pcm_pending) // frame_size_in) * frame_size_in
                        if process_len > 0:
                            to_process = bytes(pcm_pending[:process_len])
                            pcm_pending = pcm_pending[process_len:]

                            data_conv = to_process
                            # 声道转单声道
                            if in_channels == 2:
                                try:
                                    data_conv = audioop.tomono(data_conv, in_width, 0.5, 0.5)
                                except Exception:
                                    # 失败则取左声道近似
                                    data_conv = data_conv[0::2*in_width] + data_conv[in_width::2*in_width]
                                    data_conv = audioop.lin2lin(data_conv, in_width, in_width)
                            elif in_channels != 1:
                                # 非1/2声道，保守取第一声道样本
                                try:
                                    # 依声道宽度拆分，取第一声道
                                    step = in_channels * in_width
                                    data_conv = b''.join([to_process[i:i+in_width] for i in range(0, len(to_process), step)])
                                except Exception:
                                    pass

                            # 位宽转16bit
                            if in_width != 2:
                                try:
                                    data_conv = audioop.lin2lin(data_conv, in_width, 2)
                                except Exception:
                                    # 无法转换则丢弃该段，避免爆音
                                    data_conv = b''

                            # 采样率转16k
                            if in_rate != 16000 and data_conv:
                                try:
                                    data_conv, ratecv_state = audioop.ratecv(data_conv, 2, 1, in_rate, 16000, ratecv_state)
                                except Exception:
                                    data_conv = b''

                            if data_conv:
                                aom.add_stream_chunk(data_conv, priority=5, is_final=False)

                    # 最终flush剩余并发送结束标记
                    if is_final:
                        # 把剩余对齐后再转
                        if in_channels and in_width and in_rate and len(pcm_pending) > 0:
                            frame_size_in2 = in_channels * in_width
                            tail_len = (len(pcm_pending) // frame_size_in2) * frame_size_in2
                            if tail_len > 0:
                                tail = bytes(pcm_pending[:tail_len])
                                pcm_pending = pcm_pending[tail_len:]
                                try:
                                    data_conv = tail
                                    if in_channels == 2:
                                        data_conv = audioop.tomono(data_conv, in_width, 0.5, 0.5)
                                    elif in_channels != 1:
                                        step = in_channels * in_width
                                        data_conv = b''.join([tail[i:i+in_width] for i in range(0, len(tail), step)])
                                    if in_width != 2:
                                        data_conv = audioop.lin2lin(data_conv, in_width, 2)
                                    if in_rate != 16000:
                                        data_conv, ratecv_state = audioop.ratecv(data_conv, 2, 1, in_rate, 16000, ratecv_state)
                                    if data_conv:
                                        aom.add_stream_chunk(data_conv, priority=5, is_final=False)
                                except Exception:
                                    pass
                        aom.add_stream_chunk(b'', priority=5, is_final=True)

                for net_chunk in response.iter_content(chunk_size=4096):
                    if not net_chunk:
                        continue
                    chunk_count += 1
                    total_bytes += len(net_chunk)

                    if not wav_header_parsed:
                        header_buffer.extend(net_chunk)
                        if len(header_buffer) >= 44 and header_buffer[:4] == b'RIFF' and header_buffer[8:12] == b'WAVE':
                            # 解析WAV头
                            info = parse_wav_header(bytes(header_buffer))
                            if info:
                                audio_data_start = info['audio_data_start']
                                in_channels = info['channels']
                                in_rate = info['sample_rate']
                                in_width = max(1, info['bits_per_sample'] // 8)
                                # 将头后面的音频数据作为第一批PCM提交（规范化处理）
                                if len(header_buffer) > audio_data_start:
                                    pcm_part = bytes(header_buffer[audio_data_start:])
                                    if pcm_part:
                                        _push_converted_pcm(pcm_part, is_final=False)
                                header_buffer.clear()
                                wav_header_parsed = True
                            continue
                        elif len(header_buffer) >= 44:
                            # 非标准头，当作原始PCM，采用保守默认参数：16k/单声道/16bit
                            if in_channels is None:
                                in_channels = 1
                                in_rate = 16000
                                in_width = 2
                            _push_converted_pcm(bytes(header_buffer), is_final=False)
                            header_buffer.clear()
                            wav_header_parsed = True
                            continue
                        else:
                            continue
                    else:
                        # 已解析头，直接规范化并送入队列
                        _push_converted_pcm(net_chunk, is_final=False)

                    if chunk_count % 10 == 0:
                        print(f"   📦 已送入 {chunk_count} 个数据块，累计 {total_bytes} 字节")

                # 发送结束（规范化剩余并发最终标记）
                _push_converted_pcm(b'', is_final=True)
                print(f"✅ 已逐块将柳叶PCM交给统一队列（设备优先），总计 {total_bytes} 字节")

                # 仍保存空文件占位用于调试（不影响播放）
                try:
                    with open(output_path, 'wb') as f:
                        f.write(b'')
                except Exception:
                    pass

            file_size = (output_path.stat().st_size if output_path.exists() else 0)
            if file_size:
                print(f"📁 文件已保存: {output_path.name} ({file_size} 字节)")
            return str(output_path)

        else:
            print(f"❌ 流式生成失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return None

    except Exception as e:
        print(f"❌ 流式生成异常: {e}")
        return None

# 旧的有问题的播放函数已删除，使用修复后的流式播放

def generate_liuye_voice(text, output_filename=None):
    """
    生成柳叶的语音（非流式版本，保持兼容性）

    Args:
        text (str): 要转换的文本
        output_filename (str): 输出文件名，如果为None则自动生成

    Returns:
        str: 生成的文件路径，失败返回None
    """
    session = clear_proxies()

    # 配置信息
    api_key = LIUYE_API_KEY
    voice_uri = LIUYE_VOICE_URI

    # 创建输出文件夹
    output_dir = Path("E:/liusisi/SmartSisi/evoliu/liuye_decision_center/data/柳叶语音文件")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    if output_filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"liuye_voice_{timestamp}.wav"

    output_path = output_dir / output_filename

    url = "https://api.siliconflow.cn/v1/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}"}

    payload = {
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "input": text,
        "voice": voice_uri,
        "response_format": "wav",
        "sample_rate": 16000,
        "gain": -2
    }

    print(f"🔊 正在生成柳叶语音...")
    print(f"📝 文本: {text}")
    print(f"📁 输出: {output_path}")

    try:
        response = session.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)

            file_size = output_path.stat().st_size
            print(f"✅ 柳叶语音生成成功!")
            print(f"   文件: {output_path}")
            print(f"   大小: {file_size} 字节")
            print(f"   采样率: 24000Hz")
            print(f"   音量: -2dB (调低20%)")

            return str(output_path)
        else:
            print(f"❌ 生成失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return None

    except Exception as e:
        print(f"❌ 生成异常: {e}")
        return None

def test_streaming_tts():
    """测试流式TTS"""
    print("🎵 柳叶流式TTS测试")
    print("=" * 60)

    # 测试文本
    test_texts = [
        "大家好，我是柳叶！这是流式语音合成测试。",
        "流式TTS可以边生成边播放，大大减少了等待时间。",
        "我的意中人是个盖世英雄，有一天，他会踩着七彩祥云来娶我。"
    ]

    success_count = 0
    generated_files = []

    for i, text in enumerate(test_texts, 1):
        print(f"\n🎵 流式测试 {i}/3")
        result = generate_liuye_voice_streaming(
            text,
            f"stream_test_{i}.wav",
            play_realtime=True
        )

        if result:
            success_count += 1
            generated_files.append(result)

        # 间隔3秒
        time.sleep(3)

    # 结果总结
    print(f"\n" + "=" * 60)
    print(f"🎉 流式TTS测试完成!")
    print(f"📊 成功: {success_count}/3")

    if generated_files:
        print(f"\n🎵 生成的流式文件:")
        for file_path in generated_files:
            print(f"   - {file_path}")

        print(f"\n📁 文件位置:")
        print(f"   E:/liusisi/SmartSisi/evoliu/liuye_decision_center/data/柳叶语音文件/")

        print(f"\n⚙️ 流式音频参数:")
        print(f"   - 采样率: 24000Hz")
        print(f"   - 音量: -2dB (调低20%)")
        print(f"   - 格式: WAV")
        print(f"   - 流式传输: 是")
        print(f"   - 实时播放: {'是' if PYGAME_AVAILABLE else '否 (需要pygame)'}")

    return success_count > 0

def test_liuye_voice():
    """测试柳叶语音生成（非流式）"""
    print("🎤 柳叶声音TTS测试（非流式）")
    print("=" * 50)

    # 测试文本
    test_texts = [
        "大家好，我是柳叶！这是我的语音克隆系统。",
        "现在的音质怎么样？听起来自然吗？"
    ]

    success_count = 0
    generated_files = []

    for i, text in enumerate(test_texts, 1):
        print(f"\n🔊 测试 {i}/2")
        result = generate_liuye_voice(text, f"normal_test_{i}.wav")

        if result:
            success_count += 1
            generated_files.append(result)

        # 间隔2秒
        time.sleep(2)

    # 结果总结
    print(f"\n" + "=" * 50)
    print(f"🎉 柳叶语音测试完成!")
    print(f"📊 成功: {success_count}/2")

    if generated_files:
        print(f"\n🎵 生成的文件:")
        for file_path in generated_files:
            print(f"   - {file_path}")

        print(f"\n📁 文件位置:")
        print(f"   E:/liusisi/SmartSisi/evoliu/liuye_decision_center/data/柳叶语音文件/")

        print(f"\n⚙️ 音频参数:")
        print(f"   - 采样率: 24000Hz")
        print(f"   - 音量: -2dB (调低20%)")
        print(f"   - 格式: WAV")

    return success_count > 0

def test_optimized_streaming():
    """测试最大化流式优势"""
    print("🚀 最大化SiliconFlow流式优势测试")
    print("=" * 70)

    # 测试文本 - 包含多个句子
    test_texts = [
        "大家好，我是柳叶！今天我们来测试最大化流式优势的语音合成。这个系统可以智能分句，并发生成，实时播放。",
        "床前明月光，疑是地上霜。举头望明月，低头思故乡。这是李白的静夜思，非常经典的古诗。",
        "我的意中人是个盖世英雄，有一天，他会踩着七彩祥云来娶我。这句话来自大话西游，很有名。"
    ]

    success_count = 0
    all_generated_files = []

    for i, text in enumerate(test_texts, 1):
        print(f"\n🎯 优化测试 {i}/3")
        print(f"=" * 50)

        start_time = time.time()
        generated_files = generate_liuye_voice_optimized_streaming(
            text,
            play_realtime=True
        )
        end_time = time.time()

        if generated_files:
            success_count += 1
            all_generated_files.extend(generated_files)
            print(f"✅ 测试 {i} 成功，耗时 {end_time - start_time:.3f}秒")
        else:
            print(f"❌ 测试 {i} 失败")

        # 测试间隔
        if i < len(test_texts):
            time.sleep(2)

    # 结果总结
    print(f"\n" + "=" * 70)
    print(f"🎉 最大化流式优势测试完成!")
    print(f"📊 成功: {success_count}/3")
    print(f"📁 总文件数: {len(all_generated_files)}")

    if all_generated_files:
        print(f"\n🎵 生成的优化文件:")
        for file_path in all_generated_files:
            print(f"   - {Path(file_path).name}")

        print(f"\n📁 文件位置:")
        print(f"   E:/liusisi/SmartSisi/evoliu/liuye_decision_center/data/柳叶语音文件/")

        print(f"\n🚀 优化策略:")
        print(f"   - 智能分句: 按标点符号分割")
        print(f"   - 并发生成: 每句独立快速合成")
        print(f"   - 流式传输: 1KB chunk_size")
        print(f"   - 实时播放: 边接收边播放")
        print(f"   - 延迟优化: 跳过WAV头部")

    return success_count > 0

def main():
    """主函数"""
    print("🎵 柳叶TTS系统 - 最大化流式优势版")
    print("=" * 70)
    print("1. 最大化流式优势测试 (推荐)")
    print("2. 普通流式TTS测试")
    print("3. 标准TTS测试")
    print("4. 全部测试")

    choice = input("\n请选择测试模式 (1/2/3/4): ").strip()

    if choice == "1":
        test_optimized_streaming()
    elif choice == "2":
        test_streaming_tts()
    elif choice == "3":
        test_liuye_voice()
    elif choice == "4":
        print("\n🔄 开始全部测试...")
        test_liuye_voice()
        print("\n" + "="*70)
        test_streaming_tts()
        print("\n" + "="*70)
        test_optimized_streaming()
    else:
        print("❌ 无效选择，默认运行最大化流式优势测试")
        test_optimized_streaming()

if __name__ == "__main__":
    main()
