# OpenAI Agents SDK：交接、护栏、追踪

> OpenAI Agents SDK 是基于 Responses API 构建的轻量级多 Agent 框架。五个原语：Agent、Handoff、Guardrail、Session、Tracing。交接是名为 `transfer_to_<agent>` 的工具。护栏在输入或输出上触发。追踪默认开启。

**类型：** Learn + Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 06（Tool Use）
**时间：** ~75 分钟

## 学习目标

- 说出 OpenAI Agents SDK 的五个原语。
- 解释交接：为什么它们被建模为工具、模型看到什么名称形状、上下文如何传递。
- 区分输入护栏、输出护栏和工具护栏；解释 `run_in_parallel` vs 阻塞模式。
- 用标准库实现一个带交接 + 护栏 + span 风格追踪的运行时。

## 问题

不能干净委托的 Agent 最终把所有东西塞进一个提示中。没有护栏的 Agent 发布 PII、违反政策的输出，或永远循环。OpenAI 的 SDK 将使多 Agent 工作可行的三个原语编纂化。

## 核心概念

### 五个原语

1. **Agent。** LLM + 指令 + 工具 + 交接。
2. **Handoff（交接）。** 委托给另一个 Agent。对模型表示为名为 `transfer_to_<agent_name>` 的工具。
3. **Guardrail（护栏）。** 对输入（仅第一个 Agent）、输出（仅最后一个 Agent）或工具调用（每个函数工具）的验证。
4. **Session（会话）。** 跨轮次的自动对话历史。
5. **Tracing（追踪）。** LLM 生成、工具调用、交接、护栏的内置 span。

### 交接即工具

模型在工具列表中看到 `transfer_to_billing_agent`。调用它表示运行时：

1. 复制对话上下文（或通过 `nest_handoff_history` beta 折叠）。
2. 用目标 Agent 的指令初始化目标 Agent。
3. 用目标 Agent 继续运行。

这是监督者模式（第 13 课 / 第 28 课）的产品化。

### 护栏

三种类型：

- **输入护栏。** 在第一个 Agent 的输入上运行。在任何 LLM 调用之前拒绝不安全或超出范围的请求。
- **输出护栏。** 在最后一个 Agent 的输出上运行。捕捉 PII 泄露、政策违规、格式错误的响应。
- **工具护栏。** 在每个函数工具上运行。验证参数、检查权限、审计执行。

模式：

- **并行**（默认）。护栏 LLM 与主 LLM 并行运行。更低的尾部延迟。如果触发，主 LLM 的工作被丢弃（token 浪费）。
- **阻塞**（`run_in_parallel=False`）。护栏 LLM 先运行。如果触发，主调用不浪费 token。

触发线抛出 `InputGuardrailTripwireTriggered` / `OutputGuardrailTripwireTriggered`。

### 追踪

默认开启。每次 LLM 生成、工具调用、交接和护栏都发出一个 span。`OPENAI_AGENTS_DISABLE_TRACING=1` 选择退出。`add_trace_processor(processor)` 将 span 扇出到你自己的后端，与 OpenAI 的并行。

### 会话

`Session` 在后端（SQLite、Redis、自定义）中存储对话历史。`Runner.run(agent, input, session=session)` 自动加载和追加。

### 这个模式出错的地方

- **交接漂移。** Agent A 交接给 Agent B，Agent B 又交回给 Agent A。添加跳数计数器。
- **护栏绕过。** 工具护栏仅在函数工具上触发；内置工具（文件读取器、Web 抓取）需要单独的策略。
- **过度追踪。** span 中的敏感内容。配合 OTel GenAI 内容捕获规则（第 23 课）—— 外部存储，按 ID 引用。

## 构建它

`code/main.py` 用标准库实现了 SDK 形状：

- `Agent`、`FunctionTool`、`Handoff`（作为带转移语义的函数工具）。
- `Runner` 带输入/输出/工具护栏、交接分发和跳数计数器。
- 简单的 span 发射器展示轨迹形状。
- 一个分诊 Agent 根据用户查询交接给计费或支持；一个输入护栏触发。

运行它：

```
python3 code/main.py
```

轨迹展示了两次成功的交接、一次输入护栏触发，以及镜像真实 SDK 发出的 span 树。

## 使用它

- **OpenAI Agents SDK** 用于 OpenAI 优先的产品。
- **Claude Agent SDK**（第 17 课）用于 Claude 优先的产品。
- **LangGraph**（第 13 课）当你想要显式状态和持久恢复时。
- **自定义** 当你需要精确控制（语音、多提供商、联邦部署）时。

## 发布它

`outputs/skill-agents-sdk-scaffold.md` 脚手架一个 Agents SDK 应用，带分诊 Agent、交接、输入/输出/工具护栏、会话存储和轨迹处理器。

## 练习

1. 添加交接跳数计数器：N 次转移后拒绝。追踪行为。
2. 实现 `nest_handoff_history` 作为选项 —— 在转移前将先前消息折叠为一个摘要。
3. 编写一个阻塞输出护栏。比较会触发的提示与通过的提示的延迟。
4. 将 `add_trace_processor` 接线到 JSON 日志器。每个 span 发出什么形状？
5. 阅读 SDK 文档。将标准库玩具移植到 `openai-agents-python`。你建模错了什么？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Agent | "LLM + 指令" | SDK 中的 Agent 类型；拥有工具和交接 |
| Handoff | "转移" | 模型调用以委托给另一个 Agent 的工具 |
| Guardrail | "策略检查" | 对输入/输出/工具调用的验证 |
| Tripwire | "护栏触发" | 护栏拒绝时抛出的异常 |
| Session | "历史存储" | 跨运行持久化的对话记忆 |
| Tracing | "Span" | LLM + 工具 + 交接 + 护栏的内置可观测性 |
| Blocking guardrail | "顺序检查" | 护栏先运行；触发时不浪费 token |
| Parallel guardrail | "并发检查" | 护栏并行运行；延迟更低，触发时浪费 token |

## 延伸阅读

- [OpenAI Agents SDK docs](https://openai.github.io/openai-agents-python/) — 原语、交接、护栏、追踪
- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) — Claude 风格的对应物
- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — 何时需要交接
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — Agents SDK span 映射到的标准