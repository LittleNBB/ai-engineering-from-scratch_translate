# 评估驱动的智能体开发（Eval-Driven Agent Development）

> Anthropic 的指导原则："从简单提示开始，用全面的评估来优化它们，仅在需要时才添加多步智能体系统。"评估不是最后一步。它是驱动 Phase 14 中所有其他选择的外层循环。

**类型：** Learn + Build
**语言：** Python（标准库）
**前置课程：** Phase 14 全部课程。
**时间：** ~60 分钟

## 学习目标

- 列出三个评估层级 — 静态基准（Static Benchmarks）、自定义离线评估（Custom Offline）、在线生产评估（Online Production）— 及其各自的用途。
- 解释评估器-优化器（Evaluator-Optimizer）的紧密循环。
- 描述 2026 年最佳实践：评估与代码同仓、在 CI 中运行、门控 PR。
- 将 Phase 14 的每节课与其生成的评估用例关联起来。

## 问题背景

智能体在演示中表现良好。它们在演示无法预测的方式中在生产中失败。基准测试回答的是"这个模型是否广泛具备能力？"，而非"这个智能体是否在为我的产品交付正确的补丁？"答案是：在三个层级上持续评估，每个护栏和学习到的规则都映射到一个评估用例。

## 核心概念

### 三个评估层级

1. **静态基准（Static Benchmarks）** — SWE-bench Verified 用于代码（第 19 课），WebArena/OSWorld 用于浏览/桌面（第 20 课），GAIA 用于通用智能体（第 19 课），BFCL V4 用于工具使用（第 06 课）。用于跨模型比较和回归门控。数据污染真实存在：SWE-bench+ 发现 32.67% 的解决方案泄露。始终报告 Verified / +-audited 分数。

2. **自定义离线评估（Custom Offline Evals）** — 你产品的形态：
   - LLM-as-judge（Langfuse、Phoenix、Opik — 第 24 课）。
   - 基于执行（运行补丁，检查测试）。
   - 基于轨迹（Trajectory-based，将操作序列与标准对比；OSWorld-Human 显示顶级智能体是标准的 1.4-2.7 倍）。

3. **在线评估（Online Evals）** — 生产环境：
   - 会话回放（Langfuse）。
   - 护栏触发的告警（第 16、21 课）。
   - 逐步成本/延迟追踪（第 23 课 OTel Span）。

### 评估器-优化器（Evaluator-Optimizer，Anthropic）

紧密循环：

1. 提议者（Proposer）生成输出。
2. 评估器（Evaluator）判定。
3. 优化直到评估器通过。

这是 Self-Refine（第 05 课）的泛化。你关注的任何智能体流程都可以用评估器-优化器包装以提高可靠性。

### 2026 年最佳实践

- 评估与代码同仓。
- 在每次 PR 时通过 CI 运行。
- 基于评估分数门控合并（例如"与 main 分支相比回归不超过 5%"）。
- 每个护栏映射到一个评估用例。
- 每条学习到的规则（Reflexion、pro-workflow learn-rule）映射到一个失败用例。

### 将 Phase 14 串联起来

Phase 14 的每节课都生成评估用例：

| 课程 | 生成的评估用例 |
|------|----------------|
| 01 Agent Loop | 预算耗尽、无限循环防护 |
| 02 ReWOO | 工具失败时规划器正确重新规划 |
| 03 Reflexion | 学习到的反思在重试时生效 |
| 05 Self-Refine/CRITIC | 判定器通过优化后的输出 |
| 06 Tool Use | 参数强制转换有效；未知工具被拒绝 |
| 07-10 Memory | 检索引用匹配来源；过期事实失效 |
| 12 Workflow Patterns | 每种模式产出正确输出 |
| 13 LangGraph | 恢复精确重现状态 |
| 14 AutoGen Actors | DLQ 捕获崩溃的处理器 |
| 16 OpenAI Agents SDK | 护栏在正确的输入上触发 |
| 17 Claude Agent SDK | 子智能体结果返回编排器 |
| 19-20 Benchmarks | SWE-bench Verified 分数、WebArena 成功率、OSWorld 效率 |
| 21 Computer Use | 逐步安全捕获注入的 DOM |
| 23 OTel | Span 发出所需属性 |
| 26 Failure Modes | 检测器标记已知失败 |
| 27 Prompt Injection | PVE 拒绝投毒的检索内容 |
| 28 Orchestration | Supervisor 路由到正确的专家 |
| 29 Runtime Shapes | DLQ 处理 N% 的失败 |

如果你的评估套件覆盖了以上所有用例，你就完成了 Phase 14 的覆盖。

### 评估驱动开发的常见陷阱

- **没有基线（Baseline）。** 没有"最后已知正常状态"的评估不可读。存储基线。
- **LLM 判断缺乏事实验证基础。** 判断器也会幻觉。CRITIC 模式（第 05 课）— 判断器基于外部工具验证。
- **过度拟合评估。** 为评估优化偏离了生产实用性。轮换用例。
- **不稳定的评估。** 非确定性用例导致误报。固定种子，快照状态。

## 动手实现

`code/main.py` 是一个标准库评估框架：

- 带分类的用例注册表（基准、自定义、在线）。
- 被测的脚本化智能体。
- 评估器-优化器循环：提议、判定、优化直到通过或达到最大轮次。
- CI 门控：聚合通过率 + 与基线的回归检测。

运行：

```
python3 code/main.py
```

输出：每个用例的通过/失败、回归标志、CI 门控判定。

## 实践应用

- 在智能体代码的同一仓库中编写评估用例。
- 通过 CI 在每次 PR 时运行。
- 回归时构建失败。
- 跟踪通过率随时间的变化。
- 将每次生产失败关联到一个新用例。

## 产出物

`outputs/skill-eval-suite.md` 为智能体产品构建三层评估套件，包含 CI 门控和回归追踪。

## 练习

1. 取一个你的生产失败案例。编写一个复现它的评估用例。你的智能体现在能通过吗？
2. 为你的领域构建一个三维度的 LLM 判断评分标准（事实性、语气、范围）。评估 50 个会话。
3. 将评估套件接入 CI。回归 >=5% 时构建失败。
4. 添加轨迹效率指标：智能体用了多少步 vs 标准轨迹？
5. 将 Phase 14 的每节课映射到你评估套件中的一个用例。有缺失的吗？那就是需要弥补的差距。

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| Static Benchmark（静态基准） | "现成的评估" | SWE-bench、GAIA、AgentBench、WebArena、OSWorld |
| Custom Offline Eval（自定义离线评估） | "领域评估" | 针对你产品形态的 LLM-as-judge / 执行 / 轨迹评估 |
| Online Eval（在线评估） | "生产评估" | 会话回放、护栏告警、成本/延迟追踪 |
| Evaluator-optimizer（评估器-优化器） | "提议-判定-优化" | 迭代直到判定器通过 |
| CI Gate（CI 门控） | "合并阻止器" | 评估回归时构建失败 |
| Baseline（基线） | "最后已知正常状态" | 用于检测回归的参考分数 |
| Trajectory Efficiency（轨迹效率） | "步数超标" | 智能体步数除以人类专家最小步数 |

## 延伸阅读

- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — "从简单开始，用评估优化"
- [OpenAI, SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) — 精选基准
- [Berkeley Function Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) — 工具使用基准
- [Langfuse docs](https://langfuse.com/) — 实践中的评估 + 会话回放