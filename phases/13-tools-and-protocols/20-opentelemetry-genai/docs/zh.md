# OpenTelemetry GenAI — 端到端追踪工具调用

> 一个 Agent 调用五个工具、三个 MCP 服务器和两个子 Agent。你需要一条贯穿全部的 trace。OpenTelemetry GenAI 语义约定（v1.37 及以上稳定属性）是 2026 年的标准，Datadog、Langfuse、Arize Phoenix、OpenLLMetry 和 AgentOps 原生支持。本课列出必需属性，走一遍 span 层次结构（agent → LLM → tool），并交付一个你可以插入任何 OTel 导出器的标准库 span 发出器。

**类型：** Build
**语言：** Python（stdlib，OTel span 发出器）
**前置课程：** Phase 13 · 07（MCP 服务器）、Phase 13 · 08（MCP 客户端）
**时间：** ~75 分钟

## 学习目标

- 列出 LLM span 和工具执行 span 的必需 OTel GenAI 属性。
- 构建覆盖 Agent 循环、LLM 调用、工具调用和 MCP 客户端分发的 trace 层次结构。
- 决定哪些内容要捕获（opt-in）vs 脱敏（默认）。
- 在不重写工具代码的情况下向本地收集器（Jaeger、Langfuse）发出 span。

## 问题

2026 年 2 月的一次调试：用户报告"我的 Agent 有时要 30 秒才响应；其他时候 3 秒"。没有 trace。日志显示了 LLM 调用，但没有工具分发、没有 MCP 服务器往返、没有子 Agent。你在猜测。最终你发现：一个 MCP 服务器偶尔在冷启动时挂起。

没有端到端追踪，你找不到这个问题。OTel GenAI 修复了它。

这些约定在 2025-2026 年间在 OpenTelemetry 语义约定组下确定。它们定义了稳定的属性名，使 Datadog、Langfuse、Phoenix、OpenLLMetry 和 AgentOps 都能解析相同的 span。插桩一次；发送到任何后端。

## 核心概念

### Span 层次结构

```
agent.invoke_agent  (顶层，INTERNAL span)
 ├── llm.chat       (CLIENT span)
 ├── tool.execute   (INTERNAL)
 │    └── mcp.call  (CLIENT span)
 ├── llm.chat       (CLIENT span)
 └── subagent.invoke (INTERNAL)
```

全部嵌套在一个 trace id 下。Span id 链接父子关系。

### 必需属性

按 2025-2026 语义约定：

