# Phase 4a: BibTeX 批量导出 + FlashRank 重排序可视化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BibTeX export for paper references and surface FlashRank reranker info in trace/SSE.

**Architecture:** Two independent features. BibTeX: DB migration → reference extraction → API → frontend button. Reranker: add name/model_name properties to ABC → populate in retrieve_node trace → expose in done SSE → render in TracePanel.

**Tech Stack:** Python/FastAPI/SQLite (backend), React/TypeScript (frontend), existing FlashRank/BM25 reranker module.

## Global Constraints

- No new dependencies (pip/npm)
- No new files created — all changes in existing files
- Backend tests: pytest in `paper-reading-agent/tests/`
- Frontend tests: vitest in `paper-reading-agent/frontend/`
- Commit after each task with `feat(phase4a):` prefix
- `backend/tools/reranker.py` — Reranker ABC gets `name` (abstract) + `model_name` (concrete, default None)
- BibTeX cite_key: Chinese-author surname降级为 `"anonymous"`

---

### Task 1: DB migration + PaperStore — persist references

**Files:**
- Modify: `paper-reading-agent/backend/storage/database.py:18-49`
- Modify: `paper-reading-agent/backend/storage/paper_store.py:1-59`

**Interfaces:**
- Produces: `papers` table gains `references TEXT NOT NULL DEFAULT '[]'` column; `PaperStore.add_paper()` persists `references`; `PaperStore.get_paper()` loads `references` with `json.loads()`

- [ ] **Step 1: Add references column to database migration**

In `paper-reading-agent/backend/storage/database.py`, modify the `_migrate` method to add the `references` column:

```python
async def _migrate(self, conn: aiosqlite.Connection):
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            authors TEXT NOT NULL DEFAULT '[]',
            abstract TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            raw_text TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'en',
            file_path TEXT NOT NULL DEFAULT '',
            parsed_at TEXT NOT NULL DEFAULT '',
            cache_path TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            meta TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
    """)
    # Phase 4a: add references column if it doesn't exist
    try:
        await conn.execute("ALTER TABLE papers ADD COLUMN references TEXT NOT NULL DEFAULT '[]'")
    except Exception:
        pass  # column already exists
    await conn.commit()
```

- [ ] **Step 2: Add helper functions and update PaperStore.add_paper()**

In `paper-reading-agent/backend/storage/paper_store.py`, replace the entire file:

```python
import json
from backend.models.paper import Paper, Reference
from backend.storage.database import db


def _ref_to_dict(ref: Reference) -> dict:
    return {
        "title": ref.title,
        "authors": ref.authors,
        "year": ref.year,
        "venue": ref.venue,
        "doi": ref.doi,
        "url": ref.url,
    }


def _dict_to_ref(d: dict) -> Reference:
    return Reference(
        title=d.get("title", ""),
        authors=d.get("authors", []),
        year=d.get("year"),
        venue=d.get("venue"),
        doi=d.get("doi"),
        url=d.get("url"),
    )


class PaperStore:
    async def add_paper(self, paper: Paper) -> Paper:
        conn = await db.get_db()
        try:
            await conn.execute(
                """INSERT OR REPLACE INTO papers
                   (paper_id, title, authors, abstract, metadata, raw_text, language, file_path, parsed_at, references)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (paper.paper_id, paper.title, json.dumps(paper.authors), paper.abstract,
                 json.dumps(paper.metadata), paper.raw_text, paper.language, paper.file_path,
                 paper.parsed_at, json.dumps([_ref_to_dict(r) for r in paper.references]))
            )
            await conn.commit()
            return paper
        finally:
            await conn.close()

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
                return Paper(
                    paper_id=row["paper_id"], title=row["title"],
                    authors=json.loads(row["authors"]), abstract=row["abstract"],
                    metadata=json.loads(row["metadata"]), raw_text=row["raw_text"],
                    language=row["language"], file_path=row["file_path"],
                    parsed_at=row["parsed_at"],
                    references=[_dict_to_ref(r) for r in json.loads(refs_raw)],
                )
        finally:
            await conn.close()

    async def list_papers(self) -> list[Paper]:
        conn = await db.get_db()
        try:
            papers = []
            async with conn.execute(
                "SELECT paper_id, title, authors, parsed_at FROM papers ORDER BY parsed_at DESC"
            ) as cursor:
                async for row in cursor:
                    papers.append(Paper(
                        paper_id=row["paper_id"], title=row["title"],
                        authors=json.loads(row["authors"]), parsed_at=row["parsed_at"]
                    ))
            return papers
        finally:
            await conn.close()

    async def delete_paper(self, paper_id: str) -> bool:
        conn = await db.get_db()
        try:
            cursor = await conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()
```

