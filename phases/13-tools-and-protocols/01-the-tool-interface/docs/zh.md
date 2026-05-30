# 工具接口 — 为什么 Agent 需要结构化 I/O

> 语言模型生成 token，程序执行动作。两者之间的鸿沟就是工具接口：一个让模型请求动作、宿主执行动作的契约。2026 年的每个技术栈 — OpenAI、Anthropic 和 Gemini 的 Function Calling（函数调用）；MCP 的 `tools/call`；A2A 的 task parts — 都是同一个四步循环的不同编码方式。本课命名这个循环，并展示运行它的最小机制。

**类型：** Learn
**语言：** Python（stdlib，无 LLM）
**前置课程：** Phase 11（LLM 完成 API）
**时间：** ~45 分钟

## 学习目标

- 解释为什么只能生成文本的 LLM 无法独立对现实世界执行操作。
- 绘制四步工具调用循环（describe → decide → execute → observe）并说明每一步由谁负责。
- 将工具描述编写为三个部分：名称、JSON Schema 输入和确定性执行函数。
- 区分纯工具（pure tool）和有副作用的工具（consequential tool），并说明这种划分对安全性的意义。

## 问题

LLM 输出下一个 token 的概率分布。这就是它的全部输出界面。如果你问聊天模型"班加罗尔现在的天气怎么样"，它可以写出一句看似合理的回答，但它无法调用天气 API。这句回答可能碰巧正确，也可能是三天前的过时信息。

弥合这个鸿沟正是工具接口的目的。宿主程序 — 你的 Agent 运行时、Claude Desktop、ChatGPT、Cursor 或自定义脚本 — 向模型宣告一组可调用的工具。当模型判断需要执行某个动作时，它输出一个结构化载荷，指明工具名称和参数。宿主解析该载荷，实际运行工具，然后将结果反馈给模型。这个循环持续进行，直到模型决定不再需要调用为止。

这个契约的第一个版本于 2023 年 6 月随 OpenAI 的 `functions` 参数发布。Anthropic 随后在 Claude 2.1 中推出了 `tool_use` blocks。几个月后 Gemini 添加了 `functionDeclarations`。如今每个提供商都暴露相同的形式：输入一个 JSON Schema 类型化的工具列表，输出一个 JSON 载荷的工具调用。Model Context Protocol（模型上下文协议，2024 年 11 月）将这个契约泛化，使得一个工具注册表可以服务于所有模型。A2A（2026 年 4 月，v1.0）在此基础上叠加了 Agent 间委托的相同原语。

四步循环是所有这些方案背后的不变量。Phase 13 的其余内容都是对它的展开。

## 核心概念

### 第一步：描述（describe）

宿主用三个字段声明每个工具。

- **名称（Name）。** 稳定的、机器可读的标识符。`get_weather`，而非"weather thing"。
- **描述（Description）。** 一段自然语言的简要说明。"当用户询问某个城市的当前天气状况时使用。不用于历史数据。"
- **输入模式（Input Schema）。** 一个 JSON Schema 对象（draft 2020-12），描述工具的参数。

模型接收这个列表。现代提供商使用特定的模板将这些声明序列化到系统提示中，因此你作为调用者只需处理结构化表单。

### 第二步：决策（decide）

给定用户的消息和可用工具，模型选择以下三种行为之一。

1. **直接以文本回答。** 不调用工具。
2. **调用一个或多个工具。** 输出结构化的调用对象。在 `parallel_tool_calls: true`（OpenAI 和 Gemini 默认开启，Anthropic 需要显式启用）下，模型可以在一轮中发出多个调用。
3. **拒绝。** 严格模式的结构化输出可以生成一个类型化的 `refusal` block，而非调用。

工具调用载荷有三个稳定字段：调用 `id`、工具 `name` 和 JSON `arguments` 对象。id 的存在是为了让宿主能够将后续结果与特定调用关联，这在并行调用乱序返回时尤为重要。

### 第三步：执行（execute）

宿主接收调用，根据声明的模式验证参数，然后运行执行器。无效参数意味着模型产生了幻觉字段或使用了错误类型 — 这在弱模型上是非常常见的失败模式。生产环境的宿主在遇到无效参数时通常采取三种策略之一：快速失败并将错误呈现给模型、使用受限解析器修复 JSON，或在提示中包含验证错误信息后重试模型。

