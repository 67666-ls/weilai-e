# 🪿 未来鹅 · 大学生职业成长 AI 陪伴体

> 腾讯 AI-HR 培训营 Day4 作业，对应 [`未来鹅_设计方案.md`](../未来鹅_设计方案.md)。
> 「未来鹅」= 你的求职贴心学长，从大一到毕业全程陪伴，覆盖各大主流公司校招，帮你搞清楚"去哪、做什么、怎么准备"。

## 功能一览

- **四角色 Agent + 智能路由**（LangGraph）：探索向导 / 实习导航 / 求职教练 / 面试陪练，按年级 + 意图自动切换。
- **RAG 知识库**：内置 5 篇基础文档（腾讯专题 + 17 家主流公司岗位 + 实习/面试/文化），ChromaDB 向量检索，缺依赖时自动降级关键词检索。
- **个性化记忆**：年级（大一到研三细分）/ 专业 / 兴趣 / 近期成长，按画像生成稳定 ID，跨会话连续。
- **简历自检 & 岗位匹配**：本地启发式打分 + 关键词热度，结合 LLM 给出可执行建议。
- **零 Key 也能跑**：未配置 LLM 时启用桩模型，演示完整数据流。

## 项目结构

```
weilai-e/
├── app.py                    # Streamlit 入口
├── config/                   # 设置 + 系统 Prompt
├── core/                     # State / Router / Agents / Graph
│   ├── state.py
│   ├── router.py
│   ├── agents.py
│   ├── graph.py
│   └── llm.py
├── tools/                    # RAG / 简历分析 / 岗位匹配
├── data/
│   ├── knowledge_base/       # 校招知识文档（md，含主流互联网/科技公司）
│   └── vector_store/         # ChromaDB 持久化目录
├── memory/                   # 用户画像与成长档案
├── requirements.txt
├── .env.example
└── .streamlit/secrets.toml.example
```

## 本地启动

```bash
cd weilai-e
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # 填入 LLM_API_KEY 等
streamlit run app.py
```

> 第一次启动时会自动从 `data/knowledge_base/` 构建向量索引，需要几十秒。

如需重建向量库：

```bash
python -m tools.knowledge_search
```

## 配置 LLM

`.env` / `.streamlit/secrets.toml` 任选其一，字段一致：

| Key | 说明 | 示例 |
|-----|------|------|
| `LLM_API_KEY` | 兼容 OpenAI 协议的密钥 | sk-... |
| `LLM_BASE_URL` | API Base | https://api.openai.com/v1 |
| `LLM_MODEL` | 模型名 | gpt-4o-mini / deepseek-chat |
| `LLM_TEMPERATURE` | 采样温度 | 0.7 |
| `EMBEDDING_MODEL` | 本地 embedding 模型 | BAAI/bge-small-zh-v1.5 |

支持 OpenAI、DeepSeek、通义千问 OpenAI 兼容端点、本地 vLLM 等。

## 部署到 Streamlit Community Cloud

1. 把 `weilai-e/` 推送到 GitHub。
2. 登录 [share.streamlit.io](https://share.streamlit.io) → New app → 选仓库 + `app.py`。
3. 在 Secrets 面板粘贴 `.streamlit/secrets.toml.example` 的内容并填入真实 Key。
4. 部署完成后即可获得公网链接。

## 演示对话

- **大一**：「想了解互联网行业，但不知道自己适合做什么」→ 路由到 `explorer`，提开放问题 + 行业地图。
- **大三**：「秋招想投产品实习，鹅厂、字节、阿里我该怎么选？」→ 路由到 `intern`，岗位匹配 + 多公司校招引用 + 三步行动。
- **大四**：「帮我看看简历」（粘贴简历文本）→ 路由到 `coach`，简历自检报告 + 改进建议。
- **任意年级**：「帮我模拟一场产品岗群面」→ 路由到 `mock`，进入面试陪练，每轮一题 + 反馈卡。

## 当前迭代状态

| 阶段 | 内容 | 状态 |
|------|------|------|
| V0.1 | 基础对话 + 年级路由 | ✅ |
| V0.2 | LangGraph 多 Agent + 工具调用 | ✅ |
| V0.3 | RAG 知识库 + 引用标注 | ✅ |
| V0.4 | 记忆 / 成长档案 / 跨会话 | ✅ |
| V1.0 | Streamlit Cloud 部署 + 对外演示 | ⏳ 待部署 |

## 后续可拓展

- 接入各公司校招官网 RSS / 静态 JSON，让岗位信息按时间窗口动态化。
- 增加"成长里程碑"看板，把 GrowthRecord 可视化。
- 引入 LangGraph Checkpoints 做更长会话的多分支记忆。