- [ ] **Step 3: Write tests for references persistence**

In `paper-reading-agent/tests/test_storage.py`, add:

```python
import pytest


@pytest.mark.asyncio
async def test_paper_references_roundtrip():
    """References are persisted and loaded correctly."""
    from backend.models.paper import Paper, Reference
    from backend.storage.paper_store import PaperStore
    store = PaperStore()
    paper = Paper(
        title="Test Paper",
        references=[
            Reference(title="Ref One", authors=["Alice Bob"], year=2020, venue="Test Venue", doi="10.1234/test"),
            Reference(title="Ref Two", authors=["Charlie"], year=2021),
        ],
    )
    await store.add_paper(paper)
    loaded = await store.get_paper(paper.paper_id)
    assert loaded is not None
    assert len(loaded.references) == 2
    assert loaded.references[0].title == "Ref One"
    assert loaded.references[0].authors == ["Alice Bob"]
    assert loaded.references[0].year == 2020
    assert loaded.references[0].venue == "Test Venue"
    assert loaded.references[0].doi == "10.1234/test"
    assert loaded.references[1].title == "Ref Two"


@pytest.mark.asyncio
async def test_paper_empty_references():
    """Paper with no references loads with empty list."""
    from backend.models.paper import Paper
    from backend.storage.paper_store import PaperStore
    store = PaperStore()
    paper = Paper(title="No Refs Paper")
    await store.add_paper(paper)
    loaded = await store.get_paper(paper.paper_id)
    assert loaded is not None
    assert loaded.references == []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd paper-reading-agent && python -m pytest tests/test_storage.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/storage/database.py paper-reading-agent/backend/storage/paper_store.py paper-reading-agent/tests/test_storage.py
git commit -m "feat(phase4a): add references column to papers table, persist in PaperStore"
```

---

### Task 2: Reference extraction in PDF parser

**Files:**
- Modify: `paper-reading-agent/backend/tools/pdf_parser.py`
- Modify: `paper-reading-agent/tests/test_pdf_parser.py`

**Interfaces:**
- Consumes: `Paper.references: list[Reference]` (existing model, currently unused)
- Produces: `PDFParser.parse()` populates `paper.references` via `_extract_references()`

- [ ] **Step 1: Add _extract_references method to PDFParser**

In `paper-reading-agent/backend/tools/pdf_parser.py`, add import for Reference at top:

```python
from backend.models.paper import Paper, Section, Reference
```

Add the `_extract_references` method to `PDFParser` class (before `parse` or after existing methods):

