# Phase 5.5: 论文库搜索筛选排序 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为论文库增加关键词搜索、来源筛选和排序功能——纯前端过滤 + 后端扩展返回字段。

**Architecture:** 后端 `list_papers()` 改用 `SELECT *` 返回完整字段 + `_snippet()` 截断摘要；前端 `useMemo` 即时过滤/排序，不增加 API 请求。搜索/筛选/排序为 LibraryPanel 局部状态。

**Tech Stack:** Python 3.11+, FastAPI, aiosqlite, TypeScript 5.5+, React 18, zustand

## Global Constraints

- 无新依赖、无新端点、无 DB migration
- `_snippet(text, max_len=200)` 在空格处截断，不切单词
- `PaperListResponse` 新字段追加，不破坏老消费者
- 搜索/筛选/排序为 LibraryPanel 局部 useState，不进入 compareStore
- 代码中留防抖预留注释：`// 预留：如果论文库 >200 条，考虑增加 100ms 防抖`

---

### Task 1: 后端 — list_papers 扩展 + _snippet + API 响应

**Files:**
- Modify: `backend/storage/paper_store.py:85-99`
- Modify: `backend/app.py:199-203`
- Test: `tests/test_storage.py`, `tests/test_papers_api.py`

**Interfaces:**
- Consumes: `_row_to_paper(row) -> Paper` (existing, Phase 5)
- Produces: `_snippet(text: str, max_len: int = 200) -> str`
- Produces: `GET /api/papers` returns `[{paper_id, title, authors, abstract_snippet, import_source, arxiv_id, parsed_at}]`

- [ ] **Step 1: 修改 paper_store.list_papers()**

READ `backend/storage/paper_store.py` first. Replace the `list_papers` method:

```python
    async def list_papers(self) -> list[Paper]:
        conn = await db.get_db()
        try:
            papers = []
            async with conn.execute(
                "SELECT * FROM papers ORDER BY parsed_at DESC"
            ) as cursor:
                async for row in cursor:
                    papers.append(_row_to_paper(row))
            return papers
        finally:
            await conn.close()
```

- [ ] **Step 2: 添加 _snippet 辅助函数 + 修改 list_papers 端点**

READ `backend/app.py` first. Add `_snippet` function before the `list_papers` endpoint (around line 197), and rewrite the endpoint:

```python
def _snippet(text: str, max_len: int = 200) -> str:
    """Truncate text at a word boundary near max_len, append ellipsis if cut."""
    if len(text) <= max_len:
        return text
    cutoff = text.rfind(' ', 0, max_len)
    return text[:cutoff] + '...' if cutoff > 0 else text[:max_len] + '...'


@app.get("/api/papers")
async def list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    return [{
        "paper_id": p.paper_id,
        "title": p.title,
        "authors": p.authors,
        "abstract_snippet": _snippet(p.abstract, 200) if p.abstract else "",
        "import_source": p.import_source,
        "arxiv_id": p.arxiv_id,
        "parsed_at": p.parsed_at,
    } for p in papers]
```

- [ ] **Step 3: 编写后端测试**

In `tests/test_storage.py`, add:

```python
@pytest.mark.asyncio
async def test_list_papers_returns_full_fields():
    from backend.storage.paper_store import PaperStore
    from backend.models.paper import Paper
    store = PaperStore()
    paper = Paper(
        title="Searchable Paper",
        authors=["Test Author"],
        abstract="This paper discusses testing.",
        import_source="bib_import",
        arxiv_id="2401.99999",
    )
    await store.add_paper(paper)

    papers = await store.list_papers()
    found = next((p for p in papers if p.paper_id == paper.paper_id), None)
    assert found is not None
    assert found.import_source == "bib_import"
    assert found.arxiv_id == "2401.99999"
    assert found.authors == ["Test Author"]
```

Run: `pytest tests/test_storage.py::test_list_papers_returns_full_fields -v`
Expected: PASS

In `tests/test_papers_api.py` (new file):

```python
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app, _snippet


def test_snippet_no_truncation():
    assert _snippet("Hello world", 200) == "Hello world"


def test_snippet_truncates_at_word_boundary():
    result = _snippet("Hello world this is a test of the emergency broadcast system", 30)
    # Should cut at a space before position 30
    assert len(result) <= 33  # original text + "..."
    assert result.endswith("...")


def test_snippet_short_max_len():
    result = _snippet("Supercalifragilisticexpialidocious", 10)
    assert result.endswith("...")


@pytest.mark.asyncio
async def test_list_papers_returns_new_fields():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/papers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            paper = data[0]
            assert "authors" in paper
            assert "abstract_snippet" in paper
            assert "import_source" in paper
            assert "arxiv_id" in paper


@pytest.mark.asyncio
async def test_list_papers_import_source_values():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/papers")
        data = resp.json()
        for paper in data:
            assert paper["import_source"] in ("upload", "bib_import", "external_save")
```

