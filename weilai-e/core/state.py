"""共享会话状态：作为 LangGraph 节点之间的载体。"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class ChatState(TypedDict, total=False):
    """LangGraph 状态。

    - messages: LangChain BaseMessage 列表，使用 add_messages 累加；
    - user_id: 用于读写持久化的成长档案；
    - profile: 学生画像（grade/major/interests/...），由 sidebar 注入；
    - agent: 当前/目标 Agent 名（explorer/intern/coach/mock）；
    - tools_output: 工具运行后注入到 Agent 系统提示中的"工具上下文"；
    - tool_request: 路由器或 Agent 显式声明本轮需要的工具列表。
    """

    messages: Annotated[list, add_messages]
    user_id: str
    profile: dict[str, Any]
    agent: str
    tools_output: str
    tool_request: list[str]