```python
def _extract_references(self, text: str) -> list[Reference]:
    """Extract references from paper text using regex patterns.

    Looks for:
    1. DOIs (10.XXXX/XXXX)
    2. arXiv IDs (arXiv:XXXX.XXXXX)
    3. Structured citation lines in [N] Author, "Title", Venue, Year format

    Returns list of Reference objects.
    """
    refs: list[Reference] = []
    seen_dois: set[str] = set()

    # Pattern 1: DOI — 10.XXXX/XXXX
    doi_pattern = r'\b(10\.\d{4,}/[^\s\]\)\},;]+)'
    for match in re.finditer(doi_pattern, text):
        doi = match.group(1).rstrip('.,;')
        if doi in seen_dois:
            continue
        seen_dois.add(doi)
        refs.append(Reference(title="", doi=doi))

    # Pattern 2: arXiv ID — arXiv:XXXX.XXXXX or arXiv:XXXX.XXXXXvN
    arxiv_pattern = r'(?:arXiv:\s*)(\d{4}\.\d{4,}(?:v\d+)?)'
    for match in re.finditer(arxiv_pattern, text, re.IGNORECASE):
        arxiv_id = match.group(1)
        refs.append(Reference(
            title="",
            url=f"https://arxiv.org/abs/{arxiv_id}",
        ))

    # Pattern 3: Bracketed references — [1] Author. "Title". Venue, Year.
    bracket_ref = re.finditer(
        r'\[(\d+)\]\s+(.+?)\.\s*"([^"]+)"\.\s*(?:In\s+)?([^,.]*?)(?:,\s*(\d{4}))?',
        text,
    )
    for match in bracket_ref:
        authors_str = match.group(2)
        title = match.group(3)
        venue = match.group(4).strip() if match.group(4) else ""
        year_str = match.group(5)
        year = int(year_str) if year_str else None
        authors = [a.strip() for a in authors_str.split(" and ")]
        refs.append(Reference(
            title=title,
            authors=authors,
            year=year,
            venue=venue if venue else None,
        ))

    return refs
```

- [ ] **Step 2: Call _extract_references in parse()**

In the `parse()` method, locate `return paper` and insert before it:

```python
# Extract references from raw text
paper.references = self._extract_references(paper.raw_text)

return paper
```

- [ ] **Step 3: Write tests for reference extraction**

In `paper-reading-agent/tests/test_pdf_parser.py`, add:

```python
def test_extract_doi():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    refs = parser._extract_references("Some text with DOI: 10.1234/abcdef.123 and another one.")
    dois = [r.doi for r in refs if r.doi]
    assert "10.1234/abcdef.123" in dois


def test_extract_arxiv():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    refs = parser._extract_references("See also arXiv: 2310.12345 for more details.")
    urls = [r.url for r in refs if r.url]
    assert any("2310.12345" in u for u in urls)


def test_extract_empty_text():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    assert parser._extract_references("") == []


def test_extract_doi_deduplication():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    text = "Ref 1 has DOI: 10.1234/test. Ref 2 also has DOI: 10.1234/test."
    refs = parser._extract_references(text)
    doi_refs = [r for r in refs if r.doi]
    assert len(doi_refs) == 1


def test_extract_bracketed_reference():
    from backend.tools.pdf_parser import PDFParser
    parser = PDFParser()
    text = '[1] Kaiming He and Xiangyu Zhang. "Deep Residual Learning". Proceedings of CVPR, 2016.'
    refs = parser._extract_references(text)
    bracketed = [r for r in refs if r.title == "Deep Residual Learning"]
    assert len(bracketed) == 1
    assert bracketed[0].authors == ["Kaiming He", "Xiangyu Zhang"]
    assert bracketed[0].year == 2016
    assert "CVPR" in (bracketed[0].venue or "")
```

- [ ] **Step 4: Run tests**

```bash
cd paper-reading-agent && python -m pytest tests/test_pdf_parser.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/tools/pdf_parser.py paper-reading-agent/tests/test_pdf_parser.py
git commit -m "feat(phase4a): add regex-based reference extraction to PDF parser"
```

---

### Task 3: BibTeX export API endpoint

**Files:**
- Modify: `paper-reading-agent/backend/app.py` (add route + helper functions)
- Create: `paper-reading-agent/tests/test_bibtex_export.py` (new test file)

**Interfaces:**
- Consumes: `PaperStore.get_paper()` (now returns Paper with references)
- Produces: `GET /api/papers/{paper_id}/references/export?format=bib`

- [ ] **Step 1: Write the failing tests**

