"""配置管理：本地 .env / Streamlit Secrets 双通道。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_secret(key: str, default: str = "") -> str:
    """优先读 Streamlit Secrets，再回落到环境变量。

    Streamlit 不在运行时不影响本地脚本调用。
    """
    try:  # pragma: no cover - 依赖运行环境
        import streamlit as st  # type: ignore

        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


@dataclass
class Settings:
    llm_api_key: str = field(default_factory=lambda: _read_secret("LLM_API_KEY", ""))
    llm_base_url: str = field(
        default_factory=lambda: _read_secret("LLM_BASE_URL", "https://api.openai.com/v1")
    )
    llm_model: str = field(default_factory=lambda: _read_secret("LLM_MODEL", "gpt-4o-mini"))
    llm_temperature: float = field(
        default_factory=lambda: float(_read_secret("LLM_TEMPERATURE", "0.7"))
    )

    embedding_model: str = field(
        default_factory=lambda: _read_secret("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    )

    knowledge_base_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT
        / _read_secret("KNOWLEDGE_BASE_DIR", "data/knowledge_base")
    )
    vector_store_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT
        / _read_secret("VECTOR_STORE_DIR", "data/vector_store")
    )
    memory_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / _read_secret("MEMORY_DIR", "memory/store")
    )

    def ensure_dirs(self) -> None:
        for p in (self.knowledge_base_dir, self.vector_store_dir, self.memory_dir):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_api_key)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
