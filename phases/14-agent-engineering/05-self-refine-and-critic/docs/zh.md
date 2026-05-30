# Self-Refine 与 CRITIC：迭代输出改进

> Self-Refine（Madaan 等人，2023）使用一个 LLM 扮演三个角色 —— 生成、反馈、优化 —— 在一个循环中。在 7 个任务上平均提升 +20 个绝对点。CRITIC（Gou 等人，2023）通过将验证路由到外部工具来强化反馈步骤。2026 年，这个模式在每个框架中以"评估器-优化器"（Anthropic）或护栏循环（OpenAI Agents SDK）的形式出现。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 03（Reflexion）
**时间：** ~60 分钟

## 学习目标

- 说出 Self-Refine 的三个提示（生成、反馈、优化）并解释为什么历史记录对优化提示很重要。
- 解释 CRITIC 的关键洞察：LLM 在没有外部验证的情况下不擅长自我验证。
- 用标准库实现一个带历史记录和可选外部验证器的 Self-Refine 循环。
- 将这个模式映射到 Anthropic 的"评估器-优化器"工作流和 OpenAI Agents SDK 的输出护栏。

## 问题

一个 Agent 产生了几乎正确的答案。也许一行代码有语法错误。也许一篇摘要太长了。也许一个计划遗漏了一个边界情况。你想要的是：Agent 评审自己的输出，然后修复它。

Self-Refine 表明这可以用单个模型、无训练数据、无强化学习来实现。但有一个问题：LLM 在硬事实的自我验证方面很糟糕。CRITIC 提出了修复方案 —— 将验证步骤路由到外部工具（搜索引擎、代码解释器、计算器、测试运行器）。

这两篇论文共同定义了 2026 年迭代改进的默认做法：生成、验证（尽可能外部验证）、优化、在验证器通过时停止。

## 核心概念

### Self-Refine（Madaan 等人，NeurIPS 2023）

一个 LLM，三个角色：

```
generate(task)            -> output_0
feedback(task, output_0)  -> critique_0
refine(task, output_0, critique_0, history) -> output_1
feedback(task, output_1)  -> critique_1
refine(task, output_1, critique_1, history) -> output_2
...
stop when feedback says "no issues" or budget exhausted.
```

关键细节：`refine` 看到完整的历史记录 —— 所有先前的输出和评审意见 —— 这样它不会重复犯错。论文对此进行了消融实验：去掉历史记录后质量急剧下降。

亮点：在 7 个任务（数学、代码、缩写、对话）上平均绝对提升 +20，包括 GPT-4。无训练、无外部工具、单一模型。

### CRITIC（Gou 等人，arXiv:2305.11738，2024 年 2 月 v4）

Self-Refine 的弱点：反馈步骤是 LLM 在给自己评分。对于事实性声明这是不可靠的（幻觉对于产生它的模型来说往往看起来很令人信服）。CRITIC 用 `verify(task, output, tools)` 替换了 `feedback(task, output)`，其中 `tools` 包括：

- 用于事实性声明的搜索引擎。
- 用于代码正确性的代码解释器。
- 用于算术的计算器。
- 领域特定的验证器（单元测试、类型检查器、linter）。

验证器产生一个基于工具结果的结构化评审。然后优化器基于这个评审进行优化。

亮点：CRITIC 在事实性任务上超越 Self-Refine，因为评审是有依据的。在没有外部验证器的任务上（创意写作、格式化），CRITIC 退化为 Self-Refine。

### 停止条件

两种常见形态：

1. **验证器通过。** 外部测试返回成功。可用时首选（单元测试、类型检查器、护栏断言）。
2. **未发出反馈。** 模型说"输出没问题"。更便宜但不可靠；配合最大迭代次数上限使用。

2026 年默认做法：组合使用。"如果验证器通过就停止，或者模型说没问题且迭代次数 >= 2，或者迭代次数 >= 最大迭代次数。"

### 评估器-优化器（Anthropic, 2024）

Anthropic 2024 年 12 月的帖子将其命名为五种工作流模式之一。两个角色：

- 评估器（Evaluator）：评分输出并产生评审。
- 优化器（Optimizer）：根据评审修订输出。

循环直到评估器通过。这是 Anthropic 框架中的 Self-Refine/CRITIC。Anthropic 补充的关键工程细节：评估器和优化器的提示应该有显著差异，这样模型不会只是橡皮图章。

### OpenAI Agents SDK 输出护栏

