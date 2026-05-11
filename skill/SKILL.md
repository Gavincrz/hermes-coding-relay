---
name: coding-relay
description: "编码任务委托规则：所有涉及文件操作、代码编写、命令执行的任务必须通过 coding_relay 工具委托给 Codex，禁止 Hermes 直接操作。"
version: 1.0.0
author: coding-relay plugin
metadata:
  hermes:
    tags: [coding, delegation, codex, relay, file-operations, shell-commands]
    conditions:
      requires_tools:
        - coding_relay
---

# 编码任务委托规则

本 skill 定义了 Hermes 何时以及如何将编码任务委托给 Codex CLI。

## 核心规则

**所有涉及文件操作、代码编写或命令执行的任务，必须调用 `coding_relay` 工具，禁止使用 Hermes 内置的 `write_file`、`run_command`、`edit_file` 等工具直接操作。**

这条规则的目的是：
- 编码工作由专业的编码 agent（Codex）完成，Hermes 负责对话和协调
- 编码过程中的所有文件变更和命令执行都在可控的沙盒内完成
- 用户可以通过 `/relay-back` 随时切回 Hermes 对话模式

## 必须委托的场景

以下场景必须调用 `coding_relay`：

1. **文件创建、编辑、删除**
   - 创建新文件（任何语言、任何类型）
   - 修改已有文件内容
   - 删除文件
   - 重命名或移动文件

2. **代码编写与修改**
   - 实现新功能
   - 修复 bug
   - 重构代码
   - 添加测试
   - 修改配置文件

3. **命令执行**
   - 运行测试
   - 执行构建
   - 安装依赖
   - 启动/停止服务
   - Git 操作（commit、push、pull 等）
   - 任何需要在项目目录下执行的 shell 命令

4. **项目级操作**
   - 初始化项目结构
   - 生成脚手架
   - 批量文件操作
   - 代码审查（需要读取和分析代码的）

## 不需要委托的场景

以下场景 Hermes 应直接回答，不调用 `coding_relay`：

1. **纯知识问答**
   - 解释概念（"什么是 REST API？"）
   - 架构讨论（"微服务 vs 单体怎么选？"）
   - 技术选型建议

2. **信息检索**
   - 搜索文档或资料
   - 查询 API 文档

3. **简单文本处理**
   - 翻译
   - 摘要
   - 格式转换（不涉及文件的）

4. **日常对话**
   - 闲聊
   - 确认理解用户意图
   - 澄清需求（但确认后如果涉及编码，则需要委托）

## 如何调用 coding_relay

### 基本参数

| 参数 | 说明 |
|------|------|
| `agent` | 固定填 `"codex"` |
| `prompt` | 组装好的任务描述，包含完整的上下文和意图 |
| `workdir` | 工作目录绝对路径，必须是配置根 `plugins.coding-relay.workdir_root` 下的具体项目子目录，不能直接传配置根本身 |
| `codex_thread_id` | 可选，如需恢复之前的 Codex 会话则传入 |

### prompt 组装原则

`prompt` 应该是一段自包含的任务描述，让 Codex 能独立理解并执行：

- **包含用户意图**：把用户真正想做的事说清楚
- **包含必要上下文**：相关文件路径、已有代码结构、约束条件
- **包含具体指令**：期望 Codex 做什么、产出什么
- **不要包含 Hermes 内部状态**：session_id、tool 调用链路等

### 示例

**用户说**：帮我在 ~/projects/my-app 里写一个 Python 的 hello world

**你应该调用**：
```json
{
  "agent": "codex",
  "prompt": "在当前目录下创建 hello.py，内容为一个完整的 Python Hello World 程序，要求有 if __name__ == '__main__' 入口。",
  "workdir": "/home/dontstarve/projects/my-app"
}
```

**用户说**：这个项目跑一下测试看看有没有问题