Create `paper-reading-agent/tests/test_bibtex_export.py`:

```python
import pytest
from backend.app import app
from backend.models.paper import Paper, Reference
from backend.storage.paper_store import PaperStore
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_export_bibtex_empty_references(client):
    """Paper with no references returns comment-only .bib."""
    store = PaperStore()
    paper = Paper(title="Empty Paper", references=[])
    await store.add_paper(paper)
    res = await client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
    assert res.status_code == 200
    assert "% No references found" in res.text


@pytest.mark.asyncio
async def test_export_bibtex_not_found(client):
    """Non-existent paper returns 404."""
    res = await client.get("/api/papers/nonexistent-id/references/export?format=bib")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_export_bibtex_article(client):
    """Journal article reference exports correctly."""
    store = PaperStore()
    paper = Paper(
        title="Test Paper",
        references=[
            Reference(
                title="A Novel Method",
                authors=["Alice Smith", "Bob Jones"],
                year=2023,
                venue="Journal of Testing",
                doi="10.1234/test.999",
            )
        ],
    )
    await store.add_paper(paper)
    res = await client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
    assert res.status_code == 200
    text = res.text
    assert "@article" in text
    assert "A Novel Method" in text
    assert "Smith, Alice" in text
    assert "Jones, Bob" in text
    assert "2023" in text
    assert "Journal of Testing" in text
    assert "10.1234/test.999" in text
    assert "Content-Disposition" in res.headers


@pytest.mark.asyncio
async def test_export_bibtex_inproceedings(client):
    """Conference paper detected via keyword in venue."""
    store = PaperStore()
    paper = Paper(
        title="Test",
        references=[
            Reference(
                title="Deep Learning",
                authors=["Kaiming He"],
                year=2016,
                venue="Proceedings of CVPR",
            )
        ],
    )
    await store.add_paper(paper)
    res = await client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
    assert res.status_code == 200
    assert "@inproceedings" in res.text
    assert "booktitle" in res.text


@pytest.mark.asyncio
async def test_export_bibtex_chinese_author(client):
    """Chinese author name degrades to anonymous in cite_key."""
    store = PaperStore()
    paper = Paper(
        title="Test",
        references=[
            Reference(title="Some Paper About AI", authors=["张伟"], year=2024)
        ],
    )
    await store.add_paper(paper)
    res = await client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
    assert res.status_code == 200
    assert "anonymous" in res.text.lower()


@pytest.mark.asyncio
async def test_export_bibtex_bad_format(client):
    """Non-bib format returns 400."""
    store = PaperStore()
    paper = Paper(title="Test", references=[])
    await store.add_paper(paper)
    res = await client.get(f"/api/papers/{paper.paper_id}/references/export?format=json")
    assert res.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd paper-reading-agent && python -m pytest tests/test_bibtex_export.py -v
```

