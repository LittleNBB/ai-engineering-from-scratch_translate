# Reflexion：语言强化学习

> 基于梯度的强化学习需要数千次试验和一个 GPU 集群来修复一个失败模式。Reflexion（Shinn 等人，NeurIPS 2023）用自然语言做到了这一点：每次失败试验后，Agent 写下反思，将其存储在情景记忆中，并在下一次试验中以该记忆为条件。这是 Letta 的 sleep-time compute、Claude Code 的 CLAUDE.md 学习记录，以及 pro-workflow 的 learn-rule 背后的模式。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 02（ReWOO）
**时间：** ~60 分钟

## 学习目标

- 说出 Reflexion 的三个组件（Actor、Evaluator、Self-Reflector）以及情景记忆的角色。
- 用标准库实现一个带二元评估器、反思缓冲区和全新重试的 Reflexion 循环。
- 为给定任务选择标量、启发式和自评估反馈源。
- 解释为什么语言强化能捕捉基于梯度的强化学习需要数千次试验才能修复的错误。

## 问题

一个 Agent 在某个任务上失败了。在标准强化学习中，你需要运行更多数千次试验，计算梯度，更新权重。昂贵、缓慢，而且大多数生产 Agent 没有针对每个失败的训练预算。

Reflexion（Shinn 等人，arXiv:2303.11366）问了一个不同的问题：如果 Agent 只是思考为什么失败了，然后带着这个思考再次尝试呢？没有权重更新。没有梯度。只有在试验之间存储的自然语言。

结果：在 ALFWorld 上它击败了 ReAct 和其他非微调基线。在 HotpotQA 上它超越了 ReAct。在代码生成（HumanEval/MBPP）上，它在当时达到了最先进水平。全程没有一次梯度更新。

## 核心概念

### 三个组件

```
Actor         : generates a trajectory (ReAct-style loop)
Evaluator     : scores the trajectory — binary, heuristic, or self-eval
Self-Reflector: writes a natural-language reflection on the failure
```

加上一个数据结构：

```
Episodic memory: list of prior reflections, prepended to the next trial's prompt
```

一次试验运行 Actor。Evaluator 评分。如果分数低，Self-Reflector 产生一个反思（"我选错了工具，因为我把问题误读为问 X，而实际上问的是 Y"）。反思进入情景记忆。下一次试验全新开始，但能看到反思。

### 三种评估器类型

1. **标量（Scalar）** — 外部二元信号。ALFWorld 成功或失败。HumanEval 测试通过或失败。最简单，信号最强。
2. **启发式（Heuristic）** — 预定义的失败特征。"如果 Agent 连续两次产生相同的动作，标记为卡住。""如果轨迹超过 50 步，标记为低效。"
3. **自评估（Self-evaluated）** — LLM 给自己的轨迹评分。当没有真实标签时需要。信号较弱；适合与工具验证配对（第 5 课 — CRITIC）。

2026 年的默认做法是混合使用：有标量时用标量，没有时用自评估，启发式作为安全防护。

### 为什么能泛化

Reflexion 不是一个新算法，更像是一个命名模式。几乎每一个生产"自愈" Agent 都运行某种变体：

- Letta 的 sleep-time compute（第 8 课）：一个单独的 Agent 反思过去的对话并写入记忆块。
- Claude Code 的 `CLAUDE.md` / "保存记忆" 模式：反思作为学习记录被捕获，添加到未来的会话中。
- pro-workflow 的 `/learn-rule` 命令：修正被作为显式规则捕获。
- LangGraph 的反思节点：一个评分输出并在需要时路由到优化的节点。

所有这些都源于同一个洞察：自然语言是一种足够丰富的媒介，可以在运行之间传递"我从失败中学到了什么"。

### 何时有效，何时无效

Reflexion 在以下情况有效：

- 有清晰的失败信号（测试失败、工具错误、错误答案）。
- 任务类别可复现（同一类型的问题可以再次被问到）。
- 反思有空间改进轨迹（足够的动作预算）。

Reflexion 在以下情况无效：

