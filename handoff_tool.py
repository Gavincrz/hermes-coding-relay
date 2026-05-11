"""Tool handler for entering coding mode."""

from __future__ import annotations

import json

try:
    from .output_formatter import safe_format_turn_output
    from .relay_delivery import has_delivery_context, resolve_source, stream_turn_sync
    from .relay_context import extract_message_id, extract_session_id, extract_session_key
    from .relay_runtime import (
        activate_relay,
        ensure_workdir_ready,
        persist_session_turn,
        run_codex_turn,
        validate_sandbox_mode,
        validate_workdir,
        validate_yolo,
    )
    from .session_store import find_session_record
except ImportError:  # pragma: no cover - direct import compatibility
    from output_formatter import safe_format_turn_output
    from relay_delivery import has_delivery_context, resolve_source, stream_turn_sync
    from relay_context import extract_message_id, extract_session_id, extract_session_key
    from relay_runtime import (
        activate_relay,
        ensure_workdir_ready,
        persist_session_turn,
        run_codex_turn,
        validate_sandbox_mode,
        validate_workdir,
        validate_yolo,
    )
    from session_store import find_session_record


def coding_relay(args, **kwargs):
    """Validate handoff arguments, enter coding mode, and start the first Codex turn."""
    agent = args.get("agent")
    prompt = args.get("prompt")
    workdir = args.get("workdir")
    codex_thread_id = args.get("codex_thread_id")
    sandbox_mode = args.get("sandbox_mode")
    yolo = args.get("yolo")
    session_id = extract_session_id(args) or extract_session_id(kwargs)
    session_key = extract_session_key(args) or extract_session_key(kwargs)
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

    if not isinstance(session_id, str) or not session_id.strip():
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_session_id",
                "message": "session_id is required to enter coding mode.",
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

    ensure_workdir_ready(resolved_workdir)

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
        session_id=session_id.strip(),
        workdir=resolved_workdir,
        codex_thread_id=codex_thread_id,
        session_key=session_key,
        sandbox_mode=resolved_sandbox_mode,
        yolo=yolo_enabled,
    )
    resume_notice = _build_resume_notice(codex_thread_id, resolved_workdir)

    source = resolve_source(kwargs)
    if has_delivery_context(kwargs, source):
        turn_result = stream_turn_sync(
            kwargs=kwargs,
            source=source,
            state=state,
            prompt=prompt,
            message_id=message_id,
            prelude_messages=[resume_notice] if resume_notice else None,
        )
        turn_messages: list[str] = []
    else:
        turn_result = run_codex_turn(state, prompt, message_id=message_id)
        turn_messages = safe_format_turn_output(turn_result)
        if resume_notice:
            turn_messages = [resume_notice, *turn_messages]
        persist_session_turn(state, prompt, turn_result)

    state.codex_thread_id = turn_result.codex_thread_id or state.codex_thread_id
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
            "message": "已进入 coding-relay 模式。",
        },
        ensure_ascii=False,
    )


coding_handoff = coding_relay


def _build_resume_notice(codex_thread_id: object, workdir: str) -> str:
    if not isinstance(codex_thread_id, str) or not codex_thread_id.strip():
        return ""

    record = find_session_record(codex_thread_id.strip())
    lines = ["**已恢复历史会话**", f"- thread: `{codex_thread_id.strip()}`", f"- workdir: `{workdir}`"]
    if record is None:
        return "\n".join(lines)

    last_active_at = record.get("last_active_at")
    if isinstance(last_active_at, str) and last_active_at.strip():
        lines.append(f"- 上次活跃：`{last_active_at.strip()}`")

    summary = record.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append(f"- 摘要：{summary.strip()}")

    last_files = record.get("last_files")
    if isinstance(last_files, list):
        normalized = [item for item in last_files if isinstance(item, str) and item.strip()]
        if normalized:
            lines.append("- 最近文件：" + ", ".join(f"`{item}`" for item in normalized))

    return "\n".join(lines)
