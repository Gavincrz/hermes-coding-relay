# Decisions

记录已拍板的设计选择，避免后续实现反复摇摆。

## D001 第一版只支持 Codex

日期：2026-05-09

结论：

- 第一版只支持 `codex`
- 不为 `claude`、`opencode` 提前做重抽象

理由：

- 先把 Hermes handoff 主链路做稳
- 避免为了未来扩展稀释当前实现质量

## D002 Coding Mode 完全接管

日期：2026-05-09

结论：

- 进入 coding mode 后，普通消息完全绕过 Hermes LLM
- 只有 `/back` 才退出 coding mode

理由：

- 降低 token 消耗
- 降低控制权切换复杂度

## D003 持久化主键使用 `codex_thread_id`

日期：2026-05-09

结论：

- 不额外创造语义重复的本地会话主键
- 持久化记录直接使用 `codex_thread_id`

理由：

- resume 真实依赖的就是这个标识
- 减少映射复杂度和术语混乱

## D004 运行态数据放在 `run/`

日期：2026-05-09

结论：

- 所有运行态数据写入仓库内 `run/`
- `run/` 必须加入 `.gitignore`

理由：

- 调试和排查路径更直观
- 不把插件运行态散落到 `~/.hermes/`

## D005 Summary 使用规则提取

日期：2026-05-09

结论：

- 第一版 summary 不依赖额外 LLM
- summary 来源于 prompt、agent_message、file_change、command_execution

理由：

- 降低复杂度
- 降低成本和额外失败面
- 已足够支撑“继续还是新建”的判断

## D006 workdir 只允许位于约定项目根

日期：2026-05-09

结论：

- 第一版 `workdir` 只允许位于约定项目根，例如 `~/projects/*`

理由：

- 缩小文件和命令执行边界
- 降低误操作风险

## D007 默认执行模式使用 `workspace-write + -a never`

日期：2026-05-09

结论：

- 默认 relay turn 以 `workspace-write` 启动 Codex
- 继续保留 `-a never`
- 激进模式通过显式 `yolo` 开启，不隐式升级

理由：

- `read-only` 会直接阻塞真实编码主链路
- 当前 `exec --json` 不应被假设为会稳定产出可桥接的 approval 事件
- `workspace-write` 能满足项目内修改，同时保留 v1 的非交互 relay 形态

## D008 Relay 控制命令使用独立前缀

日期：2026-05-09

结论：

- relay 自己的控制命令使用 `relay-*` 前缀，例如 `/relay-back`、`/relay-mode`
- coding mode 下除保留命令外，其余 slash 文本继续原样转给 Codex

理由：

- 降低与 Hermes 内建命令及其他插件命令的冲突概率
- 避免占用 Codex 可能使用的简短 slash 名称
- 保持“进入 coding mode 后 Hermes 让出主控制面”的直觉一致性
