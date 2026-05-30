# Agno 与 Mastra：生产运行时

> Agno（Python）和 Mastra（TypeScript）是 2026 年的生产运行时配对。Agno 瞄准微秒级 Agent 实例化和无状态 FastAPI 后端。Mastra 在 Vercel AI SDK 基础上提供 Agent、工具、工作流、统一模型路由和复合存储。

**类型：** Learn
**语言：** Python, TypeScript
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 13（LangGraph）
**时间：** ~45 分钟

## 学习目标

- 识别 Agno 的性能目标及其重要场景。
- 说出 Mastra 的三个原语 —— Agents、Tools、Workflows —— 以及支持的服务器适配器。
- 解释为什么无状态会话范围的 FastAPI 后端是推荐的 Agno 生产路径。
- 为给定技术栈选择 Agno vs Mastra（Python 优先 vs TypeScript 优先）。

## 问题

LangGraph、AutoGen、CrewAI 框架较重。想要"只要 Agent 循环，快，在我的运行时中"的团队选择 Agno（Python）或 Mastra（TypeScript）。两者都用原始速度和更贴合周围技术栈来交换一些框架拥有的原语。

## 核心概念

### Agno

- Python 运行时，前身为 Phi-data。
- "没有图、链或复杂模式 —— 只有纯 Python。"
- 来自文档的性能目标：约 2μs Agent 实例化、每个 Agent 约 3.75 KiB 内存、约 23 个模型提供商。
- 生产路径：无状态会话范围的 FastAPI 后端。每个请求启动一个全新 Agent；会话状态存储在数据库中。
- 原生多模态（文本、图像、音频、视频、文件）和 Agentic RAG。

当你每秒有数千个短生命周期 Agent（聊天扇入、评估流水线）时，速度目标很重要。当一个 Agent 运行 10 分钟时，它们不太重要。

### Mastra

- TypeScript，基于 Vercel AI SDK 构建。
- 三个原语：**Agents**、**Tools**（Zod 类型化）、**Workflows**。
- 统一模型路由器 —— 94 个提供商的 3,300+ 模型（2026 年 3 月）。
- 复合存储：记忆、工作流、可观测性分别到不同后端；ClickHouse 推荐用于大规模可观测性。
- Apache 2.0 许可，`ee/` 目录在源码可用企业许可下。
- 服务器适配器支持 Express、Hono、Fastify、Koa；一等 Next.js 和 Astro 集成。
- 提供 Mastra Studio（localhost:4111）用于调试。
- 22k+ GitHub stars，1.0 版本时每周 300k+ npm 下载（2026 年 1 月）。

### 定位

两者都不试图成为 LangGraph。它们在以下方面竞争：

- **语言适配。** Agno 用于 Python 优先团队；Mastra 用于 TypeScript 优先。
- **运行时人体工程学。** Agno = 接近零开销；Mastra = 与 Vercel 生态系统集成。
- **可观测性。** 两者都与 Langfuse/Phoenix/Opik（第 24 课）集成，但 Mastra Studio 是第一方的。

### 何时选择哪个

- **Agno** — Python 后端、大量短生命周期 Agent、强性能要求、FastAPI 技术栈。
- **Mastra** — TypeScript 后端、Next.js / Vercel 部署、统一多提供商模型路由、Zod 类型化工具。
- **LangGraph**（第 13 课）—— 当持久状态和显式图推理比原始速度更重要时。
- **OpenAI / Claude Agent SDK** —— 当你想要提供商的产品化形状时（第 16-17 课）。

### 这个模式出错的地方

- **为性能而性能。** 因为"2μs"听起来不错而选择 Agno，但工作负载是每个请求一个慢 Agent 调用。开销不是瓶颈。
- **生态系统锁定。** Mastra 的 Vercel 风格集成在 Vercel 上是加分项，在其他地方是减分项。
- **企业许可混淆。** Mastra 的 `ee/` 目录是源码可用的，不是 Apache 2.0。如果你计划分叉，请阅读许可。

## 构建它

本课主要是比较性的 —— 没有单个代码工件能公正地展示两个框架。见 `code/main.py` 获取并排的玩具代码：一个最小的"运行 Agent、流式输出、持久化会话"流程实现了两次（一次 Agno 形状，一次 Mastra 形状）。

运行它：

```
python3 code/main.py
```

两个结构不同但功能等价的轨迹。

## 使用它

- **Agno** — 需要速度和 FastAPI 形状的 Python 后端。
- **Mastra** — 带多提供商和工作流原语的 TypeScript 后端。
- 两者都提供第一方可观测性钩子。两者都与 Langfuse 集成。

## 发布它

`outputs/skill-runtime-picker.md` 根据技术栈、延迟预算和运营形态选择 Agno、Mastra、LangGraph 或提供商 SDK。

## 练习

1. 阅读 Agno 文档。将标准库 ReAct 循环（第 1 课）移植到 Agno。什么消失了？什么保留了？
2. 阅读 Mastra 文档。将同一个循环移植到 Mastra。工具有什么类型化变化（Zod vs 无）？
3. 基准测试：在你的技术栈上衡量 Agent 实例化延迟。Agno 的 2μs 对你的工作负载重要吗？
4. 设计迁移：如果你一直在 Python 中运行 CrewAI，迁移到 Agno 时什么会出问题？
5. 阅读 Mastra 的 `ee/` 许可条款。什么限制会影响开源分叉？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Agno | "快速 Python Agent" | 无状态会话范围的 Agent 运行时 |
| Mastra | "Vercel AI SDK 上的 TypeScript Agent" | Agents + Tools + Workflows + 模型路由器 |
| Unified Model Router | "多提供商访问" | 94 个提供商的 3,300+ 模型的单一客户端 |
| Composite storage | "多后端" | 记忆/工作流/可观测性分别到不同存储 |
| Mastra Studio | "本地调试器" | localhost:4111 用于自省 Agent 的 UI |
| Source-available | "非开源" | 许可允许源码阅读但限制商业使用 |

## 延伸阅读

- [Agno Agent Framework docs](https://www.agno.com/agent-framework) — 性能目标、FastAPI 集成
- [Mastra docs](https://mastra.ai/docs) — 原语、服务器适配器、模型路由器
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) — 有状态图替代方案
- [Comet Opik](https://www.comet.com/site/products/opik/) — Mastra 集成引用的可观测性比较