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

状态：todo

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

下一步：

- 进入 T007，补测试和文档收口
