from pathlib import Path


def test_api_v1_chat_messages_has_control_intent_short_route():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "resolve_intent_from_text(dispatch_text, source=\"text\")" in src
    assert "validate_intent_execution(intent_env, dispatch_text)" in src
    assert "\"llm_route\": \"control_intent\"" in src
    assert "\"command_executed\": True" in src
    assert "build_client_control_event(intent_env, username=username)" in src
