import ctypes
import os


class SpeexAecProcessor:
    def __init__(self, sample_rate=16000, frame_ms=16, filter_length_ms=200, dll_path=""):
        self._sample_rate = int(sample_rate)
        self._frame_ms = int(frame_ms)
        self._filter_length_ms = int(filter_length_ms)
        self._frame_size = int(self._sample_rate * (self._frame_ms / 1000.0))
        self._filter_length = int(self._sample_rate * (self._filter_length_ms / 1000.0))
        self._state = None
        self._lib = None
        self._ready = False
        self._load_library(dll_path)
        if self._lib:
            self._init_state()

    def _load_library(self, dll_path):
        candidates = []
        if dll_path:
            candidates.append(dll_path)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates.append(os.path.join(base_dir, "audio", "aec", "libspeexdsp.dll"))
        candidates.append(os.path.join(base_dir, "libs", "libspeexdsp.dll"))

        for path in candidates:
            if path and os.path.exists(path):
                try:
                    self._lib = ctypes.WinDLL(path)
                    return
                except Exception:
                    self._lib = None
        self._lib = None

    def _init_state(self):
        try:
            self._lib.speex_echo_state_init.argtypes = [ctypes.c_int, ctypes.c_int]
            self._lib.speex_echo_state_init.restype = ctypes.c_void_p
            self._lib.speex_echo_state_destroy.argtypes = [ctypes.c_void_p]
            self._lib.speex_echo_ctl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            self._lib.speex_echo_cancellation.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_short),
                ctypes.POINTER(ctypes.c_short),
                ctypes.POINTER(ctypes.c_short),
            ]
            self._state = self._lib.speex_echo_state_init(
                ctypes.c_int(self._frame_size), ctypes.c_int(self._filter_length)
            )
            if self._state:
                rate = ctypes.c_int(self._sample_rate)
                self._lib.speex_echo_ctl(self._state, 24, ctypes.byref(rate))
            self._ready = bool(self._state)
        except Exception:
            self._state = None
            self._ready = False

    def is_ready(self):
        return self._ready

    def process(self, mic_bytes: bytes, ref_bytes: bytes) -> bytes:
        if not self._ready or not mic_bytes:
            return mic_bytes

        if not ref_bytes:
            ref_bytes = b"\x00" * len(mic_bytes)
        if len(ref_bytes) < len(mic_bytes):
            ref_bytes = ref_bytes + (b"\x00" * (len(mic_bytes) - len(ref_bytes)))
        elif len(ref_bytes) > len(mic_bytes):
            ref_bytes = ref_bytes[: len(mic_bytes)]

        frame_bytes = self._frame_size * 2
        out = bytearray()
        total = len(mic_bytes)
        offset = 0
        while offset + frame_bytes <= total:
            mic_frame = mic_bytes[offset : offset + frame_bytes]
            ref_frame = ref_bytes[offset : offset + frame_bytes]
            mic_arr = (ctypes.c_short * self._frame_size).from_buffer_copy(mic_frame)
            ref_arr = (ctypes.c_short * self._frame_size).from_buffer_copy(ref_frame)
            out_arr = (ctypes.c_short * self._frame_size)()
            self._lib.speex_echo_cancellation(self._state, mic_arr, ref_arr, out_arr)
            out.extend(bytes(out_arr))
            offset += frame_bytes

        if offset < total:
            out.extend(mic_bytes[offset:])
        return bytes(out)

    def close(self):
        try:
            if self._state and self._lib:
                self._lib.speex_echo_state_destroy(self._state)
        except Exception:
            pass
        self._state = None
        self._ready = False