执行器本身是普通的代码。Python、TypeScript、shell 命令、数据库查询。它产生一个结果，通常是一个字符串，但也可以是任何 JSON 值或结构化内容块（MCP 中的 text、image 或 resource reference）。结果必须是可序列化的。

### 第四步：观察（observe）

宿主将工具结果追加到对话中（作为带有匹配 `id` 的 `tool` role message），然后重新调用模型。模型现在在上下文中有了工具输出，可以生成最终回答或请求更多调用。这个过程持续进行，直到模型停止发出调用，或宿主达到迭代次数的安全上限。

### 信任划分

工具在安全性方面有两种重要分类。

- **纯工具（Pure）。** 只读、确定性、无副作用。`get_weather`、`search_docs`、`get_current_time`。可以投机性地调用。
- **有副作用的工具（Consequential）。** 会改变状态、消耗资金、触及用户数据。`send_email`、`delete_file`、`execute_trade`。必须加以管控。

Meta 2026 年的 Agent 安全"二元法则"（Rule of Two）规定，单轮对话最多只能同时包含以下三项中的两项：不可信输入、敏感数据、有副作用的动作。工具接口正是你执行这条规则的地方 — 通过拒绝调用、要求用户确认或提升权限范围。详见 Phase 13 · 15 的完整安全章节和 Phase 14 · 09 的 Agent 级权限策略。

### 循环在哪里运行

| 场景 | 谁负责描述 | 谁负责决策 | 谁负责执行 |
|------|-----------|-----------|-----------|
| 单轮 Function Calling（OpenAI/Anthropic/Gemini） | 应用开发者 | LLM | 应用开发者 |
| MCP | MCP Server | LLM（通过 MCP Client） | MCP Server |
| A2A | Agent Card 发布者 | 调用方 Agent | 被调用方 Agent |
| 浏览器（Function Calling Agent） | 浏览器扩展 / WebMCP | LLM | 浏览器运行时 |

无论在哪里，都是相同的四步。列名在变；结构不变。

### 为什么不直接让模型输出 JSON？

"让模型以 JSON 格式回复"是 Function Calling 之前的模式。在前沿模型上它有 5% 到 15% 的失败率，在更小的模型上失败率更高。失败模式包括缺少花括号、尾部逗号、幻觉字段和类型错误。你随后需要 JSON 修复、重试或受限解码器。

原生 Function Calling 更好，原因有三。首先，提供商在精确的调用形式上对模型进行端到端训练，因此在严格模式下有效 JSON 率提升到 98% 到 99%。其次，调用载荷处于独立的协议槽中，而非自由文本内部 — 因此工具调用永远不会泄漏到用户可见的回复中。第三，提供商通过受限解码（OpenAI 的严格模式、Anthropic 的 `tool_use`、Gemini 的 `responseSchema`）强制执行模式合规性。输出保证通过验证。

Phase 13 · 02 会并行对比三个提供商的 API。Phase 13 · 04 深入讲解结构化输出。

### 断路器

循环在模型停止发出调用或宿主达到最大轮次时终止。生产环境的宿主将此设置为 5 到 20 轮之间。超出这个范围，你几乎可以确定陷入了模型无法退出的循环。Claude Code 默认 20 轮；OpenAI Assistants 默认 10 轮；Cursor 的 Agent 模式默认 25 轮。

无界循环的替代方案 — 每隔六个月就会以"Agent 一晚花了 400 美元 API 调用费"的复盘报告形式出现。不要在没有边界的情况下上线。

Phase 14 · 12 深入讲解错误恢复和自愈机制；Phase 17 讲解生产环境的速率限制。

### Phase 13 的后续路线

- 第 02 到 05 课打磨提供商级的工具调用界面。
- 第 06 到 14 课将循环泛化为 MCP。
- 第 15 到 18 课防御恶意服务器、对抗性用户和未认证的远程授权接口。
- 第 19 到 22 课将模式扩展到 Agent 间协作、可观测性、路由和打包。
- 第 23 课使用所有原语交付一个完整的生态系统。

后续每一课都是这个四步循环的展开。请将它作为不变量记在脑中。

