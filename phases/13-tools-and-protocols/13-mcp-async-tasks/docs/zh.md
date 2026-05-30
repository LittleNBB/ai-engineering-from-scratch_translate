# 异步任务（SEP-1686） — 先调用、后获取的长时间运行工作

> 真正的 Agent 工作需要几分钟到几小时：CI 运行、深度研究综合、批量导出。同步工具调用会断开连接、超时或阻塞 UI。SEP-1686 于 2025-11-25 合并，添加了 Tasks 原语：任何请求都可以被增强为任务，结果可以稍后获取或通过状态通知流式传输。漂移风险提示：Tasks 在 2026 年上半年仍是实验性的；SDK 接口仍在围绕规范设计中。

**类型：** Build
**语言：** Python（stdlib，异步任务状态机）
**前置课程：** Phase 13 · 07（MCP 服务器）、Phase 13 · 09（传输层）
**时间：** ~75 分钟

## 学习目标

- 识别何时应将工具从同步提升为任务增强（服务端工作超过 30 秒）。
- 走完任务生命周期：`working` → `input_required` → `completed` / `failed` / `cancelled`。
- 持久化任务状态，使崩溃不会丢失进行中的工作。
- 正确轮询 `tasks/status` 并获取 `tasks/result`。

## 问题

一个 `generate_report` 工具运行一个需要多分钟的提取管道。同步模型下的选项：

1. 保持连接打开三分钟。远程传输层会断开；客户端超时；UI 冻结。
2. 立即返回一个占位符；要求客户端轮询自定义端点。破坏了 MCP 的一致性。
3. 发射后不管；没有结果。

没有一个是好的。SEP-1686 添加了第四种：任务增强。任何请求（通常是 `tools/call`）都可以被标记为任务。服务器立即返回一个任务 id。客户端轮询 `tasks/status`，完成后获取 `tasks/result`。服务端状态在重启后仍然存在。

## 核心概念

### 任务增强

通过设置 `params._meta.task.required: true`（或 `optional: true`，由服务器决定），请求变为任务。服务器立即响应：

```json
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "_meta": {
      "task": {
        "id": "tsk_9f7b...",
        "state": "working",
        "ttl": 900000
      }
    }
  }
}
```

`ttl` 是服务器保留状态的承诺；ttl 之后任务结果将被丢弃。

### 每工具选择加入

工具注解可以声明任务支持：

- `taskSupport: "forbidden"` — 此工具始终同步运行。适用于快速工具。
- `taskSupport: "optional"` — 客户端可以请求任务增强。
- `taskSupport: "required"` — 客户端**必须**使用任务增强。

`generate_report` 工具应为 `required`。`notes_search` 工具应为 `forbidden`。

### 状态

```
working  -> input_required -> working  (通过引出循环)
working  -> completed
working  -> failed
working  -> cancelled
```

状态机是追加式的：一旦 `completed`、`failed` 或 `cancelled`，任务就是终态。

### 方法

- `tasks/status {taskId}` — 返回当前状态和进度提示。
- `tasks/result {taskId}` — 阻塞或在未完成时返回 404。
- `tasks/cancel {taskId}` — 幂等；终态忽略。
- `tasks/list` — 可选；枚举活跃和最近完成的任务。

### 流式状态变更

当服务器支持时，客户端可以订阅状态通知：

```
server -> notifications/tasks/updated {taskId, state, progress?}
```

流式传输而非轮询的客户端获得更好的 UX。轮询作为最小接口始终被支持。

### 持久化状态

规范要求声明任务支持的服务器持久化状态。崩溃不应在 ttl 内丢失已完成的结果。存储方式从 SQLite 到 Redis 到文件系统。Lesson 13 的脚手架使用文件系统。

### 取消语义

`tasks/cancel` 是幂等的。如果任务正在执行中，服务器尝试停止（检查执行器的协作取消）。如果已经是终态，请求是空操作。

### 崩溃恢复

当服务器进程重启时：

