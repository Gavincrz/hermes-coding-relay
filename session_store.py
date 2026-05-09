"""Session persistence for Codex relay runtime state."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_DIR = Path(__file__).resolve().parent / "run"
SESSIONS_PATH = RUN_DIR / "sessions.json"
MAX_SUMMARY_TEXT = 120
MAX_LAST_FILES = 5
_SUMMARY_LABELS = ("目标", "最近结果", "最近文件", "最近检查")


def upsert_session_record(
    *,
    codex_thread_id: str,
    agent: str,
    workdir: str,
    prompt: str,
    agent_texts: list[str],
    command_runs: list[dict[str, Any]],
    file_changes: list[dict[str, Any]],
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create or update one persisted Codex session record."""
    resolved_path = path or SESSIONS_PATH
    store = load_session_store(resolved_path)
    sessions = store["sessions"]
    record = _find_record(sessions, codex_thread_id)

    timestamp = _isoformat(now or datetime.now().astimezone())
    existing_summary = _as_str(record.get("summary")) if record else ""
    goal = _extract_goal(existing_summary) or _extract_goal_from_prompt(prompt)
    recent_result = _extract_recent_result(agent_texts) or _extract_summary_field(existing_summary, "最近结果")
    last_files = _merge_last_files(
        existing_last_files=_as_str_list(record.get("last_files")) if record else [],
        file_changes=file_changes,
    )
    last_check = _extract_last_check(command_runs) or _extract_summary_field(existing_summary, "最近检查")

    updated = {
        "codex_thread_id": codex_thread_id,
        "agent": agent,
        "workdir": workdir,
        "created_at": _as_str(record.get("created_at")) if record else timestamp,
        "last_active_at": timestamp,
        "summary": _build_summary(
            goal=goal,
            recent_result=recent_result,
            last_files=last_files,
            last_check=last_check,
        ),
        "last_files": last_files,
    }

    if record is None:
        sessions.append(updated)
    else:
        index = sessions.index(record)
        sessions[index] = updated

    _write_session_store(store, resolved_path)
    return updated


def load_session_store(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Load the session store from disk, tolerating missing or malformed files."""
    resolved_path = path or SESSIONS_PATH
    if not resolved_path.exists():
        return {"sessions": []}

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": []}

    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        return {"sessions": []}

    normalized = [dict(session) for session in sessions if isinstance(session, dict)]
    return {"sessions": normalized}


def _write_session_store(store: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _find_record(sessions: list[dict[str, Any]], codex_thread_id: str) -> dict[str, Any] | None:
    for session in sessions:
        if session.get("codex_thread_id") == codex_thread_id:
            return session
    return None


def _build_summary(*, goal: str, recent_result: str, last_files: list[str], last_check: str) -> str:
    sections = []
    if goal:
        sections.append(f"目标：{goal}")
    if recent_result:
        sections.append(f"最近结果：{recent_result}")
    if last_files:
        sections.append(f"最近文件：{', '.join(last_files)}")
    if last_check:
        sections.append(f"最近检查：{last_check}")
    return "；".join(sections)


def _extract_goal(summary: str) -> str:
    return _extract_summary_field(summary, "目标")


def _extract_summary_field(summary: str, label: str) -> str:
    if not summary:
        return ""
    pattern = rf"(?:^|；){re.escape(label)}：([^；]+)"
    match = re.search(pattern, summary)
    return _sanitize_excerpt(match.group(1)) if match else ""


def _extract_goal_from_prompt(prompt: str) -> str:
    normalized_prompt = _normalize_prompt(prompt)
    if not normalized_prompt:
        return ""
    return _sanitize_excerpt(normalized_prompt)


def _extract_recent_result(agent_texts: list[str]) -> str:
    for text in reversed(agent_texts):
        normalized = _sanitize_excerpt(text)
        if normalized:
            return normalized
    return ""


def _extract_last_check(command_runs: list[dict[str, Any]]) -> str:
    for command_run in reversed(command_runs):
        command = _sanitize_excerpt(_as_str(command_run.get("command")))
        if not command:
            continue

        if command_run.get("exit_code") is not None:
            return f"{command} (exit {command_run['exit_code']})"

        status = _sanitize_excerpt(_as_str(command_run.get("status")))
        if status:
            return f"{command} ({status})"
    return ""


def _merge_last_files(*, existing_last_files: list[str], file_changes: list[dict[str, Any]]) -> list[str]:
    collected = list(existing_last_files)
    for file_change in file_changes:
        path = _sanitize_path(_as_str(file_change.get("path")))
        if path:
            collected.append(path)

        changes = file_change.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            changed_path = _sanitize_path(_as_str(change.get("path")))
            if changed_path:
                collected.append(changed_path)

    deduped: list[str] = []
    for path in reversed(collected):
        if path not in deduped:
            deduped.append(path)
        if len(deduped) >= MAX_LAST_FILES:
            break
    deduped.reverse()
    return deduped


def _normalize_prompt(prompt: str) -> str:
    if not isinstance(prompt, str):
        return ""

    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _sanitize_excerpt(text: str) -> str:
    if not isinstance(text, str):
        return ""
    compact = " ".join(text.replace("；", ",").replace(";", ",").split())
    if len(compact) <= MAX_SUMMARY_TEXT:
        return compact
    return compact[: MAX_SUMMARY_TEXT - 1].rstrip() + "…"


def _sanitize_path(path: str) -> str:
    return _sanitize_excerpt(path)


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _isoformat(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()
