"""架构师角色 — 读取 issue,拆分为子任务

架构师是多 Agent 团队的规划者。它的工作是：
1. 理解 issue 的需求
2. 将问题拆分为多个独立的子任务
3. 明确每个子任务涉及的文件和接口
4. 将计划发布到任务板

设计原则：
- 子任务之间应该是独立的（可以并行实现）
- 每个子任务必须明确涉及哪些文件（避免合并冲突）
- 输出是结构化 JSON,不是自由文本
"""

from __future__ import annotations

from board import Board, Message, MsgKind, Subtask
from roles.base import Role

ARCHITECT_PROMPT = """你是一个软件架构师。你的任务是将一个 GitHub issue 拆分为多个可并行实现的子任务。

你必须严格以 JSON 格式回复：
{
  "subtasks": [
    {
      "name": "子任务名称",
      "files": ["涉及的文件路径"],
      "description": "这个子任务要做什么"
    }
  ]
}

重要规则：
- 每个子任务应该独立，可以由不同的编码者并行实现
- 每个子任务必须明确涉及哪些文件，避免多个编码者修改同一文件
- 子任务数量通常 2-6 个，不要太多也不要太少
- 子任务的粒度应该适中：太大无法并行，太小开销太大
"""


class Architect(Role):
    """架构师：读取 issue → 输出子任务 DAG
    
    工作流程：
    1. 从 Board 读取 issue 描述
    2. 调用 LLM 拆分为子任务
    3. 将子任务发送到 Board
    """

    def run(self, board: Board) -> list[Subtask]:
        """运行架构师逻辑
        Args:
        board: 任务板，用于发布计划
        Returns:
        子任务列表，供后续分配给编码者
        """       

        # 读取 issue 描述
        plan_msg = board.inbox(self.name)
        if not plan_msg:
            raise ValueError("架构师没有收到计划消息")

        issue = plan_msg[0].payload.get("issue", "unknown")

        # 调用 LLM 拆分为子任务
        user_msg = f"请将以下issue 拆分为子任务：\n\n{issue}"
        data = self.call_llm(ARCHITECT_PROMPT, user_msg)
        
        #创建子任务列表，并从 JSON 数据中解析子任务
        subtasks = []
        for item in data.get("subtasks", []):
            subtasks.append(Subtask(
                name=item.get("name"),
                files=item.get("files",[]),
            ))

        #通过定义的消息类型将子任务发送到 Board
        board.post(Message(
            kind = MsgKind.PLAN_REQUEST,
            by = self.name,
            to = "board",
            payload = {
                "issue": issue,
                "subtasks": [s.name for s in subtasks] 
            },
            tokens = self.tokens_used,
        ))

        return subtasks