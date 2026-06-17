# 论文阅读 Agent V2 设计对话记录

> 日期：2026-06-17 | 方法：Brainstorming 逐段确认 | 结果：[设计文档](2026-06-17-paper-reading-agent-v2-design.md)

---

## 对话 1：确定方向

**我**：你希望这个 Agent 的核心差异化竞争力是什么？

- A：Paperflow 级的证据溯源系统
- B：Paipai 级的多 Agent 协作系统
- C：全流程学术工作站
- D：以上都要

**用户**：D

---

## 对话 2：交付形态

**我**：Web 应用 / 纯 Python Web / 桌面应用 / 核心引擎+CLI？

**用户**：A（Web 应用 — React 前端 + FastAPI 后端）

---

## 对话 3：LLM 后端

**我**：只用 DeepSeek / 多模型可插拔 / 多模型混合编排？

**用户**：A（只用 DeepSeek）

---

## 对话 4：Agent 编排策略

**我**：LangGraph / 手写图执行器 / 混合模式？

**用户**：C（混合模式 — LangGraph 核心循环 + 轻量执行器工具层）

---

## 对话 5：Agent 数量 & 角色

**我**：3 Agent / 5-6 Agent / 动态 Agent 工厂？

**用户**：A（3 Agent — Reader / QA / Reviewer）

---

## 对话 6：确认方向 → 出方案

**我**（给出初版三个方案）：Hub-and-Spoke / Peer-to-Peer / Pipeline+Supervisor，推荐方案 3

**用户**：是否有参考过资料中那些公开 agent 智能体的架构？

**我**：诚实承认没有深入拆解，立刻补充调研 Paperflow、Paipai、GPT Researcher、HaoliangCheng/paper-reading-agent 的真实架构

**调研结论**：

| 项目 | 核心架构 | 最值得借鉴 |
|------|----------|-----------|
| Paperflow | "Report first, chat second, evidence always" | R0/R1/R2 三级证据 + Prompt Contract |
| Paipai | 9 Agent + 8 LangGraph 工作流 + 双层路由 | Hybrid RAG + HITL + Postgres Checkpoint |
| GPT Researcher | 8 Agent StateGraph，Review-Revision 循环 | 质量闭环是核心引擎 |
| HaoliangCheng | 6 阶段流水线 + Stage Router + Plan-Execute-Observe | 阶段路由 + P-E-O 循环 |

**我**（给出四个方案，推荐融合方案 D）：

| 来源 | 借鉴什么 | 放在哪里 |
|------|----------|----------|
| Paperflow | R0/R1/R2 + Prompt Contract | Reviewer Agent |
| Paipai | LangGraph + Hybrid RAG + HITL | 编排层 + 检索层 |
| GPT Researcher | Review-Revision 循环 | Reviewer ↔ QA 闭环 |
| HaoliangCheng | Stage Router + P-E-O | QA Agent |
| Claude Agent Framework | Critic-Actor | 嵌套 Agent 关系 |

**用户**：没问题

---

## 对话 7：技术栈 & 项目结构 → 确认

**用户**：没问题

---

## 对话 8：核心数据模型 & 证据系统 → 审查

**我**：给出 Evidence 模型（R0/R1/R2）、AgentState、R0/R1/R2 评级规则

**关键发现（5 个缺口）**：
1. Evidence 无法定位到 Answer 中的句子（最致命）
2. R2 缺少推理链
3. 缺少 Evidence ID
4. R0 bbox 粒度不匹配（Section bbox ≠ 引用句子 bbox）
5. AgentState.retrieved_chunks 类型太松散

**修正**：增加 `sentence_index`、`char_start`/`char_end`、`evidence_id`、`reasoning`、`based_on_evidence_ids`、`quote_span`、`RetrievedChunk` dataclass

**用户**：下一步

---

## 对话 9：LangGraph Agent 编排 → 审查

**我**：给出 10 节点 StateGraph（reader → classify → planner → retrieve → generate → observe → reviewer → should_loop → output/rewrite）、Human-in-the-Loop 设计、流式策略

**用户指出两个关键问题**：
1. observe → planner 回跳破坏了 Plan-Execute-Observe 语义，应改为 observe → retrieve（补充检索），仅 plan 本身无效时才回 planner
2. `interrupt_before=["planner"]` 时机错误，应为 `interrupt_after=["planner"]`

**修正**：拆分 observe 输出为 `plan_valid` + `sufficient`，条件边改为三路（planner / retrieve / reviewer）；`interrupt_before` 改为 `interrupt_after`

**用户**：确认继续

---

## 对话 10：混合 RAG 检索层 → 审查

**我**：给出 ChromaDB + BM25 + FlashRank 三路检索设计

**用户指出三个修正**：
1. 索引构建应前置到 reader 节点（避免每次 retrieve 重建，浪费 ~0.5s）
2. 合并阶段不做跨尺度排序（BM25 log 概率 ≠ dense cosine，交 FlashRank 统一打分）
3. `googletrans` 替换为 LLM 翻译（学术术语更准，零额外依赖）

**修正**：reader_node 构建 `state.retriever`；`_merge_results` 只去重不排序；分词器按论文语言切换；embedding 模型按语言选择

**用户**：确认

---

## 对话 11：前端架构 → 可视化伴侣失败

**用户**：需要可视化伴侣，但文字描述也需要

**我**：启动可视化伴侣服务器，创建双栏布局 + R0/R1/R2 徽标 + 步骤指示器 mockup

**问题**：第一次启动服务器进程被回收，第二次端口已监听但用户反馈"又慢又卡打不开"

**决定**：放弃可视化伴侣，继续文字推进

**我**：给出完整前端组件树、证据高亮交互流、关键技术选型、性能目标、UX 参考来源

---

## 对话 12：错误处理 & 阶段划分 → 审查

**我**：给出三级错误体系 + 全链路超时预算 + Phase 1-4 阶段划分

**用户指出三个修正**：
1. generate 流式中断"保留已生成 + 重试剩余"不可行（LLM 无法从断点续生成），改为：保留草稿展示，后台重试完整生成后替换
2. observe 超时默认 `sufficient=True` 过于乐观，改为 `sufficient=False` 强制进 reviewer 兜底
3. 缺少 LLM 429/500 限流错误的 L2 处理，增加：提示"服务繁忙" + 指数退避 3 次

**Phase 划分建议**：
- Phase 1 应包含最简前端（否则 SSE 流式和 R0/R1/R2 渲染无法验证）
- Phase 3 1 周过于激进，建议改为 2 周

---

## 设计完成 → 写入文档

所有段落确认完毕后，写入完整设计文档到 `docs/superpowers/specs/2026-06-17-paper-reading-agent-v2-design.md`（12 章，覆盖模型/编排/检索/前端/错误/性能/阶段/TechStack）。

自检通过：无 TBD、内部一致、范围聚焦、无歧义。
