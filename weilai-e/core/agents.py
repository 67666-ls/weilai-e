"""四大 Agent 节点：在调用 LLM 前按需挂上工具上下文。"""
from __future__ import annotations

from typing import Callable

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from config.prompts import AGENT_PROMPTS, SYSTEM_PROMPT
from core.llm import make_llm
from core.state import ChatState
from memory.conversation import (
    append_growth,
    load,
    render_profile_prompt,
    save,
    update_profile,
)
from tools import job_matcher, knowledge_search, resume_analyzer


def _last_user_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if getattr(m, "type", "") == "human":
            return getattr(m, "content", "") or ""
    return ""


def _build_messages(state: ChatState, agent_key: str, tool_ctx: str) -> list[BaseMessage]:
    """组装 LLM 输入：主 system + 角色 system + 画像 system + 工具上下文 + 历史。"""
    profile = state.get("profile", {}) or {}
    user_id = state.get("user_id", "anonymous")
    memory = load(user_id)
    update_profile(memory, **profile)
    profile_block = render_profile_prompt(memory)

    sys_blocks: list[str] = [SYSTEM_PROMPT, AGENT_PROMPTS[agent_key]]
    if profile_block:
        sys_blocks.append(profile_block)
    if tool_ctx:
        sys_blocks.append(tool_ctx)
    messages: list[BaseMessage] = [SystemMessage(content="\n\n".join(sys_blocks))]
    messages.extend(state.get("messages", []))
    return messages


def _persist_growth(state: ChatState, agent_key: str, summary: str) -> None:
    user_id = state.get("user_id", "anonymous")
    if not user_id:
        return
    memory = load(user_id)
    update_profile(memory, **(state.get("profile") or {}))
    append_growth(memory, agent_key, summary[:120])
    memory.last_agent = agent_key
    save(memory)


def _make_node(agent_key: str, tool_fn: Callable[[ChatState], str]):
    def node(state: ChatState) -> dict:
        tool_ctx = tool_fn(state)
        messages = _build_messages(state, agent_key, tool_ctx)
        llm = make_llm()
        resp = llm.invoke(messages)
        text = getattr(resp, "content", "") or ""
        ai_msg = AIMessage(content=text)
        _persist_growth(state, agent_key, _last_user_text(state.get("messages", [])))
        return {"messages": [ai_msg], "agent": agent_key, "tools_output": tool_ctx}

    return node


# ------- 各 Agent 工具上下文构造 -------


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


explorer_node = _make_node("explorer", _explorer_tools)
intern_node = _make_node("intern", _intern_tools)
coach_node = _make_node("coach", _coach_tools)
mock_node = _make_node("mock", _mock_tools)


AGENT_NODES = {
    "explorer": explorer_node,
    "intern": intern_node,
    "coach": coach_node,
    "mock": mock_node,
}
