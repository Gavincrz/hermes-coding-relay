"""Coding Relay Hermes plugin entrypoint."""

try:
    from .relay_config import build_tool_description, build_workdir_description, _load_config
    from .gateway_hook import pre_gateway_dispatch
    from .handoff_tool import coding_relay
    from .slash_commands import handle_relay_back_command, handle_relay_mode_command
except ImportError:  # pragma: no cover - direct import compatibility
    from relay_config import build_tool_description, build_workdir_description, _load_config
    from gateway_hook import pre_gateway_dispatch
    from handoff_tool import coding_relay
    from slash_commands import handle_relay_back_command, handle_relay_mode_command


def build_tool_schema(config=None):
    """Build the tool schema with config-derived descriptions."""
    return {
        "name": "coding_relay",
        "description": build_tool_description(config),
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Coding agent to use. v1 only supports 'codex'.",
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "Self-contained task description for Codex. Include the user's intent, "
                        "relevant context (file paths, code structure, constraints), and specific instructions. "
                        "Do not include Hermes internal state."
                    ),
                },
                "workdir": {
                    "type": "string",
                    "description": build_workdir_description(config),
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
    config = _load_config()
    ctx.register_tool(
        name="coding_relay",
        toolset="plugin_coding_relay",
        schema=build_tool_schema(config),
        handler=coding_relay,
        description=build_tool_description(config),
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
