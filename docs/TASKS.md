# Tasks

按顺序处理。一次只做一个任务。完成一个后再移动到下一个。

规则：

- `status` 只允许：`todo`、`doing`、`done`、`blocked`
- 任何时候只能有一个任务是 `doing`

## T001 插件骨架与注册入口

状态：done

目标：

- 建立 Hermes plugin 最小骨架
- 能被 Hermes 发现并加载
- 注册 `coding_relay`、`pre_gateway_dispatch`、`/relay-back`

完成标准：

- 仓库中存在最小插件文件结构
- `register(ctx)` 可成功注册 tool、hook、command
- 有基础加载或导入测试

实现备注：

- 第一版只支持 Codex
- 不实现完整 handoff 流程，只打通注册和模块边界
- 已完成：`plugin.yaml`、`__init__.py`、`handoff_tool.py`、`gateway_hook.py`、`slash_commands.py`
- 已完成：基础注册测试，覆盖 tool / hook / command 和占位 handler 行为

下一步：

- 进入 T002，实现 Codex spawn 和事件读取

---

## T002 Codex spawn 与 NDJSON 读取

状态：done

目标：

- 实现 Codex CLI 启动与 resume
- 读取 NDJSON 事件流
- 提供可复用的事件迭代接口

完成标准：

- 支持新建会话命令
- 支持 `resume <codex_thread_id>`
- 能提取 `thread.started`
- 能处理坏行、退出码、spawn 失败

实现备注：

- 只做事件读取，不做平台输出格式化
- 不在这一任务里做 gateway 接管
- 已完成：新增 `agent_spawner.py`，支持新建 / resume 命令构造
- 已完成：提供 `start_codex_process(...).iter_events()` 事件迭代接口
- 已完成：提取 `thread.started.thread_id`，并处理坏行、非零退出、spawn 失败
- 已完成：补充单测覆盖命令构造、事件提取和错误路径

下一步：

- 进入 T003，实现内部事件适配层

---

## T002R 仓库 README

状态：done

目标：

- 为 GitHub 仓库补充首页 README
- 说明项目目标、当前范围、安装方式和开发状态

完成标准：

- 仓库根目录存在 `README.md`
- README 与当前设计文档一致，不夸大未实现能力
- 包含安装方式、开发状态和文档入口

实现备注：

- 已完成：新增仓库级 `README.md`
- 已完成：说明当前仅完成插件骨架和 Codex transport 基础层
- 已完成：补充安装方式、仓库结构、开发与测试说明、路线说明

下一步：

- 回到 T003，实现内部事件适配层

---

## T002G 代码健康规则固化

状态：done

目标：

- 把“反补丁化开发”和持续重构约束写入仓库规则
- 同步更新项目初始化 skill，让新项目默认继承这套规范

完成标准：

- `AGENTS.md` 明确代码健康、复用优先和小步重构规则
- `project-bootstrap` skill 明确要求初始化阶段写入这些规则
- skill 模板包含可复用的默认表述

实现备注：

- 已完成：在 `AGENTS.md` 增加代码健康、复用优先、重构触发条件和测试安全网规则
- 已完成：更新 `project-bootstrap/SKILL.md`，要求 bootstrap 时编码这类约束
- 已完成：更新 `project-bootstrap/references/templates.md`，加入默认模板规则

下一步：

- 回到 T003，实现内部事件适配层

---

## T003 内部事件适配层

状态：done

目标：

- 将 Codex 原始事件转换成插件内部事件
- 与平台输出格式解耦

完成标准：

- 支持 `agent_message`
- 支持 `command_execution`
- 支持 `file_change`
- 支持顶层 `error`
- 未知事件可跳过且不影响主流程

实现备注：

- 第一版不展示 `reasoning`、`todo_list`、`mcp_tool_call`
- 可以先保留扩展位，但不做重抽象
- 已完成：新增 `event_adapter.py`，将 transport `StreamEvent` 适配为内部 `RelayEvent`
- 已完成：支持 `thread.started`、`agent_message`、`command_execution`、`file_change`、顶层 `error`、`turn.completed`
- 已完成：未知事件直接跳过，transport `relay_error` 原样透传，不中断主流程
- 已完成：补充单测覆盖事件映射与序列适配

