# 混合记忆：向量 + 图 + KV（Mem0）

> Mem0（Chhikara 等人，2025）将记忆视为三个并行存储 —— 向量用于语义相似度，KV 用于快速事实查找，图用于实体-关系推理。检索时一个评分层融合三者。这是 2026 年外部记忆的生产标准。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 07（MemGPT）、Phase 14 · 08（Letta Blocks）
**时间：** ~75 分钟

## 学习目标

- 解释为什么单一存储（仅向量、仅图、仅 KV）对 Agent 记忆来说是不够的。
- 说出 Mem0 的三个并行存储及其各自优化的目标。
- 描述 Mem0 的融合评分 —— 相关性、重要性、时效性 —— 以及为什么它是加权求和而非层级。
- 用标准库实现一个玩具三存储记忆，包含写入所有三个存储的 `add()` 和融合结果的 `search()`。

## 问题

单一存储对三类查询中的某一类来说是错误的：

- **语义相似度** —— "我们上周讨论了什么关于 Agent 漂移的内容？"向量胜出；KV 和图遗漏。
- **事实查找** —— "用户的电话号码是什么？"KV 胜出；向量浪费，图过度。
- **关系推理** —— "哪些客户共享同一个账单实体？"图胜出；向量和 KV 无法回答。

生产 Agent 在一次会话中发出所有三种查询。单一存储记忆对其中两种总是错误的。Mem0 的贡献是将三者接线在单一的 `add`/`search` 接口之后，用一个评分函数融合它们。

## 核心概念

### 三个并行存储

Mem0（arXiv:2504.19413，2025 年 4 月）在 `add(text, user_id, metadata)` 时：

1. 从文本中提取候选事实（LLM 驱动的步骤）。
2. 将每个事实写入向量存储（embedding）用于语义搜索。
3. 将每个事实以 (user_id, fact_type, entity) 为键写入 KV 存储，用于 O(1) 查找。
4. 将每个事实作为类型化边写入图存储（Mem0g），用于关系查询。

在 `search(query, user_id)` 时：

1. 向量存储按 embedding 余弦相似度返回 top-k。
2. KV 存储按查询派生的 (user_id, type, entity) 键返回直接命中。
3. 图存储返回从查询实体可达的子图。
4. 评分层融合三者。

### 融合评分

```
score = w_relevance * relevance(q, record)
      + w_importance * importance(record)
      + w_recency * recency(record)
```

- **相关性（Relevance）** — 向量余弦、KV 精确匹配、图路径权重。
- **重要性（Importance）** — 写入时标记或学习得到（某些事实更重要：姓名、ID、政策）。
- **时效性（Recency）** — 距离上次写入或读取的时间指数衰减。

权重按产品调节。聊天 Agent 更高 `w_recency`；合规 Agent 更高 `w_importance`；检索 Agent 更高 `w_relevance`。

### Mem0g 与时序推理

Mem0g 添加了一个冲突检测器。当新事实与现有边矛盾时，现有边被标记为无效但不删除。时序查询（"用户三月的城市是哪里？"）遍历在该时间点有效的子图。

这是 Letta 失效模式泛化的合规级行为。

### 基准数据

Mem0 论文报告（2025）：

- **LoCoMo**（长对话记忆）：91.6
- **LongMemEval**（长周期情景记忆）：93.4
- **BEAM 1M**（百万 token 记忆基准）：64.1

比较基线（全文 128k LLM、扁平向量存储、扁平 KV）全部落后 10+ 分。基准数字本身不能证明选择 —— 运营形态才能 —— 但数字表明融合设计不是舍入误差。

### 范围分类法

Mem0 按范围划分记忆：

- **用户记忆** — 跨会话持久化，以 `user_id` 为键。
- **会话记忆** — 在一个线程内持久化。
- **Agent 记忆** — 每个 Agent 实例状态。

