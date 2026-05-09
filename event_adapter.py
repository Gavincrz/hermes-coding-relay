"""Adapt Codex transport events into relay-internal events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

try:
    from .agent_spawner import StreamEvent
except ImportError:  # pragma: no cover - direct import compatibility
    from agent_spawner import StreamEvent


@dataclass(frozen=True)
class RelayEvent:
    """Represents one normalized relay event."""

    kind: str
    payload: dict


def adapt_stream_events(events: Iterable[StreamEvent]) -> Iterator[RelayEvent]:
    """Normalize an iterable of transport events."""
    for event in events:
        yield from adapt_stream_event(event)


def adapt_stream_event(event: StreamEvent) -> list[RelayEvent]:
    """Normalize one transport event into zero or more relay events."""
    if event.kind == "relay_error":
        return [RelayEvent(kind="relay_error", payload=dict(event.payload))]

    if event.kind != "raw_event":
        return []

    raw_event = event.payload
    event_type = _as_str(raw_event.get("type"))

    if event_type == "thread.started":
        thread_id = _as_str(raw_event.get("thread_id"))
        if not thread_id:
            return []
        return [RelayEvent(kind="session_init", payload={"codex_thread_id": thread_id})]

    if event_type in {"item.started", "item.completed"}:
        item = raw_event.get("item")
        if not isinstance(item, dict):
            return []
        return _adapt_item_event(item=item, phase=event_type.removeprefix("item."))

    if event_type == "error":
        return [
            RelayEvent(
                kind="relay_error",
                payload={
                    "reason": "codex_error",
                    "message": _as_str(raw_event.get("message")) or "Codex reported an error.",
                },
            )
        ]

    if event_type == "turn.completed":
        usage = raw_event.get("usage")
        return [
            RelayEvent(
                kind="turn_completed",
                payload={"usage": usage if isinstance(usage, dict) else {}},
            )
        ]

    return []


def _adapt_item_event(item: dict, phase: str) -> list[RelayEvent]:
    item_id = _as_str(item.get("id"))
    item_type = _as_str(item.get("type"))

    if item_type == "agent_message" and phase == "completed":
        text = _as_str(item.get("text"))
        if not text:
            return []
        return [RelayEvent(kind="agent_text", payload={"item_id": item_id, "text": text})]

    if item_type == "command_execution":
        kind = "command_started" if phase == "started" else "command_finished"
        return [
            RelayEvent(
                kind=kind,
                payload={
                    "item_id": item_id,
                    "command": _as_str(item.get("command")),
                    "output": _as_str(item.get("aggregated_output")),
                    "exit_code": item.get("exit_code"),
                    "status": _as_str(item.get("status")),
                },
            )
        ]

    if item_type == "file_change":
        return [
            RelayEvent(
                kind="file_change",
                payload={
                    "item_id": item_id,
                    "phase": phase,
                    "status": _as_str(item.get("status")),
                    "path": _as_str(item.get("path")),
                    "changes": item.get("changes") if isinstance(item.get("changes"), list) else [],
                },
            )
        ]

    if item_type == "error":
        return [
            RelayEvent(
                kind="relay_error",
                payload={
                    "reason": "codex_item_error",
                    "message": _as_str(item.get("message")) or "Codex reported an item error.",
                    "item_id": item_id,
                },
            )
        ]

    return []


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""
