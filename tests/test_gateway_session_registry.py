from gateway.app.session_registry import SessionRegistry


def test_open_touch_close_session():
    registry = SessionRegistry()

    info = registry.open_session(
        session_id="s1",
        device_id="d1",
        turn_id="t1",
        tags={"lane": "media"},
    )
    assert info.session_id == "s1"
    assert info.device_id == "d1"
    assert info.turn_id == "t1"

    assert registry.touch("s1", turn_id="t2") is True
    active = registry.get_active_by_device("d1")
    assert active is not None
    assert active.turn_id == "t2"

    assert registry.close_session("s1") is True
    assert registry.get("s1") is None
    assert registry.get_active_by_device("d1") is None

