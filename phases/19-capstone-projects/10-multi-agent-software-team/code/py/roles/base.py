"""角色基类 — 所有角色的统一接口

每个角色（架构师/编码者/评审者/测试者）都继承这个基类。
基类提供：
- call_llm(): 统一的 LLM 调用 + Token 记账 + 重试
- run(): 抽象方法，子类必须实现自己的逻辑

设计原则：
- 所有角色共用同一个 LLM 调用逻辑
- Token 消耗自动跟踪
- 子类只需关注自己的提示词和输出解析
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from board import Board

import openai

@dataclass
class Role(ABC): #ABC的作用是让类变成抽象类，不能被实例化
    """所有角色的基类

    Attributes:
        name: 角色名称，如 "architect", "coder-A", "reviewer"
        model: 使用的模型名称
        client: OpenAI 客户端实例
        max_tokens_budget: 该角色的 Token 上限
        tokens_used: 已消耗的 Token 数（自动累加）
    """
   
    name: str
    model: str
    client: openai.OpenAI
    max_tokens_budget: int = 50_000
    tokens_used: int = 0

    def call_llm(self, system_prompt: str, user_msg: str) -> dict:
        """统一的 LLM 调用封装

        做三件事：
        1. 调用 API(带 3 次重试）
        2. 解析 JSON 响应
        3. 记录 Token 消耗

        Args:
            system_prompt: 系统提示词（定义角色行为）
            user_msg: 用户消息（当前任务上下文）

        Returns:
            模型返回的 JSON 字典
        """
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    timeout=120, # 超时时间（复杂任务需要更长时间）
                )
                content = response.choices[0].message.content

                if response.usage:
                    tokens = response.usage.total_tokens
                else:
                    tokens = 0

                self.tokens_used += tokens
                return json.loads(content)
            except json.JSONDecodeError as e:
                # 处理 JSON 解析错误（如日志中的 Invalid \escape）
                print(f"[{self.name}] JSON parse failed: {e}")
                return {"error": "json_parse_failed", "raw": content or ""}
            except Exception as e:
                print(f"[{self.name}] Attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                else:
                    # 关键修改：重试耗尽时，返回错误字典而非抛出异常
                    print(f"[{self.name}] All retries exhausted. Returning error state.")
                    return {"error": "llm_timeout", "detail": str(e)}
                
    

    @abstractmethod
    def run(self, board:Board) -> None:
        """运行角色逻辑：从 board 读取消息 → 处理 → 写回结果
        子类必须实现这个方法。
        """
        raise NotImplementedError("子类必须实现该方法")

