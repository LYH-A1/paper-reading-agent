# 论文阅读 Agent V2 工作进度报告

> 日期：2026-06-19 | 状态：Phase 1 ✅ Phase 2 ✅ Phase 3 ✅ Phase 4a ✅ Phase 4b ✅，全部功能就绪

---

## 一、产出总览

### 设计文档 (docs/superpowers/specs/)

| 文件 | 说明 |
|------|------|
| `2026-06-17-paper-reading-agent-design.md` | V1 废案（11 文件 Streamlit 方案），保留作为设计演进参考 |
| **`2026-06-17-paper-reading-agent-v2-design.md`** | **V2 正式设计文档**（12 章）：数据模型、LangGraph 编排、R0/R1/R2 证据系统、混合 RAG、React 前端、错误处理、4 阶段规划 |
| `2026-06-17-paper-reading-agent-v2-conversation.md` | 设计对话记录：Brainstorming 逐段确认过程，包含用户决策、设计修正、调研发现 |
| **`2026-06-18-paper-reading-agent-v2-phase2-design.md`** | **Phase 2 设计文档**（10 章）：组件架构、SSE 协议、HITL、证据系统、布局 |
| **`2026-06-18-paper-reading-agent-v2-phase3-design.md`** | **Phase 3 设计文档**（7 章）：FlashRank、对话导出、用户偏好 |
| **`2026-06-19-paper-reading-agent-v2-phase4a-design.md`** | **Phase 4a 设计文档**（6 章）：BibTeX 批量导出、FlashRank 重排序可视化 |
| **`2026-06-19-paper-reading-agent-v2-phase4b-design.md`** | **Phase 4b 设计文档**（12 章）：外部检索 (arXiv + Semantic Scholar)、单论文对比分析 |

### 实现计划 (docs/superpowers/plans/)

| 文件 | 说明 |
|------|------|
| **`2026-06-17-paper-reading-agent-v2-plan.md`** | **Phase 1 实现计划**：14 个 Task × 逐步指令，含完整代码、测试用例、commit 信息 |
| **`2026-06-18-paper-reading-agent-v2-phase2-plan.md`** | **Phase 2 实现计划**：11 个 Task × 逐步指令，React 前端 + PDF.js + SSE |
| **`2026-06-18-paper-reading-agent-v2-phase3-plan.md`** | **Phase 3 实现计划**：8 个 Task × 逐步指令，FlashRank + 导出 + 偏好 |
| **`2026-06-19-paper-reading-agent-v2-phase4a-plan.md`** | **Phase 4a 实现计划**：7 个 Task × 逐步指令，BibTeX 导出 + 重排序可视化 |
| **`2026-06-19-paper-reading-agent-v2-phase4b-plan.md`** | **Phase 4b 实现计划**：7 个 Task × 逐步指令，外部检索 + 对比分析 |

### SDD 报告 (paper-reading-agent/.sdd-reports/)

Subagent-Driven Development 过程中每个 Task 生成两份报告：

| 报告类型 | 数量 | 内容 |
|----------|------|------|
| **Task Report** (`task-N-report.md`) | 10 份 | 实施者自述：创建了哪些文件、测试结果、自我审查、关注点 |
| **Task Review** (`task-N-review.md`) | 6 份 | 审查者裁定：Spec 合规性 ✅/❌ + 代码质量 Approved/NeedsFix |

缺少的 Report（Task 3/7 直接手动修复）和 Review（Task 7-14 自我审查或合并）见下方说明。

---

## 二、开发过程

### 阶段 0：设计（2 小时）

1. 读取 V1 废案 + Hello-Agents 第六章教学实验包
2. 调研 GitHub 10+ 开源 Agent 项目（Paperflow、Paipai、GPT Researcher、HaoliangCheng）
3. Brainstorming 逐段确认：差异化定位 → 交付形态 → LLM 后端 → 编排策略 → Agent 角色
4. 提出 4 个架构方案，用户选择融合方案 D
5. 逐段审查：数据模型（发现 5 个缺口）→ LangGraph 编排（2 个关键修正）→ 混合 RAG（3 个修正）→ 前端（可视化伴侣失败，文字推进）→ 错误处理 + 阶段划分（3 个修正）
6. 输出正式设计文档 + 对话记录

