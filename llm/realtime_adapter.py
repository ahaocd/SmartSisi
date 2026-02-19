import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests

from utils import config_util


_TEXT_BUFFER_LOCK = threading.Lock()
_TEXT_BUFFER: Dict[Tuple[str, str, str], str] = {}
_TEXT_BUFFER_UPDATED_AT: Dict[Tuple[str, str, str], float] = {}


_PROVIDER_DOCS = {
    "openai": [
        "https://platform.openai.com/docs/guides/realtime-webrtc",
        "https://platform.openai.com/docs/guides/realtime-websocket",
        "https://platform.openai.com/docs/api-reference/realtime-sessions/create",
        "https://platform.openai.com/docs/api-reference/realtime-server-events/response/audio",
    ],
    "gemini": [
        "https://ai.google.dev/api/live",
        "https://ai.google.dev/gemini-api/docs/live",
        "https://ai.google.dev/gemini-api/docs/openai",
    ],
    "grok": [
        "https://docs.x.ai/developers/model-capabilities/audio/voice-agent",
        "https://docs.x.ai/docs/guides/voice",
    ],
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return default


def _cfg(key: str, default: str = "") -> str:
    return _safe_text(config_util.get_value(key, default))


def _provider_name(raw: Any) -> str:
    p = _safe_text(raw).lower()
    if p in ("openai", "gemini", "grok"):
        return p
    return "openai"


def _buffer_key(provider: str, session_id: str, response_id: str) -> Tuple[str, str, str]:
    s = _safe_text(session_id) or "default"
    r = _safe_text(response_id) or "default"
    return (_provider_name(provider), s, r)


def _append_text(provider: str, session_id: str, response_id: str, chunk: str) -> None:
    text = _coerce_text(chunk)
    if text == "":
        return
    key = _buffer_key(provider, session_id, response_id)
    with _TEXT_BUFFER_LOCK:
        _TEXT_BUFFER[key] = (_TEXT_BUFFER.get(key) or "") + text
        _TEXT_BUFFER_UPDATED_AT[key] = time.time()


def _pop_text(provider: str, session_id: str, response_id: str) -> str:
    key = _buffer_key(provider, session_id, response_id)
    with _TEXT_BUFFER_LOCK:
        _TEXT_BUFFER_UPDATED_AT.pop(key, None)
        return _TEXT_BUFFER.pop(key, "")


def _merge_by_overlap(current: str, tail: str) -> str:
    if not current:
        return tail
    if not tail:
        return current
    max_overlap = min(len(current), len(tail))
    for overlap in range(max_overlap, 0, -1):
        if current.endswith(tail[:overlap]):
            return current + tail[overlap:]
    return current + tail


def _apply_done_text(provider: str, session_id: str, response_id: str, done_text: str) -> str:
    text = _coerce_text(done_text)
    if text == "":
        return ""

    key = _buffer_key(provider, session_id, response_id)
    with _TEXT_BUFFER_LOCK:
        current = _TEXT_BUFFER.get(key) or ""
        if not current:
            merged = text
        elif text.startswith(current):
            # done usually carries the full finalized text for this response.
            merged = text
        elif current.startswith(text):
            # keep the longer accumulated text.
            merged = current
        else:
            # fallback for providers that send done as the tail chunk.
            merged = _merge_by_overlap(current, text)

        _TEXT_BUFFER[key] = merged
        _TEXT_BUFFER_UPDATED_AT[key] = time.time()
        return merged


def cleanup_text_buffers(provider: str, *, session_id: str = "", ttl_seconds: int = 120) -> Dict[str, int]:
    p = _provider_name(provider)
    target_session = _safe_text(session_id)
    target_session_key = target_session or "default"
    ttl = max(15, min(_safe_int(ttl_seconds, 120), 7200))
    now = time.time()

    removed_keys = 0
    removed_chars = 0
    scanned_keys = 0

    with _TEXT_BUFFER_LOCK:
        keys = list(_TEXT_BUFFER.keys())
        for key in keys:
            kp, ks, _ = key
            if kp != p:
                continue
            if target_session and ks != target_session_key:
                continue
            scanned_keys += 1
            updated_at = float(_TEXT_BUFFER_UPDATED_AT.get(key) or now)
            if (now - updated_at) < ttl:
                continue
            txt = _TEXT_BUFFER.pop(key, "")
            _TEXT_BUFFER_UPDATED_AT.pop(key, None)
            removed_keys += 1
            removed_chars += len(txt or "")

    return {
        "provider_keys_scanned": scanned_keys,
        "provider_keys_removed": removed_keys,
        "provider_chars_removed": removed_chars,
        "ttl_seconds": ttl,
    }


def _segment_split_index(text: str, threshold_chars: int, min_segment_chars: int) -> int:
    if not text:
        return 0
    limit = min(len(text), max(1, threshold_chars))
    min_seg = max(1, min(min_segment_chars, limit))
    window = text[:limit]

    split_at = -1
    for token in (
        "\u3002",  # Chinese full stop
        "\uff01",  # Chinese exclamation mark
        "\uff1f",  # Chinese question mark
        "\uff1b",  # Chinese semicolon
        "\uff0c",  # Chinese comma
        ".",
        "!",
        "?",
        ";",
        ",",
        "\n",
    ):
        idx = window.rfind(token)
        if idx >= (min_seg - 1):
            split_at = max(split_at, idx + 1)

    if split_at < min_seg:
        ws = window.rfind(" ")
        if ws >= (min_seg - 1):
            split_at = ws + 1

    if split_at < min_seg:
        split_at = limit
    return split_at


def pop_text_segment_if_ready(
    provider: str,
    session_id: str,
    response_id: str,
    *,
    threshold_chars: int = 180,
    min_segment_chars: int = 80,
) -> str:
    key = _buffer_key(provider, session_id, response_id)
    threshold = max(40, min(_safe_int(threshold_chars, 180), 8000))
    min_seg = max(20, min(_safe_int(min_segment_chars, 80), threshold))

    with _TEXT_BUFFER_LOCK:
        current = _TEXT_BUFFER.get(key) or ""
        if len(current) < threshold:
            return ""

        split_at = _segment_split_index(current, threshold, min_seg)
        segment = current[:split_at].strip()
        remain = current[split_at:].lstrip()
        if not segment:
            return ""

        if remain:
            _TEXT_BUFFER[key] = remain
            _TEXT_BUFFER_UPDATED_AT[key] = time.time()
        else:
            _TEXT_BUFFER.pop(key, None)
            _TEXT_BUFFER_UPDATED_AT.pop(key, None)
        return segment


def get_realtime_provider_config(provider: str, *, persona: str = "sisi") -> Dict[str, Any]:
    p = _provider_name(provider)
    persona_norm = _safe_text(persona).lower() or "sisi"

    if p == "openai":
        return {
            "provider": p,
            "persona": persona_norm,
            "transport": "webrtc_or_websocket",
            "model": _cfg("realtime_openai_model", "gpt-realtime"),
            "api_key": _cfg("realtime_openai_api_key", ""),
            "ws_url": _cfg("realtime_openai_ws_url", "wss://api.openai.com/v1/realtime"),
            "client_secret_url": _cfg("realtime_openai_client_secret_url", "https://api.openai.com/v1/realtime/client_secrets"),
            "auth_mode": "bearer_or_client_secret",
            "docs": list(_PROVIDER_DOCS["openai"]),
        }

    if p == "gemini":
        return {
            "provider": p,
            "persona": persona_norm,
            "transport": "websocket",
            "model": _cfg("realtime_gemini_model", "models/gemini-live-2.5-flash-preview"),
            "api_key": _cfg("realtime_gemini_api_key", _cfg("gemini_api_key", "")),
            "ws_url": _cfg(
                "realtime_gemini_ws_url",
                "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent",
            ),
            "client_secret_url": _cfg("realtime_gemini_client_secret_url", ""),
            "auth_mode": "x-goog-api-key_or_bearer",
            "docs": list(_PROVIDER_DOCS["gemini"]),
        }

    return {
        "provider": "grok",
        "persona": persona_norm,
        "transport": "websocket",
        "model": _cfg("realtime_grok_model", "grok-voice-agent"),
        "api_key": _cfg("realtime_grok_api_key", _cfg("xai_api_key", "")),
        "ws_url": _cfg("realtime_grok_ws_url", "wss://api.x.ai/v1/realtime"),
        "client_secret_url": _cfg("realtime_grok_client_secret_url", "https://api.x.ai/v1/realtime/client_secrets"),
        "auth_mode": "bearer_or_client_secret",
        "docs": list(_PROVIDER_DOCS["grok"]),
    }


def merge_realtime_session_overrides(base: Optional[Dict[str, Any]], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base or {})
    incoming = overrides if isinstance(overrides, dict) else {}
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_realtime_session_overrides(out.get(key) or {}, value)
        else:
            out[key] = value
    return out


def build_realtime_turn_policy(
    provider: str,
    *,
    server_vad_enabled: bool = True,
    interrupt_response_enabled: bool = True,
    vad_threshold: float = 0.5,
    vad_prefix_padding_ms: int = 300,
    vad_silence_duration_ms: int = 500,
) -> Dict[str, Any]:
    p = _provider_name(provider)
    vad_on = bool(server_vad_enabled)

    threshold = max(0.0, min(_safe_float(vad_threshold, 0.5), 1.0))
    prefix_ms = max(0, min(_safe_int(vad_prefix_padding_ms, 300), 5000))
    silence_ms = max(100, min(_safe_int(vad_silence_duration_ms, 500), 5000))
    interrupt_resp = bool(interrupt_response_enabled)

    if not vad_on:
        turn_none = {"type": "none"}
        if p in ("openai", "grok"):
            return {
                "turn_detection": dict(turn_none),
                "audio": {"input": {"turn_detection": dict(turn_none)}},
            }
        return {"turn_detection": dict(turn_none)}

    turn_detection = {
        "type": "server_vad",
        "threshold": threshold,
        "prefix_padding_ms": prefix_ms,
        "silence_duration_ms": silence_ms,
        "interrupt_response": interrupt_resp,
    }

    if p in ("openai", "grok"):
        return {
            "modalities": ["text", "audio"],
            "turn_detection": dict(turn_detection),
            "audio": {"input": {"turn_detection": dict(turn_detection)}},
        }

    # Gemini Live differs in wire format; keep a provider-neutral turn policy
    # and also offer a minimal realtime_input hint for clients that want to map it.
    return {
        "turn_detection": dict(turn_detection),
        "realtime_input": {
            "automatic_activity_detection": {
                "disabled": False,
            }
        },
    }


def create_realtime_client_secret(
    provider_cfg: Dict[str, Any],
    *,
    ttl_seconds: int = 300,
    session_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    provider = _provider_name(provider_cfg.get("provider"))
    api_key = _safe_text(provider_cfg.get("api_key"))
    if not api_key:
        raise RuntimeError(f"missing realtime api_key for provider={provider}")

    url = _safe_text(provider_cfg.get("client_secret_url"))
    if not url:
        raise RuntimeError(f"client secret endpoint is not configured for provider={provider}")

    ttl = max(30, min(_safe_int(ttl_seconds, 300), 3600))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if provider == "openai":
        body = {
            "expires_after": {"anchor": "created_at", "seconds": ttl},
            "session": {
                "type": "realtime",
                "model": _safe_text(provider_cfg.get("model")),
            },
        }
        if isinstance(session_overrides, dict) and session_overrides:
            body["session"].update(session_overrides)
    elif provider == "grok":
        body = {"expires_after": {"seconds": ttl}}
        if isinstance(session_overrides, dict) and session_overrides:
            body["session"] = dict(session_overrides)
    else:
        body = {"expires_after": {"seconds": ttl}}
        if isinstance(session_overrides, dict) and session_overrides:
            body["session"] = dict(session_overrides)

    resp = requests.post(url, headers=headers, json=body, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"client_secret_request_failed status={resp.status_code} provider={provider}")
    data = resp.json() if "application/json" in str(resp.headers.get("content-type") or "").lower() else {}

    value = (
        _safe_text(data.get("value"))
        or _safe_text((data.get("client_secret") or {}).get("value"))
        or _safe_text(((data.get("session") or {}).get("client_secret") or {}).get("value"))
    )
    expires_at = (
        _safe_int(data.get("expires_at"), 0)
        or _safe_int((data.get("client_secret") or {}).get("expires_at"), 0)
        or _safe_int(((data.get("session") or {}).get("client_secret") or {}).get("expires_at"), 0)
    )
    if not value:
        raise RuntimeError(f"client_secret_missing_in_response provider={provider}")

    return {
        "provider": provider,
        "value": value,
        "expires_at": expires_at,
        "raw": data,
    }


def normalize_realtime_event(provider: str, event: Dict[str, Any], *, session_id: str = "") -> Dict[str, Any]:
    p = _provider_name(provider)
    e = event if isinstance(event, dict) else {}
    event_type = _safe_text(e.get("type"))
    response_id = _safe_text(e.get("response_id") or (e.get("response") or {}).get("id"))

    out = {
        "provider": p,
        "event_type": event_type or "unknown",
        "session_id": _safe_text(session_id),
        "response_id": response_id,
        "text_delta": "",
        "text_final": "",
        "audio_intercepted": False,
        "audio_chunks": 0,
        "done": False,
    }

    if p in ("openai", "grok"):
        text_delta = ""
        text_done = ""

        if event_type in (
            "response.output_text.delta",
            "response.text.delta",
            "response.output_audio_transcript.delta",
            "response.audio_transcript.delta",
        ):
            text_delta = _coerce_text(e.get("delta"))
        elif event_type in ("response.output_text.done", "response.text.done"):
            text_done = _coerce_text(e.get("text"))
        elif event_type in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
            text_done = _coerce_text(e.get("transcript") or e.get("text"))

        if event_type in ("response.output_audio.delta", "response.audio.delta"):
            out["audio_intercepted"] = True
            out["audio_chunks"] = 1
        elif event_type in ("response.output_audio.done", "response.audio.done"):
            out["audio_intercepted"] = True

        if text_delta:
            _append_text(p, session_id, response_id, text_delta)
            out["text_delta"] = text_delta
        if text_done:
            out["text_final"] = _apply_done_text(p, session_id, response_id, text_done)

        if event_type == "response.done":
            out["done"] = True
            out["text_final"] = out["text_final"] or _pop_text(p, session_id, response_id)
        elif text_done:
            # Keep the same final text available even before response.done.
            out["text_final"] = text_done

        return out

    # Gemini Live (BidiGenerateContent): server messages are union-style.
    server_content = e.get("serverContent") if isinstance(e.get("serverContent"), dict) else {}
    if server_content:
        out["event_type"] = "serverContent"
        text_chunks = []
        audio_chunks = 0

        model_turn = server_content.get("modelTurn") if isinstance(server_content.get("modelTurn"), dict) else {}
        parts = model_turn.get("parts") if isinstance(model_turn.get("parts"), list) else []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text_part = _safe_text(part.get("text"))
            if text_part:
                text_chunks.append(text_part)
            inline_data = part.get("inlineData") if isinstance(part.get("inlineData"), dict) else {}
            mime = _safe_text(inline_data.get("mimeType")).lower()
            if mime.startswith("audio/"):
                audio_chunks += 1

        output_tx = server_content.get("outputTranscription") if isinstance(server_content.get("outputTranscription"), dict) else {}
        output_tx_text = _safe_text(output_tx.get("text"))
        if output_tx_text:
            text_chunks.append(output_tx_text)

        text_delta = "".join([x for x in text_chunks if x]).strip()
        if text_delta:
            _append_text(p, session_id, response_id, text_delta)
            out["text_delta"] = text_delta

        if audio_chunks > 0:
            out["audio_intercepted"] = True
            out["audio_chunks"] = audio_chunks

        if bool(server_content.get("generationComplete")) or bool(server_content.get("turnComplete")):
            out["done"] = True
            out["text_final"] = _pop_text(p, session_id, response_id)
        return out

    if "setupComplete" in e:
        out["event_type"] = "setupComplete"
    elif "toolCall" in e:
        out["event_type"] = "toolCall"
    elif "toolCallCancellation" in e:
        out["event_type"] = "toolCallCancellation"
    elif "usageMetadata" in e:
        out["event_type"] = "usageMetadata"
    return out

