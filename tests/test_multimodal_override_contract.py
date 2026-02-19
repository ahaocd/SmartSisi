from pathlib import Path


def test_handle_chat_message_accepts_interact_and_callsite_passes_it():
    src = Path("core/sisi_core.py").read_text(encoding="utf-8")
    assert "def handle_chat_message(self, text, brain_prompts=None, interact=None):" in src
    assert "self.handle_chat_message(cleaned_msg, brain_prompts, interact=interact)" in src
    assert "\"llm_user_content_parts\"" in src


def test_v1_chat_messages_passes_multimodal_content_blocks():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "build_anthropic_content_parts(parts, _resolver_for_llm)" in src
    assert "multimodal_media_public_base_url" in src
    assert "llm_user_content_parts=llm_user_content_parts" in src
    assert "compose_fallback_text_and_attachments(" in src
    assert 'dispatch_text = str(fused_context.get("text") or "").strip()' in src
    assert 'in ("image", "video", "audio")' in src
    assert 'max_audio_mb=int(cfg.get("max_audio_mb", 80))' in src