- `gen_ai.operation.name` — `"chat"`、`"text_completion"`、`"embeddings"`、`"execute_tool"`、`"invoke_agent"`。
- `gen_ai.provider.name` — `"openai"`、`"anthropic"`、`"google"`、`"azure_openai"`。
- `gen_ai.request.model` — 请求的模型字符串（如 `"gpt-4o-2024-08-06"`）。
- `gen_ai.response.model` — 实际服务的模型。
- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`。
- `gen_ai.response.id` — 用于关联的提供商响应 id。

工具 span：

- `gen_ai.tool.name` — 工具标识符。
- `gen_ai.tool.call.id` — 特定调用 id。
- `gen_ai.tool.description` — 工具描述（可选）。

Agent span：

- `gen_ai.agent.name` / `gen_ai.agent.id` / `gen_ai.agent.description`。

### Span 类型

- `SpanKind.CLIENT` 用于跨越进程边界的调用（LLM 提供商、MCP 服务器）。
- `SpanKind.INTERNAL` 用于 Agent 自身的循环步骤和工具执行。

### Opt-in 内容捕获

默认情况下，span 携带指标和计时 — 不包含提示或完成内容。大型载荷和 PII 默认关闭。设置 `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` 和特定的内容捕获环境变量来包含内容。在生产中启用前请仔细审查。

### Span 上的事件

Token 级事件可以作为 span 事件添加：

- `gen_ai.content.prompt` — 输入消息。
- `gen_ai.content.completion` — 输出消息。
- `gen_ai.content.tool_call` — 记录的工具调用。

事件在 span 内按时间排序，用于详细回放。

### 导出器

OTel span 导出到：

- **Jaeger / Tempo。** 开源，本地部署。
- **Langfuse。** LLM 可观测性专用；可视化 token 使用。
- **Arize Phoenix。** 评估 + 追踪结合。
- **Datadog。** 商业；原生解析 `gen_ai.*` 属性。
- **Honeycomb。** 列式存储；查询友好。

全部使用 OTLP 线路格式。你的代码不需要关心。

### 跨 MCP 传播

当 MCP 客户端调用服务器时，将 W3C traceparent 头注入请求。Streamable HTTP 支持标准头。Stdio 原生不携带 HTTP 头；规范的 2026 路线图讨论在 JSON-RPC 调用上添加 `_meta.traceparent` 字段。

在那之前：手动在每个请求的 `_meta` 中包含 traceparent。服务器记录 trace id。

### 指标

与 span 并行，GenAI 语义约定定义了指标：

- `gen_ai.client.token.usage` — 直方图。
- `gen_ai.client.operation.duration` — 直方图。
- `gen_ai.tool.execution.duration` — 直方图。

用于不需要逐调用详情的仪表板。

### AgentOps 层

AgentOps（2024 年创立）专注于 GenAI 可观测性。它封装流行框架（LangGraph、Pydantic AI、CrewAI）自动发出 OTel span。如果你的技术栈使用受支持的框架很有用；否则使用手动插桩。

## 使用方法

`code/main.py` 为一个调用 LLM、分发两个工具并做一次 MCP 往返的 Agent 向 stdout 发出 OTel 形式的 span（以 OTLP-JSON 类格式）。没有真实的导出器 — 本课聚焦于 span 形式和属性集。将输出粘贴到兼容 OTLP 的查看器中或直接阅读。

关注要点：

- Trace id 在所有 span 中共享。
- 父子链接通过 `parentSpanId` 编码。
- 必需的 `gen_ai.*` 属性已填充。
- 内容捕获默认关闭；一个场景通过环境变量开启。

## 交付产出

本课产出 `outputs/skill-otel-genai-instrumentation.md`。给定一个 Agent 代码库，该技能生成插桩计划：在哪里添加 span、填充哪些属性、以及目标导出器。

## 练习

1. 运行 `code/main.py`。统计 span 数量并识别哪些是 CLIENT vs INTERNAL。

2. 开启内容捕获（环境变量），确认 `gen_ai.content.prompt` 和 `gen_ai.content.completion` 事件出现。注意对 PII 的影响。

3. 添加工具执行指标 `gen_ai.tool.execution.duration` 并作为每次调用的直方图样本发出。

4. 从父 Agent span 传播 traceparent 到 MCP 请求的 `_meta.traceparent` 字段。验证 MCP 服务器会看到相同的 trace id。

5. 阅读 OTel GenAI 语义约定规范。找出本课代码**未**发出的语义约定中的一个属性。添加它。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| OTel | "OpenTelemetry" | trace、metric、log 的开放标准 |
| GenAI semconv | "GenAI 语义约定" | LLM / 工具 / Agent span 的稳定属性名 |
| `gen_ai.*` | "属性命名空间" | 所有 GenAI 属性共享此前缀 |
| Span | "计时操作" | 带开始、结束和属性的工作单元 |
| Trace | "跨 span 祖先" | 共享 trace id 的 span 树 |
| SpanKind | "CLIENT / SERVER / INTERNAL" | 关于 span 方向的提示 |
| OTLP | "OpenTelemetry Line Protocol" | 导出器的线路格式 |
| Opt-in Content | "提示/完成内容捕获" | 默认关闭；环境变量启用 |
| traceparent | "W3C 头" | 跨服务传播 trace 上下文 |
| Exporter（导出器） | "后端特定的发送器" | 将 span 发送到 Jaeger / Datadog 等的组件 |

## 延伸阅读

- [OpenTelemetry — GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — GenAI span、metric 和事件的规范性约定
- [OpenTelemetry — GenAI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) — LLM 和工具执行 span 属性列表
- [OpenTelemetry — GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) — Agent 级 `invoke_agent` span
- [open-telemetry/semantic-conventions — GenAI spans](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md) — GitHub 托管的真实来源
- [Datadog — LLM OTel semantic convention](https://www.datadoghq.com/blog/llm-otel-semantic-convention/) — 生产集成演练