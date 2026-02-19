import importlib
import json
import time
import os
import pyaudio
import re
import uuid
import threading
from queue import Queue, Full, Empty
from flask import Flask, request, jsonify, Response, send_file, make_response, abort, redirect
from flask_cors import CORS
import requests
import datetime
import pytz
import logging
from pathlib import Path

from core import sisi_booter

from tts import tts_voice
from gevent import pywsgi
from scheduler.thread_manager import MyThread
from utils import config_util, util
from core import wsa_server
from core import sisi_core
# 馃毃 content_db宸插垹闄わ紝浣跨敤Mem0璁板繂绯荤粺
from core.interact import Interact
# 馃棏锔?member_db 宸插垹闄わ紝浣跨敤Mem0璁板繂绯荤粺
# from core import member_db
from flask_httpauth import HTTPBasicAuth
from qa import qa_service
from llm import liusisi
from llm import nlp_ollama_api
from gui.multimodal.media_store import MediaStore
from gui.multimodal.input_normalizer import normalize_chat_parts
from llm.multimodal_adapter import (
    build_anthropic_content_parts,
    build_openai_content_parts,
    compose_fallback_text_and_attachments,
)
from ai_module.commands.intent_map import (
    build_client_control_event,
    resolve_intent_from_text,
    validate_intent_execution,
)
from llm.realtime_adapter import (
    build_realtime_turn_policy,
    cleanup_text_buffers,
    create_realtime_client_secret,
    get_realtime_provider_config,
    merge_realtime_session_overrides,
    normalize_realtime_event,
    pop_text_segment_if_ready,
)

__app = Flask(__name__)
# 绂佺敤 Flask 榛樿鏃ュ織
__app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True
# 绂佺敤璇锋眰鏃ュ織涓棿浠?
__app.config['PROPAGATE_EXCEPTIONS'] = True

_NEW_FRONTEND_INDEX = os.path.join(__app.static_folder, "app", "index.html")
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MEDIA_STORE = MediaStore(_APP_ROOT)

def _send_frontend_index():
    resp = make_response(send_file(_NEW_FRONTEND_INDEX))
    resp.headers["Cache-Control"] = "no-store"
    return resp

auth = HTTPBasicAuth()
CORS(__app, supports_credentials=True)

