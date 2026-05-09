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

## T003 内部事件适配层

状态：todo

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

下一步：

- 进入 T004，实现 gateway coding mode 接管

---

## T004 Coding Mode 接管

状态：todo

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

下一步：

- 进入 T005，实现持久化 session 与 summary

---

## T005 会话持久化与规则摘要

状态：todo

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
