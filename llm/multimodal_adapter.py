import base64
import mimetypes
import os
import shutil
from typing import Any, Callable, Dict, List

from gui.multimodal.media_store import MediaStore
from gui.multimodal.video_preprocess import extract_video_frames
from gui.multimodal.vision_fallback import summarize_image


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _part_type(part: Dict[str, Any]) -> str:
    return str(part.get("type") or "").strip().lower()


def _compact_summary(value: Any, *, limit: int = 120) -> str:
    text = str(value or "").replace("\r", "\n").strip()
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def _normalize_image_mime(item: Dict[str, Any], path: str = "") -> str:
    mime = str(item.get("mime") or "").strip().lower()
    if mime.startswith("image/"):
        return mime
    guessed, _ = mimetypes.guess_type(path or str(item.get("name") or ""))
    guessed = str(guessed or "").strip().lower()
    if guessed.startswith("image/"):
        return guessed
    return "image/jpeg"


def _normalize_audio_mime(item: Dict[str, Any], path: str = "") -> str:
    mime = str(item.get("mime") or "").strip().lower()
    if mime.startswith("audio/"):
        return mime
    guessed, _ = mimetypes.guess_type(path or str(item.get("name") or ""))
    guessed = str(guessed or "").strip().lower()
    if guessed.startswith("audio/"):
        return guessed
    return "audio/mpeg"


def _image_item_to_anthropic_block(item: Dict[str, Any]) -> Dict[str, Any]:
    storage = str(item.get("storage") or "").strip().lower()
    if storage == "url":
        url = _safe_text(item.get("url"))
        if not url:
            return {}
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": url,
            },
        }

    path = _safe_text(item.get("path"))
    if not path or not os.path.exists(path):
        return {}
    mime = _normalize_image_mime(item, path)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    if not b64:
        return {}
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime,
            "data": b64,
        },
    }


def _image_item_to_openai_block(item: Dict[str, Any]) -> Dict[str, Any]:
    storage = str(item.get("storage") or "").strip().lower()
    if storage == "url":
        url = _safe_text(item.get("url"))
        if not url:
            return {}
        return {"type": "image_url", "image_url": {"url": url}}

    path = _safe_text(item.get("path"))
    if not path or not os.path.exists(path):
        return {}
    mime = _normalize_image_mime(item, path)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    if not b64:
        return {}
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _audio_item_to_openai_block(item: Dict[str, Any]) -> Dict[str, Any]:
    storage = str(item.get("storage") or "").strip().lower()
    if storage == "url":
        url = _safe_text(item.get("url"))
        if not url:
            return {}
        return {"type": "audio_url", "audio_url": {"url": url}}

    path = _safe_text(item.get("path"))
    if not path or not os.path.exists(path):
        return {}
    mime = _normalize_audio_mime(item, path)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    if not b64:
        return {}
    return {"type": "audio_url", "audio_url": {"url": f"data:{mime};base64,{b64}"}}


