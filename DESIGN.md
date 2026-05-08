# Coding Relay — Hermes Plugin 设计文档

> 让赫弥酱在判断 coding 任务时，将用户无缝转接到 coding agent（codex / claude code / opencode），通过飞书等 gateway 直接与 coding agent 交互，不消耗 Hermes 自身 token。

## 1. 整体流程

```
阶段1: 正常对话（赫弥酱 LLM 介入）
  用户: "帮我把 dst-server-ctl 的配置模块重构一下"
  赫弥酱: (LLM 分析) → 判断这是 coding 任务 → 调用 coding_handoff 工具

阶段2: Coding Agent 会话（赫弥酱 LLM 不介入，零 token）
  plugin 拦截用户消息 → spawn codex exec → 解析 JSONL → 流式回传飞书
  用户后续消息 → spawn codex exec resume → 解析 JSONL → 流式回传飞书
  ...
  用户: "/back"

阶段3: 回到正常对话
  赫弥酱: "回来啦～"
```

### 3.1 详细时序

```
用户消息 ──→ Gateway
               │
               ├─ pre_gateway_dispatch hook 检查 coding_mode
               │
               ├─ [coding_mode OFF] ──→ 正常 LLM 流程
               │     └─ LLM 调用 coding_handoff tool
               │          ├─ 查 sessions.json 有无匹配 session
               │          ├─ 如有 → 赫弥酱问用户 "继续还是新建？"
               │          ├─ spawn codex exec [--resume <id>] --json -C <workdir> "<prompt>"
               │          ├─ 解析 JSONL，流式回传飞书
               │          ├─ 记录 session_id，设置 coding_mode ON
               │          └─ tool 返回 {"status":"handed_off",...}
               │
               └─ [coding_mode ON] ──→ 不走 LLM
                    ├─ 用户发 "/back" → 杀 codex 进程 + coding_mode OFF
                    └─ 其他消息 → spawn codex exec resume <id> --json "<msg>"
                         ├─ 解析 JSONL，流式回传飞书
                         └─ 更新 sessions.json 的 last_active
```

---

## 2. 插件加载方式

### 2.1 目录结构

```
~/projects/coding-relay/          # 开发目录（git 管理）
├── plugin.yaml                   # 插件 manifest
├── __init__.py                   # register(ctx) 入口
├── handoff_tool.py               # coding_handoff tool 定义
├── gateway_hook.py               # pre_gateway_dispatch hook
├── session_manager.py            # session 文件读写
├── agent_spawner.py              # spawn CLI + JSONL 解析
├── output_formatter.py           # JSONL 事件 → 飞书消息格式化
└── sessions.json                 # 运行时 session 数据

~/.hermes/plugins/coding-relay    # symlink → ~/projects/coding-relay/
```

### 2.2 非侵入式

- 插件放在用户插件目录 `~/.hermes/plugins/coding-relay/`（symlink）
- Hermes 源码零修改，升级不受影响
- 通过 `config.yaml` 的 `plugins.enabled: [coding-relay]` 启用

### 2.3 plugin.yaml

```yaml
name: coding-relay
version: 0.1.0
description: "将 coding 任务转接到 codex/claude-code/opencode，通过 gateway 直接交互"
author: 小猫先生
provides_tools:
  - coding_handoff
provides_hooks:
  - pre_gateway_dispatch
requires_env: []
```

---

## 3. Hermes Plugin API 使用

### 3.1 注册的 Tool（赫弥酱 LLM 调用）

**`coding_handoff`**

赫弥酱在对话中判断需要 coding agent 时调用此工具。

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent` | string | 是 | 使用的 coding agent：`codex` / `claude` / `opencode` |
| `prompt` | string | 是 | 初始 prompt，由赫弥酱根据对话上下文组装 |
| `workdir` | string | 是 | 工作目录，如 `~/projects/dst-server-ctl/` |
| `session_id` | string | 否 | 如需 resume 上次会话，传入 session_id |

返回：

```json
{
  "status": "handed_off",
  "agent": "codex",
  "session_id": "a1b2c3-...",
  "message": "已转接到 codex。后续消息直接发给它，发送 /back 回来找赫弥酱～"
}
```

### 3.2 注册的 Slash Command

**`/back`** — 退出 coding mode，杀死当前 codex 进程（如有），回到赫弥酱正常对话。

### 3.3 注册的 Hook

**`pre_gateway_dispatch`** — gateway 层消息拦截。

行为：
- coding_mode OFF → 返回 None（正常流转）
- coding_mode ON + 消息是 `/back` → 杀进程 + 清除 coding_mode + 返回 None（让赫弥酱接手）
- coding_mode ON + 普通消息 → spawn coding agent → 返回 `{"action": "skip"}`（赫弥酱不介入）

---

## 4. Coding Mode 状态管理

### 4.1 状态存储

内存中维护一个 dict，key 为 chat_id：

```python
# coding_mode 状态（内存，gateway 重启自然清除）
_active_sessions: dict[str, CodingSession] = {}

