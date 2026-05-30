# Anthropic 工作流模式：简单优于复杂

> Schluntz 和 Zhang（Anthropic，2024 年 12 月）区分了工作流（预定义路径）和 Agent（动态工具使用）。五种工作流模式覆盖了大多数情况。从直接 API 调用开始。仅在步骤无法预测时才添加 Agent。

**类型：** Learn + Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）
**时间：** ~60 分钟

## 学习目标

- 说出 Anthropic 的五种工作流模式：提示链（prompt chaining）、路由（routing）、并行化（parallelization）、编排器-工作者（orchestrator-workers）、评估器-优化器（evaluator-optimizer）。
- 解释 Agent 与工作流的区别以及各自的工程成本。
- 识别何时选择工作流而非 Agent（反之亦然）。
- 用标准库针对脚本化 LLM 实现全部五种模式。

## 问题

团队为只需要单个函数调用的问题引入多 Agent 框架。成本是真实的：框架添加了层，模糊了提示、隐藏了控制流，并诱使过早复杂化。Schluntz 和 Zhang 2024 年 12 月的帖子是被引用最多的行业反驳：从简单开始，仅在复杂性值得其成本时才添加。

## 核心概念

### 工作流 vs Agent

- **工作流。** 通过预定义代码路径编排的 LLM 和工具。工程师拥有图。
- **Agent。** LLM 动态指挥自己的工具并采取自己的步骤。模型拥有图。

两者都有其位置。工作流更便宜、更快、更容易调试。Agent 解锁开放性问题但使故障模式更难推理。

### 增强型 LLM

所有五种模式的基础：一个 LLM 加上三种接入的能力 —— 搜索（检索）、工具（动作）、记忆（持久化）。任何 API 调用都可以使用这些。

### 五种模式

1. **提示链（Prompt chaining）。** 调用 1 的输出是调用 2 的输入。当任务有清晰的线性分解时使用。步骤之间可选的编程门控。

2. **路由（Routing）。** 一个分类器 LLM 选择调用哪个下游 LLM 或工具。当类别不同的输入需要不同处理时使用（一线支持 vs 退款 vs bug vs 销售）。

3. **并行化（Parallelization）。** 并发运行 N 个 LLM 调用，聚合结果。两种形态：分段（不同块）和投票（相同提示，N 次运行，多数/合成）。

4. **编排器-工作者（Orchestrator-workers）。** 一个编排器 LLM 动态决定运行哪些工作者（也是 LLM）并合成它们的输出。类似 Agent 循环但编排器不会无限循环。

5. **评估器-优化器（Evaluator-optimizer）。** 一个 LLM 提出答案，另一个 LLM 评估它。迭代直到评估器通过。这是 Self-Refine（第 5 课）的泛化。

### 工作流胜过 Agent 的地方

- **可预测的任务。** 如果你能枚举步骤，就应该枚举。
- **成本约束的任务。** 工作流有有界的步骤数；Agent 可能螺旋上升。
- **合规约束的任务。** 审计员想读图，而不是从轨迹中推断。

### Agent 胜过工作流的地方

- **开放性研究。** 当下一步取决于上一步返回了什么。
- **可变长度任务。** 几分钟到几小时的工作，步骤数未知。
- **新领域。** 当你还不知道正确的工作流时 —— 先探索，后编码化。

### 上下文工程的配套

"Effective context engineering for AI agents"（Anthropic 2025）形式化了相邻学科：200k 窗口是预算而非容器。包含什么、何时压缩、何时让上下文增长。在 Phase 14 的上下文压缩课程中有详细覆盖。

## 构建它

`code/main.py` 针对 `ScriptedLLM` 实现了全部五种工作流模式：

- `prompt_chain(input, steps)` — 顺序执行。
- `route(input, classifier, handlers)` — 分类 + 分发。
- `parallel_vote(prompt, n, aggregator)` — N 次运行，聚合。
- `orchestrator_workers(task, workers)` — 编排器选择工作者。
- `evaluator_optimizer(task, proposer, evaluator, max_iter)` — 循环直到通过。

运行它：

```
python3 code/main.py
```

每个模式打印其轨迹。每个模式的总代码行数约 10-15 行；框架的成本以千行计。

## 使用它

- 大多数任务直接 API 调用。
- 仅在模式真正需要持久状态（LangGraph）、Actor 模型并发（AutoGen v0.4）或角色模板（CrewAI）时使用框架。
- 当你想要 Claude Code 的框架形态而不想重建它时，使用 Claude Agent SDK。

## 发布它

`outputs/skill-workflow-picker.md` 为给定任务描述选择正确的模式，包括决策理由以及在工作流不足时重构为 Agent 的路径。

## 练习

1. 实现带置信度阈值的路由。低于阈值 -> 升级到人工。一线支持用例的阈值在哪里？
2. 给 `parallel_vote` 添加超时。当一个调用挂起时会发生什么？如何在缺少投票的情况下聚合？
3. 将 `evaluator_optimizer` 变成老虎机：跨迭代保留 top-2 输出，这样晚到的好结果不会被晚到的差结果覆盖。
4. 组合提示链与路由：路由器从三个链中选一个。衡量 token 成本与单个大提示替代方案的对比。
5. 选择你一个生产功能。画出工作流图。计算步骤数。Agent 在这里真的会更好吗？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Workflow | "预定义流程" | 工程师拥有的 LLM 和工具调用图 |
| Agent | "自主 AI" | 模型拥有的图；动态工具指挥 |
| Augmented LLM | "带工具的 LLM" | LLM + 搜索 + 工具 + 记忆；原子单元 |
| Prompt chaining | "顺序调用" | 调用 N 的输出是调用 N+1 的输入 |
| Routing | "分类器分发" | 选择哪个链/模型处理输入 |
| Parallelization | "扇出" | N 个并发调用；按分段或投票聚合 |
| Orchestrator-workers | "分发器 Agent" | 编排器 LLM 动态选择专家 LLM |
| Evaluator-optimizer | "提议者 + 裁判" | 迭代直到评估器通过；Self-Refine 泛化 |

## 延伸阅读

- [Anthropic, Building Effective Agents (Dec 2024)](https://www.anthropic.com/research/building-effective-agents) — 五种工作流模式
- [Anthropic, Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — 配套学科
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) — 有状态图何时值得其成本
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) — 编排器-工作者模式，产品化