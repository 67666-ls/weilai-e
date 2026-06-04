"""「未来鹅」Streamlit 入口：sidebar 选画像，主区域多轮对话。"""
from __future__ import annotations

# Streamlit Cloud 系统 sqlite 版本过旧，chromadb 要求 >= 3.35；用 pysqlite3 顶替。
# 必须在任何会触发 chromadb / sqlite3 的 import 之前执行。
try:
    import pysqlite3  # type: ignore
    import sys
    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass

import hashlib
import time

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from config.prompts import AGENT_LABELS
from config.settings import get_settings
from core.graph import get_app
from memory.conversation import (
    load as load_memory,
    render_profile_prompt,
    save as save_memory,
    update_profile,
)


GRADES = ["大一", "大二", "大三", "大四", "研究生"]
INTEREST_OPTIONS = [
    "互联网产品", "算法/AI", "前端", "后台", "客户端",
    "数据", "设计", "运营", "市场", "职能",
]


def _stable_user_id(grade: str, major: str) -> str:
    """根据画像生成稳定 ID，便于跨会话连续。"""
    raw = f"{grade}|{major}".strip("|") or "anonymous"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _init_state() -> None:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []  # list[BaseMessage]
    if "current_agent" not in st.session_state:
        st.session_state.current_agent = ""
    if "profile" not in st.session_state:
        st.session_state.profile = {
            "grade": "",
            "major": "",
            "interests": [],
            "target_roles": [],
            "notes": "",
        }


def _render_sidebar() -> None:
    settings = get_settings()
    with st.sidebar:
        st.title("🪿 未来鹅")
        st.caption("你的腾讯 AI 学长，从大一到毕业全程陪伴")

        st.subheader("我的画像")
        profile = st.session_state.profile
        profile["grade"] = st.selectbox(
            "年级",
            options=[""] + GRADES,
            index=([""] + GRADES).index(profile.get("grade") or ""),
        )
        profile["major"] = st.text_input("专业 / 学校", value=profile.get("major", ""))
        profile["interests"] = st.multiselect(
            "兴趣方向（多选）",
            options=INTEREST_OPTIONS,
            default=profile.get("interests") or [],
        )
        profile["notes"] = st.text_area(
            "想让学长知道的（可选）",
            value=profile.get("notes", ""),
            placeholder="例如：竞赛经历、性格、纠结点……",
            height=80,
        )

        st.divider()
        st.subheader("当前 Agent")
        if st.session_state.current_agent:
            st.success(
                f"{AGENT_LABELS.get(st.session_state.current_agent, st.session_state.current_agent)}"
                f"（{st.session_state.current_agent}）"
            )
        else:
            st.info("尚未路由，发出第一条消息后由 Router 分流")

        st.divider()
        st.subheader("环境")
        if settings.llm_ready:
            st.success(f"LLM 已就绪：{settings.llm_model}")
        else:
            st.warning("LLM Key 未配置，将启用桩模型仅作流程演示")

        st.divider()
        if st.button("🧹 重置当前会话", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.current_agent = ""
            st.rerun()


def _render_history() -> None:
    for msg in st.session_state.chat_history:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        with st.chat_message(role):
            st.markdown(getattr(msg, "content", ""))


def _persist_profile(user_id: str) -> None:
    memory = load_memory(user_id)
    update_profile(memory, **st.session_state.profile)
    save_memory(memory)


def _run_turn(user_text: str) -> None:
    profile = st.session_state.profile
    user_id = _stable_user_id(profile.get("grade", ""), profile.get("major", ""))
    _persist_profile(user_id)

    st.session_state.chat_history.append(HumanMessage(content=user_text))
    with st.chat_message("user"):
        st.markdown(user_text)

    app = get_app()
    payload = {
        "messages": st.session_state.chat_history,
        "user_id": user_id,
        "profile": profile,
    }

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("_思考中…_")
        t0 = time.time()
        try:
            result = app.invoke(payload)
        except Exception as exc:  # 防止单次失败炸掉整个会话
            placeholder.error(f"运行出错：{exc}")
            return

        agent = result.get("agent", "explorer")
        st.session_state.current_agent = agent

        last_ai: AIMessage | None = None
        for m in result.get("messages", [])[::-1]:
            if isinstance(m, AIMessage):
                last_ai = m
                break

        if last_ai is None:
            placeholder.warning("未拿到回复，请重试。")
            return

        elapsed = time.time() - t0
        header = (
            f"**{AGENT_LABELS.get(agent, agent)}**"
            f" · 用时 {elapsed:.1f}s"
        )
        placeholder.markdown(f"{header}\n\n{last_ai.content}")
        st.session_state.chat_history.append(last_ai)


def main() -> None:
    st.set_page_config(page_title="未来鹅 · 腾讯 AI 学长", page_icon="🪿", layout="wide")
    _init_state()
    _render_sidebar()

    st.markdown("### 我是「未来鹅」🪿，从大一到毕业陪你聊聊职业这件事")
    profile_block = render_profile_prompt(
        load_memory(
            _stable_user_id(
                st.session_state.profile.get("grade", ""),
                st.session_state.profile.get("major", ""),
            )
        )
    )
    if profile_block:
        with st.expander("当前画像与近期成长记录", expanded=False):
            st.markdown(profile_block)

    _render_history()

    user_text = st.chat_input("说点什么吧，比如：大三想找产品实习，该怎么准备？")
    if user_text:
        _run_turn(user_text.strip())


if __name__ == "__main__":
    main()
