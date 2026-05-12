import unittest

from output_formatter import format_turn_output, safe_format_turn_output


class FakeTurnResult:
    def __init__(self, agent_texts=None, command_runs=None, file_changes=None, errors=None, events=None):
        self.agent_texts = agent_texts or []
        self.command_runs = command_runs or []
        self.file_changes = file_changes or []
        self.errors = errors or []
        self.events = events or []


class OutputFormatterTests(unittest.TestCase):
    def test_format_turn_output_renders_events_in_order(self):
        turn_result = FakeTurnResult(
            events=[
                {"kind": "agent_text", "payload": {"text": "已修复解析器。"}},
                {"kind": "command_started", "payload": {"command": "pytest -q"}},
                {
                    "kind": "command_finished",
                    "payload": {"command": "pytest -q", "exit_code": 0, "output": "2 passed\n"},
                },
                {
                    "kind": "file_change",
                    "payload": {"phase": "completed", "path": "relay_runtime.py", "changes": [{"path": "relay_runtime.py"}, {"path": "tests/test_runtime.py"}]},
                },
            ],
        )

        self.assertEqual(
            format_turn_output(turn_result),
            [
                "已修复解析器。",
                "**已修改文件**\n- `relay_runtime.py`\n- `tests/test_runtime.py`",
            ],
        )

    def test_format_turn_output_falls_back_to_legacy_collections(self):
        turn_result = FakeTurnResult(
            agent_texts=["已修复解析器。"],
            command_runs=[
                {"event_kind": "command_started", "command": "pytest -q", "status": "in_progress"},
                {
                    "event_kind": "command_finished",
                    "command": "pytest -q",
                    "status": "completed",
                    "exit_code": 0,
                    "output": "2 passed\n",
                },
            ],
            file_changes=[
                {
                    "phase": "completed",
                    "path": "relay_runtime.py",
                    "changes": [{"path": "relay_runtime.py"}, {"path": "tests/test_runtime.py"}],
                }
            ],
        )

        self.assertEqual(
            format_turn_output(turn_result),
            [
                "已修复解析器。",
                "**已修改文件**\n- `relay_runtime.py`\n- `tests/test_runtime.py`",
            ],
        )

    def test_format_turn_output_filtered_shows_high_value_finished_commands_only(self):
        turn_result = FakeTurnResult(
            events=[
                {"kind": "agent_text", "payload": {"text": "已修复解析器。"}},
                {"kind": "command_started", "payload": {"command": "pytest -q"}},
                {
                    "kind": "command_finished",
                    "payload": {"command": "pytest -q", "exit_code": 0, "output": "2 passed\n"},
                },
                {"kind": "command_started", "payload": {"command": "ls"}},
                {"kind": "command_finished", "payload": {"command": "ls", "exit_code": 0, "output": "a.py\n"}},
            ],
        )

        self.assertEqual(
            format_turn_output(turn_result, command_visibility="filtered"),
            [
                "已修复解析器。",
                "**已完成**\n`pytest -q` (exit 0)\n```text\n2 passed\n```",
            ],
        )

    def test_format_turn_output_all_shows_started_and_finished_commands(self):
        turn_result = FakeTurnResult(
            events=[
                {"kind": "agent_text", "payload": {"text": "已修复解析器。"}},
                {"kind": "command_started", "payload": {"command": "pytest -q"}},
                {
                    "kind": "command_finished",
                    "payload": {"command": "pytest -q", "exit_code": 0, "output": "2 passed\n"},
                },
            ],
        )

        self.assertEqual(
            format_turn_output(turn_result, command_visibility="all"),
            [
                "已修复解析器。",
                "**正在执行**\n`pytest -q`",
                "**已完成**\n`pytest -q` (exit 0)\n```text\n2 passed\n```",
            ],
        )

    def test_format_turn_output_maps_common_errors(self):
        turn_result = FakeTurnResult(
            errors=[
                {"reason": "spawn_failed", "message": "failed to start Codex CLI: [Errno 2] No such file or directory"},
                {"reason": "invalid_json_line", "message": "Failed to decode"},
                {"reason": "process_exit", "message": "Codex exited with status 1.", "exit_code": 1, "stderr": "boom"},
                {"reason": "codex_error", "message": "rate limited"},
            ]
        )

        self.assertEqual(
            format_turn_output(turn_result),
            [
                "**执行失败**\nCodex CLI 不可用：未找到 `codex` 命令，请先确认安装并已加入 PATH。",
                "**执行失败**\nCodex 输出中存在无法解析的 JSON 行，已跳过异常内容并继续处理其余事件。",
                "**执行失败**\nCodex 非正常退出 (exit 1)：boom",
                "**执行失败**\nCodex 返回错误：rate limited",
            ],
        )

    def test_safe_format_turn_output_falls_back_to_agent_texts(self):
        class BadTurnResult(FakeTurnResult):
            @property
            def agent_texts(self):
                raise RuntimeError("broken")

            @agent_texts.setter
            def agent_texts(self, _value):
                pass

        self.assertEqual(safe_format_turn_output(BadTurnResult()), ["relay 输出格式化失败，已跳过格式化步骤。"])

    def test_format_turn_output_none_still_shows_failed_commands(self):
        turn_result = FakeTurnResult(
            events=[
                {"kind": "command_started", "payload": {"command": "pytest -q"}},
                {
                    "kind": "command_finished",
                    "payload": {"command": "pytest -q", "exit_code": 1, "output": "1 failed\n"},
                },
            ]
        )

        self.assertEqual(
            format_turn_output(turn_result, command_visibility="none"),
            ["**已完成**\n`pytest -q` (exit 1)\n```text\n1 failed\n```"],
        )


if __name__ == "__main__":
    unittest.main()