### 阶段 1：实现（3 小时）

采用 Subagent-Driven Development 模式：每个 Task 派独立实施者 → 审查者裁定 → 修复循环 → 标记完成。

| Task | 内容 | 文件数 | 测试 | 状态 |
|------|------|--------|------|------|
| 1 | 项目脚手架 | 19 | 2/2 | ✅ |
| 2 | 数据模型 (Paper/Evidence/AgentState) | 3 | 7/7 | ✅ |
| 3 | LLM 客户端 (DeepSeek API) | 2 | 1/1 | ✅ |
| 4 | 提示词模板 (9 组) | 1 | — | ✅ |
| 5 | PDF 解析器 (双引擎) | 4 | 2/2 | ✅ |
| 6 | 文本分块器 | 2 | 4/4 | ✅ |
| 7 | 混合检索器 (BM25+ChromaDB) | 2 | 5/5 | ✅ |
| 8 | SQLite 存储层 | 4 | 3/3 | ✅ |
| 9 | Reader Agent | 1 | — | ✅ |
| 10 | QA Agent | 1 | — | ✅ |
| 11 | Reviewer Agent | 1 | — | ✅ |
| 12 | LangGraph Supervisor | 1 | — | ✅ |
| 13 | FastAPI + 前端 HTML | 2 | — | ✅ |
| 14 | CLI 入口 | 1 | — | ✅ |

**总计**：24 commits，44 文件，2,053+ 行代码，24/24 测试通过。

### 阶段 2：集成调试（1 小时）

DeepSeek API 适配问题修复：

| 问题 | 修复 |
|------|------|
| API 返回 `thinking` + `text` 混合 content 块 | 遍历查找 `type=="text"` 的块 |
| SSE 流式 `delta.type` 为 `text_delta` 而非裸 `text` | 检查 `delta.type == "text_delta"` |
| LangGraph `SqliteSaver` 不支持 async | 切换为 `AsyncSqliteSaver` + `aiosqlite` |
| LangGraph `ainvoke()` 返回 dict 而非 AgentState | 用 `AgentState(**fields)` 重建 |
| generate 无限循环 | observe 上限 3 次 |
| `chat_stream()` 连接不稳定 | 降级为 `chat()` |

### 阶段 2：前端 + SSE + HITL（Phase 2，6 小时）

采用 Subagent-Driven Development 模式。15 commits，75 测试。

| Task | 内容 | 文件数 | 测试 | 状态 |
|------|------|--------|------|------|
| 1 | 项目脚手架 + 类型系统 | 9 | 1/1 | ✅ |
| 2 | API 客户端 | 1 | 2/2 | ✅ |
| 3 | useSSE Hook | 1 | 7/7 | ✅ |
| 4 | PaperViewer (PDF.js) | 5 | 7/7 | ✅ |
| 5 | ChatPanel (StepIndicator/MessageList/ChatInput) | 7 | 2/2 | ✅ |
| 6 | Evidence 系统 (Badge/Popover/Chain) | 4 | 3/3 | ✅ |
| 7 | HITL (PlanApprovalBanner/useApproval) | 3 | 10/10 | ✅ |
| 8 | 布局 (TopBar/Sidebar/ResizableSplit) | 9 | — | ✅ |
| 9 | 后端适配 (SSE/HITL/PDF 端点) | 2 | — | ✅ |
| 10 | 上传流程 + App 集成 | 3 | 8/8 | ✅ |

### 阶段 3：重排序 + 导出 + 偏好（Phase 3，3 小时）

采用 Subagent-Driven Development 模式。9 commits（8 tasks + 1 code review fix），97 测试。

| Task | 内容 | 文件数 | 测试 | 状态 |
|------|------|--------|------|------|
| 1 | Reranker 模块 (FlashRank + BM25) | 2 | 8/8 | ✅ |
| 2 | 集成到 HybridRetriever | 2 | 1/1 | ✅ |
| 3 | SSE 协议更新 (init/done/session) | 4 | 2/2 | ✅ |
| 4 | 导出 API (Markdown/JSON) | 3 | 3/3 | ✅ |
| 5 | 前端导出按钮 + currentSessionId | 6 | 2/2 | ✅ |
| 6 | 偏好 API (GET/PUT) | 2 | 5/5 | ✅ |
| 7 | zustand persist | 2 | 1/1 | ✅ |
| 8 | Settings 面板 | 4 | — | ✅ |

