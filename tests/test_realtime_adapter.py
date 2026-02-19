import time

from llm import realtime_adapter as ra


def test_get_realtime_provider_config_openai_defaults(monkeypatch):
    values = {
        "realtime_openai_model": "gpt-realtime",
        "realtime_openai_api_key": "k-openai",
        "realtime_openai_ws_url": "wss://api.openai.com/v1/realtime",
        "realtime_openai_client_secret_url": "https://api.openai.com/v1/realtime/client_secrets",
    }
    monkeypatch.setattr(ra.config_util, "get_value", lambda k, d="": values.get(k, d), raising=False)

    cfg = ra.get_realtime_provider_config("openai", persona="sisi")

    assert cfg["provider"] == "openai"
    assert cfg["model"] == "gpt-realtime"
    assert cfg["api_key"] == "k-openai"
    assert cfg["ws_url"].startswith("wss://")
    assert any("realtime-webrtc" in x for x in cfg["docs"])


def test_normalize_realtime_event_openai_accumulates_text_and_intercepts_audio():
    session_id = "s1"
    r1 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_text.delta", "delta": "ni"},
        session_id=session_id,
    )
    r2 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_text.delta", "delta": "hao"},
        session_id=session_id,
    )
    r3 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_audio.delta", "delta": "AAA"},
        session_id=session_id,
    )
    r4 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.done", "response_id": ""},
        session_id=session_id,
    )

    assert r1["text_delta"] == "ni"
    assert r2["text_delta"] == "hao"
    assert r3["audio_intercepted"] is True
    assert r4["done"] is True
    assert r4["text_final"] == "nihao"


def test_normalize_realtime_event_openai_done_full_text_does_not_duplicate():
    session_id = "s1-done-full"
    response_id = "r1"

    ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_text.delta", "delta": "ni", "response_id": response_id},
        session_id=session_id,
    )
    ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_text.delta", "delta": "hao", "response_id": response_id},
        session_id=session_id,
    )
    done_hint = ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_text.done", "text": "nihao", "response_id": response_id},
        session_id=session_id,
    )
    done = ra.normalize_realtime_event(
        "openai",
        {"type": "response.done", "response_id": response_id},
        session_id=session_id,
    )

    assert done_hint["text_final"] == "nihao"
    assert done["text_final"] == "nihao"


def test_normalize_realtime_event_preserves_whitespace_in_deltas():
    session_id = "s1-space"
    response_id = "r2"

    ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_text.delta", "delta": "hello ", "response_id": response_id},
        session_id=session_id,
    )
    ra.normalize_realtime_event(
        "openai",
        {"type": "response.output_text.delta", "delta": "world", "response_id": response_id},
        session_id=session_id,
    )
    done = ra.normalize_realtime_event(
        "openai",
        {"type": "response.done", "response_id": response_id},
        session_id=session_id,
    )

    assert done["text_final"] == "hello world"


def test_normalize_realtime_event_openai_alias_audio_event_names_supported():
    session_id = "s1-alias"
    r1 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.audio_transcript.delta", "delta": "foo"},
        session_id=session_id,
    )
    r2 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.audio.delta", "delta": "AAA"},
        session_id=session_id,
    )
    r3 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.audio.done"},
        session_id=session_id,
    )
    r4 = ra.normalize_realtime_event(
        "openai",
        {"type": "response.done", "response_id": "default"},
        session_id=session_id,
    )

    assert r1["text_delta"] == "foo"
    assert r2["audio_intercepted"] is True
    assert r3["audio_intercepted"] is True
    assert r4["text_final"] == "foo"


def test_normalize_realtime_event_gemini_server_content_turn_complete():
    event = {
        "serverContent": {
            "modelTurn": {
                "parts": [
                    {"text": "hello"},
                    {"inlineData": {"mimeType": "audio/pcm", "data": "AAA"}},
                ]
            },
            "turnComplete": True,
        }
    }
    got = ra.normalize_realtime_event("gemini", event, session_id="g1")
    assert got["provider"] == "gemini"
    assert got["audio_intercepted"] is True
    assert got["done"] is True
    assert "hello" in got["text_final"]


