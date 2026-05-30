# 记忆块与 Sleep-Time Compute（Letta）

> MemGPT 在 2024 年变成了 Letta。2026 年的演进增加了两个想法：模型可以直接编辑的离散功能记忆块，以及一个在主 Agent 空闲时异步合并记忆的 sleep-time Agent。这是你将记忆扩展到一次对话之外的方式。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 07（MemGPT）
**时间：** ~75 分钟

## 学习目标

- 说出 Letta 使用的三层记忆（core、recall、archival）及其各自的角色。
- 解释记忆块模式：Human 块、Persona 块和用户自定义块作为一等类型化对象。
- 描述什么是 sleep-time compute，为什么它不在关键路径上，以及为什么它可以运行比主 Agent 更强的模型。
- 实现一个脚本化的双 Agent 循环，其中主 Agent 提供响应，sleep-time Agent 在轮次之间合并记忆块。

## 问题

MemGPT（第 7 课）解决了虚拟内存控制流。三个生产问题浮现出来：

1. **延迟。** 每个记忆操作都在关键路径上。如果 Agent 必须在用户等待时修剪、总结或协调，尾部延迟会爆炸。
2. **记忆腐烂。** 写入不断积累。被矛盾的事实留存。检索被过时的内容淹没。
3. **结构丢失。** 扁平的 archival 存储无法表达"Human 块始终在提示中；Persona 块始终在提示中；Task 块按会话交换。"

Letta（letta.com）是 2026 年的重写。记忆块使结构显式化；sleep-time compute 将合并移出关键路径。

## 核心概念

### 三层结构

| 层级 | 范围 | 存储位置 | 写入者 |
|------|------|---------|-------|
| Core | 始终可见 | 主提示内部 | Agent 工具调用 + sleep-time 重写 |
| Recall | 对话历史 | 可检索 | 自动轮次日志 |
| Archival | 任意事实 | 向量 + KV + 图 | Agent 工具调用 + sleep-time 摄入 |

Core 是 MemGPT 的 core。Recall 是带有淘汰尾部的对话缓冲区。Archival 是外部存储。这种分离清理了 MemGPT 两层的重载问题。

### 记忆块

块是 core 层中一个类型化的、持久的、可编辑的部分。原始 MemGPT 论文定义了两个：

- **Human 块** — 关于用户的事实（姓名、角色、偏好、目标）。
- **Persona 块** — Agent 的自我概念（身份、语气、约束）。

Letta 泛化为任意用户自定义块：用于当前目标的 `Task` 块、用于代码库事实的 `Project` 块、用于硬约束的 `Safety` 块。每个块有 `id`、`label`、`value`、`limit`（字符上限）、`description`（让模型知道何时编辑它）。

块通过工具接口可编辑：

- `block_append(label, text)`
- `block_replace(label, old, new)`
- `block_read(label)`
- `block_summarize(label)` — 压缩接近上限的块。

### Sleep-time compute

2025 年 Letta 的新增：在后台运行第二个 Agent，不在关键路径上。Sleep-time Agent 处理对话转录和代码库上下文，将 `learned_context` 写入共享块，并合并或失效 archival 记录。

由此产生的特性：

- **无延迟成本。** 主响应不等待记忆操作。
- **允许使用更强的模型。** Sleep-time Agent 可以是更昂贵、更慢的模型，因为它不受延迟约束。
- **自然的合并窗口。** 在用户不等待时进行去重、总结、失效矛盾事实。

这与人类的工作方式一致：你完成任务，睡一觉，长期记忆在一夜之间稳定下来。

### Letta V1 与原生推理

Letta V1（`letta_v1_agent`，2026）弃用了 `send_message`/heartbeat 和内联 `Thought:` token，转而采用原生推理。Responses API（OpenAI）和带扩展思考的 Messages API（Anthropic）在单独的通道上发出推理，在各轮次间传递（在生产环境中跨提供商加密传输）。控制循环仍然是 ReAct。思考轨迹是结构性的，而非提示形态的。

### 这个模式出错的地方

- **块膨胀。** 无限的 `block_append` 很快达到上限。在写入超过上限之前接入一个块摘要器。
- **静默漂移。** Sleep-time Agent 重写了块而主 Agent 从未注意到。给块版本化并在轨迹中显示差异。
- **投毒合并。** Sleep-time Agent 将攻击者可访问的内容处理到 core 中。第 27 课同样适用于 sleep-time 接口。

## 构建它

`code/main.py` 实现了：

- `Block` — id、label、value、limit、description。
- `BlockStore` — CRUD + `near_limit(label)` 辅助函数。
- 两个脚本化 Agent — `PrimaryAgent` 服务一轮，`SleepTimeAgent` 在轮次之间合并。
- 一个展示三轮对话轨迹，包含块写入，加上一次 sleep-time 遍历，摘要一个块并失效一个过时事实。

运行它：

```
python3 code/main.py
```

转录显示了分离：主轮次快速且产生原始写入；sleep 遍历压缩和清理。

## 使用它

- **Letta**（letta.com）作为参考实现。自托管或托管云。
- **Claude Agent SDK 技能**作为块形态的知识 — 技能是一个命名的、版本化的、可检索的指令块，Agent 按需加载。
- **自定义构建**适用于想要控制存储后端的团队。使用 Letta API 契约以便后续迁移。

## 发布它

`outputs/skill-memory-blocks.md` 为任何运行时生成 Letta 形态的块系统，带 sleep-time 钩子，包括安全规则和引用接线。

## 练习

1. 添加一个 `block_summarize` 工具，当 `near_limit` 返回 true 时用模型生成的摘要替换块值。哪个触发阈值能最小化摘要调用和块溢出？
2. 在 archival 上实现 sleep-time 去重：两个文本 token 重叠 >90% 的记录合并为一个。仅在 sleep 遍历中执行，绝不在关键路径上。
3. 给块版本化。每次写入时记录旧值和差异。暴露 `block_history(label)` 以便运维调试"为什么 Agent 忘了 X"。
4. 将 sleep-time Agent 视为不可信的写入者。当它们触及 Persona 或 Safety 块时，在提交前要求第二个 Agent 审查。
5. 将示例移植到使用 Letta API（`letta_v1_agent`）。块 schema 有什么变化，原生推理如何改变轨迹形状？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Memory block | "可编辑的提示部分" | core 记忆中类型化的、持久的、LLM 可编辑的段 |
| Human block | "用户记忆" | 关于用户的事实，固定在 core 中 |
| Persona block | "Agent 身份" | 自我概念、语气、约束，固定在 core 中 |
| Sleep-time compute | "异步记忆工作" | 第二个 Agent 在关键路径之外执行合并 |
| Core / Recall / Archival | "层级" | 三层记忆分离：始终可见 / 对话 / 外部 |
| Block limit | "上限" | 每个块的字符限制；强制摘要 |
| Native reasoning | "思考通道" | 提供商级别的推理输出，非提示级别的 `Thought:` |
| Learned context | "Sleep 输出" | Sleep-time Agent 写入共享块的事实 |

## 延伸阅读

- [Letta, Memory Blocks blog](https://www.letta.com/blog/memory-blocks) — 块模式
- [Letta, Sleep-time Compute blog](https://www.letta.com/blog/sleep-time-compute) — 异步合并
- [Letta, Rearchitecting the Agent Loop](https://www.letta.com/blog/letta-v1-agent) — 原生推理重写
- [Packer 等人, MemGPT (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560) — 起源