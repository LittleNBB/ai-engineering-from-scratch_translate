# Function Calling 深入解析 — OpenAI、Anthropic、Gemini

> 三大前沿提供商在 2024 年收敛到相同的工具调用循环，然后在其他所有方面分道扬镳。OpenAI 使用 `tools` 和 `tool_calls`。Anthropic 使用 `tool_use` 和 `tool_result` blocks。Gemini 使用 `functionDeclarations` 和唯一 id 关联机制。本课并行对比三者，让你在一个提供商上编写的代码在移植到另一个提供商时不会出错。

**类型：** Build
**语言：** Python（stdlib，模式转换器）
**前置课程：** Phase 13 · 01（工具接口）
**时间：** ~75 分钟

## 学习目标

- 说出 OpenAI、Anthropic 和 Gemini 的 Function Calling 载荷在三个形式差异（声明、调用、结果）。
- 将一个工具声明在三种提供商格式之间互相转换，并预测严格模式约束的差异位置。
- 在每个提供商中使用 `tool_choice` 来强制、禁止或自动选择工具调用。
- 了解每个提供商的硬性限制（工具数量、Schema 深度、参数长度），以及超出限制时各自发出的错误签名。

## 问题

Function Calling 请求的形式因提供商而异。以下是 2026 年生产技术栈中的三个具体示例：

**OpenAI Chat Completions / Responses API。** 你传入 `tools: [{type: "function", function: {name, description, parameters, strict}}]`。模型的响应包含 `choices[0].message.tool_calls: [{id, type: "function", function: {name, arguments}}]`，其中 `arguments` 是一个你必须手动解析的 JSON 字符串。严格模式（`strict: true`）通过受限解码强制 Schema 合规。

**Anthropic Messages API。** 你传入 `tools: [{name, description, input_schema}]`。响应以 `content: [{type: "text"}, {type: "tool_use", id, name, input}]` 的形式返回。`input` 已经是解析好的对象（不是字符串）。你回复一个新的 `user` 消息，包含一个 `{type: "tool_result", tool_use_id, content}` block。

**Google Gemini API。** 你传入 `tools: [{functionDeclarations: [{name, description, parameters}]}]`（嵌套在 `functionDeclarations` 下）。响应以 `candidates[0].content.parts: [{functionCall: {name, args, id}}]` 的形式到达，其中 `id` 在 Gemini 3 及以上版本中是唯一的，用于并行调用关联。你回复 `{functionResponse: {name, id, response}}`。

相同的循环。不同的字段名、不同的嵌套、不同的字符串/对象约定、不同的关联机制。一个在 OpenAI 上编写天气 Agent 的团队移植到 Anthropic 需要两天，再移植到 Gemini 又需要一天 — 仅仅是为了处理这些管道差异。

本课构建一个转换器，将三种格式统一为一个规范的工具声明，并在边界层进行路由。Phase 13 · 17 将同一模式泛化为 LLM 网关。

## 核心概念

### 共同结构

每个提供商都需要五样东西：

1. **工具列表。** 每个工具的名称、描述和输入 Schema。
2. **Tool choice。** 强制指定某个工具、禁止工具，或让模型自行决定。
3. **调用输出。** 命名工具和参数的结构化输出。
4. **调用 id。** 将响应关联到正确的调用（对并行调用很重要）。
5. **结果注入。** 将结果绑定回调用的消息或 block。

### 形式差异，逐字段对比

| 方面 | OpenAI | Anthropic | Gemini |
|------|--------|-----------|--------|
| 声明信封 | `{type: "function", function: {...}}` | `{name, description, input_schema}` | `{functionDeclarations: [{...}]}` |
| Schema 字段 | `parameters` | `input_schema` | `parameters` |
| 响应容器 | assistant 消息上的 `tool_calls[]` | `content[]` 中 type 为 `tool_use` | `parts[]` 中 type 为 `functionCall` |
| 参数类型 | JSON 字符串 | 已解析对象 | 已解析对象 |
| Id 格式 | `call_...`（OpenAI 生成） | `toolu_...`（Anthropic） | UUID（Gemini 3+） |
| 结果 block | role `tool`，`tool_call_id` | `user` 中的 `tool_result`，`tool_use_id` | `functionResponse` 匹配 `id` |
| 强制调用某工具 | `tool_choice: {type: "function", function: {name}}` | `tool_choice: {type: "tool", name}` | `tool_config: {function_calling_config: {mode: "ANY"}}` |
| 禁止工具 | `tool_choice: "none"` | `tool_choice: {type: "none"}` | `mode: "NONE"` |
| 严格 Schema | `strict: true` | Schema 就是契约（始终强制执行） | 请求级 `responseSchema` |

