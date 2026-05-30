# 智能体可观测性（Agent Observability）：Langfuse、Phoenix、Opik

> 2026 年三大开源智能体可观测性平台占据主导地位。Langfuse（MIT 许可证）— 月安装量 600 万+，集追踪、提示管理、评估和会话回放于一体。Arize Phoenix（Elastic 2.0 许可证）— 深度智能体专项评估、RAG 相关性、OpenInference 自动插桩。Comet Opik（Apache 2.0 许可证）— 自动化提示优化、护栏（Guardrail）、LLM 判断的幻觉检测。

**类型：** Learn
**语言：** Python（标准库）
**前置课程：** Phase 14 · 23（OTel GenAI）
**时间：** ~45 分钟

## 学习目标

- 列出三大开源智能体可观测性平台及其许可证。
- 区分各自的强项：Langfuse（提示管理 + 会话）、Phoenix（RAG + 自动插桩）、Opik（优化 + 护栏）。
- 解释为什么 89% 的组织报告到 2026 年已部署智能体可观测性。
- 实现一个从追踪到仪表盘的标准库管道，包含 LLM 判断的评估功能。

## 问题背景

OTel GenAI（第 23 课）提供了模式（Schema）。你仍然需要一个平台来摄取 Span、运行评估、存储提示版本并发现回归问题。三个平台各自侧重生命周期的不同环节。

## 核心概念

### Langfuse（MIT 许可证）

- 月 SDK 安装量 600 万+，GitHub 19k+ Star。
- 功能：追踪、带版本控制和 Playground 的提示管理、评估（LLM-as-judge、用户反馈、自定义）、会话回放（Session Replay）。
- 2025 年 6 月：原商业模块（LLM-as-a-judge、标注队列、提示实验、Playground）以 MIT 许可证开源。
- 最强场景：端到端可观测性 + 紧密的提示管理闭环。

### Arize Phoenix（Elastic License 2.0）

- 更深入的智能体专项评估：追踪聚类（Trace Clustering）、异常检测、RAG 检索相关性。
- 原生 OpenInference 自动插桩。
- 可与托管版 Arize AX 配合用于生产环境。
- 无提示版本管理 — 定位为与更广泛平台配合使用的漂移/行为回归工具。
- 最强场景：RAG 相关性、行为漂移（Behavioral Drift）、异常检测。

### Comet Opik（Apache 2.0 许可证）

- 通过 A/B 实验进行自动化提示优化。
- 护栏（PII 脱敏、主题约束）。
- LLM 判断的幻觉检测（Hallucination Detection）。
- Comet 自测基准：Opik 日志 + 评估耗时 23.44 秒，Langfuse 耗时 327.15 秒（约 14 倍差距）— 厂商基准仅供参考。
- 最强场景：优化闭环、自动化实验、护栏执行。

### 行业数据

根据 Maxim（2026 年行业分析）：89% 的组织已部署智能体可观测性；质量问题是生产环境的首要障碍（32% 的受访者提及）。

### 如何选择

| 需求 | 选择 |
|------|------|
| 一体化方案含提示管理 | Langfuse |
| 深度 RAG 评估 + 漂移检测 | Phoenix |
| 自动化优化 + 护栏 | Opik |
| 开放许可证，不使用 ELv2 | Langfuse（MIT）或 Opik（Apache 2.0） |
| Datadog / New Relic 集成 | 任一 — 它们都导出 OTel |

### 这种模式的常见陷阱

- **缺乏评估策略。** 只追踪不评估，不过是昂贵的日志记录。
- **自建 LLM 判断缺乏事实验证基础。** CRITIC 模式（第 05 课）依然适用 — 判断器需要外部工具进行事实核查。
- **提示版本未关联追踪。** 当生产环境出现回归时，无法二分定位到导致问题的提示版本。

## 动手实现

`code/main.py` 实现了一个标准库追踪收集器 + LLM 判断评估器：

- 摄取 GenAI 格式的 Span。
- 按会话分组，标记失败的运行（护栏触发、低置信度评估）。
- 脚本化的 LLM 判断器，按评分标准对智能体响应打分。
- 仪表盘式的摘要：失败率、主要失败原因、评估分数分布。

运行：

```
python3 code/main.py
```

输出：按会话的评估分数和失败分类，与 Langfuse/Phoenix/Opik 的展示方式一致。

## 实践应用

- **Langfuse** — 自托管或云端；通过 OTel 或其 SDK 接入。
- **Arize Phoenix** — 自托管；OpenInference 自动插桩。
- **Comet Opik** — 自托管或云端；自动化优化闭环。
- **Datadog LLM Observability** — 适合已在使用 Datadog 的运维 + ML 混合团队。

## 产出物

`outputs/skill-obs-platform-wiring.md` 选择一个平台，将追踪 + 评估 + 提示版本接入现有智能体。

## 练习

1. 将一周的 OTel 追踪导出到 Langfuse 云端（免费层级）。哪些会话失败了？原因是什么？
2. 为你的领域编写 LLM 判断评分标准（事实正确性、语气、范围遵循度）。在 50 条追踪上测试。
3. 对比 Langfuse 的提示版本管理与 Phoenix 的追踪聚类。哪个能更快定位问题？
4. 阅读 Opik 的护栏文档。将 PII 脱敏护栏接入你的一次智能体运行。
5. 在你的语料上对比三者的基准测试。忽略厂商发布的数据；自行测量。

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| Tracing（追踪） | "Span 收集器" | 摄取 OTel / SDK Span；按会话索引 |
| Prompt Management（提示管理） | "提示 CMS" | 关联追踪的版本化提示 |
| LLM-as-judge（LLM 判断） | "自动化评估" | 独立 LLM 按评分标准对智能体输出打分 |
| Session Replay（会话回放） | "追踪回放" | 逐步回放历史运行用于调试 |
| RAG Relevancy（RAG 相关性） | "检索质量" | 检索到的上下文是否匹配查询 |
| Trace Clustering（追踪聚类） | "行为分组" | 对相似运行进行聚类以检测漂移 |
| Guardrail Enforcement（护栏执行） | "日志时策略" | 对日志内容进行 PII/毒性/范围检查 |

## 延伸阅读

- [Langfuse docs](https://langfuse.com/) — 追踪、评估、提示管理
- [Arize Phoenix docs](https://docs.arize.com/phoenix) — 自动插桩、漂移检测
- [Comet Opik](https://www.comet.com/site/products/opik/) — 优化 + 护栏
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — 三者共同消费的模式