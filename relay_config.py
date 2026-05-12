"""Plugin-local configuration helpers for coding-relay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_WORKDIR_ROOT = "~/projects"
DEFAULT_COMMAND_VISIBILITY = "none"
VALID_COMMAND_VISIBILITY = {"none", "filtered", "all"}
PLUGIN_CONFIG_NAME = "coding-relay"

try:
    from hermes_cli.config import cfg_get, load_config
except ImportError:  # pragma: no cover - direct import compatibility
    cfg_get = None
    load_config = None


def get_workdir_root(config: dict[str, Any] | None = None) -> str:
    """Return the configured root directory for relay workdirs."""
    raw_root = _resolve_raw_workdir_root(config)
    return str(Path(raw_root).expanduser().resolve())


def get_command_visibility(config: dict[str, Any] | None = None) -> str:
    """Return the configured command visibility mode for relay output."""
    raw_visibility = _resolve_raw_command_visibility(config)
    normalized = raw_visibility.strip().lower()
    if normalized in VALID_COMMAND_VISIBILITY:
        return normalized
    return DEFAULT_COMMAND_VISIBILITY


def build_workdir_description(config: dict[str, Any] | None = None) -> str:
    """Build a workdir schema description from the configured root."""
    workdir_root = get_workdir_root(config)
    return (
        "Absolute path of the project working directory. "
        f"Must be a subdirectory under {workdir_root}, not {workdir_root} itself."
    )


def build_tool_description(config: dict[str, Any] | None = None) -> str:
    """Build a tool description that reflects the current relay config."""
    workdir_root = get_workdir_root(config)
    return (
        "Delegate a coding task to Codex CLI. "
        "You MUST call this tool for ANY task that involves creating, editing, or deleting files, "
        "writing or modifying code, or running shell commands in a project directory. "
        "Do NOT use write_file, run_command, edit_file, or other built-in tools for these tasks. "
        "The configured relay workdir root is "
        f"{workdir_root}; pass a subdirectory under that root, not the root itself. "
        "Load the 'coding-relay' skill for detailed delegation rules and examples."
    )


def _resolve_raw_workdir_root(config: dict[str, Any] | None = None) -> str:
    if config is None:
        config = _load_config()

    default_root = DEFAULT_WORKDIR_ROOT
    if cfg_get is None:
        if isinstance(config, dict):
            plugins_cfg = config.get("plugins")
            if isinstance(plugins_cfg, dict):
                relay_cfg = plugins_cfg.get(PLUGIN_CONFIG_NAME)
                if isinstance(relay_cfg, dict):
                    value = relay_cfg.get("workdir_root")
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return default_root

    value = cfg_get(config, "plugins", PLUGIN_CONFIG_NAME, "workdir_root", default=default_root)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default_root


def _resolve_raw_command_visibility(config: dict[str, Any] | None = None) -> str:
    if config is None:
        config = _load_config()

    default_visibility = DEFAULT_COMMAND_VISIBILITY
    if cfg_get is None:
        if isinstance(config, dict):
            plugins_cfg = config.get("plugins")
            if isinstance(plugins_cfg, dict):
                relay_cfg = plugins_cfg.get(PLUGIN_CONFIG_NAME)
                if isinstance(relay_cfg, dict):
                    value = relay_cfg.get("command_visibility")
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return default_visibility

    value = cfg_get(config, "plugins", PLUGIN_CONFIG_NAME, "command_visibility", default=default_visibility)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default_visibility


def _load_config() -> dict[str, Any]:
    if load_config is None:
        return {}
    try:
        config = load_config()
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}
