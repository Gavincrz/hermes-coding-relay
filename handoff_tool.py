"""Tool handler for entering coding mode."""

from __future__ import annotations

import json

try:
    from .relay_runtime import activate_relay, run_codex_turn, validate_workdir
except ImportError:  # pragma: no cover - direct import compatibility
    from relay_runtime import activate_relay, run_codex_turn, validate_workdir


def coding_handoff(args, **kwargs):
    """Validate handoff arguments, enter coding mode, and start the first Codex turn."""
    agent = args.get("agent")
    prompt = args.get("prompt")
    workdir = args.get("workdir")
    codex_thread_id = args.get("codex_thread_id")
    chat_id = _extract_chat_id(args, kwargs)
    message_id = _extract_message_id(args, kwargs)

    if agent != "codex":
        return json.dumps(
            {
                "status": "rejected",
                "reason": "unsupported_agent",
                "message": "coding-relay v1 only supports agent='codex'.",
            },
            ensure_ascii=False,
        )

    if not isinstance(prompt, str) or not prompt.strip():
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_prompt",
                "message": "prompt must be a non-empty string.",
            },
            ensure_ascii=False,
        )

    if not isinstance(workdir, str) or not workdir.strip():
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_workdir",
                "message": "workdir must be a non-empty string.",
            },
            ensure_ascii=False,
        )

    if not isinstance(chat_id, str) or not chat_id.strip():
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_chat_id",
                "message": "chat_id is required to enter coding mode.",
            },
            ensure_ascii=False,
        )

    try:
        resolved_workdir = validate_workdir(workdir)
    except ValueError as exc:
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_workdir",
                "message": str(exc),
            },
            ensure_ascii=False,
        )

    state = activate_relay(chat_id=chat_id.strip(), workdir=resolved_workdir, codex_thread_id=codex_thread_id)
    turn_result = run_codex_turn(state, prompt, message_id=message_id)
    state.codex_thread_id = turn_result.codex_thread_id or state.codex_thread_id
    if turn_result.errors:
        return json.dumps(
            {
                "status": "error",
                "agent": "codex",
                "workdir": resolved_workdir,
                "codex_thread_id": turn_result.codex_thread_id,
                "errors": turn_result.errors,
                "message": "Failed to start Codex coding mode.",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "status": "handed_off",
            "agent": "codex",
            "workdir": resolved_workdir,
            "codex_thread_id": turn_result.codex_thread_id,
            "initial_messages": turn_result.agent_texts,
            "message": "已转接到 codex。后续消息直接发给它，发送 /back 回来找 Hermes。",
        },
        ensure_ascii=False,
    )


def _extract_chat_id(args, kwargs) -> str | None:
    if isinstance(args.get("chat_id"), str):
        return args["chat_id"]
    if isinstance(kwargs.get("chat_id"), str):
        return kwargs["chat_id"]
    event = kwargs.get("event")
    if isinstance(event, dict) and isinstance(event.get("chat_id"), str):
        return event["chat_id"]
    return None


def _extract_message_id(args, kwargs) -> str | None:
    if isinstance(args.get("message_id"), str):
        return args["message_id"]
    if isinstance(kwargs.get("message_id"), str):
        return kwargs["message_id"]
    event = kwargs.get("event")
    if isinstance(event, dict) and isinstance(event.get("message_id"), str):
        return event["message_id"]
    return None
