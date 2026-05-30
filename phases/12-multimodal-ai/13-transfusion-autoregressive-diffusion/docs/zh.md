# Transfusion：一个 Transformer 中的自回归文本 + 扩散图像

> Chameleon 和 Emu3 把一切都押在离散 token 上。它们有效，但量化瓶颈显而易见——图像质量在连续空间扩散模型之下就封顶了。Transfusion（Meta，Zhou 等人，2024 年 8 月）做了相反的赌注：保持图像连续，完全去掉 VQ-VAE，用两个损失训练一个 Transformer。文本 token 使用下一个 token 预测。图像 patch 使用流匹配/扩散损失。两个目标优化相同的权重。Stable Diffusion 3（MMDiT）的底层架构是近亲。本课解读 Transfusion 论点，构建一个玩具双损失训练器，并追踪让一个 Transformer 同时做两项工作的注意力掩码。

**类型：** Build
**语言：** Python（标准库，MNIST 规模玩具上的双损失训练器）
**前置课程：** Phase 12 · 11（Chameleon）、Phase 8（Generative AI）
**时间：** ~180 分钟

## 学习目标

- 接入一个在单一骨干网络上运行两个损失（文本 token 的 NTP，图像 patch 的扩散 MSE）的 Transformer。
- 解释为什么图像 patch 上的双向注意力加上文本 token 上的因果注意力是正确的掩码选择。
- 对比 Transfusion 风格（连续图像，扩散损失）与 Chameleon 风格（离散图像，NTP）在计算、质量和代码复杂度上的差异。
- 说出 MMDiT 的贡献：每个块中模态特定的权重，在残差流中的联合注意力。

## 问题

离散 vs 连续图像 token 的争论比 LLM 更古老。连续表示（原始像素、VAE 潜在向量）保留细节。离散 token（VQ 索引）适配 Transformer 的原生词汇表但在量化步骤丢失细节。

Chameleon / Emu3 走离散路线：一个损失，一个架构，但图像保真度受 tokenizer 质量限制。

扩散模型走连续路线：卓越的图像质量，但与 LLM 是独立的模型，复杂的噪声调度工程，与文本生成没有干净的整合。

Transfusion 提问：我们能两者兼得吗？保持图像连续，仍然训练一个模型，用两个损失缝合到一个梯度步骤中。

## 概念

### 双损失架构

单一的仅解码器 Transformer 处理一个包含以下内容的序列：

- 文本 token（离散的，来自 BPE 词汇表）。
- 图像 patch（连续的，16×16 像素块通过线性嵌入投影到隐藏维度——与 ViT 编码器的输入相同）。
- `<image>` 和 `</image>` 标签标记连续 patch 的位置。

前向传播运行一次。损失为每个 token 选择两个头之一：

- 文本 token：词汇 logits 头上的标准交叉熵。
- 图像 patch：连续 patch 上的扩散损失——预测添加到每个 patch 上的噪声。

梯度流经共享的 Transformer 主体。两个损失同时改善共享权重。

### 注意力掩码：因果文本 + 双向图像

文本 token 必须是因果的——你不能让文本 token 关注未来的文本，否则教师强制会破坏。然而图像 patch 代表一个快照；它们应该在同一图像块内双向关注彼此。

掩码：

```
M[i, j] = 1 当：
  (i 是文本且 j 是文本且 j <= i)   # 文本因果
  或 (i 是图像且 j 是图像且 same_image_block(i, j))   # 图像内双向
  或 (i 是文本且 j 是图像且 j < i_image_end)   # 文本关注前面的图像
  或 (i 是图像且 j 是文本且 j < i_image_start)   # 图像关注前面的文本
```

在训练和推理时实现为块三角掩码。

### Transformer 内的扩散损失

扩散损失是标准的：向图像 patch 添加噪声，要求模型预测噪声（或等价地预测干净 patch）。Transfusion 的版本使用流匹配——预测从噪声到干净的速度场。

训练期间：
1. 对每个图像 patch x0，采样随机时间步 t。
2. 采样噪声 ε，计算 xt = (1-t) * x0 + t * ε（流匹配的线性插值）。
3. Transformer 预测 v_theta(xt, t)；损失 = MSE(v_theta(xt, t), ε - x0)。
4. 与同一序列的文本 NTP 损失一起反向传播。

推理时，生成是：
- 文本 token：标准自回归采样。
- 图像 patch：扩散采样循环（典型 10-30 步），以前面的文本 token 为条件。

### MMDiT：Stable Diffusion 3 的变体

Stable Diffusion 3（Esser 等人，2024 年 3 月）大约与 Transfusion 同时发布了 MMDiT（多模态扩散 Transformer）。两者的架构是兄弟。

MMDiT 的关键差异：

