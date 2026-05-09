"""Tool handler for entering coding mode."""

from __future__ import annotations

import json

try:
    from .output_formatter import safe_format_turn_output
    from .relay_context import extract_chat_id, extract_message_id
    from .relay_runtime import (
        activate_relay,
        persist_session_turn,
        run_codex_turn,
        validate_sandbox_mode,
        validate_workdir,
        validate_yolo,
    )
except ImportError:  # pragma: no cover - direct import compatibility
    from output_formatter import safe_format_turn_output
    from relay_context import extract_chat_id, extract_message_id
    from relay_runtime import (
        activate_relay,
        persist_session_turn,
        run_codex_turn,
        validate_sandbox_mode,
        validate_workdir,
        validate_yolo,
    )


def coding_handoff(args, **kwargs):
    """Validate handoff arguments, enter coding mode, and start the first Codex turn."""
    agent = args.get("agent")
    prompt = args.get("prompt")
    workdir = args.get("workdir")
    codex_thread_id = args.get("codex_thread_id")
    sandbox_mode = args.get("sandbox_mode")
    yolo = args.get("yolo")
    chat_id = extract_chat_id(args) or extract_chat_id(kwargs)
    message_id = extract_message_id(args) or extract_message_id(kwargs)

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

    try:
        resolved_sandbox_mode = validate_sandbox_mode(sandbox_mode)
        yolo_enabled = validate_yolo(yolo)
    except ValueError as exc:
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_execution_mode",
                "message": str(exc),
            },
            ensure_ascii=False,
        )

    state = activate_relay(
        chat_id=chat_id.strip(),
        workdir=resolved_workdir,
        codex_thread_id=codex_thread_id,
        sandbox_mode=resolved_sandbox_mode,
        yolo=yolo_enabled,
    )
    turn_result = run_codex_turn(state, prompt, message_id=message_id)
    state.codex_thread_id = turn_result.codex_thread_id or state.codex_thread_id
    turn_messages = safe_format_turn_output(turn_result)
    persist_session_turn(state, prompt, turn_result)
    if turn_result.errors:
        return json.dumps(
            {
                "status": "error",
                "agent": "codex",
                "workdir": resolved_workdir,
                "codex_thread_id": turn_result.codex_thread_id,
                "messages": turn_messages,
                "errors": turn_result.errors,
                "message": "Codex coding mode 启动失败。",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "status": "handed_off",
            "agent": "codex",
            "workdir": resolved_workdir,
            "codex_thread_id": turn_result.codex_thread_id,
            "sandbox_mode": resolved_sandbox_mode,
            "yolo": yolo_enabled,
            "initial_messages": turn_messages,
            "message": "已转接到 codex。后续消息直接发给它，发送 /relay-back 回来找 Hermes。",
        },
        ensure_ascii=False,
    )