**代码审查发现**：8 个发现，3 个 bug（1 🔴 + 1 🟡 + 1 🟢），全部已修复。

---

## 三、当前状态

### 可用功能

- **CLI**：`python -m backend --paper <pdf> --query "<问题>"`
- **Web**：`http://localhost:8000`（上传 PDF + 对话 + 双栏 PDF 查看 + R0/R1/R2 证据高亮 + HITL 审批）
- **API**：`POST /api/upload`、`GET /api/query`（SSE）、`POST /api/approve`、`GET /api/papers`、`GET /api/pdf/{id}`、`GET /api/pdf/{id}/text`、`GET /api/sessions/{id}/export`、`GET/PUT /api/preferences`
- **Agent**：FlashRank 重排序（可配置）+ BM25 降级
- **导出**：Markdown / JSON 对话导出
- **偏好**：UI 布局持久化 + Agent 参数配置

### 全链路验证结果

```
[ANSWER] The paper proposes a novel method for testing PDF parsers.
[SCORE]  10/10
[TRACE]  reader -> classify -> planner -> retrieve -> generate ->
         observe -> generate -> observe -> generate -> observe -> reviewer -> output
[EVID]   1 items [R0] "The paper proposes a novel method for testing PDF parsers..."
```

### 已知限制

| 问题 | 严重度 | 计划 |
|------|--------|------|
| `chat_stream()` 连接不稳定 | 中 | Phase 2 修复，当前 chat() 兜底 |
| classify JSON 解析偶发失败 | 低 | 关键词兜底已生效 |
| ChromaDB 依赖 `pybase64` 已安装 | — | 已修复 |
| LangGraph msgpack 类型警告 | 低 | 仅日志噪音 |

---

## 四、报告文件说明

### 设计层（docs/superpowers/）

| 路径 | 角色 | 读者 |
|------|------|------|
| `specs/...-v2-design.md` | 技术规格——"要做什么" | 开发者、审查者 |
| `specs/...-v2-conversation.md` | 设计决策追溯——"为什么这样做" | 项目交接、复盘 |
| `plans/...-v2-plan.md` | 实现计划——"怎么做、分几步" | 实施者 |

### 执行层（paper-reading-agent/.sdd-reports/）

| 模式 | 示例 | 角色 |
|------|------|------|
| `task-N-report.md` | "Task 5: 创建了 4 个文件，2 测试通过，自我审查：无问题" | 实施者自述 |
| `task-N-review.md` | "Task 5 审查：8 项检查全部通过，APPROVED" | 独立审查者裁定 |

**注意**：Task 3 的 report 缺失（文件创建到错误路径，手动复制修复）；Task 7-14 的 review 为自我审查（因审查流程耗时，后期合并简化）。

### 数据层

| 路径 | 内容 |
|------|------|
| `.git/sdd/progress.md` | 进度账本——每 Task 完成时追加一行 |
| `data/paper-reading.db` | SQLite 运行时数据库 |
| `outputs/api_log.jsonl` | LLM API 调用日志 |

---

## 五、Phase 2 完成

> 日期：2026-06-18 | 状态：✅ Phase 2 完成

### Phase 2 产出

| 维度 | 内容 |
|------|------|
| **前端** | 33 文件 — Vite + React 18 + TypeScript + PDF.js + zustand |
| **后端** | 2 文件修改 — SSE `astream_events` + HITL interrupt + 新端点 |
| **测试** | 40 前端 + 35 后端 = 75 测试全通过 |
| **Commits** | 15 commits |
| **SDD Reports** | 10 task reports + 10 task reviews (`.git/sdd/`) |

### Phase 2 设计文档 (docs/superpowers/)

| 文件 | 说明 |
|------|------|
| **`specs/2026-06-18-paper-reading-agent-v2-phase2-design.md`** | Phase 2 正式设计文档（10 章）：组件架构、SSE 协议、数据流、HITL、证据系统 |
| **`plans/2026-06-18-paper-reading-agent-v2-phase2-plan.md`** | Phase 2 实现计划：11 个 Task × 逐步指令 |

### Phase 2 新增功能

