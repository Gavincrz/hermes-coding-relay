import json
import unittest
from pathlib import Path

import yaml

import __init__ as plugin
from gateway_hook import pre_gateway_dispatch
from handoff_tool import coding_handoff
from relay_runtime import ActiveRelayState, clear_active_relays, get_active_relay
from slash_commands import handle_back_command


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
    def __init__(self, codex_thread_id="thread-123", agent_texts=None, errors=None):
        self.codex_thread_id = codex_thread_id
        self.agent_texts = agent_texts or []
        self.errors = errors or []


class PluginRegistrationTests(unittest.TestCase):
    def setUp(self):
        clear_active_relays()

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

        self.assertEqual(len(ctx.commands), 1)
        self.assertEqual(ctx.commands[0]["name"], "back")
        self.assertIs(ctx.commands[0]["handler"], handle_back_command)

    def test_coding_handoff_rejects_non_codex_agent(self):
        result = json.loads(coding_handoff({"agent": "claude", "prompt": "x", "workdir": "/tmp"}, chat_id="chat-1"))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "unsupported_agent")

    def test_coding_handoff_requires_chat_id(self):
        result = json.loads(coding_handoff({"agent": "codex", "prompt": "x", "workdir": "/tmp"}))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_chat_id")

    def test_coding_handoff_rejects_workdir_outside_allowed_root(self):
        result = json.loads(
            coding_handoff({"agent": "codex", "prompt": "x", "workdir": "/tmp"}, chat_id="chat-1")
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "invalid_workdir")

    def test_coding_handoff_enters_coding_mode_and_runs_initial_turn(self):
        import handoff_tool

        original_runner = handoff_tool.run_codex_turn
        handoff_tool.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=["ready"],
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
        self.assertEqual(result["initial_messages"], ["ready"])
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

    def test_gateway_hook_defaults_to_passthrough(self):
        self.assertIsNone(pre_gateway_dispatch(event="anything"))

    def test_gateway_hook_relays_message_and_skips_hermes(self):
        import gateway_hook

        original_runner = gateway_hook.run_codex_turn
        gateway_hook.run_codex_turn = lambda state, prompt, message_id=None: FakeRunnerResult(
            codex_thread_id="thread-123",
            agent_texts=[f"reply:{prompt}"],
        )
        self.addCleanup(setattr, gateway_hook, "run_codex_turn", original_runner)

        clear_active_relays()
        state = get_active_relay("chat-1")
        self.assertIsNone(state)
        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = pre_gateway_dispatch(chat_id="chat-1", text="continue", message_id="msg-2")

        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["relay"]["messages"], ["reply:continue"])
        self.assertEqual(result["relay"]["codex_thread_id"], "thread-123")

    def test_gateway_hook_back_command_clears_active_state(self):
        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = pre_gateway_dispatch(chat_id="chat-1", text="/back")

        self.assertIsNone(result)
        self.assertIsNone(get_active_relay("chat-1"))

    def test_back_command_exits_coding_mode(self):
        from relay_runtime import activate_relay

        activate_relay("chat-1", "/home/dontstarve/projects/coding-relay", "thread-123")

        result = handle_back_command("", chat_id="chat-1")

        self.assertIn("已退出", result)
        self.assertIsNone(get_active_relay("chat-1"))


if __name__ == "__main__":
    unittest.main()
