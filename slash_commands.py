"""Slash command handlers for the coding-relay plugin."""

from __future__ import annotations

try:
    from .relay_runtime import get_active_relay, set_relay_mode, exit_coding_mode
except ImportError:  # pragma: no cover - direct import compatibility
    from relay_runtime import get_active_relay, set_relay_mode, exit_coding_mode


def handle_relay_back_command(_raw_args, **kwargs):
    """Exit coding mode for the current chat."""
    chat_id = _extract_chat_id(kwargs)
    if exit_coding_mode_for_chat(chat_id):
        return "已退出 coding mode，Hermes 重新接管。"
    return "当前 chat 不在 coding mode。可先通过 coding_handoff 进入 relay 会话。"


def handle_relay_mode_command(raw_args, **kwargs):
    """Show or update the relay execution mode for the current chat."""
    chat_id = _extract_chat_id(kwargs)
    if not isinstance(chat_id, str) or not chat_id:
        return _relay_mode_help()

    state = get_active_relay(chat_id)
    if state is None:
        return "当前 chat 不在 coding mode。可先通过 coding_handoff 进入 relay 会话。"

    requested = (raw_args or "").strip().lower()
    if not requested or requested == "status":
        return _describe_active_mode(state)

    try:
        updated = set_relay_mode(chat_id, requested)
    except ValueError:
        return _relay_mode_help()

    return f"已切换 relay 模式：{_format_mode_name(updated)}。"


def exit_coding_mode_for_chat(chat_id: str | None) -> bool:
    """Shared exit helper used by both slash command and gateway hook."""
    return exit_coding_mode(chat_id)


def _describe_active_mode(state) -> str:
    return (
        "当前 relay 模式："
        f"{_format_mode_name(state)}。"
    )


def _format_mode_name(state) -> str:
    if getattr(state, "yolo", False):
        return "yolo（danger-full-access）"
    sandbox_mode = getattr(state, "sandbox_mode", "")
    if sandbox_mode == "read-only":
        return "readonly（read-only）"
    return "safe（workspace-write）"


def _relay_mode_help() -> str:
    return "用法：/relay-mode [status|safe|readonly|yolo]"


def _extract_chat_id(kwargs) -> str | None:
    if isinstance(kwargs.get("chat_id"), str):
        return kwargs["chat_id"]
    event = kwargs.get("event")
    if isinstance(event, dict) and isinstance(event.get("chat_id"), str):
        return event["chat_id"]
    return None
