# 未来鹅

腾讯 AI-HR 培训营 Day4 作业「未来鹅 · 大学生职业成长 AI 陪伴体」的完整项目目录。

## 目录结构

- [`未来鹅_设计方案.md`](./未来鹅_设计方案.md) — 完整设计方案（架构、Agent 职责、技术选型、迭代计划、效果评估）
- [`weilai-e/`](./weilai-e/) — 可运行实现（Streamlit + LangGraph 多 Agent + RAG）
  - 详细启动方式见 [`weilai-e/README.md`](./weilai-e/README.md)

## 当前状态

V0.1–V0.4 已完成（基础对话、多 Agent 路由、RAG 知识库、跨会话记忆），V1.0 公网部署待启动。

## 备份说明

本仓库用于备份设计文档与代码，避免本地数据丢失。前后端分离改造（按设计方案 §3.1 中 FastAPI + Streamlit 的形态落地）将在新的 feature 分支推进。
