# 论文阅读 Agent V2 — Phase 5 设计文档

> 日期：2026-06-19 | 状态：已确认  
> 父文档：[V2 整体设计](2026-06-17-paper-reading-agent-v2-design.md)  
> Phase 4b 设计：[Phase 4b 设计文档](2026-06-19-paper-reading-agent-v2-phase4b-design.md)

---

## 一、概述

Phase 5 实现三个独立功能，共享论文库基础设施改进：

| 功能 | 说明 |
|------|------|
| **结构化对比报告** | 多选 2-5 篇论文，一键生成对比报告（方法/实验/贡献/局限） |
| **外部结果保存到论文库** | 将外部检索结果（arXiv）保存为论文库条目 |
| **BibTeX 导入** | 批量导入 .bib 文件，创建无 PDF 的论文库条目 |

**架构决策：** 对比报告使用独立 API + 简化 LangGraph 图（4 节点），不与现有单论文 Q&A 图耦合。

---

## 二、数据模型变更

### 2.1 Paper 模型 (`models/paper.py`)

```python
@dataclass
class Paper:
    paper_id: str              # UUID
    title: str
    authors: list[str]
    abstract: str
    sections: list[Section]
    figures: list[Figure]
    references: list[Reference]
    metadata: dict
    raw_text: str
    language: str = "en"
    file_path: str | None = None       # 改为可选（无 PDF 条目为 None）
    arxiv_id: str | None = None        # 新增：arXiv ID（如 "2401.12345"）
    arxiv_pdf_url: str | None = None   # 新增：arXiv PDF 链接
    import_source: str = "upload"      # 新增：来源类型 "upload" | "bib_import" | "external_save"
    parsed_at: str = ""
```

### 2.2 Evidence 模型 (`models/state.py`)

```python
# 新增字段
paper_id: str | None = None  # R0 证据所属论文 ID（对比报告用，单论文为 None）
```

### 2.3 CompareState (`models/state.py` — 新建)

```python
@dataclass
class CompareState:
    paper_ids: list[str]              # 选中的论文 ID 列表（2-5 篇）
    papers: list[Paper]               # 解析后的 Paper 对象列表
    reports: list[dict]               # 每篇论文的 reader report
    comparison_aspects: list[str] | None = None  # 对比维度（来自 API 请求，None 用默认）
    user_query: str = ""              # 自定义焦点（来自 API 请求）
    answer: str = ""
    evidence_list: list[Evidence] = field(default_factory=list)
    quality_score: QualityScore | None = None
    rewrite_count: int = 0
    trace: list[str] = field(default_factory=list)
    error: str | None = None
    session_id: str = ""
```

### 2.4 Database Migration (`storage/database.py`)

```sql
ALTER TABLE papers ADD COLUMN arxiv_id TEXT;
ALTER TABLE papers ADD COLUMN import_source TEXT DEFAULT 'upload';
-- file_path 列已存在，允许 NULL（现有数据不变）
```

---

## 三、对比报告

### 3.1 方案概述

- **独立端点**：`POST /api/compare`（SSE 流式）
- **独立 Graph**：`reader_batch → compare → reviewer → [decide] → output`
- **复用现有节点**：reader_node（无 PDF 适配）、reviewer_node、decide_loop（参数化）
- **不设 HITL**：对比报告为只读操作，选定论文即触发，无需审批中断

### 3.2 API

```
POST /api/compare
Content-Type: application/json

{
  "paper_ids": ["id1", "id2", "id3"],
  "aspects": ["method", "experiment"],
  "query": "focus on training efficiency"  // 可选，自定义焦点
}
```

Response：SSE 流，复用现有协议：

```
event: init   → { thread_id, session_id }
event: node   → { node: "reader_batch" }
event: node   → { node: "compare" }
event: token  → { text: "## 方法对比\n..." }
event: node   → { node: "reviewer" }
event: done   → { answer, session_id, quality_score, trace, evidence_list }
```

### 3.3 LangGraph 图

