# 论文阅读 Agent V2 — Phase 4a 设计文档

> 日期：2026-06-19 | 状态：已确认  
> 父文档：[V2 整体设计](2026-06-17-paper-reading-agent-v2-design.md)  
> Phase 3 设计：[Phase 3 设计文档](2026-06-18-paper-reading-agent-v2-phase3-design.md)

---

## 一、概述

Phase 4a 包含两个独立轻量功能，先轻后重策略中的"轻"——快速交付，零耦合。

| 功能 | 层级 | 核心改动 |
|------|------|----------|
| **BibTeX 批量导出** | 后端 + 前端 | 新增 API `/api/papers/{paper_id}/references/export` + ChatPanel 下拉增加 BibTeX 选项 |
| **FlashRank 重排序可视化** | 后端 + 前端 | Reranker 增加 name/model_name 属性 + SSE done 事件扩展 + TracePanel 渲染 |

---

## 二、BibTeX 批量导出

### 2.1 API

```
GET /api/papers/{paper_id}/references/export?format=bib
```

- Paper 不存在返回 404
- 无参考文献返回空 `.bib` 文件，内容为 `% No references found for <paper title>`
- `Content-Disposition: attachment; filename="{slug}-references.bib"`

### 2.2 BibTeX 格式规则

**entry_type 判断：**

```python
def _entry_type(venue: str) -> str:
    conference_keywords = [
        "Conference", "Proceedings", "Workshop", "Symposium",
        "CVPR", "ICML", "NeurIPS", "ACL", "EMNLP", "NAACL",
        "ICCV", "ECCV", "ICLR", "AAAI", "IJCAI", "SIGGRAPH",
    ]
    if any(kw.lower() in venue.lower() for kw in conference_keywords):
        return "inproceedings"
    return "article"
```

**cite_key 生成：**

```python
def _cite_key(authors: list[str], year: int | None, title: str) -> str:
    # 取第一作者姓氏（空格分隔取最后一段，处理中文→拼音）
    surname = ""
    if authors:
        first_author = authors[0].strip()
        parts = first_author.split()
        surname = parts[-1] if parts else first_author
    # 去除非字母数字字符，全小写
    surname = re.sub(r'[^a-zA-Z0-9]', '', surname).lower()
    # title 前 3 个有效词
    title_words = re.findall(r'[a-zA-Z]+', title.lower())
    title_part = "".join(title_words[:3])
    year_str = str(year) if year else "????"
    return f"{surname}{year_str}{title_part}"
```

- 中文作者：`"张伟"` → 现有 `authors` 列表存储的可能是拼音（`"Wei Zhang"`）或中文原文。如果是中文原文，`surname` 取最后一个字符的拼音不可靠，`re.sub` 后可能为空。此时降级为 `"anonymous"`。
- 此行为在文档中说明。

**字段映射：**

| Reference 字段 | BibTeX 字段 | article | inproceedings |
|----------------|-------------|---------|---------------|
| `title` | `title` | ✅ | ✅ |
| `authors` | `author` | ✅ | ✅ |
| `year` | `year` | ✅ | ✅ |
| `venue` | `journal` / `booktitle` | journal | booktitle |
| `doi` | `doi` | ✅ | ✅ |
| `url` | `url` | ✅ | ✅ |

**作者格式化：**

```python
def _format_authors(authors: list[str]) -> str:
    formatted = []
    for a in authors:
        parts = a.strip().split()
        if len(parts) >= 2:
            formatted.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
        else:
            formatted.append(a)
    return " and ".join(formatted)
```

### 2.3 输出示例

```bibtex
@inproceedings{he2016deepresidual,
  title = {Deep Residual Learning for Image Recognition},
  author = {He, Kaiming and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian},
  year = {2016},
  booktitle = {Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR)},
  doi = {10.1109/CVPR.2016.90}
}

@article{vaswani2017attention,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam and Parmar, Niki and Uszkoreit, Jakob and Jones, Llion and Gomez, Aidan N. and Kaiser, Lukasz and Polosukhin, Illia},
  year = {2017},
  journal = {Advances in Neural Information Processing Systems},
  url = {https://papers.nips.cc/paper/7181-attention-is-all-you-need}
}
```

### 2.4 前端入口

**ChatPanel.tsx 导出下拉增加 `BibTeX (.bib)` 选项：**
- 在现有 Markdown/JSON 导出下拉中增加分隔线和 BibTeX 选项
- label: `BibTeX (.bib)`，仅在 `paperId !== null` 时可用
- 点击调用 `GET /api/papers/{paperId}/references/export?format=bib`
- tooltip: `"Export all references from this paper in BibTeX format"`
- 对话未开始时也可导出（不依赖 `status === 'complete'`）

---

## 三、FlashRank 重排序可视化

### 3.1 Reranker 接口扩展

**`backend/tools/reranker.py` — Reranker ABC 增加两个属性：**

