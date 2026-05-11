import unittest

from agent_spawner import StreamEvent
from relay_runtime import (
    ActiveRelayState,
    activate_relay,
    clear_active_relays,
    ensure_workdir_ready,
    get_active_relay,
    prune_stale_relays_for_session_key,
    run_codex_turn,
    set_relay_mode,
    validate_workdir,
)


class FakeCodexProcess:
    def __init__(self, events):
        self.process = None
        self._events = events

    def iter_events(self):
        yield from self._events


class RelayRuntimeTests(unittest.TestCase):
    def setUp(self):
        clear_active_relays()

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
            session_id="sess-1",
            session_key="key-1",
            agent="codex",
            codex_thread_id=None,
            workdir="/home/dontstarve/projects/coding-relay",
        )

        result = run_codex_turn(state, "continue", process_starter=lambda **_: FakeCodexProcess(events))

        self.assertEqual(result.codex_thread_id, "thread-123")
        self.assertEqual(
            result.events,
            [
                {"kind": "session_init", "payload": {"codex_thread_id": "thread-123"}},
                {
                    "kind": "command_started",
                    "payload": {
                        "item_id": "cmd-1",
                        "command": "pytest -q",
                        "output": "",
                        "exit_code": None,
                        "status": "in_progress",
                    },
                },
                {
                    "kind": "command_finished",
                    "payload": {
                        "item_id": "cmd-1",
                        "command": "pytest -q",
                        "output": "1 passed\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
                {
                    "kind": "file_change",
                    "payload": {
                        "item_id": "file-1",
                        "phase": "completed",
                        "status": "completed",
                        "path": "output_formatter.py",
                        "changes": [{"path": "output_formatter.py"}],
                    },
                },
            ],
        )
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

    def test_set_relay_mode_updates_active_state(self):
        state = activate_relay("sess-1", "/home/dontstarve/projects/coding-relay", "thread-123", session_key="key-1")
        self.assertEqual(state.sandbox_mode, "workspace-write")
        self.assertFalse(state.yolo)

        updated = set_relay_mode("sess-1", "readonly")
        self.assertEqual(updated.sandbox_mode, "read-only")
        self.assertFalse(updated.yolo)

        updated = set_relay_mode("sess-1", "yolo")
        self.assertEqual(updated.sandbox_mode, "danger-full-access")
        self.assertTrue(updated.yolo)

    def test_activate_relay_prunes_stale_state_for_same_session_key(self):
        activate_relay("sess-old", "/home/dontstarve/projects/coding-relay", "thread-old", session_key="key-1")
        state = activate_relay("sess-new", "/home/dontstarve/projects/coding-relay", "thread-new", session_key="key-1")

        self.assertIsNone(get_active_relay("sess-old"))
        self.assertEqual(state.session_id, "sess-new")

    def test_prune_stale_relays_for_session_key_removes_other_session_ids(self):
        activate_relay("sess-a", "/home/dontstarve/projects/coding-relay", "thread-a", session_key="key-1")
        activate_relay("sess-b", "/home/dontstarve/projects/coding-relay", "thread-b", session_key="key-2")

        removed = prune_stale_relays_for_session_key("key-1", keep_session_id="sess-missing")

        self.assertEqual(removed, 1)

    def test_ensure_workdir_ready_creates_missing_dir_and_git(self):
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp()
        try:
            target = tmp + "/sub/project"
            self.assertFalse(__import__("os").path.exists(target))
            ensure_workdir_ready(target)
            self.assertTrue(__import__("os").path.isdir(target))
            self.assertTrue(__import__("os").path.isdir(target + "/.git"))
        finally:
            shutil.rmtree(tmp)

    def test_ensure_workdir_ready_skips_init_if_git_exists(self):
        import shutil
        import subprocess
        import tempfile

        tmp = tempfile.mkdtemp()
        try:
            subprocess.run(["git", "init"], cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            head_before = (__import__("os").path.isdir(tmp + "/.git"))
            ensure_workdir_ready(tmp)
            self.assertTrue(head_before)
        finally:
            shutil.rmtree(tmp)

    def test_validate_workdir_rejects_project_root_itself(self):
        with self.assertRaises(ValueError):
            validate_workdir("/home/dontstarve/projects")

    def test_validate_workdir_allows_project_subdirectory(self):
        self.assertEqual(
            validate_workdir("/home/dontstarve/projects/coding-relay"),
            "/home/dontstarve/projects/coding-relay",
        )


if __name__ == "__main__":
    unittest.main()
