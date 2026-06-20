"""评审者角色 — 审查代码 diff，决定批准或驳回

评审者是多 Agent 团队的质量把关者。它的工作是：
1. 读取合并后的 diff
2. 检查代码质量、逻辑正确性、潜在 bug
3. 批准或驳回（附具体原因）

设计原则：
- 评审者不能批准自己编写的代码（课程硬性要求）
- 驳回时必须指出具体问题和修改建议
- 输出是结构化 JSON，不是自由文本
"""
from __future__ import annotations

from board import Board, Message, MsgKind
from roles.base import Role


REVIEWER_PROMPT = """你是一个资深代码评审者。你需要审查代码 diff，找出潜在问题。

你的输入是一个或多个编码者提交的代码 diff。

你必须严格以 JSON 格式回复：
{
  "approved": true 或 false,
  "comment": "你的评审意见",
  "issues": [
    {
      "file": "有问题的文件路径",
      "line": "问题所在行（估算）",
      "description": "问题描述",
      "severity": "critical / major / minor"
    }
  ]
}

评审标准：
- 代码是否正确实现了需求？
- 是否有明显的 bug（逻辑错误、边界条件、异常处理）？
- 代码风格是否一致？
- 是否有安全隐患？

重要规则：
- 如果代码质量可接受，approved 设为 true
- 如果发现严重问题，approved 设为 false，并在 issues 中列出所有问题
- 即使 approved，也可以在 comment 中提出改进建议
"""


class Reviewer(Role):
  """评审者：读 diff → 批准或驳回
  
  工作流程：
  1. 从 Board 读取 REVIEW_NEEDED 消息
  2. 调用 LLM 审查 diff
  3. 发布 APPROVED 或 REVIEW_FEEDBACK 消息
  """

    
  def run(self, board: Board) -> bool:
    """运行评审者逻辑
    Args:
      board: 任务板  
    Returns:
      True 如果批准，False 如果驳回
    """
    
    review_msgs = board.inbox(self.name)
    if not review_msgs:
      raise ValueError(f"{self.name}未接收到 REVIEW_NEEDED 消息")
    
    lastest_msg = review_msgs[-1]
    diffs = lastest_msg.payload.get("diffs", [])

    diff_summary = ""
    for i, diff in enumerate(diffs):
      diff_summary += f"\ncoder{i+1} diff\n"
      diff_summary += f"subtask: {diff.get('subtask', '')}\n"
      diff_summary += f"digest:{diff.get('summary', 'none')}\n"
      diff_summary += f"edited lines: {diff.get('lines', 0)}"

      for f in diff.get("files", []):
        diff_summary += f"\n文件: {f.get('path', '?')}\n"
        diff_summary += f.get("content", "")[:2000]  # 截断避免太长
        diff_summary += "\n"

    user_msg = f"请审查以下代码 diff：\n{diff_summary}"
    data = self.call_llm(REVIEWER_PROMPT, user_msg)

    approved = data.get("approved", False)
    comment = data.get("comment", "")
    issues = data.get("issues", [])


    if approved:
      board.post(Message(
        kind=MsgKind.APPROVED,
        by=self.name,
        to="tester",
        payload={"comment": comment, "diffs": diffs},
        tokens=self.tokens_used,
      ))
    else:
      first_coder = diffs[0].get("coder", "coder-A") if diffs else "coder-A"
      board.post(Message(
        kind=MsgKind.REVIEW_FEEDBACK,
        by=self.name,
        to=first_coder,
        payload={"comment": comment, "issues": issues},
        tokens=self.tokens_used,
      ))
      
    return approved