下一步：

- 进入 T004，实现 gateway coding mode 接管

---

## T004 Coding Mode 接管

状态：done

目标：

- 在 coding mode 下绕过 Hermes LLM
- 普通消息直接转发给 Codex
- `/relay-back` 可退出 coding mode

完成标准：

- `coding_relay` 后 chat 进入 active relay state
- `pre_gateway_dispatch` 在 coding mode 下拦截普通消息
- `/relay-back` 能清理 active state，并在有活跃进程时停止它

实现备注：

- 只处理单 chat 单 active Codex 会话
- 不做复杂并发调度
- 已完成：新增 `relay_runtime.py`，集中管理 active relay state、workdir 校验、单轮 Codex turn 执行与退出清理
- 已完成：`coding_relay` 进入 active relay state，并立即发起首轮 Codex turn
- 已完成：`pre_gateway_dispatch` 在 coding mode 下拦截普通消息并通过 `resume` 语义继续会话，返回 `action=skip`
- 已完成：`/relay-back` 会清理 active state，并在有活跃进程时停止它
- 已完成：补充单测覆盖 handoff、gateway 拦截和退出行为

下一步：

- 进入 T005，实现持久化 session 与 summary

---

## T005 会话持久化与规则摘要

状态：done

目标：

- 持久化 Codex 会话记录
- 为“继续还是新建”提供可读摘要

完成标准：

- 主键使用 `codex_thread_id`
- 记录 `workdir`、`created_at`、`last_active_at`
- 规则提取 summary：来自 prompt、agent_message、file_change、command_execution
- 运行态文件仅落在 `run/`

实现备注：

- 不依赖额外 LLM 生成摘要
- 第一版不做 thread memory
- 已完成：新增 `session_store.py`，统一管理 `run/sessions.json` 的容错读写
- 已完成：按规则从 `prompt`、`agent_message`、`file_change`、`command_execution` 生成可读 `summary`
- 已完成：在 `coding_relay` 首轮和 coding mode 后续 turn 后更新 `created_at`、`last_active_at`、`last_files`
- 已完成：补充单测覆盖 summary 生成、持久化更新和 handoff / gateway 接线

未完成内容：

- 暂未在 Hermes handoff 前增加“继续还是新建”的实际交互入口；本任务先把持久化与摘要数据准备好

下一步：

- 进入 T006，实现输出格式化与错误体验

---

## T006 输出格式化与错误体验

状态：done

目标：

- 将内部事件转成稳定的平台输出
- 明确常见失败路径的用户反馈

完成标准：

- `agent_message` 可完整输出
- `command_execution` 和 `file_change` 有简明摘要
- CLI 未安装、spawn 失败、非零退出、JSON 解析异常都有明确反馈
- 输出失败不应影响 Codex 主流程

实现备注：

- 第一版优先稳定和可读，不追求复杂流式编辑体验
- 已完成：新增 `output_formatter.py`，统一格式化 `agent_text`、命令摘要、文件变更摘要和常见错误反馈
- 已完成：`coding_relay` 与 `pre_gateway_dispatch` 改为返回格式化后的平台输出，同时保留原始错误数据
- 已完成：补充单测覆盖格式化成功路径、常见错误映射和 handoff / gateway 接线

下一步：

- 进入 T007，补测试和文档收口

---

## T007 测试补强与文档收口

状态：done

目标：

- 为输出格式化链路补齐单测
- 同步收口设计与架构文档，反映新的输出模块边界

完成标准：

- 新增输出格式化相关单测，覆盖成功输出和主要错误映射
- `DESIGN.md`、`docs/ARCHITECTURE.md` 与实际输出链路一致
- `docs/TASKS.md` 记录 T006/T007 的完成情况与后续建议

实现备注：