```python
class Reranker(ABC):
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
        ...
```

**子类实现：**

```python
class FlashRankReranker(Reranker):
    @property
    def name(self) -> str:
        return "flashrank"

    @property
    def model_name(self) -> str | None:
        return self._model_name  # __init__ 中设置

class BM25FallbackReranker(Reranker):
    @property
    def name(self) -> str:
        return "bm25"
```

### 3.2 retrieve_node 修改

**`backend/agents/qa.py` — `retrieve_node`：**

```python
async def retrieve_node(state: AgentState) -> AgentState:
    if state.retriever is None:
        logger.warning("No retriever in state, cannot retrieve")
        state.retrieved_chunks = []
        state.trace.append("retrieve(empty)")
        return state

    chunks = state.retriever.retrieve(state.user_query)
    state.retrieved_chunks = chunks

    # Build reranker trace entry
    reranker = state.retriever.reranker
    trace_entry = (
        f"{len(state.retriever.chunks)} chunks → "
        f"{reranker.name} rerank"
    )
    if reranker.model_name:
        trace_entry += f" ({reranker.model_name})"
    trace_entry += f" → top {len(chunks)}"
    state.trace.append(trace_entry)

    return state
```

注意：`len(state.retriever.chunks)` 是检索前的总 chunk 数（所有候选）。rerank 后实际返回的数量是 `retrieve()` 中 `merged[:top_k]` 的结果。

### 3.3 SSE done 事件扩展

在 `_build_done_payload()` 中增加：

```python
reranker = state.retriever.reranker if state.retriever else None
payload = {
    "event": "done",
    "answer": state.answer,
    "session_id": state.session_id,
    # ... 现有字段 ...
    "reranker_used": reranker.name if reranker else "unknown",
    "reranker_summary": {
        "input_chunks": len(state.retriever.chunks) if state.retriever else 0,
        "output_chunks": len(state.retrieved_chunks),
        "model": reranker.model_name if reranker and reranker.model_name else None,
    },
}
```

### 3.4 前端渲染

**类型定义 (`types/index.ts`)：**

```typescript
interface RerankerSummary {
  input_chunks: number;
  output_chunks: number;
  model: string | null;
}

// DoneEvent 扩展
interface DoneEvent {
  // ... 现有字段 ...
  reranker_used: string;          // "flashrank" | "bm25"
  reranker_summary: RerankerSummary;
}
```

**TracePanel 渲染：**

- trace 中以 StepIndicator 行渲染：`20 chunks → flashrank rerank (ms-marco-MiniLM-L-12-v2) → top 5`
- 只读展示，不展开分数细节

**Settings 面板：**
- Phase 3 已有 `reranker` 下拉选择（flashrank/bm25），确认同步
- 无额外改动

---

## 四、文件变更清单

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app.py` | 新增 `GET /api/papers/{paper_id}/references/export?format=bib` |
| `backend/tools/reranker.py` | Reranker ABC 增加 `name` + `model_name` 属性；子类实现 |
| `backend/agents/qa.py` | `retrieve_node` 追加结构化 reranker trace |
| `backend/agents/supervisor.py` | `_build_done_payload()` 增加 `reranker_used` + `reranker_summary` |
| `frontend/src/components/ChatPanel/ChatPanel.tsx` | 导出下拉增加 BibTeX (.bib) 选项 |
| `frontend/src/api/client.ts` | 新增 `exportReferences()` 方法 |
| `frontend/src/types/index.ts` | done 事件类型增加 reranker 字段 |

### 无新建文件、无新依赖

---

## 五、测试策略

| 功能 | 测试内容 |
|------|----------|
| **BibTeX 导出** | API 返回 200 + Content-Disposition、空 references 返回注释、404、entry_type 判断（article vs inproceedings）、cite_key 生成、作者格式化、中文作者降级 anonymous |
| **Reranker 属性** | `FlashRankReranker.name` → `"flashrank"`、`BM25FallbackReranker.name` → `"bm25"`、`model_name` 正确返回 |
| **retrieve_node trace** | trace 条目包含 reranker name 和数量信息 |
| **done SSE** | `reranker_used` 和 `reranker_summary` 字段存在且类型正确 |
| **前端导出按钮** | BibTeX 选项在 paperId 存在时可用、点击触发下载、文件名正确 |

---

## 六、风险与应对

| 风险 | 可能性 | 影响 | 应对 |
|------|--------|------|------|
| PDF 解析未提取参考文献 | 中 | 空 .bib 文件 | 返回注释说明，不影响功能；后续可增强 PDF 解析 |
| 中文作者 cite_key 为空 | 低 | cite_key 降级 anonymous | 文档说明 + 代码降级处理 |
| `state.retriever` 为 None 时 done 构建崩溃 | 低 | done 事件缺失 | 添加 None 检查，降级为 "unknown" |
