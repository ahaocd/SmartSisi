import configparser

from utils import config_util


def test_get_multimodal_config_reads_audio_limit(monkeypatch):
    parser = configparser.ConfigParser()
    parser.add_section("key")
    parser.set("key", "multimodal_max_image_mb", "22")
    parser.set("key", "multimodal_max_video_mb", "333")
    parser.set("key", "multimodal_max_audio_mb", "66")
    parser.set("key", "multimodal_allowed_sources", "local,url")
    parser.set("key", "multimodal_strategy", "direct_first")
    parser.set("key", "multimodal_retention", "manual_only")

    monkeypatch.setattr(config_util, "system_config", parser, raising=False)
    got = config_util.get_multimodal_config()

    assert got["max_image_mb"] == 22
    assert got["max_video_mb"] == 333
    assert got["max_audio_mb"] == 66

