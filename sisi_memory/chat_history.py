from __future__ import annotations

import configparser
import json
import random
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

import threading

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

Role = Literal["user", "assistant", "system", "tool"]
Mode = Literal["sisi", "liuye"]
Source = Literal["voice", "webui", "api", "console", "agent", "unknown"]


@dataclass(frozen=True)
class ChatEvent:
    event_id: str
    turn_id: str
    ts: float
    user_id: str
    mode: Mode
    source: Source
    role: Role
    text: str
    meta: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None


@dataclass
class PromptContext:
    recent_messages: List[Dict[str, str]]
    summary_text: str
    older_text: str


@dataclass(frozen=True)
class HistorySettings:
    enabled: bool = True
    history_root_dir: Path = Path(__file__).resolve().parent / "data" / "chat_history"
    recent_messages: int = 6
    recent_with_timestamp: bool = True
    turns_current: int = 10
    turns_older: int = 2
    archive_min_days: int = 90
    archive_samples: int = 5
    turns_other: int = 2
    other_mode_min_score: float = 0.2
    include_other_mode: bool = False
    prompt_use_rolling_summary: bool = False
    rolling_summary_enabled: bool = False
    summary_max_chars: int = 60


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def load_history_settings() -> HistorySettings:
    """
    读取 `SmartSisi/system.conf` 中的历史/上下文配置（没有就用默认值）。
    不依赖 config_util，避免引入额外全局耦合。
    """
    base_dir = Path(__file__).resolve().parents[1]  # SmartSisi/
    system_conf = base_dir / "system.conf"

    cfg = configparser.ConfigParser()
    if system_conf.exists():
        cfg.read(system_conf, encoding="utf-8")

    section = "key"
    get = lambda k, fallback=None: cfg.get(section, k, fallback=fallback) if cfg.has_section(section) else fallback

    enabled = _as_bool(get("history_enabled", None), True)

    root_dir_str = get("history_root_dir", None)
    default_root = Path(__file__).resolve().parent / "data" / "chat_history"
    root_dir = Path(root_dir_str) if root_dir_str else default_root

    def _as_int(k: str, default: int) -> int:
        try:
            return int(get(k, str(default)))
        except Exception:
            return default

    recent_messages = max(0, _as_int("history_recent_messages", 6))
    recent_with_timestamp = _as_bool(get("history_recent_with_timestamp", None), True)
    turns_current = max(0, _as_int("history_turns_current", 10))
    turns_older = max(0, _as_int("history_turns_older", 2))
    archive_min_days = max(0, _as_int("history_archive_min_days", 90))
    archive_samples = max(0, _as_int("history_archive_samples", 5))
    turns_other = max(0, _as_int("history_turns_other", 2))
    summary_max_chars = max(0, _as_int("rolling_summary_max_chars", 60))

    try:
        other_mode_min_score = float(get("history_other_mode_min_score", "0.2"))
    except Exception:
        other_mode_min_score = 0.2

    rolling_summary_enabled = _as_bool(get("rolling_summary_enabled", None), False)
    include_other_mode = _as_bool(get("history_include_other_mode", None), False)
    prompt_use_rolling_summary = _as_bool(get("history_prompt_use_rolling_summary", None), False)

    return HistorySettings(
        enabled=enabled,
        history_root_dir=root_dir,
        recent_messages=recent_messages,
        recent_with_timestamp=recent_with_timestamp,
        turns_current=turns_current,
        turns_older=turns_older,
        archive_min_days=archive_min_days,
        archive_samples=archive_samples,
        turns_other=turns_other,
        other_mode_min_score=other_mode_min_score,
        include_other_mode=include_other_mode,
        prompt_use_rolling_summary=prompt_use_rolling_summary,
        rolling_summary_enabled=rolling_summary_enabled,
        summary_max_chars=summary_max_chars,
    )


@dataclass(frozen=True)
class SummaryLLMSettings:
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 500
    temperature: float = 0.2


