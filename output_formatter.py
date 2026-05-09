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
    """Render agent text, command/file summaries, and user-facing errors."""
    messages: list[str] = []
    messages.extend(_collect_agent_texts(turn_result))
    messages.extend(_format_command_runs(getattr(turn_result, "command_runs", [])))
    messages.extend(_format_file_changes(getattr(turn_result, "file_changes", [])))
    messages.extend(_format_errors(getattr(turn_result, "errors", [])))
    return [message for message in messages if isinstance(message, str) and message]


def _collect_agent_texts(turn_result: Any) -> list[str]:
    agent_texts = getattr(turn_result, "agent_texts", [])
    if not isinstance(agent_texts, list):
        return []
    return [text for text in agent_texts if isinstance(text, str) and text]


def _format_command_runs(command_runs: Any) -> list[str]:
    if not isinstance(command_runs, list):
        return []

    messages: list[str] = []
    for command_run in command_runs:
        if not isinstance(command_run, dict):
            continue

        command = _compact(command_run.get("command"))
        if not command:
            continue

        event_kind = _compact(command_run.get("event_kind"))
        if event_kind == "command_started":
            messages.append(f"执行命令：{command}")
            continue

        exit_code = command_run.get("exit_code")
        status = _compact(command_run.get("status"))
        summary = f"命令完成：{command}"
        if isinstance(exit_code, int):
            summary += f" (exit {exit_code})"
        elif status:
            summary += f" ({status})"

        output = _compact_output(command_run.get("output"))
        if output:
            summary += f" 输出摘要：{output}"
        messages.append(summary)

    return messages


def _format_file_changes(file_changes: Any) -> list[str]:
    if not isinstance(file_changes, list):
        return []

    completed_paths: list[str] = []
    for file_change in file_changes:
        if not isinstance(file_change, dict):
            continue
        if _compact(file_change.get("phase")) not in {"", "completed"}:
            continue

        for path in _extract_change_paths(file_change):
            if path not in completed_paths:
                completed_paths.append(path)

    if not completed_paths:
        return []

    if len(completed_paths) == 1:
        return [f"文件变更：{completed_paths[0]}"]

    displayed = ", ".join(completed_paths[:MAX_FILE_LIST])
    if len(completed_paths) > MAX_FILE_LIST:
        displayed += f" 等 {len(completed_paths)} 个文件"
    return [f"文件变更：{displayed}"]


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
            return "Codex CLI 不可用：未找到 `codex` 命令，请先确认安装并已加入 PATH。"
        return f"启动 Codex 失败：{message or '无法创建 Codex 进程。'}"

    if reason == "invalid_json_line":
        return "Codex 输出中存在无法解析的 JSON 行，已跳过异常内容并继续处理其余事件。"

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
        return summary

    if reason in {"codex_error", "codex_item_error"}:
        return f"Codex 返回错误：{message or '请查看上一轮上下文。'}"

    return message or "relay 遇到未分类错误。"


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
