"""Gateway hook for coding-mode interception."""

from __future__ import annotations

try:
    from .relay_delivery import has_delivery_context, resolve_source, send_chat_message, start_streaming_turn
    from .relay_context import extract_chat_id, extract_message_id, extract_text
    from .relay_runtime import (
        get_active_relay,
        persist_session_turn,
        prune_stale_relays_for_session_key,
        run_codex_turn,
    )
    from .slash_commands import handle_relay_back_command, handle_relay_mode_command
except ImportError:  # pragma: no cover - direct import compatibility
    from relay_delivery import has_delivery_context, resolve_source, send_chat_message, start_streaming_turn
    from relay_context import extract_chat_id, extract_message_id, extract_text
    from relay_runtime import get_active_relay, persist_session_turn, prune_stale_relays_for_session_key, run_codex_turn
    from slash_commands import handle_relay_back_command, handle_relay_mode_command


def pre_gateway_dispatch(**kwargs):
    """Bypass Hermes LLM when the chat is in coding mode."""
    chat_id = extract_chat_id(kwargs)
    session_entry = _resolve_session_entry(kwargs)
    session_id = getattr(session_entry, "session_id", None)
    session_key = getattr(session_entry, "session_key", None)

    event = kwargs.get("event")
    source = resolve_source(kwargs)

    prune_stale_relays_for_session_key(session_key, keep_session_id=session_id)

    state = get_active_relay(session_id)
    if state is None:
        return None

    text = extract_text(kwargs)
    command = text.strip()

    if command == "/relay-back":
        handle_relay_back_command("", session_id=session_id)
        send_chat_message(kwargs, source, "已退出 coding-relay 模式，回到 Hermes 对话。")
        return {"action": "skip"}

    if command.startswith("/relay-mode"):
        raw_args = command[len("/relay-mode") :].strip()
        mode_msg = handle_relay_mode_command(raw_args, session_id=session_id)
        send_chat_message(kwargs, source, mode_msg)
        return {"action": "skip"}

    if not has_delivery_context(kwargs, source):
        turn_result = run_codex_turn(state, text, message_id=extract_message_id(kwargs))
        persist_session_turn(state, text, turn_result)
        return {"action": "skip"}

    if state.turn_in_flight:
        send_chat_message(kwargs, source, "上一轮 Codex 仍在执行，请稍后再发消息。")
        return {"action": "skip"}

    start_streaming_turn(
        kwargs=kwargs,
        source=source,
        state=state,
        prompt=text,
        message_id=extract_message_id(kwargs),
    )

    return {"action": "skip"}


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
