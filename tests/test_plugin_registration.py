import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import yaml

import __init__ as plugin
import session_store
from relay_config import build_tool_description, build_workdir_description, get_command_visibility, get_workdir_root
from gateway_hook import pre_gateway_dispatch
from handoff_tool import coding_relay
from session_lookup_tool import list_relay_sessions
from relay_runtime import clear_active_relays, get_active_relay
from slash_commands import handle_relay_back_command, handle_relay_mode_command


class FakeContext:
    def __init__(self):
        self.tools = []
        self.hooks = []
        self.commands = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands.append(
            {
                "name": name,
                "handler": handler,
                "description": description,
                "args_hint": args_hint,
            }
        )


class FakeRunnerResult:
    def __init__(
        self,
        codex_thread_id="thread-123",
        agent_texts=None,
        errors=None,
        command_runs=None,
        file_changes=None,
        events=None,
    ):
        self.codex_thread_id = codex_thread_id
        self.agent_texts = agent_texts or []
        self.errors = errors or []
        self.command_runs = command_runs or []
        self.file_changes = file_changes or []
        self.events = events or []


class FakeSessionEntry:
    def __init__(self, session_id, session_key):
        self.session_id = session_id
        self.session_key = session_key


class FakeSessionStore:
    def __init__(self, entry):
        self.entry = entry

    def get_or_create_session(self, _source):
        return self.entry


class FakeEvent:
    def __init__(self, chat_id="chat-1", message_id="msg-1", platform="feishu"):
        self.source = SimpleSource(chat_id, platform)
        self.message_id = message_id
        self.text = ""


class SimpleSource:
    def __init__(self, chat_id, platform="feishu"):
        self.chat_id = chat_id
        self.platform = platform


class FakePlatform(Enum):
    FEISHU = "feishu"


class FakeAdapter:
    def __init__(self):
        self.messages = []

    async def send(self, chat_id, text):
        self.messages.append((chat_id, text))


class FakeGateway:
    def __init__(self, adapter, platform_key="feishu"):
        self.adapters = {platform_key: adapter}


