from pathlib import Path
import threading

from evoliu.guild_supervisor_agent import GuildSupervisorAgent


class _DummyStorageAbort:
    def __init__(self):
        self.task = {
            "task_id": "task_1",
            "description": "demo",
            "status": "running",
            "error": None,
        }
        self.saved_task = None
        self.saved_queue = None

    def load_task(self, task_id):
        if task_id != "task_1":
            return None
        return dict(self.task)

    def save_task(self, task_id, task_data):
        self.saved_task = (task_id, dict(task_data))

    def save_pending_queue(self, queue):
        self.saved_queue = list(queue)


class _DummyStorageClarify:
    def __init__(self):
        self.task = {
            "task_id": "task_1",
            "description": "orig task",
            "status": "waiting_clarification",
            "clarifying_question": "A or B?",
        }
        self.saved_task = None

    def load_task(self, task_id):
        if task_id != "task_1":
            return None
        return dict(self.task)

    def save_task(self, task_id, task_data):
        self.saved_task = (task_id, dict(task_data))


class _DummyStorageDissolve:
    def __init__(self):
        self.queue_cleared = False

    def list_tasks(self, status=None):
        table = {
            "running": [{"task_id": "task_1"}],
            "pending": [{"task_id": "task_2"}],
            "waiting_clarification": [{"task_id": "task_3"}],
        }
        return list(table.get(status, []))

    def clear_pending_queue(self):
        self.queue_cleared = True


class _DummyStorageSubmit:
    def __init__(self):
        self.tasks = {}
        self.pending_queue = []

    def save_task(self, task_id, task_data):
        self.tasks[task_id] = dict(task_data)

    def load_task(self, task_id):
        task = self.tasks.get(task_id)
        return dict(task) if task else None

    def save_pending_queue(self, queue):
        self.pending_queue = list(queue)

    def load_pending_queue(self):
        return list(self.pending_queue)

    def clear_pending_queue(self):
        self.pending_queue = []

    def list_tasks(self, status=None):
        values = list(self.tasks.values())
        if status is None:
            return values
        return [t for t in values if t.get("status") == status]


def test_guild_supervisor_has_liuye_contract_and_force_stop():
    src = Path("evoliu/guild_supervisor_agent.py").read_text(encoding="utf-8")
    assert "def subscribe(self, callback" in src
    assert "def answer_clarification(self, task_id: str, answer: str) -> bool:" in src
    assert "def dissolve_guild(self, reason:" in src
    assert "def ensure_listener_started(self) -> bool:" in src
    assert "self._emit_event({" in src
    assert '"type": "clarify"' in src
    assert '"type": "complete"' in src
    assert '"type": "failed"' in src


def test_submit_task_queues_first_and_records_auto_routing():
    agent = object.__new__(GuildSupervisorAgent)
    agent.storage = _DummyStorageSubmit()
    agent.guild_members = {
        "openclaw": {
            "name": "OpenClaw",
            "status": "active",
            "capabilities": ["网页搜索", "代码"],
        }
    }
    agent.pending_tasks = []
    agent._queue_lock = threading.Lock()
    agent._dispatching = False
    agent.listener_ready = False
    agent._event_loop = None
    agent.listener = None
    events = []
    agent._emit_event = lambda evt: events.append(evt)
    agent.ensure_listener_started = lambda: True

    task_id = GuildSupervisorAgent.submit_task(agent, "请帮我搜索Python教程", member_id="auto")

    assert task_id in agent.storage.tasks
    task = agent.storage.tasks[task_id]
    assert task["status"] == "pending"
    assert task["assigned_to"] == "openclaw"
    assert task.get("routing", {}).get("mode") == "auto"
    assert task.get("trace_id")
    assert task.get("correlation_id")
    assert agent.pending_tasks and agent.pending_tasks[0][0] == task_id
    assert agent.storage.pending_queue and agent.storage.pending_queue[0][0] == task_id
    assert events and events[-1]["status"] == "pending"


def test_abort_task_handles_string_session_map_without_unpack_error():
    agent = object.__new__(GuildSupervisorAgent)
    agent.storage = _DummyStorageAbort()
    agent.pending_tasks = [("task_1", "to stop"), ("task_2", "keep")]
    agent._queue_lock = threading.Lock()
    agent.task_session_map = {"task_1": "guild_task_1"}
    agent.listener = None
    agent._event_loop = None
    agent.run_task_map = {"run_1": "task_1", "run_2": "task_2"}
    agent._pending_clarifications = {"task_1": {"question": "?"}}
    events = []
    agent._emit_event = lambda evt: events.append(evt)

    ret = GuildSupervisorAgent.abort_task(agent, "task_1", reason="force-stop")

    assert ret.get("success") is True
    assert all(tid != "task_1" for tid, _ in agent.pending_tasks)
    assert "task_1" not in agent.task_session_map
    assert "run_1" not in agent.run_task_map
    assert "run_2" in agent.run_task_map
    assert "task_1" not in agent._pending_clarifications
    assert agent.storage.saved_task[1]["status"] == "aborted"
    assert agent.storage.saved_task[1]["error"] == "force-stop"
    assert events and events[-1]["status"] == "aborted"


