# ColPali 与视觉原生文档 RAG

> 传统 RAG 将 PDF 解析为文本，分块，嵌入块，存储向量。每一步都丢失信号：OCR 丢弃图表数据，分块打破表格行，文本嵌入忽略图形。ColPali（Faysse 等人，2024 年 7 月）提出了更简单的问题：为什么要提取文本？通过 PaliGemma 直接嵌入页面图像，使用 ColBERT 风格的晚期交互进行检索，保留文档携带的所有布局、图形、字体和格式信号。发布的基准：在视觉丰富文档上比文本 RAG 端到端准确率高 20-40%。ColQwen2、ColSmol 和 VisRAG 扩展了该模式。本课解读视觉原生 RAG 论点并构建一个微型 ColPali 风格索引器。

**类型：** Build
**语言：** Python（标准库，多向量索引器 + MaxSim 评分器）
**前置课程：** Phase 11（LLM Engineering — RAG 基础）、Phase 12 · 05（LLaVA）
**时间：** ~180 分钟

## 学习目标

- 解释双编码器检索（每个文档一个向量）和晚期交互检索（每个文档多个向量）之间的区别。
- 描述 ColBERT 的 MaxSim 操作以及 ColPali 如何将其从文本 token 泛化到图像 patch。
- 构建微型 ColPali 风格索引器：页面 → patch 嵌入 → 对查询词嵌入做 MaxSim → top-k 页面。
- 在发票/金融报告用例上对比 ColPali + Qwen2.5-VL 生成器 vs 文本 RAG + GPT-4。

## 问题

文本 RAG 在 PDF 上丢弃了文档的大部分内容。金融报告的 Q3 收入增长通常在图表中；医学报告的发现在注释图像中；法律合同的签名块是布局事实，而非文本事实。

文本 RAG 流水线：

1. PDF → 通过 OCR / pdftotext 转文本。
2. 文本 → 300-500 token 的块。
3. 块 → 双编码器嵌入（一个向量）。
4. 用户查询 → 嵌入 → 余弦相似度 → top-k 块。
5. 块 + 查询 → LLM。

五个有损步骤。图表未捕获。表格跨块断裂。多栏布局展平。图形注释消失。

ColPali 的修复：跳过 OCR，直接嵌入页面图像。使用 ColBERT 风格的晚期交互进行检索，使模型能在查询时关注细粒度 patch。

## 概念

### ColBERT（2020）

ColBERT（Khattab & Zaharia，arXiv:2004.12832）是一种文本检索方法。不是每个文档一个向量，而是每个 token 一个向量。查询时：

- 查询 token 有自己的嵌入（N_q 个向量）。
- 文档 token 有嵌入（N_d 个向量，通常缓存）。
- 分数 = 对每个查询 token，取与所有文档 token 的余弦相似度的最大值，然后求和：Σ_i max_j cos(q_i, d_j)。

这就是 MaxSim 操作。每个查询 token "挑选"其最佳匹配的文档 token。最终分数是求和。

优点：召回率强，处理词级语义。缺点：每个文档 N_d 个向量，存储昂贵。

### ColPali

ColPali（Faysse 等人，arXiv:2407.01449）将 ColBERT 模式应用于图像。

- 每页由 PaliGemma（ViT + 语言）编码为 patch 嵌入：每页 N_p 个向量。
- 每个用户查询（文本）编码为查询 token 嵌入：N_q 个向量。
- 分数 = Σ_i max_j cos(q_i, p_j)，即对查询文本 token 和页面图像 patch 做 MaxSim。
- 按总分检索 top-k 页面。

文档摄取时：用 PaliGemma 嵌入每页，存储所有 patch 嵌入。查询时：嵌入查询 token，对所有存储的页面嵌入计算 MaxSim，返回 top-k 页面。

优点：在视觉丰富文档上端到端比文本 RAG 高 20-40%。每个 patch 向量捕获局部布局和内容。

缺点：N_p 个 patch × 4 字节浮点 × D 维向量每页 = 存储增长快。通过 PQ / OPQ 量化缓解。

### ColQwen2 和 ColSmol

ColQwen2（illuin-tech，2024-2025）将 PaliGemma 换成 Qwen2-VL。更好的基础编码器，更好的检索。

ColSmol 是用于本地/边缘使用的小规模变体。约 1B 参数的 ColSmol 检索器在消费级 GPU 上运行。

### VisRAG

VisRAG（Yu 等人，arXiv:2410.10594）是不同的变体：不在 patch 上做 MaxSim，而是用 VLM 将每页池化为单一向量然后双编码器检索。索引更快 + 存储更小，召回率更弱。