def load_summary_llm_settings() -> Optional[SummaryLLMSettings]:
    """
    Rolling summary 使用记忆模型配置（system.conf 的 memory_llm_*）。
    """
    base_dir = Path(__file__).resolve().parents[1]  # SmartSisi/
    system_conf = base_dir / "system.conf"

    cfg = configparser.ConfigParser()
    if system_conf.exists():
        cfg.read(system_conf, encoding="utf-8")

    section = "key"
    if not cfg.has_section(section):
        return None

    base_url = (cfg.get(section, "memory_llm_base_url", fallback="") or "").strip().rstrip("/")
    api_key = (cfg.get(section, "memory_llm_api_key", fallback="") or "").strip()
    model = (cfg.get(section, "memory_llm_model", fallback="") or "").strip()

    if not base_url or not api_key or not model:
        return None

    return SummaryLLMSettings(base_url=base_url, api_key=api_key, model=model, max_tokens=200, temperature=0.2)


_io_lock = Lock()


def _safe_user_dir(root: Path, user_id: str) -> Path:
    safe = "".join(ch for ch in (user_id or "") if ch.isalnum() or ch in ("_", "-", "."))
    return root / (safe or "default_user")


def _events_file(root: Path, user_id: str, ts: float) -> Path:
    lt = time.localtime(ts)
    return _safe_user_dir(root, user_id) / f"events-{lt.tm_year:04d}-{lt.tm_mon:02d}.jsonl"


def _daily_md_file(root: Path, user_id: str, ts: float) -> Path:
    lt = time.localtime(ts)
    return _safe_user_dir(root, user_id) / "daily" / f"{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.md"


def append_event(event: ChatEvent) -> None:
    settings = load_history_settings()
    if not settings.enabled:
        return

    root = settings.history_root_dir
    ts = float(event.ts)
    jsonl_path = _events_file(root, event.user_id, ts)
    md_path = _daily_md_file(root, event.user_id, ts)

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(asdict(event), ensure_ascii=False)
    md_time = time.strftime("%H:%M:%S", time.localtime(ts))
    md_line = f"- `{md_time}` `[mode={event.mode}]` **{event.role}**: {event.text}\n"

    with _io_lock:
        jsonl_path.open("a", encoding="utf-8").write(line + "\n")
        md_path.open("a", encoding="utf-8").write(md_line)

    _maybe_schedule_summary_update(event.user_id, event.mode)


_summary_worker_lock = Lock()
_last_summary_update_ts: Dict[str, float] = {}


def _maybe_schedule_summary_update(user_id: str, mode: Mode) -> None:
    settings = load_history_settings()
    if not settings.rolling_summary_enabled:
        return
    if requests is None:
        return

    now = time.time()
    key = f"{user_id}::{mode}"
    last = _last_summary_update_ts.get(key, 0.0)
    # 节流：避免每条事件都触发一次摘要调用
    if now - last < 60.0:
        return

    llm = load_summary_llm_settings()
    if llm is None:
        return

    def _run() -> None:
        # 同一时刻只跑一个（全局），避免并发打爆接口
        with _summary_worker_lock:
            _last_summary_update_ts[key] = time.time()
            try:
                _update_rolling_summary(user_id=user_id, mode=mode, llm=llm)
            except Exception:
                return

    threading.Thread(target=_run, daemon=True).start()


