# 未来鹅 · 成长闭环引擎方案

> 目的：把"4 个 Agent + 路由 + 画像表单"的问答式产品，
> 升级为「AI 成长教练」——让对话沉淀成资产、让 AI 反过来追问用户。

---

## 一、产品定位升级

当前形态以单轮问答为主:用户提问、Agent 回答、关闭即清空。
升级目标是把单轮问答串成持续陪伴的成长闭环：

- 主动收集用户的经历与能力，沉淀为可复用的画像资产；
- 跨会话记住用户上次定下的目标，重新打开时主动追问进度；
- 把对话产物可视化为"能力雷达"，让用户看到自己的成长。

---

## 二、核心机制（按优先级）

### 机制 1 ——「反向访谈」：AI 主动收集素材

**形态**：第一次进入产品时不是空白输入框，而是 AI 主动开访谈。

> "在聊岗位之前，先认识下你。说一件你大学里最有成就感的事，不用长，就一件。"

学生回答后，AI 不只回应，而是把回答**结构化**沉淀进画像：

| 卡片类型 | 内容 |
|---|---|
| 📌 经历卡 | `[大二·课程项目] 三人团队做了 XX，我负责 YY，结果 ZZ` |
| 📌 能力卡 | `项目推动力 ⭐⭐⭐⭐ / 数据分析 ⭐⭐⭐` |
| 📌 纠结卡 | `想做产品但担心非科班背景` |

**产品价值**：这些卡日后直接拼成 STAR 素材库 / 面经故事原料，
也是后续岗位推荐、简历优化的输入。

---

### 机制 2 ——「Next Step 行动板」：取代纯聊天首屏

主页面顶部不再是 chat input，是 3 张行动卡：

```
┌─────────────────────────────────────┐
│ 🎯 本周要做  (距秋招还有 87 天)      │
├─────────────────────────────────────┤
│ ☐ 把简历项目部分按 STAR 重写一版    │
│   截止 周日   [开始] [跳过]         │
│ ☐ 投递 1 个目标岗位                 │
│ ☐ 跟学长聊一次产品岗日常            │
└─────────────────────────────────────┘
```

**关键交互**：每次进来 AI 第一句话是：

> "上周说要改简历，改完了吗？"

**根据回答更新卡片状态**：done / pending / 顺延。

把"一次性问答"升级成"持续项目"——这是跨会话状态机。

---

### 机制 3 ——「能力雷达 vs 岗位雷达」：可视化成长

把素材卡聚合成 6 维能力雷达：

- 项目推动 / 数据分析 / 沟通表达 / 技术深度 / 行业认知 / 抗压

叠加目标岗位的**要求雷达**，可视化差距。每次对话后能看到自己的雷达"长大"。

---

## 三、落地优先级

| 顺序 | 做什么 | 改动 | 工时 |
|------|--------|------|------|
| 1 | 反向访谈 Agent + 素材卡抽取 | 加 `interviewer` agent 角色；工具产出 JSON 卡片入 memory | 0.5 天 |
| 2 | Next Step 行动板 + 跨会话追问 | memory 加 `tasks` 字段；主页顶部组件；Router 注入"上次任务"上下文 | 0.5 天 |
| 3 | 雷达图 | plotly 一个组件，基于素材卡聚合 | 0.25 天 |

---

## 四、技术改动点（具体到文件）

### 4.1 `memory/conversation.py`

新增数据结构：

```python
@dataclass
class ExperienceCard:
    """经历卡：来自反向访谈的素材沉淀。"""
    ts: float
    period: str         # "大二·暑假" / "课程项目"
    title: str          # 一句话标题
    role: str           # 我担任什么
    result: str         # 结果/收获
    raw: str            # 学生原话
    tags: list[str]     # ["产品", "数据"]

@dataclass
class SkillCard:
    """能力卡：从经历提炼的能力评分（1-5）。"""
    name: str           # "项目推动" / "数据分析"
    score: int          # 1-5
    evidence: list[str] # 关联的 experience.title

@dataclass
class StruggleCard:
    """纠结卡：学生表达的焦虑/犹豫，给后续 Agent 回应用。"""
    ts: float
    content: str        # "想做产品但担心非科班背景"
    resolved: bool = False

@dataclass
class ActionTask:
    """Next Step 行动卡：跨会话追踪。"""
    ts: float
    text: str           # "把简历项目部分按 STAR 重写一版"
    deadline: str       # "本周日" / "2026-06-08"
    status: str         # "pending" / "done" / "skipped"
    created_by: str     # agent 名
```

