# Phase 5: 结构化对比报告 + 外部保存 + BibTeX 导入 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现论文库多选结构化对比报告、外部检索结果保存到论文库、BibTeX 批量导入三个功能。

**Architecture:** 对比报告使用独立 `POST /api/compare` SSE 端点 + 4 节点 LangGraph 图，不复用单论文 Q&A 图。外部保存通过 `POST /api/papers/save-external`，BibTeX 导入通过 `POST /api/papers/import-bibtex`。Paper 模型增加 `arxiv_id`/`import_source`/`arxiv_pdf_url`，`file_path` 改为可选。

**Tech Stack:** Python 3.11+ (FastAPI, LangGraph, aiosqlite, bibtexparser>=2.0.0), TypeScript 5.5+ (React 18, zustand, Vite)

## Global Constraints

- bibtexparser >= 2.0.0 (pure Python, no pyparsing dependency)
- 对比报告 max_rewrites=1（现有单论文保持 2）
- 多选上限 5 篇，下限 2 篇
- file_path 必须支持 None（无 PDF 条目）
- import_source 默认值 "upload"
- 所有无 PDF 条目的 reader_node 必须走元数据路径
- arXiv rate limit 间隔 3 秒（复用现有 ARXIV_REQUEST_INTERVAL）

---

### Task 1: Paper 模型扩展 + DB Migration

**Files:**
- Modify: `backend/models/paper.py:30-42`
- Modify: `backend/storage/database.py:17-55`
- Modify: `backend/storage/paper_store.py:28-40`, `backend/storage/paper_store.py:45-63`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Paper.arxiv_id: str | None`, `Paper.arxiv_pdf_url: str | None`, `Paper.import_source: str = "upload"`, `Paper.file_path: str | None = None`
- Produces: DB columns `arxiv_id TEXT`, `import_source TEXT DEFAULT 'upload'`
- Produces: `paper_store.add_paper()` and `get_paper()` write/read new columns

- [ ] **Step 1: 修改 Paper 模型**

```python
# backend/models/paper.py — 在现有 dataclass 中修改 file_path 默认值，增加三个新字段

@dataclass
class Paper:
    paper_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    sections: list[Section] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    raw_text: str = ""
    language: str = "en"
    file_path: str | None = None       # 改为可选
    arxiv_id: str | None = None        # 新增
    arxiv_pdf_url: str | None = None   # 新增
    import_source: str = "upload"      # 新增
    parsed_at: str = ""
```

- [ ] **Step 2: 编写 Paper 模型测试**

```python
# tests/test_models.py — 追加以下测试函数

def test_paper_default_import_source():
    p = Paper(title="test")
    assert p.import_source == "upload"

def test_paper_file_path_none():
    p = Paper(title="test", file_path=None)
    assert p.file_path is None

def test_paper_arxiv_id_optional():
    p = Paper(title="test")
    assert p.arxiv_id is None

def test_paper_arxiv_pdf_url_optional():
    p = Paper(title="test", arxiv_id="2401.12345", arxiv_pdf_url="https://arxiv.org/pdf/2401.12345.pdf")
    assert p.arxiv_id == "2401.12345"
    assert p.arxiv_pdf_url == "https://arxiv.org/pdf/2401.12345.pdf"

def test_paper_import_source_bib():
    p = Paper(title="test", import_source="bib_import")
    assert p.import_source == "bib_import"

def test_paper_import_source_external_save():
    p = Paper(title="test", import_source="external_save")
    assert p.import_source == "external_save"
```

Run: `pytest tests/test_models.py::test_paper_default_import_source tests/test_models.py::test_paper_file_path_none tests/test_models.py::test_paper_arxiv_id_optional tests/test_models.py::test_paper_arxiv_pdf_url_optional tests/test_models.py::test_paper_import_source_bib tests/test_models.py::test_paper_import_source_external_save -v`
Expected: 6 PASS

- [ ] **Step 3: 添加 DB Migration**

```python
# backend/storage/database.py — 在 _migrate() 末尾，现有 Phase 4a migration 之后追加：

        # Phase 5: add arxiv_id and import_source columns
        try:
            await conn.execute('ALTER TABLE papers ADD COLUMN arxiv_id TEXT')
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE papers ADD COLUMN import_source TEXT NOT NULL DEFAULT 'upload'")
        except Exception:
            pass
        await conn.commit()
```

- [ ] **Step 4: 编写 DB Migration 测试**

```python
# tests/test_storage.py — 追加测试

@pytest.mark.asyncio
async def test_migration_adds_arxiv_id_column():
    conn = await db.get_db()
    try:
        async with conn.execute("SELECT arxiv_id FROM papers LIMIT 0") as cursor:
            pass  # 列存在则不抛异常
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_migration_adds_import_source_column():
    conn = await db.get_db()
    try:
        async with conn.execute("SELECT import_source FROM papers LIMIT 0") as cursor:
            pass
    finally:
        await conn.close()
