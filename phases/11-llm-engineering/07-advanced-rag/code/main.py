# =============================================================================
# 高级 RAG（Advanced RAG）：从基础检索到生产级检索增强生成
# 本文件对应课程文档：phases/11-llm-engineering/07-advanced-rag/docs/zh.md
# 参考来源：
#   - Robertson & Zaragoza (2009): BM25 (Okapi BM25 排序函数)
#   - Cormack et al. (2009): Reciprocal Rank Fusion (倒数排名融合)
#   - Gao et al. (2023): HyDE - Hypothetical Document Embeddings
# =============================================================================
#
# 【初学者导读】
# RAG = Retrieval-Augmented Generation（检索增强生成）
# 核心思想：先从知识库中检索相关文档，再把文档交给 LLM 生成回答。
#
# 基础 RAG 的问题：只用一种检索方式，可能漏掉重要文档。
# 本文件展示了6种"高级 RAG"技术来解决这个问题：
#
#   1. BM25 关键词检索  - 精确匹配关键词（如 "refund policy"）
#   2. 向量检索（TF-IDF） - 语义相似度匹配（如 "money" ≈ "revenue"）
#   3. 混合检索 + RRF   - 结合 BM25 和向量检索的优点
#   4. 重排序（Reranking）- 对检索结果二次排序，提高精度
#   5. HyDE             - 先生成假设答案，再用它检索（解决查询和文档用词不同）
#   6. 父子分块          - 小块精确检索，大块提供上下文
#   7. 忠实度评估        - 检查回答是否有"幻觉"（不在文档中的内容）
#
# 【RAG 的核心流程】
# 文档 → 分块 → 向量化 → 存储
# 用户查询 → 向量化 → 检索最相似的块 → 组成提示词 → LLM 生成回答
#
# 【运行方式】
# python main.py（纯 Python 实现，无需额外依赖）
#

import math
from collections import Counter


# =============================================================================
# 第一部分：文本分块（Text Chunking）
# =============================================================================
# 【为什么要分块？】
# 文档通常很长（几千到几万字），但 LLM 的上下文窗口有限。
# 我们需要把长文档切成小块（chunk），每块约200个词。
#
# 【重叠（overlap）的作用】
# 如果块与块之间没有重叠，一个完整的句子可能被切成两半，
# 语义就不完整了。overlap=50 意味着每块和下一块重叠50个词，
# 确保语义连续性。
#
# 【示例】
# 原文: "The cat sat on the mat. The dog lay on the rug."
# 块1 (size=6, overlap=2): "The cat sat on the mat. The"
# 块2 (size=6, overlap=2): "mat. The dog lay on the rug."
# 注意 "mat. The" 出现在两块中，这就是重叠。

