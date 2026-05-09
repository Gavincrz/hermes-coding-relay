"""Runtime relay state and Codex turn orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from .agent_spawner import CodexSpawnError, start_codex_process
    from .event_adapter import adapt_stream_events
except ImportError:  # pragma: no cover - direct import compatibility
    from agent_spawner import CodexSpawnError, start_codex_process
    from event_adapter import adapt_stream_events


ALLOWED_WORKDIR_ROOT = Path("~/projects").expanduser().resolve()


@dataclass
class ActiveRelayState:
    """In-memory coding-mode binding for one chat."""

    chat_id: str
    agent: str
    codex_thread_id: str | None
    workdir: str
    current_process: Any = None
    current_message_id: str | None = None


@dataclass(frozen=True)
class RelayTurnResult:
    """Result of one Codex turn execution."""

    codex_thread_id: str | None
    agent_texts: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


_ACTIVE_RELAYS: dict[str, ActiveRelayState] = {}


def validate_workdir(workdir: str) -> str:
    """Resolve and validate workdir against the allowed project root."""
    resolved = Path(workdir).expanduser().resolve()
    try:
        resolved.relative_to(ALLOWED_WORKDIR_ROOT)
    except ValueError as exc:
        raise ValueError(f"workdir must be inside {ALLOWED_WORKDIR_ROOT}.") from exc
    return str(resolved)


def activate_relay(chat_id: str, workdir: str, codex_thread_id: str | None = None) -> ActiveRelayState:
    """Create or replace the active relay state for a chat."""
    state = ActiveRelayState(
        chat_id=chat_id,
        agent="codex",
        codex_thread_id=codex_thread_id,
        workdir=workdir,
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
    try:
        for event in adapt_stream_events(codex_process.iter_events()):
            if event.kind == "session_init":
                state.codex_thread_id = event.payload.get("codex_thread_id") or state.codex_thread_id
            elif event.kind == "agent_text":
                text = event.payload.get("text")
                if isinstance(text, str) and text:
                    agent_texts.append(text)
            elif event.kind == "relay_error":
                errors.append(dict(event.payload))
    finally:
        state.current_process = None

    return RelayTurnResult(
        codex_thread_id=state.codex_thread_id,
        agent_texts=agent_texts,
        errors=errors,
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
