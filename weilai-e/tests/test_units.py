"""轻量纯函数单元测试,不依赖 LLM/streamlit。

覆盖:
    1. tools.resume_analyzer.analyze:STAR / 模块识别 / 联系方式 / 项目数
    2. core.agents._extract_cards / _strip_card / _balanced_json:多卡 + 嵌套 + 失败容错
    3. data/role_requirements.json schema 自检 + app._load_role_requirements 兜底
    4. memory.conversation pending_tasks / mark_task / add_task 行为

直接 `python -m tests.test_units` 运行,出非 0 退出码即视为失败。
"""
from __future__ import annotations

import io
import json
import sys
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from config.settings import get_settings  # noqa: E402
from core.agents import _balanced_json, _extract_cards, _strip_card  # noqa: E402
from memory.conversation import (  # noqa: E402
    ConversationMemory,
    add_task,
    mark_task,
    pending_tasks,
)
from tools import resume_analyzer  # noqa: E402


_FAILED: list[str] = []


def assert_eq(label: str, actual, expected) -> None:
    if actual == expected:
        print(f"[PASS] {label}")
    else:
        print(f"[FAIL] {label}  expected={expected!r}  actual={actual!r}")
        _FAILED.append(label)


def assert_true(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"[PASS] {label}")
    else:
        suffix = f"  -- {detail}" if detail else ""
        print(f"[FAIL] {label}{suffix}")
        _FAILED.append(label)


# ---------- resume_analyzer ----------

GOOD_RESUME = """
姓名:张三   邮箱:zhangsan@example.com   手机:13800138000   GitHub:github.com/zs

教育背景:某 211 大学计算机科学   GPA 3.8/4.0

项目经历:
项目一 校园二手平台
- 负责后端 API,设计订单/评价两张表,接入支付沙箱
- 上线后注册转化率提升 22%,日活覆盖 1200 人
- 主导一次跨 5 人的 sprint,推动支付回调修复

项目二 课程设计 推荐系统
- 负责数据预处理与召回模块
- 离线 AUC 提升 8%,获得课程优秀

实习/工作经历:某厂 后台开发实习

技能:Python / Go 熟练,Redis 熟悉
"""

BAD_RESUME = """
我是个学生,熟练 Python,精通各种东西,熟悉很多框架,了解算法,
熟练 Java,熟练 Go,精通 SQL。我做了个项目挺好的。
"""

EMAIL_BROKEN_RESUME = """姓名:李四 邮箱:lisi.example.com  教育背景:本科"""


def test_resume_analyzer() -> None:
    print("\n--- resume_analyzer ---")
    fb = resume_analyzer.analyze(GOOD_RESUME)
    assert_true("好简历:5 模块全识别", set(fb.sections_present) >= {"基本信息", "教育背景", "项目经历", "技能"},
                f"present={fb.sections_present}")
    assert_true("好简历:STAR 行 >= 1", fb.star_lines >= 1, f"star={fb.star_lines}")
    assert_true("好简历:项目段落数 >= 2", fb.project_count >= 2, f"project_count={fb.project_count}")
    assert_eq("好简历:无 contact_warnings", fb.contact_warnings, [])

    fb2 = resume_analyzer.analyze(BAD_RESUME)
    assert_true("烂简历:抓到空泛词过多",
                any("熟练" in s or "精通" in s for s in fb2.suggestions),
                f"suggestions={fb2.suggestions}")
    assert_true("烂简历:缺少模块提示", any("缺少" in s for s in fb2.suggestions),
                f"suggestions={fb2.suggestions}")

    fb3 = resume_analyzer.analyze(EMAIL_BROKEN_RESUME)
    assert_true("邮箱格式错误能被检出",
                any("邮箱" in w for w in fb3.contact_warnings),
                f"contact_warnings={fb3.contact_warnings}")


# ---------- card 解析 ----------

CARD_TEXT_NESTED = """\
不错,继续问你两个细节。

<card>
{
  "experience": {"period": "大二·暑假", "title": "校园二手", "tags": ["产品", "数据"]},
  "skills": [{"name": "项目推动", "score": 4}, {"name": "数据分析", "score": 3}],
  "tasks": [{"text": "本周写一版 STAR 简历", "deadline": "本周日"}]
}
</card>

下次我们继续。
"""

