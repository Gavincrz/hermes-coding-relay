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
    from .relay_config import get_workdir_root
    from .session_store import upsert_session_record
except ImportError:  # pragma: no cover - direct import compatibility
    from agent_spawner import CodexSpawnError, DEFAULT_SANDBOX_MODE, VALID_SANDBOX_MODES, start_codex_process
    from event_adapter import adapt_stream_events
    from relay_config import get_workdir_root
    from session_store import upsert_session_record


RELAY_MODE_PRESETS = {
    "safe": {"sandbox_mode": DEFAULT_SANDBOX_MODE, "yolo": False},
    "readonly": {"sandbox_mode": "read-only", "yolo": False},
    "yolo": {"sandbox_mode": "danger-full-access", "yolo": True},
}


@dataclass
class ActiveRelayState:
    """In-memory coding-mode binding for one Hermes session."""

    session_id: str
    session_key: str | None
    agent: str
    codex_thread_id: str | None
    workdir: str
    sandbox_mode: str = DEFAULT_SANDBOX_MODE
    yolo: bool = False
    current_process: Any = None
    current_message_id: str | None = None
    turn_in_flight: bool = False


@dataclass(frozen=True)
class RelayTurnResult:
    """Result of one Codex turn execution."""

    codex_thread_id: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    agent_texts: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    command_runs: list[dict[str, Any]] = field(default_factory=list)
    file_changes: list[dict[str, Any]] = field(default_factory=list)


_ACTIVE_RELAYS: dict[str, ActiveRelayState] = {}


def validate_workdir(workdir: str) -> str:
    """Resolve and validate workdir against the allowed project root."""
    resolved = Path(workdir).expanduser().resolve()
    allowed_root = Path(get_workdir_root())
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"workdir must be inside {allowed_root}.") from exc
    if resolved == allowed_root:
        raise ValueError(f"workdir must be a subdirectory of {allowed_root}.")
    return str(resolved)


def ensure_workdir_ready(workdir: str) -> None:
    """Ensure the workdir exists and is a git repository."""
    path = Path(workdir)
    path.mkdir(parents=True, exist_ok=True)
    git_dir = path / ".git"
    if not git_dir.exists():
        import subprocess

        subprocess.run(
            ["git", "init"],
            cwd=str(path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )


def activate_relay(
    session_id: str,
    workdir: str,
    codex_thread_id: str | None = None,
    *,
    session_key: str | None = None,
    sandbox_mode: str = DEFAULT_SANDBOX_MODE,
    yolo: bool = False,
) -> ActiveRelayState:
    """Create or replace the active relay state for a Hermes session."""
    state = ActiveRelayState(
        session_id=session_id,
        session_key=session_key,
        agent="codex",
        codex_thread_id=codex_thread_id,
        workdir=workdir,
        sandbox_mode=sandbox_mode,
        yolo=yolo,
    )
    _ACTIVE_RELAYS[session_id] = state
    prune_stale_relays_for_session_key(session_key, keep_session_id=session_id)
    return state


def get_active_relay(session_id: str | None) -> ActiveRelayState | None:
    """Return the active relay state for a Hermes session if present."""
    if not session_id:
        return None
    return _ACTIVE_RELAYS.get(session_id)


def clear_active_relays() -> None:
    """Reset active relay state. Test-only helper."""
    _ACTIVE_RELAYS.clear()


def exit_coding_mode(session_id: str | None) -> bool:
    """Stop any active process and remove coding-mode state for the session."""
    if not session_id:
        return False
    state = _ACTIVE_RELAYS.pop(session_id, None)
    if state is None:
        return False
    _stop_process(state.current_process)
    return True


def prune_stale_relays_for_session_key(
    session_key: str | None,
    *,
    keep_session_id: str | None = None,
) -> int:
    """Remove stale relay states for the same Hermes session key."""
    if not isinstance(session_key, str) or not session_key:
        return 0

    removed = 0
    for session_id, state in list(_ACTIVE_RELAYS.items()):
        if state.session_key != session_key:
            continue
        if keep_session_id and session_id == keep_session_id:
            continue
        _ACTIVE_RELAYS.pop(session_id, None)
        _stop_process(state.current_process)
        removed += 1
    return removed


def set_relay_mode(session_id: str | None, mode: str) -> ActiveRelayState:
    """Update the execution mode for the active relay session."""
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id is required.")
    state = get_active_relay(session_id)
    if state is None:
        raise LookupError("current session is not in coding mode.")
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
    event_sink: Any | None = None,
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
    events: list[dict[str, Any]] = []
    agent_texts: list[str] = []
    errors: list[dict] = []
    command_runs: list[dict[str, Any]] = []
    file_changes: list[dict[str, Any]] = []
    try:
        for event in adapt_stream_events(codex_process.iter_events()):
            event_record = {"kind": event.kind, "payload": dict(event.payload)}
            events.append(event_record)
            if callable(event_sink):
                try:
                    event_sink(event_record)
                except Exception as exc:
                    errors.append(
                        {
                            "reason": "relay_output_failed",
                            "message": str(exc),
                        }
                    )
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
        events=events,
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