- 只补与当前输出格式化主链路直接相关的测试
- 不扩展到真实 gateway 集成测试
- 已完成：新增 `tests/test_relay_runtime.py`，验证 runtime 会保留命令/文件事件上下文供格式化层使用
- 已完成：更新 `DESIGN.md`，补充 `coding_relay` 返回口径、错误覆盖范围和格式化降级策略
- 已完成：更新 `docs/ARCHITECTURE.md`，写实 `output_formatter.py` 职责和测试 seam

下一步：

- 进入后续任务，补更真实的集成验证与平台适配

---

## T008 执行模式与 approval 边界

状态：done

目标：

- 修复默认 Codex 会话只读导致无法编码的问题
- 支持显式开启更激进的执行模式
- 明确 v1 对 Codex 交互式 approval / choice 的支持边界

完成标准：

- 默认 handoff / relay turn 以可写工作区启动 Codex
- `coding_relay` 支持显式执行模式参数，至少包含 `yolo` 开关
- 单测覆盖命令构造和参数校验
- 文档明确说明当前不桥接 Codex 自身的交互式 approval 事件到飞书

实现备注：

- 第一版优先保证可靠 relay，不扩展成完整的人机协商代理
- 若 Codex `exec --json` 未暴露稳定 approval 事件，则保留 `never` / `yolo` 两种无交互模式
- 已完成：`agent_spawner.py` 默认改为 `workspace-write + -a never`，并支持显式 `yolo`
- 已完成：`coding_relay` 支持 `sandbox_mode` / `yolo` 参数校验与回显
- 已完成：新增会话级 `/relay-mode [status|safe|readonly|yolo]` 控制，并使用 `/relay-back`
- 已完成：移除 `/back` 兼容分支，避免与 Codex 自身 slash 空间混用
- 已完成：coding mode 下除 relay 保留命令外，其余 slash 文本继续原样转给 Codex
- 已完成：补充单测覆盖命令构造、模式切换、保留命令和 slash 透传
- 已完成：设计、架构和决策文档同步写实 approval 边界与命令命名空间

下一步：

- 进入后续任务，评估是否需要单独做 Codex 交互事件桥接

---

## T009 联调测试产物边界收口

状态：done

目标：

- 明确真实联调和烟雾测试不应污染当前仓库源码树
- 收紧仓库规则，避免测试产物混入提交边界

完成标准：

- `AGENTS.md` 明确禁止在当前仓库源码树内创建联调测试产物
- `DESIGN.md`、`docs/DECISIONS.md` 写实真实 smoke 的默认落点和清理要求

实现备注：

- 已完成：`AGENTS.md` 增加“真实联调默认使用 `~/projects` 下独立临时项目”的执行纪律
- 已完成：`DESIGN.md` 增加真实 smoke 不污染当前仓库源码树的边界说明
- 已完成：`docs/DECISIONS.md` 新增 D009，固定该约束

下一步：

- 继续飞书端到端测试，使用独立临时项目作为 `workdir`

---

## T010 Hermes 会话绑定修正

状态：done

目标：

- 修复 `coding_relay` 在 Hermes tool 调用路径里拿不到 `chat_id` 的根因
- 将 active relay state 从 `chat_id` 绑定修正为 Hermes `session_id`
- 保证 `/reset` 或新会话后不会继续误命中旧 coding mode

完成标准：

- `coding_relay` 可用 `task_id/session_id` 成功进入 coding mode
- gateway hook 按当前 `session_id` 判断是否命中 relay
- 同一 `session_key` 下旧 `session_id` 的内存态会被清理
- 单测覆盖新绑定键和旧会话清理逻辑

实现备注：

- 已完成：`relay_context.py` 新增 `session_id/session_key` 提取逻辑，并兼容 Hermes 运行环境变量
- 已完成：`coding_relay` 改为以 `task_id/session_id` 建立 relay，不再依赖 `chat_id`
- 已完成：`pre_gateway_dispatch` 通过 `session_store` 解析当前 `session_id/session_key`，并在会话轮换时清理旧 active relay state
- 已完成：补充单测覆盖 `session_id` 绑定和同 `session_key` 下旧状态清理

下一步：

- 继续飞书端到端测试，验证 Hermes 真实 tool 调用路径现在可以成功进入 coding mode，并确认 `/reset` 后旧 relay 不再命中

