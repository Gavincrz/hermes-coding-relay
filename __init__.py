"""Coding Relay Hermes plugin entrypoint."""

try:
    from .gateway_hook import pre_gateway_dispatch
    from .handoff_tool import coding_handoff
    from .slash_commands import handle_relay_back_command, handle_relay_mode_command
except ImportError:  # pragma: no cover - direct import compatibility
    from gateway_hook import pre_gateway_dispatch
    from handoff_tool import coding_handoff
    from slash_commands import handle_relay_back_command, handle_relay_mode_command


TOOL_SCHEMA = {
    "name": "coding_handoff",
    "description": "Hand off a coding task from Hermes to the Codex relay plugin.",
    "parameters": {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Coding agent to use. v1 only supports 'codex'.",
            },
            "prompt": {
                "type": "string",
                "description": "Initial task prompt passed to the coding agent.",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory for the coding task.",
            },
            "codex_thread_id": {
                "type": "string",
                "description": "Existing Codex thread id to resume.",
            },
            "sandbox_mode": {
                "type": "string",
                "enum": ["read-only", "workspace-write", "danger-full-access"],
                "description": "Codex sandbox mode. Defaults to 'workspace-write'.",
            },
            "yolo": {
                "type": "boolean",
                "description": "When true, bypass Codex approvals and sandbox entirely.",
            },
        },
        "required": ["agent", "prompt", "workdir"],
        "additionalProperties": False,
    },
}


def register(ctx):
    """Register the plugin tool, hook, and slash command."""
    ctx.register_tool(
        name="coding_handoff",
        toolset="plugin_coding_relay",
        schema=TOOL_SCHEMA,
        handler=coding_handoff,
        description="Hand off a coding task to Codex via the coding-relay plugin.",
    )
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)
    ctx.register_command(
        "relay-back",
        handler=handle_relay_back_command,
        description="Exit coding mode and return control to Hermes.",
    )
    ctx.register_command(
        "relay-mode",
        handler=handle_relay_mode_command,
        description="Show or switch the current relay execution mode.",
        args_hint="[status|safe|readonly|yolo]",
    )
