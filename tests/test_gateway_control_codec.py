from gateway.app.control_codec import (
    build_control_ack,
    extract_control_type,
    is_control_payload,
)


def test_control_marker_payload():
    payload = "<control>type=interrupt;stream=abc;priority=high</control>"
    assert is_control_payload(payload) is True
    assert extract_control_type(payload) == "interrupt"


def test_json_control_payload():
    payload = '{"type":"commit_turn","stream_id":"abc"}'
    assert is_control_payload(payload) is True
    assert extract_control_type(payload) == "commit_turn"


def test_build_control_ack_json():
    ack = build_control_ack(
        ok=True,
        session_id="s1",
        device_id="d1",
        control_type="interrupt",
        ts_ms=123,
    )
    assert '"type":"control_ack"' in ack
    assert '"ok":true' in ack
    assert '"session_id":"s1"' in ack
    assert '"device_id":"d1"' in ack
    assert '"control_type":"interrupt"' in ack
    assert '"ts_ms":123' in ack

