import time
from types import SimpleNamespace

import pytest

from llm.llm_stream_adapter import (
    FirstProgressTimeoutError,
    consume_chat_completions_stream,
)


def _chunk(content=None, finish_reason=None):
    delta = SimpleNamespace(content=content)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _delayed_stream(delay_sec, content):
    time.sleep(delay_sec)
    yield _chunk(content=content, finish_reason="stop")


def test_first_progress_timeout_raises_when_stream_stalls():
    with pytest.raises(FirstProgressTimeoutError):
        consume_chat_completions_stream(
            _delayed_stream(0.2, "hello"),
            first_progress_timeout_sec=0.05,
        )


def test_first_progress_timeout_allows_normal_stream():
    result = consume_chat_completions_stream(
        _delayed_stream(0.01, "hello"),
        first_progress_timeout_sec=0.5,
    )
    assert result.text == "hello"
    assert result.chunk_count == 1