### 你实际会遇到的限制

- **OpenAI。** 每次请求 128 个工具。Schema 深度 5 层。参数字符串 <= 8192 字节。严格模式不允许 `$ref`，不允许有重叠的 `oneOf`/`anyOf`/`allOf`，每个属性都必须列在 `required` 中。
- **Anthropic。** 每次请求 64 个工具。Schema 深度实际上无限制，但实际限制为 10 层。没有严格模式标志；Schema 就是契约，模型倾向于遵守。
- **Gemini。** 每次请求 64 个函数。Schema 类型是 OpenAPI 3.0 子集（与 JSON Schema 2020-12 有细微差异）。Gemini 3 起支持并行调用唯一 id。

### `tool_choice` 行为

三种大家都支持的模式，名称各不相同。

- **Auto（自动）。** 模型自行选择调用工具或直接回答。默认值。
- **Required / Any（必需）。** 模型必须至少调用一个工具。
- **None（禁止）。** 模型不得调用工具。

加上每个提供商独有的一个模式：

- **OpenAI。** 按名称强制调用某个特定工具。
- **Anthropic。** 按名称强制调用某个特定工具；`disable_parallel_tool_use` 标志区分单个与多个调用。
- **Gemini。** `mode: "VALIDATED"` 无论模型意图如何，每个响应都通过 Schema 验证器路由。

### 并行调用

OpenAI 的 `parallel_tool_calls: true`（默认）在一条 assistant 消息中发出多个调用。你运行所有调用，然后用包含每个 `tool_call_id` 一条记录的批处理 tool-role 消息回复。Anthropic 以前默认单次调用；`disable_parallel_tool_use: false`（Claude 3.5 起默认）启用多次调用。Gemini 2 允许并行调用但不提供稳定 id；Gemini 3 添加了 UUID，因此乱序响应可以正确关联。

### 流式传输

三家都支持流式工具调用。线路格式各不相同：

- **OpenAI。** `tool_calls[i].function.arguments` 的 delta 块增量到达。你累积数据直到 `finish_reason: "tool_calls"`。
- **Anthropic。** block-start / block-delta / block-stop 事件。`input_json_delta` 块携带部分参数。
- **Gemini。** `streamFunctionCallArguments`（Gemini 3 新增）发射带 `functionCallId` 的块，使多个并行调用可以交错传输。

Phase 13 · 03 深入讲解并行 + 流式重组。本课聚焦于声明和单次调用的形式。

### 错误和修复

无效参数错误的形态也不同。

- **OpenAI（非严格模式）。** 模型返回 `arguments: "{bad json}"`，你的 JSON 解析失败，你注入错误消息并重新调用。
- **OpenAI（严格模式）。** 验证在解码过程中发生；无效 JSON 不可能出现，但 `refusal` 可能出现。
- **Anthropic。** `input` 可能包含意外字段；Schema 是建议性的。需要服务端验证。
- **Gemini。** OpenAPI 3.0 的怪癖：`enum` 在对象字段上被静默忽略；需要自己验证。

### 转换器模式

你代码中的规范工具声明看起来像这样（你选择形式）：

```python
Tool(
    name="get_weather",
    description="Use when ...",
    input_schema={"type": "object", "properties": {...}, "required": [...]},
    strict=True,
)
```

三个小函数将它转换为三种提供商的形式。`code/main.py` 中的脚手架正是这样做的，然后通过每种提供商的响应形式往返一个伪工具调用。不需要网络 — 本课教你的是形式，不是 HTTP。

