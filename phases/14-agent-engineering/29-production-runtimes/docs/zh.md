# 生产运行时（Production Runtimes）：队列、事件、定时任务

> 生产级智能体运行在六种运行时形态上：请求-响应（Request-Response）、流式（Streaming）、持久执行（Durable Execution）、基于队列的后台（Queue-based Background）、事件驱动（Event-driven）和定时调度（Scheduled）。先选形态，再选框架。在每种形态中，可观测性都是不可或缺的。

**类型：** Learn
**语言：** Python（标准库）
**前置课程：** Phase 14 · 13（LangGraph），Phase 14 · 22（Voice）
**时间：** ~60 分钟

## 学习目标

- 列出六种生产运行时形态，并将每种与框架/产品模式对应。
- 解释为什么持久执行（Durable Execution，LangGraph）对长程任务至关重要。
- 描述事件驱动运行时及 Claude Managed Agents 的适用场景。
- 解释为什么可观测性是多步智能体的关键基础设施。

## 问题背景

生产级智能体的失败方式是 Jupyter Notebook 无法暴露的：第 37 步网络超时、用户在语音通话中途挂断、定时任务在机器重启时中断、后台工作者内存耗尽。运行时形态决定了哪些失败是可以恢复的。

## 核心概念

### 请求-响应（Request-Response）

- 同步 HTTP。用户等待完成。
- 仅适用于短任务（<30 秒）。
- 技术栈：Agno（Python + FastAPI）、Mastra（TypeScript + Express/Hono/Fastify/Koa）。
- 可观测性：标准 HTTP 访问日志 + OTel Span。

### 流式（Streaming）

- 通过 SSE 或 WebSocket 实现渐进式输出。
- LiveKit 将此扩展到 WebRTC 用于语音/视频（第 22 课）。
- 技术栈：任何支持流式的框架 + 处理 SSE/WS 的前端。
- 可观测性：每块（Chunk）计时、首 Token 延迟、尾延迟。

### 持久执行（Durable Execution）

- 每步之后检查点保存状态；失败时自动恢复。
- AutoGen v0.4 Actor 模型将失败隔离到单个智能体（第 14 课）。
- LangGraph 的核心差异化特性（第 13 课）。
- 当步数未知且恢复成本高时不可或缺。

### 基于队列 / 后台（Queue-based / Background）

- 任务进入队列，工作者拾取，结果通过 Webhook 或发布/订阅回传。
- 对长程智能体不可或缺（每个任务数十到数百步，引自 Anthropic 的计算机使用公告）。
- 技术栈：Celery（Python）、BullMQ（Node）、SQS + Lambda（AWS）、自定义方案。
- 可观测性：队列深度、单任务延迟分布、死信队列（DLQ）大小。

### 事件驱动（Event-driven）

- 智能体订阅触发器：新邮件、PR 开启、定时触发。
- Claude Managed Agents 开箱即用地支持此模式（第 17 课）。
- CrewAI Flows（第 15 课）构建事件驱动的确定性工作流。
- 可观测性：触发源、事件到启动延迟、智能体延迟。

### 定时调度（Scheduled）

- 定时任务形态的智能体，周期性运行。
- 结合持久执行，使失败的夜间任务在下个周期恢复。
- 技术栈：Kubernetes CronJob + 持久框架；托管方案（Render cron、Vercel cron）。

### 2026 年部署模式

- **CrewAI Flows** — 事件驱动的生产环境。
- **Agno** 无状态 FastAPI — Python 微服务。
- **Mastra** 服务器适配器（Express、Hono、Fastify、Koa）— 嵌入式集成。
- **Pipecat Cloud / LiveKit Cloud** — 托管语音（第 22 课）。
- **Claude Managed Agents** — 托管长时间运行的异步任务。

### 可观测性是关键基础设施

没有 OpenTelemetry GenAI Span（第 23 课）加上 Langfuse/Phoenix/Opik 后端（第 24 课），你无法调试在第 40 步失败的多步智能体。这不是生产环境的可选项。它决定了是"快速调试"还是"从头用更多日志重放"。

### 生产运行时的常见陷阱

- **形态选择错误。** 为 5 分钟的任务选择请求-响应。用户挂断；工作者堆积；重试叠加。
- **没有死信队列（DLQ）。** 队列工作者没有死信处理。失败的任务消失。
- **后台工作不透明。** 后台智能体运行但没有追踪导出。失败在用户反馈之前不可见。
- **跳过持久状态。** 任何超过 30 秒且不能承受重启的运行都需要持久执行。

## 动手实现

`code/main.py` 是一个多形态的标准库演示：

- 请求-响应端点（普通函数）。
- 流式处理器（生成器）。
- 带 DLQ 的队列工作者。
- 事件触发注册表。
- 定时调度器。

运行：

```bash
python3 code/main.py
```

输出：五条追踪，展示同一任务在每种形态下的行为。相同的智能体逻辑，不同的外壳。第六种形态（持久执行）在第 13 课的 LangGraph 检查点中专门讲解。

## 实践应用

- **请求-响应** — 聊天式 UX。
- **流式** — 渐进式响应。
- **持久执行** — 长程任务。
- **队列** — 批量 / 异步 / 长时间运行。
- **事件驱动** — 智能体反应式触发。
- **定时任务** — 运维任务（记忆整合、评估、成本报告）。

## 产出物

`outputs/skill-runtime-shape.md` 为任务选择运行时形态并接入可观测性需求。

## 练习

1. 将第 01 课的 ReAct 循环移植到你的技术栈中的全部六种形态。哪种形态适合哪种产品表面？
2. 为队列演示添加 DLQ。模拟 10% 任务失败；展示 DLQ 大小。
3. 编写一个定时触发的评估智能体，每晚对你当天的前 20 条追踪运行评估。
4. 实现带背压（Backpressure）的流式处理：如果客户端较慢，则暂停智能体。这如何与轮次预算交互？
5. 阅读 Claude Managed Agents 文档。何时应将自托管的长程智能体迁移到托管方案？

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| Request-response（请求-响应） | "同步" | 用户等待；仅适用于短任务 |
| Streaming（流式） | "SSE / WS" | 渐进式输出；更好的 UX；按块可观测延迟 |
| Durable Execution（持久执行） | "从失败中恢复" | 检查点状态；从最后一步重启 |
| Queue-based（基于队列） | "后台任务" | 生产者 / 工作者池 / DLQ |
| Event-driven（事件驱动） | "基于触发器" | 智能体对外部事件做出反应 |
| DLQ（死信队列） | "死信队列" | 失败任务的停放区 |
| Claude Managed Agents | "托管运行时" | Anthropic 托管的长时间运行异步任务，带缓存和压缩 |

## 延伸阅读

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) — 持久执行细节
- [Claude Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview) — 托管长时间运行异步
- [Anthropic, Introducing computer use](https://www.anthropic.com/news/3-5-models-and-computer-use) — "每个任务数十到数百步"
- [AutoGen v0.4 (Microsoft Research)](https://www.microsoft.com/en-us/research/articles/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/) — Actor 模型故障隔离