---

## T012 编码委托指令与 workdir 初始化

状态：done

目标：

- 让 Hermes 自动将编码类任务委托给 `coding_relay`，而不是使用内置的 `write_file` / `run_command`
- 修复 Codex CLI 在无 git 仓库或不存在目录下启动失败的问题

完成标准：

- Hermes 遇到文件操作、代码编写、命令执行类任务时自动调用 `coding_relay`
- `coding_relay` 能在目录不存在时自动创建并 `git init`
- Codex CLI 命令默认带 `--skip-git-repo-check`
- 有独立单测覆盖命令构造、workdir 初始化

实现备注：

- 已完成：新增 `skill/SKILL.md`，通过 `skills.external_dirs` 注册到 Hermes system prompt 索引
- 已完成：强化 `TOOL_SCHEMA` description，明确声明编码任务必须走 `coding_relay`
- 已完成：`agent_spawner.py` 的 `build_codex_command` 默认加 `--skip-git-repo-check`
- 已完成：`relay_runtime.py` 新增 `ensure_workdir_ready`，自动 mkdir + git init
- 已完成：`handoff_tool.py` 在 `validate_workdir` 后调用 `ensure_workdir_ready`
- 已完成：更新已有测试适配新命令格式，新增 `ensure_workdir_ready` 单测
- 已完成：`~/.hermes/config.yaml` 的 `skills.external_dirs` 加入 skill 路径

未完成内容：

- 飞书端到端验证：确认 Hermes 收到编码请求时自动调用 `coding_relay` 而非内置工具
- 需要观察 Hermes 是否会因为 error 信息过于具体而自行修复（绕过 relay）

下一步：

- 重启 gateway 并进行飞书端到端测试

---

## T011 OpenCode 支持里程碑

状态：todo

说明：

- 这是 `opencode` 接入的总计划，不直接作为单一步骤执行
- 后续严格按子任务顺序推进，一次只做一个子任务
- 先调研边界，再做适配，最后做接线和测试

下一步：

- 先做 T011A，确认 `opencode` 的 CLI、resume 语义、事件格式和退出行为

---

## T011A OpenCode 调研与接入边界

状态：todo

目标：

- 确认 `opencode` 的启动命令、resume 方式、事件输出格式和退出语义
- 明确它与 Codex 在会话恢复、事件流和错误模型上的差异
- 产出最小接入边界，不改主链路

完成标准：

- 有一份清晰的 `opencode` 接入边界说明
- 明确哪些能力可直接复用现有层，哪些需要新适配
- 明确是否需要独立的恢复标识、事件类型映射或错误转换

实现备注：

- 先调研，不写实现代码
- 如果 `opencode` 的行为和 Codex 差异很大，优先记录分歧点，再决定适配拆分

下一步：

- 进入 T011B，实现 `opencode` 的 transport 和事件适配

---

## T011B OpenCode transport 与事件适配

状态：todo

目标：

- 实现 `opencode` 的 spawn / resume
- 把 `opencode` 原始事件接到内部事件适配层
- 保持与现有 Codex 适配逻辑分离

完成标准：

- `opencode` 可以新建会话并恢复会话
- 能把 `opencode` 事件转换成内部事件
- 坏行、非零退出和 spawn 失败有独立处理
- 有独立单测覆盖 transport 和事件映射

实现备注：

- 先做最小可用的 transport 封装
- 不把 `opencode` 特有差异硬塞进 Codex 适配器

下一步：

- 进入 T011C，实现 relay 接线、模式选择和测试收口

---

## T011C OpenCode relay 接线与测试

状态：todo

目标：

- 在 handoff 和 gateway 接线中支持选择 `opencode`
- 让运行态、格式化和错误反馈继续走现有分层
- 补齐文档和测试收口

完成标准：

- `coding_relay` 可显式选择 `opencode`
- `pre_gateway_dispatch` 能按 active relay state 转发到对应后端
- `opencode` 的启动、恢复、事件解析和错误反馈均有独立测试
- `DESIGN.md`、`docs/DECISIONS.md`、`docs/TASKS.md` 同步写实差异和约束

