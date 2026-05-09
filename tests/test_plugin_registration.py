import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

import yaml

import __init__ as plugin
import session_store
from gateway_hook import pre_gateway_dispatch
from handoff_tool import coding_handoff
from relay_runtime import ActiveRelayState, clear_active_relays, get_active_relay
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
    def __init__(self, codex_thread_id="thread-123", agent_texts=None, errors=None, command_runs=None, file_changes=None):
        self.codex_thread_id = codex_thread_id
        self.agent_texts = agent_texts or []
        self.errors = errors or []
        self.command_runs = command_runs or []
        self.file_changes = file_changes or []


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
        self.assertIn("coding_handoff", manifest["provides_tools"])
        self.assertIn("pre_gateway_dispatch", manifest["provides_hooks"])

    def test_register_adds_tool_hook_and_command(self):
        ctx = FakeContext()
        plugin.register(ctx)

        self.assertEqual(len(ctx.tools), 1)
        self.assertEqual(ctx.tools[0]["name"], "coding_handoff")
        self.assertEqual(ctx.tools[0]["toolset"], "plugin_coding_relay")

        self.assertEqual(ctx.hooks, [("pre_gateway_dispatch", pre_gateway_dispatch)])

        self.assertEqual(len(ctx.commands), 2)
        self.assertEqual(ctx.commands[0]["name"], "relay-back")
        self.assertIs(ctx.commands[0]["handler"], handle_relay_back_command)
        self.assertEqual(ctx.commands[1]["name"], "relay-mode")
        self.assertIs(ctx.commands[1]["handler"], handle_relay_mode_command)

    def test_coding_handoff_rejects_non_codex_agent(self):
        result = json.loads(coding_handoff({"agent": "claude", "prompt": "x", "workdir": "/tmp"}, chat_id="chat-1"))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "unsupported_agent")

    def test_coding_handoff_requires_chat_id(self):
        result = json.loads(coding_handoff({"agent": "codex", "prompt": "x", "workdir": "/tmp"}))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_chat_id")

    def test_coding_handoff_accepts_hermes_event_object_chat_id(self):
        import handoff_tool

        original_runner = handoff_tool.run_codex_turn
        handoff_tool.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-obj",
            agent_texts=["ready"],
        )
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_runner)

        event = SimpleNamespace(
            source=SimpleNamespace(chat_id="chat-event"),
            message_id="msg-event",
        )
        result = json.loads(
            coding_handoff(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay"},
                event=event,
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(result["codex_thread_id"], "thread-obj")
        self.assertEqual(get_active_relay("chat-event").chat_id, "chat-event")

    def test_coding_handoff_rejects_workdir_outside_allowed_root(self):
        result = json.loads(
            coding_handoff({"agent": "codex", "prompt": "x", "workdir": "/tmp"}, chat_id="chat-1")
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_workdir")

    def test_coding_handoff_rejects_invalid_execution_mode(self):
        result = json.loads(
            coding_handoff(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay", "yolo": "yes"},
                chat_id="chat-1",
            )
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_execution_mode")

    def test_coding_handoff_enters_coding_mode_and_runs_initial_turn(self):
        import handoff_tool

        original_runner = handoff_tool.run_codex_turn
        handoff_tool.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=["ready"],
            command_runs=[{"command": "pytest -q", "exit_code": 0, "status": "completed"}],
            file_changes=[{"path": "relay_runtime.py", "changes": [{"path": "relay_runtime.py"}]}],
        )
        self.addCleanup(setattr, handoff_tool, "run_codex_turn", original_runner)

        result = json.loads(
            coding_handoff(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay"},
                chat_id="chat-1",
                message_id="msg-1",
            )
        )

        self.assertEqual(result["status"], "handed_off")
        self.assertEqual(result["agent"], "codex")
        self.assertEqual(result["codex_thread_id"], "thread-123")
        self.assertEqual(result["sandbox_mode"], "workspace-write")
        self.assertFalse(result["yolo"])
        self.assertEqual(
            result["initial_messages"],
            ["ready", "命令完成：pytest -q (exit 0)", "文件变更：relay_runtime.py"],
        )
        self.assertEqual(
            get_active_relay("chat-1"),
            ActiveRelayState(
                chat_id="chat-1",
                agent="codex",
                codex_thread_id="thread-123",
                workdir="/home/dontstarve/projects/coding-relay",
                current_process=None,
                current_message_id=None,
            ),
        )

        store = session_store.load_session_store()
        self.assertEqual(len(store["sessions"]), 1)
        self.assertEqual(store["sessions"][0]["codex_thread_id"], "thread-123")
        self.assertIn("最近检查：pytest -q (exit 0)", store["sessions"][0]["summary"])

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
        state = get_active_relay("chat-1")
        self.assertIsNone(state)
        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = pre_gateway_dispatch(chat_id="chat-1", text="continue", message_id="msg-2")

        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["relay"]["messages"], ["reply:continue", "文件变更：gateway_hook.py"])
        self.assertEqual(result["relay"]["codex_thread_id"], "thread-123")

        store = session_store.load_session_store()
        self.assertEqual(store["sessions"][0]["codex_thread_id"], "thread-123")
        self.assertIn("最近结果：reply:continue", store["sessions"][0]["summary"])

    def test_coding_handoff_returns_formatted_spawn_failure(self):
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
            coding_handoff(
                {"agent": "codex", "prompt": "x", "workdir": "/home/dontstarve/projects/coding-relay"},
                chat_id="chat-1",
            )
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(
            result["messages"],
            ["Codex CLI 不可用：未找到 `codex` 命令，请先确认安装并已加入 PATH。"],
        )

    def test_gateway_hook_back_command_clears_active_state(self):
        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = pre_gateway_dispatch(chat_id="chat-1", text="/relay-back")

        self.assertIsNone(result)
        self.assertIsNone(get_active_relay("chat-1"))

    def test_gateway_hook_treats_back_as_agent_text(self):
        import gateway_hook

        original_runner = gateway_hook.run_codex_turn
        gateway_hook.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=[f"reply:{prompt}"],
        )
        self.addCleanup(setattr, gateway_hook, "run_codex_turn", original_runner)

        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = pre_gateway_dispatch(chat_id="chat-1", text="/back")

        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["relay"]["messages"], ["reply:/back"])
        self.assertIsNotNone(get_active_relay("chat-1"))

    def test_gateway_hook_preserves_agent_slash_commands(self):
        import gateway_hook

        original_runner = gateway_hook.run_codex_turn
        gateway_hook.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=[f"reply:{prompt}"],
        )
        self.addCleanup(setattr, gateway_hook, "run_codex_turn", original_runner)

        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = pre_gateway_dispatch(chat_id="chat-1", text="/compact")

        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["relay"]["messages"], ["reply:/compact"])

    def test_gateway_hook_relay_mode_changes_execution_mode(self):
        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = pre_gateway_dispatch(chat_id="chat-1", text="/relay-mode readonly")

        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["relay"]["messages"], ["已切换 relay 模式：readonly（read-only）。"])
        self.assertEqual(get_active_relay("chat-1").sandbox_mode, "read-only")

    def test_relay_back_command_exits_coding_mode(self):
        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = handle_relay_back_command("", chat_id="chat-1")

        self.assertIn("已退出", result)
        self.assertIsNone(get_active_relay("chat-1"))


if __name__ == "__main__":
    unittest.main()
