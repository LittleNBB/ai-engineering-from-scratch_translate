# Emu3：用下一个 Token 预测进行图像和视频生成

> BAAI 的 Emu3（Wang 等人，2024 年 9 月）是 2024 年本应终结扩散 vs 自回归之争的成果。单一 Llama 风格的仅解码器 Transformer，仅在下一个 token 预测目标上训练，覆盖文本 + VQ 图像 token + 3D VQ 视频 token 的统一词汇表，在图像生成上击败 SDXL，在感知上击败 LLaVA-1.6。没有 CLIP 损失。没有扩散调度。推理时使用无分类器引导（CFG）提升质量，但核心训练目标是带教师强制的下一个 token 预测。发表在 Nature 上。本课解读 Emu3 的论点——为什么更好的 tokenizer 加上规模就是你所需要的一切——并与扩散方法进行对比。

**类型：** Learn
**语言：** Python（标准库，3D 视频 tokenizer 数学 + 自回归采样器骨架）
**前置课程：** Phase 12 · 11（Chameleon）
**时间：** ~120 分钟

## 学习目标

- 解释为什么 Emu3 的单一损失下一个 token 目标有效，尽管长期以来假设图像质量需要扩散。
- 描述 3D 视频 tokenizer：时空 VQ 码本是什么样的，为什么 patch 跨越时间。
- 对比 Emu3 vs Stable Diffusion XL 在（训练计算、推理成本、质量天花板）上的差异。
- 说出同一个 Emu3 模型扮演的三个角色：Emu3-Gen（图像生成）、Emu3-Chat（感知）、Emu3-Stage2（视频生成）。

## 问题

2024 年之前的传统认知：图像生成需要扩散。论点：离散图像 token 损失太多信息无法重建细节，自回归采样在数千个 token 上累积误差。Stable Diffusion、DALL-E 3、Imagen、Midjourney 都使用某种形式的扩散。Chameleon（课程 12.11）在小规模上部分反驳了这一点，但在质量上未匹配 SDXL。

Emu3 正面攻击了这个论点。声明：更好的视觉 tokenizer + 足够的规模 + 下一个 token 损失 = 在同一个模型中实现击败扩散的图像生成，同时也能做感知。

发表时这个赌注颇具争议。两年后，开源统一生成家族（Emu3、Show-o、Janus-Pro、Transfusion）是研究的默认路径；生产前沿模型似乎使用某种变体。

## 概念

### Emu3 tokenizer

关键成分是视觉 tokenizer。Emu3 训练了一个自定义的 IBQ 类 tokenizer（逆瓶颈量化器，SBER-MoVQGAN 系列），每 token 8×8 分辨率缩减。512×512 的图像变成 64×64 = 4096 个 token，码本大小 32768。

这比 Chameleon 的每张 512×512 图像 1024 个 token（K=8192）更大，但每个 token 更便宜（更小的码本查找、更简单的编解码器）。关键指标：重建 PSNR 30.5 dB，与 Stable Diffusion 连续潜在空间的 32 dB 相当。

对于视频：3D VQ tokenizer 将时空 patch（4×4×4 像素）编码为一个整数。8 FPS 的 4 秒片段有 32 帧；256×256 分辨率下，4× 空间缩减和 4× 时间缩减，token 数为 (256/4) × (256/4) × (32/4) = 64 × 64 × 8 = 32,768 个 token。

tokenizer 质量是天花板。Emu3 的贡献部分在于"我们训练了一个非常好的 tokenizer"。

### 单一损失训练

Emu3 使用一个目标：在文本 token、2D 图像 token 和 3D 视频 token 的共享词汇表上进行下一个 token 预测。训练期间权重按模态特定因子乘以以平衡贡献，但损失函数相同。

在以下混合数据上训练：
- 图像生成：`<text caption> <image> image_tokens </image>`
- 图像感知：`<image> image_tokens </image> <question> text_tokens`
- 视频生成：`<text caption> <video> video_tokens </video>`
- 视频感知：类似。
- 纯文本：标准 NTP。

模型从数据分布中学习何时发出图像 token vs 文本 token。生成从模型在 `<image>` 标签后预测图像 token 中涌现。

### 无分类器引导与温度

自回归图像生成在推理时通过无分类器引导（CFG）大幅提升。Emu3 使用它：生成两次，一次用完整描述，一次用空描述，用引导权重混合 logits（典型 3.0-7.0）。这与扩散使用的 CFG 技巧相同，借用到自回归设置中。

温度很重要：太高，伪影；太低，模式坍缩。Emu3 推荐温度为感知 1.0，图像生成 0.8。

### 三个角色，一个模型

Emu3 以三个功能不同的 API 发布，但底层权重相同：

- **Emu3-Gen**。图像生成。输入文本，输出图像 token。
- **Emu3-Chat**。VQA 和描述。输入图像（token），输出文本。
- **Emu3-Stage2**。视频生成和视频 VQA。输入文本或视频，输出文本或视频。

