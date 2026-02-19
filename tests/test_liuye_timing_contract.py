from types import SimpleNamespace
import threading

from evoliu.liuye_frontend.intelligent_liuye import IntelligentLiuye


class _FakeOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **create_kwargs: object())
        )


def _build_test_liuye(monkeypatch):
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
        "sisi_memory.chat_history.format_messages_as_text",
        lambda *args, **kwargs: "",
    )
    monkeypatch.setattr(
        "sisi_memory.chat_history.append_turn",
        lambda **kwargs: None,
    )

    liuye = object.__new__(IntelligentLiuye)
    liuye.name = "intelligent-liuye"
    liuye.sisi_config = {
        "liuye_stream_first_token_timeout_sec": "5",
        "sisi_llm_model": "grok-4.1-fast",
        "sisi_llm_api_key": "demo_key",
        "sisi_llm_base_url": "http://127.0.0.1:9999/v1",
    }
    liuye._response_lock = threading.Lock()
    liuye._is_generating_response = False
    liuye._pending_guild_events = []
    liuye._pending_guild_clarify_task_id = None
    liuye._pending_guild_clarify_question = None
    liuye._legacy_text_tool_enabled = False
    liuye.tool_registry = SimpleNamespace(
        list_tools=lambda: [{"name": "submit_task"}],
        execute=lambda *args, **kwargs: "TOOL_OK",
    )

    liuye._get_current_user_id = lambda speaker_id=None: "user1"
    liuye._should_force_guild_submit = lambda text: False
    liuye.get_liuye_prompt = lambda: "SYSTEM_PROMPT"
    liuye.get_analysis_model_config = lambda: {
        "api_key": "demo_key",
        "model": "demo_model",
        "base_url": "http://127.0.0.1:9999/v1",
        "temperature": 0.2,
        "max_tokens": 256,
    }
    liuye._get_sisi_core_instance = lambda: None
    liuye._log_llm_message_order = lambda messages: None
    liuye._should_use_llm_tools = lambda user_input: True
    liuye._build_llm_tools_schema = lambda: [
        {
            "type": "function",
            "function": {
                "name": "submit_task",
                "description": "submit",
                "parameters": {
                    "type": "object",
                    "properties": {"desc": {"type": "string"}},
                    "required": ["desc"],
                },
            },
        }
    ]
    liuye._inject_tool_result_prompt = lambda text: text
    liuye._process_emotion_triggers = lambda text: text
    liuye._process_pending_guild_events = lambda: None
    liuye._should_send_to_mobile = lambda text: False
    liuye._send_to_mobile_device = lambda text, title=None: None
    return liuye


def _build_stream_consumer(script_steps):
    state = {"idx": 0}

    def _consume(_stream_iter, on_text_delta=None, first_progress_timeout_sec=None):
        step = script_steps[state["idx"]]
        state["idx"] += 1
        for tok in step.get("tokens", []):
            if on_text_delta is not None:
                on_text_delta(tok)
        return SimpleNamespace(
            text=step.get("text", ""),
            tool_calls=step.get("tool_calls", []),
            finish_reason="stop",
            chunk_count=len(step.get("tokens", [])),
            first_chunk_summary="fake_chunk",
        )

    return _consume


def test_structured_tool_path_executes_tool_before_any_tts_claim(monkeypatch):
    monkeypatch.delenv("LIUYE_PRE_TOOL_STREAMING", raising=False)
    liuye = _build_test_liuye(monkeypatch)
    timeline = []

    liuye._generate_liuye_tts = lambda text, priority=5, send_to_web=True: timeline.append(("tts", text))
    liuye._execute_llm_tool_call = lambda tool_name, arguments_json: (
        timeline.append(("tool", tool_name)),
        "task queued",
    )[1]

    consume = _build_stream_consumer(
        [
            {
                "tokens": ["ok, I will submit this task now."],
                "text": "ok, I will submit this task now.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "submit_task",
                            "arguments": "{\"desc\":\"check weather\"}",
                        },
                    }
                ],
            },
            {
                "tokens": ["task has been submitted."],
                "text": "task has been submitted.",
                "tool_calls": [],
            },
        ]
    )
    monkeypatch.setattr("llm.llm_stream_adapter.consume_chat_completions_stream", consume)

    ret = IntelligentLiuye._process_user_input_sync(liuye, "ask guild to check weather")

    assert ret == "task has been submitted."
    assert timeline[0] == ("tool", "submit_task")
    assert not any(evt[0] == "tts" and "submit this task now" in evt[1] for evt in timeline)
    assert any(evt[0] == "tts" and "task has been submitted" in evt[1] for evt in timeline)


def test_structured_no_tool_call_still_outputs_response(monkeypatch):
    monkeypatch.delenv("LIUYE_PRE_TOOL_STREAMING", raising=False)
    liuye = _build_test_liuye(monkeypatch)
    timeline = []

    liuye._generate_liuye_tts = lambda text, priority=5, send_to_web=True: timeline.append(("tts", text))
    liuye._execute_llm_tool_call = lambda tool_name, arguments_json: timeline.append(("tool", tool_name))

    consume = _build_stream_consumer(
        [
            {
                "tokens": ["Beijing is sunny today."],
                "text": "Beijing is sunny today.",
                "tool_calls": [],
            }
        ]
    )
    monkeypatch.setattr("llm.llm_stream_adapter.consume_chat_completions_stream", consume)

    ret = IntelligentLiuye._process_user_input_sync(liuye, "how is weather today")

    assert ret == "Beijing is sunny today."
    assert not any(evt[0] == "tool" for evt in timeline)
    assert any(evt[0] == "tts" and "sunny" in evt[1] for evt in timeline)


def test_pre_tool_streaming_can_be_enabled_for_legacy_behavior(monkeypatch):
    monkeypatch.setenv("LIUYE_PRE_TOOL_STREAMING", "1")
    liuye = _build_test_liuye(monkeypatch)
    timeline = []

    liuye._generate_liuye_tts = lambda text, priority=5, send_to_web=True: timeline.append(("tts", text))
    liuye._execute_llm_tool_call = lambda tool_name, arguments_json: (
        timeline.append(("tool", tool_name)),
        "task queued",
    )[1]

    consume = _build_stream_consumer(
        [
            {
                "tokens": ["ok, I will submit this task now."],
                "text": "ok, I will submit this task now.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "submit_task",
                            "arguments": "{\"desc\":\"check weather\"}",
                        },
                    }
                ],
            },
            {
                "tokens": ["task has been submitted."],
                "text": "task has been submitted.",
                "tool_calls": [],
            },
        ]
    )
    monkeypatch.setattr("llm.llm_stream_adapter.consume_chat_completions_stream", consume)

    ret = IntelligentLiuye._process_user_input_sync(liuye, "ask guild to check weather")

    assert ret == "task has been submitted."
    assert timeline[0][0] == "tts"
    assert "submit this task now" in timeline[0][1]