def test_answer_clarification_requeues_task_and_emits_progress():
    agent = object.__new__(GuildSupervisorAgent)
    agent.storage = _DummyStorageClarify()
    agent._queue_lock = threading.Lock()
    agent._pending_clarifications = {"task_1": {"question": "A or B?"}}
    queued = []
    events = []
    agent.ensure_listener_started = lambda: True
    agent.listener_ready = False
    agent._event_loop = None
    agent._queue_pending_task = lambda task_id, desc: queued.append((task_id, desc))
    agent._emit_event = lambda evt: events.append(evt)

    ok = GuildSupervisorAgent.answer_clarification(agent, "task_1", "choose A")

    assert ok is True
    assert "task_1" not in agent._pending_clarifications
    assert queued and queued[0][0] == "task_1"
    assert "clarifying" in queued[0][1].lower() or "【澄清问题】" in queued[0][1]
    assert "choose A" in queued[0][1]
    assert agent.storage.saved_task[1]["status"] == "pending"
    assert agent.storage.saved_task[1]["clarifying_question"] == ""
    assert agent.storage.saved_task[1]["clarification_answer"] == "choose A"
    assert events and events[-1]["type"] == "progress"


def test_dissolve_guild_aborts_all_active_tasks_and_resets_runtime_state():
    agent = object.__new__(GuildSupervisorAgent)
    agent.storage = _DummyStorageDissolve()
    agent.pending_tasks = [("task_4", "from queue"), ("task_4", "dedupe")]
    agent._queue_lock = threading.Lock()
    agent._pending_clarifications = {"task_2": {"question": "?"}}
    agent.task_session_map = {"task_x": "guild_task_x"}
    agent.listener = None
    agent._event_loop = None
    agent.run_task_map = {"run_1": "task_1"}
    aborted_calls = []
    events = []

    def _abort(task_id, reason=""):
        aborted_calls.append((task_id, reason))
        return {"success": True, "task_id": task_id}

    agent.abort_task = _abort
    agent._emit_event = lambda evt: events.append(evt)

    ret = GuildSupervisorAgent.dissolve_guild(agent, reason="system-reset")

    assert ret.get("success") is True
    assert ret.get("aborted_count") == 4
    assert set(tid for tid, _ in aborted_calls) == {"task_1", "task_2", "task_3", "task_4"}
    assert all(reason == "system-reset" for _, reason in aborted_calls)
    assert agent.pending_tasks == []
    assert agent.storage.queue_cleared is True
    assert agent._pending_clarifications == {}
    assert agent.task_session_map == {}
    assert agent.run_task_map == {}
    assert events and events[-1]["status"] == "idle"


def test_liuye_registers_dissolve_tool_and_finally_cleans_flag():
    src = Path("evoliu/liuye_frontend/intelligent_liuye.py").read_text(encoding="utf-8")
    assert "name=\"dissolve_guild\"" in src
    assert "def _dissolve_guild(self, reason: str = \"\") -> str:" in src
    assert "if action in (\"dissolve_guild\", \"disband_guild\", \"force_stop_guild\", \"stop_all_tasks\"):" in src
    assert "if tool_name == \"dissolve_guild\":" in src
    assert "finally:" in src
    assert "self._process_pending_guild_events()" in src


def test_liuye_query_task_schema_and_clarification_contract_updated():
    src = Path("evoliu/liuye_frontend/intelligent_liuye.py").read_text(encoding="utf-8")
    assert "\"name\": \"query_task\"" in src
    assert "\"required\": []" in src
    assert "\"name\": \"answer_clarification\"" in src
    assert "clarification_answer = self._extract_clarification_answer(text)" in src


def test_guild_supervisor_has_durable_audit_logger():
    src = Path("evoliu/guild_supervisor_agent.py").read_text(encoding="utf-8")
    assert "class GuildAuditLogger" in src
    assert "self.audit = GuildAuditLogger" in src
    assert "\"trace_id\":" in src
    assert "\"correlation_id\":" in src


def test_flask_exposes_guild_dissolve_endpoint():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "@__app.route('/api/v1/guilds/<guild_id>/dissolve', methods=['post'])" in src
    assert "guild.dissolve_guild(reason)" in src
