from core.transport_control_lane import TransportControlCoordinator
import time


def test_parse_control_payload_supports_nested_payload():
    fields = TransportControlCoordinator.parse_control_payload(
        "type=interrupt;stream=s1;payload=priority=high&ts=1000"
    )
    assert fields["type"] == "interrupt"
    assert fields["stream"] == "s1"
    assert fields["priority"] == "high"
    assert fields["ts"] == "1000"


def test_handle_control_payload_updates_state(monkeypatch):
    coord = TransportControlCoordinator()
    monkeypatch.setattr(coord, "_apply_interrupt_fast_path", lambda: "pc_stream_stop")
    monkeypatch.setattr(coord, "_dispatch_interrupt_apply_async", lambda: "stop_music_async")

    now_ms = int(time.time() * 1000)
    got = coord.handle_control_payload(
        f"type=interrupt;stream=s1;priority=high;ts={now_ms}",
        source_lane="control_lane",
    )

    assert got["ok"] is True
    snapshot = coord.snapshot()
    assert snapshot["received"] == 1
    assert snapshot["interrupt"] == 1
    assert snapshot["last_source_lane"] == "control_lane"
    assert "stop_music_async" in snapshot["last_action"]


def test_handle_capture_fx_policy_report_updates_device_caps():
    coord = TransportControlCoordinator()
    now_ms = int(time.time() * 1000)

    got = coord.handle_control_payload(
        (
            f"type=heartbeat;stream=s1;priority=normal;ts={now_ms};"
            "payload=source=android_capture_fx&aec_available=true&ns_available=true&agc_available=false"
        ),
        source_lane="control_lane",
    )

    assert got["ok"] is True
    snapshot = coord.snapshot()
    assert snapshot["heartbeat"] == 1
    assert snapshot["device_aec_available"] is True
    assert snapshot["device_ns_available"] is True
    assert snapshot["device_agc_available"] is False
    assert "capture_fx" in snapshot["last_action"]


def test_handle_wake_hit_returns_error_when_handler_unbound():
    coord = TransportControlCoordinator()
    now_ms = int(time.time() * 1000)

    got = coord.handle_control_payload(
        f"type=wake_hit;stream=s1;priority=high;ts={now_ms};epoch=2;seq=3;payload=source=device_kws&keyword=sisi",
        source_lane="control_lane",
    )

    assert got["ok"] is False
    assert got["error"] == "wake_hit_unbound"
    assert got["action"] == "wake_hit_unbound"
    snapshot = coord.snapshot()
    assert snapshot["wake_hit"] == 1
    assert snapshot["last_action"] == "wake_hit_unbound"


def test_handle_wake_hit_dispatches_handler_and_updates_state():
    coord = TransportControlCoordinator()
    got_calls = []

    def _handler(*, fields, source_lane):
        got_calls.append((fields, source_lane))
        return True

    coord.set_wake_hit_handler(_handler)
    now_ms = int(time.time() * 1000)
    got = coord.handle_control_payload(
        f"type=wake_hit;stream=s1;priority=high;ts={now_ms};epoch=2;seq=3;payload=source=device_kws&keyword=sisi",
        source_lane="control_lane",
    )

    assert got["ok"] is True
    assert got["action"] == "wake_hit_applied"
    assert len(got_calls) == 1
    fields, lane = got_calls[0]
    assert lane == "control_lane"
    assert fields.get("source") == "device_kws"
    assert fields.get("keyword") == "sisi"

    snapshot = coord.snapshot()
    assert snapshot["wake_hit"] == 1
    assert snapshot["last_control_type"] == "wake_hit"
    assert snapshot["last_source_lane"] == "control_lane"


def test_handle_control_payload_drops_stale_seq_for_same_lane_stream_epoch(monkeypatch):
    coord = TransportControlCoordinator()
    monkeypatch.setattr(coord, "_apply_interrupt_fast_path", lambda: "pc_stream_stop")
    monkeypatch.setattr(coord, "_dispatch_interrupt_apply_async", lambda: "stop_music_async")
    now_ms = int(time.time() * 1000)

    first = coord.handle_control_payload(
        f"type=interrupt;stream=s1;priority=high;ts={now_ms};epoch=4;seq=5",
        source_lane="control_lane",
    )
    second = coord.handle_control_payload(
        f"type=interrupt;stream=s1;priority=high;ts={now_ms};epoch=4;seq=5",
        source_lane="control_lane",
    )

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["dropped"] is True
    assert second["action"] == "drop_stale_seq"

    snapshot = coord.snapshot()
    assert snapshot["drop_stale_seq"] == 1
