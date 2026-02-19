import ipaddress
import json
import mimetypes
import os
import threading
import time
import urllib.parse
import uuid
from typing import Any, Dict, Optional


class MediaStore:
    """Persist uploaded or registered media and expose manifest metadata."""

    IMAGE_MIME = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
    }
    VIDEO_MIME = {
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-matroska",
        "video/mpeg",
        "video/x-msvideo",
    }
    AUDIO_MIME = {
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/ogg",
        "audio/webm",
        "audio/mp4",
        "audio/aac",
        "audio/flac",
        "audio/x-flac",
        "audio/m4a",
    }
    IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".mpeg", ".mpg", ".avi"}
    AUDIO_EXT = {".mp3", ".wav", ".ogg", ".webm", ".m4a", ".aac", ".flac", ".opus"}

    def __init__(self, app_root: str):
        self._root = os.path.join(app_root, "runtime", "multimodal")
        self._upload_root = os.path.join(self._root, "uploads")
        self._manifest_path = os.path.join(self._root, "media_manifest.json")
        self._lock = threading.Lock()
        os.makedirs(self._upload_root, exist_ok=True)
        os.makedirs(self._root, exist_ok=True)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        raw = str(name or "").strip().replace("\\", "/")
        base = raw.split("/")[-1] if raw else "file"
        base = "".join(ch for ch in base if ch.isalnum() or ch in ("-", "_", ".", " "))
        base = base.strip().replace(" ", "_")
        return base or "file"

    @staticmethod
    def _kind_from_mime_or_name(mime: str, name: str) -> str:
        m = str(mime or "").lower().strip()
        ext = os.path.splitext(str(name or "").lower())[1]
        if m.startswith("image/"):
            return "image"
        if m.startswith("video/"):
            return "video"
        if m.startswith("audio/"):
            return "audio"
        if ext in MediaStore.IMAGE_EXT:
            return "image"
        if ext in MediaStore.VIDEO_EXT:
            return "video"
        if ext in MediaStore.AUDIO_EXT:
            return "audio"
        return "file"

    @staticmethod
    def _normalize_mime(mime: str, name: str) -> str:
        m = str(mime or "").lower().strip()
        if m:
            return m
        guessed, _ = mimetypes.guess_type(name or "")
        return str(guessed or "application/octet-stream")

    @staticmethod
    def _ensure_safe_http_url(url: str) -> None:
        parsed = urllib.parse.urlparse(str(url or "").strip())
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL must be http/https")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            raise ValueError("URL hostname missing")
        if host in ("localhost",) or host.endswith(".local"):
            raise ValueError("local URL is not allowed")
        ip = None
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip and (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError("private network URL is not allowed")

    def _load_manifest(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self._manifest_path):
            return {}
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_manifest(self, data: Dict[str, Dict[str, Any]]) -> None:
        tmp = f"{self._manifest_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, self._manifest_path)

    @staticmethod
    def _validate_type(kind: str, mime: str, name: str) -> None:
        ext = os.path.splitext(str(name or "").lower())[1]
        m = str(mime or "").lower().strip()
        if kind == "image":
            if m and m not in MediaStore.IMAGE_MIME:
                raise ValueError(f"unsupported image mime: {m}")
            if ext and ext not in MediaStore.IMAGE_EXT:
                raise ValueError(f"unsupported image extension: {ext}")
            return
        if kind == "video":
            if m and m not in MediaStore.VIDEO_MIME:
                raise ValueError(f"unsupported video mime: {m}")
            if ext and ext not in MediaStore.VIDEO_EXT:
                raise ValueError(f"unsupported video extension: {ext}")
            return
        if kind == "audio":
            if m and m not in MediaStore.AUDIO_MIME:
                raise ValueError(f"unsupported audio mime: {m}")
            if ext and ext not in MediaStore.AUDIO_EXT:
                raise ValueError(f"unsupported audio extension: {ext}")
            return
        raise ValueError("only image/video/audio uploads are supported")

    @staticmethod
    def _validate_size(kind: str, size: int, max_image_mb: int, max_video_mb: int, max_audio_mb: int) -> None:
        if size < 0:
            raise ValueError("invalid file size")
        if kind == "image":
            max_bytes = max_image_mb * 1024 * 1024
            limit_mb = max_image_mb
        elif kind == "video":
            max_bytes = max_video_mb * 1024 * 1024
            limit_mb = max_video_mb
        else:
            max_bytes = max_audio_mb * 1024 * 1024
            limit_mb = max_audio_mb
        if size > max_bytes:
            raise ValueError(f"{kind} exceeds limit {limit_mb}MB")

    def save_upload(self, file_storage, max_image_mb: int, max_video_mb: int, max_audio_mb: int) -> Dict[str, Any]:
        if not file_storage:
            raise ValueError("file is required")
        original_name = self._sanitize_name(getattr(file_storage, "filename", "") or "upload.bin")
        mime = self._normalize_mime(getattr(file_storage, "mimetype", "") or "", original_name)
        kind = self._kind_from_mime_or_name(mime, original_name)
        self._validate_type(kind, mime, original_name)
        file_id = f"file_{uuid.uuid4().hex}"
        ext = os.path.splitext(original_name)[1].lower()
        save_name = f"{file_id}{ext}"
        save_path = os.path.join(self._upload_root, save_name)
        size = 0
        if kind == "image":
            max_bytes = max_image_mb * 1024 * 1024
            limit_mb = max_image_mb
        elif kind == "video":
            max_bytes = max_video_mb * 1024 * 1024
            limit_mb = max_video_mb
        else:
            max_bytes = max_audio_mb * 1024 * 1024
            limit_mb = max_audio_mb
        stream = getattr(file_storage, "stream", None)
        if stream is None:
            raise ValueError("invalid file stream")
        with open(save_path, "wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    try:
                        os.remove(save_path)
                    except Exception:
                        pass
                    raise ValueError(f"{kind} exceeds limit {limit_mb}MB")
                out.write(chunk)
        self._validate_size(kind, size, max_image_mb, max_video_mb, max_audio_mb)

        item = {
            "id": file_id,
            "kind": kind,
            "name": original_name,
            "mime": mime,
            "size": int(size),
            "storage": "local",
            "path": save_path,
            "url": "",
            "created_at": time.time(),
        }
        with self._lock:
            data = self._load_manifest()
            data[file_id] = item
            self._save_manifest(data)
        return item

    def register_url(self, url: str, name: str = "", mime: str = "") -> Dict[str, Any]:
        self._ensure_safe_http_url(url)
        parsed = urllib.parse.urlparse(str(url).strip())
        from_path = os.path.basename(parsed.path or "")
        n = self._sanitize_name(name or from_path or "remote_asset")
        m = self._normalize_mime(mime, n)
        kind = self._kind_from_mime_or_name(m, n)
        self._validate_type(kind, m, n)

        file_id = f"file_{uuid.uuid4().hex}"
        item = {
            "id": file_id,
            "kind": kind,
            "name": n,
            "mime": m,
            "size": 0,
            "storage": "url",
            "path": "",
            "url": str(url).strip(),
            "created_at": time.time(),
        }
        with self._lock:
            data = self._load_manifest()
            data[file_id] = item
            self._save_manifest(data)
        return item

    def get(self, file_id: str) -> Optional[Dict[str, Any]]:
        if not file_id:
            return None
        with self._lock:
            return (self._load_manifest().get(file_id) or None)

    def delete(self, file_id: str) -> bool:
        if not file_id:
            return False
        with self._lock:
            data = self._load_manifest()
            item = data.get(file_id)
            if not item:
                return False
            if item.get("storage") == "local":
                p = item.get("path") or ""
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            data.pop(file_id, None)
            self._save_manifest(data)
            return True

    @staticmethod
    def to_attachment(item: Dict[str, Any]) -> Dict[str, Any]:
        file_id = item.get("id", "")
        if item.get("storage") == "url":
            preview = item.get("url", "")
            download = item.get("url", "")
        else:
            preview = f"/api/v1/media/{file_id}"
            download = f"/api/v1/media/{file_id}?download=1"
        return {
            "id": file_id,
            "kind": item.get("kind", "file"),
            "name": item.get("name", ""),
            "mime": item.get("mime", "application/octet-stream"),
            "size": int(item.get("size", 0) or 0),
            "preview_url": preview,
            "download_url": download,
            "thumbnail_url": item.get("thumbnail_url") or "",
            "duration_ms": int(item.get("duration_ms", 0) or 0),
            "source": item.get("source", "upload"),
        }
