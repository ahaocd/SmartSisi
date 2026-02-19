from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from time import time
from typing import Dict, List, Optional


@dataclass
class SessionInfo:
    session_id: str
    device_id: str
    connected_at_ms: int
    last_seen_ms: int
    turn_id: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


class SessionRegistry:
    """In-memory session registry used by gateway app layer."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_session: Dict[str, SessionInfo] = {}
        self._active_by_device: Dict[str, str] = {}

    @staticmethod
    def _now_ms() -> int:
        return int(time() * 1000)

    def open_session(
        self,
        session_id: str,
        device_id: str,
        turn_id: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> SessionInfo:
        now = self._now_ms()
        info = SessionInfo(
            session_id=session_id,
            device_id=device_id,
            connected_at_ms=now,
            last_seen_ms=now,
            turn_id=turn_id,
            tags=dict(tags or {}),
        )
        with self._lock:
            self._by_session[session_id] = info
            self._active_by_device[device_id] = session_id
        return info

    def touch(self, session_id: str, turn_id: Optional[str] = None) -> bool:
        with self._lock:
            info = self._by_session.get(session_id)
            if info is None:
                return False
            info.last_seen_ms = self._now_ms()
            if turn_id is not None:
                info.turn_id = turn_id
            return True

    def close_session(self, session_id: str) -> bool:
        with self._lock:
            info = self._by_session.pop(session_id, None)
            if info is None:
                return False
            active = self._active_by_device.get(info.device_id)
            if active == session_id:
                self._active_by_device.pop(info.device_id, None)
            return True

    def get(self, session_id: str) -> Optional[SessionInfo]:
        with self._lock:
            info = self._by_session.get(session_id)
            if info is None:
                return None
            return SessionInfo(**info.__dict__)

    def get_active_by_device(self, device_id: str) -> Optional[SessionInfo]:
        with self._lock:
            session_id = self._active_by_device.get(device_id)
            if not session_id:
                return None
            info = self._by_session.get(session_id)
            if info is None:
                return None
            return SessionInfo(**info.__dict__)

    def list_sessions(self) -> List[SessionInfo]:
        with self._lock:
            return [SessionInfo(**s.__dict__) for s in self._by_session.values()]

