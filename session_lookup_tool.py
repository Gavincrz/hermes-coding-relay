"""Tool handler for querying persisted relay sessions without entering coding mode."""

from __future__ import annotations

import json

try:
    from .relay_runtime import validate_workdir
    from .session_store import list_session_records
except ImportError:  # pragma: no cover - direct import compatibility
    from relay_runtime import validate_workdir
    from session_store import list_session_records


def list_relay_sessions(args, **_kwargs):
    """Return persisted relay session candidates for one project workdir."""
    workdir = args.get("workdir")
    provider = args.get("provider")
    limit = args.get("limit", 5)

    if not isinstance(workdir, str) or not workdir.strip():
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_workdir",
                "message": "workdir must be a non-empty string.",
            },
            ensure_ascii=False,
        )

    if provider is not None and provider != "codex":
        return json.dumps(
            {
                "status": "rejected",
                "reason": "unsupported_provider",
                "message": "coding-relay v1 only supports provider='codex'.",
            },
            ensure_ascii=False,
        )

    if not isinstance(limit, int):
        return json.dumps(
            {
                "status": "rejected",
                "reason": "invalid_limit",
                "message": "limit must be an integer.",
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

    sessions = list_session_records(workdir=resolved_workdir, provider=provider, limit=limit)
    candidates = [_to_candidate(record) for record in sessions]
    return json.dumps(
        {
            "status": "ok",
            "provider": "codex",
            "workdir": resolved_workdir,
            "count": len(candidates),
            "sessions": candidates,
            "message": "已返回历史 relay 会话候选。",
        },
        ensure_ascii=False,
    )


def _to_candidate(record: dict) -> dict:
    return {
        "provider": record.get("provider", "codex"),
        "resume_token": record.get("resume_token"),
        "workdir": record.get("workdir"),
        "last_active_at": record.get("last_active_at"),
        "summary": record.get("summary"),
        "last_files": record.get("last_files") if isinstance(record.get("last_files"), list) else [],
    }
