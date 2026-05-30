# 结构化输出 — JSON Schema、Pydantic、Zod、受限解码

> "好好让模型返回 JSON"在前沿模型上也有 5% 到 15% 的失败率。结构化输出通过受限解码来弥合这个差距：模型在解码时被物理性地阻止发出违反 Schema 的 token。OpenAI 的严格模式、Anthropic 的 Schema 类型化工具使用、Gemini 的 `responseSchema`、Pydantic AI 的 `output_type` 和 Zod 的 `.parse` 是同一个思想的五种表面形式。本课构建 Schema 验证器和严格模式契约，学习者将在每个生产环境的提取管道中使用它们。

**类型：** Build
**语言：** Python（stdlib，JSON Schema 2020-12 子集）
**前置课程：** Phase 13 · 02（Function Calling 深入解析）
**时间：** ~75 分钟

## 学习目标

- 使用正确的约束（enum、min/max、required、pattern）为提取目标编写 JSON Schema 2020-12。
- 解释严格模式和受限解码为什么提供与"生成后验证"不同的保证。
- 区分三种失败模式：解析错误、Schema 违规、模型拒绝。
- 交付一个带有类型化修复和类型化拒绝处理的提取管道。

## 问题

一个读取采购订单邮件的 Agent 需要将自由文本转换为 `{customer, line_items, total_usd}`。三种方法。

**方法一：提示返回 JSON。** "以 JSON 格式回复，包含字段 customer、line_items、total_usd。"在前沿模型上 85% 到 95% 的情况下有效。六种失败方式：缺少花括号、尾部逗号、类型错误、幻觉字段、在 token 限制处截断、泄漏散文如"Here is your JSON:"。

**方法二：生成后验证。** 自由生成，解析，对照 Schema 验证，失败时重试。可靠但昂贵 — 每次重试都要付费，截断 bug 每次都会多花一轮。

**方法三：受限解码。** 提供商在解码时强制执行 Schema。无效 token 从采样分布中被屏蔽。输出保证可解析且保证可验证。失败被压缩为一种模式：拒绝（模型决定输入不符合 Schema）。

2026 年的每个前沿提供商都提供了方法三的某种形式。

- **OpenAI。** `response_format: {type: "json_schema", strict: true}` 加上模型拒绝时的 `refusal` 字段。
- **Anthropic。** 对 `tool_use` 输入的 Schema 强制执行；`stop_reason: "refusal"` 不存在，但无工具调用的 `end_turn` 就是信号。
- **Gemini。** 请求级的 `responseSchema`；2026 年 Gemini 为选定类型提供 token 级语法约束。
- **Pydantic AI。** `output_type=InvoiceModel` 输出类型化为 `InvoiceModel` 的结构化 `RunResult`。
- **Zod（TypeScript）。** 运行时解析器，对照 Zod Schema 验证提供商输出；配合 OpenAI 的 `beta.chat.completions.parse` 使用。

共同主线：声明一次 Schema，端到端强制执行。

## 核心概念

### JSON Schema 2020-12 — 通用语言

每个提供商都接受 JSON Schema 2020-12。你最常用的构造：

- `type`：`object`、`array`、`string`、`number`、`integer`、`boolean`、`null` 之一。
- `properties`：字段名到子 Schema 的映射。
- `required`：必须出现的字段名列表。
- `enum`：允许值的封闭集合。
- `minimum` / `maximum`（数字）、`minLength` / `maxLength` / `pattern`（字符串）。
- `items`：应用于每个数组元素的子 Schema。
- `additionalProperties`：`false` 禁止额外字段（默认值因模式而异）。

OpenAI 严格模式增加了三个要求：每个属性都必须列在 `required` 中、所有层级都必须设 `additionalProperties: false`、不允许未解析的 `$ref`。违反这些规则时，API 在请求时返回 400。

### Pydantic — Python 绑定

Pydantic v2 通过 `model_json_schema()` 从 dataclass 形状的模型生成 JSON Schema。Pydantic AI 封装了这个过程，你只需编写：

```python
class Invoice(BaseModel):
    customer: str
    line_items: list[LineItem]
    total_usd: Decimal
```

Agent 框架在边界层将 Schema 转换为 OpenAI 严格模式、Anthropic `input_schema` 或 Gemini `responseSchema`。模型的输出作为类型化的 `Invoice` 实例返回。验证错误抛出带有类型化错误路径的 `ValidationError`。

### Zod — TypeScript 绑定

Zod（`z.object({customer: z.string(), ...})`）是 TypeScript 的等价物。OpenAI 的 Node SDK 提供 `zodResponseFormat(Invoice)`，将其转换为 API 的 JSON Schema 载荷。

### 拒绝

严格模式无法强制模型回答。如果输入无法适配 Schema（"邮件是一首诗，不是发票"），模型会输出一个包含原因的 `refusal` 字段。你的代码必须将此作为一等公民的结果来处理，而非失败。拒绝也可以作为安全信号使用：要求模型从受保护内容的邮件中提取信用卡号时，模型会返回附带安全原因的拒绝。

### 开源的受限解码

开源权重实现使用三种技术。

1. **基于语法的解码**（`outlines`、`guidance`、`lm-format-enforcer`）：从 Schema 构建确定性有限自动机；在每一步屏蔽会违反 FSM 的 token 的 logits。
2. **使用 JSON 解析器的 Logit 屏蔽**：与模型同步运行流式 JSON 解析器；在每一步计算有效的下一 token 集合。
3. **带验证器的推测解码**：廉价的草案模型提出 token，验证器强制执行 Schema。

