"""Shared delivery helpers for relay output streaming."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

try:
    from .output_formatter import format_turn_event, safe_format_turn_output
    from .relay_config import get_command_visibility
    from .relay_runtime import get_active_relay, persist_session_turn, run_codex_turn
except ImportError:  # pragma: no cover - direct import compatibility
    from output_formatter import format_turn_event, safe_format_turn_output
    from relay_config import get_command_visibility
    from relay_runtime import get_active_relay, persist_session_turn, run_codex_turn


_log = logging.getLogger("coding-relay.delivery")
TURN_COMPLETE_MESSAGE = "**本轮完成**"


def resolve_source(kwargs: dict[str, Any]) -> Any:
    event = kwargs.get("event")
    if event is not None:
        source = getattr(event, "source", None)
        if source is not None:
            return source
    return kwargs.get("source")


def has_delivery_context(kwargs: dict[str, Any], source: Any | None = None) -> bool:
    gateway = kwargs.get("gateway")
    resolved_source = source if source is not None else resolve_source(kwargs)
    if not gateway or resolved_source is None:
        return False
    platform_key = _platform_key(getattr(resolved_source, "platform", None))
    if platform_key is None:
        return False
    return gateway.adapters.get(platform_key) is not None


def send_chat_message(kwargs: dict[str, Any], source: Any, text: str) -> None:
    """Send a relay response back to the user via the platform adapter."""
    gateway = kwargs.get("gateway")
    if not gateway or not source:
        _log.warning("cannot send relay response: missing gateway or source")
        return

    raw_platform = getattr(source, "platform", None)
    platform_key = _platform_key(raw_platform)
    platform_label = _platform_label(raw_platform)
    adapter = gateway.adapters.get(platform_key) if platform_key is not None else None
    if not adapter:
        _log.warning("cannot send relay response: no adapter for platform %s", platform_label)
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(adapter.send(source.chat_id, text))
    except RuntimeError:
        _log.warning("cannot send relay response: no running event loop")
    except Exception:
        _log.warning("failed to schedule relay response send", exc_info=True)


def send_chat_message_sync(kwargs: dict[str, Any], source: Any, text: str) -> None:
    """Send a relay response from a worker or tool thread and wait for completion."""
    gateway = kwargs.get("gateway")
    if not gateway or not source:
        _log.warning("cannot send relay response: missing gateway or source")
        return

    raw_platform = getattr(source, "platform", None)
    platform_key = _platform_key(raw_platform)
    platform_label = _platform_label(raw_platform)
    adapter = gateway.adapters.get(platform_key) if platform_key is not None else None
    if not adapter:
        _log.warning("cannot send relay response: no adapter for platform %s", platform_label)
        return

    try:
        asyncio.run(adapter.send(source.chat_id, text))
    except Exception:
        _log.warning("failed to send relay response", exc_info=True)


def stream_turn_sync(
    *,
    kwargs: dict[str, Any],
    source: Any,
    state: Any,
    prompt: str,
    message_id: str | None,
    prelude_messages: list[str] | None = None,
) -> Any:
    """Run one turn and deliver normalized output in order."""
    streamed = False
    resolved_command_visibility = get_command_visibility()

    def emit(event_record: dict[str, Any]) -> None:
        nonlocal streamed
        streamed = True
        for message in format_turn_event(event_record, command_visibility=resolved_command_visibility):
            send_chat_message_sync(kwargs, source, message)

    try:
        for message in prelude_messages or []:
            if isinstance(message, str) and message:
                send_chat_message_sync(kwargs, source, message)
        turn_result = run_codex_turn(state, prompt, message_id=message_id, event_sink=emit)
        persist_session_turn(state, prompt, turn_result)
        if not streamed:
            for message in safe_format_turn_output(turn_result, command_visibility=resolved_command_visibility):
                send_chat_message_sync(kwargs, source, message)
        if _is_active_state(kwargs, state):
            send_chat_message_sync(kwargs, source, TURN_COMPLETE_MESSAGE)
        return turn_result
    finally:
        state.turn_in_flight = False


def start_streaming_turn(*, kwargs: dict[str, Any], source: Any, state: Any, prompt: str, message_id: str | None) -> None:
    """Start one streamed turn in a daemon thread."""
    state.turn_in_flight = True
    worker = threading.Thread(
        target=stream_turn_sync,
        kwargs={
            "kwargs": kwargs,
            "source": source,
            "state": state,
            "prompt": prompt,
            "message_id": message_id,
        },
        daemon=True,
    )
    worker.start()


def _is_active_state(kwargs: dict[str, Any], expected_state: Any) -> bool:
    event = kwargs.get("event")
    session_store = kwargs.get("session_store")
    source = getattr(event, "source", None) if event is not None else kwargs.get("source")
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


def _platform_key(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized or None
    return value


def _platform_label(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized or None

    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        normalized = enum_value.strip().lower()
        return normalized or None

    return None
