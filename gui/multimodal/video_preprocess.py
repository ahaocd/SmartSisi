import os
import shutil
import subprocess
import tempfile
from typing import Dict, List


def _ffmpeg_exists() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_video_frames(
    video_path: str,
    *,
    max_frames: int = 8,
) -> Dict[str, object]:
    """
    Extract key frames by FPS sampling.
    Returns {"frames": [paths], "temp_dir": "...", "method": "ffmpeg|none"}.
    """
    p = str(video_path or "").strip()
    if not p or not os.path.exists(p):
        return {"frames": [], "temp_dir": "", "method": "none", "error": "video not found"}

    if not _ffmpeg_exists():
        return {"frames": [], "temp_dir": "", "method": "none", "error": "ffmpeg not found"}

    frame_count = max(1, int(max_frames or 8))
    temp_dir = tempfile.mkdtemp(prefix="mm_video_frames_")
    pattern = os.path.join(temp_dir, "frame_%03d.jpg")

    # Keep frame count bounded, but preserve clearer details per frame.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        p,
        "-vf",
        "fps=1,scale=1440:-2:flags=lanczos:force_original_aspect_ratio=decrease",
        "-frames:v",
        str(frame_count),
        "-q:v",
        "2",
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        return {"frames": [], "temp_dir": "", "method": "none", "error": str(e)}

    frames: List[str] = []
    for name in sorted(os.listdir(temp_dir)):
        if not name.lower().endswith(".jpg"):
            continue
        frames.append(os.path.join(temp_dir, name))
    return {"frames": frames, "temp_dir": temp_dir, "method": "ffmpeg"}
