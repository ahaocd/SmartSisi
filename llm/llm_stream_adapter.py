from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class FirstProgressTimeoutError(TimeoutError):
    """Raised when stream first progress is not observed within timeout."""


@dataclass(frozen=True)
class StreamConsumeResult:
    text: str
    tool_calls: List[Dict[str, Any]]
    finish_reason: Optional[str]
    chunk_count: int
    first_chunk_summary: str


def _as_str(x: Any) -> str:
    try:
        return str(x)
    except Exception:
        return ""


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _summarize_chunk(chunk: Any) -> str:
    try:
        c = chunk
        choices = _get(c, "choices", None)
        if isinstance(choices, list) and choices:
            ch0 = choices[0]
            delta = _get(ch0, "delta", None)
            keys = []
            if isinstance(delta, dict):
                keys = list(delta.keys())
            else:
                for k in ("content", "text", "tool_calls"):
                    if hasattr(delta, k):
                        keys.append(k)
            fr = _get(ch0, "finish_reason", None)
            return f"type={type(chunk).__name__} delta_keys={keys} finish_reason={fr}"
        return f"type={type(chunk).__name__}"
    except Exception:
        return f"type={type(chunk).__name__}"


def _extract_text_delta(delta: Any) -> str:
    """
    OpenAI-compatible streams usually expose delta.content; some providers use delta.text.
    """
    v = _get(delta, "content", None)
    if v:
        return _as_str(v)
    v = _get(delta, "text", None)
    if v:
        return _as_str(v)
    return ""


def _update_tool_calls_buffer(tool_calls_buffer: List[Dict[str, Any]], delta: Any) -> None:
    tool_calls = _get(delta, "tool_calls", None)
    if not tool_calls:
        return
    if not isinstance(tool_calls, list):
        return

    for tc in tool_calls:
        index = _get(tc, "index", None)
        try:
            index = int(index)
        except Exception:
            index = None

        tc_id = _as_str(_get(tc, "id", "")) or ""
        fn = _get(tc, "function", None)
        fn_name = _as_str(_get(fn, "name", "")) if fn is not None else ""
        fn_args = _as_str(_get(fn, "arguments", "")) if fn is not None else ""

        if index is None:
            tool_calls_buffer.append(
                {
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": fn_name, "arguments": fn_args},
                }
            )
            continue

        while index >= len(tool_calls_buffer):
            tool_calls_buffer.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})

        cur = tool_calls_buffer[index]
        if tc_id:
            cur["id"] = tc_id
        if fn_name:
            cur["function"]["name"] = fn_name
        if fn_args:
            cur["function"]["arguments"] = (cur["function"].get("arguments", "") or "") + fn_args


def _iter_with_first_progress_timeout(
    stream_iter: Any,
    first_progress_timeout_sec: Optional[float],
):
    """Yield stream chunks with a timeout guard for first progress only."""
    timeout = None
    try:
        if first_progress_timeout_sec is not None:
            timeout = float(first_progress_timeout_sec)
            if timeout <= 0:
                timeout = None
    except Exception:
        timeout = None

    if timeout is None:
        for chunk in stream_iter:
            yield chunk
        return

    stream_q = queue.Queue()

    def _producer() -> None:
        try:
            for chunk in stream_iter:
                stream_q.put(("chunk", chunk))
        except Exception as e:
            stream_q.put(("error", e))
        finally:
            stream_q.put(("done", None))

    producer_thread = threading.Thread(target=_producer, daemon=True)
    producer_thread.start()

    start_ts = time.monotonic()
    first_progress_seen = False

    while True:
        wait_timeout = None
        if not first_progress_seen:
            elapsed = time.monotonic() - start_ts
            remaining = timeout - elapsed
            if remaining <= 0:
                try:
                    close_fn = getattr(stream_iter, "close", None)
                    if callable(close_fn):
                        close_fn()
                except Exception:
                    pass
                raise FirstProgressTimeoutError(
                    f"stream first progress timeout after {timeout:.2f}s"
                )
            wait_timeout = min(remaining, 0.1)

        try:
            item_type, payload = stream_q.get(timeout=wait_timeout)
        except queue.Empty:
            continue

        if item_type == "chunk":
            first_progress_seen = True
            yield payload
            continue
        if item_type == "error":
            raise payload
        if item_type == "done":
            break


def consume_chat_completions_stream(
    stream_iter: Any,
    *,
    on_text_delta: Optional[Callable[[str], None]] = None,
    first_progress_timeout_sec: Optional[float] = None,
) -> StreamConsumeResult:
    """
    Consumes an OpenAI-compatible chat.completions streaming iterator.

    - Extracts text deltas (delta.content or delta.text)
    - Accumulates tool_calls across chunks (delta.tool_calls)
    - Returns a normalized result that never propagates an empty text silently
    """
    text_parts: List[str] = []
    tool_calls_buffer: List[Dict[str, Any]] = []
    finish_reason: Optional[str] = None
    chunk_count = 0
    first_chunk_summary = ""

    iter_source = _iter_with_first_progress_timeout(stream_iter, first_progress_timeout_sec)
    for chunk in iter_source:
        chunk_count += 1
        if chunk_count == 1:
            first_chunk_summary = _summarize_chunk(chunk)

        choices = _get(chunk, "choices", None)
        if not isinstance(choices, list) or not choices:
            continue
        ch0 = choices[0]
        delta = _get(ch0, "delta", None)
        if delta is None:
            continue

        token = _extract_text_delta(delta)
        if token:
            text_parts.append(token)
            if on_text_delta is not None:
                try:
                    on_text_delta(token)
                except Exception as e:
                    logger.debug(f"[llm_stream] on_text_delta_failed error={e}")

        _update_tool_calls_buffer(tool_calls_buffer, delta)

        fr = _get(ch0, "finish_reason", None)
        if fr:
            finish_reason = _as_str(fr)

    final_text = "".join(text_parts).strip()
    if not final_text and not tool_calls_buffer:
        msg = "(system did not receive a valid reply, please repeat your last sentence)"
        logger.error(f"[llm_stream] empty_stream chunk_count={chunk_count} finish_reason={finish_reason}")
        try:
            from sisi_memory.context_kernel import get_flag

            if get_flag("debug_llm_stream", False):
                logger.error(f"[llm_stream] first_chunk {first_chunk_summary}")
        except Exception:
            pass
        final_text = msg

    return StreamConsumeResult(
        text=final_text,
        tool_calls=tool_calls_buffer,
        finish_reason=finish_reason,
        chunk_count=chunk_count,
        first_chunk_summary=first_chunk_summary,
    )
