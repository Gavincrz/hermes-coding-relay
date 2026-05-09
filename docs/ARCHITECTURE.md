# Architecture

## Summary

`coding-relay` is a Hermes directory plugin that hands coding tasks off to Codex CLI.

第一版目标是稳定的单链路 relay：

- Hermes LLM 通过 `coding_handoff` 进入 coding mode
- gateway hook 在 coding mode 下绕过 Hermes LLM
- Codex CLI 负责实际编码工作
- 插件只负责状态、转发、事件解析和输出格式化

## Installation Model

当前项目采用 **目录插件模式**，不是 pip entry-point 模式。

代码安装方式：

- 仓库源码位于独立开发目录
- 通过 symlink 或 clone 放到 `~/.hermes/plugins/coding-relay`
- Hermes 通过 `plugin.yaml` + `__init__.py` 的目录扫描加载插件

这意味着：

- `pyproject.toml` 不是当前模式的必要前提
- `pip install .` 不会把代码安装到 `~/.hermes/plugins/coding-relay`
- 如果未来要发布为 pip 插件，需要额外提供 `[project.entry-points."hermes_agent.plugins"]`

## Runtime And Dependency Boundary

本插件是 **进程内插件**：

- 插件 Python 代码由 Hermes 进程直接 `import`
- 因此插件依赖必须对 Hermes 自己的解释器可见
- 当前运行解释器是：`/home/dontstarve/.hermes/hermes-agent/venv/bin/python`

规则：

- 不允许向系统 Python 安装依赖
- 如需 Python 依赖，必须安装到 Hermes venv
- 在安装任何 Python 依赖前，必须先向用户说明必要性、安全性、合理性，并获得明确同意

如果某个依赖满足以下任一条件，应优先考虑独立 helper，而不是直接引入 Hermes venv：

- 体积大
- 升级频繁
- 与 Hermes 自身依赖容易冲突
- 不是每次插件加载都必须 import

## Major Modules

第一版按职责拆分：

- `__init__.py`
  - 插件注册入口
  - 只负责 wiring，不放业务逻辑

- `handoff_tool.py`
  - `coding_handoff` tool handler
  - 参数校验
  - 进入 coding mode 的入口协调

- `gateway_hook.py`
  - `pre_gateway_dispatch`
  - coding mode 下的消息拦截和转发

- `slash_commands.py`
  - `/back` 等会话控制命令

- `agent_spawner.py`
  - Codex CLI 启动、终止、stdout/stderr 读取

- `event_adapter.py`
  - 原始 Codex NDJSON 事件转内部事件

- `output_formatter.py`
  - 内部事件转平台输出

- `session_store.py`
  - `run/` 下的持久化状态读写

## Dependency Direction

依赖方向应保持单向：

- registration / entrypoint
  -> handlers / hook / commands
  -> relay infrastructure
  -> persistence / formatting

约束：

- `output_formatter.py` 不应直接解析原始 Codex NDJSON
- `session_store.py` 不应依赖平台输出逻辑
- `__init__.py` 不应包含真实业务逻辑

## Source Of Truth Vs Runtime State

源码真相：

- `AGENT.md`
- `DESIGN.md`
- `docs/TASKS.md`
- `docs/DECISIONS.md`
- 本插件 Python 源码

运行态：

- `run/sessions.json`
- `run/active/`
- `run/logs/`

约束：

- 运行态文件只能写入 `run/`
- `run/` 必须在 `.gitignore` 中
- 删除 `run/` 不应破坏源码和配置真相

## Testing And Verification Seams

第一版优先覆盖这些 seam：

- `register(ctx)` 是否正确注册 tool / hook / command
- `coding_handoff` 参数校验
- gateway hook 的透传与后续拦截行为
- Codex 命令构造
- NDJSON 解析和坏行容错
- 会话持久化格式

测试优先级：

- 先保证标准库可运行的基础测试
- 再按任务逐步扩展更真实的集成验证