| 功能 | 详情 |
|------|------|
| **PDF 查看器** | PDF.js Canvas + 透明 TextLayer，支持缩放/翻页/章节导航 |
| **双栏布局** | 可拖拽分隔条，3 种模式（双栏/全宽对话/全宽论文），响应式 <768px |
| **SSE 流式对话** | 两段式 SSE 协议，token 级流式渲染，init/node/token/hitl/done 事件 |
| **证据系统** | R0/R1/R2 三色徽标内联到回答文本，EvidencePopover 悬停 tooltip，R2 推理链递归展示（上限 3 层） |
| **证据高亮跳转** | 点击 R0 徽标 → PDF 切页 + bbox 高亮（quote 文本搜索匹配 → 精确 → 模糊 → 降级） |
| **HITL 计划审批** | PlanApprovalBanner（编辑/批准/取消），条件触发（仅 compare/recommend），两段 SSE 断开重连 |
| **论文上传 & 库** | 拖拽上传 + 文件选择器，论文库 CRUD |
| **StepIndicator** | Show Your Work 步骤条，实时节点状态（✓完成 / ◌进行中 / ○等待） |
| **后端新端点** | `GET /api/query` SSE, `POST /api/approve`, `GET /api/pdf/{id}`, `GET /api/pdf/{id}/text` |

### 已知问题（已修复）

| 问题 | 严重度 | 状态 |
|------|--------|------|
| TypeScript 严格空检查警告（canvas refs） | 低 | ✅ 已修复 (ef8323c) |
| `pdfjs-dist` 类型导出不匹配 | 低 | ✅ 已修复 (ef8323c) |
| R2 推理链高亮首屏竞态 | 低 | ✅ 已修复 (ef8323c) |
| LayoutToggle 按钮缺少 aria-label | 低 | ✅ 已修复 (ef8323c) |
| session_id/thread_id 碰撞 (Segment 2) | 🔴 严重 | ✅ 已修复 (bba480f) |
| RerankerLoadError 死代码 | 🟡 重要 | ✅ 已修复 (bba480f) |
| null confidence 导出崩溃 | 🟢 次要 | ✅ 已修复 (bba480f) |

---

## 六、Phase 3 完成

> 日期：2026-06-19 | 状态：✅ Phase 3 完成

### Phase 3 产出

| 维度 | 内容 |
|------|------|
| **FlashRank 重排序** | 新建 `backend/tools/reranker.py`（Reranker 接口 + FlashRankReranker 懒加载 + BM25FallbackReranker + 工厂函数），集成到 `HybridRetriever` |
| **对话导出** | `GET /api/sessions/{id}/export?format=md|json`，Markdown 含 evidence/quality/followups，JSON 含完整结构化数据，ChatPanel 导出按钮 |
| **用户偏好** | zustand persist（UI 状态持久化）+ `GET/PUT /api/preferences`（Agent 偏好：reranker/top_k/language/embedding_model），Sidebar Settings 面板 |
| **SSE 协议增强** | init 事件增加 `session_id`，done 事件扩展 quality_score(4 字段)+followup_questions+完整 evidence_list，消息自动记录到 SQLite |
| **测试** | 97 全部通过（54 后端 + 43 前端） |
| **Commits** | 9 commits（8 tasks + 1 code review fix） |

### Phase 3 设计文档 (docs/superpowers/)

| 文件 | 说明 |
|------|------|
| **`specs/2026-06-18-paper-reading-agent-v2-phase3-design.md`** | Phase 3 正式设计文档：FlashRank、导出、偏好 |
| **`plans/2026-06-18-paper-reading-agent-v2-phase3-plan.md`** | Phase 3 实现计划：8 个 Task × 逐步指令 |

---

## 七、Phase 4a 完成

> 日期：2026-06-19 | 状态：✅ Phase 4a 完成

### Phase 4a 产出

| 维度 | 内容 |
|------|------|
| **BibTeX 批量导出** | DB 迁移（references 列）→ PDF 解析器提取参考文献（DOI/arXiv/括号引用）→ API `GET /api/papers/{id}/references/export` → ChatPanel 导出下拉 .bib 按钮 |
| **FlashRank 重排序可视化** | Reranker ABC 增加 `name`/`model_name` 属性 → retrieve_node 结构化 trace → SSE done 事件扩展 `reranker_used` + `reranker_summary` → 前端 DoneEvent 类型更新 |
| **测试** | 117 全部通过（74 后端 + 43 前端） |
| **Commits** | 7 commits |

