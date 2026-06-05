"""路由 Agent：根据画像 + 最新一句话决定 interviewer/explorer/intern/coach/mock。

策略：
1. 用户消息显式触发关键词时直接命中（interviewer/mock/coach/intern 优先级高于年级默认值）；
2. 首次进入（memory 里既无经历卡又未完成访谈）→ interviewer 主动开访谈；
3. 没显式信号时，按年级落到默认 Agent；
4. LLM 兜底（仅在配置了 Key 且依赖可用时启用），返回 JSON。
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from config.prompts import ROUTER_PROMPT
from core.llm import StubLLM, make_llm
from core.state import ChatState
from memory.conversation import load as load_memory


_GRADE_DEFAULT = {
    "大一": "explorer",
    "大二": "intern",
    "大三": "intern",
    "大四": "coach",
    "研究生": "intern",  # 兼容旧档案,默认按研一处理
    "研一": "intern",
    "研二": "coach",
    "研三": "coach",
}


_KEYWORD_RULES = [
    # 强信号:任何年级都直接命中
    ("interviewer", ("帮我做画像", "盘一下我自己", "采访我", "认识我", "聊聊我自己")),
    ("mock", ("模拟面试", "面试陪练", "面我", "出题", "压力面", "群面")),
    ("coach", ("秋招", "春招", "offer", "时间线", "笔试")),
    ("intern", ("作品集", "暑期", "日常实习", "内推")),
    ("explorer", ("迷茫", "选方向", "不知道", "什么岗位", "什么专业", "兴趣")),
]

# 弱信号:命中"简历"时,大四/研究生 → coach,低年级 → intern。
# "实习"单独出现时一律视为 intern（秋招用户多半已被上面的强信号截胡）。
_RESUME_KW = ("简历",)
_INTERN_WEAK = ("实习",)
_SENIOR_GRADES = {"大四", "研究生", "研二", "研三"}


def _last_user_text(state: ChatState) -> str:
    for m in reversed(state.get("messages", [])):
        if getattr(m, "type", "") == "human":
            return getattr(m, "content", "") or ""
    return ""


def _rule_based(state: ChatState) -> str | None:
    text = _last_user_text(state)
    text_l = text.lower()
    profile = state.get("profile", {}) or {}
    grade = profile.get("grade", "")
    for agent, kws in _KEYWORD_RULES:
        if any(kw.lower() in text_l for kw in kws):
            return agent
    # 弱信号:简历相关由年级决定
    if any(kw in text for kw in _RESUME_KW):
        return "coach" if grade in _SENIOR_GRADES else "intern"
    if any(kw in text for kw in _INTERN_WEAK):
        return "intern"
    # 首次进入:没经历卡 + 没结束过访谈 → 主动开反向访谈
    if _is_first_time(state):
        return "interviewer"
    if grade in _GRADE_DEFAULT:
        return _GRADE_DEFAULT[grade]
    return None


def _is_first_time(state: ChatState) -> bool:
    """判断是否第一次进来:既无经历卡也未完成过访谈。

    读 memory 而非 state——state 里只有当前轮次的临时字段,持久化标记在 memory 里。
    """
    user_id = state.get("user_id") or "anonymous"
    try:
        memory = load_memory(user_id)
    except Exception:
        return False
    if memory.interview_done:
        return False
    if memory.experiences:
        return False
    return True


def _llm_route(state: ChatState) -> str:
    llm = make_llm(temperature=0)
    if isinstance(llm, StubLLM):
        return "explorer"
    text = _last_user_text(state)
    profile = state.get("profile", {}) or {}
    sys = SystemMessage(content=ROUTER_PROMPT)
    usr = HumanMessage(
        content=(
            f"画像：{json.dumps(profile, ensure_ascii=False)}\n"
            f"最新一句：{text}\n"
            "请按规范返回 JSON。"
        )
    )
    try:
        resp = llm.invoke([sys, usr])
        content = getattr(resp, "content", "") or ""
        match = re.search(r"\{[^{}]*\}", content)
        if match:
            data = json.loads(match.group(0))
            agent = str(data.get("agent", "")).strip()
            if agent in {"interviewer", "explorer", "intern", "coach", "mock"}:
                return agent
    except Exception:
        pass
    return "explorer"


def route(state: ChatState) -> dict:
    """LangGraph 节点函数：返回新 state 增量。"""
    chosen = _rule_based(state) or _llm_route(state)
    return {"agent": chosen}


def select_branch(state: ChatState) -> str:
    """conditional_edges 用：返回当前 agent 名作为下一节点 key。"""
    return state.get("agent") or "explorer"
