# 端到端测试分析报告 (2026-05-11)

## 测试背景

通过 Feishu 发送消息触发 Hermes → coding-relay → Codex CLI 完整链路。测试时间约 11:40 - 12:36，共 7 轮对话（1 次 handoff + 6 次 hook 中继）。

## 发现的问题

### P1: Workdir 错误

**现象**：Codex 的工作目录是 `/home/dontstarve/projects`，而非预期的 `/home/dontstarve/projects/coding-relay-e2e-smoke`。

**根因**：Hermes LLM 调用 `coding_relay` 时传递了错误的 `workdir`。Codex session `019e151f` 的 meta 记录为 `cwd=/home/dontstarve/projects`，session record 中 `workdir` 同样是 `/home/dontstarve/projects`。

`validate_workdir` 仅检查路径是否在 `~/projects/` 下，`/home/dontstarve/projects` 本身通过了验证。

**影响**：Codex 在错误目录下执行命令，`pwd` 返回 `/home/dontstarve/projects`，后续 `rg` 搜索也基于错误目录。

**修复方向**：
1. `validate_workdir` 拒绝 `~/projects` 本身，必须传子目录路径
2. SKILL.md 强调必须传完整项目路径

### P2: /status 斜杠命令不可用

**现象**：用户发送 `/status`，Codex 把它当普通 prompt 处理，而非 CLI 命令。

**根因**：`codex exec` 模式不支持斜杠命令。`/status` 是 Codex 交互模式的内置命令，通过 `exec` 子命令调用时不识别。

Codex session 记录：
- Line 72: Codex 回复 "当前状态：已完成你前面的目录和 hello.py 任务"
- Line 83: 用户追问后，Codex 尝试 shell 执行 `/status`，得到 `/bin/bash: /status: No such file or directory (exit 127)`

**影响**：用户无法通过 relay 使用 Codex 的交互式命令。

**修复方向**：当前为已知限制。可在 hook 层拦截 `/status` 并返回 relay 状态摘要，或在文档中说明。

### P3: 输出格式问题——命令执行日志淹没有用内容

**现象**：用户最后收到的消息是 "执行命令：/bin/bash -lc \"rg --files /home/dontstarve | rg ...\"" 等命令执行细节，而非 Codex 的分析结果。

**根因**：`format_turn_output` 按以下顺序发送消息：

1. 所有 `agent_text`（Codex 的分析文本）
2. 所有 `command_runs`（命令启动 + 完成日志）
3. `file_changes`
4. `errors`

以最后一轮对话为例，Codex 产出：
- 4 段 agent_text（含 skills 列表、agents.md 搜索结果，共约 800 字符）
- 2 组命令执行对（4 条 command_started/command_finished 消息）

用户最终收到 8 条消息。有用的 agent_text 在前面发送，命令执行日志在后面，用户看到最后一条是命令日志，认为输出不完整。

此外 `MAX_OUTPUT_SNIPPET = 160` 限制了命令输出的截断长度。

**影响**：用户收到大量无用的命令执行细节，关键的 agent_text 反而被淹没。

**修复方向**：重新设计输出格式化策略——
- 方案 A：不发送 command_started/command_finished 细节，只发 agent_text + file_changes + errors
- 方案 B：将所有输出合并为一条消息，agent_text 为主，命令和文件变更附在后面
- 方案 C：command_runs 只在有错误时发送

## 本次修改清单

### gateway_hook.py

1. **修复 import bug**：诊断日志中 `from relay_runtime import _ACTIVE_RELAYS` 改为 `from .relay_runtime import _ACTIVE_RELAYS`（相对导入）。之前绝对导入导致 hook 每次调用都抛 `No module named 'relay_runtime'` 异常，Hermes 静默吞掉后走了正常 LLM 路径。

2. **添加回复发送**：hook 跑完 Codex turn 后，通过 `asyncio.get_running_loop().create_task(adapter.send())` 将结果发回飞书。之前 hook 只返回 `{"action": "skip"}`，gateway 收到 skip 后直接丢弃消息，没人发回复。

3. **清理诊断日志**：移除所有 `[RELAY-DIAG]` 调试日志。

4. **/relay-back 和 /relay-mode**：改为主动发送回复消息后返回 skip，而非在返回值中带 relay 数据。

### handoff_tool.py

- 清理 `[RELAY-DIAG]` 诊断日志。

### skill/SKILL.md

- 新增 "调用 coding_relay 时的回复规范" 章节：
  - 调用前先告知用户即将转交，展示 prompt 内容和 workdir
  - 调用后直接展示 `initial_messages`，不总结不改写
  - 成功时附上 "已进入 coding-relay 模式" 提示

### tests/test_plugin_registration.py

- 更新 3 处断言：hook 返回值从 `{"action": "skip", "relay": {...}}` 改为 `{"action": "skip"}`。

## 关键日志位置

| 内容 | 路径 |
|------|------|
| Hermes agent 日志 | `~/.hermes/logs/agent.log` |
| Hermes gateway 日志 | `~/.hermes/logs/gateway.log` |
| Codex session 日志 | `~/.codex/sessions/2026/05/11/rollout-2026-05-11T11-40-45-019e151f-7d48-7383-81fb-d639406e6480.jsonl` |
| coding-relay session 记录 | `~/projects/coding-relay/run/sessions.json` |

## 关键代码文件

| 文件 | 职责 |
|------|------|
| `gateway_hook.py` | hook 拦截后续消息，跑 Codex turn，发回复 |
| `handoff_tool.py` | 首次 handoff 工具，创建 relay + 跑第一个 Codex turn |
| `agent_spawner.py` | 构建 `codex exec` 命令，启动子进程 |
| `event_adapter.py` | 将 Codex NDJSON 事件转为内部 RelayEvent |
| `output_formatter.py` | 将 RelayTurnResult 格式化为用户可见消息列表 |
| `relay_runtime.py` | relay 状态管理（_ACTIVE_RELAYS、activate/get/exit） |
| `relay_context.py` | 从 kwargs/event 提取 session_id、chat_id 等 |
| `skill/SKILL.md` | 约束 Hermes LLM 的 handoff 行为 |