OpenAI Agents SDK 以"输出护栏"的形式提供这个模式。护栏是一个运行在 Agent 最终输出上的验证器。如果护栏触发（抛出 `OutputGuardrailTripwireTriggered`），输出被拒绝，Agent 可以重试。护栏可以调用工具（CRITIC 风格）或作为纯函数（Self-Refine 风格）。

### 2026 年的陷阱

- **橡皮图章循环。** 同一个模型用相同的提示风格做生成和评审，会收敛到"看起来没问题"。使用结构上不同的提示，或用更小更便宜的模型做评审。
- **过度优化。** 每次优化都会增加延迟和 token。预算 1-3 次；之后升级到人工审查。
- **在简单任务上使用 CRITIC。** 如果没有外部验证器，CRITIC 退化为 Self-Refine；不要为存根验证器付出延迟代价。

## 构建它

`code/main.py` 在一个玩具任务上实现了 Self-Refine 和 CRITIC：给定一个主题生成一个简短的要点列表。验证器检查格式（3 个要点，每个不超过 60 个字符）。CRITIC 添加了一个外部"事实验证器"，惩罚已知的幻觉。

组件：

- `generate` —— 脚本化的生成器。
- `feedback` —— LLM 风格的自评审。
- `verify_external` —— CRITIC 风格的有依据的验证器。
- `refine` —— 根据历史重写输出。
- 停止条件 —— 验证器通过或最多 4 次迭代。

运行它：

```
python3 code/main.py
```

比较 Self-Refine 和 CRITIC 运行。CRITIC 捕捉到了 Self-Refine 遗漏的事实错误，因为外部验证器拥有自评审没有的验证依据。

## 使用它

Anthropic 的评估器-优化器是这个模式的 Claude 友好语言。OpenAI Agents SDK 的输出护栏是 CRITIC 形态的（护栏可以调用工具）。LangGraph 提供了一个读起来像 Self-Refine 的反思节点。Google 的 Gemini 2.5 Computer Use 添加了一个每步安全评估器，是 CRITIC 的变体：每个动作在提交前都被验证。

## 发布它

`outputs/skill-refine-loop.md` 根据任务形态、验证器可用性和迭代预算配置一个评估器-优化器循环。为生成器、评估器/验证器和优化器发出提示，加上停止策略。

## 练习

1. 用 max_iterations=1 运行玩具代码。CRITIC 还有帮助吗？
2. 将外部验证器替换为一个有噪声的（30% 随机误报）。循环会怎样？这是 2026 年大多数护栏栈的现实。
3. 实现一个"生成器-评审器用不同模型"的变体：大模型生成，小模型评审。它能击败同模型吗？
4. 阅读 CRITIC 第 3 节（arXiv:2305.11738 v4）。说出三种验证工具类别并各给一个例子。
5. 将 OpenAI Agents SDK 的 `output_guardrails` 映射到 CRITIC 的验证器角色。SDK 哪里做错了，哪里做对了？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Self-Refine | "自我修复的 LLM" | 单一模型中的生成 -> 反馈 -> 优化循环，带历史记录 |
| CRITIC | "工具验证" | 用外部验证器（搜索、代码、计算、测试）替换反馈 |
| Evaluator-Optimizer | "Anthropic 工作流模式" | 两个角色 — 评估器评分，优化器修订 — 循环到收敛 |
| Output guardrail | "事后检查" | OpenAI Agents SDK 在 Agent 产生输出后运行的验证器 |
| Verify step | "评审阶段" | 承重的决策：有依据还是自评 |
| Refine history | "模型已尝试的内容" | 添加到优化提示中的先前输出 + 评审；去掉后质量崩溃 |
| Rubber-stamp loop | "自我同意失败" | 相同提示的评审返回"看起来没问题"；用结构不同的提示修复 |
| Stop condition | "收敛测试" | 验证器通过或无反馈且迭代上限；绝非单一条件 |

## 延伸阅读

- [Madaan 等人, Self-Refine (arXiv:2303.17651)](https://arxiv.org/abs/2303.17651) —— 标准论文
- [Gou 等人, CRITIC (arXiv:2305.11738)](https://arxiv.org/abs/2305.11738) —— 工具验证
- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) —— 评估器-优化器工作流模式
- [OpenAI Agents SDK docs](https://openai.github.io/openai-agents-python/) —— 输出护栏作为 CRITIC 形态的验证器