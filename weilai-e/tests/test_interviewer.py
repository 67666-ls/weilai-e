"""interviewer 端到端验证（不依赖 LLM Key）：

1. 首次进入(空 memory) → 路由到 interviewer;
2. 模拟 LLM 吐回带 <card>...</card> 的回复 → memory 里出现经历卡 / 能力卡 / 纠结卡 / 任务;
3. interview_done=True 之后下次再来 → 不再走 interviewer。

直接用 _persist 走入库分支,绕开真 LLM。
"""
from __future__ import annotations

import shutil
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from langchain_core.messages import HumanMessage  # noqa: E402

from config.settings import get_settings  # noqa: E402
from core.agents import _persist  # noqa: E402
from core.router import route  # noqa: E402
from memory.conversation import load  # noqa: E402

# 把测试用 memory 隔离到单独目录,避免污染真 store
_TEST_DIR = get_settings().memory_dir / "_test_interview"
_TEST_DIR.mkdir(parents=True, exist_ok=True)
get_settings().memory_dir = _TEST_DIR
USER_ID = "e2e"
# 清掉本次跑的痕迹
for f in _TEST_DIR.glob(f"{USER_ID}*.json"):
    f.unlink()


SAMPLE_AI = """\
听上去这是一段挺亮的经历,带我多问两句:你当时是几个人一组?具体负责哪一块?

<card>
{
  "experience": {
    "period": "大二·课程项目",
    "title": "三人组做校园二手交易平台",
    "role": "后端 API",
    "result": "上线后注册转化率 +22%",
    "tags": ["后端", "项目"]
  },
  "skills": [
    {"name": "项目推动", "score": 4},
    {"name": "工程实现", "score": 3}
  ],
  "struggle": "想做产品但担心非科班背景",
  "tasks": [
    {"text": "把简历项目部分按 STAR 重写一版", "deadline": "本周日"}
  ]
}
</card>
"""

SAMPLE_AI_DONE = """\
画像差不多有了,接下来你想聊岗位还是聊简历都可以。

<card>
{"interview_done": true}
</card>
"""


def _step(label: str, ok: bool, detail: str = "") -> bool:
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {label}" + (f"  -- {detail}" if detail else ""))
    return ok


def main() -> int:
    user_id = USER_ID
    state = {
        "messages": [HumanMessage(content="组队做了个校园二手平台,我负责后端")],
        "user_id": user_id,
        "profile": {"grade": "大三", "major": "计算机"},
    }

    all_ok = True

    # 1. 首次进入(空 memory)→ interviewer
    delta = route(state)
    all_ok &= _step("首次进入路由到 interviewer", delta.get("agent") == "interviewer",
                    f"实际 agent={delta.get('agent')}")

    # 2. 模拟 LLM 输出 <card> 走入库
    cleaned, extra = _persist(state, "interviewer", SAMPLE_AI, "组队做了个校园二手平台,我负责后端")
    mem = load(user_id)
    all_ok &= _step("经历卡入库", len(mem.experiences) == 1,
                    f"experiences={len(mem.experiences)}")
    all_ok &= _step("能力卡入库", len(mem.skills) == 2,
                    f"skills={[s.name for s in mem.skills]}")
    all_ok &= _step("纠结卡入库", len(mem.struggles) == 1,
                    f"struggles={[s.content for s in mem.struggles]}")
    all_ok &= _step("行动任务入库", len(mem.tasks) == 1,
                    f"tasks={[t.text for t in mem.tasks]}")
    all_ok &= _step("AI 文本已剥离 <card>", "<card>" not in cleaned and "听上去" in cleaned)

    # 3. 第二次:还没 interview_done,但 experiences 非空了 → 走年级默认(intern/coach 等)
    delta2 = route({**state, "messages": [HumanMessage(content="继续")]})
    all_ok &= _step("有了经历卡之后不再走 interviewer", delta2.get("agent") != "interviewer",
                    f"实际 agent={delta2.get('agent')}")

    # 4. 模拟收口(interview_done=True),再来一次 → 仍不走 interviewer
    _persist(state, "interviewer", SAMPLE_AI_DONE, "够了")
    mem2 = load(user_id)
    all_ok &= _step("interview_done 已置位", mem2.interview_done is True)

    delta3 = route({**state, "messages": [HumanMessage(content="再聊聊")]})
    all_ok &= _step("interview_done 后路由不会回到 interviewer",
                    delta3.get("agent") != "interviewer",
                    f"实际 agent={delta3.get('agent')}")

    # 5. 显式喊话仍然能命中 interviewer
    delta4 = route({
        **state,
        "messages": [HumanMessage(content="再帮我做画像一次")],
    })
    all_ok &= _step("显式 '帮我做画像' 关键词仍可命中 interviewer",
                    delta4.get("agent") == "interviewer",
                    f"实际 agent={delta4.get('agent')}")

    print("=" * 60)
    print("PASS" if all_ok else "FAIL")

    # 清理测试目录
    try:
        shutil.rmtree(_TEST_DIR)
    except Exception:
        pass
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
