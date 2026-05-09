import json
import unittest
from pathlib import Path

import yaml

import __init__ as plugin
from gateway_hook import pre_gateway_dispatch
from handoff_tool import coding_handoff
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


class PluginRegistrationTests(unittest.TestCase):
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
        result = json.loads(coding_handoff({"agent": "claude", "prompt": "x", "workdir": "/tmp"}))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "unsupported_agent")

    def test_coding_handoff_returns_placeholder_for_codex(self):
        result = json.loads(coding_handoff({"agent": "codex", "prompt": "x", "workdir": "/tmp"}))
        self.assertEqual(result["status"], "not_implemented")
        self.assertEqual(result["agent"], "codex")

    def test_gateway_hook_defaults_to_passthrough(self):
        self.assertIsNone(pre_gateway_dispatch(event="anything"))

    def test_back_command_returns_placeholder_message(self):
        self.assertIn("T004", handle_back_command(""))


if __name__ == "__main__":
    unittest.main()