- Agent 第一次就成功了。
- 失败是外部的（网络中断、工具损坏）—— 对"网络中断了"的反思对未来运行没有帮助。
- 反思变成了迷信 —— 存储关于一次性不稳定运行的叙述。

2026 年的陷阱：记忆腐烂。反思不断积累；有些已过时或错误；随着情景缓冲区增长，重运行变慢。缓解措施：定期压缩（第 6 课）、反思的 TTL，或单独的 sleep-time 清理 Agent（Letta）。

## 构建它

`code/main.py` 在一个玩具谜题上实现了 Reflexion：生成一个 3 元素列表，使其总和等于目标。Actor 发出候选列表；Evaluator 检查总和；Self-Reflector 写一行关于出了什么问题的诊断。反思进入情景记忆供下一次试验使用。

组件：

- `Actor` —— 一个在看到反思时会改进的脚本化策略。
- `Evaluator.binary()` —— 对目标总和的通过/失败判定。
- `SelfReflector` —— 生成一行失败诊断。
- `EpisodicMemory` —— 一个带 TTL 语义的有界列表。

运行它：

```
python3 code/main.py
```

轨迹显示三次试验。试验 1 失败，反思被存储，试验 2 看到反思并改进但仍失败，试验 3 成功。与基线运行（无反思）对比 —— 它始终卡在试验 1 的答案上。

## 使用它

LangGraph 将反思作为节点模式提供。Claude Code 的 `/memory` 命令和 pro-workflow 的 `/learn-rule` 将情景缓冲区外化为 Markdown 文件。Letta 的 sleep-time compute 在空闲时间运行 Self-Reflector，使主 Agent 保持低延迟。OpenAI Agents SDK 不直接提供 Reflexion；你可以用自定义 Guardrail（按分数拒绝轨迹）和跨运行持久化的记忆 `Session` 来构建它。

## 发布它

`outputs/skill-reflexion-buffer.md` 创建并维护一个带反思捕获、TTL 和去重的情景缓冲区。给定一个任务类别和一个失败，它发出一个真正有助于下一次试验的反思（而不是泛泛的"更仔细一点"）。

## 练习

1. 从二元切换到返回距离度量（离目标多远）的标量评估器。收敛更快吗？
2. 给反思添加 10 次试验的 TTL。超过该点后，旧反思是有害还是有帮助？
3. 实现启发式评估器：如果相同动作重复，标记为卡住。这如何与 Self-Reflector 交互？
4. 用忽略反思的对抗性 Actor 运行 Reflexion。强制 Actor 注意到反思的最小提示工程是什么？
5. 阅读 Reflexion 论文中关于 AlfWorld 的第 4 节。概念性地复现 130% 成功率提升：与原始 ReAct 的关键差异是什么？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Reflexion | "自我修正" | Shinn 等人 2023 — Actor、Evaluator、Self-Reflector 加情景记忆 |
| Verbal reinforcement | "无梯度学习" | 添加到下一次试验提示中的自然语言反思 |
| Episodic memory | "每任务反思" | 针对一个任务类别的先前反思的有界缓冲区 |
| Scalar evaluator | "二元成功信号" | 来自真实标签的通过/失败或数值分数 |
| Heuristic evaluator | "基于模式的检测器" | 预定义的失败特征（如卡住循环、步数过多） |
| Self-evaluator | "LLM 对自己轨迹的评判" | 没有真实标签时的低信号备选 — 配合工具验证使用 |
| Memory rot | "过时的反思" | 情景缓冲区充满过时条目；用压缩/TTL 修复 |
| Sleep-time reflection | "异步自我反思" | 在非热路径上运行 Self-Reflector，使主 Agent 保持快速 |

## 延伸阅读

- [Shinn 等人, Reflexion: Language Agents with Verbal Reinforcement Learning (arXiv:2303.11366)](https://arxiv.org/abs/2303.11366) —— 标准论文
- [Letta, Sleep-time Compute](https://www.letta.com/blog/sleep-time-compute) —— 生产中的异步反思
- [Anthropic, Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) —— 将情景缓冲区作为上下文的一部分进行管理
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) —— 反思节点模式