商业提供商在幕后选择其中一种。2026 年的技术水平对于短的结构化输出比普通生成更快，对于长的输出速度大致相同。

### 三种失败模式

1. **解析错误。** 输出不是有效的 JSON。严格模式下不可能发生。在非严格提供商上仍可能发生。
2. **Schema 违规。** 输出可解析但违反 Schema。严格模式下不可能发生。在严格模式外很常见。
3. **拒绝。** 模型拒绝执行。必须作为类型化的结果来处理。

### 重试策略

当你在严格模式之外时（Anthropic 工具使用、非严格 OpenAI、旧版 Gemini），恢复模式是：

```
生成 -> 解析 -> 验证 -> 如果失败，注入错误并重试，最多 3 次
```

一次重试通常就够了。三次重试捕获弱模型的不稳定。超过三次说明 Schema 有问题：模型对某些输入无法满足它，提示或 Schema 需要修复。

### 小模型支持

受限解码在小模型上也有效。一个 30 亿参数的开源模型配合语法强制执行，在结构化任务上优于一个 700 亿参数的模型配合原始提示。这是结构化输出对生产环境至关重要的主要原因：它将可靠性与模型大小解耦。

## 使用方法

`code/main.py` 在标准库中提供了一个最简的 JSON Schema 2020-12 验证器（类型、required、enum、min/max、pattern、items、additionalProperties）。它封装了一个 `Invoice` Schema，并将一个伪造的 LLM 输出通过验证器运行，演示解析错误、Schema 违规和拒绝路径。在生产环境中将伪造输出替换为任何提供商的真实响应。

关注要点：

- 验证器返回一个类型化的 `[ValidationError]` 列表，包含路径和消息。这就是你需要呈现给重试提示的形式。
- 拒绝分支不会重试。它记录并返回一个类型化的拒绝。Phase 14 · 09 将拒绝用作安全信号。
- `additionalProperties: false` 检查在对抗性测试输入上触发，展示了严格模式如何阻止幻觉字段。

## 交付产出

本课产出 `outputs/skill-structured-output-designer.md`。给定一个自由文本提取目标（发票、支持工单、简历等），该技能生成一个兼容严格模式的 JSON Schema 2020-12 和一个与其镜像的 Pydantic 模型，带有类型化拒绝和重试处理的桩代码。

## 练习

1. 运行 `code/main.py`。添加第四个测试用例，其 `total_usd` 为负数。确认验证器使用 `minimum` 约束路径拒绝它。

2. 扩展验证器以支持带鉴别器的 `oneOf`。常见情况：`line_item` 是产品或服务，由 `kind` 标签区分。严格模式在这里有微妙规则；查阅 OpenAI 的结构化输出指南。

3. 将相同的 Invoice Schema 编写为 Pydantic BaseModel，并比较 `model_json_schema()` 输出与你手写的 Schema。找出 Pydantic 默认设置但手写版本遗漏的那个字段。

4. 测量拒绝率。构建十个不应被提取的输入（歌词、数学证明、空邮件），使用严格模式在真实提供商上运行。统计拒绝与幻觉输出的数量。这是你拒绝感知重试的基础事实。

5. 从头到尾阅读 OpenAI 的结构化输出指南。找出它在严格模式中明确禁止但普通 JSON Schema 允许的那个构造。然后设计一个非必要地使用该禁止构造的 Schema，并将其重构为严格兼容。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| JSON Schema 2020-12 | "Schema 规范" | IETF 草案 Schema 方言，每个现代提供商都支持 |
| Strict Mode（严格模式） | "保证 Schema" | OpenAI 的标志，通过受限解码强制执行 Schema |
| Constrained Decoding（受限解码） | "Logit 屏蔽" | 解码时强制执行，屏蔽无效的下一 token |
| Refusal（拒绝） | "模型拒绝" | 输入无法适配 Schema 时的类型化结果 |
| Parse Error（解析错误） | "无效 JSON" | 输出未能解析为 JSON；严格模式下不可能发生 |
| Schema Violation（Schema 违规） | "形式错误" | 已解析但违反类型 / required / enum / 范围 |
| `additionalProperties: false` | "不允许额外字段" | 禁止未知字段；OpenAI 严格模式必须 |
| Pydantic BaseModel | "类型化输出" | 生成和验证 JSON Schema 的 Python 类 |
| Zod Schema | "TypeScript 输出类型" | 用于提供商输出验证的 TS 运行时 Schema |
| Grammar Enforcement（语法强制执行） | "开源受限解码" | 基于 FSM 的 logit 屏蔽，如 outlines / guidance |

## 延伸阅读

- [OpenAI — Structured outputs](https://platform.openai.com/docs/guides/structured-outputs) — 严格模式、拒绝和 Schema 要求
- [OpenAI — Introducing structured outputs](https://openai.com/index/introducing-structured-outputs-in-the-api/) — 2024 年 8 月发布文章，解释解码保证
- [Pydantic AI — Output](https://ai.pydantic.dev/output/) — 序列化到每个提供商的类型化 output_type 绑定
- [JSON Schema — 2020-12 release notes](https://json-schema.org/draft/2020-12/release-notes) — 规范性规范
- [Microsoft — Structured outputs in Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) — 企业部署说明和严格模式注意事项