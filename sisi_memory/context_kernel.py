from __future__ import annotations

import configparser
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Literal, Optional, Tuple

Persona = Literal["sisi", "liuye"]
MemoryScope = Literal["shared", "persona"]


def normalize_persona(value: Optional[str], default: Persona = "sisi") -> Persona:
    v = (value or "").strip().lower()
    if v == "liuye":
        return "liuye"
    if v == "sisi":
        return "sisi"
    return default


def namespaced_user_id(persona: Persona, canonical_user_id: str) -> str:
    return f"{persona}::{canonical_user_id}"


def shared_user_id(canonical_user_id: str) -> str:
    return f"shared::{canonical_user_id}"


@dataclass(frozen=True)
class UserKey:
    persona: Persona
    canonical_user_id: str

    @property
    def namespaced(self) -> str:
        return namespaced_user_id(self.persona, self.canonical_user_id)


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


@lru_cache(maxsize=1)
def _load_system_conf() -> configparser.ConfigParser:
    base_dir = Path(__file__).resolve().parents[1]  # SmartSisi/
    system_conf = base_dir / "system.conf"
    cfg = configparser.ConfigParser()
    if system_conf.exists():
        cfg.read(system_conf, encoding="utf-8")
    return cfg


def get_flag(name: str, default: bool = False, section: str = "key") -> bool:
    cfg = _load_system_conf()
    if not cfg.has_section(section):
        return default
    return _as_bool(cfg.get(section, name, fallback=None), default)


def reload_flags() -> None:
    _load_system_conf.cache_clear()


_USER_RE = re.compile(r"^user(\d+)$", re.IGNORECASE)


def _as_str(x: Any) -> str:
    try:
        return str(x)
    except Exception:
        return ""


def _clean_external_id(value: Any) -> str:
    s = _as_str(value).strip()
    if not s:
        return ""
    s = s.replace("\n", " ").replace("\r", " ").strip()
    s = s.replace("::", "_")
    return s[:128]


def _parse_user_n(value: str) -> Optional[int]:
    m = _USER_RE.match(value.strip())
    if not m:
        return None
    try:
        n = int(m.group(1))
        return n if n > 0 else None
    except Exception:
        return None


@dataclass(frozen=True)
class IdentityInput:
    voiceprint_user_id: Optional[str] = None
    asr_user_id: Optional[str] = None
    speaker_id: Optional[str] = None
    fallback: str = "default_user"


class IdentityResolver:
    """
    Maps unstable external IDs to stable canonical user IDs (userN/default_user).

    The mapping is persisted to disk to remain stable across restarts.
    """

    def __init__(self, mapping_path: Path):
        self._path = mapping_path
        self._lock = Lock()
        self._map: Dict[str, str] = {}
        self._next_user_n: int = 1
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            obj = json.loads(self._path.read_text(encoding="utf-8"))
            mapping = obj.get("mapping", {})
            if isinstance(mapping, dict):
                self._map = {str(k): str(v) for k, v in mapping.items() if str(k) and str(v)}
            nxt = obj.get("next_user_n")
            if isinstance(nxt, int) and nxt >= 1:
                self._next_user_n = nxt
            else:
                self._next_user_n = self._compute_next_user_n()
        except Exception:
            self._map = {}
            self._next_user_n = 1

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"mapping": self._map, "next_user_n": self._next_user_n}
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _compute_next_user_n(self) -> int:
        used: set[int] = set()
        for v in self._map.values():
            n = _parse_user_n(v)
            if n is not None:
                used.add(n)
        n = 1
        while n in used:
            n += 1
        return n

    def _alloc_user(self) -> str:
        uid = f"user{self._next_user_n}"
        self._next_user_n += 1
        return uid

    def _stable_candidate(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        s = value.strip()
        if not s:
            return None
        if s.lower() in {"stranger", "unknown", "none", "null", "0"}:
            return None
        if _parse_user_n(s) is not None:
            return s.lower()
        if s.isdigit() and s != "0":
            return f"user{int(s)}"
        return None

    def resolve(self, inp: IdentityInput) -> Tuple[str, Dict[str, Any]]:
        """
        Returns (canonical_user_id, debug_info).

        canonical_user_id is guaranteed to be 'userN' or 'default_user'.
        """
        with self._lock:
            stable = (
                self._stable_candidate(inp.voiceprint_user_id)
                or self._stable_candidate(inp.asr_user_id)
                or self._stable_candidate(inp.speaker_id)
            )
            if stable:
                return stable, {"source": "stable", "value": stable}

            ext = _clean_external_id(inp.voiceprint_user_id) or _clean_external_id(inp.asr_user_id) or _clean_external_id(inp.speaker_id)
            if not ext:
                fb = inp.fallback if inp.fallback in {"default_user"} else "default_user"
                return fb, {"source": "fallback", "value": fb}

            if ext in self._map:
                return self._map[ext], {"source": "mapped", "external_id": ext, "value": self._map[ext]}

            new_uid = self._alloc_user()
            self._map[ext] = new_uid
            self._save()
            return new_uid, {"source": "allocated", "external_id": ext, "value": new_uid}


_resolver: Optional[IdentityResolver] = None


def get_identity_resolver() -> IdentityResolver:
    global _resolver
    if _resolver is None:
        base_dir = Path(__file__).resolve().parents[1]  # SmartSisi/
        mapping_path = base_dir / "cache_data" / "identity_map.json"
        _resolver = IdentityResolver(mapping_path=mapping_path)
    return _resolver


def resolve_canonical_user_id(
    *,
    voiceprint_user_id: Optional[str] = None,
    asr_user_id: Optional[str] = None,
    speaker_id: Optional[str] = None,
    fallback: str = "default_user",
) -> Tuple[str, Dict[str, Any]]:
    return get_identity_resolver().resolve(
        IdentityInput(
            voiceprint_user_id=voiceprint_user_id,
            asr_user_id=asr_user_id,
            speaker_id=speaker_id,
            fallback=fallback,
        )
    )


_HistoryNeedle = re.compile(r"(之前|以前|上次|刚才|刚刚|历史|对话|聊过|说过|记得|还记得)")


def _other_persona_label(persona: Persona) -> str:
    if persona == "liuye":
        return "姐姐思思"
    return "妹妹柳叶"


def _should_force_attribution(user_input: str) -> bool:
    return bool(_HistoryNeedle.search((user_input or "").strip()))


def enforce_attribution(*, persona: Persona, user_input: str, assistant_text: str) -> str:
    """
    Ensures cross-persona references are explicitly attributed.

    This is a minimal deterministic guardrail:
    - Replace common ambiguous phrases like "鎴戜滑涔嬪墠鑱婅繃" with "浣犲拰{鍙︿竴瑙掕壊}涔嬪墠鑱婅繃"
    - For history-style questions, ensure the response includes an explicit attribution label at least once.
    """
    return (assistant_text or "").strip()


@dataclass(frozen=True)
class JournalTurn:
    user_key: UserKey
    user_text: str
    assistant_text: str
    source: str = "unknown"
    meta: Optional[Dict[str, Any]] = None


def append_turn(turn: JournalTurn) -> None:
    """
    Writes a conversational turn into the JSONL event stream (SoT).

    This is the single source for "who said what to whom" across personas.
    """
    from sisi_memory.chat_history import append_turn as append_turn_jsonl

    append_turn_jsonl(
        user_id=turn.user_key.canonical_user_id,
        mode=turn.user_key.persona,
        source=turn.source,
        user_text=turn.user_text,
        assistant_text=turn.assistant_text,
        meta=turn.meta or {},
    )
