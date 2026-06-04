"""LLM 客户端工厂：兼容 OpenAI 协议的统一封装，支持降级到桩模型。"""
from __future__ import annotations

from typing import Any

from config.settings import get_settings


def make_llm(temperature: float | None = None, **kwargs: Any):
    """返回 LangChain LLM。无 Key 时返回 StubLLM，确保 Demo 可跑通。"""
    settings = get_settings()
    if not settings.llm_ready:
        return StubLLM()

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return StubLLM()

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature if temperature is None else temperature,
        **kwargs,
    )


class StubLLM:
    """无 API Key 时的兜底：把 system + 最近一条 user 拼成回声答案。

    目的是让本地开发者在没有 LLM 凭据时也能体验整个图的数据流。
    """

    def invoke(self, messages):  # noqa: ANN001 - 兼容 LangChain 调用约定
        from langchain_core.messages import AIMessage

        sys_text = ""
        last_user = ""
        for m in messages:
            role = getattr(m, "type", "")
            content = getattr(m, "content", "")
            if role == "system":
                sys_text = content
            elif role == "human":
                last_user = content
        snippet = (sys_text or "").splitlines()[:1]
        agent_hint = snippet[0][:40] if snippet else "未来鹅"
        body = (
            "（当前未配置 LLM Key，以下为占位回复）\n"
            f"角色：{agent_hint}\n"
            f"我收到了你的问题：{last_user}\n"
            "建议：1) 在 .env 配置 LLM_API_KEY；2) 重启 Streamlit 后体验完整对话。"
        )
        return AIMessage(content=body)

    async def ainvoke(self, messages):  # noqa: ANN001
        return self.invoke(messages)

    def stream(self, messages):  # noqa: ANN001
        yield self.invoke(messages)