Run: `pytest tests/test_papers_api.py -v`
Expected: 5 PASS

- [ ] **Step 4: 运行全部后端测试确保无回归**

Run: `cd "D:/桌面/agent - 2/paper-reading-agent" && python -m pytest tests/ -v --tb=short`
Expected: all PASS (~131 tests)

- [ ] **Step 5: Commit**

```bash
cd "D:/桌面/agent - 2" && git add paper-reading-agent/backend/storage/paper_store.py paper-reading-agent/backend/app.py paper-reading-agent/tests/test_storage.py paper-reading-agent/tests/test_papers_api.py && git commit -m "feat(phase5.5): extend list_papers with full fields, add _snippet, update API response"
```

---

### Task 2: 前端 — PaperListResponse 类型扩展

**Files:**
- Modify: `frontend/src/types/index.ts`
- Test: `frontend/tests/types.test.ts`

**Interfaces:**
- Consumes: 后端 `GET /api/papers` 新响应格式
- Produces: `PaperListResponse` 含 `authors`, `abstract_snippet`, `import_source`, `arxiv_id`

- [ ] **Step 1: 扩展 PaperListResponse 类型**

READ `frontend/src/types/index.ts` first. Replace the existing `PaperListResponse`:

```typescript
export interface PaperListResponse {
  paper_id: string
  title: string
  authors: string[]              // New
  abstract_snippet: string       // New
  import_source: string          // New: "upload" | "bib_import" | "external_save"
  arxiv_id: string | null        // New
  parsed_at: string | null
}
```

- [ ] **Step 2: 编写类型测试**

READ `frontend/tests/types.test.ts` first. Append:

```typescript
  it('PaperListResponse has new Phase 5.5 fields', () => {
    const p = {
      paper_id: '1',
      title: 'Test',
      authors: ['Author One'],
      abstract_snippet: 'This is a test...',
      import_source: 'upload',
      arxiv_id: null,
      parsed_at: '2024-01-01',
    }
    expect(p.authors).toEqual(['Author One'])
    expect(p.import_source).toBe('upload')
    expect(p.abstract_snippet).toBe('This is a test...')
  })
```

Run: `cd "D:/桌面/agent - 2/paper-reading-agent/frontend" && npx vitest run tests/types.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 3: Commit**

```bash
cd "D:/桌面/agent - 2" && git add paper-reading-agent/frontend/src/types/index.ts paper-reading-agent/frontend/tests/types.test.ts && git commit -m "feat(phase5.5): extend PaperListResponse with authors, abstract_snippet, import_source, arxiv_id"
```

---

### Task 3: 前端 — LibraryPanel 搜索/筛选/排序 + CSS

**Files:**
- Modify: `frontend/src/components/Layout/LibraryPanel.tsx`
- Modify: `frontend/src/components/Layout/Layout.module.css`
- Test: `frontend/tests/frontend/LibraryPanel.test.tsx`

**Interfaces:**
- Consumes: `PaperListResponse` (Task 2), `useCompareStore`, `listPapers()`, `importBibTeX()`
- Produces: 搜索框、来源下拉、排序下拉、useMemo 过滤、防抖预留注释

- [ ] **Step 1: READ existing LibraryPanel.tsx and Layout.module.css**

- [ ] **Step 2: 重写 LibraryPanel.tsx**

Replace the file content:

```tsx
import { useState, useEffect, useRef, useMemo } from 'react'
import { listPapers, importBibTeX } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import { useCompareStore } from '@/store/compareStore'
import type { PaperListResponse } from '@/types'
import styles from './Layout.module.css'

const SOURCE_LABELS: Record<string, string> = {
  all: 'All',
  upload: 'Uploaded',
  bib_import: 'BibTeX Import',
  external_save: 'External Save',
}

