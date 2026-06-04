"""配置模块导出。"""
from .prompts import (
    AGENT_LABELS,
    AGENT_PROMPTS,
    ROUTER_PROMPT,
    SYSTEM_PROMPT,
)
from .settings import Settings, get_settings

__all__ = [
    "AGENT_LABELS",
    "AGENT_PROMPTS",
    "ROUTER_PROMPT",
    "SYSTEM_PROMPT",
    "Settings",
    "get_settings",
]
