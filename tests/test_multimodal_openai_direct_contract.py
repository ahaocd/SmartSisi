from pathlib import Path


def test_question_uses_multimodal_blocks_for_openai_and_anthropic():
    src = Path("llm/liusisi.py").read_text(encoding="utf-8")
    assert 'llm_api_style in ("openai", "anthropic")' in src
    assert 'user_message = llm_user_content_parts' in src
