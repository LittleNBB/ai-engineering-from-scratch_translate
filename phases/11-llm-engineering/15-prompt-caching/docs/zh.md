# 提示缓存与上下文缓存

> 你的系统提示是 4,000 token。你的 RAG 上下文是 20,000 token。你每次都发送两者。你也每次都为此付费——每次。提示缓存让提供商在其端保持该前缀的热度，并在复用时只收取正常费率的 10%。正确使用时，它可以将推理成本降低 50-90%，将首个 token 延迟降低 40-85%。

**类型:** Build
**语言:** Python
**前置课程:** Phase 11 · 01 (提示工程), Phase 11 · 05 (上下文工程), Phase 11 · 11 (缓存与成本)
**时间:** ~60 分钟

## 问题

一个编码代理在对话的每一轮都向 Claude 发送相同的 15,000 token 系统提示。20 轮对话，按 $3/M 输入 token 计算，仅输入成本就是 $0.90——还没算用户的实际消息。乘以每天 10,000 个对话，账单就达到每天 $9,000，用于从未改变的文本。

你无法在不损害质量的情况下缩减提示。你无法避免发送它——模型每轮都需要它。唯一的办法是停止为提供商已经见过的前缀支付全价。

这个办法就是提示缓存。Anthropic 在 2024 年 8 月发布了它（2025 年增加了 1 小时扩展 TTL 变体），OpenAI 在同年底将其自动化，Google 在 Gemini 1.5 时发布了显式上下文缓存，三者现在都将其作为前沿模型的一等功能提供。

## 概念

![Prompt caching: write once, read cheap](../assets/prompt-caching.svg)

**机制。** 当请求的前缀与最近请求的前缀匹配时，提供商从前一次运行中提供 KV 缓存，而不是重新编码 token。你第一次支付少量写入溢价，之后每次支付大量读取折扣。

**2026 年三种提供商风格。**

| 提供商 | API 风格 | 命中折扣 | 写入溢价 | 默认 TTL | 最小可缓存 |
|--------|---------|---------|---------|---------|-----------|
| Anthropic | 在内容块上显式 `cache_control` 标记 | 输入 90% 折扣 | 25% 附加费 | 5 分钟（可延长至 1 小时） | 1,024 token (Sonnet/Opus), 2,048 (Haiku) |
| OpenAI | 自动前缀检测 | 输入 50% 折扣 | 无 | 最长 1 小时（尽力而为） | 1,024 token |
| Google (Gemini) | 显式 `CachedContent` API | 按存储计费；读取约为正常的 25% | 每 token·小时存储费 | 用户设置（默认 1 小时） | 4,096 token (Flash), 32,768 (Pro) |

**不变量。** 三者都只缓存前缀。如果请求之间的任何 token 不同，第一个不同 token 之后的所有内容都是未命中。将*稳定*的部分放在顶部，*可变*的部分放在底部。

### 缓存友好的布局

```
[system prompt]          <-- 缓存这个
[tool definitions]       <-- 缓存这个
[few-shot examples]      <-- 缓存这个
[retrieved documents]    <-- 如果重用则缓存，否则不
[conversation history]   <-- 缓存到上一轮
[current user message]   <-- 永远不缓存（每次都不同）
```

违反顺序——将用户消息放在系统提示之上，在少样本示例之间穿插动态检索——缓存永远不会命中。

### 盈亏平衡计算

Anthropic 的 25% 写入溢价意味着缓存的块至少需要被读取两次才能净省钱。1 次写入 + 1 次读取平均每次请求 0.675 倍成本（节省 32%）；1 次写入 + 10 次读取平均 0.205 倍（节省 80%）。经验法则：缓存你期望在 TTL 内至少重用 3 次的任何内容。

## 构建它

### 步骤 1：带显式标记的 Anthropic 提示缓存

```python
import anthropic

client = anthropic.Anthropic()

SYSTEM = [
    {
        "type": "text",
        "text": "You are a senior Python reviewer. Follow the rubric exactly.\n\n" + RUBRIC_15K_TOKENS,
        "cache_control": {"type": "ephemeral"},
    }
]

def review(code: str):
    return client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": code}],
    )
```

`cache_control` 标记告诉 Anthropic 存储该块 5 分钟。在该窗口内重用会命中；之后过期并重新写入。

**响应使用字段：**