实现备注：

- 接线时优先复用现有状态管理和输出格式化
- 不把 `opencode` 支持扩展成通用多 agent 平台

下一步：

- 等 T011A 和 T011B 完成后，再做 T011C

---

## T013 端到端联调修复

状态：done

目标：

- 修复飞书端到端测试中发现的三个问题
- 让 coding-relay 真正可用

完成标准：

- Codex 以正确的 workdir（配置根下的项目子目录，不是根本身）启动
- hook 拦截后续消息后，Codex 的输出按事件顺序完整、可读地发送回用户
- 命令执行细节以简洁进度消息外显，不再只输出最终结论

实现备注：

已完成：
- 修复 hook import bug（相对导入）
- workdir 根改为插件级配置 `plugins.coding-relay.workdir_root`
- `validate_workdir` 仍拒绝根本身，只允许具体子目录
- tool schema description 按配置动态生成
- hook 改为按事件顺序流式发送，turn 结束补一条完成消息
- `output_formatter` 恢复命令开始/完成消息，并保持事件顺序
- `skill/SKILL.md` 同步更新 workdir 配置根和输出约束
- SKILL.md 新增 handoff 前后回复规范
- 文档补充 `codex exec` 不支持斜杠命令的已知限制

待修复（P1）：
- 无

已知限制：
- `codex exec` 不支持斜杠命令（/status 等），已文档化

详细分析见 `docs/E2E-TEST-ANALYSIS-2026-05-11.md`

下一步：

- 跑完整测试套件确认无回归

---

## T014 tool 命名统一为 `coding_relay`

状态：done

目标：

- 将 Hermes 对外暴露的 tool 名从 `coding_handoff` 统一为 `coding_relay`
- 同步更新 skill、插件注册、文档和测试，消除命名歧义

完成标准：

- `register(ctx)` 注册的 tool 名为 `coding_relay`
- skill 和文档统一指向 `coding_relay`
- 相关测试全部通过

实现备注：

- 已完成：`plugin.yaml`、`register(ctx)` 和 tool schema 统一改为 `coding_relay`
- 已完成：`skill/SKILL.md`、`README.md`、`DESIGN.md`、`docs/ARCHITECTURE.md`、`docs/DECISIONS.md`、`docs/TASKS.md` 同步改名
- 已完成：保留 `handoff_tool.py` 中的 `coding_handoff = coding_relay` 兼容别名，避免直接导入旧符号的代码立即断裂
- 已完成：更新相关单测并通过完整测试套件

下一步：

- 做一次飞书端到端验证，确认 Hermes 在真实对话里优先使用 `coding_relay`

---

## T015 首轮 relay 输出归一化与飞书格式优化

状态：done

目标：

- 让 `coding_relay` 的首轮 Codex 输出和后续 turn 走同一条 relay 发送链路
- 避免 Hermes 在 tool 成功返回后重复转述首轮正文
- 将命令、文件、错误和完成提示统一成更适合飞书的轻量 Markdown 样式

完成标准：

- handoff 时具备 gateway/source 上下文时，首轮 Codex 内容由 relay 直接发送给用户
- `initial_messages` 不再是首轮正文的默认展示出口
- `agent_text` 保留原始 Markdown 段落和代码块，不被压平成单行
- 命令进度、文件变更、错误和完成提示采用统一模板
- `skill/SKILL.md`、`DESIGN.md`、`docs/DECISIONS.md`、相关测试同步更新

实现备注：

- 已完成：新增 `relay_delivery.py`，抽取首轮 handoff 和后续 turn 共用的发送、串行流式输出和完成消息逻辑
- 已完成：`handoff_tool.py` 在有 gateway/source 上下文时直接复用 relay 发送链路；无上下文时保留 `initial_messages` 兼容路径
- 已完成：`gateway_hook.py` 复用同一发送辅助层，避免首轮和后续 turn 走两套独立实现
- 已完成：`output_formatter.py` 改为轻量 Markdown 模板，命令/文件/错误/完成提示统一风格，并保留 `agent_text` 原始 Markdown 结构
- 已完成：`skill/SKILL.md` 更新为“调用前展示完整 prompt/workdir，调用后不复述首轮正文”
- 已完成：补充和更新单测，覆盖首轮直发、格式化模板和 Markdown 保真

