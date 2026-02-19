import os
import shutil
import tempfile
from pathlib import Path

from gui.multimodal.video_preprocess import extract_video_frames


def test_extract_video_frames_uses_high_quality_ffmpeg_flags(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        video = Path(d) / "sample.mp4"
        video.write_bytes(b"fake-video")
        captured = {}

        def fake_run(cmd, check, capture_output):
            captured["cmd"] = list(cmd)
            pattern = str(cmd[-1])
            out_dir = os.path.dirname(pattern)
            os.makedirs(out_dir, exist_ok=True)
            (Path(out_dir) / "frame_001.jpg").write_bytes(b"\xff\xd8\xff\xe0jpg1")
            (Path(out_dir) / "frame_002.jpg").write_bytes(b"\xff\xd8\xff\xe0jpg2")

        monkeypatch.setattr("gui.multimodal.video_preprocess._ffmpeg_exists", lambda: True)
        monkeypatch.setattr("gui.multimodal.video_preprocess.subprocess.run", fake_run)

        result = extract_video_frames(str(video), max_frames=3)

        assert result["method"] == "ffmpeg"
        assert len(result["frames"]) == 2
        cmd = captured["cmd"]
        assert "-q:v" in cmd
        assert "2" in cmd
        vf = cmd[cmd.index("-vf") + 1]
        assert "scale=1440:-2:flags=lanczos:force_original_aspect_ratio=decrease" in vf

        temp_dir = str(result.get("temp_dir") or "")
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_extract_video_frames_returns_error_when_ffmpeg_missing(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        video = Path(d) / "sample.mp4"
        video.write_bytes(b"fake-video")
        monkeypatch.setattr("gui.multimodal.video_preprocess._ffmpeg_exists", lambda: False)

        result = extract_video_frames(str(video), max_frames=3)

        assert result["frames"] == []
        assert result["method"] == "none"
        assert "ffmpeg not found" in str(result.get("error") or "")