## 使用方法

`code/main.py` 在没有 LLM 的情况下运行四步循环。一个伪"决策者"函数通过模式匹配用户消息来模拟模型；执行器、模式验证器和观察步骤的脚手架是真实的。运行它来查看带有可打印中间状态的完整请求/响应编排，然后在后续课程中用真实的提供商替换伪决策者。

关注要点：

- 工具注册表为每个工具保存三个字段：name、description、schema 和一个 executor 引用。
- 验证器是一个最小子集的 JSON Schema 实现（类型、required、enum、min/max），仅用标准库编写。Phase 13 · 04 会提供更完整的版本。
- 循环将迭代次数限制为五次。生产环境的 Agent 恰好需要这种断路器。

## 交付产出

本课产出 `outputs/skill-tool-interface-reviewer.md`。给定一个草拟的工具定义（name + description + schema + executor 概要），该技能会审计其循环适配性：名称是否机器稳定、描述是否是完整的使用说明、模式是否正确使用了 JSON Schema 2020-12，以及纯工具与有副作用工具的分类是否明确。

## 练习

1. 在 `code/main.py` 中添加第四个工具 `get_stock_price(ticker)`。将其描述编写为"当用户按股票代码询问当前股价时使用。不用于历史价格或市场概览。"运行脚手架，确认伪决策者将提到股票代码的查询路由到新工具。

2. 故意破坏模式验证器。传入一个 `arguments` 对象缺少必填字段的调用，确认宿主在执行前拒绝它。然后传入一个包含额外未知字段的调用。做出决定：宿主应该拒绝还是忽略？用安全论证来证明你的选择。

3. 将脚手架中的每个工具分类为纯工具或有副作用的工具。为需要的注册表条目添加 `consequential: true` 标志，并修改循环使其在选择有副作用的工具时打印"将与用户确认"一行。这就是每个生产环境宿主所需的确认门控的形态。

4. 在纸上绘制四步循环，用上表中的提供商列为你喜欢的客户端（Claude Desktop、Cursor、ChatGPT 或自定义技术栈）填写。与 Phase 13 · 06 中 MCP 特定的变体进行交叉参照。

5. 从头到尾阅读 OpenAI 的 Function Calling 指南。找出存在于请求中但不在本文四步循环中的那个字段。解释它增加了什么，以及为什么它是便利的而非必要的。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Tool（工具） | "模型可以调用的东西" | name + JSON Schema 类型化输入 + executor 函数的三元组 |
| Function Calling（函数调用） | "原生工具使用" | 提供商级 API 支持，用于输出结构化工具调用而非自由文本 |
| Tool Call（工具调用） | "模型的动作请求" | 由模型输出的包含 `id`、`name`、`arguments` 的 JSON 载荷 |
| Tool Result（工具结果） | "工具返回的内容" | 执行器的输出，包裹在带有匹配 id 的 `tool` role message 中 |
| Parallel Tool Calls（并行工具调用） | "同时发出多个调用" | 一轮模型输出中的多个调用对象，彼此独立且可按 id 排序 |
| Strict Mode（严格模式） | "保证有效 JSON" | 受限解码，强制模型输出符合声明的模式 |
| Pure Tool（纯工具） | "只读工具" | 无副作用；可安全重跑 |
| Consequential Tool（有副作用的工具） | "动作工具" | 会改变外部状态；需要门控、审计或用户确认 |
| Four-step Loop（四步循环） | "工具调用周期" | describe → decide → execute → observe |
| Host（宿主） | "Agent 运行时" | 持有工具注册表、调用模型并运行执行器的程序 |

## 延伸阅读

- [OpenAI — Function calling guide](https://platform.openai.com/docs/guides/function-calling) — OpenAI 风格工具声明和调用形式的规范参考
- [Anthropic — Tool use overview](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview) — Claude 的 `tool_use` / `tool_result` block 格式
- [Google — Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling) — Gemini 的 `functionDeclarations` 和并行调用语义
- [Model Context Protocol — Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) — 工具接口的提供商无关泛化方案
- [JSON Schema — 2020-12 release notes](https://json-schema.org/draft/2020-12/release-notes) — 每个现代工具 API 所使用的模式方言