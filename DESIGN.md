# Coding Relay — Hermes Plugin 设计文档

> 目标：让 Hermes 在识别到 coding 任务后，将对话无缝切到 Codex CLI；进入 coding mode 后，后续普通消息直接走 Codex，不再消耗 Hermes LLM token，直到用户显式退出 relay 控制命令。

## 1. 第一版范围

第一版只做一条可靠主链路：

- 只支持 `codex`
- 进入 coding mode 后，普通消息完全绕过 Hermes LLM
- 通过 `coding_handoff` tool 进入 coding mode
- 通过 `pre_gateway_dispatch` hook 接管后续消息
- 通过 `/relay-back` 退出 coding mode
- 运行态数据统一写入仓库内的 `run/`

第一版**不做**：

- 多 agent 支持
- 复杂 session chain / memory capsule
- 基于额外 LLM 的摘要生成
- 完整可观测性面板

## 2. 总体流程

```text
阶段 1：正常对话（Hermes LLM 介入）
  用户发起 coding 需求
  Hermes 判断为 coding 任务
  Hermes 调用 coding_handoff

阶段 2：Coding Mode（Hermes LLM 不介入）
  plugin 启动或恢复 Codex
  plugin 解析 Codex NDJSON 事件
  plugin 将结果格式化并回传 gateway
  用户后续普通消息直接转给 Codex
  用户输入 /relay-back 退出

阶段 3：回到正常对话
  plugin 清理 active relay state
  Hermes 重新接管
```

## 3. 术语与状态模型

第一版显式区分三类标识：

- `session_id`：Hermes 当前会话标识；用于判断“当前这一轮 Hermes 会话”是否处于 coding mode
- `session_key`：Hermes 对同一 chat/source 的稳定归并键；用于识别 reset 前后的同源会话并清理旧内存态
- `codex_thread_id`：Codex `thread.started.thread_id` 返回的真实恢复标识；也是持久化主键
- `active relay state`：插件当前内存态，描述某个 `session_id` 当前绑定的 Codex 会话和进程

### 3.1 Active Relay State

```python
class ActiveRelayState:
    session_id: str
    session_key: str | None
    agent: str                  # 固定为 "codex"
    codex_thread_id: str | None
    workdir: str
    sandbox_mode: str           # 默认 "workspace-write"
    yolo: bool                  # 默认 False
    current_process: subprocess.Popen | None
    current_message_id: str | None
```

说明：

- 第一版只允许一个 `session_id` 同时绑定一个 active Codex 会话
- 同一 `session_key` 下若产生新的 `session_id`，旧的 active relay state 会被清理
- gateway 重启后内存态丢失，持久化数据仍保留在 `run/`

## 4. 仓库布局与运行态边界

### 4.1 源码目录

```text
~/projects/coding-relay/
├── plugin.yaml
├── __init__.py
├── handoff_tool.py
├── gateway_hook.py
├── agent_spawner.py
├── event_adapter.py
├── output_formatter.py
├── session_store.py
├── AGENTS.md
├── DESIGN.md
└── docs/
```

### 4.2 运行态目录

所有运行态文件只允许写入 `run/`：

```text
run/
├── sessions.json
├── active/
└── logs/
```

约束：

- `run/` 必须加入 `.gitignore`
- `run/` 只存运行态数据，不存源码配置真相
- 删除 `run/` 后，项目应仍可通过源码和配置重新启动
- 非经用户明确要求，真实联调与烟雾测试不得在当前仓库源码树内创建测试产物
- 真实 agent / gateway smoke 默认使用 `~/projects` 下独立临时项目，并在测试后清理

## 5. Hermes Plugin API 使用

### 5.1 Tool：`coding_handoff`

