"""Tool handler for entering coding mode."""

import json


def coding_handoff(args, **_kwargs):
    """Return a deterministic placeholder until the Codex transport exists."""
    agent = args.get("agent")
    prompt = args.get("prompt")
    workdir = args.get("workdir")
    codex_thread_id = args.get("codex_thread_id")

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

    return json.dumps(
        {
            "status": "not_implemented",
            "agent": "codex",
            "workdir": workdir,
            "codex_thread_id": codex_thread_id,
            "message": "coding-relay skeleton is loaded. Codex handoff transport will be implemented in T002-T004.",
        },
        ensure_ascii=False,
    )
