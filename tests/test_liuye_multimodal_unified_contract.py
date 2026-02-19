from pathlib import Path


def test_core_liuye_path_passes_interact_override_and_multimodal_parts():
    src = Path("core/sisi_core.py").read_text(encoding="utf-8")
    assert "return self._process_with_liuye(text, brain_prompts, interact=interact)" in src
    assert "def _process_with_liuye(self, text: str, brain_prompts=None, interact=None) -> tuple:" in src
    assert '"llm_user_content_parts": mm_parts' in src
    assert "llm_override=liuye_llm_override" in src


def test_intelligent_liuye_accepts_multimodal_override_and_user_content_parts():
    src = Path("evoliu/liuye_frontend/intelligent_liuye.py").read_text(encoding="utf-8")
    assert "llm_override: dict = None" in src
    assert 'if isinstance(user_input, dict) and isinstance(user_input.get("llm_user_content_parts"), list):' in src
    assert 'user_message=llm_user_content_parts if llm_user_content_parts else user_input_payload' in src
    assert 'analysis_config["base_url"] = base_url' in src
    assert 'analysis_config["model"] = model_name' in src
    assert 'chunks.append(f"[{part.get(\'type\') or \'part\'}]")' not in src
