# Chameleon 与早期融合纯 Token 多模态模型

> 我们目前看到的每个 VLM 都将图像和文本分开处理。视觉 token 来自视觉编码器，流经投影器，然后在 LLM 内部与文本会合。视觉和文本词汇表永不重叠。Chameleon（Meta，2024 年 5 月）提出：如果它们重叠会怎样？训练一个 VQ-VAE 将图像转换为来自共享词汇表的离散 token 序列。每个多模态文档现在就是一个序列——文本 token 和图像 token 交错，单一自回归损失。副作用：模型可以生成混合模态输出——在单次推理调用中交替输出文本和图像 token。本课解读早期融合论点并端到端构建玩具版本。

**类型：** Build
**语言：** Python（标准库，VQ-VAE tokenizer + 交错解码器）
**前置课程：** Phase 12 · 05、Phase 8（Generative AI）
**时间：** ~180 分钟

## 学习目标

- 解释为什么共享词汇表 + 单一损失改变了模型能做什么。
- 描述 VQ-VAE 如何将图像转换为与 Transformer 的下一个 token 目标兼容的离散序列。
- 说出 Chameleon 的训练稳定性技巧：QK-Norm、dropout 位置、LayerNorm 顺序。
- 对比 Chameleon 与 BLIP-2 的 Q-Former 方法，描述各自的适用场景。

## 问题

基于适配器的 VLM（LLaVA、BLIP-2、Qwen-VL）将文本和图像视为两种不同的东西。文本 token 经过 `embed(text_token)`；图像经过 `visual_encoder(image) → projector → ... pseudo_tokens`。模型有两条在中途合并的输入路径。

三个后果：

1. LLM 只能消费图像，不能发射图像。输出仅限文本。
2. 混合模态文档（交替的段落和图像，如文章）很笨拙——你要么在模型外部解析多模态输入，要么链式生成。
3. 分布不匹配。视觉 token 和文本 token 位于隐藏空间的不同区域，造成微妙的对齐问题。

Chameleon 拒绝了这个前提：图像只是来自共享词汇表的离散 token 序列。在交错文档上训练模型，一个损失，一个自回归解码器，你就免费解锁了混合模态生成。

## 概念

### VQ-VAE 作为图像 tokenizer

tokenizer 是一个向量量化变分自编码器。架构：

- **编码器**：CNN + ViT 将图像映射到空间特征图，比如 32×32 个维度 256 的特征。
- **码本（Codebook）**：K 个向量的学习词汇表（Chameleon 使用 8192），维度也是 256。
- **量化**：对每个空间特征，按 L2 距离查找最近的码本条目。用整数索引替换连续特征。
- **解码器**：CNN 将量化特征恢复为像素。

训练：VAE 重建损失 + 承诺损失 + 码本损失。码本索引形成图像的离散字母表。

对于 Chameleon：一张图像变成 32×32 = 1024 个从 8192 词汇表中抽取的 token。与文本 token（来自 LLM 的 BPE 词汇表，比如 32000）拼接。最终词汇表：40192。Transformer 看到一个序列，一个损失。

### 共享词汇表

Chameleon 的词汇表组合了文本 token、图像 token 和模态分隔符。每个 token 有一个单一 ID。输入嵌入层将每个 ID 映射到 D 维隐藏向量。输出投影将隐藏映射回词汇 logits。Softmax 选择下一个 token，无论什么模态。

分隔符很重要：`<image>` 和 `</image>` 标签包围图像 token 序列。生成时，如果模型发出 `<image>`，下游软件知道接下来的 1024 个 token 是 VQ 索引，要发送给解码器进行像素渲染。

### 混合模态生成

推理是在共享词汇表中的下一个 token 预测。示例提示："画一只猫并描述它。"Chameleon 发出：

```
<image> 4821 1029 2891 ... (1024 个图像 token) </image>
The cat is orange, sitting on a windowsill...
```

模型自主选择顺序——可能先图像后文本，先文本后图像，或交错。同一个解码器，同一个损失。

对比适配器 VLM 只能生成文本。Chameleon 重新开启了模型输出模态的问题。

### 训练稳定性——QK-Norm、dropout、LayerNorm 顺序

早期融合训练在规模上不稳定。Chameleon 论文记录了三个技巧：

- **QK-Norm**。在注意力内部对 query 和 key 投影应用 LayerNorm，在点积之前。防止深度处的 logit 幅度爆炸。多个 2024 年后的大型模型使用。
- **Dropout 位置**。在每个残差加法后都使用 dropout，而非仅在注意力和 MLP 之后。当图像 token 的梯度可能占主导时需要更多正则化。
- **LayerNorm 顺序**。残差分支上使用 Pre-LN（标准），加上最后一个块的跳跃连接上的额外 LN。稳定最后一层的梯度流。

没有这些技巧，340 亿参数的 Chameleon 训练在多个 checkpoint 处发散。有了它们，训练收敛。训练方案与架构同等重要。

### tokenizer 的重建天花板

VQ-VAE 是有损的。在 8192 个码本条目和每张 512×512 图像 1024 个 token 下，重建 PSNR 封顶在约 26-28 dB。这足以生成可识别的图像，但明显差于连续空间扩散（Stable Diffusion 3 达到 32+ dB）。

