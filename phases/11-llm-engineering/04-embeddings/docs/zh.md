# Embeddings（嵌入）与向量表示

> 文本是离散的，数学是连续的。每次你让 LLM 查找"相似"文档、比较含义或超越关键词搜索时，你都在依赖这两个世界之间的一座桥梁。这座桥梁就是 embedding。如果你不理解 embeddings，你就不理解现代 AI。你只是在使用它。

**类型：** Build
**语言：** Python
**前置课程：** Phase 11, Lesson 01（Prompt Engineering）
**时间：** ~75 分钟
**相关内容：** Phase 5 · 22（Embedding 模型深入）涵盖 dense vs sparse vs multi-vector、Matryoshka 截断和按轴模型选择。本课聚焦于生产流水线（向量数据库、HNSW、相似度数学）。在选择模型之前请先阅读 Phase 5 · 22。

## 学习目标

- 使用 API 提供商和开源模型生成文本 embedding，并计算它们之间的余弦相似度
- 解释为什么 embedding 解决了关键词搜索无法处理的词汇不匹配问题
- 构建一个语义搜索索引，按含义而非精确关键词匹配来检索文档
- 使用检索基准（precision@k、recall）评估 embedding 质量，并为你的任务选择正确的 embedding 模型

## 问题所在

你有 10,000 张支持工单。一位客户写道"my payment didn't go through"（我的支付没有成功）。你需要找到类似的历史工单。关键词搜索找到包含"payment"和"didn't go through"的工单。但它错过了"transaction failed"（交易失败）、"charge was declined"（扣款被拒绝）和"billing error"（账单错误）。这些工单用完全不同的词汇描述了完全相同的问题。

这就是词汇不匹配问题。人类语言有几十种方式来表达同一件事。关键词搜索将每个单词视为没有含义的独立符号。它无法知道"declined"和"didn't go through"指的是同一个概念。

你需要一种文本表示方式，其中含义而非拼写决定相似度。你需要一种方法，将"my payment didn't go through"和"transaction was declined"在某个数学空间中放置得很近，同时将"my payment arrived on time"（我的支付按时到达）推得很远，尽管它们共享"payment"这个词。

这种表示就是 embedding。

## 核心概念

### 什么是 Embedding？

Embedding 是一个表示文本含义的密集浮点数向量。"密集"这个词很重要——每个维度都携带信息，不像稀疏表示（词袋、TF-IDF）那样大多数维度为零。

"The cat sat on the mat" 变成类似 `[0.023, -0.041, 0.087, ..., 0.012]` 的东西——根据模型不同，是 768 到 3072 个数字的列表。这些数字编码了含义。你永远不会直接检查它们，而是比较它们。

### Word2Vec 的突破

2013 年，Tomas Mikolov 和他在 Google 的同事发表了 Word2Vec。核心洞察：训练一个神经网络从邻居预测一个词（或从一个词预测邻居），隐藏层的权重就变成了有意义的向量表示。

著名的结果：

```
king - man + woman = queen
```

词嵌入上的向量算术捕获了语义关系。从"man"到"woman"的方向大致与从"king"到"queen"的方向相同。这是该领域意识到几何可以编码含义的时刻。

Word2Vec 产生 300 维向量。每个词无论上下文如何都得到一个向量。"river bank"中的"bank"和"bank account"中的"bank"具有相同的 embedding。这个局限性推动了接下来十年的研究。

### 从词到句子

词嵌入表示单个 token。生产系统需要嵌入整个句子、段落或文档。出现了四种方法：

**平均法**：取句子中所有词向量的均值。廉价、有损，但在短文本上出奇地好。完全丢失词序——"dog bites man"和"man bites dog"得到相同的 embedding。

**CLS token**：Transformer 模型（BERT，2018）输出一个特殊的 [CLS] token embedding 来表示整个输入。比平均法好，但 [CLS] token 是为下一句预测训练的，而不是为相似度。

**对比学习**：显式训练模型将相似对推近、不相似对推远。Sentence-BERT（Reimers & Gurevych，2019）使用这种方法，并成为现代 embedding 模型的基础。给定"How do I reset my password?"和"I need to change my password"，模型学习到这两个应该有几乎相同的向量。

