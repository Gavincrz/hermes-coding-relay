"""Gateway hook for coding-mode interception."""

from __future__ import annotations

try:
    from .output_formatter import safe_format_turn_output
    from .relay_context import extract_chat_id, extract_message_id, extract_text
    from .relay_runtime import get_active_relay, persist_session_turn, run_codex_turn
    from .slash_commands import handle_relay_back_command, handle_relay_mode_command
except ImportError:  # pragma: no cover - direct import compatibility
    from output_formatter import safe_format_turn_output
    from relay_context import extract_chat_id, extract_message_id, extract_text
    from relay_runtime import get_active_relay, persist_session_turn, run_codex_turn
    from slash_commands import handle_relay_back_command, handle_relay_mode_command


def pre_gateway_dispatch(**kwargs):
    """Bypass Hermes LLM when the chat is in coding mode."""
    chat_id = extract_chat_id(kwargs)
    state = get_active_relay(chat_id)
    if state is None:
        return None

    text = extract_text(kwargs)
    command = text.strip()
    if command == "/relay-back":
        handle_relay_back_command("", chat_id=chat_id)
        return None
    if command.startswith("/relay-mode"):
        raw_args = command[len("/relay-mode") :].strip()
        return {
            "action": "skip",
            "relay": {
                "chat_id": state.chat_id,
                "codex_thread_id": state.codex_thread_id,
                "messages": [handle_relay_mode_command(raw_args, chat_id=chat_id)],
                "errors": [],
            },
        }

    turn_result = run_codex_turn(state, text, message_id=extract_message_id(kwargs))
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