```
reader_batch ──→ compare ──→ reviewer ──→ [decide] ──→ output
                                    ↑_________|  (rewrite 循环, max=1)
```

#### reader_all_node (`backend/agents/compare.py`)

```python
async def reader_all_node(state: CompareState) -> CompareState:
    """并行读取所有选中论文的 report。"""
    papers = []
    reports = []
    for pid in state.paper_ids:
        paper = paper_store.get(pid)
        if paper is None:
            raise ValueError(f"Paper not found: {pid}")
        papers.append(paper)

    # asyncio.gather 并行处理
    async def read_one(paper: Paper) -> dict:
        if paper.file_path is None:
            # 无 PDF：基于元数据生成最小 report
            return {
                "title": paper.title,
                "authors": paper.authors,
                "abstract": paper.abstract,
                "method": "", "contribution": "",
                "experiments": "", "limitations": "", "keywords": []
            }
        # 有 PDF：复用 reader_node
        state = reader_node(AgentState(paper=paper, user_query=""))
        return state.report

    reports = await asyncio.gather(*[read_one(p) for p in papers])
    state.papers = papers
    state.reports = reports
    state.trace.append("reader_batch: done")
    return state
```

#### compare_generate_node (`backend/agents/compare.py`)

使用 `chat()`（非流式），完整回复生成后通过 SSE 一次性推送为 `token` 事件。对比报告 context 较大（多论文 report），不适合 `chat_stream()` 逐 token 推送（DeepSeek API 连接不稳定，参见已知限制）。`max_tokens=2000` 确保回复完整。

```python
async def compare_generate_node(state: CompareState) -> CompareState:
    """基于多论文 report 生成结构化对比报告（非流式 chat）。"""
    aspects = state.comparison_aspects or ["method", "contribution", "limitation"]
    query_text = state.user_query or ""

    reports_text = "\n\n---\n\n".join([
        f"## Paper {i+1}: {r['title']}\n"
        f"Authors: {', '.join(r.get('authors', []))}\n"
        f"Method: {r.get('method', 'N/A')}\n"
        f"Contribution: {r.get('contribution', 'N/A')}\n"
        f"Experiments: {r.get('experiments', 'N/A')}\n"
        f"Limitations: {r.get('limitations', 'N/A')}"
        for i, r in enumerate(state.reports)
    ])

    prompt = COMPARE_PROMPT.format(
        aspects=", ".join(aspects),
        query=query_text if query_text else "None",
        reports=reports_text,
    )
    state.answer = await llm_client.chat(prompt, max_tokens=2000)
    state.trace.append("compare: done")
    return state
```

#### decide_loop 参数化 (`backend/agents/reviewer.py`)

```python
def decide_loop(state: AgentState | CompareState, max_rewrites: int = 2) -> str:
    """对比图传 max_rewrites=1，现有图用默认 2。"""
    if state.quality_score.total >= 7 or state.rewrite_count >= max_rewrites:
        return "output"
    return "rewrite"
```

### 3.4 SSE 流 (`backend/agents/compare_supervisor.py`)

`compare_generate_node` 使用 `chat()` 非流式调用，完整回答在节点结束时通过单个 SSE `token` 事件发送。reviewer 同理。

```python
async def stream_compare(state: CompareState) -> AsyncGenerator[str, None]:
    """单段 SSE 流（无 HITL 中断）。"""
    graph = build_compare_graph()
    async for event in graph.astream_events(state, version="v1"):
        if event["event"] == "on_chain_start":
            yield format_sse("node", {"node": event["name"]})
        elif event["event"] == "on_chain_end":
            if event["name"] == "compare":
                # 对比报告生成完毕，一次性推送完整文本
                yield format_sse("token", {"text": state.answer})
            elif event["name"] == "output":
                pass  # done 事件在循环外发送
    yield format_sse("done", _build_compare_done_payload(state))
```

### 3.5 Prompts (`backend/llm/prompts.py`)