- 每块模态特定权重。每个 Transformer 块对文本 token vs 图像 patch 有独立的 Q、K、V 和 MLP 权重。注意力是联合的（跨模态）；其余都是模态特定的。
- 整流流训练。一种特定的流匹配变体，具有已知采样和比 DDPM 更简单的数学。
- 规模。MMDiT 是 SD3（20 亿和 80 亿参数变体）的骨干网络。Transfusion 的论文扩展到 70 亿。

两者都收敛到同一个核心思想：一个 Transformer 在文本上运行 NTP，在连续图像表示上运行扩散。

### 为什么这优于 Chameleon 风格

连续扩散和离散 NTP 在图像生成上的质量差距是可测量的。Transfusion 论文报告：

- 70 亿参数下，在 FID 上比同等大小的 Chameleon 风格模型高 3-5 分。
- 无需 tokenizer 训练——图像编码器更简单（到隐藏维度的线性投影，与 ViT 的输入层相同）。
- 推理可以并行化图像 patch 去噪，不像自回归图像 token。

缺点：Transfusion 是双损失模型，训练动态更复杂。损失权重需要调优。NTP 和扩散之间的调度不匹配可能导致一个头占主导。

### 下游发展

Janus-Pro（课程 12.15）通过为理解和生成解耦视觉编码器来改进 Transfusion 的想法——SigLIP 用于一个，VQ 用于另一个——同时共享 Transformer 主体。Show-o（课程 12.14）将扩散换成离散扩散（掩码预测）。统一生成家族在 Transfusion 之后快速分支。

2026 年能发射图像的生产 VLM——Gemini 3 Pro、GPT-5、Claude Opus 4.7 的图像生成路径——几乎肯定使用这个家族的某种后继。细节是专有的。

## 使用它

`code/main.py` 在微型类 MNIST 问题上构建了一个玩具 Transfusion：

- 文本描述是描述数字（0-9）的短整数序列。
- 图像是 4×4 的字节网格。
- 一对共享权重的线性投影充当 Transformer 替代品；文本上的 NTP 损失，噪声 patch 上的 MSE 损失。
- 训练循环交替两个损失，注意力掩码是显式的。
- 生成在一次前向传播中产生文本描述和 4×4 图像。

Transformer 是玩具级的。双损失管道、注意力掩码构建和推理循环才是真正的产出。

## 产出

本课生成 `outputs/skill-two-loss-trainer-designer.md`。给定新的多模态训练任务（文本 + 图像、文本 + 音频、文本 + 视频），它设计双损失调度（损失权重、掩码形状、共享 vs 模态特定块）并标记实现风险。

## 练习

1. Transfusion 风格模型训练 70% 文本 token 和 30% 图像 patch。图像扩散损失的幅度约为文本 NTP 损失的 10 倍。什么损失权重能平衡它们？

2. 为序列 `[T, T, <image>, P, P, P, P, </image>, T]` 实现块三角掩码。标记每个条目为 0 或 1。

3. MMDiT 有模态特定的 QKV 权重。与 Transfusion 的全共享 Transformer 相比，这增加了多少参数量开销？在 70 亿参数下，值得吗？

4. 生成：给定文本提示，模型运行 NTP 50 个 token，然后遇到 `<image>`，然后在 256 个 patch 上运行 20 步去噪的扩散。总共有多少次前向传播？

5. 阅读 SD3 论文第 3 节。描述整流流以及为什么它比 DDPM 在更少的推理步数中收敛。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Two-loss training（双损失训练） | "NTP + 扩散" | 单一 Transformer 在同一梯度步骤中优化文本 token 的交叉熵和连续图像 patch 的 MSE |
| Flow matching（流匹配） | "整流流" | 预测从噪声到干净数据的速度场的扩散变体；比 DDPM 数学更简单 |
| MMDiT | "多模态 DiT" | Stable Diffusion 3 的架构：联合注意力，模态特定的 MLP 和归一化 |
| Block-triangular mask（块三角掩码） | "因果文本 + 双向图像" | 跨文本因果但在图像区域内双向的注意力掩码 |
| Continuous image representation（连续图像表示） | "无 VQ" | 图像 patch 作为实值向量，而非整数码本索引 |
| Velocity prediction（速度预测） | "v 参数化" | 网络输出是噪声和数据之间的速度场，而非噪声本身 |

## 延伸阅读

- [Zhou 等人 — Transfusion (arXiv:2408.11039)](https://arxiv.org/abs/2408.11039)
- [Esser 等人 — Stable Diffusion 3 / MMDiT (arXiv:2403.03206)](https://arxiv.org/abs/2403.03206)
- [Peebles & Xie — DiT (arXiv:2212.09748)](https://arxiv.org/abs/2212.09748)
- [Zhao 等人 — MonoFormer (arXiv:2409.16280)](https://arxiv.org/abs/2409.16280)
- [Xie 等人 — Show-o (arXiv:2408.12528)](https://arxiv.org/abs/2408.12528)