未完成内容：

- 真实飞书端到端验证仍需在外部平台确认，不由当前单测替代

下一步：

- 做一次真实飞书验证，确认 Hermes 调 tool 前的提示、首轮 relay 直发和后续 turn 输出都符合预期

---

## T016 README 状态与平台支持说明收口

状态：done

目标：

- 让 `README.md` 与当前仓库真实实现保持一致
- 明确当前已验证的 gateway 平台边界，避免读者误以为已经做过多平台支持

完成标准：

- README 不再保留早期“尚未实现”的过时状态描述
- README 明确当前实现聚焦 Codex-first relay
- README 明确当前只有飞书 gateway 做过真实联调验证，其他平台尚未承诺

实现备注：

- 已完成：重写 README 的状态、能力边界、仓库布局和开发说明
- 已完成：补充“代码路径按 platform adapter 工作，但当前只有飞书做过真实验证”的说明
- 已完成：同步更新当前可用能力与已知限制，避免继续误导读者

未完成内容：

- 其他 gateway 平台仍未做真实端到端验证

下一步：

- 若后续接入并验证其他平台，再扩充 README 的平台支持矩阵

---

## T017 resume 语义收紧到显式用户意图

状态：done

目标：

- 明确 `coding_relay` 的历史会话恢复只能发生在用户明确要求 resume 的场景
- 避免 Hermes 仅凭 `workdir`、`summary` 或“像是在继续”的模糊语义擅自复用旧 `codex_thread_id`

完成标准：

- `skill/SKILL.md` 明确区分“当前 coding mode 内继续对话”和“重新 handoff 时恢复历史 session”
- `skill/SKILL.md` 明确要求：只有用户明确说继续上次、恢复上次或 resume 历史会话时，才允许传 `codex_thread_id`
- `skill/SKILL.md` 明确要求：其他情况默认新建 session，不允许隐式选择 `sessions.json` 里的旧记录

实现备注：

- 已完成：收紧 skill 中对 `codex_thread_id` 的使用说明
- 已完成：修正“上次做到哪了”示例，避免它继续暗示默认 resume
- 本轮只改 skill 和任务记录，不改代码路径

未完成内容：

- 代码层仍未实现基于 `sessions.json` 的历史会话搜索；当前只有显式传入 `codex_thread_id` 才会 resume

下一步：

- 真实飞书验证时，确认 Hermes 在未明确收到 resume 指令时不会构造 `codex_thread_id`

---

## T018 显式 resume 的历史会话提示

状态：done

目标：

- 当 `coding_relay` 被显式传入 `codex_thread_id` 做 resume 时，向用户展示一条简洁的历史会话恢复提示
- 使用 `sessions.json` 中的结构化记录告诉用户“上次做到哪了”，而不是倒最后几条原始消息

完成标准：

- 仅在显式 resume handoff 场景下输出恢复提示
- 提示优先包含 `workdir`、`last_active_at`、`summary`、`last_files`
- 若找不到历史记录，退化为最小恢复提示，不阻塞 handoff
- 补充单测覆盖有记录和无记录的 resume 提示路径

实现备注：

- 本任务不做 `sessions.json` 搜索逻辑，只消费已显式传入的 `codex_thread_id`
- 已完成：显式传入 `codex_thread_id` 时，handoff 会先生成“已恢复历史会话”提示
- 已完成：提示优先展示 `workdir`、`last_active_at`、`summary`、`last_files`
- 已完成：有 gateway/source 上下文时提示由 relay 直发；无上下文时提示进入 `initial_messages`
- 已完成：补充单测覆盖 resume 提示的 gateway 和非 gateway 路径

下一步：

- 做一次真实飞书验证，确认 resume 提示和后续 Codex 输出顺序符合预期

---

## T019 命令可见性配置分档

状态：done

目标：

- 将命令执行消息做成插件级可配置行为，而不是固定全量外显
- 默认降低噪音，同时保留联调和排障时查看完整命令过程的能力

