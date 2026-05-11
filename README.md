# hermes-coding-relay

Hermes directory plugin for handing coding tasks off to Codex CLI and relaying the follow-up conversation through Hermes gateway hooks.

## Status

This repository is functional, but still intentionally narrow in scope.

What exists today:

- `coding_relay` tool registration
- `pre_gateway_dispatch` hook takeover for coding mode
- Codex CLI spawn and resume via `codex_thread_id`
- event adaptation and ordered relay output delivery
- session persistence under `run/`
- relay control commands: `/relay-back` and `/relay-mode`
- unit tests for registration, transport, runtime, formatting, persistence, and relay takeover

Current implementation focus:

- Codex-first relay only
- no Hermes core changes
- reliable relay behavior over broad multi-agent abstraction

## Supported / Validated Platforms

Gateway delivery is implemented through Hermes platform adapters, so the code path is not hard-coded to Feishu.

Current validation status is narrower:

- real end-to-end gateway validation has only been done on Feishu
- output formatting is currently optimized for Feishu's lightweight Markdown behavior
- other gateway platforms are not yet claimed as supported until they are tested explicitly

If another platform exposes a compatible Hermes adapter, the relay code may work there, but that is not yet a documented compatibility guarantee.

## Goal

`coding-relay` lets Hermes detect a coding task, hand it off to Codex, and keep later user messages on the Codex side instead of routing every turn back through Hermes LLM.

The intended v1 flow is:

1. Hermes decides a request is a coding task.
2. Hermes shows the full handoff prompt and `workdir` to the user.
3. Hermes calls `coding_relay`.
4. The plugin starts or resumes a Codex CLI session.
5. Relay output is sent back to the user in event order.
6. Later messages are intercepted by `pre_gateway_dispatch` and forwarded directly to Codex.
7. `/relay-back` exits coding mode and returns control to Hermes.

## Scope

Current repository decisions are intentionally narrow:

- v1 supports `codex` only
- `workdir` must be a child directory under configured `plugins.coding-relay.workdir_root`
- runtime state lives under `run/`
- event parsing, session state, and output formatting remain separated
- `codex exec` slash commands such as `/status` are not treated as supported relay features

See [DESIGN.md](DESIGN.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/DECISIONS.md](docs/DECISIONS.md) for the repo-local source of truth.

## Installation Model

This project uses the Hermes directory plugin model rather than Python package entry points.

Expected layout:

```text
~/projects/coding-relay/                 # development repo
~/.hermes/plugins/coding-relay          # symlink or clone target Hermes loads
```

Hermes discovers the plugin through:

- `plugin.yaml`
- `__init__.py`

`pip install .` is not the installation path for this project.

## Repository Layout

```text
.
├── __init__.py
├── handoff_tool.py
├── gateway_hook.py
├── relay_delivery.py
├── relay_runtime.py
├── relay_context.py
├── event_adapter.py
├── output_formatter.py
├── session_store.py
├── slash_commands.py
├── plugin.yaml
├── AGENTS.md
├── DESIGN.md
├── docs/
└── tests/
```

## Development

Important repo rules live in [AGENTS.md](AGENTS.md).

Before changing code, read:

- [AGENTS.md](AGENTS.md)
- [DESIGN.md](DESIGN.md)
- [docs/TASKS.md](docs/TASKS.md)
- [docs/DECISIONS.md](docs/DECISIONS.md)

Python checks should use the Hermes venv:

```bash
/home/dontstarve/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests
```

## Testing Notes

Current automated coverage is local and process-level:

- tool registration
- Codex transport and event adaptation
- runtime relay state and session persistence
- first-turn and follow-up relay output formatting

Real gateway validation is still separate:

- Feishu is the only platform with real end-to-end validation so far
- true platform verification still requires a live Hermes gateway and external message source

## Roadmap

Near-term follow-up work is tracked in [docs/TASKS.md](docs/TASKS.md).

The main remaining validation gap is not basic plugin wiring; it is broader real-platform confirmation and any future non-Feishu gateway support.