export default function LibraryPanel() {
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const setPaper = useAppStore((s) => s.setPaper)
  const { isCompareMode, selectedPaperIds, toggleCompareMode, toggleSelection, clearSelection } = useCompareStore()
  const [importStatus, setImportStatus] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Phase 5.5: search/filter/sort — local state only
  // 预留：如果论文库 >200 条，考虑增加 100ms 防抖
  const [query, setQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [sort, setSort] = useState<'date' | 'title'>('date')

  useEffect(() => {
    listPapers().then(setPapers).catch(() => setPapers([]))
  }, [])

  const refreshPapers = () => {
    listPapers().then(setPapers).catch(() => {})
  }

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
      refreshPapers()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Import failed'
      setImportStatus(`❌ ${msg}`)
    }

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

  // Phase 5.5: local filter + sort
  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim()
    return papers
      .filter(p => {
        if (q) {
          const inTitle = (p.title || '').toLowerCase().includes(q)
          const inAuthor = (p.authors || []).some(a => a.toLowerCase().includes(q))
          const inAbstract = (p.abstract_snippet || '').toLowerCase().includes(q)
          if (!inTitle && !inAuthor && !inAbstract) return false
        }
        if (sourceFilter !== 'all' && p.import_source !== sourceFilter) return false
        return true
      })
      .sort((a, b) => {
        if (sort === 'title') return (a.title || '').localeCompare(b.title || '')
        return new Date(b.parsed_at || 0).getTime() - new Date(a.parsed_at || 0).getTime()
      })
  }, [papers, query, sourceFilter, sort])

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

      {/* Phase 5.5: search bar */}
      <div className={styles.searchBar}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder="🔍 Search papers..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {/* Phase 5.5: filter + sort row */}
      <div className={styles.filterRow}>
        <label className={styles.filterLabel}>
          Source:
          <select
            className={styles.filterSelect}
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            {Object.entries(SOURCE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className={styles.filterLabel}>
          Sort:
          <select
            className={styles.filterSelect}
            value={sort}
            onChange={(e) => setSort(e.target.value as 'date' | 'title')}
          >
            <option value="date">Date (newest)</option>
            <option value="title">Title (A-Z)</option>
          </select>
        </label>
      </div>

      {isCompareMode && (
        <p className={styles.compareHint}>Select 2-5 papers to compare</p>
      )}
      {importStatus && (
        <p className={styles.importStatus}>{importStatus}</p>
      )}

      <p className={styles.paperCount}>
        {filtered.length} paper{filtered.length !== 1 ? 's' : ''}
        {query && ` matching "${query}"`}
      </p>

      {papers.length === 0 && <p className={styles.empty}>No papers uploaded</p>}
      {papers.length > 0 && filtered.length === 0 && (
        <p className={styles.empty}>No papers match your search</p>
      )}
      <ul>
        {filtered.map((p) => {
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
              <span className={styles.paperTitle}>{p.title}</span>
              {p.authors && p.authors.length > 0 && (
                <span className={styles.paperAuthors}>{p.authors.slice(0, 2).join(', ')}</span>
              )}
              {p.import_source && p.import_source !== 'upload' && (
                <span className={styles.sourceTag}>{SOURCE_LABELS[p.import_source] || p.import_source}</span>
              )}
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

- [ ] **Step 3: 追加 CSS 到 Layout.module.css**

READ the file first. Append:

```css
.searchBar {
  margin-bottom: 6px;
}

.searchInput {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  box-sizing: border-box;
}

.filterRow {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.filterLabel {
  font-size: 12px;
  color: #666;
  display: flex;
  align-items: center;
  gap: 4px;
}

.filterSelect {
  font-size: 12px;
  padding: 2px 4px;
  border: 1px solid #ddd;
  border-radius: 3px;
  background: white;
}

.paperCount {
  font-size: 11px;
  color: #999;
  margin: 4px 0 8px;
}

.paperTitle {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.paperAuthors {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
}

.sourceTag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #f0f0f0;
  color: #888;
  flex-shrink: 0;
}
```

- [ ] **Step 4: 运行前端测试**

Run: `cd "D:/桌面/agent - 2/paper-reading-agent/frontend" && npx vitest run`
Expected: all PASS (~54 tests)

- [ ] **Step 5: Commit**

```bash
cd "D:/桌面/agent - 2" && git add paper-reading-agent/frontend/src/components/Layout/LibraryPanel.tsx paper-reading-agent/frontend/src/components/Layout/Layout.module.css && git commit -m "feat(phase5.5): add search bar, source filter, sort dropdown to LibraryPanel"
```

---

### Task 4: 全量测试验证

**Files:** 无代码修改

- [ ] **Step 1: 运行全部后端测试**

```bash
cd "D:/桌面/agent - 2/paper-reading-agent" && python -m pytest tests/ -v --tb=short
```

Expected: ~131 PASS, 0 FAIL

- [ ] **Step 2: 运行全部前端测试**

```bash
cd "D:/桌面/agent - 2/paper-reading-agent/frontend" && npx vitest run
```

Expected: ~54 PASS, 0 FAIL

- [ ] **Step 3: Commit**

```bash
cd "D:/桌面/agent - 2" && git add . && git commit -m "test(phase5.5): full test suite verification — ~185 tests passing"
```
