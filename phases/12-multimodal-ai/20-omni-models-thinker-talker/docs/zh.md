# Omni 模型：Qwen2.5-Omni 与 Thinker-Talker 分离

> GPT-4o 的产品演示在 2024 年 5 月具有颠覆性，不是因为底层模型，而是因为产品形态——一个语音界面，你说话，模型看到摄像头画面，并在 250ms 内语音回复。开源生态在 2024 年剩余时间和 2025 年竞相达到这个产品表面。Qwen2.5-Omni（2025 年 3 月）是参考开源设计：一个 Thinker（大型文本生成 Transformer）加上一个 Talker（并行语音生成 Transformer），通过流式语音 token 连接。Mini-Omni 简化了它，Moshi 匹配了其延迟，GLM-4-Voice 将其扩展到中文。本课解读 Thinker-Talker 架构和使流式实时对话工作的延迟预算。

**类型：** Build
**语言：** Python（标准库，流式流水线延迟模拟器 + VAD 循环）
**前置课程：** Phase 12 · 19（音频 LLM）、Phase 12 · 16（任意到任意）
**时间：** ~180 分钟

## 学习目标

- 将推理流水线拆分为 Thinker（文本推理）和 Talker（语音合成），解释为什么并行流式传输有效。
- 计算对话交互的首个音频字节时间（TTFAB）预算，逐组件分解。
- 描述 TMRoPE 在 Thinker 内部跨视觉、音频和文本的时间对齐位置编码。
- 说出三种实时对话模式：半双工、轮次交替、全双工。

## 问题

实时语音助手需要快速完成很多事情：

1. **听用户**。实时语音 token 化，语音活动检测（VAD）以知道用户何时说完。
2. **可选地看**。2-4 FPS 的摄像头输入，与音频一起流式输入 Thinker。
3. **思考**。以对话历史为条件组合回复。
4. **说话**。合成语音 token，解码为波形，流式传输到用户扬声器。

每一步都增加延迟。对话级体验要求总往返 < 500ms——低于此值，用户不再注意延迟。GPT-4o 声称约 250ms。Moshi 约 160ms。Qwen2.5-Omni 约 350-500ms。

每个组件都需要流式传输。不能"批处理所有内容然后解码"。

## 概念

### Thinker 和 Talker

Qwen2.5-Omni 的分解：

- **Thinker**：7B-80B 文本生成 Transformer。消费交错的文本 + 图像 + 音频 token。输出表示要说什么的文本 token。
- **Talker**：更小的语音生成 Transformer（200M-1B）。消费 Thinker 的文本输出 token 加上最近的语音上下文 token。输出离散语音 token（残差 VQ 索引）。
- **语音解码器**：流式波形解码器（SNAC、MoVQGAN 系列），实时将语音 token 转换为音频样本。

分离很重要。Thinker 必须大才能有好的推理。Talker 可以小，因为其工作是局部的——将文本转换为语音 token。更大的 Talker 不会更有表现力；只会更慢。

并行运行两者：

1. Thinker 发出文本 token t_i。
2. Talker（通过流式）消费 t_i 并发出语音 token s_i, s_{i+1}, ..., s_{i+k}。
3. 语音解码器在语音 token 到达时消费并发出音频样本。
4. 当 Thinker 到达文本 token t_{i+3} 时，Talker 已经为 t_0..t_{i+2} 流式传输了音频。

### TMRoPE——时间对齐的多模态位置

Thinker 需要整合图像帧（以 4 FPS 到达）、音频帧（以 50 帧/秒到达）和对话历史的文本。朴素的序列顺序（所有图像，然后所有音频，然后文本）会丢失时间对齐。

TMRoPE 为每个 token 分配绝对时间戳。视觉 token 在 t=2.3s。音频 token 在 t=2.32s。用户的文本 token "stop" 在 t=2.35s。RoPE 按时间戳旋转注意力；模型将它们视为时间上并发的。

这是"他边挥手边说你好"得以工作的基础设施——模型在概念上的同一时刻看到视频帧和音频。

### 流式语音合成

语音 token 必须流式传输。Mini-Omni（Xie & Wu，2024）引入了"语言模型能听、在思考时流式说话"：Thinker 输出 token 和 Talker 输出 token 在同一序列中交错。Talker 在 Thinker 提交下一个文本 token 后立即触发。无 batch 边界。

Moshi（Défossez 等人，2024 年 10 月）是最快的开源实现。单 A100 上 160ms TTFAB。架构：单一 7B Transformer 在交替位置发出文本和语音 token，带有将思考流与说话流分离的"内心独白"。这实际上是 Thinker + Talker 通过精心训练融合为一个模型。

