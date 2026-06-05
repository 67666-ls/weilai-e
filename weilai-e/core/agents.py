"""Agent 节点：在调用 LLM 前按需挂上工具上下文，调用后按需解析卡片入库。"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from config.prompts import AGENT_PROMPTS, SYSTEM_PROMPT
from core.llm import make_llm
from core.state import ChatState
from memory.conversation import (
    add_experience,
    add_skill,
    add_struggle,
    add_task,
    append_growth,
    load,
    render_pending_tasks_prompt,
    render_profile_prompt,
    save,
    update_profile,
)
from tools import job_matcher, knowledge_search, resume_analyzer


# ---------- 工具函数 ----------

def _last_user_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if getattr(m, "type", "") == "human":
            return getattr(m, "content", "") or ""
    return ""


def _build_messages(state: ChatState, agent_key: str, tool_ctx: str) -> list[BaseMessage]:
    """组装 LLM 输入：主 system + 角色 system + 画像 system + 上次任务 + 工具上下文 + 历史。"""
    profile = state.get("profile", {}) or {}
    user_id = state.get("user_id", "anonymous")
    memory = load(user_id)
    update_profile(memory, **profile)
    profile_block = render_profile_prompt(memory)
    pending_block = render_pending_tasks_prompt(memory)

    sys_blocks: list[str] = [SYSTEM_PROMPT, AGENT_PROMPTS[agent_key]]
    if profile_block:
        sys_blocks.append(profile_block)
    if pending_block:
        sys_blocks.append(pending_block)
    if tool_ctx:
        sys_blocks.append(tool_ctx)
    messages: list[BaseMessage] = [SystemMessage(content="\n\n".join(sys_blocks))]
    messages.extend(state.get("messages", []))
    return messages


# ---------- <card> 解析与入库 ----------

_CARD_RE = re.compile(r"<card>\s*(\{.*?\})\s*</card>", re.DOTALL)


def _strip_card(text: str) -> str:
    """从 AI 文本里去掉 <card>...</card> 给前端展示。"""
    return _CARD_RE.sub("", text or "").strip()


def _extract_card(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    match = _CARD_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def _ingest_card(memory: Any, card: dict[str, Any], raw_user_text: str) -> bool:
    """把卡片字典写入 memory；返回是否要标记 interview_done。"""
    exp = card.get("experience") or {}
    if isinstance(exp, dict) and (exp.get("title") or exp.get("role") or exp.get("result")):
        add_experience(
            memory,
            period=exp.get("period", ""),
            title=exp.get("title", ""),
            role=exp.get("role", ""),
            result=exp.get("result", ""),
            raw=raw_user_text[:200],
            tags=list(exp.get("tags") or []),
        )
    skills = card.get("skills") or []
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, dict) and s.get("name") and s.get("score") is not None:
                try:
                    add_skill(memory, str(s["name"]), int(s["score"]))
                except Exception:
                    continue
    struggle = card.get("struggle")
    if isinstance(struggle, str) and struggle.strip():
        add_struggle(memory, struggle.strip())
    tasks = card.get("tasks") or []
    if isinstance(tasks, list):
        for t in tasks:
            if isinstance(t, dict) and t.get("text"):
                add_task(
                    memory,
                    text=str(t["text"]).strip(),
                    deadline=str(t.get("deadline", "")).strip(),
                    created_by="interviewer",
                )
    return bool(card.get("interview_done"))


# ---------- 节点工厂 ----------

def _persist(state: ChatState, agent_key: str, ai_text: str, user_text: str) -> tuple[str, dict]:
    """统一的 memory 落库：成长记录 + 卡片解析 + interview_done 标记。

    返回 (清洗过的 ai_text, 额外 state 增量)。
    """
    user_id = state.get("user_id", "anonymous") or "anonymous"
    memory = load(user_id)
    update_profile(memory, **(state.get("profile") or {}))

    card = _extract_card(ai_text) if agent_key == "interviewer" else None
    extra: dict = {}
    if card:
        done = _ingest_card(memory, card, user_text)
        if done:
            memory.interview_done = True
            extra["interview_done"] = True

    summary = (user_text or "").strip()[:120]
    if summary:
        append_growth(memory, agent_key, summary)
    memory.last_agent = agent_key
    save(memory)

    cleaned = _strip_card(ai_text)
    return cleaned, extra


def _make_node(agent_key: str, tool_fn: Callable[[ChatState], str]):
    def node(state: ChatState) -> dict:
        tool_ctx = tool_fn(state)
        messages = _build_messages(state, agent_key, tool_ctx)
        llm = make_llm()
        resp = llm.invoke(messages)
        text = getattr(resp, "content", "") or ""
        cleaned, extra = _persist(state, agent_key, text, _last_user_text(state.get("messages", [])))
        out: dict = {"messages": [AIMessage(content=cleaned)], "agent": agent_key, "tools_output": tool_ctx}
        out.update(extra)
        return out

    return node


# ---------- 各 Agent 工具上下文 ----------

def _interviewer_tools(state: ChatState) -> str:
    """反向访谈不接外部知识库，只把已有素材给 LLM 看以避免重复问。"""
    return ""


def _explorer_tools(state: ChatState) -> str:
    text = _last_user_text(state.get("messages", []))
    chunks = knowledge_search.search(text, k=3) if text else []
    return knowledge_search.render_context(chunks)


def _intern_tools(state: ChatState) -> str:
    text = _last_user_text(state.get("messages", []))
    if not text:
        return ""
    blocks: list[str] = []
    match = job_matcher.recommend(text)
    rendered = job_matcher.render(match)
    if rendered:
        blocks.append(rendered)
    return "\n\n".join(blocks)


def _coach_tools(state: ChatState) -> str:
    text = _last_user_text(state.get("messages", []))
    blocks: list[str] = []
    if "简历" in text or len(text) > 200:
        feedback = resume_analyzer.analyze(text)
        blocks.append(resume_analyzer.render(feedback))
    chunks = knowledge_search.search(text, k=3) if text else []
    rag = knowledge_search.render_context(chunks)
    if rag:
        blocks.append(rag)
    return "\n\n".join(blocks)


def _mock_tools(state: ChatState) -> str:
    text = _last_user_text(state.get("messages", []))
    chunks = knowledge_search.search(text or "面试 题目", k=3)
    return knowledge_search.render_context(chunks)


interviewer_node = _make_node("interviewer", _interviewer_tools)
explorer_node = _make_node("explorer", _explorer_tools)
intern_node = _make_node("intern", _intern_tools)
coach_node = _make_node("coach", _coach_tools)
mock_node = _make_node("mock", _mock_tools)


AGENT_NODES = {
    "interviewer": interviewer_node,
    "explorer": explorer_node,
    "intern": intern_node,
    "coach": coach_node,
    "mock": mock_node,
}
