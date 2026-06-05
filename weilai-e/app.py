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
    ConversationMemory,
    clear_history,
    load as load_memory,
    mark_task,
    pending_tasks,
    render_cards_view,
    render_full_history,
    render_profile_prompt,
    render_profile_view,
    save as save_memory,
    update_profile,
)


GRADES = ["大一", "大二", "大三", "大四", "研一", "研二", "研三"]
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
        st.caption("你的求职贴心学长，从大一到毕业全程陪伴")

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


def _render_action_board(memory: ConversationMemory) -> None:
    """今日行动板:展示 pending 任务,带完成/跳过按钮。"""
    todos = pending_tasks(memory, limit=5)
    with st.container(border=True):
        cols = st.columns([4, 1])
        cols[0].markdown("#### 🎯 今日行动板")
        if not todos:
            cols[1].caption(" ")
            st.caption("还没有目标,去聊一聊学长会帮你定。")
            return
        cols[1].caption(f"待办 {len(todos)}")
        for task in todos:
            line = st.columns([6, 1, 1])
            head = f"☐ **{task.text}**"
            if task.deadline:
                head += f" · `截止 {task.deadline}`"
            if task.created_by:
                head += f" · _by {AGENT_LABELS.get(task.created_by, task.created_by)}_"
            line[0].markdown(head)
            if line[1].button("✅ 完成", key=f"task_done_{task.id}", use_container_width=True):
                mark_task(memory, task.id, "done")
                save_memory(memory)
                st.toast("已标记为完成 ✅")
                st.rerun()
            if line[2].button("⏭️ 跳过", key=f"task_skip_{task.id}", use_container_width=True):
                mark_task(memory, task.id, "skipped")
                save_memory(memory)
                st.toast("已跳过 ⏭️")
                st.rerun()


# 雷达图维度，与 INTERVIEWER_PROMPT 抽取的能力名对齐
_RADAR_DIMS = ["项目推动", "数据分析", "沟通表达", "技术深度", "行业认知", "抗压"]

# 目标岗位的"要求雷达"内置一份兜底，后续可由 router/intern agent 写入 memory
_ROLE_REQUIREMENTS = {
    "产品": [4, 4, 5, 2, 5, 4],
    "后端": [4, 3, 3, 5, 3, 4],
    "前端": [4, 2, 3, 4, 3, 3],
    "算法": [3, 5, 3, 5, 4, 4],
    "数据": [3, 5, 4, 4, 4, 3],
    "运营": [4, 4, 5, 1, 5, 4],
    "设计": [3, 2, 4, 3, 4, 3],
}


def _student_skill_vector(memory: ConversationMemory) -> list[int]:
    """memory.skills 拍平到 6 维。命中名取分；没命中给 0（保留'空雷达'的真实感）。"""
    by_name = {s.name: s.score for s in memory.skills}
    return [int(by_name.get(d, 0)) for d in _RADAR_DIMS]


def _match_role_vector(target_roles: list[str]) -> tuple[str, list[int]] | None:
    if not target_roles:
        return None
    for role in target_roles:
        for key, vec in _ROLE_REQUIREMENTS.items():
            if key in role:
                return role, vec
    return None


def _render_radar(memory: ConversationMemory) -> None:
    if not memory.skills:
        st.caption("还没沉淀能力评分。让反向访谈官帮你聊几轮，雷达就长出来了。")
        return
    try:
        import plotly.graph_objects as go  # 延迟导入，plotly 未装时不要让整个 app 崩
    except ImportError:
        st.warning("还没装 `plotly`，先用纯文本展示能力评分。")
        for s in memory.skills:
            st.markdown(f"- **{s.name}**：{'⭐' * s.score}{'☆' * (5 - s.score)}")
        return

    student_vec = _student_skill_vector(memory)
    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=student_vec + student_vec[:1],
            theta=_RADAR_DIMS + _RADAR_DIMS[:1],
            fill="toself",
            name="我的能力",
            line=dict(color="#5B8DEF"),
        )
    )

    role_match = _match_role_vector(memory.profile.target_roles or [])
    if role_match is None:
        role_match = _match_role_vector(memory.profile.interests or [])
    if role_match:
        role, role_vec = role_match
        fig.add_trace(
            go.Scatterpolar(
                r=role_vec + role_vec[:1],
                theta=_RADAR_DIMS + _RADAR_DIMS[:1],
                fill="toself",
                name=f"{role} 岗位要求",
                line=dict(color="#F39C12", dash="dot"),
                opacity=0.6,
            )
        )

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5], tickvals=[1, 2, 3, 4, 5])),
        showlegend=True,
        height=420,
        margin=dict(l=40, r=40, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    if not role_match:
        st.caption("提示：在侧边栏选「兴趣方向」或填目标岗位，可以叠加岗位的'要求雷达'看差距。")


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

        ai_content = (last_ai.content or "").strip()
        if not ai_content:
            ai_content = "_(模型本轮没有返回内容，可能 LLM Key 失效或被请求方限流，请重试)_"
            last_ai = AIMessage(content=ai_content)

        elapsed = time.time() - t0
        header = (
            f"**{AGENT_LABELS.get(agent, agent)}**"
            f" · 用时 {elapsed:.1f}s"
        )
        placeholder.markdown(f"{header}\n\n{ai_content}")
        st.session_state.chat_history.append(last_ai)


def main() -> None:
    st.set_page_config(page_title="未来鹅 · 求职贴心学长", page_icon="🪿", layout="wide")
    _init_state()
    _render_sidebar()

    st.markdown("### 我是「未来鹅」🪿，求职路上的贴心学长，从大一到毕业陪你聊职业")

    user_id = _stable_user_id(
        st.session_state.profile.get("grade", ""),
        st.session_state.profile.get("major", ""),
    )
    memory = load_memory(user_id)

    _render_action_board(memory)

    profile_view = render_profile_view(memory)
    history_view = render_full_history(memory)
    cards_view = render_cards_view(memory)
    has_radar = bool(memory.skills)

    if profile_view or history_view or cards_view or has_radar:
        with st.expander("📒 我的画像 & 成长记录", expanded=False):
            tab_profile, tab_history, tab_cards, tab_radar = st.tabs(
                [
                    "🪪 当前画像",
                    f"📜 成长记录（{len(memory.growth)}）",
                    f"📋 素材卡（{len(memory.experiences)}/{len(memory.skills)}/{len(memory.struggles)}）",
                    "📈 能力雷达",
                ]
            )
            with tab_profile:
                if profile_view:
                    st.markdown(profile_view)
                else:
                    st.caption("还没填画像，去左边侧边栏填一下年级和专业吧。")
            with tab_history:
                if history_view:
                    st.markdown(history_view)
                    if st.button("🗑️ 清空成长记录", key="clear_growth"):
                        clear_history(memory)
                        st.success("已清空，刷新看看。")
                        st.rerun()
                else:
                    st.caption("还没有对话记录。聊几句之后会自动记下来。")
            with tab_cards:
                if cards_view:
                    st.markdown(cards_view)
                else:
                    st.caption("还没有素材。和反向访谈官聊几句，经历/能力/纠结会自动沉淀成卡片。")
            with tab_radar:
                _render_radar(memory)

    _render_history()

    user_text = st.chat_input("说点什么吧，比如：大三想找产品实习，可以投哪些公司？")
    if user_text:
        _run_turn(user_text.strip())


if __name__ == "__main__":
    main()