def chunk_text(text, chunk_size=200, overlap=50):
    """将长文本切分为有重叠的小块。

    参数:
        text (str): 要切分的文本
        chunk_size (int): 每块的单词数
        overlap (int): 相邻块之间的重叠单词数

    返回:
        list: 文本块列表
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        # 步长 = chunk_size - overlap，这样相邻块就有 overlap 个词的重叠
        start += chunk_size - overlap
    return chunks


# =============================================================================
# 第二部分：TF-IDF 向量化（TF-IDF Vectorization）
# =============================================================================
# 【什么是 TF-IDF？】
# TF-IDF 是一种将文本转换为数字向量的经典方法。
#
# TF（Term Frequency，词频）= 一个词在文档中出现的频率
#   例如：文档有100个词，"refund"出现了3次 → TF = 3/100 = 0.03
#
# IDF（Inverse Document Frequency，逆文档频率）= 一个词的"稀有程度"
#   如果"refund"只在1/6的文档中出现 → IDF 高（稀有词，信息量大）
#   如果"the"在所有文档中都出现 → IDF 低（常见词，信息量小）
#
# TF-IDF = TF × IDF
#   高 TF-IDF 意味着：这个词在本文档中频繁出现，但在其他文档中少见
#   → 这个词能很好地代表本文档的内容
#
# 【与神经网络嵌入的区别】
# TF-IDF 是基于统计的（数词频），不理解语义。
# 例如 "money" 和 "revenue" 在 TF-IDF 中完全不相关。
# 神经网络嵌入（如 BERT、OpenAI Embeddings）能理解语义相似性。
# 这里用 TF-IDF 是为了教学目的（纯 Python 实现，无需 GPU）。

def build_vocabulary(documents):
    """从所有文档中构建词汇表（所有不重复的词，按字母排序）。

    参数:
        documents (list): 文档列表

    返回:
        list: 排序后的词汇列表
    """
    vocab = set()
    for doc in documents:
        vocab.update(doc.lower().split())
    return sorted(vocab)


def compute_tf(text, vocab):
    """计算词频（Term Frequency）。

    【公式】TF(词) = 该词在文档中出现的次数 / 文档总词数

    参数:
        text (str): 文档文本
        vocab (list): 词汇表

    返回:
        list: 每个词的 TF 值（顺序与 vocab 一致）
    """
    words = text.lower().split()
    count = Counter(words)
    total = len(words)
    if total == 0:
        return [0.0] * len(vocab)
    return [count.get(word, 0) / total for word in vocab]


def compute_idf(documents, vocab):
    """计算逆文档频率（Inverse Document Frequency）。

    【公式】IDF(词) = log((总文档数+1) / (包含该词的文档数+1)) + 1

    【直觉】
    - 如果一个词在所有文档中都出现（如 "the"），IDF ≈ 1（低权重）
    - 如果一个词只在1个文档中出现（如 "refund"），IDF 高（高权重）

    参数:
        documents (list): 所有文档
        vocab (list): 词汇表

    返回:
        list: 每个词的 IDF 值
    """
    n = len(documents)
    idf = []
    for word in vocab:
        doc_count = sum(1 for doc in documents if word in doc.lower().split())
        idf.append(math.log((n + 1) / (doc_count + 1)) + 1)
    return idf


def tfidf_embed(text, vocab, idf):
    """将文本转换为 TF-IDF 向量。

    【向量是什么？】
    向量就是一个数字列表，例如 [0.03, 0.0, 0.15, ...]
    每个数字代表词汇表中对应词的 TF-IDF 值。
    两个文本的向量越相似（余弦相似度越高），内容越相关。

    参数:
        text (str): 要向量化的文本
        vocab (list): 词汇表
        idf (list): IDF 值列表

    返回:
        list: TF-IDF 向量
    """
    tf = compute_tf(text, vocab)
    return [t * i for t, i in zip(tf, idf)]


# =============================================================================
# 第三部分：余弦相似度 + 向量检索
# =============================================================================
# 【什么是余弦相似度？】
# 两个向量之间的"夹角"的余弦值。
# - 值为 1.0 → 完全相同的方向（内容最相关）
# - 值为 0.0 → 完全垂直（内容不相关）
# - 值为 -1.0 → 完全相反（实际中很少出现）
#
# 【向量检索】
# 把查询也转成向量，然后和所有文档向量计算余弦相似度，
# 返回最相似的 top_k 个文档。

def cosine_similarity(a, b):
    """计算两个向量的余弦相似度。

    【公式】cos(θ) = (A·B) / (|A| × |B|)
    其中 A·B 是点积，|A| 是向量长度（L2范数）

    参数:
        a (list): 向量A
        b (list): 向量B

    返回:
        float: -1.0 到 1.0 之间的相似度
    """
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def vector_search(query_embedding, stored_embeddings, top_k=5):
    """向量检索：找到与查询最相似的文档。

    参数:
        query_embedding (list): 查询的向量
        stored_embeddings (list): 所有文档的向量
        top_k (int): 返回前几个最相似的

    返回:
        list: [(文档索引, 相似度分数), ...] 按相似度降序排列
    """
    scores = []
    for i, emb in enumerate(stored_embeddings):
        sim = cosine_similarity(query_embedding, emb)
        scores.append((i, sim))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


# =============================================================================
# 第四部分：BM25 关键词检索
# =============================================================================
# 【什么是 BM25？】
# BM25（Best Matching 25）是信息检索领域的经典算法，
# 广泛用于搜索引擎（如 Elasticsearch 的默认排序算法）。
#
# 【BM25 vs TF-IDF】
# - TF-IDF：词频越高分越高（但一个词出现100次不一定比10次重要10倍）
# - BM25：词频有"饱和"效应（出现足够多次后，分数不再显著增加）
# - BM25：还考虑文档长度（长文档天然包含更多词，需要惩罚）
#
# 【两个关键参数】
# k1 (1.2): 控制词频饱和速度。k1越大，词频的影响越大。
# b  (0.75): 控制文档长度惩罚。b=1 表示完全按长度惩罚，b=0 不惩罚。
#
# 【BM25 公式】
# score(q, d) = Σ IDF(term) × (tf × (k1+1)) / (tf + k1 × (1-b+b×|d|/avgdl))
# 其中：
#   tf = 词在文档中的出现次数
#   IDF = 逆文档频率
#   |d| = 文档长度
#   avgdl = 平均文档长度

class BM25:
    """BM25 检索器。

    【使用方法】
    1. 创建实例：bm25 = BM25()
    2. 索引文档：bm25.index(documents)
    3. 检索：results = bm25.search("查询词", top_k=5)
    """
    def __init__(self, k1=1.2, b=0.75):
        self.k1 = k1          # 词频饱和参数
        self.b = b            # 文档长度惩罚参数
        self.docs = []        # 原始文档列表
        self.doc_lengths = [] # 每个文档的词数
        self.avg_dl = 0       # 平均文档长度
        self.doc_freqs = {}   # 包含每个词的文档数量
        self.n_docs = 0       # 总文档数

    def index(self, documents):
        """建立索引：预计算所有文档的统计信息。

        【索引做了什么？】
        1. 计算每个文档的长度
        2. 统计每个词出现在多少个文档中（文档频率）
        3. 计算平均文档长度
        """
        self.docs = documents
        self.n_docs = len(documents)
        self.doc_lengths = []
        self.doc_freqs = {}

        for doc in documents:
            words = doc.lower().split()
            self.doc_lengths.append(len(words))
            # 统计文档频率：每个词出现在几个文档中
            unique_words = set(words)
            for word in unique_words:
                self.doc_freqs[word] = self.doc_freqs.get(word, 0) + 1

        self.avg_dl = sum(self.doc_lengths) / self.n_docs if self.n_docs else 1

    def score(self, query, doc_idx):
        """计算查询和指定文档的 BM25 分数。

        参数:
            query (str): 查询文本
            doc_idx (int): 文档索引

        返回:
            float: BM25 分数（越高越相关）
        """
        query_words = query.lower().split()
        doc_words = self.docs[doc_idx].lower().split()
        doc_len = self.doc_lengths[doc_idx]
        word_counts = Counter(doc_words)
        total = 0.0

        for term in query_words:
            if term not in word_counts:
                continue  # 文档中没有这个词，跳过
            tf = word_counts[term]
            df = self.doc_freqs.get(term, 0)
            # IDF 计算（BM25 版本）
            idf = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1)
            # BM25 的 TF 归一化（有饱和效应）
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_dl)
            total += idf * numerator / denominator

        return total

    def search(self, query, top_k=10):
        """检索与查询最相关的文档。

        参数:
            query (str): 查询文本
            top_k (int): 返回前几个

        返回:
            list: [(文档索引, BM25分数), ...]
        """
        scores = [(i, self.score(query, i)) for i in range(self.n_docs)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# =============================================================================
# 第五部分：倒数排名融合（Reciprocal Rank Fusion, RRF）
# =============================================================================
# 【什么是 RRF？】
# 当你有多个检索结果列表（如 BM25 的结果和向量检索的结果），
# RRF 是一种简单有效的方法来合并它们。
#
# 【公式】RRF_score(doc) = Σ 1/(k + rank_i)
# 其中：
#   k = 60（常数，防止排名靠前的文档权重过大）
#   rank_i = 文档在第 i 个列表中的排名（从0开始）
#
# 【为什么有效？】
# - 如果一个文档在两个列表中都排第1 → RRF 很高
# - 如果一个文档只在一个列表中排第1 → RRF 较低
# - RRF 不需要关心不同检索方法的分数尺度（BM25分数和向量分数无法直接比较）

def reciprocal_rank_fusion(ranked_lists, k=60):
    """用 RRF 合并多个排名列表。

    参数:
        ranked_lists (list): 多个排名列表，每个是 [(doc_id, score), ...]
        k (int): 平滑常数（默认60）

    返回:
        list: 融合后的 [(doc_id, rrf_score), ...] 按分数降序排列
    """
    scores = {}
    for ranked_list in ranked_lists:
        for rank, (doc_id, _) in enumerate(ranked_list):
            if doc_id not in scores:
                scores[doc_id] = 0.0
            # RRF 公式：每个排名贡献 1/(k+rank+1)
            scores[doc_id] += 1.0 / (k + rank + 1)
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused


def hybrid_search(query, chunks, vector_embeddings, vocab, idf, bm25_index, top_k=5, retrieval_pool=15):
    """混合检索：结合向量检索和 BM25，用 RRF 融合。

    【流程】
    1. 用向量检索找到 top-15 个候选
    2. 用 BM25 检索找到 top-15 个候选
    3. 用 RRF 融合两个列表
    4. 返回融合后的 top-k 个结果

    参数:
        query (str): 查询文本
        chunks (list): 所有文本块
        vector_embeddings (list): 所有文本块的向量
        vocab (list): 词汇表
        idf (list): IDF 值
        bm25_index: BM25 索引对象
        top_k (int): 最终返回的结果数
        retrieval_pool (int): 每种方法的候选数
    """
    query_emb = tfidf_embed(query, vocab, idf)
    vec_results = vector_search(query_emb, vector_embeddings, top_k=retrieval_pool)
    bm25_results = bm25_index.search(query, top_k=retrieval_pool)
    fused = reciprocal_rank_fusion([vec_results, bm25_results])
    return fused[:top_k]


# =============================================================================
# 第六部分：重排序（Reranking）
# =============================================================================
# 【什么是重排序？】
# 第一阶段检索（BM25 + 向量）速度很快但不够精确。
# 重排序是第二阶段：对第一阶段的候选结果进行更精细的评分。
#
# 【本实现的重排序策略】
# 1. 词项重叠：查询中有多少词出现在文档中
# 2. 二元组匹配：连续两个词的匹配（更精确的匹配）
# 3. 位置加权：查询词出现在文档开头的加分
# 4. 初始分数：保留第一阶段的分数
#
# 【生产环境】
# 在实际项目中，重排序通常用"交叉编码器"（Cross-Encoder）模型，
# 它会同时看查询和文档，给出更准确的相关性分数。

def rerank(query, candidates, chunks):
    """对候选结果进行重排序。

    参数:
        query (str): 查询文本
        candidates (list): 候选结果 [(doc_id, initial_score), ...]
        chunks (list): 所有文本块

    返回:
        list: 重排序后的 [(doc_id, rerank_score), ...]
    """
    # 去掉停用词（常见但无意义的词）
    query_words = set(query.lower().split())
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "what", "how",
                  "why", "when", "where", "do", "does", "for", "of", "in", "to",
                  "and", "or", "on", "at", "by", "it", "its", "this", "that",
                  "with", "from", "be", "has", "have", "had", "not", "but"}
    query_terms = query_words - stop_words

    scored = []
    for doc_id, initial_score in candidates:
        chunk = chunks[doc_id].lower()
        chunk_words = set(chunk.split())

        # 因子1：查询词与文档的重叠数量
        term_overlap = len(query_terms & chunk_words)

        # 因子2：二元组（bigram）匹配
        # 例如查询 "refund policy" → bigram = {"refund policy"}
        # 如果文档中包含 "refund policy" 这个连续词组 → 匹配
        query_bigrams = set()
        q_list = [w for w in query.lower().split() if w not in stop_words]
        for i in range(len(q_list) - 1):
            query_bigrams.add(q_list[i] + " " + q_list[i + 1])
        bigram_matches = sum(1 for bg in query_bigrams if bg in chunk)

        # 因子3：位置加权（查询词出现在文档开头的加分）
        position_boost = 0
        for term in query_terms:
            pos = chunk.find(term)
            if pos != -1 and pos < len(chunk) // 3:  # 在前1/3的位置
                position_boost += 0.5

        # 综合评分（加权求和）
        rerank_score = (
            term_overlap * 1.0      # 词项重叠
            + bigram_matches * 2.0  # 二元组匹配（权重更高）
            + position_boost        # 位置加权
            + initial_score * 5.0   # 初始分数（保留第一阶段的信号）
        )
        scored.append((doc_id, rerank_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# =============================================================================
# 第七部分：HyDE（Hypothetical Document Embeddings）
# =============================================================================
# 【什么是 HyDE？】
# 问题：用户问 "How much money did the company make?"
# 但文档中用的是 "revenue" 和 "earnings"，不是 "money"。
# 直接用查询去检索，可能匹配不上。
#
# HyDE 的解决方案：
# 1. 先让 LLM 生成一个"假设的回答"（包含文档中会出现的词汇）
# 2. 用这个假设回答去检索（而不是用原始查询）
# 3. 因为假设回答的用词更接近文档，检索效果更好
#
# 【为什么叫"假设文档嵌入"？】
# - Hypothetical：假设的（LLM 编造的）
# - Document：这里指假设的回答
# - Embeddings：向量化
# 所以 HyDE = 用假设回答的向量来检索

def hyde_generate_hypothesis(query):
    """生成假设的回答（模板版，实际项目中用 LLM 生成）。

    【本实现用模板模拟】
    实际项目中，这里会调用 LLM API 生成假设回答。
    模板版本只是演示 HyDE 的思路。

    参数:
        query (str): 用户查询

    返回:
        str: 假设的回答文本
    """
    templates = {
        "what": "The answer to '{query}' is as follows: Based on our documentation, {topic} involves specific policies and procedures that define the process and requirements.",
        "how": "To address '{query}': The process involves several steps. First, you need to initiate the request for {topic}. Then, the system processes it according to the defined rules and policies.",
        "default": "Regarding '{query}': Our records indicate specific details and policies related to {topic} that provide a comprehensive answer to this question."
    }
    query_lower = query.lower().strip()
    if query_lower.startswith("what"):
        template = templates["what"]
    elif query_lower.startswith("how"):
        template = templates["how"]
    else:
        template = templates["default"]

    # 提取查询中的关键词作为"主题"
    filler = {"what", "is", "the", "how", "do", "does", "a", "an", "for", "of",
              "to", "in", "on", "at", "by", "and", "or", "are", "was", "were", "?"}
    topic_words = [w.strip("?.,!") for w in query.lower().split() if w.strip("?.,!") not in filler]
    topic = " ".join(topic_words) if topic_words else "this topic"

    return template.format(query=query, topic=topic)


def hyde_search(query, vector_embeddings, vocab, idf, top_k=5):
    """用 HyDE 方法检索。

    【流程】
    1. 生成假设回答
    2. 将假设回答向量化
    3. 用假设回答的向量去检索

    返回:
        tuple: (检索结果, 假设回答文本)
    """
    hypothesis = hyde_generate_hypothesis(query)
    hypothesis_emb = tfidf_embed(hypothesis, vocab, idf)
    results = vector_search(hypothesis_emb, vector_embeddings, top_k)
    return results, hypothesis


# =============================================================================
# 第八部分：父子分块（Parent-Child Chunking）
# =============================================================================
# 【什么是父子分块？】
# 问题：
# - 大块（如200词）→ 上下文丰富，但检索不够精确
# - 小块（如50词）→ 检索精确，但上下文不够
#
# 解决方案：同时维护两种块！
# - 子块（child, 50词）：用于检索（精确匹配）
# - 父块（parent, 200词）：用于生成回答（提供上下文）
#
# 【工作流程】
# 1. 用户查询 → 在子块中检索 → 找到最相关的子块
# 2. 通过 child_to_parent 映射 → 找到对应的父块
# 3. 把父块交给 LLM 生成回答（上下文更完整）

def create_parent_child_chunks(text, parent_size=200, child_size=50):
    """创建父子分块。

    参数:
        text (str): 完整文本
        parent_size (int): 父块的单词数
        child_size (int): 子块的单词数

    返回:
        tuple: (父块列表, 子块列表, 子块到父块的映射字典)
    """
    words = text.split()
    parents = []
    children = []
    child_to_parent = {}  # 子块索引 → 父块索引

    parent_idx = 0
    start = 0
    while start < len(words):
        parent_end = min(start + parent_size, len(words))
        parent_text = " ".join(words[start:parent_end])
        parents.append(parent_text)

        # 在每个父块内部创建子块
        child_start = start
        while child_start < parent_end:
            child_end = min(child_start + child_size, parent_end)
            child_text = " ".join(words[child_start:child_end])
            child_idx = len(children)
            children.append(child_text)
            child_to_parent[child_idx] = parent_idx  # 记录映射关系
            child_start += child_size

        parent_idx += 1
        start += parent_size

    return parents, children, child_to_parent


# =============================================================================
# 第九部分：忠实度评估（Faithfulness Evaluation）
# =============================================================================
# 【什么是忠实度？】
# 检查 LLM 的回答是否"忠实"于检索到的文档。
# 如果回答中的内容在文档中找不到，就是"幻觉"（hallucination）。
#
# 【评估方法】
# 1. 把回答拆成句子
# 2. 对每个句子，检查其关键词是否出现在检索到的文档中
# 3. 如果超过50%的关键词在文档中能找到 → 句子"有依据"
# 4. 忠实度 = 有依据的句子数 / 总句子数
#
# 【忠实度 = 1.0】→ 所有内容都有文档支持（好！）
# 【忠实度 = 0.5】→ 一半的内容没有文档支持（可能有幻觉！）

def evaluate_faithfulness(answer, retrieved_chunks):
    """评估回答的忠实度。

    参数:
        answer (str): LLM 的回答
        retrieved_chunks (list): 检索到的文档块

    返回:
        tuple: (忠实度分数 0-1, 无依据的句子列表)
    """
    answer_sentences = [s.strip() for s in answer.split(".") if len(s.strip()) > 10]
    if not answer_sentences:
        return 1.0, []

    grounded = 0
    ungrounded = []
    context = " ".join(retrieved_chunks).lower()

    for sentence in answer_sentences:
        words = set(sentence.lower().split())
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "and", "or",
                      "to", "of", "in", "for", "on", "at", "by", "it", "this", "that"}
        content_words = words - stop_words
        if not content_words:
            grounded += 1
            continue

        # 检查内容词在上下文中的匹配比例
        matched = sum(1 for w in content_words if w in context)
        ratio = matched / len(content_words) if content_words else 0

        if ratio >= 0.5:
            grounded += 1  # 超过50%的词在上下文中找到 → 有依据
        else:
            ungrounded.append(sentence)  # 无依据的句子

    score = grounded / len(answer_sentences) if answer_sentences else 1.0
    return score, ungrounded


# =============================================================================
# 第十部分：RAG 提示词构建器
# =============================================================================
# 【build_rag_prompt 做了什么？】
# 把检索到的文档块和用户查询组装成一个完整的提示词。
# 关键指令："只根据以下上下文回答"——防止 LLM 用自身知识编造答案。

def build_rag_prompt(query, retrieved_chunks):
    """构建 RAG 提示词。

    参数:
        query (str): 用户查询
        retrieved_chunks (list): 检索到的文档块

    返回:
        str: 完整的提示词
    """
    context = "\n\n---\n\n".join(
        f"[Source {i+1}]\n{chunk}"
        for i, chunk in enumerate(retrieved_chunks)
    )
    return (
        "Answer the question based ONLY on the following context.\n"
        "If the context doesn't contain enough information, "
        "say \"I don't have enough information to answer that.\"\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query}\n\n"
        "Answer:"
    )


# =============================================================================
# 第十一部分：示例数据
# =============================================================================
# 【Acme Corp 公司文档】
# 模拟一家虚构公司的6份文档：退款政策、产品概览、安全实践、
# API 文档、财报、SLA 可靠性承诺。
# 这些文档覆盖不同主题，用于测试检索系统能否准确找到相关文档。

SAMPLE_DOCUMENTS = [
    """Acme Corp Refund Policy.
    All standard plan customers are eligible for a full refund within 30 days of purchase.
    Enterprise plan customers receive an extended 60-day refund window with pro-rated refunds
    calculated from the date of cancellation. Refunds are processed within 5-7 business days
    and returned to the original payment method. No refunds are available after the refund
    window closes. Customers must submit refund requests through the support portal or by
    contacting their account manager directly. Annual subscriptions that are cancelled mid-term
    will receive a pro-rated credit for the remaining months.""",

    """Acme Corp Product Overview.
    Acme Corp offers three product tiers: Starter, Professional, and Enterprise.
    The Starter plan includes basic features for individual users at $29 per month.
    The Professional plan adds team collaboration, advanced analytics, and priority
    support for $99 per month per user. The Enterprise plan includes everything in
    Professional plus custom integrations, dedicated account management, SSO,
    audit logs, and a 99.99% uptime SLA. Enterprise pricing is custom and starts
    at $500 per month for up to 50 users. All plans include a 14-day free trial
    with no credit card required.""",

    """Acme Corp Security Practices.
    Acme Corp maintains SOC 2 Type II compliance and undergoes annual third-party
    security audits. All data is encrypted at rest using AES-256 and in transit
    using TLS 1.3. Customer data is stored in isolated tenants within AWS
    us-east-1 and eu-west-1 regions. Data residency can be configured per
    organization for Enterprise customers. Backups are performed every 6 hours
    with 30-day retention. Acme Corp does not sell or share customer data with
    third parties. Enterprise customers can request data deletion within 24 hours.
    Bug bounty program available through HackerOne.""",

    """Acme Corp API Documentation.
    The Acme API uses REST with JSON request and response bodies. Authentication
    is via Bearer tokens issued through OAuth 2.0. Rate limits are 100 requests
    per minute for Starter, 1000 for Professional, and 10000 for Enterprise.
    Rate limit headers are included in every response: X-RateLimit-Limit,
    X-RateLimit-Remaining, and X-RateLimit-Reset. Exceeding the rate limit
    returns HTTP 429 with a Retry-After header. The API supports pagination
    via cursor-based pagination using the next_cursor field. Webhooks are
    available for real-time event notifications on Professional and Enterprise
    plans. API versioning uses date-based versions in the URL path.""",

    """Acme Corp Q3 2025 Earnings Report.
    Total revenue for Q3 2025 was $47.2 million, up 23% year-over-year.
    Enterprise segment contributed $31.8 million, representing 67% of total
    revenue. Professional segment added $12.1 million. Starter segment
    contributed $3.3 million. Customer count grew to 14,200 from 11,800
    in Q3 2024. Net retention rate was 118%. Operating expenses were
    $38.4 million. EBITDA was $8.8 million with an 18.6% margin.
    Free cash flow was $6.2 million. Guidance for Q4 2025 is $51-53 million
    in revenue with continued margin expansion.""",

    """Acme Corp Uptime and Reliability.
    Acme Corp guarantees 99.9% uptime for Professional plans and 99.99% uptime
    for Enterprise plans. Uptime is calculated monthly excluding scheduled
    maintenance windows which are announced 72 hours in advance. If uptime
    falls below the guaranteed level, customers receive service credits:
    10% credit for each 0.1% below the SLA threshold, up to a maximum of
    30% of the monthly fee. Service credits must be requested within 30 days
    of the incident. Status page updates are posted at status.acme.com
    within 5 minutes of any detected incident. Post-incident reports are
    published within 48 hours for any outage exceeding 15 minutes."""
]


# =============================================================================
# 主程序入口：8步演示
# =============================================================================
# 【演示流程】
# Step 1: BM25 关键词检索
# Step 2: 向量检索 vs BM25 对比
# Step 3: 混合检索（RRF 融合）
# Step 4: 重排序
# Step 5: HyDE（假设文档嵌入）
# Step 6: 父子分块
# Step 7: 忠实度评估
# Step 8: 全面对比（Vector vs BM25 vs Hybrid vs Rerank）

if __name__ == "__main__":
    # --- 准备数据：将文档分块 ---
    all_chunks = []
    chunk_sources = []  # 记录每个块来自哪个文档
    source_names = ["refund", "product", "security", "api", "earnings", "uptime"]
    for i, doc in enumerate(SAMPLE_DOCUMENTS):
        doc_chunks = chunk_text(doc, chunk_size=50, overlap=10)
        for c in doc_chunks:
            all_chunks.append(c)
            chunk_sources.append(source_names[i])

    # =========================================================
    # Step 1: BM25 关键词检索
    # =========================================================
    print("=" * 65)
    print("STEP 1: BM25 Keyword Search")
    print("=" * 65)

    bm25 = BM25()
    bm25.index(all_chunks)

    test_query = "What was revenue last quarter?"
    bm25_results = bm25.search(test_query, top_k=5)
    print(f"  Query: {test_query}")
    print(f"  BM25 top-5:")
    for rank, (idx, score) in enumerate(bm25_results):
        preview = all_chunks[idx][:70].replace("\n", " ")
        print(f"    #{rank+1} [{chunk_sources[idx]}] score={score:.4f} | {preview}...")

    # =========================================================
    # Step 2: 向量检索 vs BM25 对比
    # =========================================================
    print("\n" + "=" * 65)
    print("STEP 2: Vector Search vs BM25")
    print("=" * 65)

    # 构建 TF-IDF 向量
    vocab = build_vocabulary(all_chunks)
    idf = compute_idf(all_chunks, vocab)
    embeddings = [tfidf_embed(c, vocab, idf) for c in all_chunks]

    queries = [
        "What is the refund policy for enterprise customers?",
        "What was revenue last quarter?",
        "How is data encrypted?",
        "What are the API rate limits for enterprise?",
        "What happens if uptime falls below SLA?"
    ]

    for query in queries:
        query_emb = tfidf_embed(query, vocab, idf)
        vec_top1 = vector_search(query_emb, embeddings, top_k=1)[0]
        bm25_top1 = bm25.search(query, top_k=1)[0]

        print(f"\n  Query: {query}")
        print(f"    Vector #1: [{chunk_sources[vec_top1[0]]}] score={vec_top1[1]:.4f}")
        print(f"    BM25   #1: [{chunk_sources[bm25_top1[0]]}] score={bm25_top1[1]:.4f}")
        agree = "AGREE" if chunk_sources[vec_top1[0]] == chunk_sources[bm25_top1[0]] else "DISAGREE"
        print(f"    {agree}")

    # =========================================================
    # Step 3: 混合检索（RRF 融合）
    # =========================================================
    print("\n" + "=" * 65)
    print("STEP 3: Reciprocal Rank Fusion (Hybrid Search)")
    print("=" * 65)

    query = "What was revenue last quarter?"
    print(f"  Query: {query}")

    query_emb = tfidf_embed(query, vocab, idf)
    vec_results = vector_search(query_emb, embeddings, top_k=10)
    bm25_results = bm25.search(query, top_k=10)

    print(f"\n  Vector top-3:")
    for rank, (idx, score) in enumerate(vec_results[:3]):
        print(f"    #{rank+1} [{chunk_sources[idx]}] {score:.4f}")

    print(f"\n  BM25 top-3:")
    for rank, (idx, score) in enumerate(bm25_results[:3]):
        print(f"    #{rank+1} [{chunk_sources[idx]}] {score:.4f}")

    # 用 RRF 融合两个列表
    fused = reciprocal_rank_fusion([vec_results, bm25_results])
    print(f"\n  RRF fused top-5:")
    for rank, (idx, score) in enumerate(fused[:5]):
        preview = all_chunks[idx][:60].replace("\n", " ")
        print(f"    #{rank+1} [{chunk_sources[idx]}] rrf={score:.4f} | {preview}...")

    # =========================================================
    # Step 4: 重排序
    # =========================================================
    print("\n" + "=" * 65)
    print("STEP 4: Reranking")
    print("=" * 65)

    query = "enterprise refund policy"
    print(f"  Query: {query}")

    # 先混合检索，再重排序
    hybrid_results = hybrid_search(query, all_chunks, embeddings, vocab, idf, bm25, top_k=10)
    reranked = rerank(query, hybrid_results, all_chunks)

    print(f"\n  Before reranking (top-5):")
    for rank, (idx, score) in enumerate(hybrid_results[:5]):
        preview = all_chunks[idx][:60].replace("\n", " ")
        print(f"    #{rank+1} [{chunk_sources[idx]}] score={score:.4f} | {preview}...")

    print(f"\n  After reranking (top-5):")
    for rank, (idx, score) in enumerate(reranked[:5]):
        preview = all_chunks[idx][:60].replace("\n", " ")
        print(f"    #{rank+1} [{chunk_sources[idx]}] score={score:.4f} | {preview}...")

    # =========================================================
    # Step 5: HyDE（假设文档嵌入）
    # =========================================================
    print("\n" + "=" * 65)
    print("STEP 5: HyDE (Hypothetical Document Embeddings)")
    print("=" * 65)

    query = "How much money did the company make?"
    print(f"  Query: {query}")
    print(f"  (Note: query uses 'money', docs use 'revenue' and 'earnings')")

    # 直接检索 vs HyDE 检索
    query_emb = tfidf_embed(query, vocab, idf)
    direct_results = vector_search(query_emb, embeddings, top_k=3)
    hyde_results, hypothesis = hyde_search(query, embeddings, vocab, idf, top_k=3)

    print(f"\n  Hypothesis: {hypothesis[:100]}...")

    print(f"\n  Direct search top-3:")
    for rank, (idx, score) in enumerate(direct_results):
        print(f"    #{rank+1} [{chunk_sources[idx]}] {score:.4f}")

    print(f"\n  HyDE search top-3:")
    for rank, (idx, score) in enumerate(hyde_results):
        print(f"    #{rank+1} [{chunk_sources[idx]}] {score:.4f}")

    # =========================================================
    # Step 6: 父子分块
    # =========================================================
    print("\n" + "=" * 65)
    print("STEP 6: Parent-Child Chunking")
    print("=" * 65)

    full_text = " ".join(SAMPLE_DOCUMENTS)
    parents, children, child_to_parent = create_parent_child_chunks(
        full_text, parent_size=100, child_size=25
    )

    print(f"  Total words: {len(full_text.split())}")
    print(f"  Parent chunks: {len(parents)} (100 words each)")
    print(f"  Child chunks: {len(children)} (25 words each)")
    print(f"  Ratio: {len(children)/len(parents):.1f} children per parent")

    # 用子块检索，然后找到对应的父块
    child_vocab = build_vocabulary(children)
    child_idf = compute_idf(children, child_vocab)
    child_embeddings = [tfidf_embed(c, child_vocab, child_idf) for c in children]

    query = "enterprise refund 60 days"
    query_emb = tfidf_embed(query, child_vocab, child_idf)
    child_results = vector_search(query_emb, child_embeddings, top_k=3)

    print(f"\n  Query: {query}")
    print(f"\n  Matched children:")
    for rank, (idx, score) in enumerate(child_results):
        parent_idx = child_to_parent[idx]
        print(f"    Child #{idx} (score={score:.4f}):")
        print(f"      Child text: {children[idx][:80]}...")
        print(f"      Parent #{parent_idx}: {parents[parent_idx][:80]}...")

    # =========================================================
    # Step 7: 忠实度评估
    # =========================================================
    print("\n" + "=" * 65)
    print("STEP 7: Faithfulness Evaluation")
    print("=" * 65)

    # 好的回答（所有内容都有文档支持）
    good_answer = (
        "Enterprise customers receive a 60-day refund window. "
        "Refunds are pro-rated from the date of cancellation. "
        "Processing takes 5-7 business days."
    )
    # 坏的回答（包含幻觉：90天、即时处理、$50手续费——文档中都没提到）
    bad_answer = (
        "Enterprise customers receive a 90-day refund window. "
        "Refunds are processed instantly. "
        "There is a $50 processing fee."
    )
    context_chunks = [all_chunks[i] for i, _ in hybrid_search(
        "enterprise refund", all_chunks, embeddings, vocab, idf, bm25, top_k=3
    )]

    good_score, good_ungrounded = evaluate_faithfulness(good_answer, context_chunks)
    bad_score, bad_ungrounded = evaluate_faithfulness(bad_answer, context_chunks)

    print(f"  Context: {len(context_chunks)} chunks about refund policy")
    print(f"\n  Good answer: \"{good_answer[:80]}...\"")
    print(f"  Faithfulness: {good_score:.2f}")
    if good_ungrounded:
        print(f"  Ungrounded claims: {good_ungrounded}")
    else:
        print(f"  All claims grounded in context.")

    print(f"\n  Bad answer: \"{bad_answer[:80]}...\"")
    print(f"  Faithfulness: {bad_score:.2f}")
    if bad_ungrounded:
        print(f"  Ungrounded claims:")
        for claim in bad_ungrounded:
            print(f"    - \"{claim}\"")

    # =========================================================
    # Step 8: 全面对比
    # =========================================================
    print("\n" + "=" * 65)
    print("STEP 8: Full Advanced RAG Pipeline Comparison")
    print("=" * 65)

    comparison_queries = [
        ("What is the refund policy for enterprise?", "refund"),
        ("What was Q3 revenue?", "earnings"),
        ("How is customer data encrypted?", "security"),
        ("What are the API rate limits?", "api"),
        ("What is the uptime guarantee?", "uptime"),
    ]

    print(f"  {'Query':<45s} {'Vector':>8s} {'BM25':>8s} {'Hybrid':>8s} {'Rerank':>8s}")
    print("  " + "-" * 77)

    for query, expected_source in comparison_queries:
        query_emb = tfidf_embed(query, vocab, idf)

        vec_top = vector_search(query_emb, embeddings, top_k=1)[0]
        vec_hit = "HIT" if chunk_sources[vec_top[0]] == expected_source else "miss"

        bm25_top = bm25.search(query, top_k=1)[0]
        bm25_hit = "HIT" if chunk_sources[bm25_top[0]] == expected_source else "miss"

        hybrid_top = hybrid_search(query, all_chunks, embeddings, vocab, idf, bm25, top_k=1)[0]
        hybrid_hit = "HIT" if chunk_sources[hybrid_top[0]] == expected_source else "miss"

        hybrid_pool = hybrid_search(query, all_chunks, embeddings, vocab, idf, bm25, top_k=10)
        reranked_top = rerank(query, hybrid_pool, all_chunks)[0]
        rerank_hit = "HIT" if chunk_sources[reranked_top[0]] == expected_source else "miss"

        print(f"  {query:<45s} {vec_hit:>8s} {bm25_hit:>8s} {hybrid_hit:>8s} {rerank_hit:>8s}")

    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    print("  Advanced RAG techniques:")
    print("    1. BM25 keyword search catches exact term matches")
    print("    2. Hybrid search (vector + BM25 + RRF) combines both signals")
    print("    3. Reranking scores candidates more carefully with cross-attention")
    print("    4. HyDE bridges the query-document vocabulary gap")
    print("    5. Parent-child chunking: precise search, rich context")
    print("    6. Faithfulness evaluation catches hallucinated claims")
    print("\n  In production:")
    print("    - Replace TF-IDF with neural embeddings")
    print("    - Replace the simple reranker with a cross-encoder model")
    print("    - Replace HyDE templates with actual LLM hypothesis generation")
    print("    - Add metadata filtering before search")
    print("    - Evaluate with Recall@k and faithfulness on a test set")