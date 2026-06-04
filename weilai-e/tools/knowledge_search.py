"""基于 ChromaDB 的本地 RAG 检索。

设计要点：
1. 启动时若向量库为空，自动从 knowledge_base 目录加载并建索引；
2. 嵌入模型默认使用本地 sentence-transformers，避免依赖外部 API；
3. 提供轻量降级路径：当依赖缺失或模型加载失败时，退化到关键词检索。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from config.settings import get_settings


_CHUNK_SIZE = 600
_CHUNK_OVERLAP = 80


def _read_corpus() -> list[tuple[str, str]]:
    """读取知识库 markdown，返回 (source, text)。"""
    settings = get_settings()
    docs: list[tuple[str, str]] = []
    if not settings.knowledge_base_dir.exists():
        return docs
    for path in sorted(settings.knowledge_base_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        docs.append((path.name, text))
    return docs


def _split(text: str) -> list[str]:
    """按段落聚合到目标长度，避免破坏 markdown 段落语义。"""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if not buf:
            buf = p
        elif len(buf) + len(p) + 2 <= _CHUNK_SIZE:
            buf = f"{buf}\n\n{p}"
        else:
            chunks.append(buf)
            tail = buf[-_CHUNK_OVERLAP:] if _CHUNK_OVERLAP else ""
            buf = f"{tail}\n\n{p}" if tail else p
    if buf:
        chunks.append(buf)
    return chunks


class _KeywordIndex:
    """无依赖的兜底实现：倒排关键词命中。"""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str]] = []  # (source, chunk_id, text)

    def add(self, source: str, chunks: Iterable[str]) -> None:
        for i, c in enumerate(chunks):
            self.entries.append((source, f"{source}#{i}", c))

    def search(self, query: str, k: int = 4) -> list[dict]:
        q_terms = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
        if not q_terms:
            return []
        scored: list[tuple[float, tuple[str, str, str]]] = []
        for entry in self.entries:
            text_lower = entry[2].lower()
            score = sum(text_lower.count(t) for t in q_terms)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"source": e[0], "chunk_id": e[1], "text": e[2], "score": float(s)}
            for s, e in scored[:k]
        ]


_index: object | None = None
_index_kind: str = ""  # "chroma" or "keyword"


def _build_chroma():
    """尝试构建 chroma 向量索引；失败抛异常由调用方降级。"""
    import chromadb
    from chromadb.utils import embedding_functions

    settings = get_settings()
    client = chromadb.PersistentClient(path=str(settings.vector_store_dir))
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model
    )
    collection = client.get_or_create_collection(
        name="weilai_e_kb", embedding_function=embedder
    )
    if collection.count() == 0:
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        for source, text in _read_corpus():
            for i, chunk in enumerate(_split(text)):
                ids.append(f"{source}#{i}")
                docs.append(chunk)
                metas.append({"source": source})
        if ids:
            collection.add(ids=ids, documents=docs, metadatas=metas)
    return collection


def _build_keyword() -> _KeywordIndex:
    idx = _KeywordIndex()
    for source, text in _read_corpus():
        idx.add(source, _split(text))
    return idx


def _ensure_index() -> tuple[object, str]:
    global _index, _index_kind
    if _index is not None:
        return _index, _index_kind
    try:
        _index = _build_chroma()
        _index_kind = "chroma"
    except Exception:
        _index = _build_keyword()
        _index_kind = "keyword"
    return _index, _index_kind


def search(query: str, k: int = 4) -> list[dict]:
    """检索知识库，返回 [{source, text, score}]。"""
    if not query.strip():
        return []
    index, kind = _ensure_index()
    if kind == "chroma":
        res = index.query(query_texts=[query], n_results=k)  # type: ignore[attr-defined]
        out: list[dict] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0] if "distances" in res else [0.0] * len(ids)
        for i, doc in enumerate(docs):
            out.append(
                {
                    "source": metas[i].get("source", "") if i < len(metas) else "",
                    "chunk_id": ids[i] if i < len(ids) else "",
                    "text": doc,
                    "score": 1.0 - float(dists[i]) if i < len(dists) else 0.0,
                }
            )
        return out
    return index.search(query, k)  # type: ignore[union-attr]


def reset_index() -> None:
    """开发期重建索引：清掉缓存的内存索引。Chroma 持久化文件不主动删，避免误伤。"""
    global _index, _index_kind
    _index = None
    _index_kind = ""


def render_context(results: list[dict]) -> str:
    """把检索结果渲染成可拼到 prompt 的引用块。"""
    if not results:
        return ""
    lines = ["# 校招知识库检索结果"]
    for r in results:
        source = r.get("source", "")
        lines.append(f"\n[校招资料 · {source}]\n{r['text']}")
    return "\n".join(lines)


def build_index_cli() -> None:
    """脚本式入口：python -m tools.knowledge_search 重建索引。"""
    reset_index()
    _ensure_index()
    print(f"index ready: kind={_index_kind}")


if __name__ == "__main__":
    build_index_cli()