每次写入选择一个范围。检索可以跨范围查询，使用每范围的权重。不加思考地混合范围就是你得到"助手向 Alice 透露了 Bob 的项目"这类事件的原因。

### 这个模式出错的地方

- **Embedding 漂移。** 前几百次查询看起来正确的向量结果会随着语料库增长而退化。添加对最常用 top-N 记录的定期重新嵌入。
- **KV schema 蔓延。** `(user_id, type, entity)` 看起来简单，直到每个团队都添加自己的 `type`。每季度审计类型集合。
- **图爆炸。** 一个有噪声的提取器每条消息添加 50 条边。限制每次 `add` 调用的图写入；丢弃低置信度的边。

## 构建它

`code/main.py` 用标准库实现了三存储模式：

- `VectorStore` — 简单的 token 重叠相似度作为 embedding 替代。
- `KVStore` — 以 `(user_id, fact_type, entity)` 为键的字典。
- `GraphStore` — 类型化边（subject、relation、object、valid）。
- `Mem0` — 顶层门面，带 `add()`、`search()`、融合评分和范围感知检索。
- 一个多用户、多会话对话的完整轨迹。

运行它：

```
python3 code/main.py
```

输出展示三条独立的召回路径加上融合后的 top-k。在 `main()` 顶部翻转评分权重，观察排名变化。

## 使用它

- **Mem0（Apache 2.0）** — 生产就绪。用 Postgres + Qdrant + Neo4j 自托管，或使用托管云。
- **Letta** — 三层 core/recall/archival；自带向量和图后端。
- **Zep** — 商业替代方案，带时序知识图谱和事实提取。
- **自定义构建** — 当你需要精确控制提取器（合规）或融合权重（语音 Agent 中时效性主导）时。

## 发布它

`outputs/skill-hybrid-memory.md` 生成一个三存储记忆脚手架，带融合评分器、范围分类法和时序失效。

## 练习

1. 将玩具向量相似度替换为真实的 embedding 模型（sentence-transformers、Ollama、OpenAI embeddings）。在合成长对话上衡量 recall@10。1000 次写入后排名会漂移吗？
2. 添加时序查询：`search(query, as_of=timestamp)`。仅返回在该时间点或之前有效的记录。哪个存储需要最多的工作？
3. 实现冲突检测器：如果传入的事实与图边矛盾，失效旧边并记录两者。在"用户住在柏林" -> "用户住在里斯本"上测试。
4. 将融合评分器扩展为包含 `user_feedback` 维度（对检索记录的点赞）。你如何防止博弈（Agent 只返回它已经喜欢的记录）？
5. 阅读 Mem0 文档（`docs.mem0.ai`）。将玩具代码移植为 `mem0` 客户端调用。在相同的 20 个测试查询上比较检索质量。

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Hybrid memory | "向量加图加 KV" | 三个并行写入的存储，检索时融合 |
| Fact extraction | "记忆摄入" | 将文本拆分为 (entity, relation, fact) 元组的 LLM 步骤 |
| Fusion scoring | "相关性排序" | 相关性、重要性、时效性的加权求和 |
| Scope | "记忆命名空间" | user / session / agent — 决定谁能看到什么 |
| Mem0g | "记忆图" | 带时序有效性的类型化边，用于关系查询 |
| Temporal invalidation | "软删除" | 标记矛盾的边为无效；从不删除 |
| Embedding drift | "检索腐烂" | 随语料库增长向量质量下降；定期重新嵌入 |

## 延伸阅读

- [Chhikara 等人, Mem0 (arXiv:2504.19413)](https://arxiv.org/abs/2504.19413) — 原始论文
- [Mem0 docs](https://docs.mem0.ai/platform/overview) — 生产 API、SDK、托管云
- [Packer 等人, MemGPT (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560) — 虚拟上下文前身
- [Letta, Memory Blocks blog](https://www.letta.com/blog/memory-blocks) — 三层兄弟设计