def collect_attachments_from_parts(parts: List[Dict[str, Any]], resolver: Callable[[str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []
    for part in parts or []:
        t = _part_type(part)
        if t not in ("image", "video", "audio"):
            continue
        file_id = _safe_text(part.get("file_id"))
        if not file_id:
            continue
        item = resolver(file_id) or {}
        if not item:
            continue
        try:
            attachments.append(MediaStore.to_attachment(item))
        except Exception:
            continue
    return attachments


def build_openai_content_parts(parts: List[Dict[str, Any]], resolver: Callable[[str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build OpenAI-like content array for direct multimodal providers.
    """
    out: List[Dict[str, Any]] = []
    for part in parts or []:
        t = _part_type(part)
        if t == "text":
            text = _safe_text(part.get("text"))
            if text:
                out.append({"type": "text", "text": text})
            continue
        if t not in ("image", "video", "audio"):
            continue
        file_id = _safe_text(part.get("file_id"))
        if not file_id:
            continue
        item = resolver(file_id) or {}
        if not item:
            continue
        if t == "image":
            block = _image_item_to_openai_block(item)
            if block:
                out.append(block)
            continue
        if t == "audio":
            block = _audio_item_to_openai_block(item)
            if block:
                out.append(block)
            else:
                out.append({"type": "text", "text": f"[audio:{item.get('name') or file_id}]"})
            continue

        # OpenAI-compatible path: convert local video to keyframes and pass as image_url blocks.
        path = _safe_text(item.get("path"))
        if path and os.path.exists(path):
            frame_info = extract_video_frames(path, max_frames=3)
            frames = frame_info.get("frames") or []
            for frame_path in frames:
                frame_item = {
                    "storage": "local",
                    "path": frame_path,
                    "mime": "image/jpeg",
                    "name": os.path.basename(frame_path) or "video-frame.jpg",
                }
                block = _image_item_to_openai_block(frame_item)
                if block:
                    out.append(block)
            temp_dir = str(frame_info.get("temp_dir") or "").strip()
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass
            if frames:
                continue

        # URL videos or extraction failure: keep concise marker fallback.
        out.append({"type": "text", "text": f"[video:{item.get('name') or file_id}]"})
    return out


def build_anthropic_content_parts(parts: List[Dict[str, Any]], resolver: Callable[[str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build Anthropic content blocks directly from normalized parts.
    """
    out: List[Dict[str, Any]] = []
    for part in parts or []:
        t = _part_type(part)
        if t == "text":
            text = _safe_text(part.get("text"))
            if text:
                out.append({"type": "text", "text": text})
            continue

        if t == "image":
            file_id = _safe_text(part.get("file_id"))
            if not file_id:
                continue
            item = resolver(file_id) or {}
            if not item:
                continue
            block = _image_item_to_anthropic_block(item)
            if block:
                out.append(block)
            continue
        if t == "audio":
            file_id = _safe_text(part.get("file_id"))
            if not file_id:
                continue
            item = resolver(file_id) or {}
            if not item:
                continue
            out.append({"type": "text", "text": f"[audio:{item.get('name') or file_id}]"})
            continue

        if t != "video":
            continue

        # Anthropic video support differs by provider; convert keyframes to image blocks.
        file_id = _safe_text(part.get("file_id"))
        if not file_id:
            continue
        item = resolver(file_id) or {}
        if not item:
            continue
        path = _safe_text(item.get("path"))
        if not path or not os.path.exists(path):
            continue

        frame_info = extract_video_frames(path, max_frames=3)
        frames = frame_info.get("frames") or []
        for frame_path in frames:
            frame_item = {
                "storage": "local",
                "path": frame_path,
                "mime": "image/jpeg",
                "name": os.path.basename(frame_path) or "video-frame.jpg",
            }
            block = _image_item_to_anthropic_block(frame_item)
            if block:
                out.append(block)

        temp_dir = str(frame_info.get("temp_dir") or "").strip()
        if temp_dir:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
    return out


def compose_fallback_text_and_attachments(
    parts: List[Dict[str, Any]],
    resolver: Callable[[str], Dict[str, Any]],
    *,
    persona: str = "sisi",
) -> Dict[str, Any]:
    """
    Convert multimodal parts to concise text context for text-only persona pipelines.
    """
    text_blocks: List[str] = []
    media_blocks: List[str] = []
    attachments: List[Dict[str, Any]] = collect_attachments_from_parts(parts, resolver)

    for part in parts or []:
        part_type = _part_type(part)
        if part_type == "text":
            text = _safe_text(part.get("text"))
            if text:
                text_blocks.append(text)
            continue

        if part_type not in ("image", "video", "audio"):
            continue

        file_id = _safe_text(part.get("file_id"))
        item = resolver(file_id) if file_id else None
        if not item:
            continue

        if part_type == "image":
            summary = _compact_summary(summarize_image(item, persona=persona), limit=160)
            media_blocks.append(f"[图片] {summary}" if summary else "[图片]")
            continue
        if part_type == "audio":
            audio_name = _safe_text(item.get("name")) or "audio"
            duration_ms = int(item.get("duration_ms", 0) or 0)
            if duration_ms > 0:
                media_blocks.append(f"[音频] {audio_name} 时长{duration_ms // 1000}s")
            else:
                media_blocks.append(f"[音频] {audio_name}")
            continue

        # Video fallback: summarize a few sampled keyframes.
        video_line = "[视频]"
        path = _safe_text(item.get("path"))
        if path and os.path.exists(path):
            frame_info = extract_video_frames(path, max_frames=3)
            frames = frame_info.get("frames") or []
            frame_summaries: List[str] = []
            for frame_path in frames:
                fake_item = {
                    "storage": "local",
                    "path": frame_path,
                    "mime": "image/jpeg",
                    "name": "video-frame",
                }
                summary = _compact_summary(summarize_image(fake_item, persona=persona), limit=80)
                if summary:
                    frame_summaries.append(summary)

            temp_dir = str(frame_info.get("temp_dir") or "").strip()
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

            if frame_summaries:
                video_line = f"{video_line} 关键帧: {'；'.join(frame_summaries[:2])}"

        media_blocks.append(video_line)

    final_lines: List[str] = []
    if text_blocks:
        final_lines.append("\n".join(text_blocks))
    if media_blocks:
        final_lines.append("多模态:\n" + "\n".join(media_blocks))

    return {
        "text": "\n\n".join([x for x in final_lines if x]).strip(),
        "attachments": attachments,
    }
