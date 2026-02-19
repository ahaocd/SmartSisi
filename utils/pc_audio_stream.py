import threading


class _PyAudioBackend:
    def __init__(self):
        import pyaudio

        self._pyaudio = pyaudio.PyAudio()

    def open_stream(self, sample_rate, channels, sample_width, frames_per_buffer):
        fmt = self._pyaudio.get_format_from_width(sample_width)
        return self._pyaudio.open(
            format=fmt,
            channels=channels,
            rate=sample_rate,
            output=True,
            frames_per_buffer=frames_per_buffer,
        )


class PCStream:
    def __init__(self, backend=None, pre_silence_ms=50):
        self._backend = backend or _PyAudioBackend()
        self._stream = None
        self._cfg = None
        self._lock = threading.Lock()
        self._primed = False
        self._pre_silence_ms = max(0, int(pre_silence_ms))

    def _ensure_open(self, sample_rate, channels, sample_width, frames_per_buffer):
        cfg = (sample_rate, channels, sample_width, frames_per_buffer)
        if self._stream is None or self._cfg != cfg:
            if self._stream:
                try:
                    self._stream.close()
                except Exception:
                    pass
            self._stream = self._backend.open_stream(
                sample_rate, channels, sample_width, frames_per_buffer
            )
            self._cfg = cfg
            self._primed = False

    def _write_silence_if_needed(self):
        if self._primed or self._pre_silence_ms <= 0:
            return
        sample_rate, channels, sample_width, _ = self._cfg
        total_samples = int(sample_rate * (self._pre_silence_ms / 1000.0))
        if total_samples <= 0:
            return
        silence = b"\x00" * (total_samples * channels * sample_width)
        self._stream.write(silence)
        self._primed = True

    def write_pcm(
        self, data, sample_rate, channels, sample_width, frames_per_buffer=1024
    ):
        if not data:
            return
        with self._lock:
            self._ensure_open(sample_rate, channels, sample_width, frames_per_buffer)
            self._write_silence_if_needed()
            self._stream.write(data)

    def close(self):
        with self._lock:
            if self._stream:
                self._stream.close()
                self._stream = None
                self._cfg = None


_pc_stream_singleton = None


def get_pc_stream():
    global _pc_stream_singleton
    if _pc_stream_singleton is None:
        _pc_stream_singleton = PCStream()
    return _pc_stream_singleton
