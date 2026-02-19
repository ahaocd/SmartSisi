from pathlib import Path
import threading

from evoliu.liuye_frontend.intelligent_liuye import IntelligentLiuye


class _DummyGuild:
    def __init__(self, ready=False):
        self.listener_ready = bool(ready)
        self.listener_running = False
        self.pending_tasks = []
        self.ensure_calls = 0
        self.subscribe_calls = 0
        self.submit_calls = []

    def ensure_listener_started(self):
        self.ensure_calls += 1
        return True

    def subscribe(self, cb):
        self.subscribe_calls += 1
        self._callback = cb
        return "unsubscribe_token"

    def submit_task(self, description):
        self.submit_calls.append(description)
        return "task_demo_1"


def test_handoff_messages_forwarded_to_message_builder_contract():
    src = Path("evoliu/liuye_frontend/intelligent_liuye.py").read_text(encoding="utf-8")
    assert "handoff_messages=handoff_messages" in src


def test_structured_tools_and_legacy_text_router_contract():
    src = Path("evoliu/liuye_frontend/intelligent_liuye.py").read_text(encoding="utf-8")
    assert 'LIUYE_STRUCTURED_TOOLS", "1"' in src
    assert 'LIUYE_LEGACY_TEXT_TOOL_ROUTER", "0"' in src
    assert "return True" in src  # _should_use_llm_tools 默认启用


def test_submit_task_offline_is_queued_instead_of_rejected(monkeypatch):
    dummy_guild = _DummyGuild(ready=False)
    monkeypatch.setattr(IntelligentLiuye, "guild", property(lambda self: dummy_guild))

    liuye = object.__new__(IntelligentLiuye)
    liuye.name = "智能柳叶"
    liuye._guild_enabled = True
    liuye._guild_unsubscribe = None
    liuye._latest_submitted_task_id = None
    liuye._latest_submitted_task_time = 0
    liuye._on_guild_event = lambda evt: None

    ret = IntelligentLiuye._submit_task_to_guild(liuye, "查一下今天AI新闻")

    assert "已加入公会队列" in ret
    assert "未提交" not in ret
    assert dummy_guild.ensure_calls == 1
    assert dummy_guild.subscribe_calls == 1
    assert dummy_guild.submit_calls and "查一下今天AI新闻" in dummy_guild.submit_calls[0]
    assert liuye._latest_submitted_task_id == "task_demo_1"
    assert liuye._latest_submitted_task_time > 0


def test_guild_report_mode_filters_progress_and_queues_during_generation():
    liuye = object.__new__(IntelligentLiuye)
    liuye.name = "智能柳叶"
    liuye._guild_report_mode = "important_only"
    liuye._response_lock = threading.Lock()
    liuye._is_generating_response = False
    liuye._pending_guild_events = []
    played = []
    liuye._generate_liuye_tts = lambda text, priority=5, send_to_web=True: played.append((text, priority))

    # important_only 模式下，progress 默认不主动播报
    IntelligentLiuye._on_guild_task_progress(liuye, {"task_id": "task_1", "progress": "正在搜索"})
    assert played == []

    # 切换 always 后，生成中先入队，生成结束后再播报
    IntelligentLiuye._set_guild_report_mode(liuye, "always")
    liuye._is_generating_response = True
    IntelligentLiuye._on_guild_task_progress(liuye, {"task_id": "task_1", "progress": "正在总结"})
    assert liuye._pending_guild_events and liuye._pending_guild_events[0]["type"] == "progress"
    assert liuye._pending_guild_events[0]["priority"] == 4

    liuye._is_generating_response = False
    IntelligentLiuye._process_pending_guild_events(liuye)
    assert played and "公会进展更新" in played[0][0]
    assert played[0][1] == 4


def test_should_use_llm_tools_respects_env_switch(monkeypatch):
    liuye = object.__new__(IntelligentLiuye)

    monkeypatch.setenv("LIUYE_STRUCTURED_TOOLS", "1")
    assert IntelligentLiuye._should_use_llm_tools(liuye, "随便聊聊")

    monkeypatch.setenv("LIUYE_STRUCTURED_TOOLS", "0")
    assert not IntelligentLiuye._should_use_llm_tools(liuye, "请帮我查天气")
