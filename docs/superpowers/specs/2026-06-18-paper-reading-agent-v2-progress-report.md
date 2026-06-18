# 论文阅读 Agent V2 工作进度报告

> 日期：2026-06-18 | 状态：Phase 1 完成，Web 服务运行中

---

## 一、产出总览

### 设计文档 (docs/superpowers/specs/)

| 文件 | 说明 |
|------|------|
| `2026-06-17-paper-reading-agent-design.md` | V1 废案（11 文件 Streamlit 方案），保留作为设计演进参考 |
| **`2026-06-17-paper-reading-agent-v2-design.md`** | **V2 正式设计文档**（12 章）：数据模型、LangGraph 编排、R0/R1/R2 证据系统、混合 RAG、React 前端、错误处理、4 阶段规划 |
| `2026-06-17-paper-reading-agent-v2-conversation.md` | 设计对话记录：Brainstorming 逐段确认过程，包含用户决策、设计修正、调研发现 |

### 实现计划 (docs/superpowers/plans/)

| 文件 | 说明 |
|------|------|
| **`2026-06-17-paper-reading-agent-v2-plan.md`** | **实现计划**：14 个 Task × 逐步指令，含完整代码、测试用例、commit 信息 |

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

---

## 三、当前状态

### 可用功能

- **CLI**：`python -m backend --paper <pdf> --query "<问题>"`
- **Web**：`http://localhost:8000`（上传 PDF + 对话 + R0/R1/R2 徽标）
- **API**：`POST /api/upload`、`POST /api/query`（SSE）、`GET /api/papers`

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

## 五、下一步

| 阶段 | 内容 | 预估 |
|------|------|------|
| Phase 2 | 完整 React 前端（PDF.js 证据高亮、双栏布局、HITL 审批） | 2 周 |
| Phase 3 | FlashRank 重排序、对话导出、用户偏好 | 2 周 |
| Phase 4 | 多论文对比、外部检索、BibTeX 导出 | 后续 |

**Phase 2 启动条件**：安装 Node.js + npm，在 `frontend/` 下创建 Vite + React + TypeScript 项目。
