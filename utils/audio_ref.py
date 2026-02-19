import threading
import time
from collections import deque


class PlaybackReferenceBuffer:
    def __init__(self, max_ms=2000, sample_rate=16000, sample_width=2):
        self._lock = threading.Lock()
        self._chunks = deque()
        self._size = 0
        self._max_bytes = int(sample_rate * (max_ms / 1000.0) * sample_width)
        self._playing = False
        self._last_play_start = 0.0
        self._last_play_stop = 0.0
        self._sample_rate = sample_rate
        self._sample_width = sample_width
        self._delay_bytes = 0
        self._pending_delay_bytes = 0

    def set_playing(self, playing: bool):
        now = time.time()
        with self._lock:
            if playing and not self._playing:
                self._last_play_start = now
                self._pending_delay_bytes = self._delay_bytes
                self._chunks.clear()
                self._size = 0
            if not playing and self._playing:
                self._last_play_stop = now
                self._chunks.clear()
                self._size = 0
            self._playing = playing

    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    def last_play_start(self) -> float:
        with self._lock:
            return self._last_play_start

    def last_play_stop(self) -> float:
        with self._lock:
            return self._last_play_stop

    def push_pcm(self, data: bytes):
        if not data:
            return
        with self._lock:
            self._chunks.append(data)
            self._size += len(data)
            while self._size > self._max_bytes and self._chunks:
                removed = self._chunks.popleft()
                self._size -= len(removed)

    def pop_pcm(self, n_bytes: int) -> bytes:
        if n_bytes <= 0:
            return b""
        out = bytearray()
        with self._lock:
            if self._pending_delay_bytes > 0:
                delay = min(n_bytes, self._pending_delay_bytes)
                out.extend(b"\x00" * delay)
                self._pending_delay_bytes -= delay
            need_bytes = n_bytes - len(out)
            while self._chunks and len(out) < n_bytes:
                chunk = self._chunks[0]
                need = n_bytes - len(out)
                if len(chunk) <= need:
                    out.extend(self._chunks.popleft())
                    self._size -= len(chunk)
                else:
                    out.extend(chunk[:need])
                    self._chunks[0] = chunk[need:]
                    self._size -= need
        if len(out) < n_bytes:
            out.extend(b"\x00" * (n_bytes - len(out)))
        return bytes(out)

    def set_delay_ms(self, delay_ms: int):
        if delay_ms is None:
            delay_ms = 0
        if delay_ms < 0:
            delay_ms = 0
        with self._lock:
            self._delay_bytes = int(self._sample_rate * (delay_ms / 1000.0) * self._sample_width)
            self._pending_delay_bytes = self._delay_bytes


_buffers = {}
_buffers_lock = threading.Lock()
_DEFAULT_KEY = "default"
_DEFAULT_MAX_MS = 2000
_DEFAULT_SAMPLE_RATE = 16000
_DEFAULT_SAMPLE_WIDTH = 2
_DEFAULT_DELAYS_MS = {
    "broadcast": 200,
}


def _normalize_key(key):
    return key or _DEFAULT_KEY


def _get_buffer(key):
    norm_key = _normalize_key(key)
    with _buffers_lock:
        buf = _buffers.get(norm_key)
        if buf is None:
            buf = PlaybackReferenceBuffer(
                max_ms=_DEFAULT_MAX_MS,
                sample_rate=_DEFAULT_SAMPLE_RATE,
                sample_width=_DEFAULT_SAMPLE_WIDTH,
            )
            delay_ms = _DEFAULT_DELAYS_MS.get(norm_key)
            if delay_ms is not None:
                buf.set_delay_ms(delay_ms)
            _buffers[norm_key] = buf
        return buf


def set_playing(playing: bool, key: str = None):
    _get_buffer(key).set_playing(playing)


def is_playing(key: str = None) -> bool:
    return _get_buffer(key).is_playing()


def last_play_start(key: str = None) -> float:
    return _get_buffer(key).last_play_start()


def last_play_stop(key: str = None) -> float:
    return _get_buffer(key).last_play_stop()


def push_playback_pcm(data: bytes, key: str = None):
    _get_buffer(key).push_pcm(data)


def pop_reference_pcm(n_bytes: int, key: str = None) -> bytes:
    return _get_buffer(key).pop_pcm(n_bytes)


def set_delay_ms(key: str, delay_ms: int):
    _get_buffer(key).set_delay_ms(delay_ms)


def should_suppress_input(now_ts: float, hold_ms: int, tail_ms: int, key: str = None) -> bool:
    if hold_ms <= 0 and tail_ms <= 0:
        return False
    buf = _get_buffer(key)
    playing = buf.is_playing()
    if playing:
        # While playback is active, keep suppressing mic input to avoid
        # self-trigger loops (TTS picked up by capture path). `hold_ms`
        # remains a minimum warmup window for legacy callers.
        start_ts = buf.last_play_start()
        if start_ts > 0 and (now_ts - start_ts) * 1000.0 < hold_ms:
            return True
        return True
    stop_ts = buf.last_play_stop()
    if stop_ts > 0 and (now_ts - stop_ts) * 1000.0 < tail_ms:
        return True
    return False