CARD_TEXT_MULTI = """\
聊到这里收个口。
<card>{"skills": [{"name": "沟通表达", "score": 3}]}</card>
顺便记下纠结点:
<card>{"struggle": "想做产品但担心非科班背景"}</card>
"""

CARD_TEXT_BROKEN = """\
解析失败也别炸。
<card>{this is not json</card>
正常文本继续。
"""


def test_card_parsing() -> None:
    print("\n--- card 解析 ---")
    cards = _extract_cards(CARD_TEXT_NESTED)
    assert_eq("嵌套 JSON:解析出 1 张卡", len(cards), 1)
    if cards:
        exp = cards[0].get("experience", {})
        assert_eq("嵌套 JSON:experience.period", exp.get("period"), "大二·暑假")
        assert_eq("嵌套 JSON:experience.tags 是 list", exp.get("tags"), ["产品", "数据"])
        skills = cards[0].get("skills", [])
        assert_eq("嵌套 JSON:skills 数量", len(skills), 2)

    cards2 = _extract_cards(CARD_TEXT_MULTI)
    assert_eq("多个 <card> 块都被解析", len(cards2), 2)

    cards3 = _extract_cards(CARD_TEXT_BROKEN)
    assert_eq("非法 JSON 不抛异常,返回空", cards3, [])

    cleaned = _strip_card(CARD_TEXT_NESTED)
    assert_true("_strip_card 去掉了 <card>",
                "<card>" not in cleaned and "继续问" in cleaned,
                f"cleaned={cleaned!r}")

    # _balanced_json 直接拿到的字符串能 json.loads
    raw = _balanced_json('  {"a": [1,2,{"b": "c"}], "d": "}"}  ')
    assert_true("_balanced_json:跳过字符串里的 }",
                raw is not None and json.loads(raw)["d"] == "}",
                f"raw={raw}")


# ---------- role_requirements ----------

def test_role_requirements_json() -> None:
    print("\n--- role_requirements.json ---")
    path = Path(__file__).resolve().parent.parent / "data" / "role_requirements.json"
    assert_true("role_requirements.json 存在", path.exists())
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    dims = data.get("_dimensions") or []
    assert_eq("维度名 6 个", len(dims), 6)
    roles = data.get("roles") or []
    assert_true("至少有 7 类岗位", len(roles) >= 7, f"roles={len(roles)}")
    for entry in roles:
        kw = entry.get("keywords") or []
        vec = entry.get("vector") or []
        ok = bool(kw) and len(vec) == len(dims) and all(isinstance(v, int) and 0 <= v <= 5 for v in vec)
        assert_true(f"岗位 {kw[0] if kw else '?'} schema 正确", ok,
                    f"entry={entry}")


# ---------- pending_tasks ----------

def test_pending_tasks() -> None:
    print("\n--- pending_tasks ---")
    mem = ConversationMemory(user_id="unit_test")
    add_task(mem, text="A", created_by="interviewer")
    t2 = add_task(mem, text="B", created_by="coach")
    add_task(mem, text="C")

    pending = pending_tasks(mem, limit=10)
    assert_eq("初始 pending 数量", len(pending), 3)

    mark_task(mem, t2.id, "done")
    pending = pending_tasks(mem, limit=10)
    assert_eq("mark done 后 pending 减少", len(pending), 2)
    assert_true("done 任务不出现在 pending",
                all(t.text != "B" for t in pending),
                f"pending={[t.text for t in pending]}")

    # 不存在的 id 不抛
    assert_eq("mark 不存在的 id 返回 False", mark_task(mem, "nope", "done"), False)

    # limit 截断,取最新 N 条
    for i in range(8):
        add_task(mem, text=f"task-{i}")
    last3 = pending_tasks(mem, limit=3)
    assert_eq("limit=3 时返回 3 条", len(last3), 3)
    assert_eq("limit 取最近的几条", last3[-1].text, "task-7")


def main() -> int:
    settings = get_settings()
    print(f"== 单元测试 ==  memory_dir={settings.memory_dir}")
    suites = [
        ("resume_analyzer", test_resume_analyzer),
        ("card 解析", test_card_parsing),
        ("role_requirements", test_role_requirements_json),
        ("pending_tasks", test_pending_tasks),
    ]
    for name, fn in suites:
        try:
            fn()
        except Exception as exc:
            print(f"[CRASH] {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            _FAILED.append(name)

    print("\n" + "=" * 60)
    if _FAILED:
        print(f"FAIL ({len(_FAILED)} 项):" + ", ".join(_FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