def test_cleanup_text_buffers_by_session_and_ttl():
    provider = "openai"
    session_keep = "keep"
    session_drop = "drop"
    response_id = "default"

    ra.normalize_realtime_event(
        provider,
        {"type": "response.output_text.delta", "delta": "x"},
        session_id=session_keep,
    )
    ra.normalize_realtime_event(
        provider,
        {"type": "response.output_text.delta", "delta": "y"},
        session_id=session_drop,
    )

    key_drop = ra._buffer_key(provider, session_drop, response_id)
    with ra._TEXT_BUFFER_LOCK:
        ra._TEXT_BUFFER_UPDATED_AT[key_drop] = time.time() - 600

    stats = ra.cleanup_text_buffers(provider, session_id=session_drop, ttl_seconds=120)
    assert stats["provider_keys_removed"] == 1
    assert stats["provider_chars_removed"] == 1

    keep_done = ra.normalize_realtime_event(
        provider,
        {"type": "response.done", "response_id": response_id},
        session_id=session_keep,
    )
    drop_done = ra.normalize_realtime_event(
        provider,
        {"type": "response.done", "response_id": response_id},
        session_id=session_drop,
    )
    assert keep_done["text_final"] == "x"
    assert drop_done["text_final"] == ""


def test_pop_text_segment_if_ready_splits_and_keeps_tail():
    provider = "openai"
    session_id = "seg-1"
    response_id = "default"

    ra.normalize_realtime_event(
        provider,
        {"type": "response.output_text.delta", "delta": "A" * 220},
        session_id=session_id,
    )
    segment = ra.pop_text_segment_if_ready(
        provider,
        session_id,
        response_id,
        threshold_chars=180,
        min_segment_chars=80,
    )
    assert len(segment) >= 80
    assert len(segment) <= 180

    done = ra.normalize_realtime_event(
        provider,
        {"type": "response.done", "response_id": response_id},
        session_id=session_id,
    )
    assert done["text_final"] == ("A" * (220 - len(segment)))


def test_create_realtime_client_secret_parses_openai_payload(monkeypatch):
    class _Resp:
        ok = True
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"value": "secret-abc", "expires_at": 1770000000}

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = dict(headers or {})
        captured["json"] = dict(json or {})
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(ra.requests, "post", fake_post)

    got = ra.create_realtime_client_secret(
        {
            "provider": "openai",
            "api_key": "k-openai",
            "model": "gpt-realtime",
            "client_secret_url": "https://api.openai.com/v1/realtime/client_secrets",
        },
        ttl_seconds=180,
        session_overrides={"instructions": "speak chinese"},
    )

    assert got["provider"] == "openai"
    assert got["value"] == "secret-abc"
    assert captured["url"].endswith("/v1/realtime/client_secrets")
    assert captured["json"]["session"]["model"] == "gpt-realtime"
    assert captured["json"]["expires_after"]["seconds"] == 180


def test_build_realtime_turn_policy_openai_server_vad_interrupt():
    policy = ra.build_realtime_turn_policy(
        "openai",
        server_vad_enabled=True,
        interrupt_response_enabled=True,
        vad_threshold=0.61,
        vad_prefix_padding_ms=320,
        vad_silence_duration_ms=640,
    )
    assert policy["turn_detection"]["type"] == "server_vad"
    assert policy["turn_detection"]["interrupt_response"] is True
    assert policy["turn_detection"]["threshold"] == 0.61
    assert policy["audio"]["input"]["turn_detection"]["type"] == "server_vad"


def test_merge_realtime_session_overrides_keeps_nested_defaults():
    base = {
        "modalities": ["text", "audio"],
        "audio": {
            "input": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                }
            }
        },
    }
    overrides = {
        "audio": {
            "input": {
                "turn_detection": {
                    "threshold": 0.8,
                }
            }
        },
        "instructions": "mobile barge-in",
    }

    merged = ra.merge_realtime_session_overrides(base, overrides)
    assert merged["audio"]["input"]["turn_detection"]["type"] == "server_vad"
    assert merged["audio"]["input"]["turn_detection"]["threshold"] == 0.8
    assert merged["instructions"] == "mobile barge-in"
