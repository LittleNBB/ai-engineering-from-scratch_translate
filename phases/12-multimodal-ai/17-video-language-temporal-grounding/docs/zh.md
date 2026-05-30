# 视频语言模型：时间 Token 与定位

> 视频不是照片的堆叠。5 秒片段有因果顺序、动作动词和事件计时，图像模型无法表示。Video-LLaMA（Zhang 等人，2023 年 6 月）发布了第一个带视听定位的开源视频 LLM。VideoChat 和 Video-LLaVA 扩展了该模式。到 2025 年，Qwen2.5-VL 的 TMRoPE 缩小了与前沿专有模型的差距。每个系统以不同方式解决时间 token——每片段 Q-former、每帧拼接池化、每 token TMRoPE。本课解读这些模式，构建均匀 vs 动态帧采样器，并在时间定位任务上评估。

**类型：** Build
**语言：** Python（标准库，帧采样器 + 时间定位评估器）
**前置课程：** Phase 12 · 08（LLaVA-OneVision）
**时间：** ~180 分钟

## 学习目标

- 解释为什么时间位置编码独立于视觉编码器改变视频 VLM 性能。
- 对比均匀、动态 FPS 和事件驱动帧采样在每秒 token 数 vs 定位准确率上的差异。
- 描述每片段 Q-former（Video-LLaMA）vs 每帧池化（Video-LLaVA）vs 每 token M-RoPE（Qwen2.5-VL）设计。
- 说出四个视频基准：VideoMME、TempCompass、EgoSchema、Video-MMMU。

## 问题

30 FPS 的 1 分钟视频有 1800 帧。每帧 196 个视觉 token（ViT-B at 224），那是 352k token——大于任何 2024 年代 LLM 上下文。

三种缩减策略存在：

1. 子采样帧（根据内容 1-8 FPS）。
2. 激进池化每帧的 patch token（3×3 或 4×4 双线性池化）。
3. 通过 Q-former 压缩，取 16 帧片段输出 64 个 token。

每种权衡不同。子采样丢失时间细节。池化丢失空间细节。Q-former 两者都丢失一点但节省 token。

时间位置编码是另一轴：模型如何知道帧 5 在帧 6 之前？选项包括简单 1D 时间 RoPE（Video-LLaMA）、学习的时间嵌入（Video-LLaVA）和 TMRoPE（Qwen2.5-VL，完整 3D）。

## 概念

### Video-LLaMA：每片段 Q-former + 音频分支

Video-LLaMA（2023）是第一个开源视频 LLM。架构：

- 2 FPS 的 16 帧片段（即 8 秒）。
- 逐帧 ViT 特征 → 视频 Q-former 交叉关注所有 16 帧 → 32 个学习 query → LLM。
- 并行音频分支：波形 → ImageBind 音频编码器 → 音频 Q-former → 32 个 query → LLM。

优势：视听联合推理。劣势：固定片段长度，无任意时间定位。

### VideoChat 和 Video-LLaVA

VideoChat 保留了 Video-LLaMA 的想法但去掉了音频并简化了。Video-LLaVA（Lin 等人，2023）在图像和视频帧上训练单一视觉编码器（"投影前对齐"），给出统一表示。两者都是冻结 CLIP 编码器 + MLP + LLM。

两者都不处理长视频。都是 8-16 帧系统。

### Qwen2.5-VL 和 TMRoPE

Qwen2.5-VL 引入了 TMRoPE——时间模态旋转位置嵌入。每个 patch token 携带 (t, h, w) 位置，其中 t 是实际时间戳（非帧索引）。

与简单时间嵌入的关键区别：

- **绝对时间，非索引**。模型看到"在 4.2 秒"而非"在第 15 帧"。
- **逐 token 旋转，非每片段**。每个视觉 token 按其时间戳独立旋转。
- **兼容动态 FPS**。如果你在这里以 2 FPS 采样在那里以 4 FPS 采样，TMRoPE 原生处理不均匀间距。

TMRoPE 支持"猫在第几秒跳？"的查询。模型可以输出"在 4.2 秒"。Video-LLaMA 只能说"片段早期"。

### 帧采样策略

**均匀**：在时长内均匀采样 N 帧。简单，丢失运动峰值。

**动态 FPS**：根据运动强度自适应采样。光流或帧差分选择高运动段进行更密集采样。Qwen2.5-VL 在此上训练。

**事件驱动**：运行轻量检测器，在动作发生处采样更多。VideoAgent 使用。

**关键帧 + 上下文**：在镜头边界 + 少量相邻帧处采样。用于电影内容。

