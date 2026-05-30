# 失败模式（Failure Modes）：智能体为何崩溃

> MASFT（Berkeley，2025）将多智能体的 14 种失败模式归为 3 大类。微软的分类法（Taxonomy）记录了现有 AI 失败如何在智能体场景中被放大。行业现场数据收敛为五种反复出现的模式：幻觉操作、范围蔓延、级联错误、上下文丢失、工具误用。

**类型：** Learn + Build
**语言：** Python（标准库）
**前置课程：** Phase 14 · 05（Self-Refine and CRITIC），Phase 14 · 24（Observability）
**时间：** ~60 分钟

## 学习目标

- 列出 MASFT 的三大失败类别，以及每个类别中至少四种具体模式。
- 解释智能体失败如何放大现有的 AI 失败模式（偏见、幻觉）。
- 描述五种行业反复出现的模式及其缓解措施。
- 实现一个标准库检测器，为智能体追踪数据打上失败模式标签。

## 问题背景

团队发布的智能体在 90% 的追踪中运行良好。剩下 10% 的失败并非随机噪声 — 它们归入少量反复出现的类别。一旦你能命名它们，就可以监控并修复它们。

## 核心概念

### MASFT（Berkeley，arXiv:2503.13657）

多智能体系统失败分类法（Multi-Agent System Failure Taxonomy）。14 种失败模式聚类为 3 大类。标注者间一致性 Cohen's Kappa 为 0.88 — 说明这些类别可以可靠区分。

核心观点：失败是多智能体系统的基本设计缺陷，而非仅靠更好的基础模型就能修复的 LLM 局限性。

### 微软智能体 AI 失败模式分类法（Microsoft Taxonomy of Failure Mode in Agentic AI Systems）

- 现有的 AI 失败（偏见、幻觉、数据泄露）在智能体场景中被放大。
- 新的失败源自自主性：大规模非预期操作、工具误用、任务漂移（Mission Drift）。
- 该白皮书是智能体产品的风险登记册。

### 智能体 AI 故障特征（Characterizing Faults in Agentic AI，arXiv:2603.06847）

- 失败源于编排（Orchestration）、内部状态演进和环境交互。
- 不仅仅是"代码不好"或"模型输出不好"。

### LLM 智能体幻觉调查（LLM Agent Hallucinations Survey，arXiv:2509.18970）

两种主要表现：

1. **指令遵循偏差（Instruction-following Deviation）** — 智能体不遵循系统提示。
2. **长程上下文误用（Long-range Contextual Misuse）** — 智能体遗忘或误用早期轮次的上下文。

子意图错误（Sub-intention Errors）：遗漏（Omission，跳过步骤）、冗余（Redundancy，重复步骤）、乱序（Disorder，步骤顺序错误）。

### 五种行业反复出现的模式

Arize、Galileo、NimbleBrain 2024-2026 年的行业分析收敛为：

1. **幻觉操作（Hallucinated Actions）。** 智能体调用不存在的工具或捏造参数。
2. **范围蔓延（Scope Creep）。** 智能体超出用户要求执行任务（创建额外 PR、发送额外邮件）。
3. **级联错误（Cascading Errors）。** 一次错误调用触发下游影响。一个虚假 SKU 幻觉触发四次 API 调用 — 引发多系统事故。
4. **上下文丢失（Context Loss）。** 长程任务遗忘早期轮次的约束。
5. **工具误用（Tool Misuse）。** 用错误参数调用正确的工具，或直接调用错误的工具。

级联错误是最致命的。智能体无法区分"我失败了"和"任务不可能完成"，经常在收到 400 错误时仍幻觉出一条成功消息来闭环。

### 缓解措施：每步设门控

在推理链的每一步设置自动化验证门控，基于环境状态检查事实依据。具体包括：

- 逐步安全分类器（第 21 课）。
- 工具调用参数验证（第 06 课）。
- 将检索内容与已知事实交叉验证（第 05 课，CRITIC）。
- 通过重新探测状态来检测成功幻觉（文件是否真的被创建了？）。

### 失败监控的常见陷阱

- **只标记崩溃。** 大多数智能体失败产出的是看起来正常的输出。需要内容级别的检查。
- **没有基线（Baseline）。** 漂移检测需要"最后已知正常状态"；没有它就无法判断"情况在恶化"。
- **过度告警。** 每次失败都触发告警。应进行聚类和限流。

## 动手实现

`code/main.py` 实现了一个标准库失败模式标记器：

- 覆盖五种模式的合成追踪数据集。
- 每种模式的检测函数（基于工具调用、输出、重复操作的签名模式）。
- 标记器为每条追踪打标签并报告模式分布。

运行：

```
python3 code/main.py
```

输出：每条追踪的标签 + 聚合分布，是对 Phoenix 追踪聚类功能的低成本复现。

## 实践应用

- **Phoenix** — 生产环境的漂移聚类（第 24 课）。
- **Langfuse** — 会话回放 + 标注。
- **自定义方案** — 用于可观测性平台无法检测的领域特定签名。

## 产出物

`outputs/skill-failure-detector.md` 生成针对你领域的失败模式检测器，并接入追踪存储。

## 练习

1. 添加一个"成功幻觉"检测器：智能体返回成功但目标状态未改变。
2. 从你构建的产品中标注 100 条真实追踪。哪种模式最常见？修复它的成本是多少？
3. 实现"级联半径"指标：给定第 N 步的失败，它影响了多少下游步骤？
4. 阅读 MASFT 的 14 种失败模式。选择三种适用于你产品的模式。编写检测器。
5. 将一个检测器接入 CI 任务：如果 >=5% 的追踪标记了某种模式，则构建失败。

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| MASFT | "多智能体失败分类法" | Berkeley 的 14 模式 3 类分类 |
| Cascading Error（级联错误） | "涟漪失败" | 一个早期错误在 N 个步骤中传播 |
| Context Loss（上下文丢失） | "忘了约束" | 长程轮次丢失早期轮次的事实 |
| Tool Misuse（工具误用） | "错误工具/错误参数" | 有效调用，但调用方式错误 |
| Success Hallucination（成功幻觉） | "伪造完成" | 智能体在 400 错误上声称成功；状态未改变 |
| Scope Creep（范围蔓延） | "越界" | 智能体做了超出要求的事 |
| Instruction-following Deviation（指令遵循偏差） | "违抗" | 忽略系统提示或用户约束 |
| Sub-intention Errors（子意图错误） | "计划缺陷" | 计划执行中的遗漏、冗余、乱序 |

## 延伸阅读

- [Cemri et al., MASFT (arXiv:2503.13657)](https://arxiv.org/abs/2503.13657) — 14 种失败模式，3 大类
- [Microsoft, Taxonomy of Failure Mode in Agentic AI Systems](https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Taxonomy-of-Failure-Mode-in-Agentic-AI-Systems-Whitepaper.pdf) — 风险登记册
- [Arize Phoenix](https://docs.arize.com/phoenix) — 实践中的漂移聚类
- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — 简单模式如何完全避免某些失败