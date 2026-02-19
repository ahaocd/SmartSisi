from pathlib import Path


def test_legacy_chat_completions_uses_unified_persona_mainline():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "has_multimodal_media = False" in src
    assert "llm_user_content_parts = mm_blocks" in src
    assert 'persona = "liuye" if str(model).startswith("liuye") else "sisi"' in src
    assert "llm_override = _api_v1_build_multimodal_llm_override(persona)" in src
    assert "liusisi.set_system_mode(persona)" in src
    assert "llm_user_content_parts=llm_user_content_parts" in src
    assert "def _handle_sisi_request(username, msg, observation, stream, model, llm_override=None, llm_user_content_parts=None):" in src
    assert "return _handle_liuye_request(username, last_content, observation, stream)" not in src
