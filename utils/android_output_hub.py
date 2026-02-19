import socket
import threading
import time
from typing import Any, Dict, Optional

from utils import util


START_FLAG = bytes([0, 1, 2, 3, 4, 5, 6, 7, 8])
END_FLAG = bytes([8, 7, 6, 5, 4, 3, 2, 1, 0])

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2
PCM_BYTES_PER_SECOND = TARGET_SAMPLE_RATE * TARGET_CHANNELS * TARGET_SAMPLE_WIDTH


class AndroidOutputHub:
    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = AndroidOutputHub()
        return cls._instance

    def __init__(self):
        self._lock = threading.Lock()
        self._active_sessions: Dict[int, Dict[str, Any]] = {}
        self._active_clip_label = ""
        self._active_clip_started_at = 0.0
        self._active_clip_pcm_bytes = 0
        self._realtime_pacing_enabled = True
        self._max_send_ahead_seconds = 0.02
        self._pacing_window_started_at = 0.0
        self._pacing_window_pcm_bytes = 0
        self._pacing_window_last_activity_at = 0.0
        self._pacing_window_reset_gap_seconds = 0.8
        # Legacy Android parser emits audio only after END marker.
        # Chunk mode wraps each PCM chunk with START/END so playback can stream.
        self._chunk_packet_mode = True

    def has_output_device(self, target_user: Optional[str] = None) -> bool:
        listeners = self._resolve_output_listeners(target_user=target_user)
        return bool(listeners)

    def begin_clip(self, label: Optional[str] = None, target_user: Optional[str] = None) -> bool:
        listeners = self._resolve_output_listeners(target_user=target_user)
        if not listeners:
            with self._lock:
                self._active_sessions = {}
                self._active_clip_label = label or ""
                self._active_clip_started_at = 0.0
                self._active_clip_pcm_bytes = 0
                self._pacing_window_started_at = 0.0
                self._pacing_window_pcm_bytes = 0
                self._pacing_window_last_activity_at = 0.0
            util.log(1, f"[transport] remote_audio_skip no_output_device label={label or 'audio'}")
            return False

        sessions: Dict[int, Dict[str, Any]] = {}
        for listener in listeners:
            session_key = id(listener)
            user_label = getattr(listener, "username", "unknown")
            try:
                if not self._chunk_packet_mode:
                    listener.deviceConnector.sendall(START_FLAG)
                sessions[session_key] = {
                    "listener": listener,
                    "user": user_label,
                    "bytes": 0,
                    "chunks": 0,
                }
            except socket.error:
                util.printInfo(1, user_label, "[transport] remote_audio_socket_disconnected")
                self._safe_stop_listener(listener)
            except Exception as e:
                util.printInfo(1, user_label, f"[transport] remote_audio_begin_failed: {str(e)}")
                self._safe_stop_listener(listener)

        now = time.perf_counter()
        with self._lock:
            self._active_sessions = sessions
            self._active_clip_label = label or ""
            self._active_clip_started_at = time.perf_counter()
            self._active_clip_pcm_bytes = 0
            if (
                self._pacing_window_started_at <= 0.0
                or (now - self._pacing_window_last_activity_at) > self._pacing_window_reset_gap_seconds
            ):
                self._pacing_window_started_at = now
                self._pacing_window_pcm_bytes = 0
            self._pacing_window_last_activity_at = now

        if sessions:
            util.log(
                1,
                f"[transport] remote_audio_begin users={len(sessions)} label={self._active_clip_label or 'audio'} chunk_mode={self._chunk_packet_mode}",
            )
        return bool(sessions)

    def push_pcm(self, data: bytes) -> int:
        if not data:
            return 0

        self._pace_clip_send(len(data))
        payload = self._build_payload(data)

        with self._lock:
            sessions_snapshot = list(self._active_sessions.items())

        delivered = 0
        for session_key, session in sessions_snapshot:
            listener = session.get("listener")
            user_label = session.get("user", "unknown")
            try:
                listener.deviceConnector.sendall(payload)
                delivered += 1
                with self._lock:
                    current = self._active_sessions.get(session_key)
                    if current is not None:
                        current["bytes"] += len(data)
                        current["chunks"] += 1
            except socket.error:
                util.printInfo(1, user_label, "[transport] remote_audio_socket_disconnected")
                self._remove_session(session_key, stop_listener=True)
            except Exception as e:
                util.printInfo(1, user_label, f"[transport] remote_audio_chunk_failed: {str(e)}")
                self._remove_session(session_key, stop_listener=True)

        if delivered > 0:
            now = time.perf_counter()
            with self._lock:
                self._active_clip_pcm_bytes += len(data)
                self._pacing_window_pcm_bytes += len(data)
                self._pacing_window_last_activity_at = now

        return delivered

    def end_clip(self, interrupted: bool = False):
        with self._lock:
            sessions = self._active_sessions
            clip_label = self._active_clip_label or "audio"
            clip_started_at = self._active_clip_started_at
            clip_pcm_bytes = self._active_clip_pcm_bytes
            self._active_sessions = {}
            self._active_clip_label = ""
            self._active_clip_started_at = 0.0
            self._active_clip_pcm_bytes = 0

        clip_send_seconds = 0.0
        if clip_started_at > 0:
            clip_send_seconds = max(0.0, time.perf_counter() - clip_started_at)
        clip_audio_seconds = clip_pcm_bytes / float(PCM_BYTES_PER_SECOND)
        clip_speed_x = 0.0
        if clip_send_seconds > 0:
            clip_speed_x = clip_audio_seconds / clip_send_seconds

        for session in sessions.values():
            listener = session.get("listener")
            user_label = session.get("user", "unknown")
            sent_bytes = int(session.get("bytes", 0))
            sent_chunks = int(session.get("chunks", 0))

            try:
                if not self._chunk_packet_mode:
                    listener.deviceConnector.sendall(END_FLAG)
            except socket.error:
                util.printInfo(1, user_label, "[transport] remote_audio_socket_disconnected")
                self._safe_stop_listener(listener)
            except Exception as e:
                util.printInfo(1, user_label, f"[transport] remote_audio_end_failed: {str(e)}")
                self._safe_stop_listener(listener)

            if interrupted:
                util.log(
                    1,
                    f"[transport] remote_audio_interrupted user={user_label} sent_bytes={sent_bytes} label={clip_label}",
                )
            util.log(
                1,
                f"[transport] remote_audio_sent bytes={sent_bytes} chunks={sent_chunks} user={user_label} payload=pcm16 label={clip_label} send_s={clip_send_seconds:.3f} audio_s={clip_audio_seconds:.3f} speed_x={clip_speed_x:.2f}",
            )

    def abort_clip(self):
        self.end_clip(interrupted=True)

    def _remove_session(self, session_key: int, stop_listener: bool = False):
        listener = None
        with self._lock:
            session = self._active_sessions.pop(session_key, None)
            if session:
                listener = session.get("listener")
        if stop_listener and listener is not None:
            self._safe_stop_listener(listener)

    def _resolve_output_listeners(self, target_user: Optional[str] = None):
        try:
            from core import sisi_booter  # delayed import

            listeners = list(getattr(sisi_booter, "DeviceInputListenerDict", {}).values())
        except Exception:
            return []

        matched = []
        for listener in listeners:
            if not getattr(listener, "isOutput", False):
                continue
            if target_user and getattr(listener, "username", None) != target_user:
                continue
            matched.append(listener)

        if matched:
            return matched

        if target_user:
            # Fallback to all output listeners if target user is not found.
            return [listener for listener in listeners if getattr(listener, "isOutput", False)]
        return []

    def _build_payload(self, pcm_data: bytes) -> bytes:
        if not self._chunk_packet_mode:
            return pcm_data
        return START_FLAG + pcm_data + END_FLAG

    def _pace_clip_send(self, next_pcm_bytes: int):
        with self._lock:
            pacing_window_started_at = self._pacing_window_started_at
            paced_pcm_bytes = self._pacing_window_pcm_bytes
            pacing_enabled = self._realtime_pacing_enabled

        if not pacing_enabled or pacing_window_started_at <= 0:
            return

        expected_elapsed = (paced_pcm_bytes + next_pcm_bytes) / float(PCM_BYTES_PER_SECOND)
        actual_elapsed = time.perf_counter() - pacing_window_started_at
        ahead_seconds = expected_elapsed - actual_elapsed
        sleep_seconds = ahead_seconds - self._max_send_ahead_seconds
        if sleep_seconds <= 0:
            return
        time.sleep(min(sleep_seconds, 0.2))

    @staticmethod
    def _safe_stop_listener(listener):
        try:
            listener.stop()
        except Exception:
            pass


def get_android_output_hub():
    return AndroidOutputHub.get_instance()
