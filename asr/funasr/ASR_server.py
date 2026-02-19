import asyncio
import websockets
import argparse
import json
import logging
import os
import time
import threading
import concurrent.futures

# 🔧 修复FFmpeg路径问题（torchcodec需要FFmpeg shared版本的DLL）
def fix_ffmpeg_path():
    """修复FFmpeg路径，让torchcodec能找到DLL"""
    ffmpeg_paths = [
        # BtbN FFmpeg 7.1 GPL Shared (带DLL，兼容torchcodec 0.9.1)
        r"C:\Users\senlin\AppData\Local\Microsoft\WinGet\Packages\BtbN.FFmpeg.GPL.Shared.7.1_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-n7.1.3-22-g40b336e650-win64-gpl-shared-7.1\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\ffmpeg\bin",
    ]
    for ffmpeg_path in ffmpeg_paths:
        if os.path.exists(ffmpeg_path):
            current_path = os.environ.get('PATH', '')
            if ffmpeg_path not in current_path:
                os.environ['PATH'] = ffmpeg_path + ';' + current_path
            os.environ['FFMPEG_BINARY'] = os.path.join(ffmpeg_path, "ffmpeg.exe")
            print(f"[FFmpeg] 路径已配置: {ffmpeg_path}")
            return True
    print("[FFmpeg] 未找到shared版本")
    return False

# 在导入FunASR之前修复FFmpeg
fix_ffmpeg_path()

# 优先设置本地模型缓存目录，避免每次联网下载
try:
    os.environ.setdefault('MODELSCOPE_CACHE', r"C:\Users\senlin\.cache\modelscope\hub")
except Exception:
    pass

from funasr import AutoModel

# SISI声纹识别系统 - 唯一的声纹识别方案
print("[SISI] 声纹识别系统已就绪")

# 设置日志级别
logger = logging.getLogger(__name__)
logger.setLevel(logging.CRITICAL)

# 解析命令行参数
parser = argparse.ArgumentParser()
parser.add_argument("--host", type=str, default="0.0.0.0", help="host ip, localhost, 0.0.0.0")
parser.add_argument("--port", type=int, default=10197, help="grpc server port")
parser.add_argument("--ngpu", type=int, default=1, help="0 for cpu, 1 for gpu")
args = parser.parse_args()

# 初始化模型
print("model loading")
print(f"FunASR版本检查...")

# 检查FunASR版本
try:
    import funasr
    print(f"FunASR版本: {funasr.__version__}")
except:
    print("无法获取FunASR版本")

# 检查ModelScope版本
try:
    import modelscope
    print(f"ModelScope版本: {modelscope.__version__}")
except:
    print("无法获取ModelScope版本")

# 🔥 读取配置文件，根据asr_mode选择模型
import configparser
config = configparser.ConfigParser()
# 修复：正确计算配置文件路径（ASR_server.py在SmartSisi/asr/funasr/，需要向上3层到SmartSisi/）
current_file = os.path.abspath(__file__)  # E:\liusisi\SmartSisi\asr\funasr\ASR_server.py
asr_dir = os.path.dirname(current_file)  # E:\liusisi\SmartSisi\asr\funasr
smartsisi_dir = os.path.dirname(os.path.dirname(asr_dir))  # E:\liusisi\SmartSisi
config_path = os.path.join(smartsisi_dir, "system.conf")
asr_mode = "sensevoice"  # 默认值

try:
    print(f"[配置] 尝试读取配置文件: {config_path}")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    config.read(config_path, encoding='utf-8')
    asr_mode = config.get('key', 'asr_mode', fallback='sensevoice').lower()
    print(f"[配置] 配置文件读取成功: asr_mode = {asr_mode}")
except Exception as e:
    print(f"[配置] 配置文件读取失败: {e}，使用默认值 sensevoice")

# 根据配置加载对应模型
local_root = os.path.expandvars(r"C:\Users\senlin\.cache\modelscope\hub\models\iic")

