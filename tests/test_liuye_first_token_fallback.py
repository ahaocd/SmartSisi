from types import SimpleNamespace
import threading

from evoliu.liuye_frontend.intelligent_liuye import IntelligentLiuye


def _build_liuye_instance():
    liuye = object.__new__(IntelligentLiuye)
    liuye.name = "intelligent-liuye-test"
    liuye.sisi_config = {
        "liuye_llm_model": "primary-model",
        "liuye_llm_api_key": "primary-key",
        "liuye_llm_base_url": "http://primary.test/v1",
        "liuye_llm_temperature": "0.3",
        "liuye_llm_max_tokens": "128",
        "liuye_stream_first_token_timeout_sec": "5",
        "sisi_llm_model": "grok-4.1-fast",
        "sisi_llm_api_key": "grok-key",
        "sisi_llm_base_url": "http://fallback-grok.test/v1",
    }

    liuye._response_lock = threading.Lock()
    liuye._is_generating_response = False
    liuye._pending_guild_events = []
    liuye._pending_guild_clarify_task_id = None
    liuye._pending_guild_clarify_question = None
    liuye._legacy_text_tool_enabled = False

    liuye._get_current_user_id = lambda speaker_id=None: "user1"
    liuye._should_force_guild_submit = lambda text: False
    liuye.get_liuye_prompt = lambda: "SYSTEM_PROMPT"
    liuye._log_llm_message_order = lambda messages: None
    liuye._should_use_llm_tools = lambda user_input: False
    liuye._build_llm_tools_schema = lambda: []
    liuye._inject_tool_result_prompt = lambda text: text
    liuye._process_emotion_triggers = lambda text: text
    liuye._process_pending_guild_events = lambda: None
    liuye._get_sisi_core_instance = lambda: None
    liuye._should_send_to_mobile = lambda text: False
    liuye._send_to_mobile_device = lambda text, title=None: None
    liuye._generate_liuye_tts = lambda text, priority=5, send_to_web=True: None

    liuye.tool_registry = SimpleNamespace(
        list_tools=lambda: [],
        execute=lambda *args, **kwargs: "",
    )
    return liuye


class _FakeOpenAI:
    init_calls = []
    create_calls = []

    def __init__(self, *args, **kwargs):
        self.base_url = kwargs.get("base_url")
        self.api_key = kwargs.get("api_key")
        _FakeOpenAI.init_calls.append({"base_url": self.base_url, "api_key": self.api_key})
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        _FakeOpenAI.create_calls.append(
            {
                "base_url": self.base_url,
                "model": kwargs.get("model"),
                "stream": kwargs.get("stream"),
            }
        )
        if self.base_url == "http://primary.test/v1":
            return "primary_stream"
        if self.base_url == "http://fallback-grok.test/v1":
            return "fallback_stream"
        return "unknown_stream"


def test_first_token_timeout_falls_back_to_grok(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)
    monkeypatch.setattr(
        "sisi_memory.context_kernel.resolve_canonical_user_id",
        lambda **kwargs: ("default_user", {}),
    )
    monkeypatch.setattr(
        "sisi_memory.context_kernel.get_flag",
        lambda *args, **kwargs: False,
        raising=False,
    )
    monkeypatch.setattr(
        "sisi_memory.chat_history.build_prompt_context",
        lambda **kwargs: SimpleNamespace(summary_text="", older_text="", recent_messages=[]),
    )
    monkeypatch.setattr(
        "sisi_memory.chat_history.append_turn",
        lambda **kwargs: None,
    )

    from llm.llm_stream_adapter import FirstProgressTimeoutError

    consume_calls = []

    def _fake_consume(stream_iter, on_text_delta=None, first_progress_timeout_sec=None):
        consume_calls.append(
            {
                "stream_iter": stream_iter,
                "first_progress_timeout_sec": first_progress_timeout_sec,
            }
        )
        if stream_iter == "primary_stream":
            raise FirstProgressTimeoutError("timeout")
        if on_text_delta is not None:
            on_text_delta("fallback ok")
        return SimpleNamespace(
            text="fallback ok",
            tool_calls=[],
            finish_reason="stop",
            chunk_count=1,
            first_chunk_summary="fake",
        )

    monkeypatch.setattr("llm.llm_stream_adapter.consume_chat_completions_stream", _fake_consume)

    liuye = _build_liuye_instance()
    result = IntelligentLiuye._process_user_input_sync(liuye, "hello")

    assert result == "fallback ok"
    assert len(_FakeOpenAI.init_calls) == 2
    assert _FakeOpenAI.init_calls[0]["base_url"] == "http://primary.test/v1"
    assert _FakeOpenAI.init_calls[1]["base_url"] == "http://fallback-grok.test/v1"
    assert _FakeOpenAI.create_calls[0]["model"] == "primary-model"
    assert _FakeOpenAI.create_calls[1]["model"] == "grok-4.1-fast"
    assert consume_calls[0]["first_progress_timeout_sec"] == 5.0
    assert consume_calls[1]["first_progress_timeout_sec"] is None
