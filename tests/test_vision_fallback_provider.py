from gui.multimodal import vision_fallback
from utils import config_util


def test_choose_vision_provider_prefers_multimodal_override(monkeypatch):
    monkeypatch.setattr(
        config_util,
        "get_multimodal_llm_override",
        lambda persona: {
            "base_url": "https://mm.example/v1",
            "api_key": "mm-key",
            "model": "mm-model",
        },
        raising=False,
    )
    monkeypatch.setattr(config_util, "image_model_api_key", "img-key", raising=False)
    monkeypatch.setattr(config_util, "image_model_base_url", "https://img.example/v1", raising=False)
    monkeypatch.setattr(config_util, "image_model_engine", "img-model", raising=False)

    got = vision_fallback._choose_vision_provider("sisi")
    assert got["base_url"] == "https://mm.example/v1"
    assert got["api_key"] == "mm-key"
    assert got["model"] == "mm-model"


def test_choose_vision_provider_uses_image_model_when_no_override(monkeypatch):
    monkeypatch.setattr(config_util, "get_multimodal_llm_override", lambda persona: None, raising=False)
    monkeypatch.setattr(config_util, "image_model_api_key", "img-key", raising=False)
    monkeypatch.setattr(config_util, "image_model_base_url", "https://img.example/v1", raising=False)
    monkeypatch.setattr(config_util, "image_model_engine", "img-model", raising=False)

    got = vision_fallback._choose_vision_provider("sisi")
    assert got["base_url"] == "https://img.example/v1"
    assert got["api_key"] == "img-key"
    assert got["model"] == "img-model"