**指令调优的 embedding**：最新方法。E5 和 GTE 等模型接受任务前缀（"search_query:"、"search_document:"），告诉模型要产生什么类型的 embedding。这让一个模型可以服务多种任务。

```mermaid
graph LR
    subgraph "2013: Word2Vec"
        W1["king"] --> V1["[0.2, -0.1, ...]"]
        W2["queen"] --> V2["[0.3, -0.2, ...]"]
    end

    subgraph "2019: Sentence-BERT"
        S1["How do I reset my password?"] --> E1["[0.04, 0.12, ...]"]
        S2["I need to change my password"] --> E2["[0.05, 0.11, ...]"]
    end

    subgraph "2024: 指令调优"
        I1["search_query: password reset"] --> T1["[0.08, 0.09, ...]"]
        I2["search_document: To reset your password, click..."] --> T2["[0.07, 0.10, ...]"]
    end
```

### 现代 Embedding 模型

市场已经稳定在少数几个生产级选项上（2026 年初的 MTEB 分数，MTEB v2）：

| 模型 | 提供商 | 维度 | MTEB | 上下文 | 成本 / 1M tokens |
|------|--------|------|------|--------|------------------|
| Gemini Embedding 2 | Google | 3072（Matryoshka） | 67.7（检索） | 8192 | $0.15 |
| embed-v4 | Cohere | 1024（Matryoshka） | 65.2 | 128K | $0.12 |
| voyage-4 | Voyage AI | 1024/2048（Matryoshka） | 66.8 | 32K | $0.12 |
| text-embedding-3-large | OpenAI | 3072（Matryoshka） | 64.6 | 8192 | $0.13 |
| text-embedding-3-small | OpenAI | 1536（Matryoshka） | 62.3 | 8192 | $0.02 |
| BGE-M3 | BAAI | 1024（dense+sparse+ColBERT） | 63.0 多语言 | 8192 | 开源权重 |
| Qwen3-Embedding | Alibaba | 4096（Matryoshka） | 66.9 | 32K | 开源权重 |
| Nomic-embed-v2 | Nomic | 768（Matryoshka） | 63.1 | 8192 | 开源权重 |

MTEB（Massive Text Embedding Benchmark）v2 涵盖 100+ 个任务，跨检索、分类、聚类、重排序和摘要。分数越高越好。到 2026 年，开源权重模型（Qwen3-Embedding、BGE-M3）在大多数维度上匹配或超越闭源托管模型。Gemini Embedding 2 领先纯检索；Voyage/Cohen 领先特定领域（金融、法律、代码）。在提交之前，务必在你自己的查询上进行基准测试。

### 相似度度量

给定两个 embedding 向量，有三种方式衡量它们的相似程度：

**余弦相似度（Cosine similarity）**：两个向量之间夹角的余弦值。范围从 -1（相反方向）到 1（相同方向）。忽略大小——一个 10 词的句子和一个 500 词的文档如果方向相同，可以得 1.0 分。这是 90% 用例的默认选择。

```
cosine_sim(a, b) = dot(a, b) / (||a|| * ||b||)
```

**点积（Dot product）**：两个向量的原始内积。当向量归一化（单位长度）时与余弦相似度相同。计算更快。OpenAI 的 embedding 是归一化的，所以点积和余弦给出相同的排序。

```
dot(a, b) = sum(a_i * b_i)
```

**欧氏距离（Euclidean / L2 distance）**：向量空间中的直线距离。越小越相似。对大小差异敏感。当空间中的绝对位置而不仅仅是方向很重要时使用。

```
L2(a, b) = sqrt(sum((a_i - b_i)^2))
```

何时使用哪种：

| 度量 | 使用场景 | 避免场景 |
|------|---------|---------|
| 余弦相似度 | 比较不同长度的文本；大多数检索任务 | 大小携带信息 |
| 点积 | embedding 已归一化；需要最大速度 | 向量大小不一 |
| 欧氏距离 | 聚类；空间最近邻问题 | 比较长度差异巨大的文档 |

### 向量数据库与 HNSW

暴力相似度搜索将查询与每个存储的向量进行比较。在 100 万个 1536 维的向量上，每次查询需要 15 亿次乘加运算。太慢了。

