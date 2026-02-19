from pathlib import Path


def test_flask_server_has_realtime_session_and_event_routes():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "@__app.route('/api/v1/realtime/session', methods=['post'])" in src
    assert "@__app.route('/api/v1/realtime/event', methods=['post'])" in src
    assert "build_realtime_turn_policy(" in src
    assert "merge_realtime_session_overrides(" in src
    assert "_api_v1_emit_realtime_tts(" in src
    assert "normalize_realtime_event(provider, event, session_id=session_id)" in src
    assert '"audio_intercepted": bool(intercept_audio and normalized.get("audio_intercepted"))' in src
    assert "cleanup_text_buffers(" in src
    assert "pop_text_segment_if_ready(" in src
    assert '"buffer_cleanup": cleanup_stats' in src
    assert '"tts_segment_enqueued": tts_segment_enqueued' in src
    assert '"interrupt_policy": {' in src
    assert '"text_route": "transparent_pass"' in src


def test_realtime_segment_tts_uses_bounded_queue_worker_model():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "_API_V1_REALTIME_TTS_QUEUE_MAXSIZE" in src
    assert "_API_V1_REALTIME_TTS_WORKER_COUNT" in src
    assert "_api_v1_enqueue_realtime_tts(" in src
    assert "_api_v1_start_realtime_tts_workers(" in src
    assert "threading.Thread(target=_async_emit, daemon=True).start()" not in src


def test_realtime_segment_threshold_defaults_are_conservative():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "_API_V1_REALTIME_SEGMENT_THRESHOLD_DEFAULT = 260" in src
    assert "_API_V1_REALTIME_SEGMENT_MIN_DEFAULT = 120" in src