```python
response = review(code_a)
response.usage
# InputTokensUsage(
#     input_tokens=120,
#     cache_creation_input_tokens=15023,   # 按 1.25 倍付费
#     cache_read_input_tokens=0,
#     output_tokens=340,
# )

response_b = review(code_b)
response_b.usage
# cache_creation_input_tokens=0
# cache_read_input_tokens=15023           # 按 0.1 倍付费
```

在 CI 中检查两个字段——如果 `cache_read_input_tokens` 在请求间一直为零，你的缓存键在漂移。

### 步骤 2：一小时扩展 TTL

对于长时间运行的批处理作业，5 分钟默认值在作业之间过期。设置 `ttl`：

```python
{"type": "text", "text": RUBRIC, "cache_control": {"type": "ephemeral", "ttl": "1h"}}
```

1 小时 TTL 的写入溢价是 2 倍（50% 超基线而非 25%），但对于任何重用前缀超过 5 次的批处理来说，回报很快。

### 步骤 3：OpenAI 自动缓存

OpenAI 不需要你配置任何东西。超过 1,024 token 的任何前缀匹配最近请求会自动获得 50% 折扣。

```python
from openai import OpenAI
client = OpenAI()

resp = client.chat.completions.create(
    model="gpt-5",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},   # 长且稳定
        {"role": "user", "content": user_msg},
    ],
)
resp.usage.prompt_tokens_details.cached_tokens  # 折扣部分
```

同样的缓存友好布局规则适用。有两件事会破坏 OpenAI 的缓存但不会破坏 Anthropic 的：更改 `user` 字段（用作缓存键组件）和重新排序工具。

### 步骤 4：Gemini 显式上下文缓存

Gemini 将缓存视为你创建和命名的一等对象：

```python
from google import genai
from google.genai import types

client = genai.Client()

cache = client.caches.create(
    model="gemini-3-pro",
    config=types.CreateCachedContentConfig(
        display_name="rubric-v3",
        system_instruction=RUBRIC,
        contents=[FEW_SHOT_EXAMPLES],
        ttl="3600s",
    ),
)

resp = client.models.generate_content(
    model="gemini-3-pro",
    contents=["Review this code:\n" + code],
    config=types.GenerateContentConfig(cached_content=cache.name),
)
```

Gemini 对缓存存续期间按每 token·小时收取存储费，读取约为正常输入费率的 25%。当你在数天内跨多个会话重用同一个巨大提示时，这是正确的形态。

### 步骤 5：在生产中测量命中率

参见 `code/main.py` 获取模拟的三提供商会计器，跟踪写入/读取/未命中计数并计算每 1K 请求的混合成本。根据目标命中率门控部署——大多数生产 Anthropic 设置在预热后应看到 >80% 的读取比例。

## 2026 年仍然存在的陷阱

- **顶部的动态时间戳。** 系统提示顶部的 `"Current time: 2026-04-22 15:30:02"`。每个请求都未命中。将时间戳移到缓存断点下方。
- **工具重排序。** 以稳定顺序序列化工具——部署间的字典重排会破坏每次命中。
- **自由文本近似重复。** "You are helpful." vs "You are a helpful assistant." ——一字节差异 = 完全未命中。
- **太小的块。** Anthropic 强制 1,024 token 的下限（Haiku 为 2,048）。更小的块静默不缓存。
- **盲目的成本仪表板。** 将"输入 token"分为缓存和非缓存。否则流量下降看起来像是缓存成功。

## 使用它

2026 年缓存技术栈：

| 场景 | 选择 |
|------|------|
| 带稳定 10k+ 系统提示的代理，多轮对话 | Anthropic `cache_control`，5 分钟 TTL |
| 重用前缀超过 30 分钟的批处理作业 | Anthropic，`ttl: "1h"` |
| GPT-5 上的无服务器端点，无自定义基础设施 | OpenAI 自动（只需让你的前缀稳定且长） |
| 大型代码/文档语料库的多日重用 | Gemini 显式 `CachedContent` |
| 跨提供商降级 | 保持可缓存前缀布局在各提供商间相同，以便任何命中都有效 |

与语义缓存（Phase 11 · 11）结合用于用户消息层：提示缓存处理*token 相同*的重用，语义缓存处理*含义相同*的重用。

## 交付它

保存 `outputs/skill-prompt-caching-planner.md`：

