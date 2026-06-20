"""编码者角色 — 领取子任务，生成代码 diff

编码者是多 Agent 团队的执行者。每个编码者：
1. 从 Board 读取分配给自己的子任务
2. 调用 LLM 生成代码实现
3. 将 diff 发布到 Board

设计原则：
- 每个编码者独立工作，不知道其他编码者在做什么
- 输出是代码 diff（文本），不是真实文件操作
- diff 包含修改的文件、行数、代码内容
"""

from __future__ import annotations

from board import Board,Message,MsgKind,Subtask
from .base import Role


CODER_PROMPT = """你是一个高级 Python 开发者。你收到了一个子任务，需要实现代码。

你的输出必须严格是 JSON 格式：
{
  "files": [
    {
      "path": "文件路径",
      "content": "完整的文件内容"
    }
  ],
  "summary": "你做了什么的简要描述",
  "tests": "测试代码（如有）"
}

重要规则：
- 只修改分配给你的文件，不要碰其他文件
- 代码必须是完整可运行的，不要用省略号
- 如果需要新增文件，也要包含完整内容
- 保持代码简洁，符合 Python 最佳实践
- 包含必要的注释
"""


class Coder(Role):
    """编码者：领取子任务 → 生成代码 diff
    
    工作流程：
    1. 从 Board 读取分配给自己的子任务
    2. 调用 LLM 生成代码
    3. 将 diff 发布到 Board
    """

    def run(self, board: Board, subtask: Subtask) -> dict:
        user_msg = (
            f"请实现以下子任务：\n\n"
            f"子任务名称：{subtask.name}\n"
            f"涉及文件：{', '.join(subtask.files)}\n"
            f"请为这些文件编写完整代码。"
        )

        data = self.call_llm(CODER_PROMPT, user_msg)    

        files = data.get("files", []) 
        #data.get是字典的get方法，用于获取字典中指定键的值，如果键不存在，则返回默认值
        summary = data.get("summary", "")


        subtask.lines_changed = sum(
            len(f.get("content", "").splitlines()) for f in files
        )

        diff_payload = {
            "subtask": subtask.name,
            "files": files,
            "summary": summary,
            "lines": subtask.lines_changed,
            "has_bug": subtask.has_bug,
        }

        board.post(Message(
            kind = MsgKind.DIFF_READY,
            by = self.name,
            to = "merge_coord",
            payload = diff_payload,
            tokens = self.tokens_used,
        ))

        return diff_payload