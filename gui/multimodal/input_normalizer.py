from typing import Any, Callable, Dict, List


def _as_type(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_text_part(part: Dict[str, Any]) -> Dict[str, Any]:
    text = str(part.get("text") or "").strip()
    if not text:
        raise ValueError("text part is empty")
    return {
        "type": "text",
        "text": text,
        "file_id": "",
        "url": "",
        "mime": "text/plain",
        "name": "text",
        "size": len(text.encode("utf-8")),
    }


def _normalize_media_part(part: Dict[str, Any], resolver: Callable[[str], Dict[str, Any]]) -> Dict[str, Any]:
    t = _as_type(part.get("type"))
    if t not in ("image", "video", "audio"):
        raise ValueError(f"unsupported part type: {t}")

    file_id = str(part.get("file_id") or "").strip()
    if not file_id:
        raise ValueError(f"{t} part requires file_id")

    item = resolver(file_id)
    if not item:
        raise ValueError(f"file_id not found: {file_id}")
    item_kind = str(item.get("kind") or "").strip().lower()
    if item_kind != t:
        raise ValueError(f"file kind mismatch: expected {t}, got {item_kind or 'unknown'}")

    return {
        "type": t,
        "text": "",
        "file_id": file_id,
        "url": item.get("url", ""),
        "mime": item.get("mime", ""),
        "name": item.get("name", ""),
        "size": int(item.get("size", 0) or 0),
    }


def normalize_chat_parts(
    payload: Dict[str, Any],
    resolver: Callable[[str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    raw_parts = payload.get("parts")
    if not isinstance(raw_parts, list):
        raw_parts = []

    parts: List[Dict[str, Any]] = []
    for raw in raw_parts:
        if not isinstance(raw, dict):
            continue
        t = _as_type(raw.get("type"))
        if t == "text":
            parts.append(_normalize_text_part(raw))
            continue
        if t in ("image", "video", "audio"):
            parts.append(_normalize_media_part(raw, resolver))
            continue

    # Compat path: old payload only has msg/text/content
    if not parts:
        msg = payload.get("msg")
        if msg is None:
            msg = payload.get("text")
        if msg is None:
            msg = payload.get("content")
        text = str(msg or "").strip()
        if text:
            parts.append(
                {
                    "type": "text",
                    "text": text,
                    "file_id": "",
                    "url": "",
                    "mime": "text/plain",
                    "name": "text",
                    "size": len(text.encode("utf-8")),
                }
            )

    if not parts:
        raise ValueError("missing parts or text")
    return parts
