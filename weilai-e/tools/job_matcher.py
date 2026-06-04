"""岗位匹配工具：基于关键词和 RAG 的简单匹配。"""
from __future__ import annotations

from . import knowledge_search


# 岗位特征：学生表达 → 推荐方向。仅作启发，最终由 LLM 综合判断。
ROLE_HINTS: dict[str, list[str]] = {
    "后台开发": ["后端", "后台", "服务端", "C++", "Go", "Java", "高并发", "分布式"],
    "前端开发": ["前端", "JS", "JavaScript", "TypeScript", "React", "Vue", "网页"],
    "客户端开发": ["客户端", "iOS", "Android", "App", "桌面"],
    "算法/AI": ["算法", "AI", "机器学习", "深度学习", "推荐", "NLP", "CV", "大模型"],
    "数据开发/分析": ["数据", "SQL", "数据仓库", "BI", "增长", "数据分析"],
    "产品经理": ["产品经理", "产品", "PRD", "用户研究", "迭代"],
    "用户研究": ["用户研究", "访谈", "调研"],
    "视觉/交互设计": ["设计", "UI", "UX", "交互", "Figma"],
    "运营": ["运营", "增长运营", "内容运营", "社区"],
    "市场公关": ["市场", "公关", "品牌", "媒介"],
}


def match_by_keyword(text: str) -> list[tuple[str, int]]:
    """基于关键词命中给出粗排候选。"""
    hits: list[tuple[str, int]] = []
    text_l = text.lower()
    for role, terms in ROLE_HINTS.items():
        score = sum(1 for t in terms if t.lower() in text_l)
        if score:
            hits.append((role, score))
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits


def recommend(student_input: str, top_k: int = 3) -> dict:
    """给出岗位推荐 + 相关知识库片段，供下游 Agent 整合。"""
    keyword_hits = match_by_keyword(student_input)[:top_k]
    rag_chunks = knowledge_search.search(student_input, k=3)
    return {
        "candidates": [{"role": role, "score": score} for role, score in keyword_hits],
        "evidence": rag_chunks,
    }


def render(result: dict) -> str:
    if not result.get("candidates") and not result.get("evidence"):
        return ""
    lines = ["# 岗位匹配建议"]
    if result.get("candidates"):
        lines.append("候选方向（关键词热度排序）：")
        for c in result["candidates"]:
            lines.append(f"- {c['role']}（命中度 {c['score']}）")
    ev = knowledge_search.render_context(result.get("evidence", []))
    if ev:
        lines.append("")
        lines.append(ev)
    return "\n".join(lines)
