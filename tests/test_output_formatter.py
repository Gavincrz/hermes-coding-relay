import unittest

from output_formatter import format_turn_output, safe_format_turn_output


class FakeTurnResult:
    def __init__(self, agent_texts=None, command_runs=None, file_changes=None, errors=None):
        self.agent_texts = agent_texts or []
        self.command_runs = command_runs or []
        self.file_changes = file_changes or []
        self.errors = errors or []


class OutputFormatterTests(unittest.TestCase):
    def test_format_turn_output_renders_agent_text_command_and_file_change(self):
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
                "执行命令：pytest -q",
                "命令完成：pytest -q (exit 0) 输出摘要：2 passed",
                "文件变更：relay_runtime.py, tests/test_runtime.py",
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
                "Codex CLI 不可用：未找到 `codex` 命令，请先确认安装并已加入 PATH。",
                "Codex 输出中存在无法解析的 JSON 行，已跳过异常内容并继续处理其余事件。",
                "Codex 非正常退出 (exit 1)：boom",
                "Codex 返回错误：rate limited",
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


if __name__ == "__main__":
    unittest.main()