向量数据库用近似最近邻（ANN）算法解决这个问题。主流算法是 HNSW（Hierarchical Navigable Small World，分层可导航小世界）：

1. 构建向量的多层图
2. 顶层稀疏——远距离集群之间的长距离连接
3. 底层密集——附近向量之间的细粒度连接
4. 搜索从顶层开始，贪心下降以精细化
5. 以 O(log n) 时间返回近似 top-k 结果，而非 O(n)

HNSW 以微小的准确率损失（通常 95-99% recall）换取巨大的速度提升。在 1000 万个向量上，暴力搜索需要数秒，HNSW 需要毫秒。

```mermaid
graph TD
    subgraph "HNSW 层级"
        L2["第 2 层（稀疏）"] -->|"长跳"| L1["第 1 层（中等）"]
        L1 -->|"短跳"| L0["第 0 层（密集，所有向量）"]
    end

    Q["查询向量"] -->|"从顶层进入"| L2
    L0 -->|"最近邻"| R["Top-k 结果"]
```

生产选项：

| 数据库 | 类型 | 最佳场景 | 最大规模 |
|--------|------|---------|---------|
| Pinecone | 托管 SaaS | 零运维生产 | 数十亿 |
| Weaviate | 开源自部署 | 自托管，混合搜索 | 1 亿+ |
| Qdrant | 开源 | 高性能，过滤 | 1 亿+ |
| ChromaDB | 嵌入式 | 原型开发，本地开发 | 100 万 |
| pgvector | Postgres 扩展 | 已在使用 Postgres | 1000 万 |
| FAISS | 库 | 进程内，研究 | 10 亿+ |

### 分块策略（Chunking Strategies）

文档太长，无法作为单个向量嵌入。一个 50 页的 PDF 涵盖几十个主题——它的 embedding 成为所有内容的平均值，与任何具体内容都不相似。你需要将文档拆分为块，然后分别嵌入每个块。

**固定大小分块**：每 N 个 token 拆分一次，有 M 个 token 的重叠。简单且可预测。当文档没有清晰结构时效果好。512 token 的块，50 token 的重叠：块 1 是 token 0-511，块 2 是 token 462-973。

**基于句子的分块**：在句子边界处分拆，将句子分组直到达到 token 上限。每个块至少是一个完整句子。比固定大小好，因为你永远不会把一个想法切两半。

**递归分块**：先尝试在最大边界处拆分（章节标题）。如果仍然太大，尝试段落边界。然后是句子边界。然后是字符限制。这就是 LangChain 的 `RecursiveCharacterTextSplitter`，对混合格式的语料库效果很好。

**语义分块**：嵌入每个句子，然后将 embedding 相似的连续句子分组。当 embedding 相似度低于阈值时，开始一个新块。昂贵（需要单独嵌入每个句子）但产生最连贯的块。

| 策略 | 复杂度 | 质量 | 最佳场景 |
|------|--------|------|---------|
| 固定大小 | 低 | 尚可 | 非结构化文本，日志 |
| 基于句子 | 低 | 好 | 文章，邮件 |
| 递归 | 中等 | 好 | Markdown、HTML、混合文档 |
| 语义 | 高 | 最佳 | 关键检索质量 |

大多数系统的最佳点：256-512 token 的块，50 token 的重叠。

### 双编码器（Bi-Encoder）vs 交叉编码器（Cross-Encoder）

双编码器独立嵌入查询和文档，然后比较向量。速度快——你嵌入查询一次，然后与预计算的文档 embedding 比较。这是你用于检索的方式。

交叉编码器将查询和文档作为单个输入，输出相关性分数。速度慢——它通过完整模型处理每个查询-文档对。但准确得多，因为它可以同时关注查询和文档的 token。

生产模式：双编码器检索 top-100 候选，交叉编码器重排到 top-10。这就是检索-然后重排（retrieve-then-rerank）流水线。

```mermaid
graph LR
    Q["查询"] --> BE["双编码器：嵌入查询"]
    BE --> VS["向量搜索：top 100"]
    VS --> CE["交叉编码器：重排"]
    CE --> R["Top 10 结果"]
```