class CodingSession:
    agent: str              # "codex" / "claude" / "opencode"
    session_id: str         # CLI 返回的 session ID
    workdir: str            # 工作目录
    current_process: subprocess.Popen | None  # 正在运行的 CLI 进程
    message_id: str | None  # 当前飞书消息 ID（用于流式编辑）
```

### 4.2 生命周期

```
coding_handoff tool 调用
  → spawn codex exec
  → 记录 session_id 到 _active_sessions[chat_id]
  → 记录到 sessions.json

用户后续消息
  → _active_sessions[chat_id] 存在 → coding_mode ON
  → spawn codex exec resume <session_id>

/back
  → kill _active_sessions[chat_id].current_process
  → del _active_sessions[chat_id]
```

---

## 5. Session 持久化

### 5.1 文件路径

`~/.hermes/plugins/coding-relay/sessions.json`

### 5.2 格式

```json
{
  "sessions": [
    {
      "id": "a1b2c3-...",
      "project": "/home/dontstarve/projects/dst-server-ctl",
      "agent": "codex",
      "workdir": "/home/dontstarve/projects/dst-server-ctl",
      "created": "2026-05-08T15:00:00",
      "last_active": "2026-05-08T15:30:00",
      "summary": "重构配置模块"
    }
  ]
}
```

### 5.3 Session 查询与确认

赫弥酱调用 `coding_handoff` 之前（在她的 LLM 对话阶段），由 skill 引导她：

1. 读取 `sessions.json`
2. 按 `workdir` + `agent` 匹配已有 session
3. 如有匹配，通过 `clarify` 工具问用户："上次有一个 codex 会话（重构配置模块），要继续还是新建？"
4. 用户选择"继续" → handoff 时传 `session_id`
5. 用户选择"新建" → handoff 时不传 `session_id`

---

## 6. CLI Spawn 与输出解析

### 6.1 Codex 命令

**新建会话：**
```bash
codex exec --json -C <workdir> "<prompt>"
```

**Resume 会话：**
```bash
codex exec resume <session_id> --json "<prompt>"
```

**关键 flag：**
- `--json`：输出 NDJSON 到 stdout
- `-C <workdir>`：指定工作目录
- `--dangerously-bypass-approvals-and-sandbox`：如果需要（待讨论，可能不需要）

### 6.2 JSONL 事件解析

参考 Clowder AI 的 `codex-event-transform.ts` 实现。

Codex `--json` 输出的事件类型及处理策略：

| 事件 | `e.type` | `item.type` | 展示策略 |
|------|----------|-------------|---------|
| 会话开始 | `thread.started` | — | 提取 `session_id` 记录 |
| Agent 文本回复 | `item.completed` | `agent_message` | **核心内容，完整展示** |
| 命令执行开始 | `item.started` | `command_execution` | `🔧 <command>` |
| 命令执行完成 | `item.completed` | `command_execution` | 结果摘要（截断到合理长度） |
| 文件变更 | `item.completed` | `file_change` | `📝 修改了 N 个文件` |
| MCP 调用开始 | `item.started` | `mcp_tool_call` | `🔧 MCP: server/tool` |
| MCP 调用完成 | `item.completed` | `mcp_tool_call` | 结果摘要 |
| 任务进度 | `item.*` | `todo_list` | 第一版不展示 |
| 推理过程 | `item.completed` | `reasoning` | 不展示 |
| 错误 | `error` | — | 展示错误信息 |
| 搜索 | `item.completed` | `web_search` | 不展示 |

### 6.3 输出格式化示例

```
🔧 执行: cargo test --lib
✅ cargo test --lib (exit: 0)
   running 12 tests... all passed

我认为配置模块可以按以下方式重构：
1. 将 config.rs 拆分为 parser 和 validator
2. ...

