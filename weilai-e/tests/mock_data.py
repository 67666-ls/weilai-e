"""未来鹅 模拟测试数据：覆盖四类年级画像 + 四个 Agent 的典型对话。

每条样本携带：
- profile：sidebar 注入的画像
- user_text：学生这一句话
- expect_agent：期望路由到的 Agent
- note：用例意图（用于报告里展示）
"""
from __future__ import annotations

# 一段模拟简历（可拼到对话里触发 resume_analyzer）
SAMPLE_RESUME = """\
姓名：张三   手机：138****0001   邮箱：zhangsan@xx.edu.cn
学校：某大学 计算机科学与技术 本科 大四（GPA 3.6/4.0）

# 项目经历
1. 校园二手交易平台（2024.03 - 2024.09）
- 负责后台 API 设计与实现，基于 FastAPI + PostgreSQL，QPS 峰值 120。
- 主导引入 Redis 缓存热门商品列表，接口 P95 从 380ms 降到 90ms。
- 推动前后端分离方案落地，注册转化率提升 22%。

2. 课程项目：基于 BERT 的评论情感分析（2023.11 - 2024.01）
- 完成 8w 条数据清洗与标注，使用 HuggingFace Transformers 微调，F1 0.89。

# 实习经历
- 某创业公司 后台开发实习生（2024.07-09）
  搭建订单服务 gRPC 接口，覆盖 5 个核心场景，迭代 3 个版本。

# 技能
熟练 Python / Go，了解 MySQL / Redis / Kafka，使用过 Docker / K8s。
GitHub: github.com/zhangsan
"""


PROFILES = {
    "freshman": {
        "grade": "大一",
        "major": "计算机科学与技术",
        "interests": ["互联网产品", "算法/AI"],
        "target_roles": [],
        "notes": "高考报志愿时挺感兴趣，但还没想清楚未来方向",
    },
    "sophomore": {
        "grade": "大二",
        "major": "软件工程",
        "interests": ["前端", "后台"],
        "target_roles": [],
        "notes": "课程项目做过一个小程序，想试试实习",
    },
    "junior": {
        "grade": "大三",
        "major": "计算机科学与技术",
        "interests": ["互联网产品", "数据"],
        "target_roles": ["产品经理", "数据分析"],
        "notes": "有一段创业公司运营实习，准备暑期投鹅厂",
    },
    "senior": {
        "grade": "大四",
        "major": "计算机科学与技术",
        "interests": ["后台", "算法/AI"],
        "target_roles": ["后台开发"],
        "notes": "秋招中，已有 2 个 offer 在等鹅厂",
    },
    "grad": {
        "grade": "研究生",
        "major": "人工智能",
        "interests": ["算法/AI"],
        "target_roles": ["算法工程师"],
        "notes": "研一，想冲春招",
    },
}


CASES: list[dict] = [
    # ---- explorer ----
    {
        "id": "C01",
        "profile": PROFILES["freshman"],
        "user_text": "学长,我才大一,有点迷茫,听说有产品研发设计运营,到底都是干嘛的?",
        "expect_agent": "explorer",
        "note": "大一 + 迷茫关键词命中 explorer (避开首次访谈分支)",
    },
    {
        "id": "C02",
        "profile": PROFILES["freshman"],
        "user_text": "我有点迷茫，不知道大学这四年该做什么准备，感觉同学都很卷",
        "expect_agent": "explorer",
        "note": "迷茫关键词命中 explorer",
    },

    # ---- intern ----
    {
        "id": "C03",
        "profile": PROFILES["sophomore"],
        "user_text": "大二想找一段日常实习练练手,目标是前端开发,作品集和简历该怎么准备?",
        "expect_agent": "intern",
        "note": "实习/作品集 → intern",
    },
    {
        "id": "C04",
        "profile": PROFILES["junior"],
        "user_text": "大三暑期想投鹅厂的产品实习,但我之前没产品经验,只做过运营,内推靠谱吗?",
        "expect_agent": "intern",
        "note": "实习 + 内推关键词 → intern；岗位匹配应给出产品经理候选",
    },

    # ---- coach ----
    {
        "id": "C05",
        "profile": PROFILES["senior"],
        "user_text": "秋招时间线我快踩空了,鹅厂后台开发的笔试和面试一般什么节奏?现在还能准备吗?",
        "expect_agent": "coach",
        "note": "秋招/笔试 关键词 → coach",
    },
    {
        "id": "C06",
        "profile": PROFILES["senior"],
        "user_text": f"帮我看下我的简历,后台开发岗想冲鹅厂:\n\n{SAMPLE_RESUME}",
        "expect_agent": "coach",
        "note": "简历关键词 + 长文本 → coach,触发 resume_analyzer",
    },
    {
        "id": "C07",
        "profile": PROFILES["grad"],
        "user_text": "我手里有美团和字节的 offer,但还在等鹅厂算法的二面通知,该怎么决策?",
        "expect_agent": "coach",
        "note": "offer 关键词 → coach",
    },

    # ---- mock ----
    {
        "id": "C08",
        "profile": PROFILES["junior"],
        "user_text": "学长帮我模拟一场产品经理岗的群面吧,我紧张得不行",
        "expect_agent": "mock",
        "note": "模拟面试关键词 → mock",
    },
    {
        "id": "C09",
        "profile": PROFILES["senior"],
        "user_text": "出题吧,我想练一道行为题,最好用 STAR 框架",
        "expect_agent": "mock",
        "note": "出题关键词 → mock",
    },

    # ---- interviewer (反向访谈:首次进入 + 主动喊话) ----
    {
        "id": "C10",
        "profile": {"grade": "", "major": "", "interests": [], "target_roles": [], "notes": ""},
        "user_text": "你好,这是什么产品?",
        "expect_agent": "interviewer",
        "note": "空画像 + 无任何 memory → 首次进入,主动开反向访谈",
    },
    {
        "id": "C11",
        "profile": PROFILES["junior"],
        "user_text": "学长先盘一下我自己吧,采访我一下",
        "expect_agent": "interviewer",
        "note": "interviewer 关键词显式命中,跳过年级默认值",
    },
]