重排模型：Cohere Rerank 3.5（每 1000 次查询 $2），BGE-reranker-v2（免费，开源），Jina Reranker v2（免费，开源）。

### Matryoshka Embedding

传统 embedding 是全有或全无的。一个 1536 维的向量使用 1536 个浮点数。你无法在不重新训练的情况下截断到 256 维。

Matryoshka 表示学习（Kusupati et al., 2022）解决了这个问题。模型被训练为前 N 个维度捕获最重要的信息，就像俄罗斯套娃一样。将 1536 维的 Matryoshka embedding 截断到 256 维会损失一些准确率，但仍然可用。

OpenAI 的 text-embedding-3-small 和 text-embedding-3-large 通过 `dimensions` 参数支持 Matryoshka 截断。请求 256 维而非 1536 维将存储减少 6 倍，在 MTEB 基准测试上大约损失 3-5% 的准确率。

### 二值量化（Binary Quantization）

一个 1536 维的 embedding 以 float32 存储使用 6,144 字节。乘以 1000 万个文档：仅向量就需要 61 GB。

二值量化将每个浮点数转换为一个比特：正值变为 1，负值变为 0。存储从 6,144 字节降到 192 字节——32 倍的缩减。相似度使用汉明距离（计算不同比特数）计算，CPU 可以在单条指令内完成。

准确率损失大约在检索 recall 上 5-10%。常见模式：对数百万向量的首轮搜索使用二值量化，然后用全精度向量对 top-1000 重新评分。这让你以 32 倍更少的内存获得 95%+ 的全精度准确率。

## 动手构建

我们从零构建一个语义搜索引擎。没有向量数据库，没有外部 embedding API。纯 Python 加 numpy 进行数学运算。

### 步骤 1：文本分块

```python
def chunk_text(text, chunk_size=200, overlap=50):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def chunk_by_sentences(text, max_chunk_tokens=200):
    sentences = text.replace("\n", " ").split(".")
    sentences = [s.strip() + "." for s in sentences if s.strip()]
    chunks = []
    current_chunk = []
    current_length = 0
    for sentence in sentences:
        sentence_length = len(sentence.split())
        if current_length + sentence_length > max_chunk_tokens and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0
        current_chunk.append(sentence)
        current_length += sentence_length
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks
```

### 步骤 2：从零构建 Embedding

我们使用 TF-IDF 加 L2 归一化实现一个简单的密集 embedding。这不是神经 embedding，但它遵循相同的契约：输入文本，输出固定大小的向量，相似的文本产生相似的向量。

```python
import math
import numpy as np
from collections import Counter

class SimpleEmbedder:
    def __init__(self):
        self.vocab = []
        self.idf = []
        self.word_to_idx = {}

    def fit(self, documents):
        vocab_set = set()
        for doc in documents:
            vocab_set.update(doc.lower().split())
        self.vocab = sorted(vocab_set)
        self.word_to_idx = {w: i for i, w in enumerate(self.vocab)}
        n = len(documents)
        self.idf = np.zeros(len(self.vocab))
        for i, word in enumerate(self.vocab):
            doc_count = sum(1 for doc in documents if word in doc.lower().split())
            self.idf[i] = math.log((n + 1) / (doc_count + 1)) + 1

    def embed(self, text):
        words = text.lower().split()
        count = Counter(words)
        total = len(words) if words else 1
        vec = np.zeros(len(self.vocab))
        for word, freq in count.items():
            if word in self.word_to_idx:
                tf = freq / total
                vec[self.word_to_idx[word]] = tf * self.idf[self.word_to_idx[word]]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec
```

### 步骤 3：相似度函数

```python
def cosine_similarity(a, b):
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def dot_product(a, b):
    return float(np.dot(a, b))


def euclidean_distance(a, b):
    return float(np.linalg.norm(a - b))
```

### 步骤 4：带暴力搜索的向量索引

