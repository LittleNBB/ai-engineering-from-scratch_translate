# 并行工具调用与工具流式传输

> 三次独立的天气查询如果串行执行，就是三次往返。并行运行，总时间缩短为最慢的那一次调用。如今每个前沿提供商都能在单轮中发出多个工具调用。收益是真实的；实现细节则相当微妙。本课同时讲解两个方面：并行扇出和流式参数重组，重点讲解 id 关联陷阱。

**类型：** Build
**语言：** Python（stdlib，线程池 + 流式脚手架）
**前置课程：** Phase 13 · 02（Function Calling 深入解析）
**时间：** ~75 分钟

## 学习目标

- 解释 `parallel_tool_calls: true` 为何存在以及何时应禁用它。
- 在并行扇出期间将流式参数块关联到正确的工具调用 id。
- 在不提前解析的情况下将部分 `arguments` 字符串重组为完整的 JSON。
- 运行三城市天气基准测试，展示串行与并行的延迟对比。

## 问题

没有并行调用时，一个回答"班加罗尔、东京和苏黎世的天气如何"的 Agent 会这样执行：

```
user -> LLM
LLM -> 调用 get_weather(Bengaluru)
host -> 运行执行器，返回结果
LLM -> 调用 get_weather(Tokyo)
host -> 运行执行器，返回结果
LLM -> 调用 get_weather(Zurich)
host -> 运行执行器，返回结果
LLM -> 最终文本回答
```

三次 LLM 往返，每次还要承担执行器延迟。大约是理想墙钟时间的 4 倍。

使用并行调用：

```
user -> LLM
LLM -> 调用 get_weather(Bengaluru); 调用 get_weather(Tokyo); 调用 get_weather(Zurich)
host -> 并发运行所有三个执行器，返回三个结果
LLM -> 最终文本回答
```

一次 LLM 往返。执行器耗时是三者中的最大值，而非总和。在 OpenAI、Anthropic 和 Gemini 上的生产基准测试显示，扇出工作负载的墙钟时间减少了 60% 到 70%。

代价是关联复杂性。当三个调用乱序完成时，你的结果必须携带匹配的 `tool_call_id`，以便模型能够正确排列。当结果以流式传输时，你必须在执行前将部分参数片段组装成完整的 JSON。Gemini 3 添加唯一 id 的部分原因就是为了解决一个现实问题：两个对同一工具的并行调用无法区分。

## 核心概念

### 启用并行

- **OpenAI。** `parallel_tool_calls: true` 默认开启。设为 `false` 强制串行。
- **Anthropic。** 通过 `disable_parallel_tool_use: false` 启用并行（Claude 3.5 及以上默认）。设为 `true` 为串行。
- **Gemini。** 始终支持并行；`tool_config.function_calling_config.mode = "AUTO"` 让模型自行决定。

当工具存在顺序依赖关系（先 `create_file` 再 `write_file`）、一个调用的输出作为另一个调用的输入、或速率限制器无法处理扇出时，应禁用并行。

### Id 关联

模型发出的每个调用都有一个 `id`。宿主返回的每个结果都必须包含相同的 id。否则结果就是模糊的。

- **OpenAI。** 每条 tool-role 消息上的 `tool_call_id`。
- **Anthropic。** 每个 `tool_result` block 上的 `tool_use_id`。
- **Gemini。** 每个 `functionResponse` 上的 `id`（Gemini 3 及以上；Gemini 2 通过名称匹配，这对同名并行调用会出问题）。

### 并发运行调用

宿主在独立的线程、协程或远程 worker 上运行每个调用的执行器。最简单的脚手架使用线程池；生产环境使用 asyncio 配合 `asyncio.gather` 或结构化并发。完成顺序不可预测 — id 是标识符。

一个常见 bug：按调用列表顺序而非完成顺序回复结果。这通常能工作，因为模型只关心 `tool_call_id`，但如果结果丢失或重复，乱序提交会使调试更困难。建议按完成顺序回复，并显式标注 id。

### 流式工具调用

当模型以流式传输时，`arguments` 以片段到达。三个并行调用的三组独立流块在传输线上交错。你需要为每个 id 准备一个累积器。

各提供商的形式：

- **OpenAI。** 每个块是 `choices[0].delta.tool_calls[i].function.arguments`（部分字符串）。块携带 `index`（在调用列表中的位置）。你按 index 累积，首次出现时读取 `id`，当 `finish_reason = "tool_calls"` 时解析 JSON。
- **Anthropic。** 流事件为 `message_start`，然后每个 block 一个 `content_block_start`，类型为 `tool_use`（包含 id、name、空 input）。`content_block_delta` 事件携带 `input_json_delta` 块。`content_block_stop` 关闭每个 block。
- **Gemini。** `streamFunctionCallArguments`（Gemini 3 及以上）发射带 `functionCallId` 的块，使调用可以清晰交错。Gemini 3 之前，流式传输一次返回一个完整调用。

### 部分 JSON 与过早解析陷阱

在 `arguments` 完成之前你无法解析它。部分 JSON 如 `{"city": "Beng` 是无效的，会抛出异常。正确的信号门是提供商的调用结束信号：OpenAI 的 `finish_reason = "tool_calls"`、Anthropic 的 `content_block_stop`、或 Gemini 的流结束事件。只有在此之后才尝试 `json.loads`。更稳健的方法是使用增量 JSON 解析器，在结构完成时产生事件；OpenAI 的流式指南推荐此方法用于显示实时"思考"指示器的 UX。花括号计数作为完整性测试是不可靠的（引号字符串或转义内容中的花括号会导致误报），应仅作为非正式的调试启发式方法使用。

### 乱序完成

