"""Gateway hook for coding-mode interception."""

from __future__ import annotations

try:
    from .output_formatter import safe_format_turn_output
    from .relay_runtime import get_active_relay, persist_session_turn, run_codex_turn
    from .slash_commands import exit_coding_mode_for_chat
except ImportError:  # pragma: no cover - direct import compatibility
    from output_formatter import safe_format_turn_output
    from relay_runtime import get_active_relay, persist_session_turn, run_codex_turn
    from slash_commands import exit_coding_mode_for_chat


def pre_gateway_dispatch(**kwargs):
    """Bypass Hermes LLM when the chat is in coding mode."""
    chat_id = _extract_chat_id(kwargs)
    state = get_active_relay(chat_id)
    if state is None:
        return None

    text = _extract_text(kwargs)
    if text.strip() == "/back":
        exit_coding_mode_for_chat(chat_id)
        return None

    turn_result = run_codex_turn(state, text, message_id=_extract_message_id(kwargs))
    turn_messages = safe_format_turn_output(turn_result)
    persist_session_turn(state, text, turn_result)
    return {
        "action": "skip",
        "relay": {
            "chat_id": state.chat_id,
            "codex_thread_id": turn_result.codex_thread_id,
            "messages": turn_messages,
            "errors": turn_result.errors,
        },
    }


def _extract_chat_id(kwargs) -> str | None:
    if isinstance(kwargs.get("chat_id"), str):
        return kwargs["chat_id"]
    event = kwargs.get("event")
    if isinstance(event, dict) and isinstance(event.get("chat_id"), str):
        return event["chat_id"]
    return None


def _extract_text(kwargs) -> str:
    for key in ("text", "message", "content", "raw_text"):
        value = kwargs.get(key)
        if isinstance(value, str):
            return value
    event = kwargs.get("event")
    if isinstance(event, dict):
        for key in ("text", "message", "content", "raw_text"):
            value = event.get(key)
            if isinstance(value, str):
                return value
    return ""


def _extract_message_id(kwargs) -> str | None:
    if isinstance(kwargs.get("message_id"), str):
        return kwargs["message_id"]
    event = kwargs.get("event")
    if isinstance(event, dict) and isinstance(event.get("message_id"), str):
        return event["message_id"]
    return None