由 Hermes LLM 调用，用于进入 coding mode。

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent` | string | 是 | 第一版仅允许 `codex` |
| `prompt` | string | 是 | Hermes 组装好的初始 prompt |
| `workdir` | string | 是 | 工作目录 |
| `codex_thread_id` | string | 否 | 如需恢复历史 Codex 会话则传入 |
| `sandbox_mode` | string | 否 | `read-only` / `workspace-write` / `danger-full-access` |
| `yolo` | boolean | 否 | 是否使用 Codex 的危险全开模式 |

返回：

```json
{
  "status": "handed_off",
  "agent": "codex",
  "codex_thread_id": "019e0769-f520-7aa2-a219-da891e701f8d",
  "sandbox_mode": "workspace-write",
  "yolo": false,
  "initial_messages": [
    "已转接到 codex。",
    "命令完成：pytest -q (exit 0)"
  ],
  "message": "已转接到 codex。后续消息直接发给它，发送 /relay-back 回来找 Hermes。"
}
```

行为：

1. 校验 `agent == "codex"`
2. 校验 `workdir` 位于允许的项目根内
3. 若传入 `codex_thread_id`，走 resume；否则新建会话
4. 以当前 `session_id` 建立 `active relay state`
5. 持久化更新 `run/sessions.json`

### 5.2 Slash Command：`/relay-back`

作用：

- 退出 coding mode
- 若当前有活跃 Codex 进程，则优先温和终止，再必要时强杀
- 清理当前 `session_id` 的 `active relay state`

### 5.3 Slash Command：`/relay-mode`

作用：

- 查看当前 relay 执行模式
- 在当前 `session_id` 的 active relay state 上切换后续 turn 的执行策略

支持值：

- `status`
- `safe`：`workspace-write + -a never`
- `readonly`：`read-only + -a never`
- `yolo`：`--dangerously-bypass-approvals-and-sandbox`

### 5.4 Hook：`pre_gateway_dispatch`

行为：

- 当前 `session_id` 不在 coding mode：返回 `None`
- coding mode 中收到 `/relay-back`：执行退出逻辑，返回 `None`
- coding mode 中收到 `/relay-mode ...`：修改 active relay state，返回 `{"action": "skip"}`
- coding mode 中收到其他普通消息或 slash 命令：原样转发给 Codex，返回 `{"action": "skip"}`，Hermes 不介入

## 6. Codex 调用方式

第一版按非交互模式调用 Codex。

### 6.1 新建会话

```bash
codex -a never -s workspace-write exec --json -C <workdir> "<prompt>"
```

### 6.2 恢复会话

```bash
codex -a never -s workspace-write exec resume <codex_thread_id> --json "<prompt>"
```

### 6.3 Yolo 模式

```bash
codex --dangerously-bypass-approvals-and-sandbox exec --json -C <workdir> "<prompt>"
```

说明：

- `--json`：输出 NDJSON
- 默认 `workspace-write`：保证工作区内真实编码可写，不再落入只读会话
- `-a never`：gateway 模式下不等待交互式 approval
- `-C <workdir>`：仅新建会话时指定工作目录
- resume 时以 `codex_thread_id` 为唯一恢复标识
- `yolo` 用于显式放弃 sandbox 和 approval 边界，只在用户明确要求时开启

## 7. 事件解析分层

第一版严格分三层，不把 JSONL 解析、状态更新和飞书展示糊在一起。

### 7.1 `agent_spawner.py`

职责：

- 构造 Codex CLI 参数
- 启动 / 终止子进程
- 读取 stdout / stderr
- 逐行产出原始 NDJSON 事件

### 7.2 `event_adapter.py`

职责：

- 将 Codex 原始事件转换成插件内部事件
- 未知事件跳过并记录，不影响主流程

内部事件建议最小集合：

- `session_init`
- `agent_text`
- `command_started`
- `command_finished`
- `file_change`
- `relay_error`
- `turn_completed`

### 7.3 `output_formatter.py`

职责：

- 将内部事件转换成 gateway / 飞书可读输出
- 与 Codex 原始事件结构解耦

## 8. 第一版支持的 Codex 事件

第一版只消费主链路必需事件：

| 原始事件 | 处理 |
|---------|------|
| `thread.started` | 提取 `codex_thread_id`，产出 `session_init` |
| `item.completed` + `agent_message` | 产出 `agent_text` |
| `item.started` + `command_execution` | 产出 `command_started` |
| `item.completed` + `command_execution` | 产出 `command_finished` |
| `item.started` / `item.completed` + `file_change` | 产出 `file_change` |
| `error` | 产出 `relay_error` |
| `turn.completed` | 记录本轮结束和 usage |

第一版暂不对外展示：

- `todo_list`
- `reasoning`
- `mcp_tool_call`
- `web_search`

它们后续可作为内部扩展点，但不进入 v1 主流程。

## 9. 输出策略

第一版目标是稳定可读，不追求复杂富交互。

建议策略：

1. `agent_text`：完整输出
2. `command_started`：简短提示，例如 `执行命令：pytest -q`
3. `command_finished`：输出 exit code 和截断后的结果摘要
4. `file_change`：输出去重后的文件名摘要，必要时截断为少量文件 + 总数
5. `relay_error`：给用户明确错误，而不是静默失败；至少覆盖 CLI 未安装、spawn 失败、非零退出和 JSON 解析异常
6. `output_formatter` 自身异常时回退到原始 `agent_text`，不阻断 Codex 主流程

如果 gateway / 飞书消息编辑能力不稳定，允许第一版退化为“连续发新消息”，不强制实现单消息流式编辑。

### 9.1 Approval 与交互边界

第一版支持两类交互：

- 普通文本对话，包括 Codex 在 `agent_message` 中提出的方案选择
- relay 控制命令：`/relay-back`、`/relay-mode`

第一版不承诺：

- 将 Codex 自身运行时的结构化 approval / choice 事件桥接成飞书按钮或确认框
- 在 `exec --json` 上构建稳定的“等待用户批准后继续”的协议层

因此 v1 的工程边界是：

- 默认 `safe` 模式：`workspace-write + -a never`
- 显式 `readonly`
- 显式 `yolo`

## 10. 会话持久化与继续能力

### 10.1 存储位置

`run/sessions.json`

### 10.2 数据结构

```json
{
  "sessions": [
    {
      "codex_thread_id": "019e0769-f520-7aa2-a219-da891e701f8d",
      "agent": "codex",
      "workdir": "/home/dontstarve/projects/dst-server-ctl",
      "created_at": "2026-05-09T10:00:00+08:00",
      "last_active_at": "2026-05-09T10:30:00+08:00",
      "summary": "目标：重构配置模块；最近结果：已拆分 parser/validator；最近检查：pytest -q (exit 0)",
      "last_files": [
        "config.py",
        "validator.py",
        "tests/test_config.py"
      ]
    }
  ]
}
```

### 10.3 summary 来源

第一版 summary 采用规则提取，不依赖额外 LLM。

来源按优先级组合：

1. 初始 `prompt`
2. 最近几条 `agent_message`
3. 最近的 `file_change`
4. 最近的 `command_execution` 结果

目标是支撑两件事：

- Hermes 在下次 handoff 前询问“继续还是新建”
- 人类快速知道上次做到哪

## 11. workdir 约束

第一版 `workdir` 只允许位于约定项目根下，例如：

- `~/projects/*`

理由：

- 防止 Hermes 或 agent 被错误路由到任意路径
- 缩小命令执行和文件修改边界

不在允许范围内的路径，`coding_handoff` 直接拒绝。

## 12. 错误处理

第一版采用简单直接的错误策略：

| 场景 | 处理 |
|------|------|
| Codex CLI 未安装 | 明确告知未安装 |
| spawn 失败 | 明确告知启动失败 |
| NDJSON 某一行解析失败 | 跳过该行并记录日志 |
| Codex 非零退出 | 返回有限且可读的错误摘要 |
| 输出回传失败 | 记录日志，但不影响 Codex 主进程 |

原则：

- 未知事件不阻塞主流程
- 单行坏数据不导致整轮失败
- 用户总能知道“是哪里坏了”

## 13. 后续扩展

第一版完成后，再考虑：

- `todo_list` 内部状态跟踪
- `reasoning` / `mcp_tool_call` 可观测性
- 更好的流式编辑体验
- 多 agent adapter

这些都属于后续任务，不进入 v1 必做范围。