```python
COMPARE_PROMPT = """You are an academic comparison analyst. Based on the following
paper reports, generate a structured comparison report.

Comparison aspects: {aspects}
User focus: {query}

Paper reports:
{reports}

Generate a structured report using markdown tables:

## Method Comparison
| Paper | Method | Core Innovation |

## Experiments Comparison
| Paper | Dataset | Key Metrics | Results |

## Contributions Comparison
| Paper | Contribution |

## Limitations Comparison
| Paper | Limitation |

## Summary
Brief synthesis of similarities, differences, and recommendations.
"""
```

---

## 四、外部结果保存到论文库

### 4.1 API

```
POST /api/papers/save-external
Content-Type: application/json

{
  "arxiv_id": "2401.12345"   // 从 ExternalResult.url 中解析
}

Response 200:
{
  "paper_id": "uuid-xxx",
  "title": "Attention Is All You Need",
  "already_saved": false
}

Response 200 (重复):
{
  "paper_id": "existing-uuid",
  "title": "Attention Is All You Need",
  "already_saved": true
}
```

### 4.2 后端逻辑

```python
async def save_external(arxiv_id: str) -> dict:
    # 1. 去重：arxiv_id 精确匹配，fallback title slug
    existing = paper_store.get_by_arxiv_id(arxiv_id)
    if not existing:
        existing = paper_store.get_by_title_slug(slugify(title_from_arxiv(arxiv_id)))
    if existing:
        return {"paper_id": existing.paper_id, "title": existing.title, "already_saved": True}

    # 2. 从 arXiv API 拉取完整元数据
    meta = await fetch_arxiv_metadata(arxiv_id)  # 复用 ExternalRetriever 的 arXiv 解析

    # 3. 构造 Paper + 入库
    paper = Paper(
        title=meta.title,
        authors=meta.authors,
        abstract=meta.abstract,
        raw_text=meta.abstract,
        arxiv_id=arxiv_id,
        arxiv_pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        file_path=None,
        import_source="external_save",
    )
    paper_store.add_paper(paper)
    return {"paper_id": paper.paper_id, "title": paper.title, "already_saved": False}
```

### 4.3 paper_store 新增方法

```python
def get_by_arxiv_id(self, arxiv_id: str) -> Paper | None: ...
def get_by_title_slug(self, slug: str) -> Paper | None: ...
```

### 4.4 辅助函数

`slugify(title: str) -> str`：标准化标题用于匹配——lowercase + 移除标点/多余空白。前端已有 `api/client.ts` 中的 `slugify` 实现，后端需新增独立的 Python 版本（`backend/utils/text_utils.py` 或直接在 `paper_store.py` 中内联）。

`arxiv_id` 从 `ExternalResult.url` 中解析——URL 格式固定为 `https://arxiv.org/abs/{arxiv_id}`，正则提取 `/abs/(.*)` 即可。

`fetch_arxiv_metadata(arxiv_id)` 复用 `ExternalRetriever._search_arxiv()` 的 HTTP 调用和 Atom XML 解析逻辑，按单个 arXiv ID 精确查询（`id_list=[arxiv_id]`）。

---

## 五、BibTeX 导入

### 5.1 API

```
POST /api/papers/import-bibtex
Content-Type: application/json

{
  "bibtex_content": "@article{...}\n@inproceedings{...}"
}

Response 200:
{
  "imported": 12,
  "skipped": 3,
  "errors": [
    {"line": 45, "error": "Missing required field: title"}
  ],
  "papers": [
    {"paper_id": "...", "title": "Foo", "import_source": "bib_import"},
    ...
  ]
}
```

### 5.2 解析 (`backend/tools/bibtex_importer.py`)