Expected: FAIL — 404 on all tests (route doesn't exist)

- [ ] **Step 3: Add BibTeX export route and helpers to app.py**

In `paper-reading-agent/backend/app.py`, after the existing `_export_markdown` function (around line 393), add:

```python
# ---- BibTeX Export ----

@app.get("/api/papers/{paper_id}/references/export")
async def export_references(paper_id: str, format: str = Query(default="bib", pattern="^(bib)$")):
    """Export paper references as BibTeX (.bib) file."""
    if format != "bib":
        return JSONResponse({"error": "Only bib format is supported"}, status_code=400)

    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper:
        return JSONResponse({"error": "Paper not found"}, status_code=404)

    if not paper.references:
        bib_content = f"% No references found for {paper.title or 'this paper'}"
    else:
        bib_content = _format_bibtex(paper.references)

    title_slug = _slugify(paper.title or "references")
    filename = f"{title_slug}-references.bib"
    return Response(
        content=bib_content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _entry_type(venue: str) -> str:
    """Determine BibTeX entry type from venue name using keyword matching."""
    conference_keywords = [
        "Conference", "Proceedings", "Workshop", "Symposium",
        "CVPR", "ICML", "NeurIPS", "ACL", "EMNLP", "NAACL",
        "ICCV", "ECCV", "ICLR", "AAAI", "IJCAI", "SIGGRAPH",
    ]
    if any(kw.lower() in (venue or "").lower() for kw in conference_keywords):
        return "inproceedings"
    return "article"


def _cite_key(authors: list[str], year: int | None, title: str) -> str:
    """Generate BibTeX cite key: FirstAuthorSurnameYearTitleWords."""
    surname = ""
    if authors:
        first_author = authors[0].strip()
        parts = first_author.split()
        surname = parts[-1] if parts else first_author
    surname = re.sub(r'[^a-zA-Z0-9]', '', surname).lower()
    if not surname:
        surname = "anonymous"
    title_words = re.findall(r'[a-zA-Z]+', title.lower())
    title_part = "".join(title_words[:3])
    year_str = str(year) if year else "????"
    return f"{surname}{year_str}{title_part}"


def _format_authors(authors: list[str]) -> str:
    """Format authors as 'LastName, FirstName' joined with ' and '."""
    formatted = []
    for a in authors:
        parts = a.strip().split()
        if len(parts) >= 2:
            formatted.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
        else:
            formatted.append(a)
    return " and ".join(formatted)


def _format_bibtex(references: list) -> str:
    """Format a list of Reference objects as BibTeX string."""
    entries = []
    for ref in references:
        entry_type = _entry_type(ref.venue or "")
        key = _cite_key(ref.authors, ref.year, ref.title)

        lines = [f"@{entry_type}{{{key},"]
        lines.append(f"  title = {{{ref.title}}},")
        if ref.authors:
            lines.append(f"  author = {{{_format_authors(ref.authors)}}},")
        if ref.year:
            lines.append(f"  year = {{{ref.year}}},")
        if ref.venue:
            venue_field = "booktitle" if entry_type == "inproceedings" else "journal"
            lines.append(f"  {venue_field} = {{{ref.venue}}},")
        if ref.doi:
            lines.append(f"  doi = {{{ref.doi}}},")
        if ref.url:
            lines.append(f"  url = {{{ref.url}}},")
        # Remove trailing comma from last field line
        lines[-1] = lines[-1].rstrip(",")
        lines.append("}")
        entries.append("\n".join(lines))

    return "\n\n".join(entries) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd paper-reading-agent && python -m pytest tests/test_bibtex_export.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/app.py paper-reading-agent/tests/test_bibtex_export.py
git commit -m "feat(phase4a): add BibTeX export API endpoint for paper references"
```

---

### Task 4: Frontend — BibTeX export button

**Files:**
- Modify: `paper-reading-agent/frontend/src/api/client.ts`
- Modify: `paper-reading-agent/frontend/src/components/ChatPanel/ChatPanel.tsx`

**Interfaces:**
- Consumes: `GET /api/papers/{paper_id}/references/export?format=bib`
- Produces: `exportReferences()` function in client.ts; BibTeX option in ChatPanel export dropdown

- [ ] **Step 1: Add exportReferences() to API client**

In `paper-reading-agent/frontend/src/api/client.ts`, add after the existing `putPreferences` function:

```typescript
function slugify(text: string, maxLen: number = 50): string {
  return text
    .replace(/[^\w一-鿿-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, maxLen)
}

export function getReferencesExportUrl(paperId: string): string {
  return `${BASE}/papers/${encodeURIComponent(paperId)}/references/export?format=bib`
}

export async function exportReferences(paperId: string, paperTitle: string): Promise<void> {
  const res = await fetch(getReferencesExportUrl(paperId))
  if (!res.ok) return
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const slug = slugify(paperTitle || 'references')
  const date = new Date().toISOString().slice(0, 10)
  a.download = `${slug}-references-${date}.bib`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 2: Add BibTeX option to ChatPanel export dropdown**

In `paper-reading-agent/frontend/src/components/ChatPanel/ChatPanel.tsx`:

Add import at top (after existing imports):

```typescript
import { exportReferences } from '@/api/client'
```

Replace the export buttons section (the `showExport` block):

```tsx
        <div className={styles.exportGroup}>
          {showExport && (
            <>
              <button
                className={styles.exportBtn}
                onClick={() => handleExport('md')}
                data-testid="export-btn"
                title="Export as Markdown"
              >
                ⬇ .md
              </button>
              <button
                className={styles.exportBtn}
                onClick={() => handleExport('json')}
                title="Export as JSON"
              >
                .json
              </button>
            </>
          )}
          {paper && (
            <button
              className={styles.exportBtn}
              onClick={() => exportReferences(paper.paper_id, paper.title)}
              data-testid="export-bibtex-btn"
              title="Export all references from this paper in BibTeX format"
            >
              .bib
            </button>
          )}
        </div>
```

- [ ] **Step 3: Run frontend tests**

```bash
cd paper-reading-agent/frontend && npx vitest run
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add paper-reading-agent/frontend/src/api/client.ts paper-reading-agent/frontend/src/components/ChatPanel/ChatPanel.tsx
git commit -m "feat(phase4a): add BibTeX export button to ChatPanel dropdown"
```

---

### Task 5: Reranker ABC — add name and model_name properties

**Files:**
- Modify: `paper-reading-agent/backend/tools/reranker.py`
- Modify: `paper-reading-agent/tests/test_reranker.py`

**Interfaces:**
- Consumes: (none — isolated change to Reranker interface)
- Produces: `Reranker.name` (abstract property), `Reranker.model_name` (concrete property, default `None`); `FlashRankReranker._model_name` stores model name

- [ ] **Step 1: Write failing tests**

In `paper-reading-agent/tests/test_reranker.py`, add:

```python
def test_flashrank_reranker_name():
    from backend.tools.reranker import FlashRankReranker
    r = FlashRankReranker(model="ms-marco-MiniLM-L-12-v2")
    assert r.name == "flashrank"


def test_flashrank_reranker_model_name():
    from backend.tools.reranker import FlashRankReranker
    r = FlashRankReranker(model="ms-marco-MiniLM-L-12-v2")
    assert r.model_name == "ms-marco-MiniLM-L-12-v2"


def test_bm25_reranker_name():
    from backend.tools.reranker import BM25FallbackReranker
    r = BM25FallbackReranker()
    assert r.name == "bm25"


def test_bm25_reranker_model_name_is_none():
    from backend.tools.reranker import BM25FallbackReranker
    r = BM25FallbackReranker()
    assert r.model_name is None


def test_reranker_name_is_abstract():
    """Cannot instantiate Reranker without implementing name."""
    from backend.tools.reranker import Reranker
    with pytest.raises(TypeError):
        class Incomplete(Reranker):
            def rerank(self, query, passages):
                return passages
        Incomplete()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd paper-reading-agent && python -m pytest tests/test_reranker.py::test_flashrank_reranker_name tests/test_reranker.py::test_flashrank_reranker_model_name tests/test_reranker.py::test_bm25_reranker_name tests/test_reranker.py::test_bm25_reranker_model_name_is_none tests/test_reranker.py::test_reranker_name_is_abstract -v
```

Expected: FAIL — `AttributeError: 'FlashRankReranker' object has no attribute 'name'`

- [ ] **Step 3: Add properties to Reranker classes**

In `paper-reading-agent/backend/tools/reranker.py`:

Update `Reranker` ABC:

```python
class Reranker(ABC):
    """Abstract reranker interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier: 'flashrank' | 'bm25'."""
        ...

    @property
    def model_name(self) -> str | None:
        """Model name if applicable, None for non-ML rerankers."""
        return None

    @abstractmethod
    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Re-rank passages by relevance to query. Returns passages sorted best-first."""
```

Update `BM25FallbackReranker` — add `name`:

```python
class BM25FallbackReranker(Reranker):
    """Zero-dependency fallback: sort by existing BM25 score descending."""

    @property
    def name(self) -> str:
        return "bm25"

    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return sorted(
            passages,
            key=lambda c: c.scores.get("bm25", 0),
            reverse=True,
        )
```

Update `FlashRankReranker` — change `self.model_name` to `self._model_name`, add `name` and `model_name` properties:

```python
class FlashRankReranker(Reranker):
    """Cross-encoder reranker using the flashrank library.

    Model is downloaded lazily on first ``rerank()`` call so service startup
    is never blocked. If loading fails the factory function degrades to BM25.
    """

    def __init__(self, model: str = "ms-marco-MiniLM-L-12-v2"):
        self._model_name = model
        self._ranker = None  # lazy -- loaded on first rerank()

    @property
    def name(self) -> str:
        return "flashrank"

    @property
    def model_name(self) -> str | None:
        return self._model_name

    def _ensure_loaded(self) -> None:
        if self._ranker is None:
            try:
                from flashrank import Ranker
                self._ranker = Ranker(model_name=self._model_name)
            except Exception as e:
                raise RerankerLoadError(
                    f"FlashRank model '{self._model_name}' failed to load: {e}"
                ) from e

    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not passages:
            return []
        rank_input = [{"id": p.chunk_id, "text": p.text} for p in passages]
        try:
            self._ensure_loaded()
            scored = self._ranker.rerank(query, rank_input)
        except Exception:
            logger.warning("FlashRank rerank failed, returning original order")
            return passages
        score_map: dict[str, float] = {}
        for item in scored:
            score_map[item["id"]] = float(item.get("score", 0))
        for p in passages:
            p.scores["rerank"] = score_map.get(p.chunk_id, 0)
        passages.sort(key=lambda c: c.scores.get("rerank", 0), reverse=True)
        return passages
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd paper-reading-agent && python -m pytest tests/test_reranker.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/tools/reranker.py paper-reading-agent/tests/test_reranker.py
git commit -m "feat(phase4a): add name and model_name properties to Reranker ABC and subclasses"
```

---

### Task 6: Backend — retrieve_node trace + done SSE payload

**Files:**
- Modify: `paper-reading-agent/backend/agents/qa.py` (retrieve_node trace)
- Modify: `paper-reading-agent/backend/agents/supervisor.py` (_build_done_payload)
- Modify: `paper-reading-agent/tests/test_sse_protocol.py` (SSE done payload test)

**Interfaces:**
- Consumes: `Reranker.name`, `Reranker.model_name` (from Task 5)
- Produces: trace string; done SSE event gains `reranker_used` and `reranker_summary` fields

- [ ] **Step 1: Update retrieve_node in qa.py**

In `paper-reading-agent/backend/agents/qa.py`, replace the `retrieve_node` function:

```python
async def retrieve_node(state: AgentState) -> AgentState:
    """Hybrid RAG retrieval using cached retriever from reader."""
    if state.retriever is None:
        logger.warning("No retriever in state, cannot retrieve")
        state.retrieved_chunks = []
        state.trace.append("retrieve(empty)")
        return state

    chunks = state.retriever.retrieve(state.user_query)
    state.retrieved_chunks = chunks

    # Build reranker trace entry
    reranker = state.retriever.reranker
    total_chunks = len(state.retriever.chunks)
    trace_entry = f"{total_chunks} chunks -> {reranker.name} rerank"
    if reranker.model_name:
        trace_entry += f" ({reranker.model_name})"
    trace_entry += f" -> top {len(chunks)}"
    state.trace.append(trace_entry)

    return state
```

Note: Uses `->` not `→` for trace strings to avoid confusion with TracePanel's ` → ` separator.

- [ ] **Step 2: Update _build_done_payload in supervisor.py**

In `paper-reading-agent/backend/agents/supervisor.py`, in `_build_done_payload`, add reranker fields. Replace the payload dict construction:

```python
    qs = state.quality_score
    reranker = state.retriever.reranker if state.retriever else None
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
        "followup_questions": state.followup_questions,
        "reranker_used": reranker.name if reranker else "unknown",
        "reranker_summary": {
            "input_chunks": len(state.retriever.chunks) if state.retriever else 0,
            "output_chunks": len(state.retrieved_chunks),
            "model": reranker.model_name if reranker and reranker.model_name else None,
        },
    }
```

- [ ] **Step 3: Update SSE protocol test**

In `paper-reading-agent/tests/test_sse_protocol.py`, add:

```python
import json


def test_done_payload_includes_reranker_fields():
    """Done SSE payload includes reranker_used and reranker_summary."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState, RetrievedChunk
    from backend.tools.reranker import BM25FallbackReranker

    class MockRetriever:
        chunks = [{"chunk_id": "1"}] * 20
        reranker = BM25FallbackReranker()

    state = AgentState(
        answer="test answer",
        session_id="sess-1",
        retrieved_chunks=[RetrievedChunk(chunk_id="1", text="test", page=1) for _ in range(5)],
        trace=[],
    )
    state.retriever = MockRetriever()

    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert payload["reranker_used"] == "bm25"
    assert payload["reranker_summary"]["input_chunks"] == 20
    assert payload["reranker_summary"]["output_chunks"] == 5
    assert payload["reranker_summary"]["model"] is None


def test_done_payload_handles_none_retriever():
    """Done SSE payload degrades gracefully when retriever is None."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState

    state = AgentState(answer="test", session_id="sess-1", retrieved_chunks=[], trace=[])
    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert payload["reranker_used"] == "unknown"
    assert payload["reranker_summary"]["input_chunks"] == 0
    assert payload["reranker_summary"]["output_chunks"] == 0
    assert payload["reranker_summary"]["model"] is None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd paper-reading-agent && python -m pytest tests/test_sse_protocol.py tests/test_reranker.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/agents/qa.py paper-reading-agent/backend/agents/supervisor.py paper-reading-agent/tests/test_sse_protocol.py
git commit -m "feat(phase4a): add reranker trace to retrieve_node and reranker fields to done SSE payload"
```

---

### Task 7: Frontend — types update

**Files:**
- Modify: `paper-reading-agent/frontend/src/types/index.ts`

**Interfaces:**
- Consumes: `DoneEvent` from SSE with new `reranker_used` and `reranker_summary` fields
- Produces: TypeScript types extended; TracePanel renders trace as-is (no code change needed)

- [ ] **Step 1: Update DoneEvent type**

In `paper-reading-agent/frontend/src/types/index.ts`, add reranker types and update `DoneEvent`:

```typescript
// ---- Reranker ----
export interface RerankerSummary {
  input_chunks: number
  output_chunks: number
  model: string | null
}

export interface DoneEvent {
  event: 'done'
  answer: string
  session_id?: string
  quality_score: QualityScore
  evidence_list: Evidence[]
  trace: string[]
  followup_questions: string[]
  reranker_used: string
  reranker_summary: RerankerSummary
}
```

- [ ] **Step 2: Run frontend tests to confirm no breakage**

```bash
cd paper-reading-agent/frontend && npx vitest run
```

Expected: ALL PASS (extra fields in DoneEvent don't break existing SSE event parsing — JSON.parse ignores unknown fields)

- [ ] **Step 3: Commit**

```bash
git add paper-reading-agent/frontend/src/types/index.ts
git commit -m "feat(phase4a): add reranker_used and reranker_summary to DoneEvent TypeScript type"
```

---

## Verification

After all 7 tasks, run the full test suite:

```bash
# Backend
cd paper-reading-agent && python -m pytest tests/ -v

# Frontend
cd paper-reading-agent/frontend && npx vitest run
```

Expected: ALL PASS (97+ tests including new ones)