def _update_rolling_summary(user_id: str, mode: Mode, llm: SummaryLLMSettings) -> None:
    settings = load_history_settings()
    root = settings.history_root_dir
    user_dir = _safe_user_dir(root, user_id)
    files = _list_event_files(user_dir)
    if not files:
        return

    scan_lines: List[str] = []
    for p in reversed(files[-3:]):
        scan_lines.extend(_tail_lines(p, max_lines=500))
        if len(scan_lines) >= 800:
            break

    events = _parse_events(scan_lines)
    if not events:
        return
    events = [e for e in events if e.mode == mode]
    if not events:
        return

    # 摘要输入：只取近期一段，避免成本爆炸
    recent_events = events[-120:]
    recent_text = _format_events_as_messages(recent_events)

    prev_summary = get_rolling_summary(user_id, mode)
    sys_prompt = (
        "你是一个对话摘要器。任务：将对话滚动压缩成一段【中文】摘要，用于后续 prompt。\n"
        "要求：\n"
        "- 保留稳定事实（身份、偏好、项目目标、约定、未完成任务）。\n"
        "- 删除寒暄、重复、情绪化措辞和无关细节。\n"
        "- 不要逐句复述，不要引用原话，不要输出列表编号。\n"
        f"- 输出 2~4 个短事件，用“；”分隔，整段不超过 {settings.summary_max_chars} 字。"
    )
    user_prompt = (
        f"【已有摘要】\n{prev_summary.strip() or '（无）'}\n\n"
        f"【近期对话（用于更新摘要）】\n{recent_text}\n\n"
        "请输出更新后的摘要："
    )

    url = f"{llm.base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {llm.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": llm.model,
        "temperature": llm.temperature,
        "max_tokens": llm.max_tokens,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    summary_text = (
        (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if isinstance(data, dict)
        else ""
    )
    summary_text = _trim_summary(summary_text, settings.summary_max_chars)
    if summary_text:
        write_rolling_summary(user_id=user_id, mode=mode, summary_text=summary_text)


def append_turn(
    user_id: str,
    mode: Mode,
    source: Source,
    user_text: str,
    assistant_text: str,
    meta: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
) -> str:
    """
    写入一轮对话（同一个 turn_id）：user + assistant。
    同步落盘 JSONL + 当日 Markdown（极轻量，不做摘要/检索等慢操作）。
    """
    settings = load_history_settings()
    if not settings.enabled:
        return ""

    now = time.time()
    turn_id = str(uuid.uuid4())
    meta = meta or {}

    def _mk(role: Role, text: str) -> ChatEvent:
        return ChatEvent(
            event_id=str(uuid.uuid4()),
            turn_id=turn_id,
            ts=now,
            user_id=user_id,
            mode=mode,
            source=source,
            role=role,
            text=text,
            meta=meta,
            trace_id=trace_id,
        )

    if user_text:
        append_event(_mk("user", user_text))
    if assistant_text:
        append_event(_mk("assistant", assistant_text))
    return turn_id


def _summary_path(root: Path, user_id: str, mode: Mode) -> Path:
    return _safe_user_dir(root, user_id) / "summary" / mode / "rolling_summary.json"


def _trim_summary(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if not text or max_chars <= 0:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars].strip()


def get_rolling_summary(user_id: str, mode: Mode) -> str:
    settings = load_history_settings()
    if not settings.rolling_summary_enabled:
        return ""

    path = _summary_path(settings.history_root_dir, user_id, mode)
    if not path.exists():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (data.get("summary_text") or "").strip()
    except Exception:
        return ""


def write_rolling_summary(user_id: str, mode: Mode, summary_text: str) -> None:
    settings = load_history_settings()
    path = _summary_path(settings.history_root_dir, user_id, mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary_text": summary_text}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _list_event_files(user_dir: Path) -> List[Path]:
    return sorted(user_dir.glob("events-*.jsonl"))


def _tail_lines(path: Path, max_lines: int) -> List[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return lines[-max_lines:] if max_lines > 0 else []
    except Exception:
        return []


def _parse_events(lines: Iterable[str]) -> List[ChatEvent]:
    events: List[ChatEvent] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            events.append(ChatEvent(**obj))
        except Exception:
            continue
    events.sort(key=lambda e: e.ts)
    return events


def _extract_keywords(text: str) -> List[str]:
    text = (text or "").strip().lower()
    if not text:
        return []
    parts = re.split(r"[^\u4e00-\u9fffA-Za-z0-9_]+", text)
    return [p for p in parts if len(p) >= 2][:12]


_TS_RE = re.compile(r"\[ts:[^\]]+\]")
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CTRL_TAG_RE = re.compile(r"\{[^{}]*\}")


def _clean_text_for_prompt(text: str, role: Optional[str] = None) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = _THINK_RE.sub("", t)
    t = _TS_RE.sub("", t)
    if role and role != "user":
        # 防止模型被历史对话里的控制标记“带偏”（仅清理 {} 控制标记）
        t = _CTRL_TAG_RE.sub("", t)
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _related_score(query: str, text: str) -> float:
    kws = _extract_keywords(query)
    if not kws:
        return 0.0
    t = (text or "").lower()
    hits = sum(1 for k in kws if k in t)
    return hits / max(1, len(kws))


def _format_events_as_messages(events: List[ChatEvent]) -> str:
    lines: List[str] = []
    for e in events:
        text = _clean_text_for_prompt(e.text, role=e.role)
        if not text:
            continue
        lines.append(f"{text}")
    return "\n".join(lines).strip()


def _dedupe_events_for_prompt(events: List[ChatEvent]) -> List[ChatEvent]:
    """去重事件，防止同一轮被重复写入后污染上下文。"""
    uniq: List[ChatEvent] = []
    seen = set()
    for e in events:
        cleaned = _clean_text_for_prompt(e.text, role=e.role)
        if not cleaned:
            continue
        # 以秒级时间 + 角色 + 内容做轻量去重
        key = (int(float(e.ts)), e.mode, e.role, cleaned)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return uniq


def _events_to_messages(events: List[ChatEvent]) -> List[Dict[str, str]]:
    settings = load_history_settings()
    with_ts = bool(settings.recent_with_timestamp)
    messages: List[Dict[str, str]] = []
    for e in _dedupe_events_for_prompt(events):
        text = _clean_text_for_prompt(e.text, role=e.role)
        if not text:
            continue
        if with_ts:
            ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(e.ts)))
            speaker = "用户" if e.role == "user" else "助手"
            text = f"[time:{ts_str}] [{speaker}] {text}"
        if e.role == "user":
            messages.append({"role": "user", "content": text})
        else:
            messages.append({"role": "assistant", "content": text})
    return messages


def format_messages_as_text(messages: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for m in messages:
        role = m.get("role")
        content = _clean_text_for_prompt(m.get("content") or "", role=m.get("role"))
        if not content:
            continue
        lines.append(content)
    return "\n".join(lines).strip()


def _format_events_with_time(events: List[ChatEvent]) -> str:
    lines: List[str] = []
    for e in _dedupe_events_for_prompt(events):
        text = _clean_text_for_prompt(e.text, role=e.role)
        if not text:
            continue
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(e.ts)))
        if e.role == "user":
            speaker = (
                (e.meta or {}).get("speaker_name")
                or (e.meta or {}).get("voiceprint_real_name")
                or (e.meta or {}).get("user_external_id")
                or e.user_id
                or "user"
            )
        else:
            speaker = "LLM"
        lines.append(f"{ts} {speaker}: {text}")
    return "\n".join(lines).strip()


