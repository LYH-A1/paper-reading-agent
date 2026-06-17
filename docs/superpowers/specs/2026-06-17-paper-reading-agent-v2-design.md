# 论文阅读 Agent V2 设计文档

> 版本：v2.0 | 日期：2026-06-17 | 状态：已确认
> 前身：[V1 废案](2026-06-17-paper-reading-agent-design.md)

---

## 一、设计目标

对标业界优秀开源 Agent 项目，构建一个**证据可追溯、多 Agent 协作、全流程**的论文阅读智能体。

### 核心差异化

| 维度 | 目标 | 参考来源 |
|------|------|----------|
| 证据溯源 | 每句话标注 R0/R1/R2 评级，可追溯到 PDF 页码/bbox | [Paperflow](https://github.com/shiml20/Paperflow) |
| 多 Agent 编排 | 3 Agent（Reader/QA/Reviewer）LangGraph 图式协作 | [Paipai](https://github.com/sunshijun-ctr/paipai) + [GPT Researcher](https://github.com/assafelovic/gpt-researcher) |
| 质量闭环 | Review-Revision 循环，不达标重答（最多 2 次） | GPT Researcher |
| 阶段路由 | 根据问题类型动态选择阅读深度（方法/数学/代码） | [HaoliangCheng/paper-reading-agent](https://github.com/HaoliangCheng/paper-reading-agent) |
| 混合 RAG | ChromaDB + BM25 + FlashRank 三路检索 | Paipai |
| Human-in-the-Loop | 执行计划审批，LangGraph 检查点持久化 | Paipai |

### 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + PDF.js |
| 后端 | FastAPI + WebSocket/SSE |
| Agent 编排 | LangGraph StateGraph（核心循环）+ 自定义轻量执行器（工具层） |
| LLM | DeepSeek API（Anthropic 协议），单模型 |
| 向量检索 | ChromaDB + BM25 + FlashRank |
| PDF 解析 | PyMuPDF（主）+ pdfplumber（备） |
| 存储 | SQLite（元数据/对话）+ 文件系统（PDF/缓存） |
| 状态持久化 | SQLite Checkpointer（LangGraph 原生） |

---

## 二、项目结构

```
paper-reading-agent/
├── backend/
│   ├── app.py                    # FastAPI 入口 + WebSocket/SSE
│   ├── config.py                 # 环境变量、常量
│   ├── agents/
│   │   ├── supervisor.py         # LangGraph SuperGraph 编排器
│   │   ├── reader.py             # Reader Agent（报告生成）
│   │   ├── qa.py                 # QA Agent（Plan-Execute-Observe）
│   │   └── reviewer.py           # Reviewer Agent（R0/R1/R2 + 质量门控）
│   ├── tools/
│   │   ├── pdf_parser.py         # PyMuPDF + pdfplumber 双引擎
│   │   ├── retriever.py          # 混合 RAG（ChromaDB + BM25 + FlashRank）
│   │   ├── citation_search.py    # 外部引用检索（arXiv/Semantic Scholar，v2）
│   │   └── registry.py           # 工具注册中心
│   ├── models/
│   │   ├── paper.py              # Paper, Section, Figure 数据模型
│   │   ├── state.py              # AgentState, Evidence, QualityScore 数据模型
│   │   └── api.py                # 请求/响应 Pydantic 模型
│   ├── llm/
│   │   ├── client.py             # DeepSeek API 封装（流式+重试+日志）
│   │   └── prompts.py            # 全部提示词模板
│   ├── storage/
│   │   ├── database.py           # SQLite 操作层
│   │   ├── paper_store.py        # 论文库 CRUD
│   │   └── session_store.py      # 对话历史 CRUD
│   └── utils/
│       ├── text_splitter.py      # 智能分块（1000字/块，200字重叠，保持章节边界）
│       └── logger.py             # 结构化日志
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── PaperViewer.tsx       # PDF 渲染 + 证据高亮
│   │   │   ├── ChatPanel.tsx         # 对话流
│   │   │   ├── EvidenceBadge.tsx     # R0/R1/R2 徽标
│   │   │   ├── EvidencePopover.tsx   # 引用悬停预览（原文 + 跳转按钮）
│   │   │   ├── StepIndicator.tsx     # Show Your Work 步骤条
│   │   │   ├── TracePanel.tsx        # 思考链路展开面板
│   │   │   ├── FollowUpSuggest.tsx   # 追问建议按钮
│   │   │   ├── LibraryPanel.tsx      # 论文库侧栏
│   │   │   └── LayoutToggle.tsx      # 布局切换（双栏/全宽对话/全宽论文）
│   │   ├── hooks/
│   │   │   ├── useSSE.ts             # SSE 流式接收
│   │   │   └── usePDFJump.ts         # PDF 页码跳转 + bbox 高亮
│   │   └── types/index.ts
│   ├── package.json
│   └── vite.config.ts
├── data/                          # 运行时数据
│   ├── papers/                    # 上传的 PDF 文件
│   ├── reports/                   # Reader 生成的 JSON 报告
│   └── paper-reading.db           # SQLite 数据库
├── outputs/                       # 导出制品（trace、API log、会话导出）
├── requirements.txt
└── README.md
```

**与 V1 废案的关键变化：**
- 前端 Streamlit → React + TypeScript，支持 PDF.js 证据高亮
- Agent 单文件 `agent_core.py` → 3 独立 Agent + Supervisor
- 检索 TF-IDF → ChromaDB + BM25 + FlashRank
- 新增 Evidence 数据模型支撑 R0/R1/R2
- LangGraph 替代手写状态机

---

## 三、核心数据模型

### 3.1 论文模型

```python
@dataclass
class Section:
    heading: str                       # "3. Method"
    content: str
    page_start: int
    page_end: int
    bbox: tuple | None                 # PDF 坐标（整个章节）

@dataclass
class Figure:
    caption: str
    page: int
    bbox: tuple
    image_base64: str | None

@dataclass
class Paper:
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    sections: list[Section]
    figures: list[Figure]
    references: list[Reference]        # 结构化引用列表
    metadata: dict                     # 期刊、年份、DOI、arXiv ID
    raw_text: str
    language: str                      # "zh" | "en"
    file_path: str
    parsed_at: str
```

### 3.2 证据模型（R0/R1/R2）

```python
class EvidenceLevel(Enum):
    R0 = "R0"  # 严格来自当前论文，可定位到具体页码+bbox
    R1 = "R1"  # 来自外部来源，记录来源元数据
    R2 = "R2"  # 推论/判断/研究意见

@dataclass
class Evidence:
    evidence_id: str                    # UUID

    # 回答文本中的定位锚点
    claim: str                          # 原文陈述句
    sentence_index: int | None          # answer 中第几句话
    char_start: int | None             # answer 字符偏移 [start, end)
    char_end: int | None

    level: EvidenceLevel                # R0 / R1 / R2

    # R0 专属
    page: int | None                    # 页码
    quote: str | None                   # 原文引用
    quote_span: tuple | None           # 在段落中的字符偏移
    section_heading: str | None         # 所属章节

    # R1 专属
    source_title: str | None
    source_url: str | None
    source_venue: str | None
    source_year: int | None

    # R2 专属
    reasoning: str | None               # 推理过程
    based_on_evidence_ids: list[str]    # 引用的其他 Evidence ID

    # 通用
    confidence: float                   # 0.0-1.0
    claim_group_id: str | None          # 多证据支撑同一 claim 时分组
```

### 3.3 质量评分 & 状态

```python
@dataclass
class QualityScore:
    relevance: int                     # 0-3 切题度
    consistency: int                   # 0-4 原文一致性（无幻觉）
    completeness: int                  # 0-3 关键信息覆盖率

    @property
    def total(self) -> int:            # 动态计算，不存储
        return self.relevance + self.consistency + self.completeness

@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    page: int
    section_heading: str
    source: str                        # "bm25" | "dense" | "rerank"
    scores: dict[str, float]           # 各路原始分数

@dataclass
class AgentState:
    paper: Paper | None
    report: dict | None                # Reader 生成的 JSON 报告
    retriever: HybridRetriever | None  # 索引缓存（reader 构建一次）

    user_query: str
    intent: str

    plan: dict | None                  # 执行计划
    plan_feedback: str | None          # HITL 反馈
    observation: dict | None           # observe 自检结果

    retrieved_chunks: list[RetrievedChunk]
    answer: str
    evidence_list: list[Evidence]

    quality_score: QualityScore | None
    rewrite_count: int

    trace: list[str]
    error: str | None
```

---

## 四、LangGraph Agent 编排

### 4.1 状态机图

```
[reader] → [classify] → [planner] ─(interrupt_after)─→ [retrieve]
                                                              │
                    ┌─────────────────────────────────────────┘
                    ▼
              [generate] → [observe]
                    │           │
                    │   sufficient│insufficient
                    │           │
                    │   plan_valid│not plan_valid
                    │           │
                    ▼           ▼
              [reviewer]   [retrieve/planner]
                    │
              [should_loop]
               │        │
         score≥7    score<7 & count<2
               │        │
          [output]   [rewrite] → 回 [generate]
```

### 4.2 节点职责

| 节点 | Agent | 职责 |
|------|-------|------|
| reader | Reader | PDF 解析 + 结构化报告生成 + 构建检索索引（仅一次） |
| classify | QA | 意图分类（summary/qa/compare/recommend） |
| planner | QA | 生成执行计划 → LangGraph 暂停等用户审批 |
| retrieve | QA | 混合 RAG 检索（复用 reader 缓存的索引） |
| generate | QA | LLM 流式生成回答 |
| observe | QA | 自检：计划有效性 + 回答充分性 |
| reviewer | Reviewer | R0/R1/R2 证据标注 + 3 维质量评分 |
| rewrite | — | 将 reviewer 扣分原因反馈注入 prompt |
| output | — | 格式化输出 + 追问建议生成 |

### 4.3 条件边逻辑

| 条件边 | 判断 | 分支 |
|--------|------|------|
| `observe → ?` | `plan_valid=False` → planner；`sufficient=False` → retrieve；`sufficient=True` → reviewer |
| `should_loop → ?` | `total ≥ 7` 或 `rewrite_count ≥ 2` → output；否则 → rewrite |

### 4.4 Human-in-the-Loop

```python
graph.compile(
    interrupt_after=["planner"],       # planner 生成计划后暂停
    checkpointer=SqliteSaver(db_path)
)
# 用户批准 → graph.invoke(None, config) 恢复
# 用户拒绝 → 更新 plan_feedback → 回跳 planner 重生成
```

---

## 五、混合 RAG 检索层

### 5.1 架构

```
PDF文本 → 智能分块 → [BM25 索引 / ChromaDB 索引]（并行，仅构建一次）
                          │
                    查询时并行检索
                          │
                    FlashRank 重排序（top-20 → top-5）
```

### 5.2 关键设计

- **索引构建前置**：reader 节点构建一次，缓存到 `AgentState.retriever`
- **三路互补**：BM25 保证术语不漏 + ChromaDB 捕获语义 + FlashRank 最终仲裁
- **合并阶段不做跨尺度排序**：BM25 和 dense 分数不可比，交 FlashRank 统一打分
- **查询翻译**：英文论文中文查询时，用 LLM 翻译查询词（零额外依赖，学术术语更准）
- **分词适配**：按论文语言选择 jieba（中文）/ nltk（英文）
- **embedding 模型**：`all-MiniLM-L6-v2`（英文）/ `BAAI/bge-large-zh`（中文），按论文语言切换

### 5.3 降级策略

| 场景 | 策略 |
|------|------|
| 检索结果为空 | 降级为论文摘要全文 |
| top-5 平均相关度 < 0.3 | 扩大为 top-10 |
| ChromaDB 崩溃 | 自动降级为纯 BM25 |
| FlashRank 不可用 | 按 BM25 分数排序 |

---

## 六、前端架构

### 6.1 组件树

```
App.tsx
├── LeftPanel: PaperViewer
│   ├── SectionNav（章节导航）
│   ├── PDFRenderer（pdf.js + 证据高亮叠层）
│   └── SearchBar（论文内全文搜索）
├── RightPanel: ChatPanel
│   ├── StepIndicator（Show Your Work 步骤条）
│   ├── PlanApprovalBanner（HITL 审批）
│   ├── MessageList
│   │   ├── UserMessage
│   │   └── AssistantMessage
│   │       ├── AnswerText（含 EvidenceBadge 内联渲染）
│   │       ├── EvidencePopover（悬停 tooltip + 跳转按钮）
│   │       ├── QualityBar（评分 + R0/R1/R2 计数）
│   │       ├── TracePanel（折叠思考链路）
│   │       └── FollowUpSuggest（追问按钮组）
│   └── ChatInput
├── Sidebar（抽屉式）
│   ├── LibraryPanel（论文库）
│   ├── HistoryPanel（对话历史）
│   └── SettingsPanel（用户偏好）
└── LayoutToggle（双栏/全宽对话/全宽论文）
```

### 6.2 证据高亮交互流

```
1. Reviewer 返回 evidence_list（含 page + sentence_index + char_span）
2. ChatPanel 在 answer Markdown 的 char_span 位置插入 <EvidenceBadge level={R0}>
3. 点击 R0 徽标：
   → PaperViewer 切换页面 + PDF 高亮（bbox 叠层）
   → EvidencePopover 弹出原文引用
4. 悬停 R2 徽标：
   → EvidencePopover 展示推理链：R2 ← [R0(#3), R0(#5)]
   → 递归展开依赖的证据
```

### 6.3 关键 UX 模式

- **Show Your Work**：步骤指示器实时显示节点状态（借鉴 Claude Code）
- **3 种布局切换**：双栏（默认）/ 全宽对话 / 全宽论文（借鉴 ChatGPT Canvas + Kimi）
- **追问建议**：每次回答后自动生成 3 个追问按钮
- **思考链路折叠**：可展开查看完整 trace
- **坡度式降级**：警告横幅而非阻断弹窗

---

## 七、错误处理 & 性能

### 7.1 三级错误体系

| 级别 | 说明 | 示例 |
|------|------|------|
| L1 | 自动恢复，用户无感知 | 引擎切换、重试、规则兜底 |
| L2 | 降级展示，流程继续 | 低置信度标注、部分结果展示 |
| L3 | 硬中断，需用户干预 | 非 PDF 文件、双引擎失败 |

### 7.2 各节点错误处理

| 节点 | 错误 | 级别 | 策略 |
|------|------|------|------|
| reader | 非 PDF | L3 | 立即拒绝 |
| | 单引擎失败 | L1 | 自动切换备用引擎 |
| | 双引擎均失败 | L3 | "无法解析" |
| | 文本 < 100 字 | L2 | "可能扫描版"，仍允许追问 |
| | 超时 >60s | L2 | 截断前 30 页 |
| classify | LLM JSON 不规范 | L1 | 关键词规则兜底 |
| | LLM 超时 | L1 | 重试 2 次 |
| planner | 生成失败 | L1 | 默认计划 |
| retrieve | 结果为空 | L2 | 降级摘要全文 |
| | ChromaDB 崩溃 | L1 | 降级纯 BM25 |
| generate | 流式中断 | L1 | 保留已生成草稿，后台重试完整生成后替换 |
| observe | 超时 | L1 | 默认 `sufficient=False`，强制进 reviewer 兜底 |
| reviewer | 标注不完整 | L2 | 未标默认 R2 + 提示 |
| | 评分 JSON 失败 | L1 | 默认 5/10，强制 rewrite |
| LLM 429/500 | 限流 | L2 | 提示"服务繁忙，30s 后重试" + 指数退避 3 次 |

### 7.3 节点超时预算

| 节点 | 超时 | 超时行为 |
|------|------|----------|
| reader | 60s | 截断 30 页 |
| classify | 5s | 规则兜底 |
| planner | 10s | 默认计划 |
| retrieve | 3s | 返回已检索部分 |
| generate | 60s | 保留草稿，后台重试 |
| observe | 5s | `sufficient=False` |
| reviewer | 15s | 默认 5/10 |

### 7.4 性能目标

| 操作 | 目标 | 优化手段 |
|------|------|----------|
| 页面首屏 | < 2s | React lazy + 代码分包 |
| 论文解析 | < 5s | PyMuPDF + 进度条 |
| 二次加载（缓存命中） | < 0.2s | JSON 缓存 |
| 意图分类 | < 2s | 短 prompt |
| 混合检索 | < 0.15s | 双索引预构建 |
| 首 token | < 1.5s | DeepSeek 流式 |
| 完整回答 | 5-15s | 流式渲染 |
| 质量评估 | < 3s | 短 prompt |
| 切换论文 | < 0.5s | 缓存 + 懒加载 |

---

## 八、依赖清单

```
# 核心
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
langgraph>=0.2.0
langgraph-checkpoint-sqlite>=1.0.0

# LLM
httpx>=0.27.0
python-dotenv>=1.0.1
pydantic>=2.7.0

# PDF
PyMuPDF>=1.24.0
pdfplumber>=0.11.0

# 检索
chromadb>=0.5.0
rank-bm25>=0.2.2
flashrank>=0.2.0
sentence-transformers>=3.0.0

# 存储
aiosqlite>=0.20.0

# 前端（独立 package.json）
# react, pdfjs-dist, react-markdown, @tanstack/virtual
```

---

## 九、开发阶段

### Phase 1：核心引擎 MVP（2 周）

```
交付物：
├── backend/config.py
├── backend/llm/client.py
├── backend/llm/prompts.py
├── backend/tools/pdf_parser.py
├── backend/tools/retriever.py     # 不含 FlashRank
├── backend/models/paper.py
├── backend/models/state.py
├── backend/agents/supervisor.py
├── backend/agents/reader.py
├── backend/agents/qa.py
├── backend/agents/reviewer.py
├── backend/storage/database.py
├── frontend/（最简单页）            # 仅验证 SSE + EvidenceBadge 渲染
└── CLI 入口

验证：python -m backend.cli --paper sample.pdf --query "..."
输出：完整 trace + evidence_list
```

### Phase 2：Web 应用（2 周）

```
交付物：
├── frontend/*                     # 完整 React 应用
├── backend/app.py                 # FastAPI + SSE
└── backend/api/*

功能：PDF 上传、双栏对话、SSE 流式、R0/R1/R2 渲染、思考链路、追问、论文库 CRUD
```

### Phase 3：进阶特性（2 周）

```
- FlashRank 重排序接入
- Human-in-the-Loop 审批
- PDF 证据高亮跳转（pdf.js bbox 定位）
- 对话历史导出（Markdown / Obsidian）
- 用户偏好持久化
```

### Phase 4：扩展（后续）

```
- 多论文对比分析
- 外部检索（arXiv / Semantic Scholar）
- 图表/公式 OCR
- BibTeX / APA 导出
```

---

## 十、UX 参考来源

| 产品 | 借鉴内容 |
|------|----------|
| Paperflow | R0/R1/R2 证据评级 + report-first 理念 |
| ChatGPT Canvas | 双栏可调布局 |
| Perplexity | 内联引用标注 + 追问建议 + 悬停 tooltip |
| Claude Code | Show Your Work 步骤指示器 + 思考链路展开 |
| Kimi | 侧边章节导航 + 长文滚动 |

---

## 十一、模块依赖关系

```
app.py ───→ supervisor.py ───→ reader.py
                │                  ├──→ pdf_parser.py
                ├──→ qa.py ────────├──→ retriever.py
                │   ├──→ llm/client.py ──→ config.py
                │   └──→ prompts.py
                ├──→ reviewer.py ──├──→ models/state.py
                │                  └──→ prompts.py
                └──→ storage/ ─────├──→ models/paper.py
                                   └──→ models/api.py
```

---

## 十二、设计决策记录

| 决策 | 选择 | 排除方案 | 理由 |
|------|------|----------|------|
| Agent 编排 | LangGraph + 自定义工具层 | 纯 LangGraph / 纯手写 | 复杂编排用 LangGraph，简单工具不走图 |
| Agent 数量 | 3（Reader/QA/Reviewer） | 5-6 / 动态生成 | 3 个职责清晰，覆盖核心链路，后续可扩展 |
| LLM 后端 | DeepSeek 单模型 | 多模型可插拔 / 混合编排 | 用户已有 API，单模型简化运维 |
| 前端框架 | React + TypeScript | Streamlit / Gradio | PDF.js 证据高亮需要前端精细控制 |
| 检索方案 | ChromaDB + BM25 + FlashRank | 纯 TF-IDF / 纯 dense | 三路互补，FlashRank ~50ms 开销占比 <2% |
| 存储方案 | SQLite + 文件系统 | PostgreSQL / 纯文件 | 单用户场景 SQLite 足够，本地优先 |
| 交付形态 | Web 应用 | 桌面应用 / CLI | 对标 Paperflow 双前端模式 |
