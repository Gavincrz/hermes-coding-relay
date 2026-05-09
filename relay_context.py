"""Helpers for extracting Hermes gateway context from dicts or event objects."""

from __future__ import annotations

import os
from typing import Any


def extract_chat_id(payload: Any) -> str | None:
    """Return a chat id from plugin kwargs or a Hermes MessageEvent-like object."""
    return _extract_string_field(payload, "chat_id")


def extract_message_id(payload: Any) -> str | None:
    """Return a message id from plugin kwargs or a Hermes MessageEvent-like object."""
    return _extract_string_field(payload, "message_id")


def extract_text(payload: Any) -> str:
    """Return the first available text-like field from kwargs or an event object."""
    for key in ("text", "message", "content", "raw_text"):
        value = _lookup_value(payload, key)
        if isinstance(value, str):
            return value
    return ""


def extract_session_id(payload: Any) -> str | None:
    """Return a Hermes session id from kwargs or tool dispatch context."""
    session_id = _extract_string_field(payload, "session_id")
    if session_id:
        return session_id
    task_id = _extract_string_field(payload, "task_id")
    if task_id:
        return task_id
    return None


def extract_session_key(payload: Any) -> str | None:
    """Return the current Hermes session key from kwargs or environment."""
    session_key = _extract_string_field(payload, "session_key")
    if session_key:
        return session_key

    env_value = os.getenv("HERMES_SESSION_KEY", "").strip()
    if env_value:
        return env_value
    return None


def _extract_string_field(payload: Any, field_name: str) -> str | None:
    value = _lookup_value(payload, field_name)
    if isinstance(value, str) and value:
        return value
    return None


def _lookup_value(payload: Any, field_name: str) -> Any:
    if isinstance(payload, dict):
        direct = payload.get(field_name)
        if direct is not None:
            return direct

        event = payload.get("event")
        event_value = _lookup_event_value(event, field_name)
        if event_value is not None:
            return event_value

    return _lookup_event_value(payload, field_name)


def _lookup_event_value(event: Any, field_name: str) -> Any:
    if event is None:
        return None

    if isinstance(event, dict):
        direct = event.get(field_name)
        if direct is not None:
            return direct

        source = event.get("source")
        source_value = _lookup_source_value(source, field_name)
        if source_value is not None:
            return source_value
        return None

    direct = getattr(event, field_name, None)
    if direct is not None:
        return direct

    source = getattr(event, "source", None)
    source_value = _lookup_source_value(source, field_name)
    if source_value is not None:
        return source_value

    return None


def _lookup_source_value(source: Any, field_name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(field_name)
    return getattr(source, field_name, None)
