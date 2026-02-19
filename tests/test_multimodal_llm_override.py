import configparser

from utils import config_util


def _make_parser(values):
    parser = configparser.ConfigParser()
    parser.add_section("key")
    for k, v in values.items():
        parser.set("key", k, str(v))
    return parser


def test_multimodal_override_prefers_explicit_provider(monkeypatch):
    parser = _make_parser(
        {
            "multimodal_llm_base_url": "https://mm.example/v1",
            "multimodal_llm_api_key": "mm-key",
            "multimodal_llm_model": "mm-model",
        }
    )
    monkeypatch.setattr(config_util, "system_config", parser, raising=False)
    got = config_util.get_multimodal_llm_override("sisi")
    assert got["provider_id"] == "multimodal_llm"
    assert got["base_url"] == "https://mm.example/v1"
    assert got["api_key"] == "mm-key"
    assert got["model"] == "mm-model"


def test_multimodal_override_requires_explicit_multimodal_keys(monkeypatch):
    parser = _make_parser(
        {
            "agentss_base_url": "https://agent.example/v1",
            "agentss_api_key": "agent-key",
            "agentss_model_engine": "agent-model",
        }
    )
    monkeypatch.setattr(config_util, "system_config", parser, raising=False)
    assert config_util.get_multimodal_llm_override("sisi") is None


def test_multimodal_override_returns_none_when_incomplete(monkeypatch):
    parser = _make_parser(
        {
            "multimodal_llm_base_url": "https://mm.example/v1",
            "multimodal_llm_api_key": "",
            "multimodal_llm_model": "mm-model",
        }
    )
    monkeypatch.setattr(config_util, "system_config", parser, raising=False)
    got = config_util.get_multimodal_llm_override("sisi")
    assert got is None


def test_multimodal_override_claude_defaults_to_anthropic(monkeypatch):
    parser = _make_parser(
        {
            "multimodal_llm_base_url": "https://mm.example/v1",
            "multimodal_llm_api_key": "mm-key",
            "multimodal_llm_model": "claude-haiku-4-5-20251001",
        }
    )
    monkeypatch.setattr(config_util, "system_config", parser, raising=False)
    got = config_util.get_multimodal_llm_override("sisi")
    assert got["api_style"] == "anthropic"


def test_multimodal_override_honors_explicit_api_style(monkeypatch):
    parser = _make_parser(
        {
            "multimodal_llm_base_url": "https://mm.example/v1",
            "multimodal_llm_api_key": "mm-key",
            "multimodal_llm_model": "claude-haiku-4-5-20251001",
            "multimodal_llm_api_style": "openai",
        }
    )
    monkeypatch.setattr(config_util, "system_config", parser, raising=False)
    got = config_util.get_multimodal_llm_override("sisi")
    assert got["api_style"] == "openai"