完成标准：

- 新增插件配置 `plugins.coding-relay.command_visibility`
- 支持三档：`none`、`filtered`、`all`
- 默认值为 `none`
- `filtered` 仅显示高价值成功命令和所有失败命令
- `all` 显示命令开始和命令完成
- 补充单测覆盖三档行为

实现备注：

- 已完成：新增 `relay_config.get_command_visibility()`，从插件配置读取命令可见性
- 已完成：`output_formatter.py` 支持按 `none` / `filtered` / `all` 过滤 `command_started` / `command_finished`
- 已完成：默认 `none` 仅隐藏成功命令；失败命令仍显示
- 已完成：`filtered` 通过规则识别测试、静态检查和构建类高价值命令，不使用 AI
- 已完成：`handoff_tool.py` 与 `relay_delivery.py` 在首轮和后续 turn 路径统一应用该配置
- 已完成：补充单测覆盖默认静默、过滤显示和全显示

未完成内容：

- 暂未将高价值命令规则做成独立可配置列表；当前仍是内置规则集

下一步：

- 做一次真实飞书验证，确认 `none` / `filtered` / `all` 在实际消息体验上的噪音差异符合预期

---

## T020 飞书 relay 上下文诊断日志

状态：done

目标：

- 为 handoff 和 `pre_gateway_dispatch` 补最小、非敏感的诊断日志
- 在真实飞书端到端里确认到底走了直发路径还是无发送 fallback 路径

完成标准：

- handoff 路径记录是否拿到 `gateway`、`event`、`source`、adapter 和 resume 标记
- hook 路径记录是否命中 active relay、是否具备可发送上下文、最终走了哪条分支
- 日志不记录完整 prompt、用户原文、token、密钥等敏感内容

实现备注：

- 本任务只加诊断日志，不修改分支行为
- 已完成：handoff 路径记录 `gateway/event/source/adapter` 是否存在，以及 streamed/fallback 分支选择
- 已完成：`pre_gateway_dispatch` 记录 active relay 命中、可发送上下文和 streamed/fallback/busy 分支选择
- 已完成：`stream_turn_sync` 记录开始、fallback 格式化和结束统计
- 已完成：日志不记录 prompt、用户原文或其他敏感内容

下一步：

- 跑一轮真实飞书测试，对照日志确认上下文缺口

---

## T021 resume 来源约束到 coding-relay session store

状态：done

目标：

- 明确 Hermes 在显式 resume 场景下只能使用 coding-relay 自己维护的 `run/sessions.json`
- 避免 Hermes 自行搜索 `~/.codex`、sqlite、session_search 或其他非 relay 会话源

完成标准：

- `skill/SKILL.md` 明确写死 resume 的唯一候选来源是 coding-relay 的 session store
- `skill/SKILL.md` 明确禁止 Hermes 自行搜索 Codex 本地目录、数据库或其他历史来源
- `skill/SKILL.md` 示例与规则保持一致

实现备注：

- 已完成：补充 resume 来源约束，限定为 coding-relay 自己的 `run/sessions.json`
- 已完成：明确禁止使用 `~/.codex`、sqlite、session_search 等路径自行猜测 thread id
- 本轮只改 skill 和任务记录，不改代码

未完成内容：

- 代码层尚未提供“按 workdir 从 session store 选候选 thread”的专门工具接口；当前仍依赖 Hermes 按 skill 约束读取 relay 记录

下一步：

- 重新部署插件并重启 gateway，再做一轮飞书测试验证 Hermes 是否停止搜索外部 Codex 会话源

---

## T022 修复飞书 relay adapter 查找回归

状态：done

目标：

- 修复 `relay_delivery` 在真实 Hermes gateway 中查找平台 adapter 失败的问题
- 恢复 coding mode 后续消息和 `/relay-back` 的飞书回发能力

完成标准：

- follow-up turn 在 `source.platform` 为 Hermes `Platform` 枚举时，仍能正确命中 `gateway.adapters`
- `/relay-back` 在 relay mode 中能通过同一发送链路正常回发退出提示
- 补测试覆盖 Hermes 实际的枚举 key 形状，避免再次回归