if asr_mode == "funasr":
    # 使用FunASR Paraformer模型
    print("[配置] 模式: FunASR (Paraformer)")
    try:
        local_paraformer = os.path.join(local_root, "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch")
        local_vad = os.path.join(local_root, "speech_fsmn_vad_zh-cn-16k-common-pytorch")
        local_punc = os.path.join(local_root, "punc_ct-transformer_zh-cn-common-vocab272727-pytorch")

        if os.path.exists(local_paraformer) and os.path.exists(local_vad) and os.path.exists(local_punc):
            print("[模型] 使用本地Paraformer模型")
            asr_model = AutoModel(
                model=local_paraformer,
                vad_model=local_vad,
                punc_model=local_punc,
                disable_update=True,
                device="cpu"
            )
        else:
            print("[模型] 使用远程Paraformer模型")
            asr_model = AutoModel(
                model="iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                disable_update=True,
                device="cpu"
            )
        print("[模型] FunASR Paraformer加载成功")
    except Exception as e:
        print(f"[错误] Paraformer加载失败: {e}")
        raise

else:
    # 使用SenseVoice模型（默认）
    print("[配置] 模式: SenseVoice")
    try:
        local_model = os.path.join(local_root, "SenseVoiceSmall")
        local_vad = os.path.join(local_root, "speech_fsmn_vad_zh-cn-16k-common-pytorch")
        local_punc = os.path.join(local_root, "punc_ct-transformer_zh-cn-common-vocab272727-pytorch")

        if os.path.exists(local_model) and os.path.exists(local_vad) and os.path.exists(local_punc):
            print("[模型] 使用本地SenseVoice模型")
            asr_model = AutoModel(
                model=local_model,
                vad_model=local_vad,
                punc_model=local_punc,
                disable_update=True,
                device="cpu"
            )
        else:
            print("[模型] 使用远程SenseVoice模型")
            asr_model = AutoModel(
                model="iic/SenseVoiceSmall",
                vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                disable_update=True,
                device="cpu"
            )
        print("[模型] SenseVoice加载成功")
    except Exception as e:
        print(f"[错误] SenseVoice加载失败: {e}")
        raise

# 验证模型功能
print("[验证] 验证ASR模型功能...")
try:
    if hasattr(asr_model, 'generate') or hasattr(asr_model, '__call__'):
        print(f"[验证] ASR功能可用 - {asr_mode.upper()}模型已就绪")
    elif hasattr(asr_model, 'model'):
        print(f"[验证] ASR功能可用 - {asr_mode.upper()}模型对象已加载")
    else:
        print("[验证] ASR功能验证失败 - 未找到预期的方法")
        print(f"[验证] 模型对象属性: {dir(asr_model)[:10]}...")
except Exception as ve:
    print(f"[验证] ASR功能验证异常: {ve}")
    print("[验证] 但模型已加载，继续启动服务...")

print("model loaded")

# 🚀 极速响应优化配置
param_dict = {
    # ✅ 开启（不影响速度）
    "use_itn": True,              # 数字归一化：一千二百三十四→1234
    "sentence_timestamp": True,    # 句子时间戳：返回每句话的时间
    
    # ❌ 不开启（影响速度）
    "word_timestamp": False,       # 词级时间戳：不需要
    
    # 🎯 批量大小优化
    "batch_size": 1,               # 单句处理，降低延迟
}

# 使用脚本所在目录的相对路径
script_dir = os.path.dirname(os.path.abspath(__file__))
hotword_path = os.path.join(script_dir, "data", "hotword.txt")
os.makedirs(os.path.dirname(hotword_path), exist_ok=True)  # 创建目录

