"""对话记忆与用户成长档案：本地 JSON 存储，支持跨会话连续性。"""
from __future__ import annotations

import json
import time
import uuid
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
class ExperienceCard:
    """经历卡：来自反向访谈的素材沉淀，可直接转 STAR。"""

    ts: float
    period: str = ""       # "大二·暑假" / "课程项目"
    title: str = ""        # 一句话标题
    role: str = ""         # 我担任什么
    result: str = ""       # 结果/收获
    raw: str = ""          # 学生原话（节选）
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class SkillCard:
    """能力卡：从经历提炼的能力评分（1-5）。"""

    name: str              # "项目推动" / "数据分析"
    score: int             # 1-5
    evidence: list[str] = field(default_factory=list)  # 关联 experience.id
    ts: float = 0.0


@dataclass
class StruggleCard:
    """纠结卡：学生表达的焦虑/犹豫。"""

    ts: float
    content: str           # "想做产品但担心非科班背景"
    resolved: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class ActionTask:
    """Next Step 行动卡：跨会话追踪。"""

    ts: float
    text: str              # "把简历项目部分按 STAR 重写一版"
    deadline: str = ""     # "本周日" / "2026-06-08"
    status: str = "pending"  # pending / done / skipped
    created_by: str = ""   # agent 名
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class ConversationMemory:
    user_id: str
    profile: UserProfile = field(default_factory=UserProfile)
    growth: list[GrowthRecord] = field(default_factory=list)
    last_agent: str = ""
    experiences: list[ExperienceCard] = field(default_factory=list)
    skills: list[SkillCard] = field(default_factory=list)
    struggles: list[StruggleCard] = field(default_factory=list)
    tasks: list[ActionTask] = field(default_factory=list)
    interview_done: bool = False  # 反向访谈是否已结束（达到轮数或学生喊停）

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "profile": asdict(self.profile),
            "growth": [asdict(g) for g in self.growth],
            "last_agent": self.last_agent,
            "experiences": [asdict(e) for e in self.experiences],
            "skills": [asdict(s) for s in self.skills],
            "struggles": [asdict(s) for s in self.struggles],
            "tasks": [asdict(t) for t in self.tasks],
            "interview_done": self.interview_done,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationMemory":
        profile = UserProfile(**data.get("profile", {}))
        growth = [GrowthRecord(**g) for g in data.get("growth", [])]
        experiences = [ExperienceCard(**e) for e in data.get("experiences", [])]
        skills = [SkillCard(**s) for s in data.get("skills", [])]
        struggles = [StruggleCard(**s) for s in data.get("struggles", [])]
        tasks = [ActionTask(**t) for t in data.get("tasks", [])]
        return cls(
            user_id=data["user_id"],
            profile=profile,
            growth=growth,
            last_agent=data.get("last_agent", ""),
            experiences=experiences,
            skills=skills,
            struggles=struggles,
            tasks=tasks,
            interview_done=data.get("interview_done", False),
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


# ---------- 素材卡管理 ----------

def add_experience(memory: ConversationMemory, **kwargs: Any) -> ExperienceCard:
    card = ExperienceCard(ts=kwargs.pop("ts", time.time()), **kwargs)
    memory.experiences.append(card)
    if len(memory.experiences) > 30:
        memory.experiences = memory.experiences[-30:]
    return card


def add_skill(memory: ConversationMemory, name: str, score: int, evidence: list[str] | None = None) -> SkillCard:
    """同名技能存在则更新分数与 evidence，否则新增。"""
    score = max(1, min(5, int(score)))
    for s in memory.skills:
        if s.name == name:
            s.score = score
            if evidence:
                s.evidence = list(dict.fromkeys((s.evidence or []) + evidence))
            s.ts = time.time()
            return s
    card = SkillCard(name=name, score=score, evidence=evidence or [], ts=time.time())
    memory.skills.append(card)
    return card


def add_struggle(memory: ConversationMemory, content: str) -> StruggleCard:
    card = StruggleCard(ts=time.time(), content=content)
    memory.struggles.append(card)
    if len(memory.struggles) > 20:
        memory.struggles = memory.struggles[-20:]
    return card


# ---------- Next Step 任务管理 ----------

def add_task(memory: ConversationMemory, text: str, deadline: str = "", created_by: str = "") -> ActionTask:
    task = ActionTask(ts=time.time(), text=text, deadline=deadline, created_by=created_by)
    memory.tasks.append(task)
    if len(memory.tasks) > 30:
        memory.tasks = memory.tasks[-30:]
    return task


def mark_task(memory: ConversationMemory, task_id: str, status: str) -> bool:
    for t in memory.tasks:
        if t.id == task_id:
            t.status = status
            return True
    return False


def pending_tasks(memory: ConversationMemory, limit: int = 5) -> list[ActionTask]:
    return [t for t in memory.tasks if t.status == "pending"][-limit:]


# ---------- 渲染：给 LLM 用 ----------

def render_profile_prompt(memory: ConversationMemory) -> str:
    """渲染为可拼进 system 的画像段落。"""
    p = memory.profile
    lines = ["# 学生画像"]
    if p.grade:
        lines.append(f"- 年级:{p.grade}")
    if p.major:
        lines.append(f"- 专业:{p.major}")
    if p.interests:
        lines.append(f"- 兴趣:{', '.join(p.interests)}")
    if p.target_roles:
        lines.append(f"- 目标岗位:{', '.join(p.target_roles)}")
    if p.notes:
        lines.append(f"- 备注:{p.notes}")
    if memory.experiences:
        lines.append("# 经历卡（来自反向访谈）")
        for e in memory.experiences[-5:]:
            seg = f"- [{e.period or '未注'}] {e.title or e.raw[:30]}"
            if e.role:
                seg += f" / 角色:{e.role}"
            if e.result:
                seg += f" / 结果:{e.result}"
            lines.append(seg)
    if memory.skills:
        lines.append("# 能力评分（学生自评+访谈推断,1-5）")
        for s in memory.skills:
            lines.append(f"- {s.name}: {'⭐' * s.score}")
    if memory.struggles:
        unresolved = [s for s in memory.struggles if not s.resolved][-3:]
        if unresolved:
            lines.append("# 待解的纠结点")
            for s in unresolved:
                lines.append(f"- {s.content}")
    if memory.growth:
        recent = memory.growth[-3:]
        lines.append("# 近期成长记录")
        for g in recent:
            lines.append(f"- [{g.agent}] {g.summary}")
    return "\n".join(lines) if len(lines) > 1 else ""


def render_pending_tasks_prompt(memory: ConversationMemory) -> str:
    """跨会话追问：把上次定的任务塞进 system，AI 第一句就能追。"""
    todos = pending_tasks(memory, limit=5)
    if not todos:
        return ""
    lines = ["# 学生上次定下还没完成的事（请主动追问进度）"]
    for t in todos:
        seg = f"- {t.text}"
        if t.deadline:
            seg += f"（截止 {t.deadline}）"
        lines.append(seg)
    return "\n".join(lines)


# ---------- 渲染：给前端用 ----------

def render_profile_view(memory: ConversationMemory) -> str:
    p = memory.profile
    if not any([p.grade, p.major, p.interests, p.target_roles, p.notes]):
        return ""
    lines = []
    if p.grade:
        lines.append(f"- **年级**:{p.grade}")
    if p.major:
        lines.append(f"- **专业 / 学校**:{p.major}")
    if p.interests:
        lines.append(f"- **兴趣方向**:{', '.join(p.interests)}")
    if p.target_roles:
        lines.append(f"- **目标岗位**:{', '.join(p.target_roles)}")
    if p.notes:
        lines.append(f"- **备注**:{p.notes}")
    if memory.last_agent:
        lines.append(f"- **上次会话由**:{memory.last_agent}")
    return "\n".join(lines)


def render_full_history(memory: ConversationMemory) -> str:
    if not memory.growth:
        return ""
    from datetime import datetime
    from config.prompts import AGENT_LABELS

    lines = []
    for g in reversed(memory.growth):
        when = datetime.fromtimestamp(g.ts).strftime("%Y-%m-%d %H:%M")
        agent_label = AGENT_LABELS.get(g.agent, g.agent)
        lines.append(f"- `{when}` · **{agent_label}**:{g.summary}")
    return "\n".join(lines)


def render_cards_view(memory: ConversationMemory) -> str:
    """素材卡 tab：经历 + 能力 + 纠结。"""
    if not (memory.experiences or memory.skills or memory.struggles):
        return ""
    lines: list[str] = []
    if memory.experiences:
        lines.append("#### 📌 经历卡")
        for e in reversed(memory.experiences):
            head = f"**{e.title or e.raw[:30]}**"
            if e.period:
                head = f"`{e.period}` " + head
            lines.append(f"- {head}")
            sub = []
            if e.role:
                sub.append(f"角色:{e.role}")
            if e.result:
                sub.append(f"结果:{e.result}")
            if e.tags:
                sub.append("标签:" + " / ".join(e.tags))
            if sub:
                lines.append("  " + " · ".join(sub))
    if memory.skills:
        lines.append("\n#### 🎯 能力卡")
        for s in memory.skills:
            lines.append(f"- **{s.name}**:{'⭐' * s.score}{'☆' * (5 - s.score)}")
    if memory.struggles:
        lines.append("\n#### 💭 纠结卡")
        for s in reversed(memory.struggles):
            mark = "✅" if s.resolved else "⏳"
            lines.append(f"- {mark} {s.content}")
    return "\n".join(lines)


def clear_history(memory: ConversationMemory) -> None:
    """清空成长记录但保留画像。"""
    memory.growth = []
    memory.last_agent = ""
    save(memory)