`ConversationMemory` 字段补充：

```python
experiences: list[ExperienceCard] = []
skills: list[SkillCard] = []
struggles: list[StruggleCard] = []
tasks: list[ActionTask] = []
```

新增接口：`add_experience / add_skill / add_struggle / add_task / mark_task_done / pending_tasks / render_cards_view`。

### 4.2 `config/prompts.py`

新增 `INTERVIEWER_PROMPT`：

- 一次只问一个问题，从「成就感事件」开始；
- 学生回答后必须输出结构化 JSON（包在 `<card>...</card>` 标签里），由后端解析入库；
- 5 轮后或学生说"够了"则转交其他 Agent。

`AGENT_LABELS` 补 `"interviewer": "反向访谈"`。

### 4.3 `core/agents.py`

新增 `interviewer_node`：

- 工具：解析上一条 AI 回复中的 `<card>...</card>`，写入 memory；
- 触发：第一次进来 + 用户主动喊"帮我做画像"；
- 退出：5 轮后路由到 explorer/intern/coach。

### 4.4 `core/router.py`

补强：

- `memory.experiences` 为空 + 用户没明显意图时 → `interviewer`；
- 进入任意 Agent 前，把 `memory.pending_tasks()` 拼进 system prompt；
- 用户回答里带"改完了/做完了/跳过" → 调 `mark_task_done`。

### 4.5 `app.py`

主页顶部新增"今日行动板"组件（在欢迎语之前、chat history 之上）：

- 显示 `pending_tasks`，每条带 [✅ 完成] [⏭️ 跳过] 按钮；
- 没有 task 时显示空态："还没有目标，去聊一聊学长会帮你定。"
- 进入聊天时，如果有 pending_tasks，AI 第一句自动追问（由后端在 router 阶段注入到 system prompt 里完成）。

「我的画像 & 成长记录」expander 加第三个 tab：📋 素材卡（经历/能力/纠结），第四个 tab：📈 能力雷达。

### 4.6 `requirements.txt`

加 `plotly`（雷达图用）。

---

## 五、典型使用场景

1. **进入产品**：左边填年级=大三，专业=计算机；
2. **AI 主动开访谈**："说一件你大学里最有成就感的事。"
3. 学生说"组队做了一个校园二手平台，我负责后端"；
4. AI 回应 + 后台默默生成 `<card>` 写入 → 主区域第三个 tab 实时多出一张经历卡；
5. **AI 接着问**："担心校招想去大厂但不知道竞品有几家？"（追问纠结点）；
6. 5 轮后 AI 说："我帮你定 3 个本周要做的事"，主页顶部出现行动板；
7. **关闭浏览器、重开**：AI 第一句"上次说要改简历，改完了吗？"
8. 学生点 ✅ 完成；
9. 切到雷达 tab：能力雷达 vs 大厂后端要求雷达，差距一眼看到。

---

## 六、开发节奏

- **Day 1 上午**：改 `memory/conversation.py` 加数据结构 + `INTERVIEWER_PROMPT`；
- **Day 1 下午**：加 `interviewer_node`，跑通 `<card>` 解析入库；
- **Day 2 上午**：app.py 行动板 UI + tasks 字段联动；
- **Day 2 下午**：router 注入"上次任务"上下文 + 跨会话追问；
- **Day 3 上午**：雷达图 + 素材卡 tab；
- **Day 3 下午**：测试 + 调 prompt + 跑端到端验证。