📝 修改了 4 个文件
```

---

## 7. 流式输出策略

### 7.1 基本策略

1. codex 开始执行时，发送一条飞书消息作为"容器"
2. 后续输出尝试**编辑同一条消息**追加内容
3. 如果编辑失败（飞书频率限制），**发一条新消息**继续
4. `agent_message` 的完整输出单独发一条

### 7.2 飞书 API 注意事项

- 飞书消息编辑 API 频率限制需要实测
- 编辑失败时 fallback 到发新消息，确保不丢内容
- 消息内容过长时需要分段（飞书单条消息有长度上限）

---

## 8. 错误处理

简单直接：

| 场景 | 处理 |
|------|------|
| codex CLI 未安装 | 告知用户未安装，提示安装命令 |
| codex 进程非零退出 | 告知出错了 + 有限的错误信息 |
| codex spawn 失败 | 告知启动失败 |
| JSONL 解析失败 | 跳过该行，继续处理后续 |
| 飞书消息发送失败 | 日志记录，不影响 codex 进程 |

不做自动重试，出错就让用户知道，由用户决定下一步。

---

## 9. 超时策略

**不设硬超时。**

- 用户通过飞书可以直接观察 codex 是否在输出
- 如果卡住，用户发 `/back` 退出并杀进程
- 下次 handoff 时可以 resume 同一个 session 继续

---

## 10. 多 Agent 兼容性（未来）

当前仅实现 codex。架构上预留多 agent 支持：

| Agent | 非交互式命令 | JSONL 支持 | Resume 命令 |
|-------|------------|-----------|------------|
| codex | `codex exec --json` | ✅ | `codex exec resume <id> --json` |
| claude code | 待确认 | stream-json | 待确认 |
| opencode | 待确认 | ndjson | 待确认 |

每个 agent 对应一个 `AgentAdapter`，定义统一的 spawn / parse / format 接口。第一版只实现 `CodexAdapter`。

```python
class AgentAdapter(Protocol):
    def build_spawn_args(self, prompt, workdir, session_id=None) -> list[str]: ...
    def parse_event(self, event: dict) -> FormattedEvent | None: ...
    def extract_session_id(self, event: dict) -> str | None: ...
```

---

## 11. Handoff 返回值与赫弥酱衔接

### 11.1 handoff tool 返回值

```json
{
  "status": "handed_off",
  "agent": "codex",
  "session_id": "a1b2c3-...",
  "message": "已转接到 codex。后续消息直接发给它，发送 /back 回来找赫弥酱～"
}
```

赫弥酱的 LLM 看到这个返回值后，自然地告诉用户已转接。

### 11.2 /back 回来后

第一版不自动衔接。赫弥酱回来后等待用户主动说话。

未来可以优化：plugin 在退出 coding mode 时将最后一次 agent_message 的摘要写入 sessions.json 的 summary 字段，赫弥酱通过 skill 自行读取并衔接对话。

---

## 12. 赫弥酱 Skill 配合

需要一个 skill 引导赫弥酱正确使用 `coding_handoff` 工具：

1. 判断用户意图是否为 coding 任务
2. 读取 `~/.hermes/plugins/coding-relay/sessions.json` 查询历史 session
3. 如有匹配的 session，用 clarify 询问用户继续还是新建
4. 调用 `coding_handoff` 工具，传入正确的参数
5. 看到工具返回 `handed_off` 后，告诉用户已转接

---

## 13. 实现优先级

### P0（第一版必须）

- [ ] plugin 骨架（plugin.yaml + register）
- [ ] `coding_handoff` tool（仅 codex）
- [ ] `pre_gateway_dispatch` hook（消息拦截 + 转发）
- [ ] `/back` slash command
- [ ] codex exec spawn + JSONL 解析
- [ ] 流式输出（编辑 + fallback 发新消息）
- [ ] sessions.json 读写
- [ ] 错误处理

### P1（体验优化）

- [ ] 赫弥酱 skill（自动判断 + session 查询 + 确认）
- [ ] /back 后自动衔接（读取 session summary）
- [ ] 输出格式精细调优

### P2（多 agent 扩展）

- [ ] claude code adapter
- [ ] opencode adapter
- [ ] AgentAdapter 抽象接口

---

## 14. 参考实现

- Clowder AI CLI spawn: `packages/api/src/utils/cli-spawn.ts`
- Codex 事件解析: `packages/api/src/domains/cats/services/agents/providers/codex-event-transform.ts`
- NDJSON 解析: `packages/api/src/utils/ndjson-parser.ts`
- Hermes Plugin API: `hermes_cli/plugins.py`（PluginContext、register_tool、register_hook、register_command）
- Hermes Gateway Hook: `gateway/run.py`（pre_gateway_dispatch 调用点在 ~L4946）