```python
import bibtexparser  # version >= 2.0.0 (pure Python, no pyparsing)

def parse_bibtex(content: str) -> tuple[list[Paper], list[dict]]:
    """解析 .bib 内容，返回 (成功 papers, 错误列表)。"""
    library = bibtexparser.parse_string(content)
    papers = []
    errors = []

    for entry in library.entries:
        try:
            paper = entry_to_paper(entry)
            papers.append(paper)
        except ValueError as e:
            errors.append({"line": entry.raw_range.start.line, "error": str(e)})

    return papers, errors

def entry_to_paper(entry) -> Paper:
    """单个 BibTeX entry 转 Paper。"""
    authors = [str(name) for name in entry.get("author", [])]  # bibtexparser v2 自动拆分
    year = entry.get("year")
    if year:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = None  # "to appear" 等无法解析的值

    return Paper(
        title=str(entry.get("title", "Untitled")),
        authors=authors,
        abstract=str(entry.get("abstract", "")),
        raw_text=str(entry.get("abstract", "")),
        metadata={
            "year": year,
            "doi": str(entry.get("doi", "")),
            "entry_type": entry.entry_type,
        },
        file_path=None,
        import_source="bib_import",
    )
```

### 5.3 去重

- 优先 `doi` 匹配
- Fallback `title` slug 匹配（lowercase + 去标点）
- 逐条导入，出错继续（已入库不回滚）

### 5.4 依赖

```
# requirements.txt 新增
bibtexparser>=2.0.0
```

---

## 六、前端变更

### 6.1 新增类型 (`types/index.ts`)

```typescript
// 对比请求
export interface CompareRequest {
  paper_ids: string[]
  aspects?: string[]     // e.g. ["method", "experiment"]
  query?: string
}

// BibTeX 导入响应
export interface ImportBibTeXResponse {
  imported: number
  skipped: number
  errors: Array<{ line: number; error: string }>
  papers: Array<{ paper_id: string; title: string; import_source: string }>
}

// 外部保存请求
export interface SaveExternalRequest {
  arxiv_id: string
}

// Paper 类型扩展
export interface Paper {
  // ... 现有字段 ...
  arxiv_id?: string | null
  arxiv_pdf_url?: string | null
  import_source?: string    // "upload" | "bib_import" | "external_save"
  file_path?: string | null  // 改为可选
}
```

### 6.2 新增 API 函数 (`api/client.ts`)

```typescript
comparePapers(req: CompareRequest):            // 返回 SSE URL → 由 useSSE 使用
saveExternal(arxivId: string): Promise<{ paper_id: string; title: string; already_saved: boolean }>
importBibTeX(content: string): Promise<ImportBibTeXResponse>
```

### 6.3 `compareStore.ts`（新建）

```typescript
interface CompareStore {
  isCompareMode: boolean
  selectedPaperIds: string[]
  toggleCompareMode: () => void
  toggleSelection: (id: string) => void    // 最多 5 篇
  clearSelection: () => void
}
```

### 6.4 LibraryPanel 多选

- 顶部新增 `[Compare]` 切换按钮
- 多选模式：论文左侧显示复选框，提示 "Select 2-5 papers"
- 选中 2-5 篇后底部浮动 `[Compare Selected (3)]` 按钮
- 对比完成后自动退出多选模式，清空选中

### 6.5 CompareSelectModal（新建）

确认弹窗：
- 显示已选论文列表
- 可选对比维度复选框：Method / Experiment / Contribution / Limitation
- 可选自定义焦点输入框
- `[Cancel]` / `[Compare →]` 按钮

确认后：
- ChatPanel 中插入角色消息 "Comparing 3 papers: A, B, C"
- 调用 `POST /api/compare` SSE
- 答案流式渲染 + StepIndicator（reader_batch → compare → reviewer → output）

### 6.6 ExternalRefCard（新建）

`AssistantMessage` 底部，当 `external_results.length > 0` 时显示：

- 每条外部结果一个卡片（标题、作者/年份、引用数）
- `[Save →]` 按钮 → `POST /api/papers/save-external` → 成功后变 `[Saved ✓]`
- 点击标题跳转 arXiv 页面

### 6.7 PaperViewer 无 PDF 态

