from pathlib import Path


def test_android_output_hub_uses_cross_segment_pacing_window():
    src = Path("utils/android_output_hub.py").read_text(encoding="utf-8")

    assert "_pacing_window_started_at" in src, (
        "AndroidOutputHub should keep a pacing window across segmented clips "
        "to avoid queue compression between consecutive TTS chunks."
    )
    assert "_pacing_window_pcm_bytes" in src, (
        "AndroidOutputHub should track paced bytes across segments, not only per clip."
    )
    assert "_pacing_window_reset_gap_seconds" in src, (
        "AndroidOutputHub should reset pacing window only after an idle gap."
    )
    assert "self._pacing_window_pcm_bytes += len(data)" in src, (
        "AndroidOutputHub.push_pcm should advance pacing window bytes when data is delivered."
    )
    assert "expected_elapsed = (paced_pcm_bytes + next_pcm_bytes)" in src, (
        "AndroidOutputHub._pace_clip_send should use pacing-window bytes for realtime pacing."
    )


def test_android_output_hub_reduces_send_ahead_budget():
    src = Path("utils/android_output_hub.py").read_text(encoding="utf-8")
    assert "_max_send_ahead_seconds = 0.02" in src, (
        "AndroidOutputHub should use a tighter send-ahead budget to reduce burst "
        "compression on segmented TTS."
    )