def build_handoff_messages(user_id: str, mode: Mode, turns: int = 2) -> List[Dict[str, str]]:
    settings = load_history_settings()
    if not settings.enabled or turns <= 0:
        return []

    root = settings.history_root_dir
    user_dir = _safe_user_dir(root, user_id)
    files = _list_event_files(user_dir)
    if not files:
        return []

    scan_lines: List[str] = []
    for p in reversed(files[-3:]):
        scan_lines.extend(_tail_lines(p, max_lines=800))
        if len(scan_lines) >= 1200:
            break

    events = _parse_events(scan_lines)
    if not events:
        return []

    turns_map: Dict[str, List[ChatEvent]] = {}
    order: List[str] = []
    for e in events:
        if e.mode != mode:
            continue
        if e.turn_id not in turns_map:
            turns_map[e.turn_id] = []
            order.append(e.turn_id)
        turns_map[e.turn_id].append(e)

    if not order:
        return []

    target_ids = order[-turns:]
    selected: List[ChatEvent] = []
    for tid in target_ids:
        selected.extend(sorted(turns_map.get(tid, []), key=lambda ev: ev.ts))

    return _events_to_messages(selected)


def build_prompt_context(
    user_id: str,
    current_mode: Mode,
    query_text: str,
    other_mode: Optional[Mode] = None,
    include_other: bool = False,
) -> PromptContext:
    """
    构建给 LLM 的“渐进式上下文”：
    - 摘要（rolling summary，可选，默认关闭）
    - 最近对话（结构化 messages）
    - 当前 mode 为主 + 另一 mode 少量且高相关（按关键词命中率打分）
    """
    settings = load_history_settings()
    if not settings.enabled:
        return PromptContext(recent_messages=[], summary_text="", older_text="")
    # 支持配置控制是否混入另一角色上下文
    include_other = bool(include_other or settings.include_other_mode)
    summary_text = get_rolling_summary(user_id, current_mode) if settings.prompt_use_rolling_summary else ""

    root = settings.history_root_dir
    user_dir = _safe_user_dir(root, user_id)
    files = _list_event_files(user_dir)
    if not files:
        return PromptContext(recent_messages=[], summary_text=summary_text, older_text="")

    scan_lines: List[str] = []
    for p in reversed(files[-3:]):
        scan_lines.extend(_tail_lines(p, max_lines=800))
        if len(scan_lines) >= 1200:
            break

    events = _parse_events(scan_lines)
    if not events:
        return PromptContext(recent_messages=[], summary_text=summary_text, older_text="")

    turns: Dict[str, List[ChatEvent]] = {}
    order: List[str] = []
    for e in events:
        if e.turn_id not in turns:
            turns[e.turn_id] = []
            order.append(e.turn_id)
        turns[e.turn_id].append(e)

    def _turn_text(tid: str) -> str:
        return " ".join(ev.text for ev in turns.get(tid, []) if ev.text)

    def _turn_mode(tid: str) -> Mode:
        evs = turns.get(tid, [])
        for ev in evs:
            if ev.mode:
                return ev.mode
        return current_mode

    current_turn_ids = [tid for tid in order if _turn_mode(tid) == current_mode]
    # 强制只取最近10轮
    # Use config (history_turns_current); default is 10 in load_history_settings.
    max_current_turns = settings.turns_current
    picked_current = current_turn_ids[-max_current_turns:] if max_current_turns else []

    current_events: List[ChatEvent] = []
    for tid in picked_current:
        current_events.extend(turns.get(tid, []))
    current_events.sort(key=lambda e: e.ts)
    recent_messages = _events_to_messages(current_events)

    older_raw = ""
    if settings.archive_samples:
        cutoff = time.time() - (settings.archive_min_days * 24 * 3600)
        archive_events = [
            e for e in events
            if e.mode == current_mode and float(e.ts) <= cutoff and (e.text or "").strip()
        ]
        if archive_events:
            k = min(settings.archive_samples, len(archive_events))
            picked = random.sample(archive_events, k=k)
            picked.sort(key=lambda e: e.ts)
            older_raw = _format_events_with_time(picked)

    other_raw = ""
    if include_other and settings.turns_other > 0:
        target_other_mode: Mode = other_mode or ("sisi" if current_mode == "liuye" else "liuye")
        other_turn_ids = [tid for tid in order if _turn_mode(tid) == target_other_mode]
        if other_turn_ids:
            scored: List[Tuple[str, float]] = []
            for tid in other_turn_ids:
                score = _related_score(query_text, _turn_text(tid))
                scored.append((tid, score))
            scored.sort(key=lambda item: (item[1], other_turn_ids.index(item[0])), reverse=True)

            picked_other_ids: List[str] = []
            for tid, score in scored:
                if score >= settings.other_mode_min_score:
                    picked_other_ids.append(tid)
                if len(picked_other_ids) >= settings.turns_other:
                    break

            # 如果没有命中相关度，至少补一轮最新的另一角色上下文，保证角色同步
            if not picked_other_ids and other_turn_ids:
                picked_other_ids = other_turn_ids[-1:]

            other_events: List[ChatEvent] = []
            for tid in picked_other_ids:
                other_events.extend(turns.get(tid, []))
            other_events.sort(key=lambda e: e.ts)
            if other_events:
                other_raw = _format_events_with_time(other_events)

    mixed_parts: List[str] = []
    if older_raw:
        mixed_parts.append("【长期历史参考（带时间）】\n" + older_raw)
    if other_raw:
        mixed_parts.append("【另一角色同步参考（带时间，仅参考）】\n" + other_raw)
    mixed_raw = "\n\n".join(mixed_parts).strip()

    return PromptContext(
        recent_messages=recent_messages,
        summary_text=summary_text,
        older_text=mixed_raw,
    )
