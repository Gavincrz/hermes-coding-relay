import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import session_store


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.sessions_path = Path(self.temp_dir.name) / "run" / "sessions.json"
        self.original_sessions_path = session_store.SESSIONS_PATH
        session_store.SESSIONS_PATH = self.sessions_path
        self.addCleanup(setattr, session_store, "SESSIONS_PATH", self.original_sessions_path)

    def test_upsert_creates_session_summary_from_turn_artifacts(self):
        record = session_store.upsert_session_record(
            codex_thread_id="thread-123",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="重构配置模块并补测试",
            agent_texts=["已拆分 parser 和 validator。"],
            command_runs=[{"command": "pytest -q", "exit_code": 0, "status": "completed"}],
            file_changes=[
                {
                    "path": "config.py",
                    "changes": [{"path": "config.py"}, {"path": "tests/test_config.py"}],
                }
            ],
            now=datetime(2026, 5, 9, 10, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(record["provider"], "codex")
        self.assertEqual(record["resume_token"], "thread-123")
        self.assertEqual(record["codex_thread_id"], "thread-123")
        self.assertEqual(record["created_at"], "2026-05-09T10:00:00+00:00")
        self.assertEqual(record["last_active_at"], "2026-05-09T10:00:00+00:00")
        self.assertEqual(record["last_files"], ["config.py", "tests/test_config.py"])
        self.assertIn("目标：重构配置模块并补测试", record["summary"])
        self.assertIn("最近结果：已拆分 parser 和 validator。", record["summary"])
        self.assertIn("最近文件：config.py, tests/test_config.py", record["summary"])
        self.assertIn("最近检查：pytest -q (exit 0)", record["summary"])

        stored = session_store.load_session_store()
        self.assertEqual(stored["sessions"], [record])

    def test_upsert_updates_existing_record_and_preserves_goal(self):
        session_store.upsert_session_record(
            codex_thread_id="thread-123",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="重构配置模块并补测试",
            agent_texts=["第一轮完成。"],
            command_runs=[{"command": "pytest -q", "exit_code": 0, "status": "completed"}],
            file_changes=[{"path": "config.py", "changes": [{"path": "config.py"}]}],
            now=datetime(2026, 5, 9, 10, 0, 0, tzinfo=timezone.utc),
        )

        record = session_store.upsert_session_record(
            codex_thread_id="thread-123",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="继续",
            agent_texts=["已补充 validator 覆盖。"],
            command_runs=[],
            file_changes=[{"path": "tests/test_validator.py", "changes": [{"path": "tests/test_validator.py"}]}],
            now=datetime(2026, 5, 9, 11, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(record["created_at"], "2026-05-09T10:00:00+00:00")
        self.assertEqual(record["last_active_at"], "2026-05-09T11:00:00+00:00")
        self.assertEqual(record["last_files"], ["config.py", "tests/test_validator.py"])
        self.assertIn("目标：重构配置模块并补测试", record["summary"])
        self.assertIn("最近结果：已补充 validator 覆盖。", record["summary"])
        self.assertIn("最近检查：pytest -q (exit 0)", record["summary"])

    def test_find_session_record_supports_resume_token_normalization(self):
        session_store.upsert_session_record(
            codex_thread_id="thread-123",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="继续修复",
            agent_texts=["完成"],
            command_runs=[],
            file_changes=[],
            now=datetime(2026, 5, 9, 10, 0, 0, tzinfo=timezone.utc),
        )

        record = session_store.find_session_record("thread-123")

        self.assertEqual(record["resume_token"], "thread-123")
        self.assertEqual(record["provider"], "codex")

    def test_list_session_records_filters_by_workdir_and_orders_recent_first(self):
        session_store.upsert_session_record(
            codex_thread_id="thread-old",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="旧任务",
            agent_texts=["旧结果"],
            command_runs=[],
            file_changes=[],
            now=datetime(2026, 5, 9, 10, 0, 0, tzinfo=timezone.utc),
        )
        session_store.upsert_session_record(
            codex_thread_id="thread-new",
            agent="codex",
            workdir="/home/dontstarve/projects/coding-relay",
            prompt="新任务",
            agent_texts=["新结果"],
            command_runs=[],
            file_changes=[],
            now=datetime(2026, 5, 9, 11, 0, 0, tzinfo=timezone.utc),
        )
        session_store.upsert_session_record(
            codex_thread_id="thread-other",
            agent="codex",
            workdir="/home/dontstarve/projects/other-project",
            prompt="其他任务",
            agent_texts=["其他结果"],
            command_runs=[],
            file_changes=[],
            now=datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc),
        )

        records = session_store.list_session_records(workdir="/home/dontstarve/projects/coding-relay", limit=5)

        self.assertEqual([record["resume_token"] for record in records], ["thread-new", "thread-old"])

    def test_load_session_store_tolerates_invalid_json(self):
        self.sessions_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions_path.write_text("{bad json", encoding="utf-8")

        self.assertEqual(session_store.load_session_store(), {"sessions": []})


if __name__ == "__main__":
    unittest.main()
