"""任务板 — 多 Agent 团队的消息中心

Board 是所有角色之间的通信中枢。角色通过 post() 发送消息，
通过 inbox() 读取发给自己的消息。Board 自动跟踪每个角色的
Token 消耗，用于最终的成本分析。

设计原则：
- Board 是唯一的共享状态
- 角色之间不直接通信，必须通过 Board
- 每条消息都自动记账
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json

from board.message import Message

@dataclass
class Board:
    """任务板：存储所有消息，跟踪 Token 消耗   
    使用方式：
        board = Board()
        board.post(Message(kind=MsgKind.SUBTASK, by="architect", 
                          to="coder-A", payload={...}, tokens=1200))
        
        # 编码者读取发给自己的消息
        my_msgs = board.inbox("coder-A")
    """

    message: list[Message] = field(default_factory=list)
    # list和dict的差异：list是有序的，dict是无序的
    token_by_role: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    #用lambda而不是dict()，因为dict()会创建一个空的dict，而lambda会创建一个空的defaultdict,空的dict不能添加元素
    handoffs: list[dict] = field(default_factory=list)
    #给 handoffs 定义一个列表,元素是字典

    def post(self, msg: Message) -> None:
        """发送一条消息到任务板
        做两件事：
        1. 把消息存入列表
        2. 累加发送者的 Token 消耗
        3. handoff记录消息的流转
        """
        self.message.append(msg)
        self.token_by_role[msg.by] += msg.tokens
        self.handoffs.append({
            "kind": msg.kind.value,
            "from": msg.by,
            "to": msg.to,
            "tokens": msg.tokens,
            "payload_size": len(json.dumps(msg.payload)),
        })       



    def inbox(self, role: str) -> list[Message]:
        """获取某个角色收到的所有消息
        Args:
            role: 角色名，如 "reviewer", "coder-A"
        Returns:
            发送给该角色的消息列表
        """
        return [msg for msg in self.message if msg.to == role]
    

    def total_tokens(self) -> int:
        """获取所有角色的 Token 消耗总和"""
        return sum(self.token_by_role.values())