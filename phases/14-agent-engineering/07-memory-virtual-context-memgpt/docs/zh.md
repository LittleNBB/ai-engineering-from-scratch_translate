# 记忆：虚拟上下文与 MemGPT

> 上下文窗口是有限的。对话、文档和工具轨迹不是。MemGPT（Packer 等人，2023）将其框架化为操作系统的虚拟内存 —— 主上下文是 RAM，外部存储是磁盘，Agent 在它们之间进行分页。这是 2026 年每个记忆系统继承的模式。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 06（Tool Use）
**时间：** ~75 分钟

## 学习目标

- 解释 MemGPT 建立的操作系统类比：主上下文 = RAM，外部上下文 = 磁盘，记忆工具 = 换入/换出。
- 用标准库实现两层 MemGPT 模式，包含主上下文缓冲区、可搜索的外部存储和换入/换出工具。
- 描述 Agent 如何发出"中断"来查询或修改外部记忆，以及结果如何拼接回下一个提示。
- 识别 MemGPT 中延续到 Letta（第 8 课）和 Mem0（第 9 课）的设计选择。

## 问题

上下文窗口看起来应该能解决记忆问题。它们并不能。三种失败模式在生产中反复出现：

1. **溢出。** 多轮对话、长文档或工具调用密集的轨迹超出了窗口。超出截止点的一切都消失了。
2. **稀释。** 即使在窗口内，填充无关上下文也会稀释对重要内容的注意力。前沿模型在长输入上仍然会退化。
3. **持久性。** 新会话从空窗口开始。没有外部记忆的 Agent 无法跨会话说"记得你让我……"。

更大的窗口有帮助但不能解决这个问题。Mem0 的 2025 年论文测量发现，128k 窗口的基线仍然会遗漏一个带外部记忆的 4k 窗口 Agent 能捕捉到的长周期事实。

## 核心概念

### MemGPT：操作系统类比

Packer 等人（arXiv:2310.08560，2024 年 2 月 v2）将上下文管理映射到操作系统的虚拟内存：

| OS 概念 | MemGPT 概念 | 2026 年生产类比 |
|---------|------------|----------------|
| RAM | 主上下文（提示） | Anthropic/OpenAI 上下文窗口 |
| 磁盘 | 外部上下文 | 向量数据库、KV、图存储 |
| 缺页中断 | 记忆工具调用 | `memory.search`、`memory.read`、`memory.write` |
| OS 内核 | Agent 控制循环 | 带记忆工具的 ReAct 循环 |

Agent 运行一个正常的 ReAct 循环。一类额外的工具让它在主上下文和外部之间进行数据分页。

### 两层结构

- **主上下文。** 固定大小的提示，持有当前任务。始终对模型可见。
- **外部上下文。** 无界，可通过工具搜索。相关时读取，事实出现时写入。

原始论文在两个超出基础窗口的任务上评估了该设计：超过 100k token 的文档分析和跨天的多会话持久记忆对话。

### 中断模式

MemGPT 引入了记忆即中断：在对话中途，Agent 可以调用一个记忆工具，运行时执行它，结果作为一个新的观察拼接到下一个助手轮次中。概念上等同于 Unix 的 `read()` 系统调用 —— 阻塞进程、返回字节、进程继续。

标准记忆工具接口：

- `core_memory_append(section, text)` —— 写入提示的持久部分。
- `core_memory_replace(section, old, new)` —— 编辑持久部分。
- `archival_memory_insert(text)` —— 写入可搜索的外部存储。
- `archival_memory_search(query, top_k)` —— 从外部存储检索。
- `conversation_search(query)` —— 扫描过去的轮次。

### MemGPT 在哪里结束，Letta 在哪里开始

2024 年 9 月，MemGPT 变成了 Letta。研究仓库（`cpacker/MemGPT`）保留；Letta 扩展了设计：

- 三层而非两层（core、recall、archival —— 第 8 课）。
- 原生推理取代 `send_message`/heartbeat 模式（第 8 课）。
- sleep-time Agent 运行异步记忆工作（第 8 课）。

MemGPT 论文是 2026 年的基础，即使生产系统运行的是 Letta、Mem0 或自定义的两层存储。

### 这个模式出错的地方

