"""LangGraph 工作流装配：router → 条件分支 → agent → END。"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from core.agents import AGENT_NODES
from core.router import route, select_branch
from core.state import ChatState


def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("router", route)
    for name, node in AGENT_NODES.items():
        graph.add_node(name, node)

    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        select_branch,
        {name: name for name in AGENT_NODES},
    )
    for name in AGENT_NODES:
        graph.add_edge(name, END)
    return graph.compile()


_compiled = None


def get_app():
    """惰性构建并缓存，避免 Streamlit 每次 rerun 重复编译。"""
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled
