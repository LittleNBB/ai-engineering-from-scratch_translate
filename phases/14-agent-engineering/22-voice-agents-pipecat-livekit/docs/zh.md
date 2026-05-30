# 语音智能体（Voice Agents）：Pipecat 与 LiveKit

> 语音智能体在 2026 年已成为一流的产品类别。Pipecat 提供基于 Python 的帧级管道框架（VAD → STT → LLM → TTS → 传输层）。LiveKit Agents 通过 WebRTC 将 AI 模型与用户连接。在优化的技术栈中，生产环境的延迟目标为 450-600 毫秒（端到端）。

**类型：** Learn
**语言：** Python（标准库）
**前置课程：** Phase 14 · 01（Agent Loop），Phase 14 · 12（Workflow Patterns）
**时间：** ~60 分钟

## 学习目标

- 描述 Pipecat 的帧级管道架构：DOWNSTREAM（源→汇）和 UPSTREAM（控制）。
- 列出语音管道的标准阶段以及 Pipecat 支持的传输方式。
- 解释 LiveKit Agents 的两种语音智能体类（MultimodalAgent、VoicePipelineAgent）及其适用场景。
- 总结 2026 年的生产延迟预期及其对架构选择的影响。

## 问题背景

语音智能体不是简单地在文本循环上加一个 TTS 模块。延迟预算极为苛刻（~600ms），部分音频（Partial Audio）是默认行为，轮次检测（Turn Detection）依赖模型，传输方式涵盖从电话 SIP 到 WebRTC 等多种协议。你需要构建帧级管道（Pipecat）或依赖平台（LiveKit）。

## 核心概念

### Pipecat（pipecat-ai/pipecat）

- 基于 Python 的帧级管道框架。
- `Frame` → `FrameProcessor` 链式处理。
- 两个流向：
  - **DOWNSTREAM** — 源 → 汇（音频输入，TTS 输出）。
  - **UPSTREAM** — 反馈和控制（取消、指标、用户打断）。
- `PipelineTask` 通过事件（`on_pipeline_started`、`on_pipeline_finished`、`on_idle_timeout`）和观察者（Observer）管理生命周期，用于指标采集、追踪和 RTVI。

典型管道：

```
VAD (Silero) → STT → LLM（上下文交替 user/assistant）→ TTS → 传输层
```

支持的传输方式：Daily、LiveKit、SmallWebRTCTransport、FastAPI WebSocket、WhatsApp。

Pipecat Flows 增加了结构化对话（状态机）。Pipecat Cloud 是托管运行时。

### LiveKit Agents（livekit/agents）

- 通过 WebRTC 将 AI 模型与用户连接。
- 核心概念：`Agent`、`AgentSession`、`entrypoint`、`AgentServer`。
- 两种语音智能体类：
  - **MultimodalAgent** — 直接音频处理，使用 OpenAI Realtime 或等效服务。
  - **VoicePipelineAgent** — STT → LLM → TTS 级联；提供文本级控制。
- 基于 Transformer 模型的语义轮次检测（Semantic Turn Detection）。
- 原生 MCP 集成。
- 通过 SIP 支持电话线路。
- 通过 LiveKit Inference 提供 50+ 免 API 密钥模型；通过插件扩展至 200+。

### 商业平台

Vapi（在优化的技术栈中约 450-600ms）和 Retell（在 180 次测试通话中端到端约 600ms）构建在这些基础设施之上。如果你想要托管语音方案而不想组建 WebRTC 团队，选择平台即可。

### 这种模式的常见陷阱

- **未处理用户打断（Barge-in）。** 用户中断时，智能体仍在说话。需要 Pipecat 中的 UPSTREAM 取消帧，LiveKit 中有等效机制。
- **忽略 STT 置信度（Confidence）。** 低置信度的转录文本被当作准确输入传给 LLM。应根据置信度设门控或请求确认。
- **TTS 中途切断。** 当管道在句子中间取消时，TTS 需要知道或截断音频。
- **忽视延迟预算。** 每个组件增加 50-200ms。在上线前计算整条链路的延迟。

### 2026 年典型延迟

- VAD：20-60ms
- STT 部分结果：100-250ms
- LLM 首个 Token：150-400ms
- TTS 首段音频：100-200ms
- 传输层 RTT：30-80ms

端到端 450-600ms 是顶级水平。800-1200ms 是常见情况。超过 1500ms 会让人感觉明显卡顿。

## 动手实现

`code/main.py` 是一个帧级模拟管道，包含：

- `Frame` 类型（音频、转录、文本、tts_audio、控制）。
- `Processor` 接口及其 `process(frame)` 方法。
- 五阶段管道（VAD → STT → LLM → TTS → 传输层）作为脚本化的处理器。
- UPSTREAM 取消帧用于演示用户打断（Barge-in）。

运行：

```
python3 code/main.py
```

追踪日志展示了正常流程以及一个在句子中途停止 TTS 的打断取消操作。

## 实践应用

- **Pipecat** — 完全自定义控制，Python 优先，支持自定义处理器和可插拔 Provider。
- **LiveKit Agents** — WebRTC 优先的部署方式，支持电话线路。
- **Vapi / Retell** — 无需组建 WebRTC 团队即可获得托管语音智能体。
- **OpenAI Realtime / Gemini Live** — 直接音频输入/输出（MultimodalAgent）。

## 产出物

`outputs/skill-voice-pipeline.md` 为基于 Pipecat 架构的语音管道生成脚手架代码，包含 VAD + STT + LLM + TTS + 传输层以及用户打断处理。

## 练习

1. 为模拟管道添加指标观察者：统计每个阶段每秒处理的帧数。延迟累积在哪里？
2. 实现置信度门控的 STT：低于阈值时，请求"您能再说一遍吗？"
3. 添加语义轮次检测：简单规则 — 如果转录以"？"结尾，则为轮次结束。
4. 阅读 Pipecat 的传输层文档。将标准库传输替换为 SmallWebRTCTransport 配置（存根）。
5. 对比 OpenAI Realtime 与 STT+LLM+TTS 级联处理同一查询的延迟。文本级控制带来多少延迟开销？

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| Frame（帧） | "事件" | 管道中的类型化数据单元（音频、转录、文本、控制） |
| Processor（处理器） | "管道阶段" | 带有 process(frame) 方法的处理器 |
| DOWNSTREAM（下行） | "前向流" | 源到汇：音频输入，语音输出 |
| UPSTREAM（上行） | "反馈流" | 控制：取消、指标、用户打断 |
| VAD（语音活动检测） | "语音活动检测" | 检测用户何时在说话 |
| Semantic Turn Detection（语义轮次检测） | "智能轮次结束" | 基于模型的用户发言结束判断 |
| MultimodalAgent（多模态智能体） | "直接音频智能体" | 音频输入，音频输出；中间无文本 |
| VoicePipelineAgent（语音管道智能体） | "级联智能体" | STT + LLM + TTS；文本级控制 |

## 延伸阅读

- [Pipecat docs](https://docs.pipecat.ai/getting-started/introduction) — 帧级管道、处理器、传输层
- [LiveKit Agents docs](https://docs.livekit.io/agents/) — WebRTC + 语音原语
- [Vapi](https://vapi.ai/) — 托管语音平台
- [Retell AI](https://www.retellai.com/) — 托管语音，延迟基准测试