"""对话记忆与用户成长档案：本地 JSON 存储，支持跨会话连续性。"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.settings import get_settings


@dataclass
class UserProfile:
    """学生画像：进入产品时收集，对话中持续补全。"""

    grade: str = ""  # 大一/大二/大三/大四/研究生
    major: str = ""
    interests: list[str] = field(default_factory=list)
    target_roles: list[str] = field(default_factory=list)
    notes: str = ""  # 自由备注：竞赛/实习/性格特点


@dataclass
class GrowthRecord:
    """成长档案条目：用于跨会话累积。"""

    ts: float
    agent: str
    summary: str


@dataclass
class ConversationMemory:
    user_id: str
    profile: UserProfile = field(default_factory=UserProfile)
    growth: list[GrowthRecord] = field(default_factory=list)
    last_agent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "profile": asdict(self.profile),
            "growth": [asdict(g) for g in self.growth],
            "last_agent": self.last_agent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationMemory":
        profile = UserProfile(**data.get("profile", {}))
        growth = [GrowthRecord(**g) for g in data.get("growth", [])]
        return cls(
            user_id=data["user_id"],
            profile=profile,
            growth=growth,
            last_agent=data.get("last_agent", ""),
        )


def _store_path(user_id: str) -> Path:
    settings = get_settings()
    safe = "".join(c for c in user_id if c.isalnum() or c in ("_", "-")) or "anonymous"
    return settings.memory_dir / f"{safe}.json"


def load(user_id: str) -> ConversationMemory:
    path = _store_path(user_id)
    if not path.exists():
        return ConversationMemory(user_id=user_id)
    try:
        return ConversationMemory.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return ConversationMemory(user_id=user_id)


def save(memory: ConversationMemory) -> None:
    path = _store_path(memory.user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(memory.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_growth(memory: ConversationMemory, agent: str, summary: str) -> None:
    memory.growth.append(GrowthRecord(ts=time.time(), agent=agent, summary=summary))
    if len(memory.growth) > 50:
        memory.growth = memory.growth[-50:]


def update_profile(memory: ConversationMemory, **patch: Any) -> None:
    for k, v in patch.items():
        if hasattr(memory.profile, k) and v not in (None, "", []):
            setattr(memory.profile, k, v)


def render_profile_prompt(memory: ConversationMemory) -> str:
    """渲染为可拼进 system 的画像段落。"""
    p = memory.profile
    lines = ["# 学生画像"]
    if p.grade:
        lines.append(f"- 年级：{p.grade}")
    if p.major:
        lines.append(f"- 专业：{p.major}")
    if p.interests:
        lines.append(f"- 兴趣：{', '.join(p.interests)}")
    if p.target_roles:
        lines.append(f"- 目标岗位：{', '.join(p.target_roles)}")
    if p.notes:
        lines.append(f"- 备注：{p.notes}")
    if memory.growth:
        recent = memory.growth[-3:]
        lines.append("# 近期成长记录")
        for g in recent:
            lines.append(f"- [{g.agent}] {g.summary}")
    return "\n".join(lines) if len(lines) > 1 else ""


def render_profile_view(memory: ConversationMemory) -> str:
    """给主区域用的人类可读画像渲染（不进 prompt）。"""
    p = memory.profile
    if not any([p.grade, p.major, p.interests, p.target_roles, p.notes]):
        return ""
    lines = []
    if p.grade:
        lines.append(f"- **年级**：{p.grade}")
    if p.major:
        lines.append(f"- **专业 / 学校**：{p.major}")
    if p.interests:
        lines.append(f"- **兴趣方向**：{', '.join(p.interests)}")
    if p.target_roles:
        lines.append(f"- **目标岗位**：{', '.join(p.target_roles)}")
    if p.notes:
        lines.append(f"- **备注**：{p.notes}")
    if memory.last_agent:
        lines.append(f"- **上次会话由**：{memory.last_agent}")
    return "\n".join(lines)


def render_full_history(memory: ConversationMemory) -> str:
    """渲染全部成长记录（按时间倒序），不进 prompt，仅给前端展示。"""
    if not memory.growth:
        return ""
    from datetime import datetime
    from config.prompts import AGENT_LABELS

    lines = []
    for g in reversed(memory.growth):
        when = datetime.fromtimestamp(g.ts).strftime("%Y-%m-%d %H:%M")
        agent_label = AGENT_LABELS.get(g.agent, g.agent)
        lines.append(f"- `{when}` · **{agent_label}**：{g.summary}")
    return "\n".join(lines)


def clear_history(memory: ConversationMemory) -> None:
    """清空成长记录但保留画像。"""
    memory.growth = []
    memory.last_agent = ""
    save(memory)