1. 加载所有持久化的任务状态。
2. 将进程死亡时处于 `working` 状态的任务标记为 `failed`，错误为 `CRASH_RECOVERY`。
3. 在 ttl 内保留 `completed` / `failed` / `cancelled` 状态。

### 异步任务加采样

任务本身可以调用 `sampling/createMessage`。这就是长时间运行的研究任务的工作方式：服务器的任务线程根据需要采样客户端的模型，而客户端的 UI 将任务显示为 `working` 并定期更新进度。

### 为什么这是实验性的

SEP-1686 在 2025-11-25 发布，但更广泛的路线图指出了三个未解决问题：持久化订阅原语、子任务（父子任务关系）和结果 TTL 标准化。预计规范将在 2026 年演进。生产代码应仅在常见情况下将 Tasks 视为稳定，并为子任务防范未来的 SDK 变更。

## 使用方法

`code/main.py` 实现了一个持久化任务存储（基于文件系统）和一个在后台线程中运行的 `generate_report` 工具。客户端调用工具，立即获得任务 id，在 worker 更新进度时轮询 `tasks/status`，完成后获取 `tasks/result`。取消功能可用；崩溃恢复通过杀死 worker 线程并重新加载状态来模拟。

关注要点：

- 任务状态 JSON 持久化到 `/tmp/lesson-13-tasks/<id>.json`。
- Worker 线程更新 `progress` 字段；轮询显示进度推进。
- 客户端取消设置事件；worker 检查并提前退出。
- "崩溃"时的状态重载将进行中的任务标记为 `failed`，错误为 `CRASH_RECOVERY`。

## 交付产出

本课产出 `outputs/skill-task-store-designer.md`。给定一个长时间运行的工具（研究、构建、导出），该技能设计任务存储（状态形状、ttl、持久性），选择正确的 taskSupport 标志，并草绘进度通知。

## 练习

1. 运行 `code/main.py`。启动一个 `generate_report` 任务，轮询状态，然后获取结果。

2. 在运行中途添加 `tasks/cancel` 调用。验证 worker 遵守它且状态变为 `cancelled`。

3. 模拟崩溃恢复：杀死 worker 线程，重启加载器，观察 `CRASH_RECOVERY` 失败模式。

4. 将存储扩展到 SQLite。持久性优势相同；查询选项打开了（列出会话 X 的所有任务）。

5. 阅读 MCP 的 2026 路线图文章。找出最可能在未来一年影响 SDK API 设计的 Tasks 相关未解决问题。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Task（任务） | "长时间运行的工具调用" | 用 `_meta.task` 增强的异步执行请求 |
| SEP-1686 | "Tasks 规范" | 在 2025-11-25 添加 Tasks 的规范演进提案 |
| `_meta.task` | "任务信封" | 包含 id、state、ttl 的每请求元数据 |
| taskSupport | "工具标志" | 每个工具的 `forbidden` / `optional` / `required` |
| `tasks/status` | "轮询方法" | 获取当前状态和可选进度提示 |
| `tasks/result` | "获取结果" | 返回已完成的载荷，未完成时返回 404 |
| `tasks/cancel` | "停止它" | 幂等的取消请求 |
| ttl | "保留预算" | 服务器承诺保留任务状态的毫秒数 |
| `notifications/tasks/updated` | "状态推送" | 服务器发起的状态变更事件 |
| Durable Store（持久化存储） | "崩溃安全状态" | 文件系统 / SQLite / Redis 持久层 |

## 延伸阅读

- [MCP — GitHub SEP-1686 issue](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1686) — 提案来源和完整讨论
- [WorkOS — MCP async tasks for AI agent workflows](https://workos.com/blog/mcp-async-tasks-ai-agent-workflows) — 设计演练与原理
- [DeepWiki — MCP task system and async operations](https://deepwiki.com/modelcontextprotocol/modelcontextprotocol/2.7-task-system-and-async-operations) — 机制和状态机
- [FastMCP — Tasks](https://gofastmcp.com/servers/tasks) — SDK 级任务实现模式
- [MCP blog — 2026 roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) — 未解决问题和 2026 年优先事项，包括子任务