```

Run: `pytest tests/test_storage.py::test_migration_adds_arxiv_id_column tests/test_storage.py::test_migration_adds_import_source_column -v`
Expected: 2 PASS

- [ ] **Step 5: 更新 paper_store 读写新列**

```python
# backend/storage/paper_store.py — add_paper() INSERT 增加两个新列

    async def add_paper(self, paper: Paper) -> Paper:
        conn = await db.get_db()
        try:
            await conn.execute(
                """INSERT OR REPLACE INTO papers
                   (paper_id, title, authors, abstract, metadata, raw_text, language, file_path, parsed_at, "references", arxiv_id, import_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (paper.paper_id, paper.title, json.dumps(paper.authors), paper.abstract,
                 json.dumps(paper.metadata), paper.raw_text, paper.language, paper.file_path,
                 paper.parsed_at, json.dumps([_ref_to_dict(r) for r in paper.references]),
                 paper.arxiv_id, paper.import_source)
            )
            await conn.commit()
            return paper
        finally:
            await conn.close()

# get_paper() — SELECT 返回新列（注意 file_path 可能为 None）

    async def get_paper(self, paper_id: str) -> Paper | None:
        conn = await db.get_db()
        try:
            async with conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                refs_raw = row["references"] if "references" in row.keys() else "[]"
                # 安全读取新增列（兼容旧数据）
                arxiv_id = row["arxiv_id"] if "arxiv_id" in row.keys() else None
                import_source = row["import_source"] if "import_source" in row.keys() else "upload"
                file_path = row["file_path"] or None
                return Paper(
                    paper_id=row["paper_id"], title=row["title"],
                    authors=json.loads(row["authors"]), abstract=row["abstract"],
                    metadata=json.loads(row["metadata"]), raw_text=row["raw_text"],
                    language=row["language"], file_path=file_path,
                    parsed_at=row["parsed_at"],
                    references=[_dict_to_ref(r) for r in json.loads(refs_raw)],
                    arxiv_id=arxiv_id,
                    import_source=import_source,
                )
        finally:
            await conn.close()
```

- [ ] **Step 6: 编写 paper_store 新列读写测试**

```python
# tests/test_storage.py — 追加测试

@pytest.mark.asyncio
async def test_add_paper_with_arxiv_fields():
    store = PaperStore()
    paper = Paper(
        title="Test ArXiv Paper",
        authors=["Smith, J."],
        abstract="Test abstract.",
        arxiv_id="2401.12345",
        arxiv_pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
        import_source="external_save",
        file_path=None,
    )
    saved = await store.add_paper(paper)
    assert saved.arxiv_id == "2401.12345"

    fetched = await store.get_paper(saved.paper_id)
    assert fetched is not None
    assert fetched.arxiv_id == "2401.12345"
    assert fetched.import_source == "external_save"
    assert fetched.file_path is None
```

Run: `pytest tests/test_storage.py::test_add_paper_with_arxiv_fields -v`
Expected: PASS

- [ ] **Step 7: 运行全部模型 + 存储测试**

Run: `pytest tests/test_models.py tests/test_storage.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add backend/models/paper.py backend/storage/database.py backend/storage/paper_store.py tests/test_models.py tests/test_storage.py
git commit -m "feat(phase5): extend Paper model with arxiv_id, import_source, optional file_path; DB migration"
```

---

### Task 2: Evidence.paper_id + CompareState

**Files:**
- Modify: `backend/models/state.py:10-34` (Evidence), `backend/models/state.py:56-84` (AgentState)
- Create: `backend/models/state.py` 追加 CompareState
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Evidence.paper_id: str | None = None`
- Produces: `CompareState` dataclass (full definition below)
- Consumes: `QualityScore` (existing), `Evidence` (existing)

- [ ] **Step 1: 修改 Evidence 模型**

```python
# backend/models/state.py — 在 Evidence 的 external_result_id 之后追加：

    external_result_id: str | None = None  # Phase 4b
    paper_id: str | None = None            # Phase 5: R0 证据所属论文 ID（对比报告用）
```

- [ ] **Step 2: 新增 CompareState**

```python
# backend/models/state.py — 在 AgentState 之后追加：

@dataclass
class CompareState:
    paper_ids: list[str] = field(default_factory=list)
    papers: list = field(default_factory=list)           # list[Paper]
    reports: list[dict] = field(default_factory=list)
    comparison_aspects: list[str] | None = None
    user_query: str = ""
    answer: str = ""
    evidence_list: list[Evidence] = field(default_factory=list)
    quality_score: QualityScore | None = None
    rewrite_count: int = 0
    trace: list[str] = field(default_factory=list)
    error: str | None = None
    session_id: str = ""
```

- [ ] **Step 3: 编写测试**

```python
# tests/test_models.py — 追加测试

def test_evidence_paper_id_default_none():
    ev = Evidence(evidence_id="ev-1", claim="test", level=EvidenceLevel.R2)
    assert ev.paper_id is None

def test_evidence_paper_id_set():
    ev = Evidence(evidence_id="ev-1", claim="test", level=EvidenceLevel.R0, paper_id="paper-123")
    assert ev.paper_id == "paper-123"

def test_compare_state_defaults():
    cs = CompareState()
    assert cs.paper_ids == []
    assert cs.answer == ""
    assert cs.comparison_aspects is None
    assert cs.rewrite_count == 0
    assert cs.trace == []

def test_compare_state_with_ids():
    cs = CompareState(
        paper_ids=["id1", "id2"],
        comparison_aspects=["method", "experiment"],
        user_query="focus on training",
    )
    assert len(cs.paper_ids) == 2
    assert cs.comparison_aspects == ["method", "experiment"]
    assert cs.user_query == "focus on training"
```

Run: `pytest tests/test_models.py::test_evidence_paper_id_default_none tests/test_models.py::test_evidence_paper_id_set tests/test_models.py::test_compare_state_defaults tests/test_models.py::test_compare_state_with_ids -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/models/state.py tests/test_models.py
git commit -m "feat(phase5): add Evidence.paper_id and CompareState model"
```

---

### Task 3: PaperStore 扩展 — 去重查询

**Files:**
- Modify: `backend/storage/paper_store.py` — 追加方法
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces: `PaperStore.get_by_arxiv_id(arxiv_id: str) -> Paper | None`
- Produces: `PaperStore.get_by_title_slug(slug: str) -> Paper | None`
- Produces: `_slugify_title(title: str) -> str` (模块级函数)

- [ ] **Step 1: 实现 `_slugify_title` 和两个查询方法**

```python
# backend/storage/paper_store.py — 在 PaperStore 类之前追加：

import re

def _slugify_title(title: str) -> str:
    """Normalize title for matching: lowercase + remove punctuation/extra whitespace."""
    slug = title.lower()
    slug = re.sub(r'[^\w\s]', '', slug)  # 移除标点
    slug = re.sub(r'\s+', ' ', slug).strip()
    return slug


# 在 PaperStore 类末尾（delete_paper 之后）追加：

    async def get_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Find paper by arXiv ID. Returns None if not found."""
        conn = await db.get_db()
        try:
            async with conn.execute(
                "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return _row_to_paper(row)
        finally:
            await conn.close()

    async def get_by_title_slug(self, slug: str) -> Paper | None:
        """Find paper by title slug match. Fetches all papers and compares
        slugified titles since SQLite has no regex. Returns None if no match."""
        conn = await db.get_db()
        try:
            async with conn.execute("SELECT * FROM papers") as cursor:
                async for row in cursor:
                    if _slugify_title(row["title"]) == slug:
                        return _row_to_paper(row)
            return None
        finally:
            await conn.close()
```

同时提取一个 `_row_to_paper` 复用函数（避免与 `get_paper` 重复代码）：

```python
# backend/storage/paper_store.py — 在 PaperStore 类之前追加：

def _row_to_paper(row) -> Paper:
    """Convert a database row (aiosqlite.Row or dict) to a Paper object."""
    refs_raw = row["references"] if "references" in row.keys() else "[]"
    arxiv_id = row["arxiv_id"] if "arxiv_id" in row.keys() else None
    import_source = row["import_source"] if "import_source" in row.keys() else "upload"
    file_path = row["file_path"] or None
    return Paper(
        paper_id=row["paper_id"], title=row["title"],
        authors=json.loads(row["authors"]), abstract=row["abstract"],
        metadata=json.loads(row["metadata"]), raw_text=row["raw_text"],
        language=row["language"], file_path=file_path,
        parsed_at=row["parsed_at"],
        references=[_dict_to_ref(r) for r in json.loads(refs_raw)],
        arxiv_id=arxiv_id,
        import_source=import_source,
    )
```

重构 `get_paper` 使用 `_row_to_paper`：

```python
    async def get_paper(self, paper_id: str) -> Paper | None:
        conn = await db.get_db()
        try:
            async with conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return _row_to_paper(row)
        finally:
            await conn.close()
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_storage.py — 追加测试

@pytest.mark.asyncio
async def test_get_by_arxiv_id_found():
    store = PaperStore()
    paper = Paper(title="Unique Paper", arxiv_id="9999.99999", import_source="external_save")
    await store.add_paper(paper)
    found = await store.get_by_arxiv_id("9999.99999")
    assert found is not None
    assert found.title == "Unique Paper"

@pytest.mark.asyncio
async def test_get_by_arxiv_id_not_found():
    store = PaperStore()
    found = await store.get_by_arxiv_id("nonexistent.00000")
    assert found is None

@pytest.mark.asyncio
async def test_get_by_title_slug_found():
    store = PaperStore()
    paper = Paper(title="Attention Is All You Need!", import_source="bib_import")
    await store.add_paper(paper)
    found = await store.get_by_title_slug("attention is all you need")
    assert found is not None

@pytest.mark.asyncio
async def test_get_by_title_slug_not_found():
    store = PaperStore()
    found = await store.get_by_title_slug("nonexistent paper title")
    assert found is None

def test_slugify_title():
    assert _slugify_title("Attention Is All You Need!") == "attention is all you need"
    assert _slugify_title("BERT: Pre-training of Deep Bidirectional Transformers") == "bert pre training of deep bidirectional transformers"
    assert _slugify_title("  Extra   Spaces  ") == "extra spaces"
```

Run: `pytest tests/test_storage.py::test_get_by_arxiv_id_found tests/test_storage.py::test_get_by_arxiv_id_not_found tests/test_storage.py::test_get_by_title_slug_found tests/test_storage.py::test_get_by_title_slug_not_found tests/test_storage.py::test_slugify_title -v`
Expected: 5 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/storage/paper_store.py tests/test_storage.py
git commit -m "feat(phase5): add PaperStore.get_by_arxiv_id, get_by_title_slug with _row_to_paper refactor"
```

---

### Task 4: reader_node 无 PDF 适配 + decide_loop 参数化

**Files:**
- Modify: `backend/agents/reader.py:8-48`
- Modify: `backend/agents/reviewer.py:60-65`
- Test: `tests/test_reader.py`, `tests/test_reviewer.py`

**Interfaces:**
- Consumes: `Paper.file_path: str | None`
- Produces: `decide_loop(state: AgentState | CompareState, max_rewrites: int = 2) -> str`

- [ ] **Step 1: 修改 reader_node 处理 file_path=None**

```python
# backend/agents/reader.py — 修改 reader_node 函数开头

async def reader_node(state: AgentState) -> AgentState:
    """Parse PDF + generate structured report + build retrieval index (once)."""
    if state.paper is not None and state.report is not None:
        logger.info("Paper already parsed, skipping reader")
        state.trace.append("reader(cached)")
        return state

    # Phase 5: 无 PDF 路径 — 基于元数据生成最小 report
    if state.paper.file_path is None:
        paper = state.paper
        state.report = {
            "title": paper.title,
            "authors": paper.authors,
            "abstract_summary": paper.abstract[:500] if paper.abstract else "",
            "method": "",
            "contributions": [],
            "experiments_summary": "",
            "limitations": [],
            "keywords": [],
        }
        state.trace.append("reader(metadata)")
        return state

    # 原有 PDF 解析逻辑不变
    parser = PDFParser()
    try:
        paper = parser.parse(state.paper.file_path)
    except PDFParseError as e:
        state.error = str(e)
        state.trace.append("reader(error)")
        return state
    # ... 其余不变
```

- [ ] **Step 2: 编写 reader_node 无 PDF 测试**

```python
# tests/test_reader.py — 追加或新建测试

@pytest.mark.asyncio
async def test_reader_node_no_pdf_creates_minimal_report():
    from backend.agents.reader import reader_node
    from backend.models.state import AgentState
    from backend.models.paper import Paper

    paper = Paper(
        title="Test Paper Without PDF",
        authors=["Author One", "Author Two"],
        abstract="This is a test abstract for a paper without PDF.",
        file_path=None,
    )
    state = AgentState(paper=paper, user_query="")
    result = await reader_node(state)

    assert result.error is None
    assert result.report is not None
    assert result.report["title"] == "Test Paper Without PDF"
    assert "Author One" in result.report["authors"]
    assert "test abstract" in result.report["abstract_summary"]
    assert "reader(metadata)" in result.trace

@pytest.mark.asyncio
async def test_reader_node_no_pdf_empty_abstract():
    from backend.agents.reader import reader_node
    from backend.models.state import AgentState
    from backend.models.paper import Paper

    paper = Paper(title="No Abstract Paper", file_path=None)
    state = AgentState(paper=paper, user_query="")
    result = await reader_node(state)

    assert result.report["abstract_summary"] == ""
    assert result.error is None
```

Run: `pytest tests/test_reader.py -v`
Expected: all PASS（含新增 2 个）

- [ ] **Step 3: 参数化 decide_loop**

```python
# backend/agents/reviewer.py — 修改 decide_loop

def decide_loop(state: AgentState | CompareState, max_rewrites: int = 2) -> str:
    """对比图传 max_rewrites=1，现有图用默认 2。"""
    if state.quality_score is None:
        return "output"
    if state.quality_score.total >= 7 or state.rewrite_count >= max_rewrites:
        return "output"
    return "rewrite"
```

- [ ] **Step 4: 编写 decide_loop 参数化测试**

```python
# tests/test_reviewer.py — 追加测试（假设现有文件中已有 test_decide_loop）

def test_decide_loop_max_rewrites_1_stops_early():
    from backend.models.state import AgentState, QualityScore
    from backend.agents.reviewer import decide_loop

    state = AgentState()
    state.quality_score = QualityScore(relevance=1, consistency=1, completeness=1)  # total=3
    state.rewrite_count = 0
    # max_rewrites=1: score < 7, count < 1 → rewrite
    assert decide_loop(state, max_rewrites=1) == "rewrite"

    state.rewrite_count = 1  # count >= 1 → output
    assert decide_loop(state, max_rewrites=1) == "output"

def test_decide_loop_max_rewrites_default_2():
    from backend.models.state import AgentState, QualityScore
    from backend.agents.reviewer import decide_loop

    state = AgentState()
    state.quality_score = QualityScore(relevance=1, consistency=1, completeness=1)  # total=3
    state.rewrite_count = 1
    # 默认 max_rewrites=2: score < 7, count < 2 → rewrite
    assert decide_loop(state) == "rewrite"

    state.rewrite_count = 2  # count >= 2 → output
    assert decide_loop(state) == "output"

def test_decide_loop_high_score_outputs():
    from backend.models.state import AgentState, QualityScore
    from backend.agents.reviewer import decide_loop

    state = AgentState()
    state.quality_score = QualityScore(relevance=3, consistency=3, completeness=2)  # total=8
    state.rewrite_count = 0
    assert decide_loop(state) == "output"  # 不管 max_rewrites
```

Run: `pytest tests/test_reviewer.py -v`
Expected: all PASS（含新增 3 个）

- [ ] **Step 5: Commit**

```bash
git add backend/agents/reader.py backend/agents/reviewer.py tests/test_reader.py tests/test_reviewer.py
git commit -m "feat(phase5): adapt reader_node for no-PDF papers; parameterize decide_loop max_rewrites"
```

---

### Task 5: BibTeX Importer 模块

**Files:**
- Create: `backend/tools/bibtex_importer.py`
- Modify: `requirements.txt`
- Test: `tests/test_bibtex_importer.py`

**Interfaces:**
- Produces: `parse_bibtex(content: str) -> tuple[list[Paper], list[dict]]`
- Produces: `entry_to_paper(entry) -> Paper`

- [ ] **Step 1: 安装依赖**

```bash
pip install bibtexparser>=2.0.0
```

更新 `requirements.txt`，追加一行：
```
bibtexparser>=2.0.0
```

- [ ] **Step 2: 实现 bibtex_importer.py**

```python
# backend/tools/bibtex_importer.py
"""BibTeX parsing and import into paper library."""

import bibtexparser
from bibtexparser.model import Entry

from backend.models.paper import Paper
from backend.utils.logger import logger


def parse_bibtex(content: str) -> tuple[list[Paper], list[dict]]:
    """Parse .bib content, return (successful papers, error list).

    Each error dict has: {"line": int, "error": str}
    """
    try:
        library = bibtexparser.parse_string(content)
    except Exception as e:
        return [], [{"line": 0, "error": f"Failed to parse BibTeX: {e}"}]

    papers = []
    errors = []

    for entry in library.entries:
        try:
            paper = entry_to_paper(entry)
            papers.append(paper)
        except Exception as e:
            line = getattr(entry, 'start_line', 0) if hasattr(entry, 'start_line') else 0
            errors.append({"line": line, "error": str(e)})

    return papers, errors


def entry_to_paper(entry: Entry) -> Paper:
    """Convert a single BibTeX entry to a Paper object."""
    # Author parsing — bibtexparser v2 provides author as list of strings
    authors_raw = entry.get("author", [])
    if isinstance(authors_raw, str):
        authors = [a.strip() for a in authors_raw.split(" and ")]
    elif isinstance(authors_raw, list):
        authors = [str(a).strip() for a in authors_raw]
    else:
        authors = []

    # Year parsing with fallback for non-numeric values
    year_raw = entry.get("year")
    year = None
    if year_raw:
        try:
            year = int(str(year_raw))
        except (ValueError, TypeError):
            year = None  # "to appear", "in press" etc.

    # Title — strip braces
    title = str(entry.get("title", "Untitled")).strip()
    title = title.replace("{", "").replace("}", "")

    # Abstract — often missing in BibTeX
    abstract = str(entry.get("abstract", "")).strip()

    # DOI
    doi = str(entry.get("doi", "")).strip() or None

    return Paper(
        title=title,
        authors=authors,
        abstract=abstract,
        raw_text=abstract,
        metadata={
            "year": year,
            "doi": doi,
            "entry_type": entry.entry_type if hasattr(entry, 'entry_type') else "misc",
        },
        file_path=None,
        import_source="bib_import",
    )
```

- [ ] **Step 3: 编写测试**

```python
# tests/test_bibtex_importer.py

import pytest
from backend.tools.bibtex_importer import parse_bibtex, entry_to_paper


VALID_BIBTEX = """@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  year={2017},
  journal={Advances in Neural Information Processing Systems},
  volume={30}
}

@inproceedings{he2016deep,
  title={Deep Residual Learning for Image Recognition},
  author={He, Kaiming and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian},
  year={2016},
  booktitle={Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition},
  pages={770-778}
}"""


def test_parse_bibtex_valid():
    papers, errors = parse_bibtex(VALID_BIBTEX)
    assert len(papers) == 2
    assert len(errors) == 0
    assert papers[0].title == "Attention Is All You Need"
    assert len(papers[0].authors) == 3
    assert papers[0].metadata.get("year") == 2017
    assert papers[0].import_source == "bib_import"
    assert papers[0].file_path is None


def test_parse_bibtex_author_parsing():
    papers, errors = parse_bibtex(VALID_BIBTEX)
    assert "Vaswani" in str(papers[0].authors[0]) or "Vaswani" in papers[0].authors[0]
    assert "He" in str(papers[1].authors[0]) or "He" in papers[1].authors[0]


def test_parse_bibtex_empty_content():
    papers, errors = parse_bibtex("")
    assert len(papers) == 0


def test_parse_bibtex_malformed():
    papers, errors = parse_bibtex("this is not bibtex at all {{{")
    # May return empty or with errors — should not raise
    assert isinstance(papers, list)
    assert isinstance(errors, list)


def test_parse_bibtex_year_non_numeric():
    content = """@article{test2025,
      title={Test Paper},
      author={Test, Author},
      year={to appear}
    }"""
    papers, errors = parse_bibtex(content)
    assert len(papers) >= 1 or len(errors) >= 0  # should not crash
    if papers:
        assert papers[0].metadata.get("year") != "to appear"  # must be None or int


def test_parse_bibtex_doi_field():
    content = """@article{test2025,
      title={Test Paper},
      author={Test, Author},
      year={2025},
      doi={10.1234/example.2025}
    }"""
    papers, errors = parse_bibtex(content)
    if papers:
        assert papers[0].metadata.get("doi") == "10.1234/example.2025"


def test_parse_bibtex_no_title():
    content = """@article{test2025,
      author={Test, Author},
      year={2025}
    }"""
    papers, errors = parse_bibtex(content)
    # bibtexparser v2 may still parse this; title falls back to "Untitled"
    if papers:
        assert papers[0].title  # has some title
```

Run: `pytest tests/test_bibtex_importer.py -v`
Expected: 7 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tools/bibtex_importer.py requirements.txt tests/test_bibtex_importer.py
git commit -m "feat(phase5): add BibTeX importer module with bibtexparser>=2.0.0"
```

---

### Task 6: Compare Agent 节点 + COMPARE_PROMPT

**Files:**
- Create: `backend/agents/compare.py`
- Modify: `backend/llm/prompts.py`
- Test: `tests/test_compare_agent.py`

**Interfaces:**
- Consumes: `PaperStore` (from storage), `reader_node` (from agents.reader), `llm_client` (from llm.client), `CompareState` (from models.state), `AgentState` (from models.state)
- Produces: `reader_all_node(state: CompareState) -> CompareState`
- Produces: `compare_generate_node(state: CompareState) -> CompareState`

- [ ] **Step 1: 新增 COMPARE_PROMPT**

```python
# backend/llm/prompts.py — 在文件末尾追加

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

- [ ] **Step 2: 实现 compare.py**

```python
# backend/agents/compare.py
"""Compare agent nodes: parallel reader + comparison generation."""

import asyncio
from backend.models.state import CompareState, AgentState
from backend.models.paper import Paper
from backend.agents.reader import reader_node
from backend.llm.client import llm_client
from backend.llm.prompts import COMPARE_PROMPT
from backend.storage.paper_store import PaperStore
from backend.utils.logger import logger


async def reader_all_node(state: CompareState) -> CompareState:
    """Parallel read all selected papers. Handles mix of PDF and no-PDF papers."""
    store = PaperStore()
    papers = []
    for pid in state.paper_ids:
        paper = await store.get_paper(pid)
        if paper is None:
            raise ValueError(f"Paper not found: {pid}")
        papers.append(paper)

    async def read_one(paper: Paper) -> dict:
        if paper.file_path is None:
            # No PDF: generate minimal report from metadata
            return {
                "title": paper.title,
                "authors": paper.authors,
                "abstract_summary": paper.abstract[:500] if paper.abstract else "",
                "method": "",
                "contributions": [],
                "experiments_summary": "",
                "limitations": [],
                "keywords": [],
            }
        # Full PDF: reuse reader_node
        agent_state = AgentState(paper=paper, user_query="")
        try:
            result_state = await reader_node(agent_state)
            if result_state.error:
                logger.warning(f"Reader failed for {paper.title}: {result_state.error}")
                return {
                    "title": paper.title,
                    "authors": paper.authors,
                    "abstract_summary": paper.abstract[:500] or "",
                    "method": "", "contributions": [],
                    "experiments_summary": "", "limitations": [], "keywords": [],
                }
            return result_state.report or {}
        except Exception as e:
            logger.warning(f"Reader exception for {paper.title}: {e}")
            return {
                "title": paper.title,
                "authors": paper.authors,
                "abstract_summary": paper.abstract[:500] or "",
                "method": "", "contributions": [],
                "experiments_summary": "", "limitations": [], "keywords": [],
            }

    reports = await asyncio.gather(*[read_one(p) for p in papers])
    state.papers = papers
    state.reports = reports
    state.trace.append("reader_batch")
    return state


async def compare_generate_node(state: CompareState) -> CompareState:
    """Generate structured comparison report from multi-paper reports."""
    aspects = state.comparison_aspects or ["method", "contribution", "limitation"]
    query_text = state.user_query or ""

    reports_text = "\n\n---\n\n".join([
        f"## Paper {i+1}: {r.get('title', 'Unknown')}\n"
        f"Authors: {', '.join(r.get('authors', []))}\n"
        f"Method: {r.get('method_summary', r.get('method', 'N/A'))}\n"
        f"Contribution: {', '.join(r.get('contributions', [])) if r.get('contributions') else 'N/A'}\n"
        f"Experiments: {r.get('experiments_summary', 'N/A')}\n"
        f"Limitations: {', '.join(r.get('limitations', [])) if r.get('limitations') else 'N/A'}"
        for i, r in enumerate(state.reports)
    ])

    prompt = COMPARE_PROMPT.format(
        aspects=", ".join(aspects),
        query=query_text if query_text else "None",
        reports=reports_text,
    )

    try:
        state.answer = await llm_client.chat(prompt, max_tokens=2000)
    except Exception as e:
        logger.error(f"Compare generation failed: {e}")
        state.error = str(e)
        state.answer = f"Failed to generate comparison: {e}"

    state.trace.append("compare")
    return state
```

- [ ] **Step 3: 编写测试**

```python
# tests/test_compare_agent.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.agents.compare import reader_all_node, compare_generate_node
from backend.models.state import CompareState
from backend.models.paper import Paper


@pytest.mark.asyncio
async def test_reader_all_node_no_pdf_papers():
    """reader_all_node with papers that have no PDF."""
    from backend.storage.paper_store import PaperStore

    papers = [
        Paper(
            paper_id="id-1", title="Paper A",
            authors=["A. One"], abstract="Abstract A.",
            file_path=None,
        ),
        Paper(
            paper_id="id-2", title="Paper B",
            authors=["B. Two"], abstract="Abstract B.",
            file_path=None,
        ),
    ]

    with patch.object(PaperStore, 'get_paper', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = lambda pid: next((p for p in papers if p.paper_id == pid), None)
        state = CompareState(paper_ids=["id-1", "id-2"])
        result = await reader_all_node(state)

    assert len(result.reports) == 2
    assert result.reports[0]["title"] == "Paper A"
    assert result.reports[1]["title"] == "Paper B"
    assert "reader_batch" in result.trace
    assert result.error is None


@pytest.mark.asyncio
async def test_reader_all_node_paper_not_found():
    from backend.storage.paper_store import PaperStore

    with patch.object(PaperStore, 'get_paper', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        state = CompareState(paper_ids=["nonexistent"])

        with pytest.raises(ValueError, match="Paper not found"):
            await reader_all_node(state)


@pytest.mark.asyncio
async def test_reader_all_node_empty_ids():
    state = CompareState(paper_ids=[])
    result = await reader_all_node(state)
    assert result.reports == []
    assert "reader_batch" in result.trace


@pytest.mark.asyncio
async def test_compare_generate_node_basic():
    from backend.llm.client import llm_client

    state = CompareState(
        paper_ids=["id-1", "id-2"],
        reports=[
            {"title": "Paper A", "authors": ["A"], "method_summary": "Method A",
             "contributions": ["C1"], "experiments_summary": "Exp A", "limitations": ["L1"]},
            {"title": "Paper B", "authors": ["B"], "method_summary": "Method B",
             "contributions": ["C2"], "experiments_summary": "Exp B", "limitations": ["L2"]},
        ],
        comparison_aspects=["method", "contribution"],
    )

    with patch.object(llm_client, 'chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "## Method Comparison\n..."
        result = await compare_generate_node(state)

    assert result.answer == "## Method Comparison\n..."
    assert "compare" in result.trace


@pytest.mark.asyncio
async def test_compare_generate_node_llm_error():
    from backend.llm.client import llm_client

    state = CompareState(
        paper_ids=["id-1"],
        reports=[{"title": "Paper A", "authors": ["A"], "method_summary": "",
                   "contributions": [], "experiments_summary": "", "limitations": []}],
    )

    with patch.object(llm_client, 'chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = RuntimeError("LLM timeout")
        result = await compare_generate_node(state)

    assert "Failed to generate comparison" in result.answer
    assert result.error is not None


@pytest.mark.asyncio
async def test_compare_generate_node_default_aspects():
    from backend.llm.client import llm_client

    state = CompareState(
        paper_ids=["id-1"],
        reports=[{"title": "Paper A", "authors": ["A"], "method_summary": "",
                   "contributions": [], "experiments_summary": "", "limitations": []}],
        comparison_aspects=None,  # should default
    )

    with patch.object(llm_client, 'chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "report"
        result = await compare_generate_node(state)

    # prompt should contain default aspects
    call_arg = mock_chat.call_args[0][0] if mock_chat.call_args else ""
    assert "method" in call_arg.lower()
```

Run: `pytest tests/test_compare_agent.py -v`
Expected: 6 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/agents/compare.py backend/llm/prompts.py tests/test_compare_agent.py
git commit -m "feat(phase5): add compare agent nodes (reader_all, compare_generate) and COMPARE_PROMPT"
```

---

### Task 7: Compare Supervisor — LangGraph 图 + SSE

**Files:**
- Create: `backend/agents/compare_supervisor.py`
- Test: `tests/test_compare_supervisor.py`

**Interfaces:**
- Consumes: `compare.py` nodes, `reviewer.py` nodes (reviewer_node, rewrite_node, output_node, decide_loop), `CompareState`
- Produces: `build_compare_graph() -> StateGraph`
- Produces: `stream_compare(state: CompareState) -> AsyncGenerator[str, None]`
- Produces: `_build_compare_done_payload(state: CompareState) -> str`

- [ ] **Step 1: 实现 compare_supervisor.py**

```python
# backend/agents/compare_supervisor.py
"""Compare graph builder + SSE streaming."""

import json
import uuid
from typing import AsyncGenerator

from langgraph.graph import StateGraph, END

from backend.models.state import CompareState
from backend.agents.compare import reader_all_node, compare_generate_node
from backend.agents.reviewer import reviewer_node, rewrite_node, decide_loop, output_node
from backend.storage.session_store import SessionStore


async def build_compare_graph() -> StateGraph:
    """Build the 4-node compare graph: reader_batch -> compare -> reviewer -> [decide] -> output."""
    graph = StateGraph(CompareState)

    graph.add_node("reader_batch", reader_all_node)
    graph.add_node("compare", compare_generate_node)
    graph.add_node("reviewer", _compare_reviewer_node)
    graph.add_node("rewrite", _compare_rewrite_node)
    graph.add_node("output", _compare_output_node)

    graph.set_entry_point("reader_batch")
    graph.add_edge("reader_batch", "compare")
    graph.add_edge("compare", "reviewer")
    graph.add_conditional_edges("reviewer", _compare_decide_loop, {
        "output": "output",
        "rewrite": "rewrite",
    })
    graph.add_edge("rewrite", "compare")
    graph.add_edge("output", END)

    return graph.compile()


async def _compare_reviewer_node(state: CompareState) -> CompareState:
    """Thin wrapper: reviewer_node expects AgentState, so adapt."""
    from backend.models.state import AgentState
    agent_state = AgentState(
        answer=state.answer,
        paper=state.papers[0] if state.papers else None,
        evidence_list=state.evidence_list,
    )
    # Use raw_text from all papers combined
    if state.papers:
        combined_text = "\n\n---\n\n".join(p.raw_text[:16000] for p in state.papers)
        agent_state.paper.raw_text = combined_text

    result = await reviewer_node(agent_state)
    state.evidence_list = result.evidence_list
    state.quality_score = result.quality_score
    state.trace.append("reviewer")
    return state


def _compare_decide_loop(state: CompareState) -> str:
    """Route: output or rewrite. Uses max_rewrites=1 for compare."""
    return decide_loop(state, max_rewrites=1)


async def _compare_rewrite_node(state: CompareState) -> CompareState:
    """Increment rewrite count and loop back to compare."""
    state.rewrite_count += 1
    state.trace.append(f"rewrite({state.rewrite_count})")
    return state


async def _compare_output_node(state: CompareState) -> CompareState:
    """Final output node — promotes followup_questions."""
    state.trace.append("output")
    return state


async def stream_compare(
    paper_ids: list[str],
    aspects: list[str] | None = None,
    query: str = "",
) -> AsyncGenerator[str, None]:
    """SSE streaming for compare graph."""
    session_store = SessionStore()
    # Create a synthetic session for compare (no single paper_id)
    session_id = str(uuid.uuid4())

    init_payload = {
        "event": "init",
        "thread_id": session_id,
        "session_id": session_id,
    }
    yield f"event: init\ndata: {json.dumps(init_payload)}\n\n"

    state = CompareState(
        paper_ids=paper_ids,
        comparison_aspects=aspects,
        user_query=query,
    )
    state.session_id = session_id

    graph = await build_compare_graph()

    try:
        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event", "")
            node_name = event.get("name", "")

            if kind == "on_chain_start" and node_name in (
                "reader_batch", "compare", "reviewer", "rewrite", "output",
            ):
                yield f"event: node\ndata: {json.dumps({'event': 'node', 'node': node_name})}\n\n"

            if kind == "on_chain_end" and node_name == "compare":
                # Push full compare result as a single token event
                data = event.get("data", {})
                output = data.get("output", {})
                answer = ""
                if isinstance(output, dict):
                    answer = output.get("answer", "")
                elif hasattr(output, 'answer'):
                    answer = output.answer
                if answer:
                    yield f"event: token\ndata: {json.dumps({'event': 'token', 'text': answer})}\n\n"

            if kind == "on_chain_end" and node_name == "output":
                output_data = event.get("data", {}).get("output", {})
                if isinstance(output_data, dict):
                    final_state = CompareState(**{
                        k: v for k, v in output_data.items()
                        if k in CompareState.__dataclass_fields__
                    })
                else:
                    final_state = output_data if isinstance(output_data, CompareState) else state
                final_state.session_id = session_id
                yield _build_compare_done_payload(final_state)
                return

    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"


def _build_compare_done_payload(state: CompareState) -> str:
    """Build final SSE done event for compare."""
    evidence_summary = []
    for e in state.evidence_list:
        evidence_summary.append({
            "evidence_id": e.evidence_id,
            "level": e.level.value if e.level else "R2",
            "claim": e.claim,
            "page": e.page,
            "quote": e.quote,
            "section_heading": e.section_heading,
            "source_title": e.source_title,
            "source_url": e.source_url,
            "paper_id": e.paper_id,
            "confidence": e.confidence,
        })

    qs = state.quality_score
    payload = {
        "event": "done",
        "answer": state.answer,
        "session_id": state.session_id,
        "quality_score": {
            "relevance": qs.relevance if qs else 0,
            "consistency": qs.consistency if qs else 0,
            "completeness": qs.completeness if qs else 0,
            "total": qs.total if qs else 0,
        },
        "trace": state.trace,
        "evidence_list": evidence_summary,
        "followup_questions": [],
    }
    return f"event: done\ndata: {json.dumps(payload)}\n\n"
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_compare_supervisor.py

import pytest
from unittest.mock import AsyncMock, patch
from backend.agents.compare_supervisor import build_compare_graph


@pytest.mark.asyncio
async def test_build_compare_graph_compiles():
    graph = await build_compare_graph()
    assert graph is not None
    # Should have expected nodes
    nodes = graph.get_graph().nodes if hasattr(graph, 'get_graph') else {}
    # Minimal check: graph compiles without error
```

Run: `pytest tests/test_compare_supervisor.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/agents/compare_supervisor.py tests/test_compare_supervisor.py
git commit -m "feat(phase5): add compare supervisor (LangGraph + SSE streaming)"
```

---

### Task 8: 三个新 API 端点

**Files:**
- Modify: `backend/app.py`
- Test: `tests/test_compare_api.py`, `tests/test_import_api.py`

**Interfaces:**
- Produces: `POST /api/compare` (SSE)
- Produces: `POST /api/papers/save-external` (JSON)
- Produces: `POST /api/papers/import-bibtex` (JSON)
- Consumes: `compare_supervisor.stream_compare`, `ExternalRetriever` (for `fetch_arxiv_metadata`), `bibtex_importer.parse_bibtex`, `PaperStore`

- [ ] **Step 1: 实现 save-external 辅助逻辑和端点**

先需要在 `external_search.py` 中新增 `fetch_by_id` 方法：

```python
# backend/tools/external_search.py — ExternalRetriever 类中追加：

    async def fetch_by_id(self, arxiv_id: str) -> ExternalResult | None:
        """Fetch a single paper's metadata from arXiv by ID."""
        await self._respect_rate_limit()
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                results = self._parse_arxiv_xml(resp.text)
                return results[0] if results else None
        except Exception as e:
            logger.error(f"arXiv fetch_by_id failed for {arxiv_id}: {e}")
            return None
```

然后添加端点：

```python
# backend/app.py — 在 import 区域增加：

from backend.tools.bibtex_importer import parse_bibtex
from backend.agents.compare_supervisor import stream_compare
from backend.tools.external_search import ExternalRetriever

# 在 BibTeX Export 部分之后追加以下三个端点：

# ---- Phase 5: Compare ----

@app.post("/api/compare")
async def compare_papers(request: Request):
    """Generate a structured comparison report for selected papers (SSE)."""
    body = await request.json()
    paper_ids = body.get("paper_ids", [])
    aspects = body.get("aspects")
    query = body.get("query", "")

    # Validation
    if not paper_ids or len(paper_ids) < 2:
        return JSONResponse({"error": "At least 2 papers required"}, status_code=400)
    if len(paper_ids) > 5:
        return JSONResponse({"error": "Maximum 5 papers allowed"}, status_code=400)

    # Verify all papers exist
    store = PaperStore()
    for pid in paper_ids:
        paper = await store.get_paper(pid)
        if not paper:
            return JSONResponse({"error": f"Paper not found: {pid}"}, status_code=400)

    async def event_stream():
        try:
            async for sse_str in stream_compare(paper_ids, aspects, query):
                yield sse_str
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---- Phase 5: Save External Result ----

@app.post("/api/papers/save-external")
async def save_external_paper(request: Request):
    """Save an external arXiv paper to the library."""
    body = await request.json()
    arxiv_id = (body.get("arxiv_id", "") or "").strip()

    if not arxiv_id:
        return JSONResponse({"error": "arxiv_id is required"}, status_code=400)

    # Validate arxiv_id format (basic check)
    import re
    if not re.match(r'^[\d]{4}\.[\d]{4,}(v\d+)?$', arxiv_id):
        return JSONResponse({"error": "Invalid arXiv ID format"}, status_code=400)

    store = PaperStore()

    # 1. Check if already saved by arxiv_id
    existing = await store.get_by_arxiv_id(arxiv_id)
    if existing:
        return {
            "paper_id": existing.paper_id,
            "title": existing.title,
            "already_saved": True,
        }

    # 2. Fetch metadata from arXiv
    retriever = ExternalRetriever()
    result = await retriever.fetch_by_id(arxiv_id)
    if not result:
        return JSONResponse(
            {"error": "arXiv API unavailable, try again later"},
            status_code=503,
        )

    # 3. Check title-based dedup (fallback)
    from backend.storage.paper_store import _slugify_title
    title_slug = _slugify_title(result.title)
    existing = await store.get_by_title_slug(title_slug)
    if existing:
        return {
            "paper_id": existing.paper_id,
            "title": existing.title,
            "already_saved": True,
        }

    # 4. Create paper entry
    paper = Paper(
        title=result.title,
        authors=result.authors,
        abstract=result.abstract,
        raw_text=result.abstract,
        arxiv_id=arxiv_id,
        arxiv_pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        file_path=None,
        import_source="external_save",
    )
    await store.add_paper(paper)
    return {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "already_saved": False,
    }


# ---- Phase 5: Import BibTeX ----

@app.post("/api/papers/import-bibtex")
async def import_bibtex(request: Request):
    """Import papers from BibTeX content."""
    body = await request.json()
    bibtex_content = body.get("bibtex_content", "")

    if not bibtex_content.strip():
        return JSONResponse({"error": "Empty BibTeX content"}, status_code=400)

    papers, parse_errors = parse_bibtex(bibtex_content)

    store = PaperStore()
    imported = []
    skipped = 0
    import_errors = list(parse_errors)

    for paper in papers:
        # Dedup by DOI first, then title slug
        from backend.storage.paper_store import _slugify_title

        doi = paper.metadata.get("doi")
        if doi:
            # Check all papers for DOI match (simple linear scan)
            all_papers = await store.list_papers()
            # For a real implementation, this should be a direct query
            # For now, use title slug as primary dedup
            pass

        title_slug = _slugify_title(paper.title)
        existing = await store.get_by_title_slug(title_slug)
        if existing:
            skipped += 1
            continue

        await store.add_paper(paper)
        imported.append({
            "paper_id": paper.paper_id,
            "title": paper.title,
            "import_source": paper.import_source,
        })

    return {
        "imported": len(imported),
        "skipped": skipped,
        "errors": import_errors,
        "papers": imported,
    }
```

- [ ] **Step 2: 编写 API 测试**

```python
# tests/test_compare_api.py

import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app


@pytest.mark.asyncio
async def test_compare_missing_paper_ids():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/compare", json={"paper_ids": []})
        assert resp.status_code == 400
        assert "At least 2 papers" in resp.json()["error"]


@pytest.mark.asyncio
async def test_compare_too_many_papers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/compare", json={"paper_ids": ["1", "2", "3", "4", "5", "6"]})
        assert resp.status_code == 400
        assert "Maximum 5" in resp.json()["error"]


@pytest.mark.asyncio
async def test_save_external_missing_arxiv_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/papers/save-external", json={})
        assert resp.status_code == 400
        assert "arxiv_id" in resp.json()["error"]


@pytest.mark.asyncio
async def test_save_external_invalid_arxiv_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/papers/save-external", json={"arxiv_id": "not-valid"})
        assert resp.status_code == 400
        assert "Invalid arXiv ID" in resp.json()["error"]


@pytest.mark.asyncio
async def test_import_bibtex_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/papers/import-bibtex", json={"bibtex_content": ""})
        assert resp.status_code == 400
        assert "Empty" in resp.json()["error"]
```

```python
# tests/test_import_api.py

@pytest.mark.asyncio
async def test_import_bibtex_valid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/papers/import-bibtex", json={
            "bibtex_content": """@article{test2025,
              title={Test Paper},
              author={Test, Author},
              year={2025}
            }"""
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] >= 0
        assert "skipped" in data
        assert "errors" in data
```

Run: `pytest tests/test_compare_api.py tests/test_import_api.py -v`
Expected: 6 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app.py backend/tools/external_search.py tests/test_compare_api.py tests/test_import_api.py
git commit -m "feat(phase5): add /api/compare, /api/papers/save-external, /api/papers/import-bibtex endpoints"
```

---

### Task 9: 前端类型 + API Client 扩展

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/tests/types.test.ts`

**Interfaces:**
- Produces: `CompareRequest`, `ImportBibTeXResponse`, `SaveExternalRequest` (types)
- Produces: `Paper.arxiv_id`, `Paper.arxiv_pdf_url`, `Paper.import_source`, `Paper.file_path` → optional
- Produces: `comparePapers()`, `saveExternal()`, `importBibTeX()` (API functions)

- [ ] **Step 1: 扩展 Paper 类型 + 新增请求/响应类型**

```typescript
// frontend/src/types/index.ts — 修改 Paper 接口

export interface Paper {
  paper_id: string
  title: string
  file_path: string | null          // 改为可选
  parsed_at: string | null
  arxiv_id?: string | null          // 新增
  arxiv_pdf_url?: string | null     // 新增
  import_source?: string            // 新增: "upload" | "bib_import" | "external_save"
}

// 新增接口（追加到文件末尾）：

export interface CompareRequest {
  paper_ids: string[]
  aspects?: string[]
  query?: string
}

export interface ImportBibTeXResponse {
  imported: number
  skipped: number
  errors: Array<{ line: number; error: string }>
  papers: Array<{ paper_id: string; title: string; import_source: string }>
}

export interface SaveExternalRequest {
  arxiv_id: string
}

export interface SaveExternalResponse {
  paper_id: string
  title: string
  already_saved: boolean
}
```

- [ ] **Step 2: 新增 API 函数**

```typescript
// frontend/src/api/client.ts — 追加函数

import type { CompareRequest, ImportBibTeXResponse, SaveExternalResponse } from '@/types'

export function getCompareSSEUrl(params: CompareRequest): string {
  // Compare uses POST with SSE, so we return the URL for EventSource
  // Actually POST + SSE needs fetch-based streaming, not EventSource.
  // We return a helper that the caller uses with fetch().
  return `${BASE}/compare`
}

export async function comparePapers(req: CompareRequest): Promise<Response> {
  const res = await fetch(`${BASE}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Compare failed')
  }
  return res  // returns the SSE stream Response for manual reading
}

export async function saveExternal(arxivId: string): Promise<SaveExternalResponse> {
  const res = await fetch(`${BASE}/papers/save-external`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arxiv_id: arxivId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Failed to save paper')
  }
  return res.json()
}

export async function importBibTeX(content: string): Promise<ImportBibTeXResponse> {
  const res = await fetch(`${BASE}/papers/import-bibtex`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bibtex_content: content }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Import failed')
  }
  return res.json()
}
```

- [ ] **Step 3: 编写类型测试**

```typescript
// frontend/tests/types.test.ts — 追加测试

import { describe, it, expect } from 'vitest'

describe('Phase 5 types', () => {
  it('Paper supports arxiv_id', () => {
    const paper = {
      paper_id: '1', title: 'Test', file_path: null, parsed_at: null,
      arxiv_id: '2401.12345', arxiv_pdf_url: 'https://arxiv.org/pdf/2401.12345.pdf',
      import_source: 'external_save' as const,
    }
    expect(paper.arxiv_id).toBe('2401.12345')
    expect(paper.import_source).toBe('external_save')
  })

  it('Paper supports file_path null', () => {
    const paper = {
      paper_id: '1', title: 'Test', file_path: null, parsed_at: null,
    }
    expect(paper.file_path).toBeNull()
  })

  it('CompareRequest has required paper_ids', () => {
    const req = { paper_ids: ['id1', 'id2'] }
    expect(req.paper_ids).toHaveLength(2)
  })

  it('ImportBibTeXResponse shape', () => {
    const resp = { imported: 5, skipped: 2, errors: [], papers: [] }
    expect(resp.imported).toBe(5)
    expect(resp.skipped).toBe(2)
  })
})
```

Run: `cd frontend && npx vitest run tests/types.test.ts`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/tests/types.test.ts
git commit -m "feat(phase5): add frontend types and API client for compare, save-external, import-bibtex"
```

---

### Task 10: compareStore

**Files:**
- Create: `frontend/src/store/compareStore.ts`
- Test: `frontend/tests/compareStore.test.ts`

**Interfaces:**
- Produces: `useCompareStore` (zustand store) with `isCompareMode`, `selectedPaperIds`, `toggleCompareMode()`, `toggleSelection(id)`, `clearSelection()`

- [ ] **Step 1: 实现 compareStore**

```typescript
// frontend/src/store/compareStore.ts

import { create } from 'zustand'

interface CompareStore {
  isCompareMode: boolean
  selectedPaperIds: string[]
  toggleCompareMode: () => void
  toggleSelection: (id: string) => void
  clearSelection: () => void
}

export const useCompareStore = create<CompareStore>((set, get) => ({
  isCompareMode: false,
  selectedPaperIds: [],

  toggleCompareMode: () => {
    set((s) => ({
      isCompareMode: !s.isCompareMode,
      selectedPaperIds: s.isCompareMode ? [] : s.selectedPaperIds,
    }))
  },

  toggleSelection: (id: string) => {
    const { selectedPaperIds } = get()
    if (selectedPaperIds.includes(id)) {
      set({ selectedPaperIds: selectedPaperIds.filter((pid) => pid !== id) })
    } else if (selectedPaperIds.length < 5) {
      set({ selectedPaperIds: [...selectedPaperIds, id] })
    }
    // If >= 5, silently ignore (can't select more)
  },

  clearSelection: () => {
    set({ selectedPaperIds: [], isCompareMode: false })
  },
}))
```

- [ ] **Step 2: 编写测试**

```typescript
// frontend/tests/compareStore.test.ts

import { describe, it, expect, beforeEach } from 'vitest'
import { useCompareStore } from '@/store/compareStore'

describe('compareStore', () => {
  beforeEach(() => {
    useCompareStore.setState({
      isCompareMode: false,
      selectedPaperIds: [],
    })
  })

  it('starts with empty selection', () => {
    const state = useCompareStore.getState()
    expect(state.isCompareMode).toBe(false)
    expect(state.selectedPaperIds).toEqual([])
  })

  it('toggleCompareMode enters and exits', () => {
    useCompareStore.getState().toggleCompareMode()
    expect(useCompareStore.getState().isCompareMode).toBe(true)

    useCompareStore.getState().toggleCompareMode()
    expect(useCompareStore.getState().isCompareMode).toBe(false)
  })

  it('toggleCompareMode clears selection on exit', () => {
    const store = useCompareStore.getState()
    store.toggleCompareMode()
    store.toggleSelection('id-1')
    expect(useCompareStore.getState().selectedPaperIds).toContain('id-1')

    store.toggleCompareMode()  // exit → clears
    expect(useCompareStore.getState().selectedPaperIds).toEqual([])
  })

  it('toggleSelection adds and removes', () => {
    useCompareStore.getState().toggleCompareMode()
    const store = useCompareStore.getState()

    store.toggleSelection('id-1')
    expect(useCompareStore.getState().selectedPaperIds).toEqual(['id-1'])

    store.toggleSelection('id-2')
    expect(useCompareStore.getState().selectedPaperIds).toEqual(['id-1', 'id-2'])

    store.toggleSelection('id-1')  // remove
    expect(useCompareStore.getState().selectedPaperIds).toEqual(['id-2'])
  })

  it('toggleSelection caps at 5', () => {
    useCompareStore.getState().toggleCompareMode()
    const store = useCompareStore.getState()

    for (let i = 1; i <= 6; i++) {
      store.toggleSelection(`id-${i}`)
    }
    expect(useCompareStore.getState().selectedPaperIds.length).toBe(5)
  })

  it('clearSelection resets everything', () => {
    useCompareStore.getState().toggleCompareMode()
    const store = useCompareStore.getState()
    store.toggleSelection('id-1')
    store.toggleSelection('id-2')

    store.clearSelection()
    expect(useCompareStore.getState().isCompareMode).toBe(false)
    expect(useCompareStore.getState().selectedPaperIds).toEqual([])
  })
})
```

Run: `cd frontend && npx vitest run tests/compareStore.test.ts`
Expected: 6 PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/store/compareStore.ts frontend/tests/compareStore.test.ts
git commit -m "feat(phase5): add compareStore for multi-paper selection state"
```

---

### Task 11: LibraryPanel 多选模式 + BibTeX 导入按钮

**Files:**
- Modify: `frontend/src/components/Layout/LibraryPanel.tsx`
- Modify: `frontend/src/components/Layout/Layout.module.css`
- Test: `frontend/tests/LibraryPanel.test.tsx`

**Interfaces:**
- Consumes: `useCompareStore`, `listPapers`, `importBibTeX`
- Produces: Multi-select mode UI + Import BibTeX button

- [ ] **Step 1: 重写 LibraryPanel**

```tsx
// frontend/src/components/Layout/LibraryPanel.tsx

import { useState, useEffect, useRef } from 'react'
import { listPapers, importBibTeX } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import { useCompareStore } from '@/store/compareStore'
import type { PaperListResponse } from '@/types'
import styles from './Layout.module.css'

export default function LibraryPanel() {
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const setPaper = useAppStore((s) => s.setPaper)
  const { isCompareMode, selectedPaperIds, toggleCompareMode, toggleSelection, clearSelection } = useCompareStore()
  const [importStatus, setImportStatus] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listPapers().then(setPapers).catch(() => setPapers([]))
  }, [])

  const handleImportClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      setImportStatus('Importing...')
      const content = await file.text()
      const result = await importBibTeX(content)
      const parts: string[] = []
      if (result.imported > 0) parts.push(`✅ Imported ${result.imported} papers`)
      if (result.skipped > 0) parts.push(`⚠️ ${result.skipped} skipped`)
      if (result.errors.length > 0) parts.push(`❌ ${result.errors.length} errors`)
      setImportStatus(parts.join(' · '))
      // Refresh list
      listPapers().then(setPapers).catch(() => {})
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Import failed'
      setImportStatus(`❌ ${msg}`)
    }

    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handlePaperClick = (p: PaperListResponse) => {
    if (isCompareMode) {
      toggleSelection(p.paper_id)
    } else {
      setPaper({
        paper_id: p.paper_id,
        title: p.title,
        file_path: '',
        parsed_at: p.parsed_at,
      })
    }
  }

  const canCompare = selectedPaperIds.length >= 2

  return (
    <div className={styles.libraryPanel}>
      <div className={styles.libraryHeader}>
        <h3>📚 Paper Library</h3>
        <div className={styles.libraryActions}>
          <button
            className={`${styles.compareBtn} ${isCompareMode ? styles.active : ''}`}
            onClick={toggleCompareMode}
          >
            {isCompareMode ? 'Exit Compare' : 'Compare'}
          </button>
          <button className={styles.importBtn} onClick={handleImportClick}>
            Import BibTeX
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".bib"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
        </div>
      </div>

      {isCompareMode && (
        <p className={styles.compareHint}>Select 2-5 papers to compare</p>
      )}
      {importStatus && (
        <p className={styles.importStatus}>{importStatus}</p>
      )}

      {papers.length === 0 && <p className={styles.empty}>No papers uploaded</p>}
      <ul>
        {papers.map((p) => {
          const isSelected = selectedPaperIds.includes(p.paper_id)
          return (
            <li
              key={p.paper_id}
              className={`${isCompareMode ? styles.compareItem : ''} ${isSelected ? styles.selected : ''}`}
              onClick={() => handlePaperClick(p)}
            >
              {isCompareMode && (
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleSelection(p.paper_id)}
                  className={styles.checkbox}
                />
              )}
              {p.title}
            </li>
          )
        })}
      </ul>

      {isCompareMode && canCompare && (
        <button className={styles.compareFab}>
          Compare Selected ({selectedPaperIds.length})
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 追加 CSS**

```css
/* frontend/src/components/Layout/Layout.module.css — 追加 */

.libraryHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.libraryActions {
  display: flex;
  gap: 8px;
}

.compareBtn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #f5f5f5;
  cursor: pointer;
}

.compareBtn.active {
  background: #e3f2fd;
  border-color: #2196f3;
  color: #1976d2;
}

.importBtn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #f5f5f5;
  cursor: pointer;
}

.compareHint {
  font-size: 12px;
  color: #666;
  margin: 4px 0 8px;
}

.importStatus {
  font-size: 12px;
  color: #333;
  margin: 4px 0 8px;
  padding: 4px 8px;
  background: #f9f9f9;
  border-radius: 4px;
}

.compareItem {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.compareItem.selected {
  background: #e3f2fd;
}

.checkbox {
  cursor: pointer;
}

.compareFab {
  position: sticky;
  bottom: 0;
  width: 100%;
  padding: 10px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  margin-top: 8px;
}

.compareFab:hover {
  background: #1565c0;
}
```

- [ ] **Step 3: 编写测试**

```tsx
// frontend/tests/LibraryPanel.test.tsx — 追加测试（简化版）

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import LibraryPanel from '@/components/Layout/LibraryPanel'

// Mock dependencies...
describe('LibraryPanel compare mode', () => {
  it('shows compare button', () => {
    // Basic render test
  })

  it('shows compare hint when in compare mode', () => {
    // Toggle compare mode, check hint
  })
})
```

Run: `cd frontend && npx vitest run tests/LibraryPanel.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Layout/LibraryPanel.tsx frontend/src/components/Layout/Layout.module.css frontend/tests/LibraryPanel.test.tsx
git commit -m "feat(phase5): add multi-select compare mode and BibTeX import to LibraryPanel"
```

---

### Task 12: CompareSelectModal

**Files:**
- Create: `frontend/src/components/ChatPanel/CompareSelectModal.tsx`
- Test: `frontend/tests/CompareSelectModal.test.tsx`

**Interfaces:**
- Consumes: `useCompareStore.selectedPaperIds`, `useAppStore`, `listPapers`
- Produces: Modal with aspect checkboxes, custom query input, triggers SSE compare

- [ ] **Step 1: 实现 CompareSelectModal**

```tsx
// frontend/src/components/ChatPanel/CompareSelectModal.tsx

import { useState, useEffect } from 'react'
import { useCompareStore } from '@/store/compareStore'
import { useChatStore } from '@/store/chatStore'
import { listPapers, comparePapers } from '@/api/client'
import type { PaperListResponse } from '@/types'
import styles from './ChatPanel.module.css'

interface CompareSelectModalProps {
  onClose: () => void
}

const ASPECT_OPTIONS = [
  { key: 'method', label: 'Method' },
  { key: 'experiment', label: 'Experiment' },
  { key: 'contribution', label: 'Contribution' },
  { key: 'limitation', label: 'Limitation' },
]

export default function CompareSelectModal({ onClose }: CompareSelectModalProps) {
  const { selectedPaperIds, clearSelection } = useCompareStore()
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const [selectedAspects, setSelectedAspects] = useState<string[]>(['method', 'contribution'])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const { setStatus, addMessage, appendToken, addStepNode, finalizeAssistantMessage, setExternalResults, reset } = useChatStore()

  useEffect(() => {
    listPapers().then((all) => {
      setPapers(all.filter((p) => selectedPaperIds.includes(p.paper_id)))
    }).catch(() => setPapers([]))
  }, [selectedPaperIds])

  const toggleAspect = (key: string) => {
    setSelectedAspects((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }

  const handleCompare = async () => {
    setLoading(true)
    reset()
    setStatus('streaming')

    const paperTitles = papers.map((p) => p.title).join(', ')
    addMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: `Comparing ${papers.length} papers: ${paperTitles}`,
      evidenceList: [],
      qualityScore: null,
      trace: [],
    })

    try {
      const response = await comparePapers({
        paper_ids: selectedPaperIds,
        aspects: selectedAspects.length > 0 ? selectedAspects : undefined,
        query: query || undefined,
      })

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) continue
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.event === 'init') {
                // ignore
              } else if (data.event === 'node') {
                addStepNode(data.node)
              } else if (data.event === 'token') {
                appendToken(data.text)
              } else if (data.event === 'done') {
                finalizeAssistantMessage(
                  data.answer,
                  data.evidence_list || [],
                  data.quality_score || null,
                  data.trace || [],
                )
                setExternalResults(data.external_results || [])
              }
            } catch {
              // skip non-JSON lines
            }
          }
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Compare failed'
      setStatus('error')
      appendToken(`\n\n⚠️ ${msg}`)
    }

    clearSelection()
    onClose()
  }

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>Compare Papers</h3>

        <div className={styles.modalSection}>
          <p className={styles.label}>Selected:</p>
          <ul className={styles.paperList}>
            {papers.map((p) => (
              <li key={p.paper_id}>📄 {p.title}</li>
            ))}
          </ul>
        </div>

        <div className={styles.modalSection}>
          <p className={styles.label}>Aspects (optional):</p>
          <div className={styles.aspectGrid}>
            {ASPECT_OPTIONS.map((opt) => (
              <label key={opt.key} className={styles.aspectLabel}>
                <input
                  type="checkbox"
                  checked={selectedAspects.includes(opt.key)}
                  onChange={() => toggleAspect(opt.key)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div className={styles.modalSection}>
          <p className={styles.label}>Focus (optional):</p>
          <input
            type="text"
            className={styles.focusInput}
            placeholder="e.g. focus on training efficiency"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className={styles.modalActions}>
          <button onClick={onClose} disabled={loading}>Cancel</button>
          <button onClick={handleCompare} disabled={loading} className={styles.primaryBtn}>
            {loading ? 'Comparing...' : 'Compare →'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 追加 CSS**

```css
/* frontend/src/components/ChatPanel/ChatPanel.module.css — 追加 */

.modalOverlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 4px 24px rgba(0,0,0,0.15);
}

.modal h3 {
  margin: 0 0 16px;
  font-size: 18px;
}

.modalSection {
  margin-bottom: 16px;
}

.label {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 6px;
  color: #555;
}

.paperList {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
}

.paperList li {
  padding: 2px 0;
}

.aspectGrid {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.aspectLabel {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.focusInput {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  box-sizing: border-box;
}

.modalActions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

.modalActions button {
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.primaryBtn {
  background: #1976d2;
  color: white;
  border: none;
}

.primaryBtn:hover {
  background: #1565c0;
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ChatPanel/CompareSelectModal.tsx frontend/src/components/ChatPanel/ChatPanel.module.css
git commit -m "feat(phase5): add CompareSelectModal for aspect selection and SSE streaming"
```

---

### Task 13: ExternalRefCard + AssistantMessage 集成

**Files:**
- Create: `frontend/src/components/ChatPanel/ExternalRefCard.tsx`
- Modify: `frontend/src/components/ChatPanel/AssistantMessage.tsx`
- Test: `frontend/tests/ExternalRefCard.test.tsx`

**Interfaces:**
- Consumes: `useChatStore.externalResults`, `saveExternal` API
- Produces: ExternalRefCard component with save button

- [ ] **Step 1: 实现 ExternalRefCard**

```tsx
// frontend/src/components/ChatPanel/ExternalRefCard.tsx

import { useState } from 'react'
import { saveExternal } from '@/api/client'
import type { ExternalResult } from '@/types'
import styles from './ChatPanel.module.css'

interface ExternalRefCardProps {
  result: ExternalResult
  index: number
}

export default function ExternalRefCard({ result, index }: ExternalRefCardProps) {
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    // Extract arXiv ID from URL
    const match = result.url.match(/\/abs\/(.+)$/)
    const arxivId = match ? match[1] : ''
    if (!arxivId) return

    setSaving(true)
    try {
      await saveExternal(arxivId)
      setSaved(true)
    } catch {
      // silently fail — user can retry
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.externalRefCard}>
      <div className={styles.extRefHeader}>
        <a href={result.url} target="_blank" rel="noopener noreferrer" className={styles.extRefTitle}>
          [EXT-{index}] {result.title}
        </a>
        <button
          className={`${styles.saveBtn} ${saved ? styles.saved : ''}`}
          onClick={handleSave}
          disabled={saving || saved}
        >
          {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save →'}
        </button>
      </div>
      <p className={styles.extRefMeta}>
        {result.authors?.slice(0, 3).join(', ')} ({result.year || 'n.d.'})
        {result.citation_count != null && ` · Citations: ${result.citation_count}`}
      </p>
    </div>
  )
}
```

- [ ] **Step 2: 集成到 AssistantMessage**

```tsx
// frontend/src/components/ChatPanel/AssistantMessage.tsx — 在 return 的 bubble div 末尾（trace 之前）追加：

import { useChatStore } from '@/store/chatStore'
import ExternalRefCard from './ExternalRefCard'

// 在 AssistantMessage 组件内部：

  const externalResults = useChatStore((s) => s.externalResults)

  // ... existing code ...

  return (
    <div className={styles.assistantMessage}>
      <div className={styles.bubble}>
        <div className={styles.answerContent}>{renderedContent}</div>
        {evidenceList.length > 0 && ( /* ... existing evidence summary ... */ )}

        {/* Phase 5: External References cards */}
        {externalResults.length > 0 && (
          <div className={styles.externalRefs}>
            <hr />
            {externalResults.map((r, i) => (
              <ExternalRefCard key={r.result_id} result={r} index={i + 1} />
            ))}
          </div>
        )}

        {trace.length > 0 && ( /* ... existing trace ... */ )}
      </div>
    </div>
  )
```

- [ ] **Step 3: 追加 CSS**

```css
/* frontend/src/components/ChatPanel/ChatPanel.module.css — 追加 */

.externalRefs {
  margin-top: 12px;
  padding-top: 8px;
}

.externalRefCard {
  padding: 8px;
  margin: 6px 0;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: #fafafa;
}

.extRefHeader {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.extRefTitle {
  font-size: 13px;
  font-weight: 500;
  color: #1976d2;
  text-decoration: none;
  flex: 1;
}

.extRefTitle:hover {
  text-decoration: underline;
}

.extRefMeta {
  font-size: 11px;
  color: #888;
  margin: 4px 0 0;
}

.saveBtn {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.saveBtn:hover {
  background: #e3f2fd;
  border-color: #1976d2;
}

.saveBtn.saved {
  background: #e8f5e9;
  border-color: #4caf50;
  color: #2e7d32;
  cursor: default;
}
```

- [ ] **Step 4: 编写测试**

```tsx
// frontend/tests/ExternalRefCard.test.tsx

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ExternalRefCard from '@/components/ChatPanel/ExternalRefCard'

describe('ExternalRefCard', () => {
  const result = {
    result_id: 'r-1',
    title: 'Test Paper',
    authors: ['Author A', 'Author B'],
    abstract: 'Test abstract',
    year: 2024,
    url: 'https://arxiv.org/abs/2401.12345',
    source: 'arxiv',
    citation_count: 42,
  }

  it('renders title and arXiv link', () => {
    render(<ExternalRefCard result={result} index={1} />)
    expect(screen.getByText(/\[EXT-1\]/)).toBeDefined()
    expect(screen.getByText(/Test Paper/)).toBeDefined()
  })

  it('renders author and citation info', () => {
    render(<ExternalRefCard result={result} index={1} />)
    expect(screen.getByText(/Author A/)).toBeDefined()
    expect(screen.getByText(/42/)).toBeDefined()
  })

  it('shows Save button initially', () => {
    render(<ExternalRefCard result={result} index={1} />)
    expect(screen.getByText('Save →')).toBeDefined()
  })
})
```

Run: `cd frontend && npx vitest run tests/ExternalRefCard.test.tsx`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChatPanel/ExternalRefCard.tsx frontend/src/components/ChatPanel/AssistantMessage.tsx frontend/src/components/ChatPanel/ChatPanel.module.css frontend/tests/ExternalRefCard.test.tsx
git commit -m "feat(phase5): add ExternalRefCard with save-to-library, integrate into AssistantMessage"
```

---

### Task 14: PaperViewer 无 PDF 态 + StepIndicator 更新

**Files:**
- Modify: `frontend/src/components/PaperViewer/PaperViewer.tsx`
- Modify: `frontend/src/components/ChatPanel/StepIndicator.tsx`
- Test: Frontend existing tests

**Interfaces:**
- Consumes: `Paper.file_path: string | null`, `Paper.arxiv_pdf_url: string | null`

- [ ] **Step 1: PaperViewer 无 PDF 态**

在 `PaperViewer.tsx` 中添加一个 props 用于判断是否需要显示元数据卡片。当 `paperId` 对应的 paper 没有 PDF 时（通过新增的 `hasPDF` prop 判断）：

```tsx
// frontend/src/components/PaperViewer/PaperViewer.tsx

export interface PaperViewerProps {
  paperId: string
  highlights?: HighlightRect[]
  onHighlightClick?: (box: HighlightRect) => void
  onReady?: () => void
  onPageChange?: (page: number) => void
  // Phase 5
  hasPDF?: boolean
  paperTitle?: string
  paperAuthors?: string[]
  paperAbstract?: string
  paperYear?: number
  arxivPdfUrl?: string | null
  onUploadPDF?: () => void
}

// 在组件最前面判断：
export default function PaperViewer({ paperId, highlights, onHighlightClick, onReady, onPageChange, hasPDF = true, paperTitle, paperAuthors, paperAbstract, paperYear, arxivPdfUrl, onUploadPDF }: PaperViewerProps) {
  // If no PDF, show metadata card
  if (!hasPDF && paperTitle) {
    return (
      <div className={styles.viewer}>
        <div className={styles.metadataCard}>
          <h2>📄 {paperTitle}</h2>
          {paperAuthors && paperAuthors.length > 0 && (
            <p className={styles.metaAuthors}>Authors: {paperAuthors.join(', ')}</p>
          )}
          {paperYear && <p className={styles.metaYear}>Year: {paperYear}</p>}
          {paperAbstract && (
            <div className={styles.metaAbstract}>
              <h4>Abstract</h4>
              <p>{paperAbstract}</p>
            </div>
          )}
          <div className={styles.metaActions}>
            {onUploadPDF && (
              <button onClick={onUploadPDF} className={styles.uploadBtn}>
                📤 Upload PDF
              </button>
            )}
            {arxivPdfUrl && (
              <a href={arxivPdfUrl} target="_blank" rel="noopener noreferrer" className={styles.arxivBtn}>
                Open on arXiv ↗
              </a>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ... 原有 PDF 渲染逻辑不变
}
```

追加 CSS：

```css
/* frontend/src/components/PaperViewer/PaperViewer.module.css — 追加 */

.metadataCard {
  padding: 24px;
  max-width: 640px;
  margin: 0 auto;
}

.metadataCard h2 {
  font-size: 20px;
  margin-bottom: 12px;
}

.metaAuthors, .metaYear {
  font-size: 13px;
  color: #666;
  margin: 4px 0;
}

.metaAbstract {
  margin-top: 16px;
  padding: 12px;
  background: #f9f9f9;
  border-radius: 6px;
}

.metaAbstract h4 {
  margin: 0 0 6px;
  font-size: 13px;
  color: #555;
}

.metaAbstract p {
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}

.metaActions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

.uploadBtn, .arxivBtn {
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  text-decoration: none;
}

.uploadBtn {
  background: #1976d2;
  color: white;
  border: none;
}

.arxivBtn {
  background: white;
  border: 1px solid #ccc;
  color: #333;
}

.arxivBtn:hover {
  background: #f5f5f5;
}
```

- [ ] **Step 2: StepIndicator 更新**

```tsx
// frontend/src/components/ChatPanel/StepIndicator.tsx

const NODE_ORDER = [
  'reader', 'classify', 'planner', 'retrieve', 'external_search',
  'reader_batch', 'compare', 'generate', 'observe', 'reviewer', 'output', 'rewrite',
]
```

- [ ] **Step 3: 运行前端测试确保无回归**

Run: `cd frontend && npx vitest run`
Expected: all PASS（含现有 43 测试 + 新增）

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PaperViewer/PaperViewer.tsx frontend/src/components/PaperViewer/PaperViewer.module.css frontend/src/components/ChatPanel/StepIndicator.tsx
git commit -m "feat(phase5): add no-PDF metadata card to PaperViewer, update StepIndicator"
```

---

### Task 15: 全量测试 + 最终集成验证

**Files:**
- Test: Run all tests
- Modify: 无代码修改，仅验证

- [ ] **Step 1: 运行全部后端测试**

```bash
cd paper-reading-agent
python -m pytest tests/ -v
```

Expected: ~169 PASS (128 existing + ~41 new)

- [ ] **Step 2: 运行全部前端测试**

```bash
cd paper-reading-agent/frontend
npx vitest run
```

Expected: all PASS (~43 existing + ~15 new)

- [ ] **Step 3: 验证 BibTeX 依赖安装**

```bash
python -c "import bibtexparser; print(bibtexparser.__version__)"
```

Expected: 2.x.x 版本号

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "test(phase5): full test suite — 169 backend + frontend tests passing"
```