```python
class VectorIndex:
    def __init__(self):
        self.vectors = []
        self.texts = []
        self.metadata = []

    def add(self, vector, text, meta=None):
        self.vectors.append(vector)
        self.texts.append(text)
        self.metadata.append(meta or {})

    def search(self, query_vector, top_k=5, metric="cosine"):
        scores = []
        for i, vec in enumerate(self.vectors):
            if metric == "cosine":
                score = cosine_similarity(query_vector, vec)
            elif metric == "dot":
                score = dot_product(query_vector, vec)
            elif metric == "euclidean":
                score = -euclidean_distance(query_vector, vec)
            else:
                raise ValueError(f"Unknown metric: {metric}")
            scores.append((i, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scores[:top_k]:
            results.append({
                "text": self.texts[idx],
                "score": score,
                "metadata": self.metadata[idx],
                "index": idx
            })
        return results

    def size(self):
        return len(self.vectors)
```

### 步骤 5：语义搜索引擎

```python
class SemanticSearchEngine:
    def __init__(self, chunk_size=200, overlap=50):
        self.embedder = SimpleEmbedder()
        self.index = VectorIndex()
        self.chunk_size = chunk_size
        self.overlap = overlap

    def index_documents(self, documents, source_names=None):
        all_chunks = []
        all_sources = []
        for i, doc in enumerate(documents):
            chunks = chunk_text(doc, self.chunk_size, self.overlap)
            all_chunks.extend(chunks)
            name = source_names[i] if source_names else f"doc_{i}"
            all_sources.extend([name] * len(chunks))
        self.embedder.fit(all_chunks)
        for chunk, source in zip(all_chunks, all_sources):
            vec = self.embedder.embed(chunk)
            self.index.add(vec, chunk, {"source": source})
        return len(all_chunks)

    def search(self, query, top_k=5, metric="cosine"):
        query_vec = self.embedder.embed(query)
        return self.index.search(query_vec, top_k, metric)

    def search_with_scores(self, query, top_k=5):
        results = self.search(query, top_k)
        return [
            {
                "text": r["text"][:200],
                "source": r["metadata"].get("source", "unknown"),
                "score": round(r["score"], 4)
            }
            for r in results
        ]
```

### 步骤 6：比较相似度度量

```python
def compare_metrics(engine, query, top_k=3):
    results = {}
    for metric in ["cosine", "dot", "euclidean"]:
        hits = engine.search(query, top_k=top_k, metric=metric)
        results[metric] = [
            {"score": round(h["score"], 4), "preview": h["text"][:80]}
            for h in hits
        ]
    return results
```

## 实际应用

使用生产级 embedding API 时，架构保持不变。只有 embedder 发生变化：

```python
from openai import OpenAI

client = OpenAI()

def openai_embed(texts, model="text-embedding-3-small", dimensions=None):
    kwargs = {"model": model, "input": texts}
    if dimensions:
        kwargs["dimensions"] = dimensions
    response = client.embeddings.create(**kwargs)
    return [item.embedding for item in response.data]
```

使用 OpenAI 的 Matryoshka 截断——相同模型，更少维度，更低存储：

```python
full = openai_embed(["semantic search query"], dimensions=1536)
compact = openai_embed(["semantic search query"], dimensions=256)
```

256 维向量使用 6 倍更少的存储。对于 1000 万个文档，就是 10 GB vs 61 GB。在标准基准测试上的准确率损失大约 3-5%。

使用 Cohere 进行重排：

```python
import cohere

co = cohere.ClientV2()

results = co.rerank(
    model="rerank-v3.5",
    query="What is the refund policy?",
    documents=["Full refund within 30 days...", "No refunds after 90 days..."],
    top_n=3
)
```

