"""简历分析工具：基础结构启发式，结合 LLM 给细节反馈。"""
from __future__ import annotations

import re
from dataclasses import dataclass


_SECTION_PATTERNS = {
    "基本信息": r"(姓名|手机|邮箱|学校|微信)",
    "教育背景": r"(教育|本科|研究生|GPA|学院|学校)",
    "项目经历": r"(项目|Project|作品)",
    "实习/工作经历": r"(实习|工作|公司|Intern|Job)",
    "技能": r"(技能|Skill|掌握|熟练|精通)",
}

_QUANT_PATTERN = re.compile(r"\d+\s*(%|倍|人|次|条|万|个|秒|ms|qps|MAU|DAU)?", re.I)
_VERB_PATTERN = re.compile(r"(负责|参与|搭建|实现|优化|完成|主导|推动|设计|开发)")


@dataclass
class ResumeFeedback:
    sections_present: list[str]
    sections_missing: list[str]
    quantified_lines: int
    action_verb_lines: int
    word_count: int
    suggestions: list[str]

    def to_dict(self) -> dict:
        return {
            "sections_present": self.sections_present,
            "sections_missing": self.sections_missing,
            "quantified_lines": self.quantified_lines,
            "action_verb_lines": self.action_verb_lines,
            "word_count": self.word_count,
            "suggestions": self.suggestions,
        }


def analyze(resume_text: str) -> ResumeFeedback:
    text = resume_text or ""
    present = [name for name, pat in _SECTION_PATTERNS.items() if re.search(pat, text)]
    missing = [name for name in _SECTION_PATTERNS if name not in present]

    lines = [ln for ln in text.splitlines() if ln.strip()]
    quantified = sum(1 for ln in lines if _QUANT_PATTERN.search(ln))
    actioned = sum(1 for ln in lines if _VERB_PATTERN.search(ln))

    suggestions: list[str] = []
    word_count = len(text)
    if word_count > 1500:
        suggestions.append("篇幅偏长（>1500 字），建议压到 1 页 A4，校招简历越短越精炼越好。")
    if missing:
        suggestions.append(f"缺少这些常规模块：{ '、'.join(missing) }；至少补全教育/项目/技能。")
    if quantified < max(3, len(lines) // 6):
        suggestions.append("量化结果偏少，多加数字（提升 30%、覆盖 1w 用户、QPS 5000 等）。")
    if actioned < max(3, len(lines) // 6):
        suggestions.append("用更多动作动词开头（负责/搭建/优化/主导），让 HR 看清你做了什么。")
    if not re.search(r"GitHub|github\.com|个人主页|博客", text):
        suggestions.append("技术岗可附 GitHub / 个人作品集链接，能显著提升初筛通过率。")
    if not suggestions:
        suggestions.append("整体结构齐全；可继续在项目细节里加入业务背景与你独立的贡献。")

    return ResumeFeedback(
        sections_present=present,
        sections_missing=missing,
        quantified_lines=quantified,
        action_verb_lines=actioned,
        word_count=word_count,
        suggestions=suggestions,
    )


def render(feedback: ResumeFeedback) -> str:
    lines = ["# 简历自检报告"]
    lines.append(f"- 总字数：{feedback.word_count}")
    lines.append(f"- 已识别模块：{ '、'.join(feedback.sections_present) or '—' }")
    lines.append(f"- 缺失模块：{ '、'.join(feedback.sections_missing) or '无' }")
    lines.append(f"- 量化句数 / 动作动词句数：{feedback.quantified_lines} / {feedback.action_verb_lines}")
    lines.append("")
    lines.append("## 改进建议")
    for s in feedback.suggestions:
        lines.append(f"- {s}")
    return "\n".join(lines)
