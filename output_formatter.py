"""Format relay turn artifacts into stable user-facing output."""

from __future__ import annotations

from typing import Any


MAX_OUTPUT_SNIPPET = 160
MAX_FILE_LIST = 3


def safe_format_turn_output(turn_result: Any) -> list[str]:
    """Format one turn without letting formatter failures break the relay flow."""
    try:
        return format_turn_output(turn_result)
    except Exception:
        return _fallback_messages(turn_result)


def format_turn_output(turn_result: Any) -> list[str]:
    """Render turn events in the order they were observed."""
    messages: list[str] = []
    for event in _collect_turn_events(turn_result):
        messages.extend(format_turn_event(event))

    if messages:
        return [message for message in messages if isinstance(message, str) and message]

    messages.extend(_collect_agent_texts(turn_result))
    messages.extend(_format_command_runs(getattr(turn_result, "command_runs", [])))
    messages.extend(_format_file_changes(getattr(turn_result, "file_changes", [])))
    messages.extend(_format_errors(getattr(turn_result, "errors", [])))
    return [message for message in messages if isinstance(message, str) and message]


def format_turn_event(event: Any) -> list[str]:
    """Format one normalized relay event into zero or more user-facing messages."""
    if isinstance(event, dict):
        kind = _compact(event.get("kind"))
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
    else:
        kind = _compact(getattr(event, "kind", ""))
        payload = getattr(event, "payload", {})
        if not isinstance(payload, dict):
            payload = {}

    if kind == "agent_text":
        text = _normalize_agent_text(payload.get("text"))
        return [text] if text else []

    if kind in {"command_started", "command_finished"}:
        return _format_command_event(kind, payload)

    if kind == "file_change":
        return _format_file_change_event(payload)

    if kind == "relay_error":
        return [_format_error(payload)]

    return []


def _collect_turn_events(turn_result: Any) -> list[Any]:
    events = getattr(turn_result, "events", [])
    if isinstance(events, list) and events:
        return events
    return []


def _collect_agent_texts(turn_result: Any) -> list[str]:
    agent_texts = getattr(turn_result, "agent_texts", [])
    if not isinstance(agent_texts, list):
        return []
    normalized = [_normalize_agent_text(text) for text in agent_texts if isinstance(text, str)]
    return [text for text in normalized if text]


def _format_command_runs(command_runs: Any) -> list[str]:
    if not isinstance(command_runs, list):
        return []

    messages: list[str] = []
    for command_run in command_runs:
        if not isinstance(command_run, dict):
            continue
        event_kind = _compact(command_run.get("event_kind"))
        payload = {
            "command": command_run.get("command"),
            "output": command_run.get("output"),
            "exit_code": command_run.get("exit_code"),
            "status": command_run.get("status"),
        }
        messages.extend(_format_command_event(event_kind, payload))
    return messages


def _format_command_event(event_kind: str, payload: dict[str, Any]) -> list[str]:
    command = _compact(payload.get("command"))
    if not command:
        return []

    if event_kind == "command_started":
        return [f"**正在执行**\n`{command}`"]

    if event_kind != "command_finished":
        return []

    summary = f"**已完成**\n`{command}`"
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int):
        summary += f" (exit {exit_code})"
    output = _compact_output(payload.get("output"))
    if output:
        summary += f"\n```text\n{output}\n```"
    return [summary]


def _format_file_changes(file_changes: Any) -> list[str]:
    if not isinstance(file_changes, list):
        return []

    messages: list[str] = []
    for file_change in file_changes:
        if not isinstance(file_change, dict):
            continue
        if _compact(file_change.get("phase")) not in {"", "completed"}:
            continue

        paths = _extract_change_paths(file_change)
        if not paths:
            continue
        messages.append(_build_file_change_message(paths))
    return messages


def _format_file_change_event(payload: dict[str, Any]) -> list[str]:
    if _compact(payload.get("phase")) not in {"", "completed"}:
        return []

    paths = _extract_change_paths(payload)
    if not paths:
        return []
    return [_build_file_change_message(paths)]


def _extract_change_paths(file_change: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    primary_path = _compact(file_change.get("path"))
    if primary_path:
        paths.append(primary_path)

    changes = file_change.get("changes")
    if not isinstance(changes, list):
        return paths

    for change in changes:
        if not isinstance(change, dict):
            continue
        path = _compact(change.get("path"))
        if path and path not in paths:
            paths.append(path)
    return paths


def _format_errors(errors: Any) -> list[str]:
    if not isinstance(errors, list):
        return []
    return [_format_error(error) for error in errors if isinstance(error, dict)]


def _format_error(error: dict[str, Any]) -> str:
    reason = _compact(error.get("reason"))
    message = _compact(error.get("message"))

    if reason == "spawn_failed":
        lower_message = message.lower()
        if "no such file" in lower_message or "not found" in lower_message:
            return "**执行失败**\nCodex CLI 不可用：未找到 `codex` 命令，请先确认安装并已加入 PATH。"
        return f"**执行失败**\n启动 Codex 失败：{message or '无法创建 Codex 进程。'}"

    if reason == "invalid_json_line":
        return "**执行失败**\nCodex 输出中存在无法解析的 JSON 行，已跳过异常内容并继续处理其余事件。"

    if reason == "process_exit":
        exit_code = error.get("exit_code")
        summary = "Codex 非正常退出"
        if isinstance(exit_code, int):
            summary += f" (exit {exit_code})"
        stderr = _compact_output(error.get("stderr"))
        if stderr:
            summary += f"：{stderr}"
        elif message:
            summary += f"：{message}"
        return f"**执行失败**\n{summary}"

    if reason in {"codex_error", "codex_item_error"}:
        return f"**执行失败**\nCodex 返回错误：{message or '请查看上一轮上下文。'}"

    if reason == "relay_output_failed":
        return f"**执行失败**\nrelay 输出回传失败：{message or '请查看 gateway 日志。'}"

    return f"**执行失败**\n{message or 'relay 遇到未分类错误。'}"


def _fallback_messages(turn_result: Any) -> list[str]:
    try:
        messages = _collect_agent_texts(turn_result)
    except Exception:
        messages = []
    if messages:
        return messages
    return ["relay 输出格式化失败，已跳过格式化步骤。"]


def _compact(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _compact_output(value: Any) -> str:
    compact = _compact(value)
    if len(compact) <= MAX_OUTPUT_SNIPPET:
        return compact
    return compact[: MAX_OUTPUT_SNIPPET - 1].rstrip() + "…"


def _normalize_agent_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _build_file_change_message(paths: list[str]) -> str:
    displayed_paths = paths[:MAX_FILE_LIST]
    lines = [f"- `{path}`" for path in displayed_paths]
    if len(paths) > MAX_FILE_LIST:
        lines.append(f"- 另有 {len(paths) - MAX_FILE_LIST} 个文件")
    return "**已修改文件**\n" + "\n".join(lines)