**你应该调用**：
```json
{
  "agent": "codex",
  "prompt": "运行项目的测试套件，报告测试结果。如果有失败，分析失败原因。",
  "workdir": "/home/dontstarve/projects/my-app"
}
```

**用户说**：上次做到哪了？

**你应该调用**：
```json
{
  "agent": "codex",
  "prompt": "查看项目当前状态，列出最近修改的文件和未完成的工作。",
  "workdir": "/home/dontstarve/projects/my-app",
  "codex_thread_id": "<上次返回的 thread_id>"
}
```

**用户说**：什么是设计模式里的工厂模式？

**你应该直接回答**，不调用 `coding_relay`。

**用户说**：帮我在这个项目里用工厂模式重构一下创建对象的代码

**你应该调用**：
```json
{
  "agent": "codex",
  "prompt": "重构项目中的对象创建代码，使用工厂模式。先找到直接 new 对象的地方，然后提取工厂类。",
  "workdir": "/home/dontstarve/projects/my-app"
}
```

### workdir 精确性要求

- `workdir` 必须指向实际项目目录，不能只传父目录
- `workdir` 需要能直接对应 Codex 要操作的仓库根
- `workdir` 必须位于插件配置读取到的 `workdir_root` 之下
- 如果用户只说“某个项目根”但没有给出具体子目录，需要追问或根据上下文补成具体子目录
- 在当前版本里，配置根本身不是合法 `workdir`

## 调用 coding_relay 时的回复规范

调用 `coding_relay` **之前**，你必须先回复用户，告知即将转交：

1. 说明即将把任务转交给 Codex
2. 展示你要传给 `coding_relay` 的 `prompt` 内容（原文展示，让用户确认意图是否准确）
3. 展示使用的 `workdir`

调用 `coding_relay` **之后**，根据返回结果回复用户：

- **成功（status=handed_off）**：直接展示 `initial_messages` 字段的内容，这是 Codex 的原始输出。不要总结、不要改写、不要加评论。在展示完 Codex 输出后，附上固定提示：
  - Codex 输出会按事件顺序流式生成，可能包含 `agent_text`、简洁的命令开始/完成提示、文件变更摘要和错误信息。
  > 🔄 已进入 coding-relay 模式。后续消息直接发给 Codex，发送 `/relay-back` 回来找 Hermes，发送 `/relay-mode` 查看/切换执行模式。
- **失败（status=error）**：展示 `messages` 和 `errors`，说明转交失败的原因。
- **拒绝（status=rejected）**：说明被拒绝的原因（如 workdir 不合法），并建议用户修正后重试。

**绝对不要**把 Codex 的输出拿来做二次总结或解读。用户要的是 Codex 的原始结果。

## 进入 Coding Mode 后的行为

`coding_relay` 返回成功后，当前会话进入 coding mode：

- 后续用户消息会自动转发给 Codex，不需要 Hermes 介入
- 用户发送 `/relay-back` 退出 coding mode，回到 Hermes 对话
- 用户发送 `/relay-mode` 查看/切换执行模式（safe/readonly/yolo）
- Hermes 不需要在 coding mode 期间做任何事情

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| `unsupported_agent` | agent 不是 `codex` | 确保传 `"codex"` |
| `invalid_workdir` | workdir 不在配置根下，或者就是配置根本身 | 使用具体的项目子目录路径 |
| `spawn_failed` | Codex CLI 未安装或启动失败 | 告知用户检查 Codex CLI 是否已安装 |

## 已知限制

- `codex exec` 不支持斜杠命令（例如 `/status`）
- 这类命令不会像 Codex 交互模式那样被执行
- 如果需要查看 relay 状态，应走 relay 自己的状态命令或文档化替代路径

## 确认清单

在回复用户之前，问自己：

1. 这个任务涉及创建、编辑或删除文件吗？→ 委托
2. 这个任务涉及在项目目录下执行命令吗？→ 委托
3. 这个任务涉及编写或修改代码吗？→ 委托
4. 以上都不是，只是纯对话或知识问答？→ 直接回答
