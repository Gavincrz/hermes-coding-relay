"""Gateway hook for coding-mode interception."""

from __future__ import annotations

import asyncio
import logging
import threading

try:
    from .output_formatter import format_turn_event, safe_format_turn_output
    from .relay_context import extract_chat_id, extract_message_id, extract_text
    from .relay_runtime import (
        get_active_relay,
        persist_session_turn,
        prune_stale_relays_for_session_key,
        run_codex_turn,
    )
    from .slash_commands import handle_relay_back_command, handle_relay_mode_command
except ImportError:  # pragma: no cover - direct import compatibility
    from output_formatter import format_turn_event, safe_format_turn_output
    from relay_context import extract_chat_id, extract_message_id, extract_text
    from relay_runtime import get_active_relay, persist_session_turn, prune_stale_relays_for_session_key, run_codex_turn
    from slash_commands import handle_relay_back_command, handle_relay_mode_command

_log = logging.getLogger("coding-relay.hook")
TURN_COMPLETE_MESSAGE = "Codex turn 已完成。"


def pre_gateway_dispatch(**kwargs):
    """Bypass Hermes LLM when the chat is in coding mode."""
    chat_id = extract_chat_id(kwargs)
    session_entry = _resolve_session_entry(kwargs)
    session_id = getattr(session_entry, "session_id", None)
    session_key = getattr(session_entry, "session_key", None)

    event = kwargs.get("event")
    source = getattr(event, "source", None) if event else None

    prune_stale_relays_for_session_key(session_key, keep_session_id=session_id)

    state = get_active_relay(session_id)
    if state is None:
        return None

    text = extract_text(kwargs)
    command = text.strip()

    if command == "/relay-back":
        handle_relay_back_command("", session_id=session_id)
        _send_chat_message(kwargs, source, "已退出 coding-relay 模式，回到 Hermes 对话。")
        return {"action": "skip"}

    if command.startswith("/relay-mode"):
        raw_args = command[len("/relay-mode") :].strip()
        mode_msg = handle_relay_mode_command(raw_args, session_id=session_id)
        _send_chat_message(kwargs, source, mode_msg)
        return {"action": "skip"}

    gateway = kwargs.get("gateway")
    if not gateway or not source:
        turn_result = run_codex_turn(state, text, message_id=extract_message_id(kwargs))
        persist_session_turn(state, text, turn_result)
        return {"action": "skip"}

    if state.turn_in_flight:
        _send_chat_message(kwargs, source, "上一轮 Codex 仍在执行，请稍后再发消息。")
        return {"action": "skip"}

    state.turn_in_flight = True
    worker = threading.Thread(
        target=_run_streamed_codex_turn,
        kwargs={
            "kwargs": kwargs,
            "source": source,
            "state": state,
            "prompt": text,
            "message_id": extract_message_id(kwargs),
        },
        daemon=True,
    )
    worker.start()

    return {"action": "skip"}


def _send_chat_message(kwargs, source, text):
    """Send a message back to the user via the platform adapter."""
    gateway = kwargs.get("gateway")
    if not gateway or not source:
        _log.warning("cannot send relay response: missing gateway or source")
        return

    adapter = gateway.adapters.get(source.platform)
    if not adapter:
        _log.warning("cannot send relay response: no adapter for platform %s", source.platform)
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(adapter.send(source.chat_id, text))
    except RuntimeError:
        _log.warning("cannot send relay response: no running event loop")
    except Exception:
        _log.warning("failed to schedule relay response send", exc_info=True)


def _send_chat_message_sync(kwargs, source, text):
    """Send a message back to the user from a worker thread."""
    gateway = kwargs.get("gateway")
    if not gateway or not source:
        _log.warning("cannot send relay response: missing gateway or source")
        return

    adapter = gateway.adapters.get(source.platform)
    if not adapter:
        _log.warning("cannot send relay response: no adapter for platform %s", source.platform)
        return

    try:
        asyncio.run(adapter.send(source.chat_id, text))
    except Exception:
        _log.warning("failed to send relay response", exc_info=True)


def _run_streamed_codex_turn(*, kwargs, source, state, prompt, message_id):
    """Run one Codex turn and stream normalized output in order."""
    streamed = False

    def emit(event_record):
        nonlocal streamed
        streamed = True
        for message in format_turn_event(event_record):
            _send_chat_message_sync(kwargs, source, message)

    try:
        turn_result = run_codex_turn(state, prompt, message_id=message_id, event_sink=emit)
        persist_session_turn(state, prompt, turn_result)
        if not streamed:
            for message in safe_format_turn_output(turn_result):
                _send_chat_message_sync(kwargs, source, message)
        if _is_active_state(kwargs, state):
            _send_chat_message_sync(kwargs, source, TURN_COMPLETE_MESSAGE)
    finally:
        state.turn_in_flight = False


def _is_active_state(kwargs, expected_state):
    event = kwargs.get("event")
    session_store = kwargs.get("session_store")
    source = getattr(event, "source", None)
    if session_store is None or source is None:
        return True
    try:
        session_entry = session_store.get_or_create_session(source)
    except Exception:
        return True
    session_id = getattr(session_entry, "session_id", None)
    if session_id is None:
        return True
    return get_active_relay(session_id) is expected_state


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
