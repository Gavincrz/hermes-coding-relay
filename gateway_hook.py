"""Gateway hook for coding-mode interception."""

from __future__ import annotations

try:
    from .output_formatter import safe_format_turn_output
    from .relay_context import extract_chat_id, extract_message_id, extract_text
    from .relay_runtime import (
        get_active_relay,
        persist_session_turn,
        prune_stale_relays_for_session_key,
        run_codex_turn,
    )
    from .slash_commands import handle_relay_back_command, handle_relay_mode_command
except ImportError:  # pragma: no cover - direct import compatibility
    from output_formatter import safe_format_turn_output
    from relay_context import extract_chat_id, extract_message_id, extract_text
    from relay_runtime import get_active_relay, persist_session_turn, prune_stale_relays_for_session_key, run_codex_turn
    from slash_commands import handle_relay_back_command, handle_relay_mode_command


def pre_gateway_dispatch(**kwargs):
    """Bypass Hermes LLM when the chat is in coding mode."""
    chat_id = extract_chat_id(kwargs)
    session_entry = _resolve_session_entry(kwargs)
    session_id = getattr(session_entry, "session_id", None)
    session_key = getattr(session_entry, "session_key", None)
    prune_stale_relays_for_session_key(session_key, keep_session_id=session_id)

    state = get_active_relay(session_id)
    if state is None:
        return None

    text = extract_text(kwargs)
    command = text.strip()
    if command == "/relay-back":
        handle_relay_back_command("", session_id=session_id)
        return None
    if command.startswith("/relay-mode"):
        raw_args = command[len("/relay-mode") :].strip()
        return {
            "action": "skip",
            "relay": {
                "chat_id": chat_id,
                "session_id": state.session_id,
                "codex_thread_id": state.codex_thread_id,
                "messages": [handle_relay_mode_command(raw_args, session_id=session_id)],
                "errors": [],
            },
        }

    turn_result = run_codex_turn(state, text, message_id=extract_message_id(kwargs))
    turn_messages = safe_format_turn_output(turn_result)
    persist_session_turn(state, text, turn_result)
    return {
        "action": "skip",
        "relay": {
            "chat_id": chat_id,
            "session_id": state.session_id,
            "codex_thread_id": turn_result.codex_thread_id,
            "messages": turn_messages,
            "errors": turn_result.errors,
        },
    }


def _resolve_session_entry(kwargs):
    event = kwargs.get("event")
    session_store = kwargs.get("session_store")
    source = getattr(event, "source", None)
    if session_store is None or source is None:
        return None
    try:
        return session_store.get_or_create_session(source)
    except Exception:
        return None