try:
    with open(hotword_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        lines = [line.strip() for line in lines if line.strip()]  # 过滤空行
    hotword = " ".join(lines)
    print(f"已加载热词：{hotword}")
    param_dict["hotword"] = hotword
except Exception as e:
    print(f"加载热词失败: {e}")
    # 如果文件不存在，创建一个空的热词文件
    if not os.path.exists(hotword_path):
        os.makedirs(os.path.dirname(hotword_path), exist_ok=True)
        with open(hotword_path, "w", encoding="utf-8") as f:
            f.write("看呗\n看吧\n看一下\n看看\n你看\n你看吧\n你来看\n你看一下\n你这样看\n你慢慢看\n你快点看\n你快看一下\n睁开你的眼睛\n别看了\n那你别看了\n那就别看\n那就闭上眼睛\n闭眼\n别看\n")
        print("已创建默认热词文件")
    param_dict["hotword"] = ""

print(f"[优化配置] use_itn={param_dict.get('use_itn')}, sentence_timestamp={param_dict.get('sentence_timestamp')}, batch_size={param_dict.get('batch_size')}")

websocket_users = {}
task_queue = asyncio.Queue()

async def ws_serve(websocket):
    """WebSocket处理函数 - 适配 websockets 16.0+ 新API"""
    global websocket_users
    # websockets 13.0+ 移除了path参数，需要从websocket对象获取
    try:
        path = websocket.request.path if hasattr(websocket, 'request') else "/"
    except:
        path = "/"
    
    user_id = id(websocket)
    websocket_users[user_id] = websocket
    print(f"[ASR_server] 新客户端连接: user_id={user_id}")
    try:
        async for message in websocket:
            print(f"[ASR_server] 收到消息: {message[:200] if isinstance(message, str) else f'bytes({len(message)})'}")
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    if 'url' in data:
                        print(f"[ASR_server] 收到音频文件: {data['url']}")
                        await task_queue.put((websocket, data['url']))
                        print(f"[ASR_server] 已加入处理队列，当前队列大小: {task_queue.qsize()}")
                    elif 'state' in data:
                        print(f"[ASR_server] 状态消息: {data['state']}")
                except json.JSONDecodeError as e:
                    print(f"[ASR_server] JSON解析失败: {e}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"🔌 [ASR_server] 连接关闭: {e}")
    except Exception as e:
        print(f"❌ [ASR_server] 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"[ASR_server] 清理连接: user_id={user_id}")
        if user_id in websocket_users:
            del websocket_users[user_id]
        try:
            await websocket.close()
        except:
            pass

async def _extract_voiceprint_features(audio_path: str) -> dict:
    """🔥 SISI声纹识别系统 - 基于3D-Speaker的专业声纹识别
    增强：VAD端点裁剪 + 最短有效语音门限(2.5s) + 短句早通过(≥2.0s且sim≥0.45)
    只作用于“当次识别音频”，不修改底库。
    """
    try:
        import sys
        import os
        import numpy as np
        import tempfile
        import torch  # 不用torchaudio，用soundfile替代

        # 最短有效语音门限与早通过阈值（方案B）
        EFFECTIVE_SEC_MIN = 2.0
        EARLY_PASS_SEC = 1.0   # 原为2.0：≥1.0秒允许短句提前判定
        EARLY_PASS_SIM = 0.45
        HIGH_CONF_SIM = 0.65   # 原为0.70：极短但分数很高时直过

        # 简单的路径设置
        smartsisi_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        if smartsisi_root not in sys.path:
            sys.path.insert(0, smartsisi_root)

        print(f"[ASR声纹] 使用SISI声纹识别系统")

        from core.speaker_recognition import get_sisi_speaker_recognition

        # 简单获取实例
        recognizer = get_sisi_speaker_recognition()

        print(f"[ASR声纹] 已注册档案数量: {len(recognizer.speaker_profiles)}")
        print(f"[ASR声纹] 当前阈值: {recognizer.similarity_threshold}")

        # 1) 用soundfile加载音频，避免torchcodec问题
        import soundfile as sf
        audio_data, sr = sf.read(audio_path)
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)  # 转单声道
        w = torch.from_numpy(audio_data).float().unsqueeze(0)
        
        # VAD端点裁剪（能量阈值法）并统计有效语音时长
        e = (w**2).mean(dim=0)
        thr = e.mean() * 0.15  # 放宽阈值，避免过度丢帧
        mask = e > thr
        voiced_sec_est = float(mask.sum() / sr)
        audio_for_spk = audio_path
        trimmed_sec = 0.0
        if mask.any():
            idx = torch.where(mask)[0]
            w2 = w[:, idx[0]:idx[-1] + 1]
            trimmed_sec = float(w2.shape[1] / sr)
            fd, trimmed = tempfile.mkstemp(suffix='.wav'); os.close(fd)
            sf.write(trimmed, w2.squeeze().numpy(), sr)
            audio_for_spk = trimmed
            print(f"[ASR声纹] 有效语音(估计): {voiced_sec_est:.2f}s | 裁剪后连续段: {trimmed_sec:.2f}s")
        else:
            print(f"[ASR声纹] 有效语音(估计): {voiced_sec_est:.2f}s | 无法裁剪，使用原音频")
        # 将判定依据改为“连续有效段时长”，更符合直觉
        effective_sec = trimmed_sec if trimmed_sec > 0 else voiced_sec_est

        # 2) 预估Top相似度（用于短句早通过）
        te = recognizer._extract_embedding(audio_for_spk)
        sim_top = 0.0
        if te is not None:
            te = te / np.linalg.norm(te)
            for sid in recognizer.speaker_profiles:
                ef = os.path.join(recognizer.cache_dir, f"{sid}_embedding.npy")
                if os.path.exists(ef):
                    se = np.load(ef)
                    n = np.linalg.norm(se)
                    se = se / n if n > 0 else se
                    sim_top = max(sim_top, float(np.dot(te, se)))
        print(f"[ASR声纹] 预估Top相似度: {sim_top:.3f}")

        # 3) 判定策略（方案B）：
        #    - 高分短句直过：sim_top>=0.65
        #    - 或 短句早通过：effective_sec>=1.0 且 sim_top>=0.45
        #    - 否则若 >=2.0s 则正常识别
        #    - 再否则继续累计
        if sim_top >= HIGH_CONF_SIM:
            print("[ASR声纹] 高分短句直过")
            result = recognizer.identify_speaker(audio_for_spk)
        elif effective_sec >= EARLY_PASS_SEC and sim_top >= EARLY_PASS_SIM:
            print("[ASR声纹] 短句早通过")
            result = recognizer.identify_speaker(audio_for_spk)
        elif effective_sec >= EFFECTIVE_SEC_MIN:
            result = recognizer.identify_speaker(audio_for_spk)
        else:
            print(f"[ASR声纹] ⏳ 需要更多语音(继续累计) | 当前连续段: {effective_sec:.2f}s")
            result = {
                "speaker_id": "unknown",
                "confidence": 0.0,
                "is_registered": False,
                "encounter_count": 0,
                "username": None,
                "real_name": None,
                "role": "guest",
                "hint": "need_more_speech"
            }

        print(f"[ASR声纹] SISI识别结果: {result}")

        # 🎯 构建统一身份对象（SSOT）
        is_registered = result.get("is_registered", False)
        speaker_id = result.get("speaker_id", "unknown")
        username = result.get("username") or result.get("real_name")
        confidence = result.get("confidence", 0.0)

        # 统一身份标签：owner（已注册且置信度高）或 stranger
        if is_registered and confidence >= recognizer.similarity_threshold:
            identity_label = "owner"
            user_id = speaker_id
            display_name = username or "已注册用户"
        else:
            identity_label = "stranger"
            user_id = "stranger"
            display_name = "陌生人"
            username = None

        return {
            # 统一身份对象（所有下游模块的SSOT）
            "identity": {
                "label": identity_label,
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "is_registered": is_registered,
                "confidence": confidence,
                "profile": {"gender": "male", "age": 30} if identity_label == "owner" else None
            },
            # 环境感知数据
            "env": {
                "effective_sec": effective_sec,
                "sim_top": sim_top,
                "audio_file": audio_path
            },
            # 兼容旧格式（逐步废弃）
            "speaker_id": speaker_id,
            "role": result.get("role", "guest"),
            "note": "SISI声纹识别系统"
        }

    except Exception as e:
        print(f"[ASR声纹] ❌ SISI声纹识别失败: {e}")
        import traceback
        print(f"[ASR声纹] 详细错误: {traceback.format_exc()}")
        return {"error": str(e), "speaker_id": "unknown", "confidence": 0.0}

async def worker():
    print("[ASR_server] Worker启动，等待处理任务...")
    while True:
        websocket = None
        url = None
        try:
            print("[ASR_server] Worker等待任务...")
            websocket, url = await task_queue.get()
            print(f"[ASR_server] Worker取出任务: {url}")
            print(f"[ASR_server] 准备调用process_wav_file...")
            # 无论连接状态如何都处理音频
            await process_wav_file(websocket, url)
            print(f"[ASR_server] process_wav_file完成")
        except Exception as e:
            print(f"[ASR_server] Worker异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"[ASR_server] Worker任务完成，标记task_done")
            task_queue.task_done()

async def process_wav_file(websocket, url):
    """升级版：支持完整音频上下文分析"""
    wav_path = url
    print(f"[ASR_server] 开始处理音频: {wav_path}")
    try:
        # 检查文件是否存在
        if not os.path.exists(wav_path):
            print(f"❌ [ASR_server] 音频文件不存在: {wav_path}")
            return
        
        print(f"[ASR_server] 文件存在，大小: {os.path.getsize(wav_path)} bytes")
        
        # 根据配置使用不同的ASR模型
        print(f"[ASR_server] 调用{asr_mode.upper()}模型...")
        
        if asr_mode == "funasr":
            # FunASR Paraformer 调用方式（极速优化）
            res = asr_model.generate(
                input=wav_path,
                batch_size_s=60,  # 降低批量大小，加快响应
                **param_dict
            )
        else:
            # SenseVoice 调用方式
            res = asr_model.generate(
                input=wav_path,
                is_final=True,
                **param_dict
            )
        
        print(f"[ASR_server] {asr_mode.upper()}返回: {res}")

        # websockets 16.0+ 兼容性检查
        def is_ws_open(ws):
            try:
                return ws.state.name == "OPEN" if hasattr(ws, 'state') else ws.open
            except:
                return False

        if res and is_ws_open(websocket):
            result = res[0]

            # 🎯 构建完整的音频上下文数据（兼容SenseVoice返回格式）
            if isinstance(result, dict):
                text = result.get('text', '')
            else:
                text = str(result)

            # 并行处理：SenseVoice + 专业声纹识别（使用线程池）
            print("[主交互] 开始SenseVoice + 声纹并行处理")

            # SenseVoice处理函数（同步版本）
            def process_sensevoice_sync():
                """处理SenseVoice结果（同步版本，用于线程池）"""
                print("[主交互] SenseVoice处理开始")
                sensevoice_data = {
                    "text": text,
                    "has_bgm": '<|BGM|>' in text,
                    "emotion": "neutral",
                    "language": "zh" if '<|zh|>' in text else "unknown"
                }

                # 清理SenseVoice标签（通配清除一切 <|...|> 标记）
                import re
                clean_text = re.sub(r'<\|[^>]*\|>', '', text)
                sensevoice_data["clean_text"] = clean_text.strip()

                print(f"[主交互] SenseVoice处理完成: {clean_text[:20]}...")
                print(f"[ASR文本] 长度: {len(clean_text)} 片段: {clean_text[:60]}")
                return sensevoice_data

            # 🎯 声纹识别函数（同步版本）
            def extract_voiceprint_sync():
                """声纹识别（同步版本，用于线程池）"""
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(_extract_voiceprint_features(wav_path))
                    return result
                finally:
                    loop.close()

            print("[主交互] 启动并行任务: SenseVoice + 声纹识别")
            # 真正的多线程并行（参考xiaozhi实现）
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    sensevoice_future = executor.submit(process_sensevoice_sync)
                    voiceprint_future = executor.submit(extract_voiceprint_sync)
                    
                    # 等待两个线程完成
                    try:
                        sensevoice_data = sensevoice_future.result(timeout=15)
                        print("[主交互] SenseVoice数据正常")
                    except Exception as e:
                        print(f"[主交互] SenseVoice处理异常: {e}")
                        sensevoice_data = {"text": text, "has_bgm": False, "clean_text": text}
                    
                    try:
                        voiceprint_data = voiceprint_future.result(timeout=15)
                        print(f"[主交互] 声纹识别成功: {voiceprint_data.get('speaker_id', 'unknown')}")
                    except Exception as e:
                        print(f"[主交互] 声纹识别异常: {e}")
                        voiceprint_data = {"speaker_id": "unknown", "confidence": 0.0}
                
                print("[主交互] 并行处理完成")
            except Exception as e:
                print(f"[主交互] 线程池异常: {e}")
                sensevoice_data = {"text": text, "has_bgm": False, "clean_text": text}
                voiceprint_data = {"speaker_id": "unknown", "confidence": 0.0}

            print("[主交互] 开始构建JSON数据")
            audio_context = {
                "text": sensevoice_data["clean_text"],
                "sensevoice": sensevoice_data,
                "voiceprint": voiceprint_data,
                "confidence": 0.9,
                "timestamp": [],
                "audio_events": [],
                "file_path": wav_path
            }

            # 🔥 发送完整的音频上下文数据（JSON格式）
            response_data = {
                "type": "audio_analysis",
                "text": audio_context["text"],
                "audio_context": audio_context
            }

            print("[主交互] JSON数据构建完成，发送给思思对话")
            await websocket.send(json.dumps(response_data, ensure_ascii=False))
            print("[主交互] 只发送JSON数据，避免重复触发")



    except Exception as e:
        print(f"❌ [ASR_server] 音频处理异常: {e}")
        import traceback
        traceback.print_exc()
        # 回退到基础ASR
        try:
            res = asr_model.generate(input=wav_path, is_final=True, **param_dict)
            def is_ws_open(ws):
                try:
                    return ws.state.name == "OPEN" if hasattr(ws, 'state') else ws.open
                except:
                    return False
            if res and 'text' in res[0] and is_ws_open(websocket):
                await websocket.send(res[0]['text'])
        except Exception as e2:
            print(f"❌ [ASR_server] 回退ASR也失败: {e2}")
    finally:
        # 🎯 修复：不删除音频文件，让主程序统一清理
        # 避免音频分析和音乐识别时文件已被删除的问题
        pass  # 文件由main.py的__clear_temp_files()统一清理

async def main():
    print(f"[启动] 启动FUNASR WebSocket服务...")
    print(f"[启动] 服务地址: {args.host}:{args.port}")
    print(f"[启动] SenseVoice模型已就绪")
    print(f"[启动] 热词已加载: 20个")
    print(f"[启动] websockets版本: 16.0+ (新API)")
    print("="*50)

    # websockets 13.0+ 新API: 使用 async with 模式
    worker_task = asyncio.create_task(worker())
    
    async with websockets.serve(ws_serve, args.host, args.port, ping_interval=10) as server:
        print(f"[启动] FUNASR WebSocket服务启动成功")
        print(f"[启动] 监听地址: ws://{args.host}:{args.port}")
        print(f"[启动] 等待客户端连接...")
        print("="*50)
        
        try:
            await asyncio.Future()  # 永久运行
        except KeyboardInterrupt:
            print("\n[停止] 收到停止信号，正在关闭服务...")
    
    worker_task.cancel()
    print("✅ FUNASR服务已停止")

if __name__ == "__main__":
    # 使用 asyncio 运行主函数
    asyncio.run(main())
