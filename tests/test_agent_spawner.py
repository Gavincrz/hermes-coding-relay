import io
import unittest

from agent_spawner import (
    CodexProcess,
    CodexSpawnError,
    StreamEvent,
    build_codex_command,
    start_codex_process,
)


class FakeProcess:
    def __init__(self, stdout_text="", stderr_text="", returncode=0):
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self.returncode = returncode

    def wait(self):
        return self.returncode


class AgentSpawnerTests(unittest.TestCase):
    def test_build_codex_command_for_new_session(self):
        command = build_codex_command(prompt="fix it", workdir="/repo")
        self.assertEqual(
            command,
            ["codex", "-a", "never", "-s", "workspace-write", "exec", "--skip-git-repo-check", "--json", "-C", "/repo", "fix it"],
        )

    def test_build_codex_command_for_resume(self):
        command = build_codex_command(prompt="continue", workdir="/repo", codex_thread_id="thread-123")
        self.assertEqual(
            command,
            ["codex", "-a", "never", "-s", "workspace-write", "exec", "--skip-git-repo-check", "resume", "thread-123", "--json", "continue"],
        )

    def test_build_codex_command_for_yolo_session(self):
        command = build_codex_command(prompt="fix it", workdir="/repo", yolo=True)
        self.assertEqual(
            command,
            ["codex", "--dangerously-bypass-approvals-and-sandbox", "exec", "--skip-git-repo-check", "--json", "-C", "/repo", "fix it"],
        )

    def test_iter_events_extracts_thread_started(self):
        process = CodexProcess(
            process=FakeProcess(stdout_text='{"type":"thread.started","thread_id":"thread-123"}\n'),
            command=["codex"],
        )

        events = list(process.iter_events())

        self.assertEqual(events, [StreamEvent(kind="raw_event", payload={"type": "thread.started", "thread_id": "thread-123"}, raw_line='{"type":"thread.started","thread_id":"thread-123"}')])
        self.assertEqual(process.codex_thread_id, "thread-123")

    def test_iter_events_yields_bad_line_error_and_continues(self):
        process = CodexProcess(
            process=FakeProcess(
                stdout_text='not-json\n{"type":"thread.started","thread_id":"thread-123"}\n'
            ),
            command=["codex"],
        )

        events = list(process.iter_events())

        self.assertEqual(events[0].kind, "relay_error")
        self.assertEqual(events[0].payload["reason"], "invalid_json_line")
        self.assertEqual(events[0].raw_line, "not-json")
        self.assertEqual(events[1].kind, "raw_event")
        self.assertEqual(process.codex_thread_id, "thread-123")

    def test_iter_events_reports_non_zero_exit(self):
        process = CodexProcess(
            process=FakeProcess(
                stdout_text='{"type":"thread.started","thread_id":"thread-123"}\n',
                stderr_text="fatal failure",
                returncode=7,
            ),
            command=["codex"],
        )

        events = list(process.iter_events())

        self.assertEqual(events[-1].kind, "relay_error")
        self.assertEqual(events[-1].payload["reason"], "process_exit")
        self.assertEqual(events[-1].payload["exit_code"], 7)
        self.assertEqual(events[-1].payload["stderr"], "fatal failure")

    def test_start_codex_process_raises_spawn_error(self):
        def failing_popen(*_args, **_kwargs):
            raise FileNotFoundError("codex not found")

        with self.assertRaises(CodexSpawnError):
            start_codex_process(prompt="x", workdir="/repo", popen_factory=failing_popen)

    def test_start_codex_process_uses_expected_popen_args(self):
        recorded = {}

        def fake_popen(command, **kwargs):
            recorded["command"] = command
            recorded["kwargs"] = kwargs
            return FakeProcess()

        codex_process = start_codex_process(prompt="x", workdir="/repo", popen_factory=fake_popen)

        self.assertEqual(
            codex_process.command,
            ["codex", "-a", "never", "-s", "workspace-write", "exec", "--skip-git-repo-check", "--json", "-C", "/repo", "x"],
        )
        self.assertEqual(recorded["kwargs"]["cwd"], "/repo")
        self.assertIsNotNone(recorded["kwargs"]["stdout"])
        self.assertIsNotNone(recorded["kwargs"]["stderr"])


if __name__ == "__main__":
    unittest.main()
