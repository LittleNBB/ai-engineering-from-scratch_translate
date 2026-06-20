"""A2A 类型化消息定义

这个文件定义了多 Agent 团队中所有角色之间通信的消息类型。
每条消息都有明确的类型（MsgKind），发送者（by），接收者（to）和负载（payload）。

设计原则：
- 消息是不可变的数据结构
- 每种消息类型对应一个明确的状态转换
- payload 是字典，不同类型的消息有不同的 payload 结构
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class MsgKind(Enum):
    """消息类型枚举 — 对应 A2A 协议中的类型化消息"""
    PLAN_REQUEST = "plan_request" # 计划请求消息类型
    SUBTASK = "subtask"  # 子任务消息类型
    DIFF_READY = "diff_ready"  # 差异准备就绪消息类型
    REVIEW_NEEDED = "review_needed"  # 需要审查消息类型
    REVIEW_FEEDBACK = "review_feedback"  # 审查反馈消息类型
    APPROVED = "approved"  # 已批准消息类型
    TEST_NEEDED = "test_needed"  # 需要测试消息类型
    TEST_PASSED = "test_passed"  # 测试通过消息类型
    TEST_FAILED = "test_failed"  # 测试失败消息类型


@dataclass
class Message:
    """一条类型化消息
    Attributes:
        kind: 消息类型
        by: 发送者角色名（如 "architect", "coder-A")
        to: 接收者角色名（如 "reviewer", "tester")
        payload: 消息负载，结构取决于 kind
        tokens: 这条消息消耗的 Token 数
    """

    kind: MsgKind
    by: str
    to: str
    payload: dict = field(default_factory=dict)
    tokens: int = 0


@dataclass
class Subtask:
    """架构师拆分的子任务
    
    Attributes:
        name: 子任务名称（如 "parser", "cache")
        files: 涉及的文件列表
        lines_changed: 修改的行数（编码者完成后填入）
        has_bug: 是否注入了 bug(用于评测）
    """

    name: str
    files: list[str]
    lines_changed: int = 0
    has_bug: bool = False