使用本地 embedding 无 API 依赖：

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-en-v1.5")
embeddings = model.encode(["semantic search query", "another document"])
```

我们构建的 VectorIndex 类可以与以上任何一种配合使用。替换 embedding 函数，保持搜索逻辑不变。

## 产出物

本课产出：
- `outputs/prompt-embedding-advisor.md` — 一个用于为特定用例选择 embedding 模型和策略的提示词
- `outputs/skill-embedding-patterns.md` — 一个教 Agent 如何在生产中有效使用 embedding 的技能

## 练习

1. **度量比较**：使用余弦相似度、点积和欧氏距离对相同的 5 个查询在样本文档上运行。记录每种度量的 top-3 结果。哪些查询上度量结果不一致？为什么？

2. **块大小实验**：分别用 50、100、200 和 500 词的块大小索引样本文档。对每种大小运行 5 个查询并记录 top-1 相似度分数。绘制块大小与检索质量之间的关系。找到更大的块开始降低效果的拐点。

3. **Matryoshka 模拟**：构建一个产生 500 维向量的 SimpleEmbedder。截断到 50、100、200 和 500 维。衡量在每种截断下检索 recall 如何下降。这模拟了 Matryoshka 行为而不需要真正的训练技巧。

4. **二值量化**：取搜索引擎的 embedding，将它们转换为二值（正值为 1，负值为 0），实现汉明距离搜索。将 top-10 结果与全精度余弦相似度进行比较。衡量重叠百分比。

5. **基于句子的分块**：用 `chunk_by_sentences` 替换固定大小分块。运行相同的查询并比较检索分数。尊重句子边界是否改善了结果？

## 关键术语

| 术语 | 人们常说的 | 实际含义 |
|------|-----------|----------|
| Embedding（嵌入） | "文本转数字" | 一种密集向量，其中几何接近性编码语义相似度 |
| Word2Vec | "OG embedding" | 2013 年通过预测上下文词学习词向量的模型；证明了向量算术编码含义 |
| Cosine similarity（余弦相似度） | "两个向量有多相似" | 向量之间夹角的余弦值；1 = 相同方向，0 = 正交，-1 = 相反 |
| HNSW | "快速向量搜索" | 分层可导航小世界图——多层结构，实现 O(log n) 的近似最近邻搜索 |
| Bi-encoder（双编码器） | "分开嵌入，快速比较" | 将查询和文档独立编码为向量；支持预计算和快速检索 |
| Cross-encoder（交叉编码器） | "慢但准确的重排器" | 通过完整模型联合处理查询-文档对；更高准确率，无法预计算 |
| Matryoshka embeddings | "可截断的向量" | 训练为前 N 个维度捕获最重要信息的 embedding，支持可变大小存储 |
| Binary quantization（二值量化） | "1-bit embedding" | 将浮点向量转换为二值（仅符号位），实现 32 倍存储缩减和汉明距离搜索 |
| Chunking（分块） | "拆分文档以便嵌入" | 将文档拆分为 256-512 token 的段，以便独立嵌入和检索 |
| Vector database（向量数据库） | "embedding 的搜索引擎" | 为存储向量和大规模执行近似最近邻搜索而优化的数据存储 |
| Contrastive learning（对比学习） | "通过比较训练" | 将相似对 embedding 推近、不相似对 embedding 推远的训练方法 |
| MTEB | "embedding 基准测试" | Massive Text Embedding Benchmark——8 个任务的 56 个数据集；比较 embedding 模型的标准 |

## 延伸阅读

- Mikolov et al., "Efficient Estimation of Word Representations in Vector Space" (2013) — 用 king-queen 类比开启 embedding 革命的 Word2Vec 论文
- Reimers & Gurevych, "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks" (2019) — 如何训练用于句子级相似度的双编码器，现代 embedding 模型的基础
- Kusupati et al., "Matryoshka Representation Learning" (2022) — OpenAI 为 text-embedding-3 采用的可变维度 embedding 背后的技术
- Malkov & Yashunin, "Efficient and Robust Approximate Nearest Neighbor using Hierarchical Navigable Small World Graphs" (2018) — HNSW 论文，大多数生产向量搜索背后的算法
- OpenAI Embeddings Guide (platform.openai.com/docs/guides/embeddings) — text-embedding-3 模型的实用参考，包括 Matryoshka 降维
- MTEB Leaderboard (huggingface.co/spaces/mteb/leaderboard) — 跨任务和语言比较所有 embedding 模型的实时基准
- [Muennighoff et al., "MTEB: Massive Text Embedding Benchmark" (EACL 2023)](https://arxiv.org/abs/2210.07316) — 定义 8 个任务类别（分类、聚类、配对分类、重排序、检索、STS、摘要、双语挖掘）的基准；在信任任何单一 MTEB 分数之前请先阅读
- [Sentence Transformers documentation](https://www.sbert.net/) — 双编码器 vs 交叉编码器、池化策略以及本课实现的 ingest-split-embed-store RAG 流水线的权威参考