class PluginRegistrationTests(unittest.TestCase):
    def setUp(self):
        clear_active_relays()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_sessions_path = session_store.SESSIONS_PATH
        session_store.SESSIONS_PATH = Path(self.temp_dir.name) / "run" / "sessions.json"
        self.addCleanup(setattr, session_store, "SESSIONS_PATH", self.original_sessions_path)

    def test_plugin_manifest_contains_expected_capabilities(self):
        manifest = yaml.safe_load(Path("plugin.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "coding-relay")
        self.assertIn("coding_relay", manifest["provides_tools"])
        self.assertIn("pre_gateway_dispatch", manifest["provides_hooks"])

    def test_register_adds_tool_hook_and_command(self):
        ctx = FakeContext()
        plugin.register(ctx)

        self.assertEqual(len(ctx.tools), 2)
        self.assertEqual(ctx.tools[0]["name"], "coding_relay")
        self.assertEqual(ctx.tools[0]["toolset"], "plugin_coding_relay")
        self.assertIn(get_workdir_root(), ctx.tools[0]["description"])
        self.assertIn(get_workdir_root(), ctx.tools[0]["schema"]["parameters"]["properties"]["workdir"]["description"])
        self.assertEqual(ctx.tools[1]["name"], "list_relay_sessions")
        self.assertEqual(ctx.tools[1]["toolset"], "plugin_coding_relay")
        self.assertIn(get_workdir_root(), ctx.tools[1]["schema"]["parameters"]["properties"]["workdir"]["description"])

        self.assertEqual(ctx.hooks, [("pre_gateway_dispatch", pre_gateway_dispatch)])

        self.assertEqual(len(ctx.commands), 2)
        self.assertEqual(ctx.commands[0]["name"], "relay-back")
        self.assertIs(ctx.commands[0]["handler"], handle_relay_back_command)
        self.assertEqual(ctx.commands[1]["name"], "relay-mode")
        self.assertIs(ctx.commands[1]["handler"], handle_relay_mode_command)

    def test_coding_relay_rejects_non_codex_agent(self):
        result = json.loads(coding_relay({"agent": "claude", "prompt": "x", "workdir": "/tmp"}, task_id="sess-1"))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "unsupported_agent")

    def test_coding_relay_requires_session_id(self):
        result = json.loads(coding_relay({"agent": "codex", "prompt": "x", "workdir": "/tmp"}))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_session_id")

    def test_coding_relay_rejects_workdir_outside_allowed_root(self):
        result = json.loads(
            coding_relay({"agent": "codex", "prompt": "x", "workdir": "/tmp"}, task_id="sess-1")
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_workdir")

    def test_coding_relay_rejects_invalid_execution_mode(self):
        result = json.loads(
            coding_relay(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay", "yolo": "yes"},
                task_id="sess-1",
            )
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_execution_mode")

    def test_coding_relay_enters_coding_mode_and_runs_initial_turn(self):
        import handoff_tool

        original_runner = handoff_tool.run_codex_turn
        handoff_tool.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=["ready"],
            events=[
                {"kind": "agent_text", "payload": {"text": "ready"}},
                {"kind": "command_started", "payload": {"command": "pytest -q"}},
                {
                    "kind": "command_finished",
                    "payload": {"command": "pytest -q", "exit_code": 0, "output": ""},
                },
                {
                    "kind": "file_change",
                    "payload": {"phase": "completed", "path": "relay_runtime.py", "changes": [{"path": "relay_runtime.py"}]},
                },
            ],
            command_runs=[
                {"event_kind": "command_started", "command": "pytest -q", "status": "in_progress"},
                {"event_kind": "command_finished", "command": "pytest -q", "exit_code": 0, "status": "completed"},
            ],
            file_changes=[{"path": "relay_runtime.py", "changes": [{"path": "relay_runtime.py"}]}],
        )
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_runner)

        result = json.loads(
            coding_relay(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay"},
                task_id="sess-1",
                message_id="msg-1",
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(result["agent"], "codex")
        self.assertEqual(result["resume_token"], "thread-123")
        self.assertEqual(result["codex_thread_id"], "thread-123")
        self.assertEqual(result["sandbox_mode"], "workspace-write")
        self.assertFalse(result["yolo"])
        self.assertEqual(
            result["initial_messages"],
            ["ready", "**已修改文件**\n- `relay_runtime.py`"],
        )
        state = get_active_relay("sess-1")
        self.assertIsNotNone(state)
        self.assertEqual(state.session_id, "sess-1")
        self.assertEqual(state.agent, "codex")
        self.assertEqual(state.codex_thread_id, "thread-123")
        self.assertEqual(state.workdir, "/home/dontstarve/projects/coding-relay")
        self.assertIsNone(state.current_process)
        self.assertIsNone(state.current_message_id)
        self.assertFalse(state.turn_in_flight)

        store = session_store.load_session_store()
        self.assertEqual(len(store["sessions"]), 1)
        self.assertEqual(store["sessions"][0]["resume_token"], "thread-123")
        self.assertEqual(store["sessions"][0]["codex_thread_id"], "thread-123")
        self.assertIn("最近检查：pytest -q (exit 0)", store["sessions"][0]["summary"])

    def test_list_relay_sessions_returns_candidates_without_entering_coding_mode(self):
        session_store.upsert_session_record(
            codex_thread_id="thread-older",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="修复旧问题",
            agent_texts=["旧结果"],
            command_runs=[],
            file_changes=[],
            now=datetime(2026, 5, 11, 10, 0, 0, tzinfo=timezone.utc),
        )
        session_store.upsert_session_record(
            codex_thread_id="thread-newer",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="修复新问题",
            agent_texts=["新结果"],
            command_runs=[],
            file_changes=[],
            now=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
        )

        result = json.loads(
            list_relay_sessions(
                {"workdir": "/home/dontstarve/projects/coding-relay", "limit": 5},
                task_id="sess-1",
            )
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["sessions"][0]["resume_token"], "thread-newer")
        self.assertEqual(result["sessions"][1]["resume_token"], "thread-older")
        self.assertIsNone(get_active_relay("sess-1"))

    def test_coding_relay_streams_first_turn_when_gateway_context_exists(self):
        import handoff_tool
        import relay_delivery

        adapter = FakeAdapter()
        gateway = FakeGateway(adapter)
        event = FakeEvent(chat_id="chat-1", message_id="msg-1")

        original_runner = relay_delivery.run_codex_turn
        original_handoff_runner = handoff_tool.run_codex_turn
        def fake_runner(state, prompt, message_id=None, event_sink=None):
            events = [
                {"kind": "agent_text", "payload": {"text": "# 已完成\n\n最小项目已创建。"}},
                {"kind": "command_started", "payload": {"command": "pytest -q"}},
                {"kind": "command_finished", "payload": {"command": "pytest -q", "exit_code": 0, "output": "1 passed"}},
            ]
            if callable(event_sink):
                for event_record in events:
                    event_sink(event_record)
            return FakeRunnerResult(
                codex_thread_id="thread-123",
                agent_texts=["# 已完成\n\n最小项目已创建。"],
                events=events,
            )

        relay_delivery.run_codex_turn = fake_runner
        handoff_tool.run_codex_turn = fake_runner
        self.addCleanup(setattr, relay_delivery, "run_codex_turn", original_runner)
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_handoff_runner)

        result = json.loads(
            coding_relay(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay"},
                task_id="sess-1",
                message_id="msg-1",
                gateway=gateway,
                event=event,
                session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")),
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(result["initial_messages"], [])
        self.assertEqual(
            adapter.messages,
            [
                ("chat-1", "# 已完成\n\n最小项目已创建。"),
                ("chat-1", "**本轮完成**"),
            ],
        )

    def test_coding_relay_streams_when_source_platform_is_enum(self):
        import handoff_tool
        import relay_delivery

        adapter = FakeAdapter()
        gateway = FakeGateway(adapter, platform_key=FakePlatform.FEISHU)
        event = FakeEvent(chat_id="chat-1", message_id="msg-1", platform=FakePlatform.FEISHU)

        original_runner = relay_delivery.run_codex_turn
        original_handoff_runner = handoff_tool.run_codex_turn

        def fake_runner(state, prompt, message_id=None, event_sink=None):
            events = [{"kind": "agent_text", "payload": {"text": "枚举平台回复正常。"}}]
            if callable(event_sink):
                for event_record in events:
                    event_sink(event_record)
            return FakeRunnerResult(
                codex_thread_id="thread-123",
                agent_texts=["枚举平台回复正常。"],
                events=events,
            )

        relay_delivery.run_codex_turn = fake_runner
        handoff_tool.run_codex_turn = fake_runner
        self.addCleanup(setattr, relay_delivery, "run_codex_turn", original_runner)
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_handoff_runner)

        result = json.loads(
            coding_relay(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay"},
                task_id="sess-1",
                message_id="msg-1",
                gateway=gateway,
                event=event,
                session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")),
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(
            adapter.messages,
            [
                ("chat-1", "枚举平台回复正常。"),
                ("chat-1", "**本轮完成**"),
            ],
        )

    def test_gateway_hook_streams_when_source_platform_is_enum(self):
        import gateway_hook
        import relay_delivery

        adapter = FakeAdapter()
        gateway = FakeGateway(adapter, platform_key=FakePlatform.FEISHU)

        original_runner = relay_delivery.run_codex_turn

        def fake_runner(state, prompt, message_id=None, event_sink=None):
            events = [{"kind": "agent_text", "payload": {"text": f"reply:{prompt}"}}]
            if callable(event_sink):
                for event_record in events:
                    event_sink(event_record)
            return FakeRunnerResult(
                codex_thread_id="thread-123",
                agent_texts=[f"reply:{prompt}"],
                events=events,
            )

        relay_delivery.run_codex_turn = fake_runner
        self.addCleanup(setattr, relay_delivery, "run_codex_turn", original_runner)

        from relay_runtime import activate_relay

        activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")

        event = FakeEvent(chat_id="chat-1", message_id="msg-2", platform=FakePlatform.FEISHU)
        event.text = "continue"
        result = pre_gateway_dispatch(
            event=event,
            gateway=gateway,
            session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")),
        )

        self.assertEqual(result["action"], "skip")
        deadline = time.time() + 1.0
        while len(adapter.messages) < 2 and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(
            adapter.messages,
            [
                ("chat-1", "reply:continue"),
                ("chat-1", "**本轮完成**"),
            ],
        )

    def test_coding_relay_prepends_resume_notice_without_gateway_context(self):
        import handoff_tool

        session_store.upsert_session_record(
            codex_thread_id="thread-123",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="修复 relay 输出",
            agent_texts=["已完成首轮修复。"],
            command_runs=[{"command": "pytest -q", "exit_code": 0, "status": "completed"}],
            file_changes=[{"path": "relay_delivery.py", "changes": [{"path": "relay_delivery.py"}]}],
            now=datetime(2026, 5, 11, 11, 30, 0, tzinfo=timezone.utc),
        )

        original_runner = handoff_tool.run_codex_turn
        handoff_tool.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=["继续处理完成。"],
        )
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_runner)

        result = json.loads(
            coding_relay(
                {
                    "agent": "codex",
                    "prompt": "继续处理",
                    "workdir": "/home/dontstarve/projects/coding-relay",
                    "resume_token": "thread-123",
                },
                task_id="sess-1",
                message_id="msg-1",
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(
            result["initial_messages"][0],
            "**已恢复历史会话**\n"
            "- provider: `codex`\n"
            "- resume token: `thread-123`\n"
            "- workdir: `/home/dontstarve/projects/coding-relay`\n"
            "- 上次活跃：`2026-05-11T11:30:00+00:00`\n"
            "- 摘要：目标：修复 relay 输出；最近结果：已完成首轮修复。；最近文件：relay_delivery.py；最近检查：pytest -q (exit 0)\n"
            "- 最近文件：`relay_delivery.py`",
        )
        self.assertEqual(result["initial_messages"][1:], ["继续处理完成。"])

    def test_coding_relay_streams_resume_notice_before_first_turn_output(self):
        import handoff_tool
        import relay_delivery

        session_store.upsert_session_record(
            codex_thread_id="thread-123",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="修复 relay 输出",
            agent_texts=["已完成首轮修复。"],
            command_runs=[{"command": "pytest -q", "exit_code": 0, "status": "completed"}],
            file_changes=[{"path": "relay_delivery.py", "changes": [{"path": "relay_delivery.py"}]}],
            now=datetime(2026, 5, 11, 11, 30, 0, tzinfo=timezone.utc),
        )

        adapter = FakeAdapter()
        gateway = FakeGateway(adapter)
        event = FakeEvent(chat_id="chat-1", message_id="msg-1")

        original_runner = relay_delivery.run_codex_turn
        original_handoff_runner = handoff_tool.run_codex_turn
        def fake_runner(state, prompt, message_id=None, event_sink=None):
            events = [{"kind": "agent_text", "payload": {"text": "继续处理完成。"}}]
            if callable(event_sink):
                for event_record in events:
                    event_sink(event_record)
            return FakeRunnerResult(
                codex_thread_id="thread-123",
                agent_texts=["继续处理完成。"],
                events=events,
            )

        relay_delivery.run_codex_turn = fake_runner
        handoff_tool.run_codex_turn = fake_runner
        self.addCleanup(setattr, relay_delivery, "run_codex_turn", original_runner)
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_handoff_runner)

        result = json.loads(
            coding_relay(
                {
                    "agent": "codex",
                    "prompt": "继续处理",
                    "workdir": "/home/dontstarve/projects/coding-relay",
                    "resume_token": "thread-123",
                },
                task_id="sess-1",
                message_id="msg-1",
                gateway=gateway,
                event=event,
                session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")),
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(result["initial_messages"], [])
        self.assertEqual(
            adapter.messages,
            [
                (
                    "chat-1",
                    "**已恢复历史会话**\n"
                    "- provider: `codex`\n"
                    "- resume token: `thread-123`\n"
                    "- workdir: `/home/dontstarve/projects/coding-relay`\n"
                    "- 上次活跃：`2026-05-11T11:30:00+00:00`\n"
                    "- 摘要：目标：修复 relay 输出；最近结果：已完成首轮修复。；最近文件：relay_delivery.py；最近检查：pytest -q (exit 0)\n"
                    "- 最近文件：`relay_delivery.py`",
                ),
                ("chat-1", "继续处理完成。"),
                ("chat-1", "**本轮完成**"),
            ],
        )

    def test_gateway_hook_defaults_to_passthrough(self):
        self.assertIsNone(pre_gateway_dispatch(event="anything"))

    def test_gateway_hook_relays_message_and_skips_hermes(self):
        import gateway_hook

        original_runner = gateway_hook.run_codex_turn
        gateway_hook.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=[f"reply:{prompt}"],
            file_changes=[{"path": "gateway_hook.py", "changes": [{"path": "gateway_hook.py"}]}],
        )
        self.addCleanup(setattr, gateway_hook, "run_codex_turn", original_runner)

        clear_active_relays()
        state = get_active_relay("sess-1")
        self.assertIsNone(state)
        from relay_runtime import activate_relay

        activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")

        event = FakeEvent(chat_id="chat-1", message_id="msg-2")
        event.text = "continue"
        result = pre_gateway_dispatch(event=event, session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")))

        self.assertEqual(result["action"], "skip")

        store = session_store.load_session_store()
        self.assertEqual(store["sessions"][0]["codex_thread_id"], "thread-123")
        self.assertIn("最近结果：reply:continue", store["sessions"][0]["summary"])

    def test_coding_relay_accepts_legacy_codex_thread_id_alias(self):
        import handoff_tool

        original_runner = handoff_tool.run_codex_turn
        handoff_tool.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-legacy",
            agent_texts=["继续处理完成。"],
        )
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_runner)

        result = json.loads(
            coding_relay(
                {
                    "agent": "codex",
                    "prompt": "继续处理",
                    "workdir": "/home/dontstarve/projects/coding-relay",
                    "codex_thread_id": "thread-legacy",
                },
                task_id="sess-1",
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(result["resume_token"], "thread-legacy")

    def test_coding_relay_returns_formatted_spawn_failure(self):
        import handoff_tool

        original_runner = handoff_tool.run_codex_turn
        handoff_tool.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id=None,
            errors=[
                {
                    "reason": "spawn_failed",
                    "message": "failed to start Codex CLI: [Errno 2] No such file or directory: 'codex'",
                }
            ],
        )
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_runner)

        result = json.loads(
            coding_relay(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay"},
                task_id="sess-1",
            )
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(
            result["messages"],
            ["**执行失败**\nCodex CLI 不可用：未找到 `codex` 命令，请先确认安装并已加入 PATH。"],
        )

    def test_gateway_hook_back_command_clears_active_state(self):
        from relay_runtime import activate_relay

        activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")

        event = FakeEvent(chat_id="chat-1")
        event.text = "/relay-back"
        result = pre_gateway_dispatch(event=event, session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")))

        self.assertEqual(result, {"action": "skip"})
        self.assertIsNone(get_active_relay("sess-1"))

    def test_gateway_hook_treats_back_as_agent_text(self):
        import gateway_hook

        original_runner = gateway_hook.run_codex_turn
        gateway_hook.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=[f"reply:{prompt}"],
        )
        self.addCleanup(setattr, gateway_hook, "run_codex_turn", original_runner)

        from relay_runtime import activate_relay

        activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")

        event = FakeEvent(chat_id="chat-1")
        event.text = "/back"
        result = pre_gateway_dispatch(event=event, session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")))

        self.assertEqual(result["action"], "skip")
        self.assertIsNotNone(get_active_relay("sess-1"))

    def test_gateway_hook_preserves_agent_slash_commands(self):
        import gateway_hook

        original_runner = gateway_hook.run_codex_turn
        gateway_hook.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=[f"reply:{prompt}"],
        )
        self.addCleanup(setattr, gateway_hook, "run_codex_turn", original_runner)

        from relay_runtime import activate_relay

        activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")

        event = FakeEvent(chat_id="chat-1")
        event.text = "/compact"
        result = pre_gateway_dispatch(event=event, session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")))

        self.assertEqual(result["action"], "skip")

    def test_gateway_hook_relay_mode_changes_execution_mode(self):
        from relay_runtime import activate_relay

        activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")

        event = FakeEvent(chat_id="chat-1")
        event.text = "/relay-mode readonly"
        result = pre_gateway_dispatch(event=event, session_store=FakeSessionStore(FakeSessionEntry("sess-1", "key-1")))

        self.assertEqual(result["action"], "skip")
        self.assertEqual(get_active_relay("sess-1").sandbox_mode, "read-only")

    def test_relay_back_command_exits_coding_mode(self):
        from relay_runtime import activate_relay

        activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")

        result = handle_relay_back_command("", task_id="sess-1")

        self.assertIn("已退出", result)
        self.assertIsNone(get_active_relay("sess-1"))

    def test_tool_description_reflects_configured_workdir_root(self):
        config = {"plugins": {"coding-relay": {"workdir_root": "/tmp/custom-root"}}}
        self.assertIn("/tmp/custom-root", build_workdir_description(config))
        self.assertIn("/tmp/custom-root", build_tool_description(config))

    def test_command_visibility_defaults_and_reads_plugin_config(self):
        self.assertEqual(get_command_visibility({}), "none")
        self.assertEqual(get_command_visibility({"plugins": {"coding-relay": {"command_visibility": "filtered"}}}), "filtered")
        self.assertEqual(get_command_visibility({"plugins": {"coding-relay": {"command_visibility": "all"}}}), "all")
        self.assertEqual(get_command_visibility({"plugins": {"coding-relay": {"command_visibility": "loud"}}}), "none")


if __name__ == "__main__":
    unittest.main()