def load_users():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base_dir, "config", "verifier.json"),
        os.path.join(base_dir, "verifier.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}

users = load_users()

@auth.verify_password
def verify_password(username, password):
    if not users or config_util.start_mode == 'common':
        return True
    if username in users and users[username] == password:
        return username

@__app.after_request
def add_header(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    try:
        path = request.path or ""
        if path.startswith("/static/app/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    except Exception:
        pass
    return response

def __get_template():
    try:
        if os.path.exists(_NEW_FRONTEND_INDEX):
            return _send_frontend_index()
        return make_response("frontend not built: run gui/frontend `npm run build` to generate gui/static/app/", 404)
    except Exception as e:
        return f"Error rendering template: {e}", 500

def __get_device_list():
    try:
        if config_util.start_mode == 'common':
            audio = pyaudio.PyAudio()
            device_list = []
            for i in range(audio.get_device_count()):
                devInfo = audio.get_device_info_by_index(i)
                if devInfo['hostApi'] == 0:
                    device_list.append(devInfo["name"])
            return list(set(device_list))
        else:
            return []
    except Exception as e:
        print(f"Error getting device list: {e}")
        return []

_API_V1_SESSIONS = {}
_API_V1_SESSIONS_LOCK = threading.Lock()
_API_V1_REALTIME_TTS_QUEUE_MAXSIZE = 24
_API_V1_REALTIME_TTS_WORKER_COUNT = 2
_API_V1_REALTIME_TTS_QUEUE = Queue(maxsize=_API_V1_REALTIME_TTS_QUEUE_MAXSIZE)
_API_V1_REALTIME_TTS_WORKERS = []
_API_V1_REALTIME_TTS_WORKERS_LOCK = threading.Lock()
_API_V1_REALTIME_SEGMENT_THRESHOLD_DEFAULT = 260
_API_V1_REALTIME_SEGMENT_MIN_DEFAULT = 120


def _api_v1_realtime_tts_worker():
    while True:
        interact = _API_V1_REALTIME_TTS_QUEUE.get()
        try:
            if interact is None:
                return
            sisi_booter.sisi_core.on_interact(interact)
        except Exception as e:
            util.log(2, f"[Realtime] emit_tts_failed: {e}")
        finally:
            _API_V1_REALTIME_TTS_QUEUE.task_done()


def _api_v1_start_realtime_tts_workers():
    if _API_V1_REALTIME_TTS_WORKERS:
        return
    with _API_V1_REALTIME_TTS_WORKERS_LOCK:
        if _API_V1_REALTIME_TTS_WORKERS:
            return
        for idx in range(_API_V1_REALTIME_TTS_WORKER_COUNT):
            worker = threading.Thread(
                target=_api_v1_realtime_tts_worker,
                name=f"realtime-tts-{idx}",
                daemon=True,
            )
            worker.start()
            _API_V1_REALTIME_TTS_WORKERS.append(worker)


def _api_v1_enqueue_realtime_tts(interact):
    _api_v1_start_realtime_tts_workers()
    try:
        _API_V1_REALTIME_TTS_QUEUE.put_nowait(interact)
        return True
    except Full:
        dropped = 0
        while True:
            try:
                _API_V1_REALTIME_TTS_QUEUE.get_nowait()
                _API_V1_REALTIME_TTS_QUEUE.task_done()
                dropped += 1
                break
            except Empty:
                break
        if dropped > 0:
            util.log(
                1,
                f"[Realtime] emit_tts_queue_backpressure dropped={dropped} maxsize={_API_V1_REALTIME_TTS_QUEUE_MAXSIZE}",
            )
        try:
            _API_V1_REALTIME_TTS_QUEUE.put_nowait(interact)
            return True
        except Full:
            util.log(2, "[Realtime] emit_tts_queue_full_drop_latest")
            return False

def _api_v1_chinese_initial(ch):
    """Return pinyin-like initial for CJK using GBK range table (no external deps)."""
    try:
        gbk = ch.encode("gbk")
    except Exception:
        return ""
    if len(gbk) == 1:
        return ch.lower() if ch.isalnum() else ""
    asc = gbk[0] * 256 + gbk[1] - 65536
    if -20319 <= asc <= -20284:
        return "a"
    if -20283 <= asc <= -19776:
        return "b"
    if -19775 <= asc <= -19219:
        return "c"
    if -19218 <= asc <= -18711:
        return "d"
    if -18710 <= asc <= -18527:
        return "e"
    if -18526 <= asc <= -18240:
        return "f"
    if -18239 <= asc <= -17923:
        return "g"
    if -17922 <= asc <= -17418:
        return "h"
    if -17417 <= asc <= -16475:
        return "j"
    if -16474 <= asc <= -16213:
        return "k"
    if -16212 <= asc <= -15641:
        return "l"
    if -15640 <= asc <= -15166:
        return "m"
    if -15165 <= asc <= -14923:
        return "n"
    if -14922 <= asc <= -14915:
        return "o"
    if -14914 <= asc <= -14631:
        return "p"
    if -14630 <= asc <= -14150:
        return "q"
    if -14149 <= asc <= -14091:
        return "r"
    if -14090 <= asc <= -13319:
        return "s"
    if -13318 <= asc <= -12839:
        return "t"
    if -12838 <= asc <= -12557:
        return "w"
    if -12556 <= asc <= -11848:
        return "x"
    if -11847 <= asc <= -11056:
        return "y"
    if -11055 <= asc <= -10247:
        return "z"
    return ""

def _api_v1_build_guild_id():
    try:
        cfg = config_util.read_config_json()
    except Exception:
        cfg = {}
    attr = cfg.get("attribute") or {}
    name = (attr.get("name") or cfg.get("name") or cfg.get("bot_name") or "").strip()
    if not name:
        return "sisi"
    words = re.findall(r"[A-Za-z0-9]+", name)
    if words:
        return "".join([w[0].lower() for w in words])[:8]
    initials = []
    for ch in name:
        initial = _api_v1_chinese_initial(ch)
        if initial:
            initials.append(initial)
    guild_id = re.sub(r"[^a-z0-9]", "", "".join(initials).lower())
    return guild_id[:8] if guild_id else "sisi"

_API_V1_GUILD_ID = _api_v1_build_guild_id()

def _api_v1_trace_id():
    return uuid.uuid4().hex

def _api_v1_ok(data=None, trace_id=None):
    return jsonify({
        "success": True,
        "data": data or {},
        "error": None,
        "trace_id": trace_id or _api_v1_trace_id()
    })

def _api_v1_error(code, message, detail=None, status=400, trace_id=None):
    return jsonify({
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "detail": detail or {}
        },
        "trace_id": trace_id or _api_v1_trace_id()
    }), status

def _api_v1_mask_key(value):
    if not value:
        return ""
    s = str(value)
    if len(s) <= 6:
        return "***"
    return f"{s[:3]}...{s[-3:]}"

def _api_v1_read_system_conf():
    return config_util.system_conf_to_dict(config_util.read_system_conf())

def _api_v1_build_models_url(base_url: str) -> str:
    if not base_url:
        return ""
    url = str(base_url).strip()
    if not url:
        return ""
    if url.endswith("/models"):
        return url
    if url.endswith("/v1") or url.endswith("/v1/"):
        return url.rstrip("/") + "/models"
    return url.rstrip("/") + "/v1/models"

def _api_v1_fetch_provider_models():
    conf = _api_v1_read_system_conf()
    key = conf.get("key", {}) if isinstance(conf, dict) else {}
    base_url = str(key.get("sisi_llm_base_url", "") or "").strip()
    api_key = str(key.get("sisi_llm_api_key", "") or "").strip()
    url = _api_v1_build_models_url(base_url)
    if not url:
        raise ValueError("missing sisi_llm_base_url")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.get(url, headers=headers, timeout=10)
    if not resp.ok:
        raise RuntimeError(f"provider models request failed: {resp.status_code}")
    data = resp.json()
    models = data.get("data") if isinstance(data, dict) else None
    if not isinstance(models, list):
        raise ValueError("provider models response missing data list")
    return models

def _api_v1_write_system_conf(conf_dict):
    config_util.write_system_conf(conf_dict)
    config_util.load_config()

def _api_v1_get_liuye():
    from evoliu.liuye_frontend.intelligent_liuye import get_intelligent_liuye
    return get_intelligent_liuye()

def _api_v1_get_guild():
    from evoliu.guild_supervisor_agent import get_guild_instance
    return get_guild_instance()

def _api_v1_get_memory_system():
    from sisi_memory.sisi_mem0 import SisiMemorySystem
    return SisiMemorySystem()

def _api_v1_get_model_aliases():
    try:
        cfg = config_util.read_config_json()
        aliases = cfg.get("model_aliases", {})
        return aliases if isinstance(aliases, dict) else {}
    except Exception:
        return {}

def _api_v1_resolve_model_alias(model_name):
    if not model_name:
        return model_name
    aliases = _api_v1_get_model_aliases()
    return aliases.get(model_name, model_name)

def _api_v1_set_sisi_llm_model(model_name):
    if not model_name:
        return
    try:
        conf = _api_v1_read_system_conf()
        key = conf.get("key", {})
        key["sisi_llm_model"] = model_name
        conf["key"] = key
        _api_v1_write_system_conf(conf)
    except Exception:
        try:
            config_util.sisi_llm_model = model_name
        except Exception:
            pass

def _api_v1_get_json():
    return request.get_json(silent=True) or {}


def _api_v1_get_multimodal_cfg():
    try:
        return config_util.get_multimodal_config()
    except Exception:
        return {
            "max_image_mb": 20,
            "max_video_mb": 500,
            "max_audio_mb": 80,
            "strategy": "direct_first",
            "allowed_sources": ["local", "url"],
            "retention": "manual_only",
        }


def _api_v1_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _api_v1_media_resolver(file_id):
    item = _MEDIA_STORE.get(file_id)
    return item or {}


def _api_v1_norm_persona(value):
    p = str(value or "").strip().lower()
    return p if p in ("sisi", "liuye") else ""


def _api_v1_sanitize_llm_override(raw):
    if not isinstance(raw, dict):
        return None
    base_url = str(raw.get("base_url") or "").strip().rstrip("/")
    api_key = str(raw.get("api_key") or "").strip()
    model = str(raw.get("model") or "").strip()
    if not base_url or not api_key or not model:
        return None
    api_style = str(raw.get("api_style") or "").strip().lower()
    if api_style not in ("openai", "anthropic"):
        api_style = "anthropic" if model.lower().startswith("claude-") else "openai"
    return {
        "provider_id": str(raw.get("provider_id") or "override").strip() or "override",
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "api_style": api_style,
    }


def _api_v1_build_multimodal_llm_override(persona: str):
    try:
        raw = config_util.get_multimodal_llm_override(persona or "sisi")
    except Exception:
        raw = None
    return _api_v1_sanitize_llm_override(raw)


def _api_v1_get_multimodal_media_public_base() -> str:
    raw = str(config_util.get_value("multimodal_media_public_base_url", "") or "").strip()
    return raw.rstrip("/")


def _api_v1_dispatch_text_interaction(username: str, text: str, *, llm_override=None, llm_user_content_parts=None):
    from core.async_interaction_manager import process_interaction_async

    payload = {"user": username, "msg": text}
    safe_override = _api_v1_sanitize_llm_override(llm_override)
    route = "persona_default"
    provider_id = ""
    if safe_override:
        payload["llm_override"] = safe_override
        route = "multimodal_override"
        provider_id = safe_override.get("provider_id", "")
    if isinstance(llm_user_content_parts, list) and llm_user_content_parts:
        payload["llm_user_content_parts"] = llm_user_content_parts

    interact = Interact("text", 1, payload)
    route_suffix = f" route={route}" + (f" provider={provider_id}" if provider_id else "")
    util.printInfo(1, username, f"[v1.chat]{route_suffix} {text}", time.time())
    is_interrupt = any(k in text.lower() for k in ["别说", "停止", "打断", "不要", "stop"])
    priority = "high" if is_interrupt else "normal"
    ok = process_interaction_async(interact, priority)
    if not ok:
        raise RuntimeError("failed to enqueue interaction")


def _api_v1_emit_realtime_tts(username: str, text: str, *, provider: str = "", session_id: str = "") -> bool:
    content = str(text or "").strip()
    if not content:
        return False
    payload = {
        "user": str(username or "User").strip() or "User",
        "text": content,
        "audio": "",
        "source": "realtime",
        "provider": str(provider or "").strip().lower(),
        "session_id": str(session_id or "").strip(),
    }
    interact = Interact("transparent_pass", 2, payload)
    return _api_v1_enqueue_realtime_tts(interact)

@__app.route('/api/submit', methods=['post'])
def api_submit():
    try:
        data = request.get_json() if request.is_json else request.form.get('data')
        if not data:
            return jsonify({'result': 'error', 'message': '未提供数据'})
            
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return jsonify({'result': 'error', 'message': '鏃犳晥鐨凧SON鏁版嵁'})
                
        if 'config' not in data:
            return jsonify({'result': 'error', 'message': '鏁版嵁涓己灏慶onfig'})

        config_util.load_config()
        existing_config = config_util.config
        
        def merge_configs(existing, new):
            for key, value in new.items():
                if isinstance(value, dict) and key in existing:
                    if isinstance(existing[key], dict):
                        merge_configs(existing[key], value)
                    else:
                        existing[key] = value
                else:
                    existing[key] = value

        merge_configs(existing_config, data['config'])
        config_util.save_config(existing_config)
        config_util.load_config()
        
        response = make_response(jsonify({'result': 'successful'}))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        return response
        
    except Exception as e:
        return jsonify({'result': 'error', 'message': f'淇濆瓨閰嶇疆鏃跺嚭閿? {str(e)}'}), 500

@__app.route('/api/get-data', methods=['post'])
def api_get_data():
    # 鑾峰彇閰嶇疆鍜岃闊冲垪琛?
    try:
        config_util.load_config()
        voice_list = [
            {"id": "sisi", "name": "思思", "voice_uri": config_util.sisi_voice_uri},
            {"id": "liuye", "name": "柳叶", "voice_uri": config_util.liuye_voice_uri}
        ]
        # siliconflow 不发送完整音色列表，这里仅回传当前选择
        wsa_server.get_web_instance().add_cmd({"deviceList": __get_device_list()})
        if sisi_booter.is_running():
            wsa_server.get_web_instance().add_cmd({"liveState": 1})
        return json.dumps({'config': config_util.config, 'voice_list': voice_list})
    except Exception as e:
        return jsonify({'result': 'error', 'message': f'鑾峰彇鏁版嵁鏃跺嚭閿? {e}'}), 500


@__app.route('/api/tts/voices', methods=['get', 'post'])
def api_tts_voices():
    """
    GET: 返回当前思思/柳叶音色
    POST: 更新思思/柳叶音色（role + voice_uri 或直接传 sisi_voice_uri/liuye_voice_uri）
    """
    try:
        if request.method == 'GET':
            config_util.load_config()
            return jsonify({
                "sisi_voice_uri": config_util.sisi_voice_uri,
                "liuye_voice_uri": config_util.liuye_voice_uri
            })

        data = _api_v1_get_json()
        if not isinstance(data, dict):
            return jsonify({'result': 'error', 'message': 'payload must be object'}), 400

        updates = {}
        role = data.get("role")
        voice_uri = data.get("voice_uri")
        if role and voice_uri:
            role = str(role).strip().lower()
            if role not in ("sisi", "liuye"):
                return jsonify({'result': 'error', 'message': 'role must be sisi|liuye'}), 400
            updates[f"{role}_voice_uri"] = voice_uri
        else:
            if "sisi_voice_uri" in data:
                updates["sisi_voice_uri"] = data.get("sisi_voice_uri")
            if "liuye_voice_uri" in data:
                updates["liuye_voice_uri"] = data.get("liuye_voice_uri")

        if not updates:
            return jsonify({'result': 'error', 'message': 'missing voice updates'}), 400

        # 更新 system.conf（保留注释）
        config_util.update_system_conf_keys(updates, section="key")
        config_util.load_config()

        # 同步当前模式音色到运行态
        try:
            from llm import liusisi as liusisi_module
            current_mode = liusisi_module.get_current_system_mode()
        except Exception:
            current_mode = "sisi"
        try:
            from utils import voice_policy
            voice_policy.apply_voice_for_mode(current_mode)
        except Exception:
            pass

        return jsonify({
            "result": "successful",
            "sisi_voice_uri": config_util.sisi_voice_uri,
            "liuye_voice_uri": config_util.liuye_voice_uri,
            "current_mode": current_mode
        })
    except Exception as e:
        return jsonify({'result': 'error', 'message': f'update tts voices failed: {str(e)}'}), 500


@__app.route('/api/config/all', methods=['get', 'post'])
def api_config_all():
    try:
        if request.method == 'GET':
            config_json = config_util.read_config_json()
            system_conf = config_util.system_conf_to_dict(config_util.read_system_conf())
            resp = make_response(jsonify({'config_json': config_json, 'system_conf': system_conf}))
            resp.headers['Cache-Control'] = 'no-store'
            return resp

        data = request.get_json() if request.is_json else request.form.get('data')
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return jsonify({'result': 'error', 'message': 'invalid json'}), 400

        if not isinstance(data, dict):
            return jsonify({'result': 'error', 'message': 'payload must be object'}), 400

        if 'config_json' not in data or 'system_conf' not in data:
            return jsonify({'result': 'error', 'message': 'missing config_json or system_conf'}), 400

        config_util.write_config_json(data['config_json'])
        config_util.write_system_conf(data['system_conf'])
        config_util.load_config()

        resp = make_response(jsonify({'result': 'successful'}))
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    except Exception as e:
        return jsonify({'result': 'error', 'message': f'config all failed: {str(e)}'}), 500

@__app.route('/api/start-live', methods=['post'])
def api_start_live():
    # 鍚姩
    try:
        sisi_booter.start()
        time.sleep(1)
        wsa_server.get_web_instance().add_cmd({"liveState": 1})
        return '{"result":"successful"}'
    except Exception as e:
        return jsonify({'result': 'error', 'message': f'鍚姩鏃跺嚭閿? {e}'}), 500

@__app.route('/api/stop-live', methods=['post'])
def api_stop_live():
    # 鍋滄
    try:
        sisi_booter.stop()
        time.sleep(1)
        wsa_server.get_web_instance().add_cmd({"liveState": 0})
        return '{"result":"successful"}'
    except Exception as e:
        return jsonify({'result': 'error', 'message': f'鍋滄鏃跺嚭閿? {e}'}), 500

@__app.route('/api/send', methods=['post'])
def api_send():
    """
    鐢ㄦ埛鏂囧瓧杈撳叆鎺ュ彛

    鍔熻兘锛氭帴鏀跺墠绔彂閫佺殑鏂囧瓧娑堟伅锛屽紓姝ュ鐞嗙敤鎴蜂氦浜?
    浼樺厛绾э細normal (鏅€氱敤鎴疯緭鍏?

    璇锋眰鏍煎紡锛?
    {
        "username": "User",
        "msg": "鐢ㄦ埛杈撳叆鐨勬秷鎭?
    }

    杩斿洖鏍煎紡锛?
    {
        "result": "successful"
    }
    """
    # 鎺ユ敹鍓嶇鍙戦€佺殑娑堟伅
    data = request.values.get('data')
    if not data:
        return jsonify({'result': 'error', 'message': '未提供数据'})

    try:
        info = json.loads(data)
        username = info.get('username')
        msg = info.get('msg')

        if not username or not msg:
            return jsonify({'result': 'error', 'message': '鐢ㄦ埛鍚嶅拰娑堟伅鍐呭涓嶈兘涓虹┖'})

        # 鍒涘缓浜や簰瀵硅薄
        interact = Interact("text", 1, {'user': username, 'msg': msg})
        util.printInfo(1, username, '[鏂囧瓧鍙戦€佹寜閽甝{}'.format(interact.data["msg"]), time.time())

        # 馃幆 浣跨敤缁熶竴寮傛绠＄悊鍣ㄥ鐞?
        from core.async_interaction_manager import process_interaction_async

        # 妫€鏌ユ槸鍚︿负鎵撴柇鎸囦护锛岃缃珮浼樺厛绾?
        is_interrupt = any(keyword in msg.lower() for keyword in ["别唱了", "停止", "打断", "不要"])
        priority = "high" if is_interrupt else "normal"

        success = process_interaction_async(interact, priority)

        if success:
            return '{"result":"successful"}'
        else:
            return jsonify({'result': 'error', 'message': '澶勭悊闃熷垪宸叉弧锛岃绋嶅悗閲嶈瘯'})

    except json.JSONDecodeError:
        return jsonify({'result': 'error', 'message': '鏃犳晥鐨凧SON鏁版嵁'})
    except Exception as e:
        return jsonify({'result': 'error', 'message': f'鍙戦€佹秷鎭椂鍑洪敊: {e}'}), 500

# 鑾峰彇鎸囧畾鐢ㄦ埛鐨勬秷鎭褰?
def _api_get_msg_parse_payload():
    data = request.form.get("data")
    if data is None:
        payload = request.get_json(silent=True)
    else:
        payload = json.loads(data)
    if isinstance(payload, dict):
        return payload
    return {}


def _api_get_msg_as_int(value, default=200, min_value=1, max_value=1000):
    try:
        n = int(value)
    except Exception:
        n = int(default)
    if n < min_value:
        return min_value
    if n > max_value:
        return max_value
    return n


def _api_get_msg_tail_lines(path: Path, max_lines: int):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if max_lines <= 0:
            return []
        return lines[-max_lines:]
    except Exception:
        return []


def _api_get_msg_guess_latest_user_id(history_root: Path):
    latest_user_id = "default_user"
    latest_mtime = -1.0
    try:
        for user_dir in history_root.iterdir():
            if not user_dir.is_dir():
                continue
            for event_file in user_dir.glob("events-*.jsonl"):
                try:
                    mtime = float(event_file.stat().st_mtime)
                except Exception:
                    continue
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_user_id = user_dir.name
    except Exception:
        return "default_user"
    return latest_user_id


def _api_get_msg_resolve_user_id(payload: dict, history_root: Path):
    unknown_tokens = {"", "0", "none", "null", "unknown", "stranger", "user"}
    for key in ("canonical_user_id", "user_id", "username"):
        value = str(payload.get(key) or "").strip()
        if value and value.lower() not in unknown_tokens:
            return value
    try:
        current_user = str(getattr(sisi_booter.sisi_core, "current_user_id", "") or "").strip()
        if current_user and current_user.lower() not in unknown_tokens:
            return current_user
    except Exception:
        pass
    return _api_get_msg_guess_latest_user_id(history_root)


def _api_get_msg_build_history_root():
    try:
        from sisi_memory.chat_history import load_history_settings

        settings = load_history_settings()
        root = Path(settings.history_root_dir)
    except Exception:
        root = Path(_APP_ROOT) / "sisi_memory" / "data" / "chat_history"
    return root


def _api_get_msg_load_recent_messages(history_root: Path, canonical_user_id: str, limit: int, system_filter: str = ""):
    user_dir = history_root / canonical_user_id
    if not user_dir.exists():
        return []

    event_files = sorted(user_dir.glob("events-*.jsonl"))
    if not event_files:
        return []

    max_scan_lines = max(800, int(limit) * 10)
    collected_lines = []
    for event_file in reversed(event_files):
        if len(collected_lines) >= max_scan_lines:
            break
        collected_lines.extend(_api_get_msg_tail_lines(event_file, max_scan_lines))

    items = []
    for line in collected_lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        role = str(obj.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        system_id = str(obj.get("mode") or obj.get("system_id") or "sisi").strip().lower()
        if system_id not in ("sisi", "liuye"):
            system_id = "sisi"
        if system_filter and system_id != system_filter:
            continue
        text = obj.get("text")
        if text is None:
            text = obj.get("content")
        content = str(text or "").strip()
        if not content:
            continue
        try:
            ts = float(obj.get("ts") or obj.get("timestamp") or time.time())
        except Exception:
            ts = time.time()
        meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else {}
        try:
            created_at = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()
        except Exception:
            created_at = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
        items.append(
            {
                "id": str(obj.get("event_id") or f"evt_{int(ts * 1000)}"),
                "turn_id": str(obj.get("turn_id") or ""),
                "system_id": system_id,
                "role": role,
                "content": content,
                "created_at": created_at,
                "created_ts": ts,
                "source": str(obj.get("source") or "history"),
                "trace_id": str(obj.get("trace_id") or ""),
                "meta": meta,
            }
        )

    items.sort(key=lambda x: float(x.get("created_ts") or 0.0))
    if len(items) > limit:
        items = items[-limit:]
    return items


def _api_get_msg_to_legacy_item(item: dict, default_username: str):
    ts = float(item.get("created_ts") or time.time())
    timezone = pytz.timezone("Asia/Shanghai")
    timetext = datetime.datetime.fromtimestamp(ts, timezone).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    role = str(item.get("role") or "")
    system_id = str(item.get("system_id") or "sisi")
    legacy_type = "member" if role == "user" else system_id
    username = str((item.get("meta") or {}).get("speaker_name") or default_username)
    return {
        "type": legacy_type,
        "way": "text",
        "content": item.get("content") or "",
        "createtime": ts,
        "timetext": timetext,
        "username": username,
        "id": item.get("id") or "",
        "is_adopted": 0,
        "role": role,
        "system_id": system_id,
        "created_at": item.get("created_at") or "",
        "meta": item.get("meta") or {},
    }


@__app.route('/api/get-msg', methods=['post'])
def api_get_Msg():
    try:
        payload = _api_get_msg_parse_payload()
        limit = _api_get_msg_as_int(payload.get("limit"), default=240, min_value=1, max_value=2000)
        system_filter = str(payload.get("system_id") or payload.get("mode") or "").strip().lower()
        if system_filter not in ("", "sisi", "liuye"):
            system_filter = ""

        history_root = _api_get_msg_build_history_root()
        canonical_user_id = _api_get_msg_resolve_user_id(payload, history_root)
        messages = _api_get_msg_load_recent_messages(
            history_root=history_root,
            canonical_user_id=canonical_user_id,
            limit=limit,
            system_filter=system_filter,
        )

        systems = {"sisi": [], "liuye": []}
        for msg in messages:
            cleaned = {k: v for k, v in msg.items() if k != "created_ts"}
            sid = str(cleaned.get("system_id") or "sisi")
            if sid not in systems:
                sid = "sisi"
                cleaned["system_id"] = sid
            systems[sid].append(cleaned)

        legacy_list = [_api_get_msg_to_legacy_item(msg, canonical_user_id) for msg in messages]

        if sisi_booter.is_running():
            wsa_server.get_web_instance().add_cmd({"liveState": 1})

        return jsonify(
            {
                "result": "successful",
                "user_id": canonical_user_id,
                "count": len(messages),
                "list": legacy_list,
                "messages": [x for xs in systems.values() for x in xs],
                "systems": systems,
            }
        )
    except json.JSONDecodeError:
        return jsonify({"result": "error", "list": [], "message": "invalid json payload"}), 400
    except Exception as e:
        return jsonify({"result": "error", "list": [], "message": f"get-msg failed: {e}"}), 500
@__app.route('/api/system/mode', methods=['post'])
def api_set_system_mode():
    """切换系统模式：sisi / liuye"""
    try:
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode") or "").strip().lower()
        if mode not in ("sisi", "liuye"):
            return jsonify({"result": "error", "message": "mode must be sisi|liuye"}), 400
        try:
            from llm import liusisi as liusisi_module
            liusisi_module.set_system_mode(mode)
            current_mode = liusisi_module.get_current_system_mode()
        except Exception as e:
            return jsonify({"result": "error", "message": f"set mode failed: {e}"}), 500
        return jsonify({"result": "successful", "mode": current_mode})
    except Exception as e:
        return jsonify({"result": "error", "message": f"set mode failed: {e}"}), 500

@__app.route('/v1/models', methods=['get'])
def api_v1_models():
    """
    OpenAI鍏煎鐨勬ā鍨嬪垪琛ㄦ帴鍙?
    WebUI闇€瑕佽繖涓帴鍙ｆ潵鑾峰彇鍙敤妯″瀷
    """
    try:
        raw_models = _api_v1_fetch_provider_models()
        models = []
        seen = set()
        for m in raw_models:
            if not isinstance(m, dict):
                continue
            model_id = str(m.get("id", "")).strip()
            if not model_id or model_id in seen:
                continue
            model = dict(m)
            if not model.get("name"):
                display_name = str(model.get("display_name", "") or "").strip()
                model["name"] = display_name or model_id
            models.append(model)
            seen.add(model_id)

        # Do not inject local aliases into provider model list
    except Exception as e:
        return jsonify({
            "error": "MODEL_LIST_ERROR",
            "message": str(e)
        }), 502
    return jsonify({
        "object": "list",
        "data": models
    })

@__app.route('/v1/chat/completions', methods=['post'])
@__app.route('/api/send/v1/chat/completions', methods=['post'])
def api_send_v1_chat_completions():
    """
    OpenAI兼容聊天接口（统一主链）。
    根据 model 映射 persona（sisi/liuye），统一入队到 SmartSisi 核心路由。
    文本默认走各persona自有LLM，多模态在检测到媒体块时才启用 llm_override。
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '未提供数据'})
    try:
        # 瑙ｆ瀽娑堟伅
        last_content = ""
        has_multimodal_media = False
        llm_override = None
        llm_user_content_parts = None
        if 'messages' in data and data['messages']:
            last_message = data['messages'][-1]
            username = last_message.get('role', 'User')
            if username == 'user':
                username = 'User'
            raw_content = last_message.get('content', 'No content provided')
            if isinstance(raw_content, list):
                parts = []
                mm_blocks = []
                for p in raw_content:
                    if isinstance(p, dict):
                        ptype = str(p.get("type") or "").strip().lower()
                        if ptype == "text":
                            text_block = str(p.get("text") or "").strip()
                            if text_block:
                                parts.append(text_block)
                                mm_blocks.append({"type": "text", "text": text_block})
                        elif ptype in ("image_url", "image"):
                            parts.append("[image]")
                            image_block = None
                            if ptype == "image_url":
                                image_payload = p.get("image_url") if isinstance(p.get("image_url"), dict) else {}
                                image_url = str(image_payload.get("url") or "").strip()
                                if image_url:
                                    image_block = {"type": "image_url", "image_url": {"url": image_url}}
                                    detail = str(image_payload.get("detail") or "").strip()
                                    if detail:
                                        image_block["image_url"]["detail"] = detail
                            else:
                                src = p.get("source") if isinstance(p.get("source"), dict) else {}
                                src_type = str(src.get("type") or "").strip().lower()
                                if src_type == "url":
                                    image_url = str(src.get("url") or "").strip()
                                    if image_url:
                                        image_block = {"type": "image_url", "image_url": {"url": image_url}}
                                elif src_type == "base64":
                                    media_type = str(src.get("media_type") or "").strip()
                                    b64_data = str(src.get("data") or "").strip()
                                    if media_type and b64_data:
                                        image_block = {
                                            "type": "image_url",
                                            "image_url": {"url": f"data:{media_type};base64,{b64_data}"},
                                        }
                            if image_block:
                                has_multimodal_media = True
                                mm_blocks.append(image_block)
                        elif ptype in ("video", "video_url"):
                            parts.append("[video]")
                            has_multimodal_media = True
                            mm_blocks.append({"type": "text", "text": "[video]"})
                last_content = " ".join([x for x in parts if x]).strip() or "No content provided"
                if has_multimodal_media and mm_blocks:
                    llm_user_content_parts = mm_blocks
            elif isinstance(raw_content, dict):
                last_content = str(raw_content.get("text") or raw_content.get("content") or "").strip() or "No content provided"
            else:
                last_content = str(raw_content or "No content provided")
        else:
            last_content = 'No messages found'
            username = 'User'

        model = data.get('model', 'sisi')
        resolved_model = _api_v1_resolve_model_alias(model)
        persona = "liuye" if str(model).startswith("liuye") else "sisi"
        # alias resolution is internal; avoid noisy logs in UI-facing output
        observation = data.get('observation', '')
        stream = data.get('stream', False)

        if has_multimodal_media:
            llm_override = _api_v1_build_multimodal_llm_override(persona)
            if not llm_override:
                return jsonify({'error': 'MULTIMODAL_LLM_UNAVAILABLE'}), 503

        try:
            current_mode = _api_v1_norm_persona(liusisi.get_current_system_mode()) or "sisi"
            if persona != current_mode:
                liusisi.set_system_mode(persona)
        except Exception:
            pass
         
        util.printInfo(1, username, f'[API] model={model}, msg={last_content}', time.time())
        try:
            util.log(
                1,
                f"[API] path={request.path}, stream={stream}, model={model}, persona={persona}, "
                f"multimodal={has_multimodal_media}, override={'on' if llm_override else 'off'}",
            )
        except Exception:
            pass

        if persona == "sisi" and resolved_model and model not in ("sisi", "sisi-streaming", "default"):
            _api_v1_set_sisi_llm_model(resolved_model)

        return _handle_sisi_request(
            username,
            last_content,
            observation,
            stream,
            model,
            llm_override=llm_override,
            llm_user_content_parts=llm_user_content_parts,
        )
            
    except Exception as e:
        util.log(2, f"[API] request error: {e}")
        return jsonify({'error': f'澶勭悊璇锋眰鏃跺嚭閿? {e}'}), 500


def _handle_sisi_request(username, msg, observation, stream, model, llm_override=None, llm_user_content_parts=None):
    """统一主链处理请求（按当前系统模式在核心层路由到 sisi/liuye）。"""
    # 馃敟 鏍囪涓篧ebUI璋冪敤锛屽己鍒跺惎鐢═TS鎾斁
    payload = {
        'user': username, 
        'msg': msg, 
        'observation': str(observation),
        'from_webui': True  # mark WebUI-origin for TTS
    }
    safe_override = _api_v1_sanitize_llm_override(llm_override)
    if safe_override:
        payload["llm_override"] = safe_override
    if isinstance(llm_user_content_parts, list) and llm_user_content_parts:
        payload["llm_user_content_parts"] = llm_user_content_parts
    interact = Interact("text", 1, payload)
    
    if stream or model == 'sisi-streaming':
        # WebUI/ws_only 娴佸紡妗ユ帴宸茬Щ闄わ細缁熶竴闄嶇骇涓衡€滈潪娴佸紡寮傛澶勭悊鈥濓紝閬垮厤鍚姩/渚濊禆 WebUI銆?
        import threading

        def async_process():
            try:
                if hasattr(sisi_booter.sisi_core, "_skip_next_tts"):
                    sisi_booter.sisi_core._skip_next_tts = False
                sisi_booter.sisi_core.on_interact(interact)
            except Exception as e:
                util.log(2, f"[寮傛澶勭悊] Sisi澶勭悊寮傚父: {str(e)}")

        threading.Thread(target=async_process, daemon=True).start()
        return non_streaming_response(msg, "姝ｅ湪澶勭悊鎮ㄧ殑璇锋眰锛岃绋嶇瓑...")

    else:
        # 闈炴祦寮?- 寮傛澶勭悊
        import threading
        def async_process():
            try:
                # 馃敟 娓呴櫎鍙兘娈嬬暀鐨勮烦杩囨爣璁?
                if hasattr(sisi_booter.sisi_core, '_skip_next_tts'):
                    sisi_booter.sisi_core._skip_next_tts = False
                sisi_booter.sisi_core.on_interact(interact)
            except Exception as e:
                util.log(2, f"[寮傛澶勭悊] Sisi澶勭悊寮傚父: {str(e)}")

        thread = threading.Thread(target=async_process, daemon=True)
        thread.start()
        return non_streaming_response(msg, "姝ｅ湪澶勭悊鎮ㄧ殑璇锋眰锛岃绋嶇瓑...")

@__app.route('/api/get-member-list', methods=['post'])
def api_get_Member_list():
    # 鑾峰彇鎴愬憳鍒楄〃
    try:
        # 馃棏锔?member_db 宸插垹闄わ紝杩斿洖绌哄垪琛?
        list = []  # 浣跨敤Mem0璁板繂绯荤粺锛屼笉鍐嶇淮鎶ょ敤鎴峰垪琛?
        return json.dumps({'list': list})
    except Exception as e:
        return jsonify({'list': [], 'message': f'鑾峰彇鎴愬憳鍒楄〃鏃跺嚭閿? {e}'}), 500

@__app.route('/api/get_run_status', methods=['post'])
def api_get_run_status():
    # 鑾峰彇杩愯鐘舵€?
    try:
        status = sisi_booter.is_running()
        return json.dumps({'status': status})
    except Exception as e:
        return jsonify({'status': False, 'message': f'鑾峰彇杩愯鐘舵€佹椂鍑洪敊: {e}'}), 500

@__app.route('/api/v1/transport/status', methods=['get'])
def api_v1_transport_status():
    try:
        return _api_v1_ok({
            "running": bool(sisi_booter.is_running()),
            "transport": sisi_booter.get_transport_runtime_status(),
        })
    except Exception as e:
        return _api_v1_error("TRANSPORT_STATUS_ERROR", str(e), status=500)

@__app.route('/api/adopt_msg', methods=['POST'])
def adopt_msg():
    # 閲囩撼娑堟伅
    data = request.get_json()
    if not data:
        return jsonify({'status':'error', 'msg': '未提供数据'})

    id = data.get('id')

    if not id:
        return jsonify({'status':'error', 'msg': 'id涓嶈兘涓虹┖'})

    if  config_util.config["interact"]["QnA"] == "":
        return jsonify({'status':'error', 'msg': '璇峰厛璁剧疆Q&A鏂囦欢'})

    try:
        # 馃 浣跨敤Mem0璁板繂绯荤粺鏇夸唬content_db
        info = None  # Mem0璁板繂绯荤粺涓嶄娇鐢ㄤ紶缁烮D鏌ヨ
        content = ''
        if info is not None:
            previous_info = None  # Mem0璁板繂绯荤粺澶勭悊
            previous_content = ''
            result = True  # 榛樿閲囩撼
            if result:
                qa_service.QAService().record_qapair(previous_content, content)
                return jsonify({'status': 'success', 'msg': '閲囩撼鎴愬姛'})
            else:
                return jsonify({'status':'error', 'msg': '閲囩撼澶辫触'}), 500
        else:
            return jsonify({'status':'error', 'msg': '消息未找到'}), 404
    except Exception as e:
        return jsonify({'status':'error', 'msg': f'采纳消息时出错: {e}'}), 500

def stream_response(text, music_info=None):
    """
    澶勭悊娴佸紡鍝嶅簲
    
    Args:
        text: 鍝嶅簲鏂囨湰
        music_info: 闊充箰淇℃伅瀛楀吀 {"playing": bool, "song": str}
    """
    def generate():
        # 馃幍 濡傛灉鏈夐煶涔愪俊鎭紝鍦ㄧ涓€涓猚hunk涓彂閫?
        first_chunk = True
        
        for chunk in text_chunks(text):
            delta = {"content": chunk}
            
            # 馃幍 鍦ㄧ涓€涓猚hunk涓坊鍔犻煶涔愬姩鐢荤姸鎬?
            if first_chunk and music_info:
                delta["music_animation"] = {
                    "playing": music_info.get("playing", False),
                    "song": music_info.get("song", "")
                }
                first_chunk = False
            
            message = {
                "id": "chatcmpl-8jqorq6Fw1Vi5XoH7pddGGpQeuPe0",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "sisi-streaming",
                "choices": [
                    {
                        "delta": delta,
                        "index": 0,
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(message)}\n\n"
            time.sleep(0.1)
        yield 'data: [DONE]\n\n'
    
    return Response(generate(), mimetype='text/event-stream')

def non_streaming_response(last_content, text):
    # 澶勭悊闈炴祦寮忓搷搴?
    return jsonify({
        "id": "chatcmpl-8jqorq6Fw1Vi5XoH7pddGGpQeuPe0",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "sisi",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text
                },
                "logprobs": "",
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(last_content),
            "completion_tokens": len(text),
            "total_tokens": len(last_content) + len(text)
        },
        "system_fingerprint": "fp_04de91a479"
    })

def text_chunks(text, chunk_size=20):
    pattern = r'([^.!?;:锛屻€傦紒锛焆+[.!?;:锛屻€傦紒锛焆?)'
    chunks = re.findall(pattern, text)
    for chunk in chunks:
        yield chunk

@__app.route('/api/v1/liuye/health', methods=['get'])
def api_v1_liuye_health():
    try:
        liuye = _api_v1_get_liuye()
        return _api_v1_ok({
            "status": getattr(liuye, "status", "unknown"),
            "version": getattr(liuye, "version", ""),
            "name": getattr(liuye, "name", "liuye")
        })
    except Exception as e:
        return _api_v1_error("LIUYE_UNAVAILABLE", str(e), status=503)

@__app.route('/api/v1/liuye/session', methods=['post'])
def api_v1_liuye_session_create():
    data = _api_v1_get_json()
    session_id = data.get("session_id") or uuid.uuid4().hex
    session = {
        "session_id": session_id,
        "created_at": time.time(),
        "user_id": data.get("user_id") or "default",
        "messages": data.get("messages") or [],
        "metadata": data.get("metadata") or {}
    }
    with _API_V1_SESSIONS_LOCK:
        _API_V1_SESSIONS[session_id] = session
    return _api_v1_ok(session)

@__app.route('/api/v1/liuye/session/<session_id>', methods=['get'])
def api_v1_liuye_session_get(session_id):
    with _API_V1_SESSIONS_LOCK:
        session = _API_V1_SESSIONS.get(session_id)
    if not session:
        return _api_v1_error("SESSION_NOT_FOUND", "session not found", status=404)
    return _api_v1_ok(session)

@__app.route('/api/v1/liuye/session/<session_id>/turn', methods=['post'])
def api_v1_liuye_session_turn(session_id):
    data = _api_v1_get_json()
    with _API_V1_SESSIONS_LOCK:
        session = _API_V1_SESSIONS.get(session_id)
    if not session:
        return _api_v1_error("SESSION_NOT_FOUND", "session not found", status=404)

    messages = data.get("messages") or session.get("messages") or []
    input_text = data.get("input")
    if not input_text and messages:
        last = messages[-1]
        if isinstance(last, dict):
            input_text = last.get("content")

    if not input_text:
        return _api_v1_error("MISSING_INPUT", "missing input or messages")

    try:
        liuye = _api_v1_get_liuye()
        reply = liuye.process_user_input(str(input_text))
    except Exception as e:
        return _api_v1_error("LIUYE_ERROR", str(e), status=500)

    session_update = [
        {"role": "user", "content": input_text},
        {"role": "assistant", "content": reply}
    ]
    with _API_V1_SESSIONS_LOCK:
        session = _API_V1_SESSIONS.get(session_id, session)
        session["messages"] = (session.get("messages") or []) + session_update
        _API_V1_SESSIONS[session_id] = session

    if data.get("stream"):
        def generate():
            payload = {
                "type": "reply",
                "data": {
                    "text": reply,
                    "session_id": session_id,
                    "phase": "final"
                }
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return Response(generate(), mimetype="text/event-stream")

    return _api_v1_ok({
        "reply": reply,
        "session_id": session_id
    })

@__app.route('/api/v1/liuye/invoke/<tool_name>', methods=['post'])
def api_v1_liuye_invoke(tool_name):
    data = _api_v1_get_json()
    args = data.get("args") or []
    kwargs = data.get("kwargs") or {}
    try:
        liuye = _api_v1_get_liuye()
        result = liuye.tool_registry.execute(tool_name, *args, **kwargs)
        if result is None:
            return _api_v1_error("TOOL_NOT_FOUND", "tool not found", status=404)
        return _api_v1_ok({"result": result})
    except Exception as e:
        return _api_v1_error("TOOL_ERROR", str(e), status=500)

@__app.route('/api/v1/liuye/tools', methods=['get'])
def api_v1_liuye_tools():
    try:
        liuye = _api_v1_get_liuye()
        tools = liuye.tool_registry.list_tools()
        return _api_v1_ok({"tools": tools})
    except Exception as e:
        return _api_v1_error("LIUYE_ERROR", str(e), status=500)

@__app.route('/api/v1/liuye/tools/<tool_name>/metadata', methods=['get'])
def api_v1_liuye_tool_metadata(tool_name):
    try:
        liuye = _api_v1_get_liuye()
        tools_map = liuye.tool_registry.get_tools_by_category()
        tool = tools_map.get(tool_name)
        if not tool:
            return _api_v1_error("TOOL_NOT_FOUND", "tool not found", status=404)
        return _api_v1_ok({
            "name": tool_name,
            "description": tool.get("description", ""),
            "category": tool.get("category", ""),
            "examples": tool.get("examples", [])
        })
    except Exception as e:
        return _api_v1_error("TOOL_ERROR", str(e), status=500)

@__app.route('/api/v1/liuye/memory/search', methods=['post'])
def api_v1_liuye_memory_search():
    data = _api_v1_get_json()
    query = data.get("query") or ""
    user_id = data.get("user_id") or "default"
    limit = int(data.get("limit") or 5)
    if not query:
        return _api_v1_error("MISSING_QUERY", "missing query")
    try:
        mem = _api_v1_get_memory_system()
        speaker_id = f"liuye::{user_id}"
        items = mem.search_sisi_memory(query, speaker_id=speaker_id, limit=limit)
        return _api_v1_ok({"items": items})
    except Exception as e:
        return _api_v1_error("MEMORY_ERROR", str(e), status=500)

@__app.route('/api/v1/liuye/memory/add', methods=['post'])
def api_v1_liuye_memory_add():
    data = _api_v1_get_json()
    text = data.get("text") or data.get("content")
    user_id = data.get("user_id") or "default"
    response_text = data.get("response") or ""
    if not text:
        return _api_v1_error("MISSING_TEXT", "missing text")
    try:
        mem = _api_v1_get_memory_system()
        speaker_id = f"liuye::{user_id}"
        speaker_info = data.get("speaker_info") or {"mode": "liuye"}
        ok = mem.add_sisi_memory(text, speaker_id=speaker_id, response=response_text, speaker_info=speaker_info)
        return _api_v1_ok({"saved": bool(ok)})
    except Exception as e:
        return _api_v1_error("MEMORY_ERROR", str(e), status=500)

@__app.route('/api/v1/liuye/events/subscribe', methods=['get'])
def api_v1_liuye_events_subscribe():
    try:
        from evoliu.liuye_guild_integration import get_event_bus
        event_type = request.args.get("type") or "guild"
        bus = get_event_bus()
        queue = []
        lock = threading.Lock()

        def _on_event(data):
            with lock:
                queue.append({
                    "type": event_type,
                    "data": data,
                    "ts": time.time()
                })

        bus.subscribe(event_type, _on_event)

        def generate():
            try:
                yield f"data: {json.dumps({'type': 'ready'}, ensure_ascii=False)}\n\n"
                while True:
                    item = None
                    with lock:
                        if queue:
                            item = queue.pop(0)
                    if item:
                        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    else:
                        yield "data: {\"type\":\"ping\"}\n\n"
                        time.sleep(5)
            finally:
                try:
                    bus.unsubscribe(event_type, _on_event)
                except Exception:
                    pass

        return Response(generate(), mimetype="text/event-stream")
    except Exception as e:
        return _api_v1_error("EVENTS_ERROR", str(e), status=500)

@__app.route('/api/v1/models/providers', methods=['get'])
def api_v1_models_providers():
    conf = _api_v1_read_system_conf()
    key = conf.get("key", {})
    providers = []
    for k, v in key.items():
        if not k.endswith("_base_url") or not v:
            continue
        prefix = k[:-len("_base_url")]
        api_key = key.get(f"{prefix}_api_key", "")
        model = key.get(f"{prefix}_model", "") or key.get(f"{prefix}_model_engine", "") or key.get(f"{prefix}_model_path", "")
        providers.append({
            "id": prefix,
            "base_url": v,
            "api_key_set": bool(api_key),
            "api_key_preview": _api_v1_mask_key(api_key),
            "model": model
        })
    return _api_v1_ok({"providers": providers})

@__app.route('/api/v1/models/providers', methods=['post'])
def api_v1_models_providers_create():
    data = _api_v1_get_json()
    provider_id = data.get("id") or data.get("provider_id")
    if not provider_id:
        return _api_v1_error("MISSING_ID", "missing provider id")
    conf = _api_v1_read_system_conf()
    key = conf.get("key", {})
    if "base_url" in data:
        key[f"{provider_id}_base_url"] = data.get("base_url") or ""
    if "api_key" in data:
        key[f"{provider_id}_api_key"] = data.get("api_key") or ""
    if "model" in data:
        key[f"{provider_id}_model"] = data.get("model") or ""
    if "model_engine" in data:
        key[f"{provider_id}_model_engine"] = data.get("model_engine") or ""
    if "model_path" in data:
        key[f"{provider_id}_model_path"] = data.get("model_path") or ""
    conf["key"] = key
    _api_v1_write_system_conf(conf)
    return _api_v1_ok({
        "id": provider_id,
        "base_url": key.get(f"{provider_id}_base_url", ""),
        "api_key_set": bool(key.get(f"{provider_id}_api_key")),
        "api_key_preview": _api_v1_mask_key(key.get(f"{provider_id}_api_key", "")),
        "model": key.get(f"{provider_id}_model", "") or key.get(f"{provider_id}_model_engine", "") or key.get(f"{provider_id}_model_path", "")
    })

@__app.route('/api/v1/models', methods=['get'])
def api_v1_models_list():
    conf = _api_v1_read_system_conf()
    key = conf.get("key", {})
    models = []
    for k, v in key.items():
        if not v:
            continue
        if k.endswith("_model") or k.endswith("_model_engine") or k.endswith("_model_path"):
            models.append({"id": k, "value": v})
    return _api_v1_ok({"models": models})

@__app.route('/api/v1/models', methods=['post'])
def api_v1_models_create():
    data = _api_v1_get_json()
    model_id = data.get("id") or data.get("key")
    value = data.get("model") or data.get("value")
    if not model_id:
        return _api_v1_error("MISSING_ID", "missing model id")
    if value is None:
        return _api_v1_error("MISSING_VALUE", "missing model value")
    conf = _api_v1_read_system_conf()
    key = conf.get("key", {})
    key[str(model_id)] = str(value)
    conf["key"] = key
    _api_v1_write_system_conf(conf)
    return _api_v1_ok({"id": model_id, "value": value})

@__app.route('/api/v1/models/aliases', methods=['get'])
def api_v1_models_aliases():
    try:
        cfg = config_util.read_config_json()
        aliases = cfg.get("model_aliases", {})
        return _api_v1_ok({"aliases": aliases})
    except Exception as e:
        return _api_v1_error("CONFIG_ERROR", str(e), status=500)

@__app.route('/api/v1/models/aliases', methods=['post'])
def api_v1_models_aliases_create():
    data = _api_v1_get_json()
    alias = data.get("alias")
    route = data.get("route") or data.get("value")
    if not alias or route is None:
        return _api_v1_error("MISSING_ALIAS", "missing alias or route")
    cfg = config_util.read_config_json()
    aliases = cfg.get("model_aliases", {})
    aliases[alias] = route
    cfg["model_aliases"] = aliases
    config_util.write_config_json(cfg)
    return _api_v1_ok({"alias": alias, "route": route})

@__app.route('/api/v1/models/aliases/<alias>', methods=['patch'])
def api_v1_models_aliases_update(alias):
    data = _api_v1_get_json()
    route = data.get("route") or data.get("value")
    if route is None:
        return _api_v1_error("MISSING_ROUTE", "missing route")
    cfg = config_util.read_config_json()
    aliases = cfg.get("model_aliases", {})
    if alias not in aliases:
        return _api_v1_error("ALIAS_NOT_FOUND", "alias not found", status=404)
    aliases[alias] = route
    cfg["model_aliases"] = aliases
    config_util.write_config_json(cfg)
    return _api_v1_ok({"alias": alias, "route": route})

@__app.route('/api/v1/models/validate', methods=['post'])
def api_v1_models_validate():
    data = _api_v1_get_json()
    alias = data.get("alias")
    provider_id = data.get("provider_id")
    conf = _api_v1_read_system_conf()
    key = conf.get("key", {})
    if alias:
        cfg = config_util.read_config_json()
        aliases = cfg.get("model_aliases", {})
        ok = alias in aliases
        return _api_v1_ok({"valid": ok, "alias": alias})
    if provider_id:
        ok = bool(key.get(f"{provider_id}_base_url")) and bool(key.get(f"{provider_id}_model") or key.get(f"{provider_id}_model_engine"))
        return _api_v1_ok({"valid": ok, "provider_id": provider_id})
    return _api_v1_error("MISSING_TARGET", "missing alias or provider_id")

@__app.route('/api/v1/models/usage', methods=['get'])
def api_v1_models_usage():
    return _api_v1_ok({"usage": []})

@__app.route('/api/v1/guilds', methods=['get'])
def api_v1_guilds_list():
    try:
        guild = _api_v1_get_guild()
        status = guild.get_status_summary()
        return _api_v1_ok({
            "guilds": [{
                "id": _API_V1_GUILD_ID,
                "name": "adventurers_guild",
                "members": status.get("members", []),
                "running_count": status.get("running_count", 0),
                "pending_count": status.get("pending_count", 0)
            }]
        })
    except Exception as e:
        return _api_v1_error("GUILD_UNAVAILABLE", str(e), status=503)

@__app.route('/api/v1/guilds', methods=['post'])
def api_v1_guilds_create():
    return _api_v1_error("GUILD_SINGLETON", "only one guild is supported", status=409)

@__app.route('/api/v1/guilds/<guild_id>', methods=['get'])
def api_v1_guilds_get(guild_id):
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404)
    try:
        guild = _api_v1_get_guild()
        status = guild.get_status_summary()
        return _api_v1_ok({
            "id": _API_V1_GUILD_ID,
            "name": "adventurers_guild",
            "status": status
        })
    except Exception as e:
        return _api_v1_error("GUILD_UNAVAILABLE", str(e), status=503)

@__app.route('/api/v1/guilds/<guild_id>', methods=['patch'])
def api_v1_guilds_update(guild_id):
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404)
    return _api_v1_error("GUILD_READONLY", "guild config update not supported", status=409)

@__app.route('/api/v1/guilds/<guild_id>/roster', methods=['get'])
def api_v1_guilds_roster(guild_id):
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404)
    try:
        guild = _api_v1_get_guild()
        members = guild.get_members()
        return _api_v1_ok({"members": members})
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/guilds/<guild_id>/roster', methods=['post'])
def api_v1_guilds_roster_add(guild_id):
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404)
    return _api_v1_error("ROSTER_READONLY", "roster update not supported", status=409)

@__app.route('/api/v1/guilds/<guild_id>/quests', methods=['get'])
def api_v1_guilds_quests(guild_id):
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404)
    try:
        guild = _api_v1_get_guild()
        status = request.args.get("status")
        tasks = guild.storage.list_tasks(status=status or None)
        return _api_v1_ok({"quests": tasks})
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/guilds/<guild_id>/quests', methods=['post'])
def api_v1_guilds_quests_create(guild_id):
    trace_id = _api_v1_trace_id()
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404, trace_id=trace_id)
    data = _api_v1_get_json()
    description = data.get("description") or data.get("input")
    member_id = data.get("member_id") or "auto"
    if not description:
        return _api_v1_error("MISSING_DESCRIPTION", "missing description", trace_id=trace_id)
    try:
        guild = _api_v1_get_guild()
        task_id = guild.submit_task(description, member_id=member_id, trace_id=trace_id, source="api")
        task_data = guild.storage.load_task(task_id) or {}
        assigned_to = task_data.get("assigned_to") or member_id
        return _api_v1_ok({"task_id": task_id, "assigned_to": assigned_to}, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500, trace_id=trace_id)

@__app.route('/api/v1/guilds/<guild_id>/match', methods=['post'])
def api_v1_guilds_match(guild_id):
    trace_id = _api_v1_trace_id()
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404, trace_id=trace_id)
    data = _api_v1_get_json()
    description = data.get("description") or data.get("input")
    member_id = data.get("member_id") or "auto"
    if not description:
        return _api_v1_error("MISSING_DESCRIPTION", "missing description", trace_id=trace_id)
    try:
        guild = _api_v1_get_guild()
        task_id = guild.submit_task(description, member_id=member_id, trace_id=trace_id, source="api")
        task_data = guild.storage.load_task(task_id) or {}
        assigned_to = task_data.get("assigned_to") or member_id
        return _api_v1_ok({"task_id": task_id, "assigned_to": assigned_to}, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500, trace_id=trace_id)

@__app.route('/api/v1/guilds/<guild_id>/events', methods=['get'])
def api_v1_guilds_events(guild_id):
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404)
    try:
        from evoliu.liuye_guild_integration import get_event_bus
        event_type = request.args.get("type") or "guild"
        bus = get_event_bus()
        queue = []
        lock = threading.Lock()

        def _on_event(data):
            with lock:
                queue.append({
                    "type": event_type,
                    "data": data,
                    "ts": time.time()
                })

        bus.subscribe(event_type, _on_event)

        def generate():
            try:
                yield f"data: {json.dumps({'type': 'ready'}, ensure_ascii=False)}\n\n"
                while True:
                    item = None
                    with lock:
                        if queue:
                            item = queue.pop(0)
                    if item:
                        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    else:
                        yield "data: {\"type\":\"ping\"}\n\n"
                        time.sleep(5)
            finally:
                try:
                    bus.unsubscribe(event_type, _on_event)
                except Exception:
                    pass

        return Response(generate(), mimetype="text/event-stream")
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/adventurers', methods=['get'])
def api_v1_adventurers_list():
    try:
        guild = _api_v1_get_guild()
        members = guild.get_members()
        return _api_v1_ok({"adventurers": members})
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/adventurers', methods=['post'])
def api_v1_adventurers_create():
    return _api_v1_error("ADVENTURER_READONLY", "adventurer creation not supported", status=409)

@__app.route('/api/v1/adventurers/<adv_id>', methods=['get'])
def api_v1_adventurers_get(adv_id):
    try:
        guild = _api_v1_get_guild()
        member = guild.guild_members.get(adv_id)
        if not member:
            return _api_v1_error("ADVENTURER_NOT_FOUND", "adventurer not found", status=404)
        return _api_v1_ok({
            "id": adv_id,
            "name": member.get("name"),
            "status": member.get("status"),
            "capabilities": member.get("capabilities", []),
            "skills": member.get("skills", {}),
            "tools": member.get("tools", {})
        })
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/adventurers/<adv_id>', methods=['patch'])
def api_v1_adventurers_update(adv_id):
    return _api_v1_error("ADVENTURER_READONLY", "adventurer update not supported", status=409)

@__app.route('/api/v1/adventurers/<adv_id>/status', methods=['get'])
def api_v1_adventurers_status(adv_id):
    try:
        guild = _api_v1_get_guild()
        member = guild.guild_members.get(adv_id)
        if not member:
            return _api_v1_error("ADVENTURER_NOT_FOUND", "adventurer not found", status=404)
        return _api_v1_ok({"id": adv_id, "status": member.get("status", "unknown")})
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/adventurers/<adv_id>/invoke', methods=['post'])
def api_v1_adventurers_invoke(adv_id):
    trace_id = _api_v1_trace_id()
    data = _api_v1_get_json()
    description = data.get("description") or data.get("input")
    if not description:
        return _api_v1_error("MISSING_DESCRIPTION", "missing description", trace_id=trace_id)
    try:
        guild = _api_v1_get_guild()
        if adv_id not in guild.guild_members:
            return _api_v1_error("ADVENTURER_NOT_FOUND", "adventurer not found", status=404, trace_id=trace_id)
        task_id = guild.submit_task(description, member_id=adv_id, trace_id=trace_id, source="api")
        return _api_v1_ok({"task_id": task_id, "assigned_to": adv_id}, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500, trace_id=trace_id)

@__app.route('/api/v1/adventurers/<adv_id>/skills', methods=['get'])
def api_v1_adventurers_skills(adv_id):
    try:
        guild = _api_v1_get_guild()
        member = guild.guild_members.get(adv_id)
        if not member:
            return _api_v1_error("ADVENTURER_NOT_FOUND", "adventurer not found", status=404)
        return _api_v1_ok({"skills": member.get("skills", {})})
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/adventurers/<adv_id>/skills', methods=['post'])
def api_v1_adventurers_skills_add(adv_id):
    return _api_v1_error("SKILLS_READONLY", "skills update not supported", status=409)

@__app.route('/api/v1/adventurers/<adv_id>/memory/search', methods=['post'])
def api_v1_adventurers_memory_search(adv_id):
    data = _api_v1_get_json()
    query = data.get("query") or ""
    user_id = data.get("user_id") or "default"
    limit = int(data.get("limit") or 5)
    if not query:
        return _api_v1_error("MISSING_QUERY", "missing query")
    try:
        mem = _api_v1_get_memory_system()
        speaker_id = f"shared::{user_id}"
        items = mem.search_sisi_memory(query, speaker_id=speaker_id, limit=limit)
        return _api_v1_ok({"items": items})
    except Exception as e:
        return _api_v1_error("MEMORY_ERROR", str(e), status=500)

@__app.route('/api/v1/adventurers/<adv_id>/memory/add', methods=['post'])
def api_v1_adventurers_memory_add(adv_id):
    data = _api_v1_get_json()
    text = data.get("text") or data.get("content")
    user_id = data.get("user_id") or "default"
    response_text = data.get("response") or ""
    if not text:
        return _api_v1_error("MISSING_TEXT", "missing text")
    try:
        mem = _api_v1_get_memory_system()
        speaker_id = f"shared::{user_id}"
        speaker_info = data.get("speaker_info") or {"mode": "liuye"}
        ok = mem.add_sisi_memory(text, speaker_id=speaker_id, response=response_text, speaker_info=speaker_info)
        return _api_v1_ok({"saved": bool(ok)})
    except Exception as e:
        return _api_v1_error("MEMORY_ERROR", str(e), status=500)

@__app.route('/api/v1/adventurers/<adv_id>/sessions', methods=['get'])
def api_v1_adventurers_sessions(adv_id):
    try:
        guild = _api_v1_get_guild()
        tasks = guild.storage.list_tasks()
        sessions = [t for t in tasks if t.get("assigned_to") == adv_id]
        return _api_v1_ok({"sessions": sessions})
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500)

@__app.route('/api/v1/guilds/<guild_id>/dissolve', methods=['post'])
def api_v1_guilds_dissolve(guild_id):
    trace_id = _api_v1_trace_id()
    if guild_id != _API_V1_GUILD_ID:
        return _api_v1_error("GUILD_NOT_FOUND", "guild not found", status=404, trace_id=trace_id)
    data = _api_v1_get_json()
    reason = (data.get("reason") or "API触发强制解散").strip()
    try:
        guild = _api_v1_get_guild()
        result = guild.dissolve_guild(reason)
        if not isinstance(result, dict):
            result = {"success": bool(result)}
        if not result.get("success"):
            return _api_v1_error("GUILD_DISSOLVE_FAILED", result.get("error") or "dissolve failed", status=500, trace_id=trace_id)
        return _api_v1_ok(result, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("GUILD_ERROR", str(e), status=500, trace_id=trace_id)


@__app.route('/api/v1/files/upload', methods=['post'])
def api_v1_files_upload():
    trace_id = _api_v1_trace_id()
    cfg = _api_v1_get_multimodal_cfg()
    if "local" not in (cfg.get("allowed_sources") or []):
        return _api_v1_error("SOURCE_DISABLED", "local upload disabled", status=403, trace_id=trace_id)
    f = request.files.get("file")
    if not f:
        return _api_v1_error("MISSING_FILE", "missing file field", status=400, trace_id=trace_id)
    try:
        item = _MEDIA_STORE.save_upload(
            f,
            max_image_mb=int(cfg.get("max_image_mb", 20)),
            max_video_mb=int(cfg.get("max_video_mb", 500)),
            max_audio_mb=int(cfg.get("max_audio_mb", 80)),
        )
        attachment = MediaStore.to_attachment(item)
        data = {
            "file": {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "mime": item.get("mime"),
                "size": item.get("size"),
                "storage": item.get("storage"),
                "created_at": item.get("created_at"),
            },
            "attachment": attachment,
        }
        return _api_v1_ok(data, trace_id=trace_id)
    except ValueError as e:
        return _api_v1_error("INVALID_FILE", str(e), status=400, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("UPLOAD_ERROR", str(e), status=500, trace_id=trace_id)


@__app.route('/api/v1/files/register-url', methods=['post'])
def api_v1_files_register_url():
    trace_id = _api_v1_trace_id()
    cfg = _api_v1_get_multimodal_cfg()
    if "url" not in (cfg.get("allowed_sources") or []):
        return _api_v1_error("SOURCE_DISABLED", "url source disabled", status=403, trace_id=trace_id)
    payload = _api_v1_get_json()
    url = str(payload.get("url") or "").strip()
    if not url:
        return _api_v1_error("MISSING_URL", "missing url", status=400, trace_id=trace_id)
    try:
        item = _MEDIA_STORE.register_url(
            url=url,
            name=str(payload.get("name") or "").strip(),
            mime=str(payload.get("mime") or "").strip(),
        )
        return _api_v1_ok(
            {
                "file": {
                    "id": item.get("id"),
                    "kind": item.get("kind"),
                    "name": item.get("name"),
                    "mime": item.get("mime"),
                    "size": item.get("size"),
                    "storage": item.get("storage"),
                    "url": item.get("url"),
                    "created_at": item.get("created_at"),
                },
                "attachment": MediaStore.to_attachment(item),
            },
            trace_id=trace_id,
        )
    except ValueError as e:
        return _api_v1_error("INVALID_URL", str(e), status=400, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("REGISTER_URL_ERROR", str(e), status=500, trace_id=trace_id)


@__app.route('/api/v1/files/<file_id>', methods=['get'])
def api_v1_files_get(file_id):
    trace_id = _api_v1_trace_id()
    item = _MEDIA_STORE.get(file_id)
    if not item:
        return _api_v1_error("FILE_NOT_FOUND", "file not found", status=404, trace_id=trace_id)
    return _api_v1_ok(
        {
            "file": {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "mime": item.get("mime"),
                "size": item.get("size"),
                "storage": item.get("storage"),
                "url": item.get("url") if item.get("storage") == "url" else "",
                "created_at": item.get("created_at"),
            },
            "attachment": MediaStore.to_attachment(item),
        },
        trace_id=trace_id,
    )


@__app.route('/api/v1/files/<file_id>', methods=['delete'])
def api_v1_files_delete(file_id):
    trace_id = _api_v1_trace_id()
    ok = _MEDIA_STORE.delete(file_id)
    if not ok:
        return _api_v1_error("FILE_NOT_FOUND", "file not found", status=404, trace_id=trace_id)
    return _api_v1_ok({"deleted": True, "file_id": file_id}, trace_id=trace_id)


@__app.route('/api/v1/media/<file_id>', methods=['get'])
def api_v1_media_get(file_id):
    item = _MEDIA_STORE.get(file_id)
    if not item:
        return jsonify({"error": "FILE_NOT_FOUND"}), 404
    if item.get("storage") == "url":
        target = str(item.get("url") or "").strip()
        if not target:
            return jsonify({"error": "URL_NOT_FOUND"}), 404
        return redirect(target, code=302)
    p = str(item.get("path") or "").strip()
    if not p or not os.path.exists(p):
        return jsonify({"error": "FILE_MISSING"}), 404
    as_download = str(request.args.get("download") or "0").strip() in ("1", "true", "yes")
    return send_file(
        p,
        mimetype=item.get("mime") or "application/octet-stream",
        as_attachment=as_download,
        download_name=item.get("name") or None,
        conditional=True,
    )


@__app.route('/api/v1/realtime/session', methods=['post'])
def api_v1_realtime_session():
    trace_id = _api_v1_trace_id()
    payload = _api_v1_get_json()

    provider = str(payload.get("provider") or config_util.get_value("realtime_provider", "openai") or "openai").strip().lower()
    persona = _api_v1_norm_persona(payload.get("persona") or payload.get("system_id"))
    if not persona:
        try:
            persona = _api_v1_norm_persona(liusisi.get_current_system_mode()) or "sisi"
        except Exception:
            persona = "sisi"

    cfg = get_realtime_provider_config(provider, persona=persona)
    model_override = str(payload.get("model") or "").strip()
    if model_override:
        cfg["model"] = model_override

    try:
        ttl_seconds = int(str(payload.get("ttl_seconds", 300)).strip())
    except Exception:
        ttl_seconds = 300
    ttl_seconds = max(30, min(ttl_seconds, 3600))

    default_issue_secret = provider in ("openai", "grok")
    issue_client_secret = _api_v1_bool(payload.get("issue_client_secret"), default=default_issue_secret)
    server_vad_enabled = _api_v1_bool(
        payload.get("server_vad_enabled"),
        default=_api_v1_bool(config_util.get_value("realtime_server_vad_enabled", "true"), default=True),
    )
    interrupt_response_enabled = _api_v1_bool(
        payload.get("interrupt_response_enabled"),
        default=_api_v1_bool(config_util.get_value("realtime_interrupt_response_enabled", "true"), default=True),
    )
    try:
        vad_threshold = float(
            str(payload.get("vad_threshold", config_util.get_value("realtime_vad_threshold", 0.5))).strip()
        )
    except Exception:
        vad_threshold = 0.5
    vad_threshold = max(0.0, min(vad_threshold, 1.0))

    try:
        vad_prefix_padding_ms = int(
            str(
                payload.get(
                    "vad_prefix_padding_ms",
                    config_util.get_value("realtime_vad_prefix_padding_ms", 300),
                )
            ).strip()
        )
    except Exception:
        vad_prefix_padding_ms = 300
    vad_prefix_padding_ms = max(0, min(vad_prefix_padding_ms, 5000))

    try:
        vad_silence_duration_ms = int(
            str(
                payload.get(
                    "vad_silence_duration_ms",
                    config_util.get_value("realtime_vad_silence_duration_ms", 500),
                )
            ).strip()
        )
    except Exception:
        vad_silence_duration_ms = 500
    vad_silence_duration_ms = max(100, min(vad_silence_duration_ms, 5000))

    session_user_overrides = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    session_defaults = build_realtime_turn_policy(
        provider,
        server_vad_enabled=server_vad_enabled,
        interrupt_response_enabled=interrupt_response_enabled,
        vad_threshold=vad_threshold,
        vad_prefix_padding_ms=vad_prefix_padding_ms,
        vad_silence_duration_ms=vad_silence_duration_ms,
    )
    session_overrides = merge_realtime_session_overrides(session_defaults, session_user_overrides)
    secret = {}

    if issue_client_secret:
        try:
            secret = create_realtime_client_secret(
                cfg,
                ttl_seconds=ttl_seconds,
                session_overrides=session_overrides,
            )
        except Exception as e:
            return _api_v1_error(
                "REALTIME_CLIENT_SECRET_ERROR",
                str(e),
                status=502,
                trace_id=trace_id,
            )

    return _api_v1_ok(
        {
            "provider": cfg.get("provider"),
            "persona": persona,
            "transport": cfg.get("transport"),
            "model": cfg.get("model"),
            "ws_url": cfg.get("ws_url"),
            "auth_mode": cfg.get("auth_mode"),
            "issue_client_secret": issue_client_secret,
            "client_secret": secret,
            "intercept_audio_default": True,
            "text_route": "transparent_pass",
            "session_defaults": session_defaults,
            "session": session_overrides,
            "interrupt_policy": {
                "server_vad_enabled": server_vad_enabled,
                "interrupt_response_enabled": interrupt_response_enabled,
                "vad_threshold": vad_threshold,
                "vad_prefix_padding_ms": vad_prefix_padding_ms,
                "vad_silence_duration_ms": vad_silence_duration_ms,
                "client_interrupt_event": "response.cancel",
            },
            "docs": cfg.get("docs") or [],
        },
        trace_id=trace_id,
    )


@__app.route('/api/v1/realtime/event', methods=['post'])
def api_v1_realtime_event():
    trace_id = _api_v1_trace_id()
    payload = _api_v1_get_json()

    provider = str(payload.get("provider") or config_util.get_value("realtime_provider", "openai") or "openai").strip().lower()
    session_id = str(payload.get("session_id") or "").strip()
    username = str(payload.get("username") or "User").strip() or "User"

    event = payload.get("event")
    if not isinstance(event, dict):
        event = payload if isinstance(payload, dict) else {}

    intercept_audio = _api_v1_bool(payload.get("intercept_audio"), default=True)
    emit_tts_on_done = _api_v1_bool(payload.get("emit_tts_on_done"), default=True)
    emit_tts_on_segment = _api_v1_bool(payload.get("emit_tts_on_segment"), default=True)

    try:
        buffer_ttl_seconds = int(
            str(
                payload.get(
                    "buffer_ttl_seconds",
                    config_util.get_value("realtime_text_buffer_ttl_seconds", 120),
                )
            ).strip()
        )
    except Exception:
        buffer_ttl_seconds = 120
    try:
        segment_threshold_chars = int(
            str(
                payload.get(
                    "segment_threshold_chars",
                    config_util.get_value("realtime_text_segment_threshold_chars", _API_V1_REALTIME_SEGMENT_THRESHOLD_DEFAULT),
                )
            ).strip()
        )
    except Exception:
        segment_threshold_chars = _API_V1_REALTIME_SEGMENT_THRESHOLD_DEFAULT
    try:
        segment_min_chars = int(
            str(
                payload.get(
                    "segment_min_chars",
                    config_util.get_value("realtime_text_segment_min_chars", _API_V1_REALTIME_SEGMENT_MIN_DEFAULT),
                )
            ).strip()
        )
    except Exception:
        segment_min_chars = _API_V1_REALTIME_SEGMENT_MIN_DEFAULT
    segment_threshold_chars = max(40, min(segment_threshold_chars, 8000))
    segment_min_chars = max(20, min(segment_min_chars, segment_threshold_chars))

    cleanup_stats = cleanup_text_buffers(
        provider,
        session_id=session_id,
        ttl_seconds=buffer_ttl_seconds,
    )

    normalized = normalize_realtime_event(provider, event, session_id=session_id)
    tts_enqueued = False
    tts_text = ""
    tts_segment_enqueued = False
    tts_segment_text = ""

    if emit_tts_on_segment and not normalized.get("done"):
        tts_segment_text = pop_text_segment_if_ready(
            provider,
            session_id,
            str(normalized.get("response_id") or ""),
            threshold_chars=segment_threshold_chars,
            min_segment_chars=segment_min_chars,
        )
        if tts_segment_text:
            tts_segment_enqueued = _api_v1_emit_realtime_tts(
                username,
                tts_segment_text,
                provider=provider,
                session_id=session_id,
            )

    if emit_tts_on_done and normalized.get("done"):
        tts_text = str(normalized.get("text_final") or "").strip()
        if tts_text:
            tts_enqueued = _api_v1_emit_realtime_tts(
                username,
                tts_text,
                provider=provider,
                session_id=session_id,
            )

    return _api_v1_ok(
        {
            "normalized": normalized,
            "audio_intercepted": bool(intercept_audio and normalized.get("audio_intercepted")),
            "buffer_cleanup": cleanup_stats,
            "tts_enqueued": tts_enqueued,
            "text_for_tts": tts_text,
            "tts_segment_enqueued": tts_segment_enqueued,
            "text_segment_for_tts": tts_segment_text,
            "segment_threshold_chars": segment_threshold_chars,
            "segment_min_chars": segment_min_chars,
        },
        trace_id=trace_id,
    )


@__app.route('/api/v1/chat/messages', methods=['post'])
def api_v1_chat_messages():
    trace_id = _api_v1_trace_id()
    payload = _api_v1_get_json()
    username = str(payload.get("username") or "User").strip() or "User"
    persona = _api_v1_norm_persona(payload.get("persona") or payload.get("system_id"))
    if not persona:
        try:
            persona = _api_v1_norm_persona(liusisi.get_current_system_mode()) or "sisi"
        except Exception:
            persona = "sisi"

    try:
        parts = normalize_chat_parts(payload, _api_v1_media_resolver)
    except ValueError as e:
        return _api_v1_error("INVALID_PARTS", str(e), status=400, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("INVALID_PARTS", str(e), status=500, trace_id=trace_id)

    try:
        has_multimodal_media = any(
            str((p or {}).get("type") or "").strip().lower() in ("image", "video", "audio")
            for p in (parts or [])
        )
        llm_override = _api_v1_build_multimodal_llm_override(persona) if has_multimodal_media else None
        if has_multimodal_media and not llm_override:
            return _api_v1_error(
                "MULTIMODAL_LLM_UNAVAILABLE",
                "检测到多模态输入，但未配置可用的多模态LLM（multimodal_llm_*）",
                status=503,
                trace_id=trace_id,
            )

        attachments = []
        if has_multimodal_media:
            fused_context = compose_fallback_text_and_attachments(
                parts,
                _api_v1_media_resolver,
                persona=persona,
            )
            dispatch_text = str(fused_context.get("text") or "").strip()
            fused_attachments = fused_context.get("attachments")
            if isinstance(fused_attachments, list):
                attachments = fused_attachments
        else:
            text_parts = []
            for p in (parts or []):
                if str((p or {}).get("type") or "").strip().lower() != "text":
                    continue
                t = str((p or {}).get("text") or "").strip()
                if t:
                    text_parts.append(t)
            dispatch_text = "\n".join(text_parts).strip()

        if not dispatch_text and has_multimodal_media:
            dispatch_text = "多模态输入"
        if not dispatch_text:
            return _api_v1_error("EMPTY_INPUT", "text content is empty after normalization", status=400, trace_id=trace_id)

        # Lightweight intent routing for text commands:
        # LLM may assist understanding, but execution stays deterministic.
        if not has_multimodal_media:
            intent_env = resolve_intent_from_text(dispatch_text, source="text")
            can_execute_intent, deny_reason = validate_intent_execution(intent_env, dispatch_text)
            intent_name = str((intent_env or {}).get("intent") or "").strip()
            if can_execute_intent and intent_name:
                if intent_name == "interrupt_output":
                    try:
                        fei = getattr(sisi_booter, "sisi_core", None)
                        if fei:
                            try:
                                fei._stop_all_systems()
                            except Exception:
                                pass
                            try:
                                fei._stop_current_tasks()
                            except Exception:
                                pass
                            try:
                                fei._execute_interrupt_function("stop_music")
                            except Exception:
                                pass
                    except Exception:
                        pass

                    try:
                        wsa_server.get_web_instance().add_cmd({"audio_command": "stop"})
                        wsa_server.get_web_instance().add_cmd({"music_event": "stop"})
                    except Exception:
                        pass

                    return _api_v1_ok(
                        {
                            "accepted": True,
                            "persona": persona,
                            "message": dispatch_text,
                            "parts": parts,
                            "attachments": attachments,
                            "artifacts": [],
                            "llm_route": "control_intent",
                            "llm_provider_id": "",
                            "command_executed": True,
                            "control_intent": {
                                "intent": "interrupt_output",
                                "action": "interrupt_output",
                                "confidence": float(intent_env.get("confidence") or 0.0),
                                "args": {},
                                "source": "text",
                            },
                        },
                        trace_id=trace_id,
                    )

                ws_event = build_client_control_event(intent_env, username=username)
                pushed = False
                if ws_event:
                    try:
                        wsa_server.get_web_instance().add_cmd(ws_event)
                        pushed = True
                    except Exception as ws_err:
                        util.log(2, f"[intent] push_control_intent_failed: {ws_err}")

                if pushed:
                    return _api_v1_ok(
                        {
                            "accepted": True,
                            "persona": persona,
                            "message": dispatch_text,
                            "parts": parts,
                            "attachments": attachments,
                            "artifacts": [],
                            "llm_route": "control_intent",
                            "llm_provider_id": "",
                            "command_executed": True,
                            "control_intent": ws_event.get("control_intent") if isinstance(ws_event, dict) else {},
                        },
                        trace_id=trace_id,
                    )
            elif intent_name:
                util.log(1, f"[intent] denied intent={intent_name} reason={deny_reason}")

        llm_user_content_parts = None
        if has_multimodal_media and llm_override:
            public_media_base = _api_v1_get_multimodal_media_public_base()

            def _resolver_for_llm(file_id):
                item = _api_v1_media_resolver(file_id) or {}
                if not item:
                    return {}
                if str(item.get("storage") or "").strip().lower() == "local" and public_media_base:
                    patched = dict(item)
                    patched["storage"] = "url"
                    patched["url"] = f"{public_media_base}/api/v1/media/{file_id}"
                    return patched
                return item

            style = str((llm_override or {}).get("api_style") or "").strip().lower()
            if style == "anthropic":
                llm_user_content_parts = build_anthropic_content_parts(parts, _resolver_for_llm)
            elif style == "openai":
                llm_user_content_parts = build_openai_content_parts(parts, _resolver_for_llm)

            if not isinstance(llm_user_content_parts, list) or not llm_user_content_parts:
                return _api_v1_error(
                    "MULTIMODAL_CONTENT_EMPTY",
                    "多模态内容构建失败，请检查上传文件或URL可访问性",
                    status=400,
                    trace_id=trace_id,
                )

        try:
            current_mode = _api_v1_norm_persona(liusisi.get_current_system_mode()) or "sisi"
            if persona != current_mode:
                liusisi.set_system_mode(persona)
        except Exception:
            pass

        _api_v1_dispatch_text_interaction(
            username,
            dispatch_text,
            llm_override=llm_override,
            llm_user_content_parts=llm_user_content_parts,
        )

        llm_route = "multimodal_override" if llm_override else "persona_default"
        llm_provider_id = str((llm_override or {}).get("provider_id") or "")

        return _api_v1_ok(
            {
                "accepted": True,
                "persona": persona,
                "message": dispatch_text,
                "parts": parts,
                "attachments": attachments,
                "artifacts": [],
                "llm_route": llm_route,
                "llm_provider_id": llm_provider_id,
            },
            trace_id=trace_id,
        )
    except RuntimeError as e:
        return _api_v1_error("DISPATCH_ERROR", str(e), status=503, trace_id=trace_id)
    except Exception as e:
        return _api_v1_error("CHAT_ERROR", str(e), status=500, trace_id=trace_id)

@__app.route('/', methods=['get'])
@auth.login_required
def home_get():
    if os.path.exists(_NEW_FRONTEND_INDEX):
        return _send_frontend_index()
    return make_response("frontend not built: run gui/frontend `npm run build` to generate gui/static/app/", 404)

@__app.route('/', methods=['post'])
@auth.login_required
def home_post():
    try:
        return __get_template()
    except Exception as e:
        return f"Error processing request: {e}", 500

@__app.route('/setting', methods=['get'])
def setting():
    try:
        if os.path.exists(_NEW_FRONTEND_INDEX):
            return _send_frontend_index()
        return make_response("frontend not built: run gui/frontend `npm run build` to generate gui/static/app/", 404)
    except Exception as e:
        return f"Error loading settings page: {e}", 500


@__app.route('/<path:path>', methods=['get'])
@auth.login_required
def spa_fallback(path):
    """
    SPA 璺敱鍥為€€锛氳 /settings銆?activity銆?lab/* 杩欑被鍓嶇 history 璺敱鍦?5000 绔彛鐩存帴鍙闂€?

    璇存槑锛氶潤鎬佽祫婧愪笌鍚庣 API 浠嶈蛋鍚勮嚜鐨勮矾鐢憋紝涓嶅湪杩欓噷澶勭悊銆?
    """
    # 鍚庣璺敱鍓嶇紑鐩存帴鏀捐锛堜繚鎸?404 鎴栫敱鍏跺畠 handler 澶勭悊锛?
    if path.startswith(('api/', 'audio/', 'static/')):
        abort(404)

    if os.path.exists(_NEW_FRONTEND_INDEX):
        return _send_frontend_index()

    return make_response("frontend not built: run gui/frontend `npm run build` to generate gui/static/app/", 404)

# 杈撳嚭鐨勯煶棰慼ttp
@__app.route('/audio/<filename>')
def serve_audio(filename):
    audio_file = os.path.join(os.getcwd(), "samples", filename)
    if os.path.exists(audio_file):
        return send_file(audio_file)
    else:
        return jsonify({'error': '文件未找到'}), 404

#鎵撴嫑鍛?
@__app.route('/to_greet', methods=['POST'])
def to_greet():
    data = request.get_json()
    username = data.get('username', 'User')
    observation = data.get('observation', '')
    interact = Interact("hello", 1, {"user": username, "msg": "打招呼", "observation": str(observation)})

    # 馃敡 鍏抽敭淇锛氬紓姝ュ鐞嗘墦鎷涘懠
    import threading
    def async_process():
        try:
            sisi_booter.sisi_core.on_interact(interact)
        except Exception as e:
            util.log(2, f"[寮傛澶勭悊] 鎵撴嫑鍛煎鐞嗗紓甯? {str(e)}")

    # 鍚姩寮傛绾跨▼澶勭悊浜や簰
    thread = threading.Thread(target=async_process, daemon=True)
    thread.start()

    # 绔嬪嵆杩斿洖鎴愬姛
    return jsonify({'status': 'success', 'data': '姝ｅ湪鎵撴嫑鍛?..', 'msg': '宸茶繘琛屾墦鎷涘懠'}), 200

#鍞ら啋:鍦ㄦ櫘閫氬敜閱掓ā寮忥紝杩涜澶у睆浜や簰鎵嶆湁鎰忎箟
@__app.route('/to_wake', methods=['POST'])
def to_wake():
    data = request.get_json()
    username = data.get('username', 'User')
    observation = data.get('observation', '')
    sisi_booter.recorderListener.wakeup_matched = True
    return jsonify({'status': 'success', 'msg': '已唤醒'}), 200

#鎵撴柇
@__app.route('/to_stop_talking', methods=['POST'])
def to_stop_talking():
    try:
        data = request.get_json()
        username = data.get('username', 'User')
        message = data.get('text', '浣犲ソ锛岃璇达紵')
        observation = data.get('observation', '')
        # 立即停止当前播放与队列（TTS + 音乐）
        try:
            fei = getattr(sisi_booter, "sisi_core", None)
            if fei:
                try:
                    fei._stop_all_systems()
                except Exception:
                    pass
                try:
                    fei._stop_current_tasks()
                except Exception:
                    pass
                try:
                    fei._execute_interrupt_function("stop_music")
                except Exception:
                    pass
        except Exception:
            pass

        # 通知前端立刻停止播放状态
        try:
            wsa_server.get_web_instance().add_cmd({"audio_command": "stop"})
            wsa_server.get_web_instance().add_cmd({"music_event": "stop"})
        except Exception:
            pass

        return jsonify({
            'status': 'success',
            'data': '已停止播放',
            'msg': 'stop_talking ok'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'msg': str(e)
        }), 500


#娑堟伅閫忎紶鎺ュ彛
@__app.route('/transparent_pass', methods=['post'])
def transparent_pass():
    try:
        data = request.form.get('data')
        if data is None:
            data = request.get_json()
        else:
            data = json.loads(data)
        user = data.get('user', 'User')
        response_text = data.get('text', '')
        audio_url = data.get('audio', '')
        interact = Interact('transparent_pass', 2, {'user': user, 'text': response_text, 'audio': audio_url})
        util.printInfo(1, user, '閫忎紶鎾斁锛歿}锛寋}'.format(response_text, audio_url), time.time())

        # 馃敡 鍏抽敭淇锛氬紓姝ュ鐞嗛€忎紶
        import threading
        def async_process():
            try:
                sisi_booter.sisi_core.on_interact(interact)
            except Exception as e:
                util.log(2, f"[寮傛澶勭悊] 閫忎紶澶勭悊寮傚父: {str(e)}")

        # 鍚姩寮傛绾跨▼澶勭悊浜や簰
        thread = threading.Thread(target=async_process, daemon=True)
        thread.start()

        # 绔嬪嵆杩斿洖鎴愬姛
        return jsonify({'code': 200, 'message' : '鎴愬姛'})
    except Exception as e:
        return jsonify({'code': 500, 'message': f'鍑洪敊: {e}'}), 500

@__app.route('/api/browser-check', methods=['GET'])
def browser_check():
    return jsonify({
        'supported': True,
        'browser_info': {}
    })


def run():
    class NullLogHandler:
        def write(self, *args, **kwargs):
            pass
    server = pywsgi.WSGIServer(
        ('0.0.0.0', 5000), 
        __app,
        log=NullLogHandler()  
    )
    server.serve_forever()


def start():
    """鍚姩Flask GUI (5000)"""
    # 鍚姩鍘熸湁Flask GUI
    MyThread(target=run).start()

