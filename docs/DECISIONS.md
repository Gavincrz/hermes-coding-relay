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
- 只有 `/relay-back` 才退出 coding mode

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

- 第一版 `workdir` 只允许位于约定项目根下的具体子目录，例如 `~/projects/*`
- `~/projects` 根目录本身不算合法 `workdir`

理由：

- 缩小文件和命令执行边界
- 降低误操作风险

## D011 `codex exec` 不支持斜杠命令

日期：2026-05-11

结论：

- 第一版 `codex exec` 路径不承诺支持 `/status` 这类斜杠命令
- 这类命令只属于 Codex 交互模式，不应被 relay 当成可靠能力

理由：

- `codex exec` 的执行模型是非交互式的
- 端到端联调里已经确认斜杠命令不会按预期生效
- 先把限制文档化，避免用户继续把它当成可用能力

## D012 relay 配置与输出采用插件级约束

日期：2026-05-11

结论：

- `workdir_root` 作为插件级配置，从 `plugins.coding-relay.workdir_root` 读取，默认值为 `~/projects`
- `validate_workdir` 和 tool schema description 都基于同一个配置来源生成
- Codex turn 输出按事件顺序流式发送，turn 完成后额外补一条收尾消息

理由：

- 运行时校验和模型侧约束必须一致，避免 prompt 和实际行为打架
- 允许在不改 Hermes 核心的前提下调整项目根边界
- 用户需要看到有价值的进度、命令和错误信息，而不是只看最终结论

## D013 对外 tool 名统一为 `coding_relay`

日期：2026-05-11

结论：

- 插件和 skill 继续使用 `coding-relay`
- Hermes 对外注册的 tool 名统一为 `coding_relay`
- 旧的 Python 符号名 `coding_handoff` 只作为兼容别名保留，不再作为文档化入口

理由：

- 插件名、skill 名和 tool 名长期不一致，会提高模型和人工使用时的混淆概率
- `coding_relay` 比 `coding_handoff` 更接近这套能力在用户侧的整体心智模型
- 保留兼容别名可以降低现有导入路径的断裂风险

## D014 首轮输出与后续 turn 共用 relay 发送链路

日期：2026-05-11

结论：

- `coding_relay` 的首轮 Codex 输出不再默认依赖 Hermes 展示 `initial_messages`
- 只要 handoff 时存在可用的 gateway/source，上下文中的首轮事件就由 relay 直接按顺序发送给用户
- Hermes 在 tool 返回后只做极简确认，或不额外发送任何内容
- relay 对外输出统一采用轻量 Markdown：保留原始 `agent_text`，命令/文件/错误/完成消息使用短标题模板

理由：

- 首轮和后续 turn 使用两套输出出口，会让用户体验和联调路径不一致
- 让 Hermes 复述首轮正文，会造成重复消息和职责重叠
- 飞书支持基础 Markdown，足以承载代码块、强调和链接，不需要引入更重的富文本协议

## D015 显式 resume 先展示结构化恢复提示

日期：2026-05-11

结论：

- 当 `coding_relay` 被显式传入 `codex_thread_id` 做 resume 时，relay 先展示一条“已恢复历史会话”提示
- 提示内容来源于 `run/sessions.json` 中该线程的结构化记录，不读取最后几条原始消息
- 提示优先包含 `workdir`、`last_active_at`、`summary`、`last_files`
- 如果没有对应记录，退化为最小提示，不阻塞 resume

理由：

- 用户需要确认当前恢复的是哪一个历史线程，以及上次做到哪里
- 结构化摘要比“最后几条消息”更稳定，也更适合飞书阅读
- 这条提示只在显式 resume 时出现，不会污染普通新建 session 或当前 coding mode 内的连续对话

## D016 命令执行消息采用三档可见性配置

日期：2026-05-12

结论：

- 插件新增 `plugins.coding-relay.command_visibility`
- 支持 `none`、`filtered`、`all` 三档
- 默认值为 `none`
- `filtered` 通过规则显示测试、静态检查和构建类高价值成功命令；失败命令始终显示

理由：

- 当前“命令开始 + 命令完成”全部外显，对真实对话过于吵闹
- 联调和排障时仍需要可切换到全量命令视图
- 这类过滤属于稳定展示逻辑，适合用规则和配置解决，不需要额外 AI 参与

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
- 不保留 `/back` 这类短别名兼容

理由：

- 降低与 Hermes 内建命令及其他插件命令的冲突概率
- 避免占用 Codex 可能使用的简短 slash 名称
- 保持“进入 coding mode 后 Hermes 让出主控制面”的直觉一致性

## D009 真实联调不污染当前仓库源码树

日期：2026-05-09

结论：

- 非经用户明确要求，不在当前仓库源码树内创建真实联调、烟雾测试或探针产物
- 真实 agent / gateway smoke 默认使用 `~/projects` 下独立临时项目
- 测试完成后清理临时项目，不把测试产物混入 git 工作树

理由：

- 避免把联调产物混入源码提交边界
- 降低误报、脏工作树和测试后残留文件的风险
- 与 `run/` 只存运行态、源码树不落临时产物的规则保持一致

## D010 Active relay state 按 Hermes session_id 绑定

日期：2026-05-09

结论：

- `coding_relay` 不再以 `chat_id` 作为进入 coding mode 的前提
- active relay state 以内存态 `session_id` 为主键
- 同一 `session_key` 下若出现新的 `session_id`，旧 relay state 自动清理
- `codex_thread_id` 继续作为可恢复的持久化标识，和 active coding mode 解耦

理由：

- Hermes 普通 tool 调用稳定传入的是 `task_id/session_id`，不是 `chat_id`
- `/reset` 后需要让旧 coding mode 自然失效，不能继续命中新会话
- active coding mode 属于瞬时控制态，不应作为永久真相保存
