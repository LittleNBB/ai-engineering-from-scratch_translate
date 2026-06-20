"""全局配置 — LLM 客户端 + 环境变量 + 模型选择

这个文件是整个项目的配置中心。所有需要 LLM 客户端的模块
都从这里导入，而不是各自重复配置。

设计原则：
- 配置只加载一次
- .env 文件从项目根目录向上查找
- 模型名称和预算都有合理的默认值
"""

from __future__ import annotations 

import os
from pathlib import Path
import openai

def load_dotenv() -> None:
    """从当前文件向上查找 .env 文件并加载环境变量
    
    查找顺序：
    1. 从 code/py/ 开始
    2. 向上逐级查找 .env
    3. 找到就加载，找不到就跳过
    """
    path = Path(__file__).resolve().parent 
    while True:
        env_path = path / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue # 忽略空行和注释
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
            return
        parent = path.parent
        if parent == path:
            return # 到达根目录，找不到 .env 文件
        path = parent

load_dotenv()

# LLM 客户端 — 所有角色共用
client = openai.OpenAI(
    api_key=os.environ.get("MIMO_API_KEY", ""),
    base_url=os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"),
)
# 默认模型名称
DEFAULT_MODEL = os.environ.get("MIMO_SB", "mimo-v2.5")

# 预算上限
DEFAULT_MAX_TURNS = 50          # 每角色最大轮次
DEFAULT_MAX_TOKENS = 50_000     # 每角色最大 Token