当 `paper.file_path === null` 时显示元数据卡片：
- 标题 + 作者 + 年份 + 完整 abstract
- `[Upload PDF]` 按钮（上传后触发解析 + 刷新）
- `[Open on arXiv ↗]` 链接（若有 `arxiv_pdf_url`）

**Upload PDF 流程**：`[Upload PDF]` 触发文件选择器，选中 PDF 后调用已有的 `POST /api/upload`，**返回新的 paper_id**。前端将 appStore 的 paper 替换为新 paper（含 PDF），旧的元数据条目自动被取代。这比新增一个"更新已有 paper 的 file_path"端点更简单——不需要 paper_store 增加 update 方法。（如果用户想保留旧 paper_id，需要手动删除旧条目。）

**`[Open on arXiv ↗]`**：直接打开 `arxiv_pdf_url` 到新标签页。用户如需存档可下载后手动上传。

### 6.8 BibTeX 导入按钮

LibraryPanel 顶部 `[Import BibTeX]` 按钮 → 文件选择器 `.bib` → `FileReader.readAsText()` → API → Toast：

```
✅ Imported 12 papers
⚠️ 3 skipped (already exist)
❌ 2 errors (line 45, 67)
[View Details] [Dismiss]
```

### 6.9 StepIndicator 更新

NODE_ORDER 新增：
```typescript
['reader', 'classify', 'planner', 'retrieve', 'external_search',
 'reader_batch', 'compare', 'generate', 'observe', 'reviewer', 'output', 'rewrite']
```

---

