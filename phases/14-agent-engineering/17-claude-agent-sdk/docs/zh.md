# Claude Agent SDK：子 Agent 与会话存储

> Claude Agent SDK 是 Claude Code 框架的库形式。内置工具、用于上下文隔离的子 Agent、钩子、W3C trace 传播、会话存储等价。Claude Managed Agents 是用于长时异步工作的托管替代方案。

**类型：** Learn + Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 10（Skill Libraries）
**时间：** ~75 分钟

## 学习目标

- 解释 Anthropic Client SDK（原始 API）和 Claude Agent SDK（框架形状）之间的区别。
- 描述子 Agent —— 并行化和上下文隔离 —— 以及何时使用它们。
- 说出 Python SDK 的会话存储接口（`append`、`load`、`list_sessions`、`delete`、`list_subkeys`）和 `--session-mirror` 的角色。
- 用标准库实现一个带内置工具、带隔离上下文的子 Agent 生成、生命周期钩子和会话存储的框架。

## 问题

一个原始 LLM API 只能给你一次往返。一个生产 Agent 需要工具执行、MCP 服务器、生命周期钩子、子 Agent 生成、会话持久化、trace 传播。Claude Agent SDK 以库的形式提供了这个形状 —— Claude Code 使用的同一个框架，为自定义 Agent 暴露出来。

## 核心概念

### Client SDK vs Agent SDK

- **Client SDK（`anthropic`）。** 原始 Messages API。你拥有循环、工具、状态。
- **Agent SDK（`claude-agent-sdk`）。** 内置工具执行、MCP 连接、钩子、子 Agent 生成、会话存储。Claude Code 的循环作为库。

### 内置工具

SDK 开箱即用提供 10+ 工具：文件读写、shell、grep、glob、Web 抓取等。自定义工具通过标准工具 schema 接口注册。

### 子 Agent

Anthropic 文档化的两个用途：

1. **并行化。** 并发运行独立工作。"为这 20 个模块中的每一个找到测试文件"是 20 个并行子 Agent 任务。
2. **上下文隔离。** 子 Agent 使用自己的上下文窗口；只有结果返回给编排器。编排器的预算得到保留。

Python SDK 近期新增：`list_subagents()`、`get_subagent_messages()` 用于读取子 Agent 转录。

### 会话存储

与 TypeScript 的协议等价：

- `append(session_id, message)` — 添加一轮。
- `load(session_id)` — 恢复对话。
- `list_sessions()` — 枚举。
- `delete(session_id)` — 级联到子 Agent 会话。
- `list_subkeys(session_id)` — 列出子 Agent 键。

`--session-mirror`（CLI 标志）在流式传输时将转录镜像到外部文件，用于调试。

### 钩子

可注册的生命周期钩子：

- `PreToolUse`、`PostToolUse` — 门控或审计工具调用。
- `SessionStart`、`SessionEnd` — 设置和拆卸。
- `UserPromptSubmit` — 在模型看到用户输入之前对其操作。
- `PreCompact` — 在上下文压缩之前运行。
- `Stop` — Agent 退出时清理。
- `Notification` — 侧通道告警。

钩子是 pro-workflow（Phase 14 课程参考）和类似系统添加横切行为的方式。

### W3C trace context

调用者上活跃的 OTel span 通过 W3C trace context 头传播到 CLI 子进程中。整个多进程 trace 在你的后端中显示为一个 trace。

### Claude Managed Agents

托管替代方案（beta header `managed-agents-2026-04-01`）。长时异步工作、内置提示缓存、内置压缩。用控制换取托管基础设施。

### 这个模式出错的地方

- **子 Agent 过度生成。** 为 100 个小任务生成 100 个子 Agent。开销占主导。改为批量处理。
- **钩子蔓延。** 每个团队都添加钩子；启动时间膨胀。每季度审查钩子。
- **会话膨胀。** 会话不断积累；大小增长。使用 `list_sessions` + 过期策略。

## 构建它

`code/main.py` 用标准库实现了 SDK 形状：

- `Tool`、`ToolRegistry` 带内置 `read_file`、`write_file`、`list_dir`。
- `Subagent` — 私有上下文、隔离运行、结果返回。
- `SessionStore` — append、load、list、delete、list_subkeys。
- `Hooks` — `pre_tool_use`、`post_tool_use`、`session_start`、`session_end`。
- 演示：主 Agent 并行生成 3 个子 Agent（各自隔离），聚合结果，持久化会话。

运行它：

```
python3 code/main.py
```

轨迹展示了子 Agent 上下文隔离（编排器上下文大小保持有界）、钩子执行和会话持久化。

## 使用它

- **Claude Agent SDK** 用于想要 Claude Code 框架形状的 Claude 优先产品。
- **Claude Managed Agents** 用于托管的长时异步工作。
- **OpenAI Agents SDK**（第 16 课）用于 OpenAI 优先的对应物。
- **LangGraph + 自定义工具** 如果你想要图形状的状态机。

## 发布它

`outputs/skill-claude-agent-scaffold.md` 脚手架一个 Claude Agent SDK 应用，带子 Agent、钩子、会话存储、MCP 服务器附加和 W3C trace 传播。

## 练习

1. 添加一个子 Agent 生成器，将 20 个任务批量分成 5 个并行子 Agent 的组。衡量编排器上下文大小与每任务一个的对比。
2. 实现一个 `PreToolUse` 钩子，对 `write_file` 调用进行速率限制（每会话每分钟 5 次）。追踪行为。
3. 将 `list_subkeys` 接线到渲染子 Agent 树。深层嵌套是什么样的？
4. 将玩具代码移植到真实的 `claude-agent-sdk` Python 包。工具有什么注册变化？
5. 阅读 Claude Managed Agents 文档。何时从自托管切换到托管？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Agent SDK | "Claude Code 即库" | 框架形状：工具、MCP、钩子、子 Agent、会话存储 |
| Subagent | "子 Agent" | 独立上下文、自有预算；结果向上冒泡 |
| Session store | "对话数据库" | 持久化、加载、列出、删除轮次，带子 Agent 级联 |
| Hook | "生命周期回调" | 工具前后、会话、提示提交、压缩、停止 |
| W3C trace context | "跨进程 trace" | 父 span 传播到 CLI 子进程 |
| Managed Agents | "托管框架" | Anthropic 托管的长时异步工作 |
| `--session-mirror` | "转录镜像" | 流式传输时将会话轮次写入外部文件 |
| MCP server | "工具接口" | 附加到 Agent 的外部工具/资源源 |

## 延伸阅读

- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) — Claude Code 的库形式
- [Anthropic, Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) — 生产模式
- [Claude Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview) — 托管替代方案
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) — 对应物