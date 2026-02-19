import pytest

from gui.multimodal.input_normalizer import normalize_chat_parts
from gui.multimodal.media_store import MediaStore
from llm.multimodal_adapter import (
    build_anthropic_content_parts,
    build_openai_content_parts,
    compose_fallback_text_and_attachments,
)


def test_normalize_chat_parts_accepts_audio_file_id():
    items = {
        "a1": {
            "id": "a1",
            "kind": "audio",
            "storage": "url",
            "url": "https://example.com/speech.mp3",
            "mime": "audio/mpeg",
            "name": "speech.mp3",
            "size": 123,
        }
    }

    def resolver(file_id):
        return items.get(file_id)

    got = normalize_chat_parts(
        {
            "parts": [
                {"type": "text", "text": "listen"},
                {"type": "audio", "file_id": "a1"},
            ]
        },
        resolver,
    )

    assert got[0]["type"] == "text"
    assert got[1]["type"] == "audio"
    assert got[1]["mime"] == "audio/mpeg"


def test_build_openai_content_parts_supports_audio_data_uri(tmp_path):
    audio_path = tmp_path / "speech.mp3"
    audio_path.write_bytes(b"ID3fake")
    items = {
        "a1": {
            "id": "a1",
            "kind": "audio",
            "storage": "local",
            "path": str(audio_path),
            "mime": "audio/mpeg",
            "name": "speech.mp3",
        }
    }

    def resolver(file_id):
        return items.get(file_id)

    blocks = build_openai_content_parts(
        [
            {"type": "text", "text": "listen"},
            {"type": "audio", "file_id": "a1"},
        ],
        resolver,
    )

    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "audio_url"
    assert blocks[1]["audio_url"]["url"].startswith("data:audio/mpeg;base64,")


def test_build_anthropic_content_parts_audio_falls_back_to_text():
    items = {
        "a1": {
            "id": "a1",
            "kind": "audio",
            "storage": "url",
            "url": "https://example.com/speech.mp3",
            "mime": "audio/mpeg",
            "name": "speech.mp3",
        }
    }

    def resolver(file_id):
        return items.get(file_id)

    blocks = build_anthropic_content_parts([{"type": "audio", "file_id": "a1"}], resolver)
    assert blocks == [{"type": "text", "text": "[audio:speech.mp3]"}]


def test_compose_fallback_text_and_attachments_includes_audio():
    items = {
        "a1": {
            "id": "a1",
            "kind": "audio",
            "storage": "url",
            "url": "https://example.com/speech.mp3",
            "mime": "audio/mpeg",
            "name": "speech.mp3",
            "duration_ms": 3200,
        }
    }

    def resolver(file_id):
        return items.get(file_id)

    got = compose_fallback_text_and_attachments([{"type": "audio", "file_id": "a1"}], resolver)
    assert "[音频] speech.mp3" in got["text"]
    assert got["attachments"][0]["kind"] == "audio"


def test_media_store_audio_type_and_size_constraints():
    assert MediaStore._kind_from_mime_or_name("audio/mpeg", "speech.mp3") == "audio"
    assert MediaStore._kind_from_mime_or_name("audio/webm", "clip.webm") == "audio"
    MediaStore._validate_type("audio", "audio/mpeg", "speech.mp3")
    with pytest.raises(ValueError):
        MediaStore._validate_size("audio", 3 * 1024 * 1024, max_image_mb=1, max_video_mb=1, max_audio_mb=2)