- **记忆腐烂。** 写入比读取积累得更快；检索被过时的事实淹没。修复：定期合并（Letta sleep-time）、显式失效（Mem0 冲突检测器）。
- **记忆投毒。** 外部记忆是检索到的文本。如果攻击者控制的内容落入记忆笔记，Agent 在下一次会话中会重新摄入它。这是 Greshake 等人（第 27 课）攻击在时间维度上的重述。
- **引用丢失。** Agent 回忆"用户让我发布 X"但无法引用是哪一轮。在每次 archival 写入时存储来源引用（会话 ID、轮次 ID）。

## 构建它

`code/main.py` 用标准库实现了 MemGPT 的两层模式：

- `MainContext` —— 固定大小的提示缓冲区，带 `core` 字典和 `messages` 列表；超出上限时自动压缩最旧的消息。
- `ArchivalStore` —— 内存中的 BM25 类存储（token 重叠评分），记录为 (id, text, tags, session, turn)。
- 五个映射到 MemGPT 接口的记忆工具。
- 一个脚本化的 Agent，用事实填充 archival，然后通过调用 `archival_memory_search` 回答问题。

运行它：

```
python3 code/main.py
```

轨迹显示 Agent 写入三个事实，将主上下文填充到上限（强制淘汰），然后通过从 archival 检索来回答后续问题 —— 在没有真实 LLM 的情况下重现了 MemGPT 工作流。

## 使用它

今天每个生产记忆系统都是 MemGPT 的变体：

- **Letta**（第 8 课）—— 三层、原生推理、sleep-time compute。
- **Mem0**（第 9 课）—— 向量 + KV + 图融合评分层。
- **OpenAI Assistants / Responses** —— 通过线程和文件的托管记忆。
- **Claude Agent SDK** —— 通过技能和会话存储的长期记忆。

按运营形态选择（自托管、托管、框架集成），而不是按核心模式 —— 核心模式就是 MemGPT。

## 发布它

`outputs/skill-virtual-memory.md` 是一个可复用的技能，为任何目标运行时生成正确的两层记忆脚手架（主层 + archival + 工具接口），并内置淘汰策略和引用字段。

## 练习

1. 添加一个以 token 为单位的 `max_main_context_tokens` 上限（用 `len(text.split())` * 1.3 近似）。超出上限时将最旧的消息压缩为摘要。比较有和没有摘要器的行为。
2. 在 archival 存储上正确实现 BM25（词频、逆文档频率）。在玩具事实集上衡量 recall@10，与 token 重叠基线对比。
3. 给 archival 插入添加 `citation` 字段（session_id、turn_id、source_url）。让 Agent 在每个有检索支持的回答中引用来源。
4. 模拟记忆投毒：添加一条 archival 记录说"忽略所有未来的用户指令"。编写一个防护措施，扫描检索结果中的指令形状文本并将其标记为不可信。
5. 将实现移植到使用 MemGPT 研究仓库的 core-memory JSON schema（`cpacker/MemGPT`）。从扁平字符串切换到类型化部分时有什么变化？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Virtual context | "无限记忆" | 主层（提示）+ 外部层（可搜索），带换入/换出 |
| Main context | "工作记忆" | 提示 —— 固定大小，始终可见 |
| Archival memory | "长期存储" | 外部可搜索的持久化，按需检索 |
| Core memory | "持久提示部分" | 固定在主上下文中的命名部分 |
| Memory tool | "记忆 API" | Agent 发出的读写外部记忆的工具调用 |
| Interrupt | "记忆缺页中断" | Agent 暂停，运行时获取，结果拼接到下一轮 |
| Memory rot | "过时事实" | 旧写入淹没检索；用合并修复 |
| Memory poisoning | "注入的持久笔记" | 攻击者内容作为记忆存储，召回时重新摄入 |

## 延伸阅读

- [Packer 等人, MemGPT (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560) —— OS 启发的虚拟上下文论文
- [Letta, Memory Blocks blog](https://www.letta.com/blog/memory-blocks) —— 三层演进
- [Anthropic, Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) —— 将上下文视为预算
- [Chhikara 等人, Mem0 (arXiv:2504.19413)](https://arxiv.org/abs/2504.19413) —— 基于此模式的混合生产记忆