## 七、文件变更清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `backend/agents/compare.py` | reader_all_node + compare_generate_node |
| `backend/agents/compare_supervisor.py` | 对比 LangGraph 构建 + SSE 流 |
| `backend/tools/bibtex_importer.py` | BibTeX 解析 + Paper 构造 |
| `frontend/src/store/compareStore.ts` | 多选状态管理 |
| `frontend/src/components/ChatPanel/CompareSelectModal.tsx` | 多选确认弹窗 |
| `frontend/src/components/ChatPanel/ExternalRefCard.tsx` | 外部参考卡片 + 保存按钮 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/models/paper.py` | Paper 增加 `arxiv_id`、`arxiv_pdf_url`、`import_source`；`file_path` 改可选 |
| `backend/models/state.py` | Evidence 增加 `paper_id`；新增 `CompareState` |
| `backend/agents/reader.py` | reader_node 适配无 PDF（`file_path=None` → 元数据路径） |
| `backend/agents/reviewer.py` | `decide_loop` 参数化 `max_rewrites` |
| `backend/llm/prompts.py` | 新增 `COMPARE_PROMPT` |
| `backend/storage/database.py` | Migration: `ALTER TABLE papers ADD arxiv_id, import_source` |
| `backend/storage/paper_store.py` | 新增 `get_by_arxiv_id()`、`get_by_title_slug()` |
| `backend/app.py` | 新增 3 个端点：`POST /api/compare`、`POST /api/papers/save-external`、`POST /api/papers/import-bibtex` |
| `frontend/src/types/index.ts` | 新增类型 + Paper 扩展 |
| `frontend/src/api/client.ts` | 新增 3 个 API 函数 |
| `frontend/src/components/Layout/LibraryPanel.tsx` | 多选模式 + Import BibTeX 按钮 |
| `frontend/src/components/ChatPanel/AssistantMessage.tsx` | 回答底部 ExternalRefCard 列表 |
| `frontend/src/components/ChatPanel/StepIndicator.tsx` | NODE_ORDER 增加 reader_batch、compare |
| `frontend/src/components/PaperViewer/PaperViewer.tsx` | 无 PDF 态元数据卡片 |
| `requirements.txt` | 新增 `bibtexparser>=2.0.0` |

### 不修改

| 文件 | 原因 |
|------|------|
| `backend/agents/qa.py` | 单论文 Q&A 不变 |
| `backend/agents/supervisor.py` | 单论文图不变 |
| `backend/agents/reviewer.py` (reviewer_node) | 复用；仅 decide_loop 参数化 |
| `backend/tools/external_search.py` | 已有 arXiv 解析逻辑，引入复用 |

---

## 八、测试策略

| 分类 | 功能 | 测试数 |
|------|------|--------|
| **模型** | Paper 新字段（import_source 默认值、file_path=None、arxiv_id 可选） | 3 |
| | CompareState 创建 + 默认值 | 2 |
| | Evidence.paper_id（对比必填 / 单论文 None） | 1 |
| **Agent** | reader_node 无 PDF 路径 → 最小 report | 2 |
| | reader_all_node（并行 3 论文、混合 PDF+无 PDF、空列表报错） | 3 |
| | compare_generate_node（正常、aspect 指定、query 自定义） | 3 |
| | compare_graph 全流程 + rewrite 循环 | 2 |
| | decide_loop 参数化（max=1 vs =2、阈值边界） | 2 |
| **API** | POST /api/compare（SSE 事件序列、done payload、错误） | 3 |
| | POST /api/papers/save-external（拉取、去重、重复） | 3 |
| | POST /api/papers/import-bibtex（正常、空文件、格式错、重复） | 4 |
| **存储** | get_by_arxiv_id、get_by_title_slug、无匹配 None | 3 |
| | DB migration（列存在、默认值） | 2 |
| **前端** | 新增类型兼容性 | 2 |
| | CompareStore（toggle、clear、边界 >5） | 3 |
| | CompareSelectModal / ExternalRefCard / LibraryPanel 多选 | 3 |
| | **总计（后端 + 前端）** | **~41** |

累计：128（现有） + 41 = **~169 测试**。

---

## 九、错误处理

| 场景 | 策略 |
|------|------|
| compare API paper_ids 为空 | 400 "At least 2 papers required" |
| paper_ids 不足 2 篇 | 400 "Select at least 2 papers" |
| paper_ids 超过 5 篇 | 400 "Maximum 5 papers allowed" |
| paper_id 不存在 | 400 "Paper not found: {id}" |
| save-external arxiv_id 无效 | 400 "Invalid arXiv ID" |
| arXiv API 不可用（save-external） | 503 "arXiv API unavailable, try again later" |
| import-bibtex 文件为空 | 400 "Empty BibTeX content" |
| bibtexparser 解析失败 | 200 + errors 列表（部分成功） |
| compare LLM 调用失败 | 500 + 错误消息 |
| 对比报告质量 < 5 | max_rewrites=1 后直接输出（容错） |

---

## 十、架构图

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                     │
├─────────────────────────────────────────────────────────┤
│  LibraryPanel          ChatPanel          PaperViewer   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ [Compare] btn│  │ CompareSelect│  │ PDF / 元数据 │   │
│  │ [Import .bib]│  │ Modal        │  │ 卡片         │   │
│  │ checkboxes   │  │ ExternalRef  │  │ [Upload PDF]│   │
│  │ [Compare(3)] │  │ Cards        │  │ [Open arXiv]│   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│         │                  │                  │          │
│  compareStore        chatStore           appStore       │
├─────────┼──────────────────┼──────────────────┼──────────┤
│         │            API Client              │          │
├─────────┼──────────────────┼──────────────────┼──────────┤
│                    Backend (FastAPI)                     │
├─────────────────────────────────────────────────────────┤
│  POST /api/compare         (SSE)                        │
│  POST /api/papers/save-external                         │
│  POST /api/papers/import-bibtex                         │
├─────────────────────────────────────────────────────────┤
│  compare_supervisor.py  ─→  compare_graph               │
│  compare.py  ─→  reader_all_node + compare_generate     │
│  bibtex_importer.py  ─→  parse + Paper 构造             │
│  paper_store.py  ─→  get_by_arxiv_id / get_by_title_slug│
│  external_search.py  ─→  arXiv API 复用                 │
└─────────────────────────────────────────────────────────┘
```
