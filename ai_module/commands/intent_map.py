import json
import re
from typing import Any, Dict, Tuple


INTENT_WHITELIST = {
    "interrupt_output",
    "open_multimodal",
    "image_analysis_capture",
    "video_call_start",
    "video_call_stop",
}

_ANCHOR_TOKENS = {
    "interrupt_output": ("停止", "打断", "别说", "stop"),
    "open_multimodal": ("多模态", "看图", "图像分析"),
    "image_analysis_capture": ("拍照", "拍几帧", "画面", "摄像头", "镜头"),
    "video_call_start": ("视频通话", "连麦", "实时通话", "实时视频"),
    "video_call_stop": ("结束视频通话", "关闭视频通话", "挂断", "停止视频通话"),
}

_NEGATION_TOKENS = ("不要", "不用", "不想", "别", "取消", "关闭", "结束")


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return default


def _normalize_text(text: str) -> str:
    t = _safe_text(text).lower()
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t)
    return t


def _contains_any(text: str, tokens) -> bool:
    return any(tok in text for tok in (tokens or ()))


def _parse_suffix_control_json(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Extract a trailing JSON control block from text, if present.
    Return (block, stripped_text).
    """
    raw = str(text or "")
    if "{" not in raw or "}" not in raw:
        return {}, raw

    tail = raw.rstrip()
    if not tail.endswith("}"):
        return {}, raw

    depth = 0
    start = -1
    for idx in range(len(tail) - 1, -1, -1):
        ch = tail[idx]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                start = idx
                break
            if depth < 0:
                return {}, raw

    if start < 0 or depth != 0:
        return {}, raw

    candidate = tail[start:]
    try:
        block = json.loads(candidate)
    except Exception:
        return {}, raw

    if not isinstance(block, dict):
        return {}, raw
    if not _safe_text(block.get("intent")):
        return {}, raw

    stripped = tail[:start].rstrip()
    return block, stripped


def resolve_intent_from_text(text: str, *, source: str = "user") -> Dict[str, Any]:
    """
    Convert raw text into a normalized intent envelope.
    This is intentionally lightweight: rule-based + optional suffix JSON hint.
    """
    block, stripped_text = _parse_suffix_control_json(text)
    base_text = stripped_text if block else str(text or "")
    normalized = _normalize_text(base_text)

    envelope: Dict[str, Any] = {
        "intent": "",
        "confidence": 0.0,
        "source": _safe_text(source) or "user",
        "residual_text": _safe_text(base_text),
        "from_control_suffix": bool(block),
        "ack": "",
        "args": {},
    }

    if block:
        envelope["intent"] = _safe_text(block.get("intent"))
        envelope["confidence"] = _to_float(block.get("confidence"), 0.8)
        args = block.get("args")
        envelope["args"] = dict(args) if isinstance(args, dict) else {}
        if _safe_text(block.get("ack")):
            envelope["ack"] = _safe_text(block.get("ack"))
        return envelope

    if not normalized:
        return envelope

    if _contains_any(normalized, ("停止说话", "别说了", "打断", "停一下", "stop")):
        envelope.update(
            {
                "intent": "interrupt_output",
                "confidence": 0.98,
                "ack": "好的，已停止当前输出。",
            }
        )
        return envelope

    if _contains_any(normalized, ("结束视频通话", "关闭视频通话", "停止视频通话", "挂断", "退出连麦")):
        envelope.update(
            {
                "intent": "video_call_stop",
                "confidence": 0.95,
                "ack": "好的，正在结束视频通话。",
            }
        )
        return envelope

    if _contains_any(normalized, ("拍照分析", "拍几帧", "拍一张", "分析画面", "看一下画面", "摄像头看看")):
        envelope.update(
            {
                "intent": "image_analysis_capture",
                "confidence": 0.9,
                "ack": "好的，我来抓取画面并进行分析。",
                "args": {"frames": 3},
            }
        )
        return envelope

    if _contains_any(normalized, ("打开多模态", "进入多模态", "看图模式", "图像分析模式")):
        envelope.update(
            {
                "intent": "open_multimodal",
                "confidence": 0.88,
                "ack": "好的，已切换到多模态输入模式。",
            }
        )
        return envelope

    start_video_tokens = ("开始视频通话", "打开视频通话", "进入视频通话", "发起视频通话", "连麦", "实时通话", "实时视频")
    if _contains_any(normalized, start_video_tokens):
        if _contains_any(normalized, _NEGATION_TOKENS):
            return envelope
        envelope.update(
            {
                "intent": "video_call_start",
                "confidence": 0.92,
                "ack": "好的，正在准备实时视频通话。",
            }
        )
        return envelope

    return envelope


def validate_intent_execution(
    envelope: Dict[str, Any],
    source_text: str,
    *,
    min_confidence: float = 0.75,
) -> Tuple[bool, str]:
    """
    Hard gate before executing any action.
    """
    intent = _safe_text((envelope or {}).get("intent"))
    if not intent:
        return False, "no_intent"
    if intent not in INTENT_WHITELIST:
        return False, "not_whitelisted"

    confidence = _to_float((envelope or {}).get("confidence"), 0.0)
    if confidence < float(min_confidence):
        return False, "low_confidence"

    normalized = _normalize_text(source_text)
    anchors = _ANCHOR_TOKENS.get(intent, ())
    if anchors and not _contains_any(normalized, anchors):
        return False, "anchor_mismatch"

    if intent in ("video_call_start", "open_multimodal", "image_analysis_capture"):
        if _contains_any(normalized, _NEGATION_TOKENS):
            return False, "negated"

    return True, "ok"


def build_client_control_event(envelope: Dict[str, Any], *, username: str = "User") -> Dict[str, Any]:
    """
    Convert an executable intent envelope to a WS control event for frontend.
    """
    intent = _safe_text((envelope or {}).get("intent"))
    if intent not in INTENT_WHITELIST or intent == "interrupt_output":
        return {}

    action_map = {
        "open_multimodal": "open_multimodal",
        "image_analysis_capture": "capture_frames_and_analyze",
        "video_call_start": "video_call_start",
        "video_call_stop": "video_call_stop",
    }
    action = action_map.get(intent, "")
    if not action:
        return {}

    payload = {
        "intent": intent,
        "action": action,
        "confidence": _to_float((envelope or {}).get("confidence"), 0.0),
        "args": dict((envelope or {}).get("args") or {}),
        "source": _safe_text((envelope or {}).get("source")) or "user",
    }
    return {
        "control_intent": payload,
        "Username": _safe_text(username) or "User",
    }