### VAD 和轮次交替

语音活动检测在输入端运行。两种模式：

- **半双工**：用户说话，模型听。模型说话，用户听。通过 VAD 静音检测（约 200ms）明确交接。
- **全双工**：双方可以同时说话。模型可以反馈（"嗯哼"）或打断。更难。Moshi 支持此模式。

Qwen2.5-Omni 默认支持半双工，通过静音阈值进行轮次交替。全双工需要应用层处理。

### Qwen3-Omni（2025 年 11 月）

后续版本。Qwen3-80B Thinker，更大的 Talker，改进的 TMRoPE-v2。延迟接近 GPT-4o 的 250ms。开源权重。OmniBench 基准上与 Gemini 2.0 Live 竞争力相当。

### 生产延迟预算

典型流式交互：

- 麦克风 -> 音频 token：40-80ms。
- 预填充（提示 + 历史）：7B 上 100-200ms，70B 上更多。
- 第一个 Thinker 文本 token：40ms。
- Talker 处理第一个文本 token：20ms。
- 第一批语音 token 提交：40ms。
- 残差 VQ 解码：30ms。
- 语音波形解码：50-80ms。

总 TTFAB：7B 上 320-510ms，70B 上 600-900ms。前沿质量通常意味着 70B+；因此存在前沿延迟差距。

### Token 速率数学

16kHz 语音以 50 Hz 基础语音 token，你需要每秒 50 个语音 token 输出。Talker 必须发出 ≥50 tok/s 才能跟上。在 H100 上典型 LLM 吞吐量 30-80 tok/s，小型（200-300M）Talker 足够快；7B Talker 会跟不上。

这就是为什么存在小型专用 Talker 模型，而非"直接用主模型"。

## 使用它

`code/main.py`：

- 用模拟 token 发射速率模拟 Thinker-Talker 流水线。
- 为可配置的模型大小和麦克风采样率计算 TTFAB。
- 演示带 VAD 静音阈值的半双工轮次交替。

## 产出

本课生成 `outputs/skill-omni-streaming-budget.md`。给定实时语音产品的目标 TTFAB 和功能集（视觉输入、双语、全双工），选择 Qwen2.5-Omni、Qwen3-Omni、Moshi 或 Mini-Omni 并确定 Thinker/Talker 规模。

## 练习

1. 你的目标 TTFAB 是 300ms。在 7B Thinker 和 300M Talker 上，写出每个组件的延迟。

2. Qwen2.5-Omni 使用 TMRoPE。描述用户在 t=1s 开始说话、摄像头在 t=1.2s 捕获手势时模型看到了什么。

3. 全双工支持要求模型在听的同时发出音频。提出一种教这个的训练数据格式。

4. 阅读 Moshi 论文第 4 节。描述"内心独白"分离以及为什么它避免了 Thinker-Talker 分离。

5. 计算吞吐量预算：Talker 必须以多快的速度发出 token 才能跟上 16kHz 语音的每秒 50 个基础层 token？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Thinker | "推理大脑" | 大型文本生成 Transformer，产生要说什么 |
| Talker | "语音生成嘴" | 小型 Transformer，从 Thinker 的文本产生离散语音 token |
| TTFAB | "延迟预算" | 首个音频字节时间：从用户语音结束到首个音频样本输出 |
| TMRoPE | "时间对齐 RoPE" | 跨视觉、音频、文本使用绝对时间戳的位置编码 |
| Half-duplex（半双工） | "轮次交替" | 用户和模型交替；VAD 静音检测用户说完 |
| Full-duplex（全双工） | "同时" | 模型可以同时说话和听；支持反馈 |
| Inner monologue（内心独白） | "Moshi 分离" | 单模型设计，思考流和说话流交错 |

## 延伸阅读

- [Xu 等人 — Qwen2.5-Omni (arXiv:2503.20215)](https://arxiv.org/abs/2503.20215)
- [Qwen Team — Qwen3-Omni (arXiv:2509.17765)](https://arxiv.org/html/2509.17765v1)
- [Xie & Wu — Mini-Omni (arXiv:2408.16725)](https://arxiv.org/abs/2408.16725)
- [Défossez 等人 — Moshi (arXiv:2410.00037)](https://arxiv.org/abs/2410.00037)
- [Zeng 等人 — GLM-4-Voice (arXiv:2412.02612)](https://arxiv.org/abs/2412.02612)