实现备注：

- 根因：诊断阶段把 adapter lookup 从原始 `source.platform` 错改成了字符串归一化值，和 Hermes `gateway.adapters` 的枚举 key 不匹配
- 已完成：发送链路拆分“adapter lookup key”和“日志展示 platform label”
- 已完成：adapter 查找恢复使用原始平台对象；日志继续输出可读字符串
- 已完成：补充 handoff 和 hook 的枚举平台测试，覆盖真实 Hermes 形状

下一步：

- 重启 gateway 后重新做飞书端到端验证，确认 follow-up turn 和 `/relay-back` 恢复正常

---

## T024 清理飞书联调临时诊断日志

状态：done

目标：

- 清理仅用于定位问题的 relay `info` 级诊断日志
- 保留功能修复和真实发送失败的 `warning`

完成标准：

- `gateway_hook.py` 不再保留联调期的 active/fallback/busy/streaming 诊断日志
- `handoff_tool.py` 不再保留首轮 handoff 的上下文诊断日志
- `relay_delivery.py` 不再保留 `stream_turn_sync` 的开始/结束/fallback 统计日志
- adapter 查找修复和发送失败告警保持不变

实现备注：

- 已完成：移除 `handoff_tool.py` 中仅用于联调的首轮 handoff 诊断日志
- 已完成：移除 `gateway_hook.py` 中仅用于联调的 `coding-relay.hook` 诊断日志
- 已完成：移除 `relay_delivery.py` 中仅用于联调的 `stream_turn_sync` 诊断日志
- 已完成：保留 `cannot send relay response: ...` 这类真实运行失败告警

下一步：

- 继续飞书端到端验证，确认日志降噪后行为不回退

---

## T023 历史会话查询工具与 resume_token 收口

状态：done

目标：

- 提供不进入 coding mode 的历史会话查询工具，避免 Hermes 自行搜索 `run/sessions.json`
- 将对外 resume 参数从 `codex_thread_id` 收口为 provider-neutral 的 `resume_token`
- 保持当前 Codex 实现兼容旧字段，同时把 resume 决策流程迁移到“先查候选，再由用户确认”

完成标准：

- 新增独立工具用于按 `workdir` 列出历史 relay 会话候选
- `coding_relay` 对外支持 `resume_token`，并兼容旧 `codex_thread_id`
- `skill/SKILL.md` 明确：显式 resume 先调查询工具，再根据用户确认调用 `coding_relay`
- 补充单测覆盖历史会话查询、`resume_token` 恢复和旧字段兼容

实现备注：

- 第一版只做 Codex 后端；不为多 provider 提前做运行时重构
- 不新增本地伪造统一 session id；继续使用 provider 原生恢复标识
- 查询工具只消费 relay 自己的 session store，不暴露底层文件路径给 Hermes

实现备注：

- 已完成：新增 `list_relay_sessions` 工具，按 `workdir` 返回历史 relay 会话候选且不进入 coding mode
- 已完成：`session_store.py` 输出和查询统一补充 `provider` / `resume_token` 归一化字段，并兼容旧 `codex_thread_id`
- 已完成：`coding_relay` 对外支持 `resume_token`，同时保留 `codex_thread_id` 兼容别名
- 已完成：更新 `skill/SKILL.md`，显式 resume 改为先调 `list_relay_sessions`，再由用户确认后调用 `coding_relay`
- 已完成：更新 `DESIGN.md`、`docs/DECISIONS.md`、`docs/ARCHITECTURE.md`，写实新的查询工具和恢复标识命名
- 已完成：补充单测覆盖历史会话查询、`resume_token` 恢复和旧字段兼容

未完成内容：

- 真实飞书端到端尚未验证“列候选 -> 用户选择 -> 第二次 handoff resume”整条交互
- 当前内部 runtime 和事件层仍保留 `codex_thread_id` 命名；本轮只收口对外接口和 session store 口径

下一步：

- 做一次真实飞书验证，确认 Hermes 会先调用 `list_relay_sessions`，再根据用户确认使用 `resume_token` 进入 relay
