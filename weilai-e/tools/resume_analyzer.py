"""简历分析工具:基础结构启发式 + STAR 检查 + 表达清晰度,结合 LLM 给细节反馈。"""
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
_VERB_PATTERN = re.compile(r"(负责|参与|搭建|实现|优化|完成|主导|推动|设计|开发|重构|修复)")
_RESULT_PATTERN = re.compile(r"(提升|降低|增长|减少|节省|获得|发布|上线|拿下|累计|覆盖|达成)")
# 项目段落标题:形如 "项目一 / 项目1 / Project 1"
_PROJECT_HEADER = re.compile(r"^[\s\-\*]*(项目[一二三四五六七八九十\d]|Project\s*\d)", re.I | re.M)
_VAGUE_WORDS = ["精通", "熟练", "了解", "熟悉", "掌握"]
_VAGUE_THRESHOLD = 3
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")


@dataclass
class ResumeFeedback:
    sections_present: list[str]
    sections_missing: list[str]
    quantified_lines: int
    action_verb_lines: int
    star_lines: int            # 同时含动词 + 数字 + 结果词的「STAR-ish」行数
    project_count: int         # 识别到的项目段落数
    word_count: int
    contact_warnings: list[str]  # 邮箱/手机问题
    suggestions: list[str]

    def to_dict(self) -> dict:
        return {
            "sections_present": self.sections_present,
            "sections_missing": self.sections_missing,
            "quantified_lines": self.quantified_lines,
            "action_verb_lines": self.action_verb_lines,
            "star_lines": self.star_lines,
            "project_count": self.project_count,
            "word_count": self.word_count,
            "contact_warnings": self.contact_warnings,
            "suggestions": self.suggestions,
        }


def _check_contacts(text: str) -> list[str]:
    warnings: list[str] = []
    emails = _EMAIL_PATTERN.findall(text)
    if "邮箱" in text or "@" in text:
        if not emails:
            warnings.append("看起来你提到了邮箱但格式不对,检查一下有没有漏 @ 或 .com。")
    phones = _PHONE_PATTERN.findall(text)
    if "手机" in text and not phones:
        warnings.append("没识别到 11 位手机号,确认下格式是否正确。")
    return warnings


def _vague_word_density(text: str) -> dict[str, int]:
    return {w: len(re.findall(w, text)) for w in _VAGUE_WORDS}


def analyze(resume_text: str) -> ResumeFeedback:
    text = resume_text or ""
    present = [name for name, pat in _SECTION_PATTERNS.items() if re.search(pat, text)]
    missing = [name for name in _SECTION_PATTERNS if name not in present]

    lines = [ln for ln in text.splitlines() if ln.strip()]
    quantified = sum(1 for ln in lines if _QUANT_PATTERN.search(ln))
    actioned = sum(1 for ln in lines if _VERB_PATTERN.search(ln))
    star = sum(
        1
        for ln in lines
        if _QUANT_PATTERN.search(ln) and (_VERB_PATTERN.search(ln) or _RESULT_PATTERN.search(ln))
    )
    project_count = len(_PROJECT_HEADER.findall(text))
    contact_warnings = _check_contacts(text)
    vague = _vague_word_density(text)

    suggestions: list[str] = []
    word_count = len(text)
    if word_count > 1500:
        suggestions.append("篇幅偏长(>1500 字),建议压到 1 页 A4,校招简历越短越精炼越好。")
    if word_count and word_count < 400:
        suggestions.append("篇幅偏短(<400 字),项目细节和实习经历可以再展开,补充背景与你独立的贡献。")
    if missing:
        suggestions.append(f"缺少这些常规模块:{ '、'.join(missing) };至少补全教育/项目/技能。")
    if quantified < max(3, len(lines) // 6):
        suggestions.append("量化结果偏少,多加数字(提升 30%、覆盖 1w 用户、QPS 5000 等)。")
    if actioned < max(3, len(lines) // 6):
        suggestions.append("用更多动作动词开头(负责/搭建/优化/主导),让 HR 看清你做了什么。")
    if lines and star < max(2, len(lines) // 10):
        suggestions.append("项目描述要尽量凑齐 STAR 三件套:动词 + 数字 + 结果词(提升/上线/获得),现在大多数行只占其中一两项。")
    if project_count == 0 and "项目" in text:
        suggestions.append("项目段落建议用「项目一/项目二」明确分块,每个项目独立段落,HR 才能 5 秒扫到。")
    if project_count == 1:
        suggestions.append("只有 1 个项目稍单薄,校招建议至少 2-3 个项目(课程项目/竞赛/开源都可以),覆盖不同类型能力。")
    overuse = [w for w, c in vague.items() if c >= _VAGUE_THRESHOLD]
    if overuse:
        suggestions.append(f"「{ '/'.join(overuse) }」出现次数偏多,这些词在 HR 眼里近乎噪音,建议替换成具体动作或量化结果。")
    if not re.search(r"GitHub|github\.com|个人主页|博客", text):
        suggestions.append("技术岗可附 GitHub / 个人作品集链接,能显著提升初筛通过率。")
    if not suggestions:
        suggestions.append("整体结构齐全;可继续在项目细节里加入业务背景与你独立的贡献。")

    return ResumeFeedback(
        sections_present=present,
        sections_missing=missing,
        quantified_lines=quantified,
        action_verb_lines=actioned,
        star_lines=star,
        project_count=project_count,
        word_count=word_count,
        contact_warnings=contact_warnings,
        suggestions=suggestions,
    )


def render(feedback: ResumeFeedback) -> str:
    lines = ["# 简历自检报告"]
    lines.append(f"- 总字数:{feedback.word_count}")
    lines.append(f"- 已识别模块:{ '、'.join(feedback.sections_present) or '—' }")
    lines.append(f"- 缺失模块:{ '、'.join(feedback.sections_missing) or '无' }")
    lines.append(
        f"- 量化句数 / 动作动词句数 / STAR 完整句数:"
        f"{feedback.quantified_lines} / {feedback.action_verb_lines} / {feedback.star_lines}"
    )
    lines.append(f"- 识别到的项目段落数:{feedback.project_count}")
    if feedback.contact_warnings:
        lines.append("- 联系方式:" + ";".join(feedback.contact_warnings))
    lines.append("")
    lines.append("## 改进建议")
    for s in feedback.suggestions:
        lines.append(f"- {s}")
    return "\n".join(lines)
