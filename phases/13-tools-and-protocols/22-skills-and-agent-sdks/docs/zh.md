# 技能与 Agent SDK — Anthropic Skills、AGENTS.md、OpenAI Apps SDK

> MCP 说"有哪些工具"。技能说"如何完成任务"。2026 年的技术栈两者都用。Anthropic 的 Agent Skills（开放标准，2025 年 12 月）以 SKILL.md 形式发布，支持渐进式披露。OpenAI 的 Apps SDK 是 MCP 加小组件元数据。AGENTS.md（现在在 60,000 多个仓库中）位于仓库根目录作为项目级 Agent 上下文。本课说明各自的覆盖范围，并构建一个跨 Agent 携带的最简 SKILL.md + AGENTS.md 组合。

**类型：** Learn
**语言：** Python（stdlib，SKILL.md 解析器和加载器）
**前置课程：** Phase 13 · 07（MCP 服务器）
**时间：** ~45 分钟

## 学习目标

- 区分三层：AGENTS.md（项目上下文）、SKILL.md（可复用知识）、MCP（工具）。
- 用 YAML frontmatter 和渐进式披露编写 SKILL.md。
- 以文件系统风格将技能加载到 Agent 运行时。
- 将技能与 MCP 服务器和 AGENTS.md 组合，使一个包在 Claude Code、Cursor 和 Codex 中都能工作。

## 问题

一个工程师将发布说明写作流程提炼为多步骤提示："读取最新的已合并 PR。按领域分组。每个摘要。按照团队风格写更新日志条目。发布到 Slack 草稿。"他们把它放在团队的 Notion 文档中。

现在他们想在 Claude Code、Cursor 和 Codex CLI 中使用这个工作流。每个 Agent 有不同的加载指令方式：Claude Code 斜杠命令、Cursor rules、Codex `.codex.md`。工程师复制了三遍工作流并维护三个副本。

AGENTS.md 和 SKILL.md 一起修复了这个问题：

- **AGENTS.md** 位于仓库根目录。每个兼容的 Agent 在会话开始时读取它。"这个项目怎么运作？约定是什么？哪个命令运行测试？"
- **SKILL.md** 是一个可移植的组合：YAML frontmatter（name、description）+ markdown 正文 + 可选资源。支持技能的 Agent 按名称按需加载。
- **MCP**（Phase 13 · 06-14）处理技能需要调用的工具。

三层，一个可移植的工件。

## 核心概念

### AGENTS.md（agents.md）

2025 年末推出，到 2026 年 4 月已被 60,000 多个仓库采用。仓库根目录一个文件。格式：

```markdown
# Project: my-service

## Conventions
- TypeScript with strict mode.
- Use Pydantic for models on the Python side.
- Tests run with `pnpm test`.

## Build and run
- `pnpm dev` for local dev server.
- `pnpm build` for production bundle.
```

Agent 在会话开始时读取此文件，并用它来校准自己在该项目中的行为。2026 年的每个编码 Agent 都支持 AGENTS.md：Claude Code、Cursor、Codex、Copilot Workspace、opencode、Windsurf、Zed。

### SKILL.md 格式

Anthropic 的 Agent Skills（2025 年 12 月作为开放标准发布）：