```
call_A: 快速 API，最先返回
call_B: 慢速 API，第二个返回
call_C: 中等 API，第三个返回
```

宿主的回复仍然必须引用 id：

```
[{role: "tool", tool_call_id: "call_A", content: ...},
 {role: "tool", tool_call_id: "call_B", content: ...},
 {role: "tool", tool_call_id: "call_C", content: ...}]
```

在 OpenAI 或 Anthropic 上，回复顺序对正确性没有影响。Gemini 接受任何顺序，只要 id 匹配。

### 基准测试：串行 vs 并行

`code/main.py` 中的脚手架模拟了三个延迟分别为 400、600 和 800 毫秒的执行器。串行总耗时 1800 毫秒。并行耗时 max(400, 600, 800) = 800 毫秒。差异是常数而非比例的，因此节省量随工具数量增加而增长。

现实中的注意事项：并行调用会给下游 API 带来压力。对一个有速率限制的服务进行 10 路扇出会失败。Phase 13 · 17 讲解网关级的背压机制；重试语义计划在未来阶段中讲解。

### 流式扇出的墙钟时间

如果模型本身以流式传输，你可以在一个调用的参数完成后立即开始执行，而不必等待所有调用全部完成。这是 OpenAI 记录的一种优化，但并非所有 SDK 都暴露。本课的脚手架实现了这一点：一旦模拟流产生了完整的参数对象，宿主就立即启动该调用。

## 使用方法

`code/main.py` 分为两部分。第一部分使用 `concurrent.futures.ThreadPoolExecutor` 顺序和并行地运行三个模拟天气调用，并打印墙钟时间。第二部分重放一个假的流式响应 — 三个并行调用的 `arguments` 块在同一条流上交错 — 并使用 `StreamAccumulator` 按 id 重组它们。无需 LLM，无需网络，只专注于重组逻辑。

关注要点：

- 顺序计时器达到 1.8 秒。并行计时器在相同的假延迟下达到 0.8 秒。
- 累积器通过按 id 缓冲来处理乱序到达的块，仅在每个调用的 JSON 完成时才解析。
- 一旦某个 id 的参数完成，执行器就立即启动，而非等待所有流结束。

## 交付产出

本课产出 `outputs/skill-parallel-call-safety-check.md`。给定一个工具注册表，该技能审计哪些工具可以安全并行化、哪些有顺序依赖关系、哪些会使下游速率限制不堪重负 — 返回一个带有每个工具 `parallel_safe` 标志的修订注册表。

## 练习

1. 运行 `code/main.py` 并更改模拟延迟。确认并行与串行的比率约为 `max/sum`（实际运行由于线程调度、序列化和脚手架开销会略微偏离理想值）。在什么延迟分布下并行不再有意义？

2. 扩展累积器以处理"调用在流式传输中途被取消"的情况，丢弃其缓冲区并发出 `cancelled` 事件。哪个提供商的文档明确记录了这种情况？查看 Anthropic 的 `content_block_stop` 语义和 OpenAI 的 `finish_reason: "length"` 行为。

3. 用 `asyncio.gather` 替换线程池。对比两者的基准测试。你应该会看到 async 有小幅优势，因为上下文切换成本更低，但仅当执行器执行真实 I/O 时才有效。

4. 选择两个不应并行化的工具（例如 `create_file` 然后 `write_file`）。向注册表添加一个 `ordering_dependency` 图，并基于该图对并行扇出进行门控。这是依赖感知调度的最小机制，未来的 Agent 工程阶段会将其正式化。

5. 阅读 OpenAI 的并行 Function Calling 部分和 Anthropic 的 `disable_parallel_tool_use` 文档。找出 Anthropic 建议禁用并行的那一种现实工具类型。（提示：对同一资源的有副作用变更。）

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Parallel Tool Calls（并行工具调用） | "一轮中扇出" | 模型在一条 assistant 消息中发出多个工具调用 |
| `parallel_tool_calls` | "OpenAI 的标志" | 启用或禁用多调用输出 |
| `disable_parallel_tool_use` | "Anthropic 的反向标志" | 退出标志；默认并行启用 |
| Tool Call ID（工具调用 id） | "关联句柄" | 结果消息必须回显的每次调用标识符 |
| Accumulator（累积器） | "流缓冲区" | 用于部分 `arguments` 块的 per-id 字符串缓冲区 |
| Out-of-order Completion（乱序完成） | "最快的先到" | 并行调用以不可预测的顺序完成；id 是粘合剂 |
| Dependency Graph（依赖图） | "顺序约束" | 输出作为其他工具输入的工具；不能并行化 |
| Parse-early Trap（过早解析陷阱） | "JSON.parse 爆了" | 尝试解析不完整的 `arguments` 字符串 |
| `streamFunctionCallArguments` | "Gemini 3 特性" | 每次调用带唯一 id 的流式参数块 |
| Completion-order Reply（完成顺序回复） | "不用等所有结果" | 结果到达后立即回复，按 id 键控 |

## 延伸阅读

- [OpenAI — Parallel function calling](https://platform.openai.com/docs/guides/function-calling#parallel-function-calling) — 默认行为和退出标志
- [Anthropic — Tool use: implementing tool use](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implementing-tool-use) — `disable_parallel_tool_use` 和结果批处理
- [Google — Gemini function calling parallel section](https://ai.google.dev/gemini-api/docs/function-calling) — Gemini 3 起的 id 关联并行调用
- [OpenAI — Streaming responses with tools](https://platform.openai.com/docs/api-reference/responses-streaming) — OpenAI 流的块参数重组
- [Anthropic — Streaming messages](https://docs.anthropic.com/en/api/messages-streaming) — 带 `input_json_delta` 的 `content_block_delta`