### Phase 4a 开发过程

采用 Subagent-Driven Development 模式。

| Task | 内容 | 文件数 | 测试 | 状态 |
|------|------|--------|------|------|
| 1 | DB migration + PaperStore 持久化 references | 3 | 5 | ✅ |
| 2 | PDF 解析器参考文献提取（DOI/arXiv/括号引用） | 2 | 7 | ✅ |
| 3 | BibTeX 导出 API | 2 | 6 | ✅ |
| 4 | 前端 BibTeX 导出按钮 | 2 | 43 | ✅ |
| 5 | Reranker ABC name/model_name 属性 | 2 | 13 | ✅ |
| 6 | retrieve_node trace + done SSE 扩展 | 3 | 17 | ✅ |
| 7 | 前端 DoneEvent 类型更新 | 1 | 43 | ✅ |

### Phase 4a 设计文档 (docs/superpowers/)

| 文件 | 说明 |
|------|------|
| **`specs/2026-06-19-paper-reading-agent-v2-phase4a-design.md`** | Phase 4a 正式设计文档：BibTeX 导出、FlashRank 可视化 |
| **`plans/2026-06-19-paper-reading-agent-v2-phase4a-plan.md`** | Phase 4a 实现计划：7 个 Task × 逐步指令 |

### 最终审查结果

全分支代码审查：0 Critical，0 Important，2 Minor（exportReferences 静默吞错 + slugify 重复）。

---

## 八、Phase 4b 完成

> 日期：2026-06-19 | 状态：✅ Phase 4b 完成

### Phase 4b 产出

| 维度 | 内容 |
|------|------|
| **外部检索** | 新建 `external_search.py`（ExternalResult + ExternalRetriever）→ arXiv API 主检索（Atom XML 解析）→ Semantic Scholar 补充引用数/相关论文 → 三级降级策略（超时/429/失败） |
| **对比分析** | LangGraph 新增 `external_search` 节点 → planner 路由 → retrieve 之后条件执行 → generate_node 融合 [EXT-N] 双源证据 → observe 感知外部结果充分性 → retry loop |
| **前端** | StepIndicator 新增 `external_search` 步骤 → EvidencePopover R1 证据显示 "View on arXiv ↗" → chatStore 持久化 externalResults |
| **测试** | 128 全部通过（85 后端 + 43 前端） |
| **Commits** | 7 commits |

### Phase 4b 开发过程

采用 Subagent-Driven Development 模式。

| Task | 内容 | 文件数 | 测试 | 状态 |
|------|------|--------|------|------|
| 1 | ExternalResult + ExternalRetriever 模块（arXiv XML + S2） | 2 | 7 | ✅ |
| 2 | AgentState + Evidence 外部检索字段 | 2 | 9 | ✅ |
| 3 | Config + Prompts（S2_API_KEY + SEARCH_QUERY_PROMPT） | 2 | — | ✅ |
| 4 | external_search_node + _build_search_query + route | 1 | — | ✅ |
| 5 | generate_node + observe_node + check_observe_result | 1 | — | ✅ |
| 6 | supervisor.py 图集成 + SSE + done payload | 2 | 6 | ✅ |
| 7 | 前端 types + chatStore + EvidencePopover + StepIndicator | 7 | 43 | ✅ |

### Phase 4b 设计文档 (docs/superpowers/)

| 文件 | 说明 |
|------|------|
| **`specs/2026-06-19-paper-reading-agent-v2-phase4b-design.md`** | Phase 4b 正式设计文档：外部检索、对比分析 |
| **`plans/2026-06-19-paper-reading-agent-v2-phase4b-plan.md`** | Phase 4b 实现计划：7 个 Task × 逐步指令 |

### 最终审查结果

全分支代码审查：0 Critical，0 Important，0 Minor。实现干净，无正确性 bug。

---

## 九、下一步

| 阶段 | 内容 | 预估 |
|------|------|------|
| Phase 5 | 论文库多选对比、外部结果"保存到论文库"、BibTeX 导入等 | 后续 |