tokenizer 是瓶颈。更好的 tokenizer（MAGVIT-v2、IBQ、SBER-MoVQGAN）提升了天花板。Emu3（课程 12.12）仅通过更好的 tokenizer 就实现了 SDXL 质量的生成。

### Chameleon vs BLIP-2 / LLaVA

Chameleon（早期融合，共享词汇表）：
- 一个损失，一个解码器。
- 生成混合模态输出。
- tokenizer 是质量天花板。
- 昂贵：推理路径上每张生成图像需要 VQ-VAE 解码器。

BLIP-2 / LLaVA（晚期融合，独立塔）：
- 视觉输入，仅文本输出。
- 复用预训练 LLM。
- 理解任务无 tokenizer 瓶颈。
- 便宜：单次前向传播。

按任务选择。需要图像生成选 Chameleon 系列。只需要理解，适配器 VLM 更简单且复用更多预训练计算。

### Fuyu 和 AnyGPT

Fuyu（Adept，2023）是相关方法：完全跳过独立的视觉编码器，将原始图像 patch 作为 token 通过 LLM 的输入投影送入，无 tokenizer。比 Chameleon 简单，但失去了共享词汇表的输出生成能力。

AnyGPT（Zhan 等人，2024）将 Chameleon 扩展到四种模态：文本、图像、语音、音乐。对每种模态使用相同的 VQ-VAE 技巧，共享 Transformer。任意到任意生成。课程 12.16 更深入介绍。

## 使用它

`code/main.py` 构建了一个玩具级端到端早期融合模型：

- 一个将 8×8 patch 映射到码本索引（K=16）的微型 VQ-VAE 风格量化器。
- 一个共享词汇表：(文本 id 0..31) + (图像 id 32..47) + (分隔符 48, 49)。
- 一个在合成描述 + 图像 token 序列上训练的玩具自回归解码器（二元组表）。
- 给定提示发出交替文本 + 图像 token 的采样循环。

代码故意将 Transformer 保持极小（二元组），让你可以端到端追踪信号流。

## 产出

本课生成 `outputs/skill-tokenizer-vs-adapter-picker.md`。给定产品规格（仅理解 vs 理解 + 生成、所需图像质量、成本预算），它在 Chameleon 系列（早期融合）和 LLaVA 系列（晚期融合）之间做出选择，并用量化的经验法则提供依据。

## 练习

1. Chameleon 使用 K=8192 个码本条目和每张 512×512 图像 1024 个 token。估算与 24 位 RGB 图像相比的压缩比。是有损的吗？损失多大？

2. 一张 4K 图像（3840×2160）在相同 VQ-VAE 密度下产生多少个图像 token？Chameleon 风格模型能在一次推理调用中生成 4K 图像吗？什么先崩溃——上下文、tokenizer 质量还是 KV 缓存？

3. 用纯 Python 实现 QK-Norm。给定 64 维的 query 和 key，展示 LayerNorm 前后的点积。为什么幅度控制在深度处很重要？

4. 阅读 Chameleon 第 2.3 节关于训练稳定性。描述论文在没有 QK-Norm 的 34B 模型上观察到的确切失败模式。"范数爆炸"的特征是什么？

5. 扩展玩具解码器以在给定纯文本提示时发出混合模态响应。测量模型在训练数据分布 60% 文本优先 / 40% 图像优先下，选择图像优先 vs 文本优先的频率。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Early fusion（早期融合） | "统一 token" | 图像从第一步就转换为与 Transformer 共享词汇表的离散 token |
| VQ-VAE | "图像 tokenizer" | CNN + ViT + 码本，将图像映射为 Transformer 可预测的整数索引 |
| Shared vocabulary（共享词汇表） | "一个字典" | 覆盖文本 + 图像 + 模态分隔符的单一 token ID 空间 |
| QK-Norm | "注意力稳定器" | 在 query 和 key 点积前应用 LayerNorm，防止范数爆炸 |
| Mixed-modality generation（混合模态生成） | "文本 + 图像输出" | 在一次推理中自主产生交错文本和图像 token |
| Codebook size（码本大小） | "K 个条目" | VQ-VAE 可量化到的离散向量数量；在压缩和保真度之间权衡 |
| Tokenizer ceiling（tokenizer 天花板） | "重建极限" | 解码 VQ token 可达到的最佳 PSNR；限制模型的图像质量 |

## 延伸阅读

- [Chameleon Team — Chameleon: Mixed-Modal Early-Fusion Foundation Models (arXiv:2405.09818)](https://arxiv.org/abs/2405.09818)
- [Aghajanyan 等人 — CM3 (arXiv:2201.07520)](https://arxiv.org/abs/2201.07520)
- [Yu 等人 — CM3Leon (arXiv:2309.02591)](https://arxiv.org/abs/2309.02591)
- [Zhan 等人 — AnyGPT (arXiv:2402.12226)](https://arxiv.org/abs/2402.12226)
- [Adept — Fuyu-8B blog (adept.ai)](https://www.adept.ai/blog/fuyu-8b)