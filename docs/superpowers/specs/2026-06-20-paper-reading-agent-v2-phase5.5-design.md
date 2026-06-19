# 论文阅读 Agent V2 — Phase 5.5 设计文档

> 日期：2026-06-20 | 状态：已确认  
> 父文档：[V2 整体设计](2026-06-17-paper-reading-agent-v2-design.md)  
> Phase 5 设计：[Phase 5 设计文档](2026-06-19-paper-reading-agent-v2-phase5-design.md)

---

## 一、概述

Phase 5.5 为论文库增加搜索、筛选和排序能力。纯前端过滤 + 后端扩展 `list_papers` 返回字段，无新依赖、无新端点、无 DB migration。

| 功能 | 实现方式 |
|------|----------|
| **关键词搜索** | 前端 useMemo 即时过滤：标题/作者/摘要 snippet |
| **来源筛选** | 下拉选择：All / Uploaded / BibTeX Import / External Save |
| **排序** | 下拉选择：Date (newest) / Title (A-Z) |

**架构决策：** 混合方案 — 后端一次性返回全量论文含完整字段，前端 useMemo 即时过滤/排序。论文库规模（数十到数百篇）完全够用。预留 >200 条时的轻量防抖提示。

---

## 二、后端变更

### 2.1 `paper_store.list_papers()` 扩展

改为 `SELECT *` + `_row_to_paper`（Phase 5 已提取），返回完整 `Paper` 对象：

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

### 2.2 `_snippet()` 辅助函数

```python
def _snippet(text: str, max_len: int = 200) -> str:
    """截断文本，在 max_len 前最后一个空格处切断，避免单词截半。"""
    if len(text) <= max_len:
        return text
    cutoff = text.rfind(' ', 0, max_len)
    return text[:cutoff] + '...' if cutoff > 0 else text[:max_len] + '...'
```

### 2.3 `GET /api/papers` 响应扩展

```python
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

新增字段：`authors`、`abstract_snippet`、`import_source`、`arxiv_id`。

---

## 三、前端变更

### 3.1 类型扩展

```typescript
export interface PaperListResponse {
  paper_id: string
  title: string
  authors: string[]           // 新增
  abstract_snippet: string    // 新增
  import_source: string       // 新增
  arxiv_id: string | null     // 新增
  parsed_at: string | null
}
```

### 3.2 LibraryPanel 搜索栏

搜索/筛选/排序为 LibraryPanel 局部状态（不污染 compareStore）：

```typescript
// 预留：如果论文库 >200 条，考虑增加 100ms 防抖
const [query, setQuery] = useState('')
const [sourceFilter, setSourceFilter] = useState('all')
const [sort, setSort] = useState<'date' | 'title'>('date')
```

布局：

```
┌──────────────────────────────────────┐
│ 📚 Paper Library    [Compare][Import]│
│ ┌──────────────────────────────────┐ │
│ │ 🔍 Search papers...              │ │
│ └──────────────────────────────────┘ │
│ Source: [All ▾]  Sort: [Date ▾]      │
│ ──────────────────────────────────── │
│ <count> papers                        │
│ ☐ Attention Is All You Need          │
│ ...                                  │
└──────────────────────────────────────┘
```

**过滤逻辑（useMemo）：**

```typescript
const filtered = useMemo(() => {
  const q = query.toLowerCase()
  return papers
    .filter(p => {
      if (q) {
        const inTitle = p.title.toLowerCase().includes(q)
        const inAuthor = (p.authors || []).some(a => a.toLowerCase().includes(q))
        const inAbstract = (p.abstract_snippet || '').toLowerCase().includes(q)
        if (!inTitle && !inAuthor && !inAbstract) return false
      }
      if (sourceFilter !== 'all' && p.import_source !== sourceFilter) return false
      return true
    })
    .sort((a, b) => {
      if (sort === 'date') return new Date(b.parsed_at || 0).getTime() - new Date(a.parsed_at || 0).getTime()
      return (a.title || '').localeCompare(b.title || '')
    })
}, [papers, query, sourceFilter, sort])
```

**来源映射：**

```typescript
const SOURCE_LABELS: Record<string, string> = {
  all: 'All',
  upload: 'Uploaded',
  bib_import: 'BibTeX Import',
  external_save: 'External Save',
}
```

### 3.3 CSS 追加

搜索栏相关样式（`.searchBar`、`.filterRow`、`.filterSelect`、`.paperCount`）追加到 `Layout.module.css`。

---

## 四、测试策略

| 文件 | 测试 | 数量 |
|------|------|------|
| `tests/test_storage.py` | `list_papers()` 返回完整字段含 import_source/arxiv_id | 1 |
| `tests/test_papers_api.py` | `GET /api/papers` 响应包含 authors/abstract_snippet/import_source/arxiv_id；_snippet 截断与边界 | 4 |
| `frontend/tests/LibraryPanel.test.tsx` | 搜索过滤、来源筛选、排序切换 | 3 |

预计 ~8 新增。累计：178 + 8 = **~186 测试**。

---

## 五、文件变更清单

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/storage/paper_store.py` | `list_papers()` 改用 `SELECT *` + `_row_to_paper` |
| `backend/app.py` | `_snippet()` 辅助函数；`GET /api/papers` 响应扩展字段 |
| `frontend/src/types/index.ts` | `PaperListResponse` 增加 authors/abstract_snippet/import_source/arxiv_id |
| `frontend/src/components/Layout/LibraryPanel.tsx` | 搜索框 + 来源下拉 + 排序下拉 + useMemo 过滤 |
| `frontend/src/components/Layout/Layout.module.css` | 搜索栏样式 |
| `tests/test_storage.py` | list_papers 完整字段测试 |
| `tests/test_papers_api.py` | API 响应新字段测试 + _snippet 测试 |
| `frontend/tests/LibraryPanel.test.tsx` | 搜索/筛选/排序测试 |

### 不修改

- `PaperListResponse` 老消费者（`App.tsx`、`CompareSelectModal`）— 新字段追加，不破坏兼容
- `compareStore.ts` — 搜索是 LibraryPanel 局部状态
- 其他所有文件

---

## 六、错误处理

| 场景 | 策略 |
|------|------|
| 搜索无匹配 | 显示 "No papers match your search" 空状态 |
| 论文库为空 | 保持现有空状态 "No papers uploaded" |
| `parsed_at` 为 null（旧数据） | 排序时 fallback 到 epoch 0 |
| `import_source` 为未知值 | 下拉中显示原始值 |

---

## 七、预留扩展点

- **防抖**：代码中留注释，论文库 >200 条时增加 100ms 防抖
- **分页**：当前全量返回，论文库 >1000 条时考虑 `?limit=&offset=` 服务端分页
- **高亮**：搜索结果中匹配关键词高亮（后续 Phase 可做）