```markdown
---
name: prompt-caching-planner
description: Design a cache-friendly prompt layout and pick the right provider caching mode.
version: 1.0.0
phase: 11
lesson: 15
tags: [llm-engineering, caching, cost]
---

给定一个提示（系统 + 工具 + 少样本 + 检索 + 历史 + 用户）和使用配置（每小时请求数、所需 TTL、提供商），输出：

1. 布局。重新排序的节，标记单个缓存断点；解释哪些节是稳定的，哪些是易变的。
2. 提供商模式。Anthropic cache_control、OpenAI 自动或 Gemini CachedContent。从 TTL 和重用模式说明理由。
3. 盈亏平衡。TTL 内每次写入的预期读取次数；与无缓存的成本对比及数学计算。
4. 验证计划。CI 断言第二次相同请求时 cache_read_input_tokens > 0；仪表板按缓存/非缓存 token 分开。
5. 故障模式。列出此设置中最可能导致缓存未命中的三个原因（动态时间戳、工具重排、近似重复文本）以及你将如何防止每个。

拒绝发布将动态字段放在断点之上的缓存计划。拒绝在没有使 2 倍写入溢价回本的重用计数的情况下启用 1 小时 TTL。
```

## 练习

1. **简单。** 使用 5,000 token 系统提示对 Claude 进行 10 轮对话。分别在有无 `cache_control` 的情况下运行。报告每次的输入 token 账单。
2. **中等。** 编写一个测试工具，给定提示模板和请求日志，计算每个提供商（Anthropic 5 分钟、Anthropic 1 小时、OpenAI 自动、Gemini 显式）的预期命中率和美元节省。
3. **困难。** 构建布局优化器：给定一个提示和标记为 `stable=True/False` 的字段列表，重写提示以在不丢失信息的情况下将单个缓存断点放在最大缓存友好位置。在真实 Anthropic 端点上验证。

## 关键术语

| 术语 | 人们怎么说 | 它的实际含义 |
|------|-----------|-------------|
| Prompt caching | "让长提示变便宜" | 复用提供商端的 KV 缓存用于匹配前缀；重复输入 token 50-90% 折扣。 |
| `cache_control` | "Anthropic 标记" | 内容块属性，声明"到这里为止的所有内容可缓存"；`{"type": "ephemeral"}`。 |
| Cache write | "支付溢价" | 填充缓存的第一次请求；Anthropic 按 ~1.25 倍输入费率计费，OpenAI 免费。 |
| Cache read | "折扣" | 匹配前缀的后续请求；按 10%（Anthropic）、50%（OpenAI）、~25%（Gemini）计费。 |
| TTL | "存活时间" | 缓存保持热度的秒数；Anthropic 5 分钟默认（可延长 1 小时），OpenAI 最长 1 小时，Gemini 用户设置。 |
| Extended TTL | "1 小时 Anthropic 缓存" | `{"type": "ephemeral", "ttl": "1h"}`；2 倍写入溢价但对批处理重用值得。 |
| Prefix match | "为什么我的缓存未命中" | 缓存仅在从开始到断点的每个 token 都字节相同时才命中。 |
| Context caching (Gemini) | "显式的那个" | Google 的命名、按存储计费的缓存对象；最适合大型语料库的多日重用。 |

## 延伸阅读

- [Anthropic — 提示缓存](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) — `cache_control`、1 小时 TTL、盈亏平衡表。
- [OpenAI — 提示缓存](https://platform.openai.com/docs/guides/prompt-caching) — 自动前缀匹配。
- [Google — 上下文缓存](https://ai.google.dev/gemini-api/docs/caching) — `CachedContent` API 和存储定价。
- [Anthropic 工程 — 长上下文工作负载的提示缓存](https://www.anthropic.com/news/prompt-caching) — 带延迟数字的原始发布文章。
- Phase 11 · 05 (上下文工程) — 在哪里切分提示以便缓存可以着陆。
- Phase 11 · 11 (缓存与成本) — 将提示缓存与用户消息的语义缓存配对。
- [Pope et al., "Efficiently Scaling Transformer Inference" (2022)](https://arxiv.org/abs/2211.05102) — 提示缓存暴露给用户的 KV 缓存内存模型；解释了为什么缓存的前比重算便宜约 10 倍。
- [Agrawal et al., "SARATHI: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills" (2023)](https://arxiv.org/abs/2308.16369) — prefill 是提示缓存加速的阶段；本文解释了为什么缓存命中时 TTFT 急剧下降而 TPOT 不受影响。
- [Leviathan et al., "Fast Inference from Transformers via Speculative Decoding" (2023)](https://arxiv.org/abs/2211.17192) — 提示缓存与推测解码、Flash Attention 和 MQA/GQA 一起作为弯曲推理成本曲线的杠杆；阅读此论文了解另外三个。