import threading
import queue
import time
import audioop
import wave
import os
from collections import deque

from utils.pc_audio_stream import PCStream
from utils.android_output_hub import get_android_output_hub
from utils import util


class PCStreamSink:
    _END = object()

    def __init__(self, label=None):
        self.label = label or ""
        self._queue = queue.Queue()
        self._done = False
        self._lock = threading.Lock()
        self._buffered_bytes = 0

    def push(self, data: bytes):
        if not data:
            return
        with self._lock:
            self._buffered_bytes += len(data)
        self._queue.put(data)

    def finish(self):
        with self._lock:
            if self._done:
                return
            self._done = True
        self._queue.put(self._END)

    def is_done(self):
        with self._lock:
            return self._done

    def buffered_bytes(self):
        with self._lock:
            return self._buffered_bytes

    def pop(self, timeout=0.1):
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is self._END:
            return self._END
        with self._lock:
            self._buffered_bytes -= len(item)
        return item


class PCStreamQueue:
    TARGET_RATE = 16000
    TARGET_CHANNELS = 1
    TARGET_WIDTH = 2

    DEFAULT_PREFETCH_MS = 80
    DEFAULT_CROSSFADE_MS = 20
    DEFAULT_HEAD_TRIM_MS = 200
    DEFAULT_HEAD_TRIM_THRESHOLD = 200
    DEFAULT_TAIL_FLUSH_MS = 200
    DEFAULT_SEGMENT_FADE_IN_MS = 10
    DEFAULT_FIRST_EXTRA_FADE_IN_MS = 20

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PCStreamQueue()
        return cls._instance

    def __init__(self):
        self._streams = deque()
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._play_loop, daemon=True)
        self._pc_stream = PCStream(pre_silence_ms=0)
        self._interrupt_event = threading.Event()

        self.prefetch_ms = self.DEFAULT_PREFETCH_MS
        self.crossfade_ms = self.DEFAULT_CROSSFADE_MS
        self.head_trim_ms = self.DEFAULT_HEAD_TRIM_MS
        self.head_trim_threshold = self.DEFAULT_HEAD_TRIM_THRESHOLD
        self.tail_flush_ms = self.DEFAULT_TAIL_FLUSH_MS
        self.segment_fade_in_ms = self.DEFAULT_SEGMENT_FADE_IN_MS
        self.first_extra_fade_in_ms = self.DEFAULT_FIRST_EXTRA_FADE_IN_MS

        self._tail_buffer = bytearray()
        self._tail_timestamp = 0.0
        self._state_callback = None
        self._playing = False
        self._level_interval = 0.03
        self._last_level_ts = 0.0
        self._audio_ref_key = None
        self._audio_ref_mirror_broadcast = True
        self._output_diag_last_ts = 0.0
        self._output_diag_interval_s = 2.0
        self._output_diag_chunks = 0
        self._output_diag_pcm_bytes = 0
        self._output_diag_remote_chunks = 0
        self._output_diag_remote_bytes = 0
        self._output_diag_remote_zero = 0
        self._output_diag_local_chunks = 0
        self._output_diag_local_bytes = 0
        self._output_diag_local_fallback = 0

        # Unified output routing policy.
        self.local_playback_enabled = True
        self.remote_playback_enabled = True
        self.auto_disable_local_when_remote = True

        self._android_output_hub = get_android_output_hub()
        self._active_remote_clip = False
        self._active_local_playback = True

        self._thread.start()

    def set_state_callback(self, callback):
        self._state_callback = callback

    def set_output_policy(
        self,
        local_enabled=None,
        remote_enabled=None,
        auto_disable_local_when_remote=None,
    ):
        if local_enabled is not None:
            self.local_playback_enabled = bool(local_enabled)
        if remote_enabled is not None:
            self.remote_playback_enabled = bool(remote_enabled)
        if auto_disable_local_when_remote is not None:
            self.auto_disable_local_when_remote = bool(auto_disable_local_when_remote)

    def enqueue_stream(self, label=None):
        sink = PCStreamSink(label=label)
        with self._lock:
            self._streams.append(sink)
        return sink

    def enqueue_wav_file(self, file_path, label=None):
        sink = self.enqueue_stream(label=label)
        t = threading.Thread(
            target=self._stream_wav_file_to_sink,
            args=(file_path, sink),
            daemon=True,
        )
        t.start()
        return sink

    def stream_wav_file_to_sink(self, file_path, sink):
        self._stream_wav_file_to_sink(file_path, sink)

    def wait_until_idle(self, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.is_idle():
                return True
            time.sleep(0.05)
        return False

    def is_idle(self):
        with self._lock:
            if self._streams:
                return False
        if self._playing:
            return False
        return len(self._tail_buffer) == 0

    def stop(self):
        self._running = False

    def stop_all(self):
        """立即中断当前播放并清空队列"""
        self._interrupt_event.set()
        try:
            self._android_output_hub.abort_clip()
        except Exception:
            pass
        with self._lock:
            self._streams.clear()
        self._tail_buffer.clear()
        self._active_remote_clip = False
        self._active_local_playback = True
        self._set_playing(False)

    def interrupt(self):
        self.stop_all()

    @staticmethod
    def _convert_pcm(data, in_rate, in_channels, in_width, state):
        if not data:
            return b"", state

        pcm = data
        if in_channels == 2:
            pcm = audioop.tomono(pcm, in_width, 0.5, 0.5)
        elif in_channels != 1:
            step = in_channels * in_width
            pcm = b"".join([pcm[i:i + in_width] for i in range(0, len(pcm), step)])

        if in_width != 2:
            try:
                pcm = audioop.lin2lin(pcm, in_width, 2)
            except Exception:
                pcm = b""

        if in_rate != PCStreamQueue.TARGET_RATE and pcm:
            try:
                pcm, state = audioop.ratecv(
                    pcm, 2, 1, in_rate, PCStreamQueue.TARGET_RATE, state
                )
            except Exception:
                pcm = b""

        return pcm, state

    def _stream_wav_file_to_sink(self, file_path, sink):
        if not file_path:
            sink.finish()
            return
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            sink.finish()
            return

        ratecv_state = None
        try:
            with wave.open(abs_path, "rb") as wf:
                in_rate = wf.getframerate()
                in_channels = wf.getnchannels()
                in_width = wf.getsampwidth()
                chunk_frames = 1024
                while True:
                    frames = wf.readframes(chunk_frames)
                    if not frames:
                        break
                    pcm, ratecv_state = self._convert_pcm(
                        frames, in_rate, in_channels, in_width, ratecv_state
                    )
                    if pcm:
                        sink.push(pcm)
        except Exception:
            pass
        finally:
            sink.finish()

    def _play_loop(self):
        while self._running:
            if self._interrupt_event.is_set():
                with self._lock:
                    self._streams.clear()
                self._tail_buffer.clear()
                self._set_playing(False)
                self._interrupt_event.clear()
                time.sleep(0.01)
                continue

            sink = None
            with self._lock:
                if self._streams:
                    sink = self._streams.popleft()

            if sink is None:
                self._maybe_flush_tail()
                time.sleep(0.01)
                continue

            self._set_playing(True)
            self._play_sink(sink)
            self._set_playing(False)
            if self._interrupt_event.is_set():
                self._interrupt_event.clear()

    def _set_playing(self, playing):
        if self._playing == playing:
            return
        self._playing = playing
        try:
            from utils import audio_ref
            audio_ref.set_playing(playing, key=self._audio_ref_key)
            if self._audio_ref_mirror_broadcast:
                audio_ref.set_playing(playing, key="broadcast")
        except Exception:
            pass
        if self._state_callback:
            try:
                self._state_callback(playing)
            except Exception:
                pass
        try:
            from core import wsa_server
            web_instance = wsa_server.get_web_instance()
            if web_instance:
                if playing:
                    web_instance.add_cmd({"audio_event": "start"})
                    web_instance.add_cmd({"audio_command": "start"})
                    web_instance.add_cmd({"agent_status": "speaking"})
                else:
                    web_instance.add_cmd({"audio_event": "complete"})
                    web_instance.add_cmd({"audio_command": "stop"})
                    web_instance.add_cmd({"agent_status": "idle"})
                    web_instance.add_cmd({"audio_level": 0})
        except Exception:
            pass

    def _maybe_flush_tail(self):
        if not self._tail_buffer:
            return
        if (time.time() - self._tail_timestamp) * 1000.0 >= self.tail_flush_ms:
            self._write_pcm(bytes(self._tail_buffer))
            self._tail_buffer.clear()

    def _play_sink(self, sink):
        sink_label = getattr(sink, "label", "") or "audio"
        self._active_remote_clip = False
        self._active_local_playback = True

        if self.remote_playback_enabled:
            try:
                self._active_remote_clip = self._android_output_hub.begin_clip(label=sink_label)
            except Exception as e:
                util.log(2, f"[transport] remote_audio_begin_failed: {str(e)}")
                self._active_remote_clip = False

        if self.local_playback_enabled:
            self._active_local_playback = not (
                self.auto_disable_local_when_remote and self._active_remote_clip
            )
        else:
            self._active_local_playback = False

        route_name = "local_only"
        if self._active_remote_clip and self._active_local_playback:
            route_name = "dual"
        elif self._active_remote_clip and not self._active_local_playback:
            route_name = "remote_only"
        util.log(1, f"[transport] output_route mode={route_name} label={sink_label}")
        util.log(
            1,
            "[transport][ref_diag] clip_start label={} route={} remote_clip={} local_playback={} ref_key={} mirror_broadcast={}".format(
                sink_label,
                route_name,
                int(bool(self._active_remote_clip)),
                int(bool(self._active_local_playback)),
                self._audio_ref_key or "default",
                int(bool(self._audio_ref_mirror_broadcast)),
            ),
        )
        try:
            from core import wsa_server

            web_instance = wsa_server.get_web_instance()
            if web_instance:
                web_instance.add_cmd({"output_route": route_name, "output_route_label": sink_label})
        except Exception:
            pass

        prefetch_bytes = int(
            (self.prefetch_ms / 1000.0)
            * self.TARGET_RATE
            * self.TARGET_CHANNELS
            * self.TARGET_WIDTH
        )
        try:
            if prefetch_bytes > 0:
                self._wait_for_prefetch(sink, prefetch_bytes, timeout=1.0)

            stream_iter = self._iter_trimmed_chunks(sink)
            first = next(stream_iter, None)
            if first is None:
                return

            if self._tail_buffer:
                head = bytearray(first)
                while len(head) < self._crossfade_bytes():
                    nxt = next(stream_iter, None)
                    if nxt is None:
                        break
                    head.extend(nxt)
                head = bytearray(self._apply_fade_in(bytes(head), self.segment_fade_in_ms))
                mixed, remainder = self._crossfade(bytes(self._tail_buffer), bytes(head))
                self._tail_buffer.clear()
                if mixed:
                    self._write_pcm(mixed)
                if remainder:
                    self._output_buffered(remainder)
            else:
                fade_ms = self.segment_fade_in_ms + self.first_extra_fade_in_ms
                first = self._apply_fade_in(first, fade_ms)
                self._output_buffered(first)

            for chunk in stream_iter:
                if chunk:
                    self._output_buffered(chunk)

            self._tail_timestamp = time.time()
        finally:
            if self._active_remote_clip:
                has_pending_stream = False
                with self._lock:
                    has_pending_stream = bool(self._streams)
                if not has_pending_stream and self._tail_buffer:
                    self._write_pcm(bytes(self._tail_buffer))
                    self._tail_buffer.clear()
                self._android_output_hub.end_clip(interrupted=self._interrupt_event.is_set())
            self._active_remote_clip = False
            self._active_local_playback = True

    def _wait_for_prefetch(self, sink, min_bytes, timeout=1.0):
        end = time.time() + timeout
        while time.time() < end:
            if sink.buffered_bytes() >= min_bytes or sink.is_done():
                return True
            time.sleep(0.01)
        return False

    def _iter_trimmed_chunks(self, sink):
        max_trim_bytes = int(
            (self.head_trim_ms / 1000.0)
            * self.TARGET_RATE
            * self.TARGET_CHANNELS
            * self.TARGET_WIDTH
        )
        threshold = int(self.head_trim_threshold)
        trimmed = False
        head_buf = bytearray()

        while True:
            if self._interrupt_event.is_set():
                break
            chunk = sink.pop(timeout=0.05)
            if chunk is None:
                continue
            if chunk is PCStreamSink._END:
                if not trimmed and head_buf:
                    if len(head_buf) > max_trim_bytes:
                        head_buf = head_buf[max_trim_bytes:]
                    if head_buf:
                        yield bytes(head_buf)
                break

            if trimmed:
                yield chunk
                continue

            head_buf.extend(chunk)
            out, trimmed, head_buf = self._trim_buffer(
                head_buf, max_trim_bytes, threshold
            )
            if out:
                yield out

    @staticmethod
    def _trim_buffer(buf, max_trim_bytes, threshold):
        if not buf:
            return b"", False, buf
        scan_len = min(len(buf), max_trim_bytes)
        scan_len -= scan_len % 2
        if scan_len <= 0:
            return b"", False, buf

        for i in range(0, scan_len, 2):
            val = int.from_bytes(buf[i:i + 2], "little", signed=True)
            if abs(val) >= threshold:
                cut = i
                return bytes(buf[cut:]), True, bytearray()

        if len(buf) >= max_trim_bytes:
            return bytes(buf[scan_len:]), True, bytearray()

        return b"", False, buf

    def _crossfade_bytes(self):
        return int(
            (self.crossfade_ms / 1000.0)
            * self.TARGET_RATE
            * self.TARGET_CHANNELS
            * self.TARGET_WIDTH
        )

    @staticmethod
    def _crossfade(prev_tail, new_head):
        if not prev_tail or not new_head:
            return b"", new_head
        mix_len = min(len(prev_tail), len(new_head))
        mix_len -= mix_len % 2
        if mix_len <= 0:
            return b"", new_head

        out = bytearray(mix_len)
        total_samples = mix_len // 2
        for i in range(total_samples):
            a = int.from_bytes(prev_tail[i * 2:i * 2 + 2], "little", signed=True)
            b = int.from_bytes(new_head[i * 2:i * 2 + 2], "little", signed=True)
            if total_samples > 1:
                t = i / (total_samples - 1)
            else:
                t = 1.0
            val = int(a * (1.0 - t) + b * t)
            if val > 32767:
                val = 32767
            elif val < -32768:
                val = -32768
            out[i * 2:i * 2 + 2] = int(val).to_bytes(2, "little", signed=True)

        remainder = new_head[mix_len:]
        return bytes(out), remainder

    def _output_buffered(self, data):
        if not data:
            return
        if self._interrupt_event.is_set():
            return
        tail_keep = self._crossfade_bytes()
        if tail_keep <= 0:
            self._write_pcm(data)
            return

        combined = bytes(self._tail_buffer) + data
        if len(combined) <= tail_keep:
            self._tail_buffer = bytearray(combined)
            return

        out = combined[:-tail_keep]
        self._tail_buffer = bytearray(combined[-tail_keep:])
        if out:
            self._write_pcm(out)

    def _write_pcm(self, data):
        if not data:
            return
        if self._interrupt_event.is_set():
            return
        try:
            from utils import audio_ref
            audio_ref.push_playback_pcm(data, key=self._audio_ref_key)
            if self._audio_ref_mirror_broadcast:
                audio_ref.push_playback_pcm(data, key="broadcast")
        except Exception:
            pass
        try:
            now = time.time()
            if now - self._last_level_ts >= self._level_interval:
                rms = audioop.rms(data, 2)
                level = min(1.0, max(0.0, rms / 32768.0))
                from core import wsa_server
                web_instance = wsa_server.get_web_instance()
                if web_instance:
                    web_instance.add_cmd({"audio_level": level})
                self._last_level_ts = now
        except Exception:
            pass

        remote_delivered = 0
        if self._active_remote_clip:
            try:
                remote_delivered = self._android_output_hub.push_pcm(data)
            except Exception as e:
                util.log(2, f"[transport] remote_audio_chunk_failed: {str(e)}")

        should_write_local = self._active_local_playback
        local_fallback = False
        if (
            not should_write_local
            and self.auto_disable_local_when_remote
            and self.local_playback_enabled
            and self._active_remote_clip
            and remote_delivered <= 0
        ):
            should_write_local = True
            local_fallback = True

        local_written = False
        if should_write_local:
            self._pc_stream.write_pcm(
                data,
                sample_rate=self.TARGET_RATE,
                channels=self.TARGET_CHANNELS,
                sample_width=self.TARGET_WIDTH,
                frames_per_buffer=1024,
            )
            local_written = True

        self._record_output_diag(
            data_bytes=len(data),
            remote_delivered=remote_delivered,
            local_written=local_written,
            local_fallback=local_fallback,
        )

    def _apply_fade_in(self, data, fade_ms):
        if not data:
            return data
        fade_samples = int((fade_ms / 1000.0) * self.TARGET_RATE)
        if fade_samples <= 1:
            return data
        total_samples = len(data) // 2
        if total_samples <= 1:
            return data
        fade_samples = min(fade_samples, total_samples)
        buf = bytearray(data)
        for i in range(fade_samples):
            val = int.from_bytes(buf[i * 2:i * 2 + 2], "little", signed=True)
            t = i / (fade_samples - 1)
            scaled = int(val * t)
            if scaled > 32767:
                scaled = 32767
            elif scaled < -32768:
                scaled = -32768
            buf[i * 2:i * 2 + 2] = int(scaled).to_bytes(2, "little", signed=True)
        return bytes(buf)

    def _record_output_diag(self, data_bytes, remote_delivered, local_written, local_fallback):
        self._output_diag_chunks += 1
        self._output_diag_pcm_bytes += max(0, int(data_bytes))
        if remote_delivered > 0:
            self._output_diag_remote_chunks += 1
            self._output_diag_remote_bytes += int(remote_delivered)
        elif self._active_remote_clip:
            self._output_diag_remote_zero += 1
        if local_written:
            self._output_diag_local_chunks += 1
            self._output_diag_local_bytes += max(0, int(data_bytes))
        if local_fallback:
            self._output_diag_local_fallback += 1

        now = time.time()
        if now - self._output_diag_last_ts < self._output_diag_interval_s:
            return

        queue_depth = 0
        with self._lock:
            queue_depth = len(self._streams)

        util.log(
            1,
            (
                "[transport][ref_diag] key={} mirror_broadcast={} remote_clip={} local_playback={} "
                "chunks={} pcm_bytes={} remote_chunks={} remote_bytes={} remote_zero={} "
                "local_chunks={} local_bytes={} local_fallback={} queue={}"
            ).format(
                self._audio_ref_key or "default",
                int(bool(self._audio_ref_mirror_broadcast)),
                int(bool(self._active_remote_clip)),
                int(bool(self._active_local_playback)),
                int(self._output_diag_chunks),
                int(self._output_diag_pcm_bytes),
                int(self._output_diag_remote_chunks),
                int(self._output_diag_remote_bytes),
                int(self._output_diag_remote_zero),
                int(self._output_diag_local_chunks),
                int(self._output_diag_local_bytes),
                int(self._output_diag_local_fallback),
                int(queue_depth),
            ),
        )
        self._output_diag_last_ts = now
        self._output_diag_chunks = 0
        self._output_diag_pcm_bytes = 0
        self._output_diag_remote_chunks = 0
        self._output_diag_remote_bytes = 0
        self._output_diag_remote_zero = 0
        self._output_diag_local_chunks = 0
        self._output_diag_local_bytes = 0
        self._output_diag_local_fallback = 0


def get_pc_stream_queue():
    return PCStreamQueue.get_instance()
