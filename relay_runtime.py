"""Runtime relay state, turn orchestration, and session persistence hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from .agent_spawner import (
        CodexSpawnError,
        DEFAULT_SANDBOX_MODE,
        VALID_SANDBOX_MODES,
        start_codex_process,
    )
    from .event_adapter import adapt_stream_events
    from .session_store import upsert_session_record
except ImportError:  # pragma: no cover - direct import compatibility
    from agent_spawner import CodexSpawnError, DEFAULT_SANDBOX_MODE, VALID_SANDBOX_MODES, start_codex_process
    from event_adapter import adapt_stream_events
    from session_store import upsert_session_record


ALLOWED_WORKDIR_ROOT = Path("~/projects").expanduser().resolve()
RELAY_MODE_PRESETS = {
    "safe": {"sandbox_mode": DEFAULT_SANDBOX_MODE, "yolo": False},
    "readonly": {"sandbox_mode": "read-only", "yolo": False},
    "yolo": {"sandbox_mode": "danger-full-access", "yolo": True},
}


@dataclass
class ActiveRelayState:
    """In-memory coding-mode binding for one chat."""

    chat_id: str
    agent: str
    codex_thread_id: str | None
    workdir: str
    sandbox_mode: str = DEFAULT_SANDBOX_MODE
    yolo: bool = False
    current_process: Any = None
    current_message_id: str | None = None


@dataclass(frozen=True)
class RelayTurnResult:
    """Result of one Codex turn execution."""

    codex_thread_id: str | None
    agent_texts: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    command_runs: list[dict[str, Any]] = field(default_factory=list)
    file_changes: list[dict[str, Any]] = field(default_factory=list)


_ACTIVE_RELAYS: dict[str, ActiveRelayState] = {}


def validate_workdir(workdir: str) -> str:
    """Resolve and validate workdir against the allowed project root."""
    resolved = Path(workdir).expanduser().resolve()
    try:
        resolved.relative_to(ALLOWED_WORKDIR_ROOT)
    except ValueError as exc:
        raise ValueError(f"workdir must be inside {ALLOWED_WORKDIR_ROOT}.") from exc
    return str(resolved)


def activate_relay(
    chat_id: str,
    workdir: str,
    codex_thread_id: str | None = None,
    *,
    sandbox_mode: str = DEFAULT_SANDBOX_MODE,
    yolo: bool = False,
) -> ActiveRelayState:
    """Create or replace the active relay state for a chat."""
    state = ActiveRelayState(
        chat_id=chat_id,
        agent="codex",
        codex_thread_id=codex_thread_id,
        workdir=workdir,
        sandbox_mode=sandbox_mode,
        yolo=yolo,
    )
    _ACTIVE_RELAYS[chat_id] = state
    return state


def get_active_relay(chat_id: str | None) -> ActiveRelayState | None:
    """Return the active relay state for a chat if present."""
    if not chat_id:
        return None
    return _ACTIVE_RELAYS.get(chat_id)


def clear_active_relays() -> None:
    """Reset active relay state. Test-only helper."""
    _ACTIVE_RELAYS.clear()


def exit_coding_mode(chat_id: str | None) -> bool:
    """Stop any active process and remove coding-mode state for the chat."""
    if not chat_id:
        return False
    state = _ACTIVE_RELAYS.pop(chat_id, None)
    if state is None:
        return False
    _stop_process(state.current_process)
    return True


def set_relay_mode(chat_id: str | None, mode: str) -> ActiveRelayState:
    """Update the execution mode for the active relay session."""
    if not isinstance(chat_id, str) or not chat_id:
        raise ValueError("chat_id is required.")
    state = get_active_relay(chat_id)
    if state is None:
        raise LookupError("current chat is not in coding mode.")
    if not isinstance(mode, str):
        raise ValueError("mode must be a string.")

    normalized = mode.strip().lower()
    preset = RELAY_MODE_PRESETS.get(normalized)
    if preset is None:
        raise ValueError("mode must be one of: readonly, safe, yolo.")

    state.sandbox_mode = preset["sandbox_mode"]
    state.yolo = preset["yolo"]
    return state


def run_codex_turn(
    state: ActiveRelayState,
    prompt: str,
    *,
    message_id: str | None = None,
    process_starter=start_codex_process,
) -> RelayTurnResult:
    """Execute one Codex turn for the active chat state."""
    state.current_message_id = message_id
    try:
        codex_process = process_starter(
            prompt=prompt,
            workdir=state.workdir,
            codex_thread_id=state.codex_thread_id,
            sandbox_mode=state.sandbox_mode,
            yolo=state.yolo,
        )
    except CodexSpawnError as exc:
        state.current_process = None
        return RelayTurnResult(
            codex_thread_id=state.codex_thread_id,
            errors=[{"reason": "spawn_failed", "message": str(exc)}],
        )

    state.current_process = codex_process.process
    agent_texts: list[str] = []
    errors: list[dict] = []
    command_runs: list[dict[str, Any]] = []
    file_changes: list[dict[str, Any]] = []
    try:
        for event in adapt_stream_events(codex_process.iter_events()):
            if event.kind == "session_init":
                state.codex_thread_id = event.payload.get("codex_thread_id") or state.codex_thread_id
            elif event.kind == "agent_text":
                text = event.payload.get("text")
                if isinstance(text, str) and text:
                    agent_texts.append(text)
            elif event.kind in {"command_started", "command_finished"}:
                payload = dict(event.payload)
                payload["event_kind"] = event.kind
                command_runs.append(payload)
            elif event.kind == "file_change":
                payload = dict(event.payload)
                payload["event_kind"] = event.kind
                file_changes.append(payload)
            elif event.kind == "relay_error":
                errors.append(dict(event.payload))
    finally:
        state.current_process = None

    return RelayTurnResult(
        codex_thread_id=state.codex_thread_id,
        agent_texts=agent_texts,
        errors=errors,
        command_runs=command_runs,
        file_changes=file_changes,
    )


def persist_session_turn(state: ActiveRelayState, prompt: str, turn_result: Any) -> None:
    """Persist a completed turn into run/sessions.json when a thread id exists."""
    codex_thread_id = getattr(turn_result, "codex_thread_id", None) or state.codex_thread_id
    if not isinstance(codex_thread_id, str) or not codex_thread_id:
        return

    upsert_session_record(
        codex_thread_id=codex_thread_id,
        agent=state.agent,
        workdir=state.workdir,
        prompt=prompt,
        agent_texts=_as_str_list(getattr(turn_result, "agent_texts", [])),
        command_runs=_as_dict_list(getattr(turn_result, "command_runs", [])),
        file_changes=_as_dict_list(getattr(turn_result, "file_changes", [])),
    )


def _stop_process(process: Any) -> None:
    if process is None:
        return
    poll = getattr(process, "poll", None)
    if callable(poll) and poll() is not None:
        return

    terminate = getattr(process, "terminate", None)
    if callable(terminate):
        terminate()

    wait = getattr(process, "wait", None)
    if callable(wait):
        try:
            wait(timeout=1)
            return
        except TypeError:
            wait()
            return
        except Exception:
            pass

    kill = getattr(process, "kill", None)
    if callable(kill):
        kill()


def _as_str_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value]


def _as_dict_list(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return [dict(value) for value in values if isinstance(value, dict)]


def validate_sandbox_mode(sandbox_mode: str | None) -> str:
    """Validate the requested Codex sandbox mode."""
    if sandbox_mode is None:
        return DEFAULT_SANDBOX_MODE
    if not isinstance(sandbox_mode, str):
        raise ValueError("sandbox_mode must be a string.")
    normalized = sandbox_mode.strip()
    if normalized not in VALID_SANDBOX_MODES:
        raise ValueError(
            "sandbox_mode must be one of: " + ", ".join(sorted(VALID_SANDBOX_MODES)) + "."
        )
    return normalized


def validate_yolo(yolo: Any) -> bool:
    """Validate the optional yolo flag."""
    if yolo is None:
        return False
    if isinstance(yolo, bool):
        return yolo
    raise ValueError("yolo must be a boolean.")