生产团队将这个转换器封装在 `AbstractToolset`（Pydantic AI）、`UniversalToolNode`（LangGraph）或 `BaseTool`（LlamaIndex）中。Phase 13 · 17 交付一个网关，在三者之上暴露 OpenAI 形式的 API。

## 使用方法

`code/main.py` 定义了一个规范的 `Tool` dataclass 和三个转换器，分别输出 OpenAI、Anthropic 和 Gemini 的声明 JSON。然后它解析每种提供商形式的手工构建响应，转换为相同的规范调用对象，证明它们在底层语义上完全一致。运行它，并行对比三种声明。

关注要点：

- 三个声明块仅在信封和字段名上有差异。
- 三个响应块在调用所处位置上不同（顶层 `tool_calls`、`content[]` block、`parts[]` 条目）。
- 一个 `canonical_call()` 函数从所有三种响应形式中提取 `{id, name, args}`。

## 交付产出

本课产出 `outputs/skill-provider-portability-audit.md`。给定一个针对某个提供商的 Function Calling 集成，该技能会生成可移植性审计：它依赖了哪些提供商限制、哪些字段需要重命名、以及移植到其他提供商时什么会出错。

## 练习

1. 运行 `code/main.py`，验证三种提供商的声明 JSON 都序列化了同一个底层 `Tool` 对象。修改规范工具以添加一个 enum 参数，确认只有 Gemini 转换器需要处理 OpenAPI 的怪癖。

2. 为每个提供商实现一个 `ListToolsResponse` 解析器，提取模型在 `list_tools` 或发现调用后返回的工具列表。OpenAI 原生没有这个功能；注意这种不对称性。

3. 实现 `tool_choice` 转换：将规范的 `ToolChoice(mode="force", tool_name="x")` 映射到所有三种提供商的形式。然后映射 `mode="any"` 和 `mode="none"`。查阅本课的对比表。

4. 选择三家提供商之一，从头到尾阅读其 Function Calling 指南。找出其 Schema 规范中其他两家不支持的一个字段。候选者：OpenAI 的 `strict`、Anthropic 的 `disable_parallel_tool_use`、Gemini 的 `function_calling_config.allowed_function_names`。

5. 编写一个测试向量：一个参数违反声明 Schema 的工具调用。通过每个提供商的验证器运行（Lesson 01 中的标准库实现可以作为代理），记录触发了哪些错误。记录你在生产环境中对严格性的要求会选择哪个提供商。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Function Calling（函数调用） | "Tool use" | 提供商级 API，用于输出结构化工具调用 |
| Tool Declaration（工具声明） | "Tool spec" | name + description + JSON Schema 输入载荷 |
| `tool_choice` | "强制 / 禁止" | Auto / required / none / specific-name 模式 |
| Strict Mode（严格模式） | "Schema 强制执行" | OpenAI 的标志，约束解码以匹配 Schema |
| `tool_use` block | "Anthropic 的调用形式" | 包含 id、name、input 的内联内容 block |
| `functionCall` part | "Gemini 的调用形式" | 包含 name、args 和 id 的 `parts[]` 条目 |
| 参数为字符串 | "JSON 字符串化" | OpenAI 将参数作为 JSON 字符串而非对象返回 |
| Parallel Tool Calls（并行工具调用） | "一轮中扇出" | 一条 assistant 消息中的多个工具调用 |
| Refusal（拒绝） | "模型拒绝" | 仅在严格模式下出现的拒绝 block，而非调用 |
| OpenAPI 3.0 子集 | "Gemini Schema 怪癖" | Gemini 使用一种与 JSON Schema 有细微差异的方言 |

## 延伸阅读

- [OpenAI — Function calling guide](https://platform.openai.com/docs/guides/function-calling) — 包括严格模式和并行调用的规范参考
- [Anthropic — Tool use overview](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview) — `tool_use` 和 `tool_result` block 语义
- [Google — Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling) — 并行调用、唯一 id 和 OpenAPI 子集
- [Vertex AI — Function calling reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling) — Gemini 的企业级界面
- [OpenAI — Structured outputs](https://platform.openai.com/docs/guides/structured-outputs) — 严格模式 Schema 强制执行细节