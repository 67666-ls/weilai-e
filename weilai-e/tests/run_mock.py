"""跑模拟数据：把每条 case 喂进 LangGraph,打印路由 + 工具上下文 + 回复摘要。

用法：
    cd weilai-e
    python -m tests.run_mock

无 LLM_API_KEY 时,Agent 节点会走 StubLLM 兜底（不影响路由 + 工具触发的验证）。
"""
from __future__ import annotations

import io
import sys
import time
import traceback

# Windows 控制台默认 GBK,无法打印中文/特殊字符,强制 UTF-8。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
else:  # Python 3.6 及以下兜底
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage

from config.prompts import AGENT_LABELS
from config.settings import get_settings
from core.graph import get_app
from tests.mock_data import CASES


def _short(text: str, n: int = 120) -> str:
    text = (text or "").replace("\n", " ⏎ ").strip()
    return text if len(text) <= n else text[:n] + "…"


def _run_one(case: dict) -> dict:
    app = get_app()
    payload = {
        "messages": [HumanMessage(content=case["user_text"])],
        "user_id": f"test_{case['id']}",
        "profile": case["profile"],
    }
    t0 = time.time()
    try:
        result = app.invoke(payload)
        elapsed = time.time() - t0
        agent = result.get("agent", "")
        tools_output = result.get("tools_output", "")
        ai_text = ""
        for m in result.get("messages", [])[::-1]:
            if getattr(m, "type", "") == "ai":
                ai_text = getattr(m, "content", "") or ""
                break
        return {
            "ok": True,
            "agent": agent,
            "elapsed": elapsed,
            "tools_output": tools_output,
            "ai_text": ai_text,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "agent": "",
            "elapsed": time.time() - t0,
            "tools_output": "",
            "ai_text": "",
            "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        }


def main() -> int:
    settings = get_settings()
    print("=" * 78)
    print(f" 未来鹅 · 模拟数据测试   |   LLM 就绪: {settings.llm_ready}   |   共 {len(CASES)} 条")
    print("=" * 78)

    rows: list[dict] = []
    for case in CASES:
        r = _run_one(case)
        passed = r["ok"] and r["agent"] == case["expect_agent"]
        rows.append({"case": case, "result": r, "passed": passed})

        flag = "PASS" if passed else ("FAIL" if r["ok"] else "CRASH")
        print(f"\n[{flag}] [{case['id']}] {case['note']}")
        print(f"   画像: grade={case['profile'].get('grade') or '-'}, "
              f"major={case['profile'].get('major') or '-'}")
        print(f"   学生: {_short(case['user_text'], 100)}")
        if r["ok"]:
            agent_label = AGENT_LABELS.get(r["agent"], r["agent"])
            print(f"   路由: 期望={case['expect_agent']}  实际={r['agent']}  ({agent_label})  耗时 {r['elapsed']:.2f}s")
            print(f"   工具: {_short(r['tools_output'], 120) or '(空)'}")
            print(f"   回复: {_short(r['ai_text'], 160) or '(空)'}")
        else:
            print(f"   ❗错误: {_short(r['error'], 200)}")

    # 汇总
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    crashed = sum(1 for r in rows if not r["result"]["ok"])
    routed_wrong = sum(1 for r in rows if r["result"]["ok"] and not r["passed"])

    print("\n" + "=" * 78)
    print(f" 结果: 通过 {passed}/{total}  |  路由错 {routed_wrong}  |  异常 {crashed}")
    print("=" * 78)

    # 表格
    print(f"\n{'ID':<5} {'expect':<10} {'actual':<10} {'agent_label':<10} {'tool?':<6} {'reply?':<7}")
    print("-" * 60)
    for row in rows:
        c = row["case"]; r = row["result"]
        actual = r["agent"] if r["ok"] else "ERR"
        label = AGENT_LABELS.get(actual, "-")
        tool_flag = "yes" if r["tools_output"] else "no"
        reply_flag = "yes" if r["ai_text"] else "no"
        print(f"{c['id']:<5} {c['expect_agent']:<10} {actual:<10} {label:<10} {tool_flag:<6} {reply_flag:<7}")

    return 0 if (passed == total) else 1


if __name__ == "__main__":
    sys.exit(main())