没有任务特定的头。只有不同的提示模板。同一个 checkpoint。

### 基准

来自 Emu3 论文（2024 年 9 月）：

- 图像生成：在 MJHQ-30K FID 上击败 SDXL（5.4 vs 5.6），GenEval 总分（0.54 vs 0.55——统计平局），Deep-Eval 综合分数持平。
- 图像感知：在 VQAv2 上击败 LLaVA-1.6（75.1 vs 72.4），MMMU 上大致持平。
- 视频生成：4 秒片段质量在 FVD 上与 Sora 时代公开基准模型相当。

数字并非总是胜出——Emu3 在这里得一分在那里失一分——但"下一个 token 预测就是你所需要的一切"的声明在各模态上都是站得住脚的。

### 计算成本

Emu3 在约 3000 亿多模态 token 上用 7B 参数模型训练。GPU 小时大致与 Llama-2-7B 预训练相当（A100 级硬件上 2k-4k GPU 年）。Stable Diffusion 3 等扩散模型在类似预算下训练，但需要独立的文本编码器和更复杂的流水线。

推理时，Emu3 每张图像比 SDXL 慢：4096 个图像 token 以 30 tok/s 约 2 分钟生成一张 512×512 图像，vs SDXL 的 2-5 秒。推测解码和 KV 缓存优化缩小了差距但没有消除。自回归图像生成计算量大；这是持续存在的权衡。

### 为什么重要

Emu3 的深层贡献是概念性的。如果下一个 token 预测能扩展到匹配扩散的图像生成，统一模型路径（一个损失，一个骨干网络，任意模态）就是可行的。未来模型不需要独立的文本编码器、独立的扩散调度器、独立的 VAE。一个 Transformer，每模态一个 tokenizer，扩展。

Show-o、Janus-Pro 和 InternVL-U 都建立在这个论点之上或对其发起挑战。中国实验室（BAAI、DeepSeek）在 2025 年比美国实验室更积极地在这个方向发表。

## 使用它

`code/main.py` 构建了两个玩具组件：

- 2D vs 3D VQ tokenizer 计数计算器：给定（分辨率、patch、片段长度、FPS），计算图像 vs 视频的 token 数量。
- 带温度下无分类器引导的自回归图像 token 采样器。

CFG 实现匹配 Emu3 的方案——用引导权重混合条件和无条件 logits。

## 产出

本课生成 `outputs/skill-token-gen-cost-analyzer.md`。给定生成产品规格（图像或视频、目标分辨率、质量层级、延迟预算），它计算 token 数量、推理成本，并在 Emu3 系列 vs 扩散之间做出选择。

## 练习

1. Emu3 在 8×8 缩减下每张 512×512 图像产生 4096 个 token。计算 1024×1024 和 2048×2048 的等效数量。推理延迟会怎样？

2. 阅读 Emu3 第 3.3 节关于视频 tokenizer。描述 3D VQ patch 形状以及为什么是 4×4×4 而非 8×8×1。

3. 无分类器引导权重 5.0 vs 3.0：视觉效果有什么不同？在 `code/main.py` 中追踪数学。

4. 计算 Emu3-7B 在 300B token 上的训练 FLOPs 并与 Stable Diffusion 3 对比。哪个训练更贵？

5. Emu3 在 FID 上击败 SDXL 但在 VQAv2 上不如专用 VLM。解释为什么统一损失方法在不同基准上对专家模型显示出不同的优势。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Next-token prediction（下一个 token 预测） | "NTP" | 标准自回归损失：给定 token[0..i] 预测 token[i+1]；当各模态被 token 化后对所有模态有效 |
| IBQ tokenizer | "逆瓶颈量化器" | 一类具有更大码本（32768+）和比 Chameleon 更好重建质量的 VQ-VAE |
| 3D VQ | "时空量化器" | 按 (时间, 行, 列) 索引的码本；一个 token 覆盖 4×4×4 像素立方体 |
| Classifier-free guidance（无分类器引导） | "CFG" | 用权重 gamma 混合条件和无条件 logits；推理时提升图像质量 |
| Unified vocabulary（统一词汇表） | "共享 token" | 文本 + 图像 + 视频都从同一整数空间抽取；模型预测下一个到来的任何模态 |
| MJHQ-30K | "图像生成基准" | Midjourney 质量的基准，30k 个提示；Emu3 在此报告 FID |

## 延伸阅读

- [Wang 等人 — Emu3: Next-Token Prediction is All You Need (arXiv:2409.18869)](https://arxiv.org/abs/2409.18869)
- [Sun 等人 — Emu: Generative Pretraining in Multimodality (arXiv:2307.05222)](https://arxiv.org/abs/2307.05222)
- [Liu 等人 — LWM (arXiv:2402.08268)](https://arxiv.org/abs/2402.08268)
- [Yu 等人 — MAGVIT-v2 (arXiv:2310.05737)](https://arxiv.org/abs/2310.05737)
- [Tian 等人 — VAR (arXiv:2404.02905)](https://arxiv.org/abs/2404.02905)