```markdown
---
name: release-notes-writer
description: Write a changelog entry for the latest merged PRs following this project's style.
---

# Release notes writer

When invoked, run these steps:

1. List PRs merged since the last tag. Use `gh pr list --base main --state merged`.
2. Group by label: feature, fix, chore, docs.
3. For each PR in each group, write one line: `- <title> (#<num>)`.
4. Draft the release notes and stage them in CHANGELOG.md.

If the user says "ship", run `git tag vX.Y.Z` and `gh release create`.

## Notes

- Never include commits without a PR.
- Skip "chore" entries from the public changelog.
```

Frontmatter 声明技能的身份。正文是技能加载时呈现给模型的提示。

### 渐进式披露

技能可以引用子资源，Agent 仅在需要时获取。示例：

```
skills/
  release-notes-writer/
    SKILL.md
    style-guide.md
    template.md
    scripts/
      generate.sh
```

SKILL.md 说"风格规则见 style-guide.md"。Agent 仅在技能活跃运行时才拉取 style-guide.md。这避免了用模型可能不需要的细节膨胀提示。

### 文件系统发现

Agent 运行时扫描已知目录查找 SKILL.md 文件：

- `~/.anthropic/skills/*/SKILL.md`
- 项目 `./skills/*/SKILL.md`
- `~/.claude/skills/*/SKILL.md`

加载按文件夹名和 frontmatter `name` 进行。Claude Code、Anthropic Claude Agent SDK 和 SkillKit（跨 Agent）都遵循此模式。

### Anthropic Claude Agent SDK

`@anthropic-ai/claude-agent-sdk`（TypeScript）和 `claude-agent-sdk`（Python）在会话开始时加载技能，将它们作为运行时内可调用的"agents"暴露。当用户调用时，Agent 循环分发到技能。

### OpenAI Apps SDK

2025 年 10 月发布；直接构建在 MCP 上。将 OpenAI 之前的 Connectors 和 Custom GPT Actions 统一到单一开发者界面。一个 Apps SDK 应用是：

- 一个 MCP 服务器（tools、resources、prompts）。
- 加上 ChatGPT UI 的小组件元数据。
- 加上可选的 MCP Apps `ui://` 资源用于交互式界面。

相同的协议，更丰富的 UX。

### 通过 SkillKit 实现跨 Agent 可移植性

SkillKit 和类似的跨 Agent 分发层将单个 SKILL.md 翻译为 32 多个 AI Agent（Claude Code、Cursor、Codex、Gemini CLI、OpenCode 等）的原生格式。一个真实来源；多个消费者。

### 三层技术栈

| 层 | 文件 | 加载时机 | 目的 |
|----|------|---------|------|
| AGENTS.md | 仓库根目录 | 会话开始 | 项目级约定 |
| SKILL.md | 技能目录 | 技能被调用时 | 可复用工作流 |
| MCP 服务器 | 外部进程 | 需要工具时 | 可调用动作 |

三层可以组合：Agent 在会话开始时读取 AGENTS.md，用户调用一个技能，技能的指令包含 MCP 工具调用，Agent 通过 MCP 客户端分发。

## 使用方法

`code/main.py` 提供了一个标准库 SKILL.md 解析器和加载器。它发现 `./skills/` 下的技能，解析 YAML frontmatter 加 markdown 正文，生成按技能名键控的字典。然后模拟一个 Agent 循环，按名称调用 `release-notes-writer`。

关注要点：

- YAML frontmatter 用最简的标准库解析器解析（无 `pyyaml` 依赖）。
- 技能正文原样存储；调用时 Agent 将其前置到系统提示。
- 渐进式披露通过 `read_subresource` 函数演示，按需拉取引用的文件。

## 交付产出

本课产出 `outputs/skill-agent-bundle.md`。给定一个工作流，该技能生成组合的 SKILL.md + AGENTS.md + MCP 服务器蓝图组合，跨 Agent 可移植。

## 练习

1. 运行 `code/main.py`。在 `skills/` 下添加第二个技能并确认加载器能发现它。

2. 为此课程仓库编写一个 AGENTS.md。包括测试命令、风格约定和 Phase 13 的心智模型。

3. 将团队内部文档中的多步骤工作流移植到 SKILL.md。验证它在 Claude Code 中能加载。

4. 将技能手动翻译为 Cursor 和 Codex 的原生规则格式。统计格式之间的差异 — 这是 SkillKit 自动化的翻译面。

5. 阅读 Anthropic Agent Skills 博客文章。找出 Claude Agent SDK 中本课加载器未涵盖的一个功能。（提示：Agent 子调用。）

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| SKILL.md | "技能文件" | YAML frontmatter 加 markdown 正文，由 Agent 运行时加载 |
| AGENTS.md | "仓库根目录 Agent 上下文" | 会话开始时读取的项目级约定文件 |
| Progressive Disclosure（渐进式披露） | "延迟加载子资源" | 技能正文引用仅在需要时拉取的文件 |
| Frontmatter | "顶部 YAML 块" | `---` 分隔符中的元数据（name、description） |
| Claude Agent SDK | "Anthropic 的技能运行时" | `@anthropic-ai/claude-agent-sdk`，加载技能并路由 |
| OpenAI Apps SDK | "MCP 加小组件元数据" | OpenAI 构建在 MCP 上的开发者平台，带 ChatGPT UI 钩子 |
| Skill Discovery（技能发现） | "文件系统扫描" | 遍历已知目录查找 SKILL.md，按名称键控 |
| Cross-agent Portability（跨 Agent 可移植性） | "一个技能多个 Agent" | 通过 SkillKit 类工具将一个 SKILL.md 翻译到 32 多个 Agent |
| Agent Skill（Agent 技能） | "可移植知识" | MCP 工具概念之外的可复用任务模板 |
| Apps SDK | "MCP 加 ChatGPT UI" | Connectors 和 Custom GPTs 统一到 MCP |

## 延伸阅读

- [Anthropic — Agent Skills announcement](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — 2025 年 12 月发布
- [Anthropic — Agent Skills docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — SKILL.md 格式参考
- [OpenAI — Apps SDK](https://developers.openai.com/apps-sdk) — 基于 MCP 的 ChatGPT 开发者平台
- [agents.md](https://agents.md/) — AGENTS.md 格式和采用列表
- [Anthropic — anthropics/skills GitHub](https://github.com/anthropics/skills) — 官方技能示例