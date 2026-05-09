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
- 注册 `coding_handoff`、`pre_gateway_dispatch`、`/back`

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

- `AGENT.md` 明确代码健康、复用优先和小步重构规则
- `project-bootstrap` skill 明确要求初始化阶段写入这些规则
- skill 模板包含可复用的默认表述

实现备注：

- 已完成：在 `AGENT.md` 增加代码健康、复用优先、重构触发条件和测试安全网规则
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
- `/back` 可退出 coding mode

完成标准：

- `coding_handoff` 后 chat 进入 active relay state
- `pre_gateway_dispatch` 在 coding mode 下拦截普通消息
- `/back` 能清理 active state，并在有活跃进程时停止它

实现备注：

- 只处理单 chat 单 active Codex 会话
- 不做复杂并发调度
- 已完成：新增 `relay_runtime.py`，集中管理 active relay state、workdir 校验、单轮 Codex turn 执行与退出清理
- 已完成：`coding_handoff` 进入 active relay state，并立即发起首轮 Codex turn
- 已完成：`pre_gateway_dispatch` 在 coding mode 下拦截普通消息并通过 `resume` 语义继续会话，返回 `action=skip`
- 已完成：`/back` 和 hook 内 `/back` 都会清理 active state，并在有活跃进程时停止它
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
- 已完成：在 `coding_handoff` 首轮和 coding mode 后续 turn 后更新 `created_at`、`last_active_at`、`last_files`
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
- 已完成：`coding_handoff` 与 `pre_gateway_dispatch` 改为返回格式化后的平台输出，同时保留原始错误数据
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
- 已完成：更新 `DESIGN.md`，补充 `coding_handoff` 返回口径、错误覆盖范围和格式化降级策略
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
- `coding_handoff` 支持显式执行模式参数，至少包含 `yolo` 开关
- 单测覆盖命令构造和参数校验
- 文档明确说明当前不桥接 Codex 自身的交互式 approval 事件到飞书

实现备注：

- 第一版优先保证可靠 relay，不扩展成完整的人机协商代理
- 若 Codex `exec --json` 未暴露稳定 approval 事件，则保留 `never` / `yolo` 两种无交互模式
- 已完成：`agent_spawner.py` 默认改为 `workspace-write + -a never`，并支持显式 `yolo`
- 已完成：`coding_handoff` 支持 `sandbox_mode` / `yolo` 参数校验与回显
- 已完成：新增会话级 `/relay-mode [status|safe|readonly|yolo]` 控制，并保留 `/relay-back`
- 已完成：coding mode 下除 relay 保留命令外，其余 slash 文本继续原样转给 Codex
- 已完成：补充单测覆盖命令构造、模式切换、保留命令和 slash 透传
- 已完成：设计、架构和决策文档同步写实 approval 边界与命令命名空间

下一步：

- 进入后续任务，评估是否需要单独做 Codex 交互事件桥接
