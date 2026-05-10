# hermes-coding-relay

Hermes plugin for handing coding tasks off to external coding agents and relaying agent sessions through the gateway.

## Status

This repository is early-stage.

What exists today:

- Hermes directory plugin skeleton
- `coding_handoff` tool registration
- `pre_gateway_dispatch` hook registration
- `/back` command registration
- Codex CLI command construction and NDJSON event streaming foundation
- basic unit tests for registration and transport behavior

What does not exist yet:

- gateway coding-mode takeover
- session persistence
- output formatting
- multi-agent support

The current v1 implementation focus is a reliable Codex-first relay. Broader multi-agent support is a later direction, not current behavior.

## Goal

`coding-relay` lets Hermes detect a coding task, hand it off to a coding agent, and keep the follow-up conversation on the agent side instead of routing every message back through Hermes LLM.

The intended v1 flow is:

1. Hermes decides a request is a coding task.
2. Hermes calls `coding_handoff`.
3. The plugin starts or resumes a Codex CLI session.
4. Gateway messages are relayed to Codex while coding mode is active.
5. `/back` exits coding mode and returns control to Hermes.

## Current Scope

Current repository decisions are intentionally narrow:

- v1 supports `codex` only
- Hermes core is not modified
- runtime state must live under `run/`
- event parsing, session state, and output formatting stay separated

See [DESIGN.md](DESIGN.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/DECISIONS.md](docs/DECISIONS.md) for the repo-local source of truth.

## Installation Model

This project currently uses the Hermes directory plugin model rather than Python package entry points.

Expected layout:

```text
~/projects/hermes-coding-relay/         # development repo
~/.hermes/plugins/coding-relay          # symlink or clone target Hermes loads
```

Hermes discovers the plugin through:

- `plugin.yaml`
- `__init__.py`

This means `pip install .` is not the installation path for the current version.

## Repository Layout

```text
.
├── __init__.py
├── handoff_tool.py
├── gateway_hook.py
├── slash_commands.py
├── agent_spawner.py
├── plugin.yaml
├── AGENTS.md
├── DESIGN.md
├── docs/
└── tests/
```

Planned later modules include:

- `event_adapter.py`
- `output_formatter.py`
- `session_store.py`

## Development

Important repo rules live in [AGENTS.md](AGENTS.md).

Before changing code, read:

- [AGENTS.md](AGENTS.md)
- [DESIGN.md](DESIGN.md)
- [docs/TASKS.md](docs/TASKS.md)
- [docs/DECISIONS.md](docs/DECISIONS.md)

Python checks should use the Hermes venv:

```bash
/home/dontstarve/.hermes/hermes-agent/venv/bin/python -m unittest \
  tests.test_agent_spawner \
  tests.test_plugin_registration
```

## Roadmap

Near-term work is already tracked in [docs/TASKS.md](docs/TASKS.md):

- T003 internal event adapter
- T004 coding-mode gateway takeover
- T005 session persistence and summary extraction
- T006 output formatting and error experience

## Notes

The repo name is agent-agnostic on purpose, but the current implementation is not. If you are evaluating the project today, treat it as a Codex-first relay foundation rather than a finished multi-agent router.
