import tempfile
from pathlib import Path

from llm.liusisi import send_llm_request
from llm.multimodal_adapter import build_anthropic_content_parts, build_openai_content_parts


class _DummyResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"content": [{"type": "text", "text": "ok"}]}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _DummySession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return _DummyResponse()


def test_build_anthropic_content_parts_with_local_image():
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "x.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfakepng")

        items = {
            "f1": {
                "id": "f1",
                "kind": "image",
                "storage": "local",
                "path": str(img),
                "mime": "image/png",
                "name": "x.png",
            }
        }

        def resolver(file_id):
            return items.get(file_id)

        blocks = build_anthropic_content_parts(
            [
                {"type": "text", "text": "看图"},
                {"type": "image", "file_id": "f1"},
            ],
            resolver,
        )

        assert len(blocks) == 2
        assert blocks[0]["type"] == "text"
        assert blocks[0]["text"] == "看图"
        assert blocks[1]["type"] == "image"
        assert blocks[1]["source"]["type"] == "base64"
        assert blocks[1]["source"]["media_type"] == "image/png"
        assert blocks[1]["source"]["data"]


def test_send_llm_request_anthropic_keeps_multimodal_blocks_and_retries_520():
    session = _DummySession(
        [
            _DummyResponse(status_code=520, payload={"error": "cf-520"}),
            _DummyResponse(status_code=200, payload={"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    llm_cfg = {
        "base_url": "https://example.com/v1",
        "api_key": "k",
        "model": "claude-haiku-4-5-20251001",
        "api_style": "anthropic",
    }
    req_data = {
        "messages": [
            {"role": "system", "content": "你是sisi"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看图回答"},
                    {"type": "image", "source": {"type": "url", "url": "https://example.com/x.png"}},
                ],
            },
        ],
    }

    res = send_llm_request(session, req_data, llm_cfg)

    assert res["text"] == "ok"
    assert len(session.calls) == 2
    last = session.calls[-1]
    assert last["url"] == "https://example.com/v1/messages"
    assert last["json"]["messages"][0]["role"] == "user"
    content_blocks = last["json"]["messages"][0]["content"]
    assert isinstance(content_blocks, list)
    assert content_blocks[0]["type"] == "text"
    assert content_blocks[1]["type"] == "image"
    assert content_blocks[1]["source"]["type"] == "url"


def test_send_llm_request_openai_keeps_multimodal_blocks():
    session = _DummySession(
        [
            _DummyResponse(
                status_code=200,
                payload={
                    "choices": [
                        {
                            "message": {
                                "content": "ok",
                            }
                        }
                    ]
                },
            )
        ]
    )
    llm_cfg = {
        "base_url": "https://example.com/v1",
        "api_key": "k",
        "model": "Pro/moonshotai/Kimi-K2.5",
        "api_style": "openai",
    }
    req_data = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看图回答"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,AAA=",
                        },
                    },
                ],
            }
        ],
    }

    res = send_llm_request(session, req_data, llm_cfg)

    assert res["text"] == "ok"
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://example.com/v1/chat/completions"
    content_blocks = call["json"]["messages"][0]["content"]
    assert isinstance(content_blocks, list)
    assert content_blocks[0]["type"] == "text"
    assert content_blocks[1]["type"] == "image_url"


def test_build_openai_content_parts_video_converts_frames(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        video = Path(d) / "x.mp4"
        video.write_bytes(b"fake-video")

        f1 = Path(d) / "f1.jpg"
        f2 = Path(d) / "f2.jpg"
        f1.write_bytes(b"\xff\xd8\xff\xe0fakejpg1")
        f2.write_bytes(b"\xff\xd8\xff\xe0fakejpg2")

        temp_dir = Path(d) / "frames_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        def fake_extract_video_frames(path, max_frames=3):
            assert str(video) == path
            assert max_frames == 3
            return {"frames": [str(f1), str(f2)], "temp_dir": str(temp_dir)}

        monkeypatch.setattr("llm.multimodal_adapter.extract_video_frames", fake_extract_video_frames)

        items = {
            "v1": {
                "id": "v1",
                "kind": "video",
                "storage": "local",
                "path": str(video),
                "mime": "video/mp4",
                "name": "x.mp4",
            }
        }

        def resolver(file_id):
            return items.get(file_id)

        blocks = build_openai_content_parts(
            [
                {"type": "text", "text": "看视频"},
                {"type": "video", "file_id": "v1"},
            ],
            resolver,
        )

        assert len(blocks) == 3
        assert blocks[0]["type"] == "text"
        assert blocks[1]["type"] == "image_url"
        assert blocks[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert blocks[2]["type"] == "image_url"
        assert blocks[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert not temp_dir.exists()
