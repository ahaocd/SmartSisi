from ai_module.commands.intent_map import (
    build_client_control_event,
    resolve_intent_from_text,
    validate_intent_execution,
)


def test_resolve_interrupt_intent_and_pass_whitelist_gate():
    env = resolve_intent_from_text("别说了，停止")
    ok, reason = validate_intent_execution(env, "别说了，停止")
    assert env["intent"] == "interrupt_output"
    assert ok is True
    assert reason == "ok"


def test_negated_video_start_is_not_executed():
    env = resolve_intent_from_text("不要开始视频通话")
    ok, reason = validate_intent_execution(env, "不要开始视频通话")
    assert env["intent"] == ""
    assert ok is False
    assert reason == "no_intent"


def test_suffix_control_json_parsed_but_still_needs_anchor_match():
    text = '按你说的做 {"intent":"video_call_start","confidence":0.95,"args":{"provider":"openai"}}'
    env = resolve_intent_from_text(text, source="assistant")
    ok, reason = validate_intent_execution(env, "按你说的做")
    assert env["intent"] == "video_call_start"
    assert env["from_control_suffix"] is True
    assert ok is False
    assert reason == "anchor_mismatch"


def test_build_client_control_event_for_video_call():
    env = resolve_intent_from_text("开始视频通话")
    ok, reason = validate_intent_execution(env, "开始视频通话")
    evt = build_client_control_event(env, username="User")
    assert ok is True
    assert reason == "ok"
    assert evt["control_intent"]["intent"] == "video_call_start"
    assert evt["control_intent"]["action"] == "video_call_start"
    assert evt["Username"] == "User"

