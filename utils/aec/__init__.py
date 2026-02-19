from utils import config_util as cfg
from utils.aec.null_aec import NullAecProcessor
from utils.aec.speex_aec import SpeexAecProcessor

_logged_aec_error = False


def _log_aec_error_once(msg):
    global _logged_aec_error
    if _logged_aec_error:
        return
    _logged_aec_error = True
    try:
        from utils import util
        util.log(3, f"[错误][AEC] {msg}")
    except Exception:
        pass


def get_aec_processor(sample_rate=16000):
    cfg.load_config()
    enabled = str(getattr(cfg, "aec_enabled", "false")).lower() == "true"
    backend = (getattr(cfg, "aec_backend", "") or "speexdsp").strip().lower()
    required = str(getattr(cfg, "aec_required", "false")).lower() == "true"

    if not enabled:
        return NullAecProcessor()

    if backend == "speexdsp":
        proc = SpeexAecProcessor(
            sample_rate=sample_rate,
            frame_ms=int(getattr(cfg, "aec_frame_ms", 16)),
            filter_length_ms=int(getattr(cfg, "aec_filter_length_ms", 200)),
            dll_path=getattr(cfg, "aec_dll_path", ""),
        )
        if not proc.is_ready():
            _log_aec_error_once(
                f"configured AEC backend not available, dll_path='{getattr(cfg, 'aec_dll_path', '')}'"
            )
            if required:
                raise RuntimeError("Configured AEC backend not available")
            return NullAecProcessor()
        return proc

    if required:
        _log_aec_error_once("AEC backend is not available")
        raise RuntimeError("AEC backend is not available")
    return NullAecProcessor()