### 每帧池化

1 FPS 每帧 576 个 token，5 分钟片段是 172,800 个 token。用 Qwen2.5-VL-72B 的 128k 上下文可行但昂贵。

3×3 双线性池化减少到每帧 64 个 token → 5 分钟 19,200 个 token。大多数任务的最佳平衡点。

更激进池化（6×6 → 每帧 16 个 token）用于空间细节不太重要的代理工作流。

### 四个视频基准

- **VideoMME**：全面视频理解，短 + 中 + 长。
- **TempCompass**：细粒度时间推理，"之前" / "之后"问题。
- **EgoSchema**：长视野第一人称视频。
- **Video-MMMU**：多模态多学科视频问题。

完整的视频 VLM 评估涵盖全部四个。它们强调不同轴——TempCompass 全部关于顺序，EgoSchema 关于 3 分钟以上推理，VideoMME 跨越时长。

### 定位输出格式

时间定位的输出格式：

- **自由文本**："猫大约在 4 秒时跳了。"易于解析但不精确。
- **结构化 JSON**：`{"event": "jump", "start": 4.1, "end": 4.3}`。Qwen2.5-VL 训练此格式。
- **基于 token**：特殊的 `<time>4.1</time>` token 与答案交错。Qwen2.5-VL 的内部格式。

基于 token 对下游使用最准确。Qwen2.5-VL 的 JSON 输出格式直接解析。

### 2026 年最佳实践

2026 年视频 VLM 的最佳实践：

- **编码器**：带 M-RoPE 或 TMRoPE 的 SigLIP 2（Qwen2.5-VL）。
- **帧采样**：动态 FPS（根据运动 1-4）配合最大帧上限。
- **每帧池化**：3×3 双线性。
- **输出**：带时间和事件字段的结构化 JSON。
- **基准**：VideoMME + TempCompass 用于通用；EgoSchema 用于长视野。

## 使用它

`code/main.py` 包括：

- 均匀和动态 FPS 帧采样器。
- 玩具时间定位评估器：给定时间 T 的"真实"事件和模型输出，以容差评分准确率。
- Video-LLaMA（16 帧，Q-former）、Video-LLaVA（8 帧，MLP）、Qwen2.5-VL（动态 FPS + TMRoPE）的对比。

## 产出

本课生成 `outputs/skill-video-vlm-frame-planner.md`。给定视频任务（监控、动作识别、时间定位、摘要），它选择帧采样器、池化因子、输出格式和预期准确率层级。

## 练习

1. 对于 3 分钟的烹饪演示，选择均匀 vs 动态 FPS。用 token 数提供依据。

2. TMRoPE 具体增加了什么简单时间嵌入表做不到的？

3. 为时间定位编写一个 VLM 可以学会发出的 JSON schema。包含错误情况。

4. 阅读 Video-LLaVA 第 3 节关于"投影前对齐"。为什么这比训练独立的图像和视频编码器更好？

5. 给定 VideoMME 排行榜，2026 年顶级开源模型和顶级专有模型之间的差距是多少？多少差距可归因于时间编码 vs 基础 LLM 规模？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Temporal grounding（时间定位） | "时间定位答案" | VLM 输出事件发生的具体时间戳范围 |
| TMRoPE | "时间多模态 RoPE" | 带绝对时间戳的 3D 旋转位置，Qwen2.5-VL 使用 |
| Dynamic FPS（动态 FPS） | "运动感知采样" | 高运动段采样更多帧，静态段更少 |
| Frame pooling（帧池化） | "每帧空间压缩" | 在 LLM 之前用双线性插值减少每帧 patch 数 |
| Video Q-former | "片段压缩器" | 将 N 帧映射到 K 个学习 query 的交叉注意力瓶颈 |
| VideoMME | "视频基准" | 全面的短/中/长视频基准，2500+ 样本 |

## 延伸阅读

- [Zhang 等人 — Video-LLaMA (arXiv:2306.02858)](https://arxiv.org/abs/2306.02858)
- [Li 等人 — VideoChat (arXiv:2305.06355)](https://arxiv.org/abs/2305.06355)
- [Lin 等人 — Video-LLaVA (arXiv:2311.10122)](https://arxiv.org/abs/2311.10122)
- [Qwen Team — Qwen2.5-VL (arXiv:2502.13923)](https://arxiv.org/abs/2502.13923)
- [Lin 等人 — VILA-1.5 (arXiv:2312.07533)](https://arxiv.org/abs/2312.07533)