质量 vs 成本权衡：ColPali 追求质量，VisRAG 追求规模。

### M3DocRAG

M3DocRAG（Cho 等人，arXiv:2411.04952）将多模态检索扩展到多页多文档推理。跨文档检索页面，为 VLM 组合多页上下文。

### ViDoRe——基准

ColPali 的配套基准。视觉文档检索评估。任务包括金融报告、科学论文、行政文档、医疗记录、手册。指标：nDCG@5。

ColPali-v1 在 ViDoRe 上得分约 80% nDCG@5；相同文档的文本 RAG 得分约 50-60%。

### 端到端 RAG 流水线

视觉原生 RAG：

1. **摄取**：PDF → 页面图像 → PaliGemma 编码 → 存储所有 patch 嵌入。
2. **查询**：用户文本 → 查询 token 嵌入 → 对所有索引页面做 MaxSim → top-k 页面。
3. **生成**：top-k 页面图像 + 查询 → VLM（Qwen2.5-VL 或 Claude）→ 答案。

完全没有 OCR。图形、图表、字体、布局全部流入答案。

### 存储数学

一份 50 页的金融报告，每页 729 个 patch，128 维嵌入：

- ColPali：50 × 729 × 128 × 4 字节 = 约 18 MB 原始，PQ 后约 4 MB。
- 文本 RAG：50 个块 × 768 维 × 4 字节 = 约 150 kB。

ColPali 每份文档存储约 30 倍。大规模下，OPQ / PQ 将其降至约 5-10 倍，通常可接受。

### 文本 RAG 何时仍然胜出

- 无布局信号的纯文本文档（wiki 文章、聊天记录）。文本 RAG 更简单且存储更便宜。
- 存储主导成本的数百万页档案。
- 严格监管要求检索旁有可提取的 OCR 文本。

2026 年的其他所有场景——金融报告、科学论文、法律合同、医疗记录、UX 文档——视觉原生 RAG 胜出。

## 使用它

`code/main.py`：

- 玩具 patch 编码器：将"页面"（特征向量的小网格）映射到 patch 嵌入数组。
- MaxSim 评分器：计算查询 token 嵌入集与页面 patch 集之间的 ColBERT 风格分数。
- 索引 5 个玩具页面，运行 3 个查询，返回带分数的 top-k。

## 产出

本课生成 `outputs/skill-vision-rag-designer.md`。给定文档 RAG 项目，在 ColPali / ColQwen2 / VisRAG / 文本 RAG 之间选择并确定存储规模。

## 练习

1. 一份 200 页的年度报告，每页 729 个 patch，128 维嵌入，4 字节浮点。计算原始存储和 PQ 压缩（8 倍）存储。

2. MaxSim 是 Σ_i max_j cos(q_i, p_j)。这个求和捕获了什么简单均值相似度没有的？

3. ColPali 以 patch 集索引页面。如果我们在词级别索引（如 ColBERT）会有什么变化？权衡？

4. 为 100 万页语料设计端到端流水线，每查询延迟预算 500ms。选择 ColQwen2 / VisRAG 并提供依据。

5. 阅读 M3DocRAG（arXiv:2411.04952）。描述多页注意力模式及其与单页 ColPali 检索的区别。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Late interaction（晚期交互） | "ColBERT 风格" | 使用每 token 或每 patch 嵌入 + MaxSim 的检索，而非单一文档向量 |
| MaxSim | "patch 上取最大" | 对每个查询 token，选择最高相似度的文档 token；跨查询求和 |
| Bi-encoder（双编码器） | "单向量" | 每个文档一个向量；更快但丢失粒度 |
| Multi-vector（多向量） | "每文档多向量" | 每个文档/页面存储 N_p 个向量；存储成本增长但召回率提升 |
| Patch embedding（patch 嵌入） | "页面特征" | 来自 VLM 编码器的每图像 patch 一个向量，每页缓存 |
| ViDoRe | "视觉文档基准" | ColPali 的视觉文档检索基准套件 |
| PQ quantization（PQ 量化） | "乘积量化" | 在缩小存储约 8 倍的同时保持向量相似度的压缩 |

## 延伸阅读

- [Faysse 等人 — ColPali (arXiv:2407.01449)](https://arxiv.org/abs/2407.01449)
- [Khattab & Zaharia — ColBERT (arXiv:2004.12832)](https://arxiv.org/abs/2004.12832)
- [Yu 等人 — VisRAG (arXiv:2410.10594)](https://arxiv.org/abs/2410.10594)
- [Cho 等人 — M3DocRAG (arXiv:2411.04952)](https://arxiv.org/abs/2411.04952)
- [illuin-tech/colpali GitHub](https://github.com/illuin-tech/colpali)