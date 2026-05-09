import unittest

from agent_spawner import StreamEvent
from relay_runtime import ActiveRelayState, run_codex_turn


class FakeCodexProcess:
    def __init__(self, events):
        self.process = None
        self._events = events

    def iter_events(self):
        yield from self._events


class RelayRuntimeTests(unittest.TestCase):
    def test_run_codex_turn_keeps_event_context_for_formatter(self):
        events = [
            StreamEvent(kind="raw_event", payload={"type": "thread.started", "thread_id": "thread-123"}),
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "item.started",
                    "item": {
                        "id": "cmd-1",
                        "type": "command_execution",
                        "command": "pytest -q",
                        "status": "in_progress",
                    },
                },
            ),
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "item.completed",
                    "item": {
                        "id": "cmd-1",
                        "type": "command_execution",
                        "command": "pytest -q",
                        "status": "completed",
                        "exit_code": 0,
                        "aggregated_output": "1 passed\n",
                    },
                },
            ),
            StreamEvent(
                kind="raw_event",
                payload={
                    "type": "item.completed",
                    "item": {
                        "id": "file-1",
                        "type": "file_change",
                        "status": "completed",
                        "path": "output_formatter.py",
                        "changes": [{"path": "output_formatter.py"}],
                    },
                },
            ),
        ]
        state = ActiveRelayState(
            chat_id="chat-1",
            agent="codex",
            codex_thread_id=None,
            workdir="/home/dontstarve/projects/coding-relay",
        )

        result = run_codex_turn(state, "continue", process_starter=lambda **_: FakeCodexProcess(events))

        self.assertEqual(result.codex_thread_id, "thread-123")
        self.assertEqual(
            result.command_runs,
            [
                {
                    "item_id": "cmd-1",
                    "command": "pytest -q",
                    "output": "",
                    "exit_code": None,
                    "status": "in_progress",
                    "event_kind": "command_started",
                },
                {
                    "item_id": "cmd-1",
                    "command": "pytest -q",
                    "output": "1 passed\n",
                    "exit_code": 0,
                    "status": "completed",
                    "event_kind": "command_finished",
                },
            ],
        )
        self.assertEqual(
            result.file_changes,
            [
                {
                    "item_id": "file-1",
                    "phase": "completed",
                    "status": "completed",
                    "path": "output_formatter.py",
                    "changes": [{"path": "output_formatter.py"}],
                    "event_kind": "file_change",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
