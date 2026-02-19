from __future__ import annotations

import json
from typing import Any, Dict, Optional


def is_control_payload(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if text.startswith("<control>") and text.endswith("</control>"):
        return True
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            return isinstance(obj, dict) and "type" in obj
        except Exception:
            return False
    return False


def extract_control_type(message: str) -> str:
    text = (message or "").strip()
    if text.startswith("<control>") and text.endswith("</control>"):
        body = text[len("<control>") : -len("</control>")]
        for part in body.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key.strip().lower() == "type":
                return value.strip().lower()
        return "unknown"
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            return str(obj.get("type", "unknown")).strip().lower()
        except Exception:
            return "unknown"
    return "unknown"


def build_control_ack(
    *,
    ok: bool,
    session_id: str,
    device_id: str,
    control_type: str,
    reason: str = "",
    ts_ms: Optional[int] = None,
) -> str:
    payload: Dict[str, Any] = {
        "type": "control_ack",
        "ok": bool(ok),
        "session_id": session_id,
        "device_id": device_id,
        "control_type": control_type or "unknown",
    }
    if reason:
        payload["reason"] = reason
    if ts_ms is not None:
        payload["ts_ms"] = int(ts_ms)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

