class NullAecProcessor:
    def __init__(self, *args, **kwargs):
        self._ready = True

    def is_ready(self):
        return True

    def process(self, mic_bytes: bytes, ref_bytes: bytes) -> bytes:
        return mic_bytes
