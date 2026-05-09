"""Slash command handlers for the coding-relay plugin."""

from __future__ import annotations

try:
    from .relay_runtime import exit_coding_mode
except ImportError:  # pragma: no cover - direct import compatibility
    from relay_runtime import exit_coding_mode


def handle_back_command(_raw_args, **kwargs):
    """Exit coding mode for the current chat."""
    chat_id = _extract_chat_id(kwargs)
    if exit_coding_mode_for_chat(chat_id):
        return "已退出 coding mode，Hermes 重新接管。"
    return "当前 chat 不在 coding mode。"


def exit_coding_mode_for_chat(chat_id: str | None) -> bool:
    """Shared exit helper used by both slash command and gateway hook."""
    return exit_coding_mode(chat_id)


def _extract_chat_id(kwargs) -> str | None:
    if isinstance(kwargs.get("chat_id"), str):
        return kwargs["chat_id"]
    event = kwargs.get("event")
    if isinstance(event, dict) and isinstance(event.get("chat_id"), str):
        return event["chat_id"]
    return None
