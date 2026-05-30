# OpenTelemetry GenAI 语义约定

> OpenTelemetry 的 GenAI 特别兴趣小组（GenAI SIG，2024 年 4 月启动）定义了智能体遥测（Agent Telemetry）的标准模式。Span 名称、属性和内容捕获规则在各厂商之间趋于统一，使得智能体追踪数据在 Datadog、Grafana、Jaeger 和 Honeycomb 中具有一致的含义。

**类型：** Learn + Build
**语言：** Python（标准库）
**前置课程：** Phase 14 · 13（LangGraph），Phase 14 · 24（Observability Platforms）
**时间：** ~60 分钟

## 学习目标

- 列出 GenAI Span 的类别：模型/客户端（Model/Client）、智能体（Agent）、工具（Tool）。
- 区分 `invoke_agent` 的 CLIENT Span 和 INTERNAL Span 及其适用场景。
- 列出顶层 GenAI 属性：Provider 名称、请求模型、数据源 ID。
- 解释内容捕获契约（Content-capture Contract）：按需启用（Opt-in）、`OTEL_SEMCONV_STABILITY_OPT_IN`、外部引用推荐。

## 问题背景

每个厂商都发明自己的 Span 名称。运维团队不得不为每个框架构建独立的仪表盘。OpenTelemetry 的 GenAI SIG 通过定义统一标准来解决这个问题，整个生态系统都可以对准这一个目标。

## 核心概念

### Span 类别

1. **模型 / 客户端 Span（Model / Client Spans）。** 覆盖原始 LLM 调用。由 Provider SDK（Anthropic、OpenAI、Bedrock）和框架的模型适配器发出。
2. **智能体 Span（Agent Spans）。** `create_agent`（构造智能体时）和 `invoke_agent`（运行智能体时）。
3. **工具 Span（Tool Spans）。** 每次工具调用一个；通过父子关系连接到智能体 Span。

### 智能体 Span 命名

- Span 名称：如果智能体有名称则为 `invoke_agent {gen_ai.agent.name}`；否则回退为 `invoke_agent`。
- Span 类型（Kind）：
  - **CLIENT** — 用于远程智能体服务（OpenAI Assistants API、Bedrock Agents）。
  - **INTERNAL** — 用于进程内智能体框架（LangChain、CrewAI、本地 ReAct）。

### 关键属性

- `gen_ai.provider.name` — `anthropic`、`openai`、`aws.bedrock`、`google.vertex`。
- `gen_ai.request.model` — 模型 ID。
- `gen_ai.response.model` — 实际解析的模型（可能因路由与请求不同）。
- `gen_ai.agent.name` — 智能体标识符。
- `gen_ai.operation.name` — `chat`、`completion`、`invoke_agent`、`tool_call`。
- `gen_ai.data_source.id` — 用于 RAG：查询了哪个语料库或存储。

针对 Anthropic、Azure AI Inference、AWS Bedrock、OpenAI 有各自的技术特定约定。

### 内容捕获（Content Capture）

默认规则：插桩（Instrumentation）**不应**默认捕获输入/输出。捕获需通过以下字段按需启用：

- `gen_ai.system_instructions`
- `gen_ai.input.messages`
- `gen_ai.output.messages`

推荐的生产模式：将内容存储到外部（S3、日志存储），在 Span 上记录引用（指针 ID，而非文本内容）。这是第 27 课内容投毒防御在可观测性层面的体现。

### 稳定性（Stability）

截至 2026 年 3 月，大多数约定仍处于实验阶段。通过以下方式启用稳定预览：

```
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

Datadog v1.37+ 原生将 GenAI 属性映射到其 LLM Observability 模式。其他后端（Grafana、Honeycomb、Jaeger）支持原始属性。

### 这种模式的常见陷阱

- **在 Span 中捕获完整提示内容。** PII、密钥、客户数据出现在运维人员可见的追踪中。应存储到外部。
- **缺少 `gen_ai.provider.name`。** 多 Provider 仪表盘在缺少归因时会失效。
- **Span 缺少父子链接。** 孤立的工具 Span。始终需要传播上下文。
- **未设置稳定性 Opt-in。** 后端升级时属性可能会被重命名。

## 动手实现

`code/main.py` 实现了一个符合 GenAI 约定的标准库 Span 发射器：

- 带有 GenAI 属性模式的 `Span`。
- 支持嵌套上下文的 `Tracer`，包含 `start_span` 方法。
- 脚本化的智能体运行，发出：`create_agent`、`invoke_agent`（INTERNAL）、每个工具的 Span、LLM 调用的 `chat` Span。
- 内容捕获模式：将提示存储到外部，Span 上仅记录引用 ID。

运行：

```
python3 code/main.py
```

输出：一棵包含所有必需 GenAI 属性的 Span 树，以及展示按需内容引用的"外部存储"。

## 实践应用

- **Datadog LLM Observability**（v1.37+）原生映射属性。
- **Langfuse / Phoenix / Opik**（第 24 课）— 自动插桩生态系统。
- **Jaeger / Honeycomb / Grafana Tempo** — 原始 OTel 追踪；基于 GenAI 属性构建仪表盘。
- **自托管** — 运行带有 GenAI 处理器的 OTel Collector。

## 产出物

`outputs/skill-otel-genai.md` 将 OTel GenAI Span 接入现有智能体，配置内容捕获默认值和外部引用存储。

## 练习

1. 用 `invoke_agent`（INTERNAL）+ 每个工具的 Span 对第 01 课的 ReAct 循环进行插桩。发送到 Jaeger 实例。
2. 添加"仅引用"模式的内容捕获：提示存入 SQLite，Span 属性仅携带行 ID。
3. 阅读 `gen_ai.data_source.id` 的规范。将其接入第 09 课的 Mem0 搜索。
4. 设置 `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`，验证属性不会被 Collector 重命名。
5. 构建一个仪表盘：仅通过 GenAI 属性分析"哪些工具错误与哪些模型相关"。

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| GenAI SIG | "OpenTelemetry GenAI 小组" | 定义该模式的 OTel 工作组 |
| invoke_agent | "智能体 Span" | 表示一次智能体运行的 Span 名称 |
| CLIENT Span | "远程调用" | 调用远程智能体服务的 Span |
| INTERNAL Span | "进程内" | 进程内智能体运行的 Span |
| gen_ai.provider.name | "Provider" | anthropic / openai / aws.bedrock / google.vertex |
| gen_ai.data_source.id | "RAG 数据源" | 检索命中的语料库/存储 |
| Content Capture（内容捕获） | "提示日志" | 按需捕获消息；生产环境应外部存储 |
| Stability Opt-in（稳定性启用） | "预览模式" | 用于固定实验性约定的环境变量 |

## 延伸阅读

- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — 规范
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) — 默认生成 GenAI Span
- [AutoGen v0.4 (Microsoft Research)](https://www.microsoft.com/en-us/research/articles/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/) — 内置 OTel Span
- [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) — W3C 追踪上下文传播