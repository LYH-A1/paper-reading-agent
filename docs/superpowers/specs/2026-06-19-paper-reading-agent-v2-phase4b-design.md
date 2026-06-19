# 论文阅读 Agent V2 — Phase 4b 设计文档

> 日期：2026-06-19 | 状态：已确认  
> 父文档：[V2 整体设计](2026-06-17-paper-reading-agent-v2-design.md)  
> Phase 4a 设计：[Phase 4a 设计文档](2026-06-19-paper-reading-agent-v2-phase4a-design.md)

---

## 一、概述

Phase 4b 实现外部检索 + 单论文对比分析。范围：单论文入口 + arXiv/Semantic Scholar 外部检索 + LLM 融合对比。搜索结果不作为持久论文，仅用于单次对比分析。

| 功能 | 层级 | 核心改动 |
|------|------|----------|
| **外部检索 (arXiv + S2)** | 后端 | 新建 `external_search.py`，LangGraph 新增 `external_search` 节点 |
| **对比分析** | 后端 + 前端 | generate_node 融合内外证据，EvidencePopover 支持外部链接 |

---

## 二、ExternalRetriever 模块

### 2.1 架构

```
backend/tools/external_search.py
├── ExternalResult (dataclass)      — 单个外部检索结果
├── ExternalRetriever                — 检索器（可缓存到 AgentState）
│   ├── search(query, top_k) → list[ExternalResult]
│   ├── _search_arxiv(query, n)     — arXiv API 主检索
│   └── _enrich_with_s2(results)    — Semantic Scholar 补充引用

backend/agents/qa.py
└── _build_search_query(state) → str  — LLM 提取搜索关键词（模块级函数）
```

**缓存策略：** `ExternalRetriever` 在 first use 创建后存入 `AgentState.external_retriever`（与 `HybridRetriever` 模式一致），后续节点复用。`_build_search_query` 是 `qa.py` 的模块级函数（需要访问 `llm_client`），不走 ExternalRetriever。

### 2.2 数据模型

```python
@dataclass
class ExternalResult:
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    url: str = ""               # arXiv abs URL
    source: str = ""            # "arxiv" | "semantic_scholar"
    citation_count: int | None = None   # 来自 S2
    related_titles: list[str] = field(default_factory=list)  # 来自 S2 的推荐（最多 3）
```

### 2.3 arXiv 检索

- **端点：** `GET http://export.arxiv.org/api/query?search_query=all:{query}&max_results={n}&sortBy=relevance`
- **解析：** `xml.etree.ElementTree` 解析 Atom XML → 提取 `<entry>` 元素
- **字段提取：** title（去多余空白）、authors（`<author>/<name>`）、abstract（截断 500 字符）、year（从 `<published>` 取）、arxiv_id → 构造 url
- **Rate limit：** 每次请求前检查 `time.time() - self._last_request_time`，不足 3 秒则 `asyncio.sleep()`

### 2.4 Semantic Scholar 补充

- **端点：** `GET https://api.semanticscholar.org/graph/v1/paper/search/match?query={title}&fields=citationCount,citations.title`
- **API key：** 环境变量 `S2_API_KEY`，通过 `x-api-key` header 传递
- **匹配策略：** 对 arXiv 返回的每条结果，用 title 在 S2 中 match。title 匹配成功后获取 citationCount + 引用论文的 title（最多 3 条），写入 `ExternalResult.citation_count` 和 `related_titles`
- **降级：** key 缺失或 S2 返回 429 → 跳过 enrichment，保留纯 arXiv 结果
- **超时：** 单条 S2 请求 timeout 5s，整体 enrichment 超时 15s

### 2.5 搜索查询构造

```python
async def _build_search_query(state: AgentState) -> str:
    """用 LLM 从检索结果中提取 3-5 个关键术语用于外部搜索。"""
    chunks_text = "\n".join(c.text[:200] for c in state.retrieved_chunks[:5])
    prompt = (
        "From the following paper excerpts, extract 3-5 key technical terms "
        "(method names, baseline algorithms, frameworks) that would be useful "
        "for searching related work on arXiv. Return ONLY a space-separated "
        "list of terms, no explanation.\n\n" + chunks_text
    )
    terms = await llm_client.chat(prompt, max_tokens=80)
    return terms.strip()
```

如果 `retrieved_chunks` 为空，降级为直接使用 `state.user_query`。

### 2.6 错误处理

| 错误场景 | 等级 | 策略 |
|----------|------|------|
| arXiv 超时（>10s） | L2 | `external_search_node` 设置 `state.external_search_error = "arXiv timed out"`，跳过 external_search，直接进 generate |
| S2 返回 429 或超时 | L1 | 跳过 enrichment，仅返回 arXiv 结果，trace 中记录 `"s2 skipped (rate limited)"` |
| arXiv + S2 都失败 | L2 | 同 L2，设置 error 字段，generate 仅用内部 R0 证据，回答开头提示"外部检索暂不可用" |
| arXiv 返回 0 结果 | L1 | 正常返回空列表，generate 基于仅内部证据生成回答 |

---

## 三、LangGraph 集成

### 3.1 新流程

```
reader → classify → planner → retrieve → [external_search] → generate → observe → reviewer → output
                                           ↑
                                   compare/recommend 时执行
```

### 3.2 条件路由

在 `supervisor.py build_graph()` 中：

```python
graph.add_node("external_search", external_search_node)
graph.add_conditional_edges("retrieve", route_after_retrieve, {
    "external_search": "external_search",
    "generate": "generate",
})
graph.add_edge("external_search", "generate")
```

```python
def route_after_retrieve(state: AgentState) -> str:
    if state.intent in ("compare", "recommend"):
        return "external_search"
    return "generate"
```

### 3.3 external_search_node

```python
async def external_search_node(state: AgentState) -> AgentState:
    """Search external sources for comparison/recommendation context."""
    from backend.tools.external_search import ExternalRetriever

    if state.external_retriever is None:
        state.external_retriever = ExternalRetriever()

    query = await _build_search_query(state)
    try:
        results = await asyncio.wait_for(
            state.external_retriever.search(query, top_k=5),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        state.external_search_error = "External search timed out"
        state.trace.append("external_search: timeout")
        return state
    except Exception as e:
        state.external_search_error = f"External search failed: {e}"
        state.trace.append("external_search: error")
        return state

    state.external_results = results
    state.trace.append(f"external_search: {len(results)} results")
    return state
```

### 3.4 observe 扩展

`observe_node` 增加外部检索充分性检查。如果 `intent` 是 compare/recommend 且外部结果 <2 条，标记 insufficient 以触发重试：

```python
# 在 observe_node 返回前
if state.intent in ("compare", "recommend"):
    observe_cycles = state.trace.count("observe")
    ext_count = len(state.external_results) if state.external_results else 0
    if ext_count < 2 and observe_cycles < 2:
        obs["sufficient"] = False
        obs["gaps"] = obs.get("gaps", []) + [
            f"External search returned only {ext_count} results, need more for comparison"
        ]
    state.observation = obs
```

`check_observe_result` 同步更新，增加 `external_search` 路由：

```python
def check_observe_result(state: AgentState) -> str:
    obs = state.observation or {}
    observe_cycles = state.trace.count("observe")
    if observe_cycles >= 3:
        return "reviewer"
    if not obs.get("plan_valid", True):
        return "planner"
    if not obs.get("sufficient", False):
        # Phase 4b: if external search returned too few results, retry it
        if state.intent in ("compare", "recommend"):
            ext_count = len(state.external_results) if state.external_results else 0
            if ext_count < 2:
                return "external_search"
        return "retrieve"
    return "reviewer"
```

graph 条件边更新：

```python
graph.add_conditional_edges("observe", check_observe_result, {
    "reviewer": "reviewer",
    "retrieve": "retrieve",
    "planner": "planner",
    "external_search": "external_search",  # Phase 4b
})
```

重试时，`external_search_node` 检测到已有结果→用 `related_titles` 扩展查询（而非重复相同搜索）。`observe_cycles` 通过 `state.trace.count("observe")` 计算，上限 3 次不变。

### 3.5 supervisor.py HITL 适配

`external_search` 节点在 `planner` 之后执行，不影响 HITL 中断逻辑。Segment 1（reader→planner）不变，Segment 2 流式事件中增加 `external_search` 的 on_chain_start/end 事件。

---

## 四、数据模型变更

### 4.1 AgentState

```python
# 新增字段
external_retriever: Any | None = None          # ExternalRetriever 实例
external_results: list = field(default_factory=list)  # ExternalResult 列表
external_search_error: str | None = None
# observe_cycles 通过 state.trace.count("observe") 计算，无需新增字段
```

### 4.2 Evidence

```python
# 新增字段
external_result_id: str | None = None  # 指向 ExternalResult.result_id
```

R1 证据生成时，如果来源是外部检索，Reviewer Agent 在 evidence 中填入对应的 `external_result_id`。

---

## 五、generate_node 变更

`generate_node` 构造 context 时追加外部结果：

```python
# 现有内部 context（不变）
context = "\n\n".join(c.text for c in state.retrieved_chunks[:5])

# Phase 4b: 追加外部检索结果
if state.external_results:
    ext_header = "\n\n### External References (from arXiv/Semantic Scholar):\n"
    ext_lines = []
    for i, r in enumerate(state.external_results):
        ext_lines.append(
            f"[EXT-{i+1}] {r.title} ({r.year or 'n.d.'})\n"
            f"    Authors: {', '.join(r.authors[:3])}\n"
            f"    Abstract: {r.abstract[:400]}\n"
            f"    URL: {r.url}\n"
            f"    Citations: {r.citation_count or 'N/A'}"
        )
        if r.related_titles:
            ext_lines.append(f"    Related: {', '.join(r.related_titles[:3])}")
    context += ext_header + "\n".join(ext_lines)
```

如果 `state.external_search_error` 非空，在 context 前追加提示：
```
Note: External search is currently unavailable. Answer based on internal paper content only.
```

---

## 六、提示词变更

### 6.1 ANSWER_PROMPTS["compare"]

```python
"compare": '''You are a comparative analysis assistant. Compare the paper's approach
with alternatives from both the paper's internal references [Section X] and
external search results [EXT-N].

Rules:
1. After each claim about the current paper, cite: [Section X, Page Y]
2. After each claim about external work, cite: [EXT-N]
3. Distinguish between what the paper states, what external sources state,
   and your own analysis
4. Use a comparison table when comparing numerical results
5. Structure: **Our Paper** vs **External Work** → **Key Differences** → **Recommendation**''',
```

### 6.2 ANSWER_PROMPTS["recommend"]

```python
"recommend": '''You are a literature recommendation assistant. Based on the paper's
content, references [Section X], and external search results [EXT-N],
recommend 3-5 related papers with a brief explanation of relevance.

For each recommendation, indicate whether it comes from the paper's own
references or from external search. Provide DOI or arXiv URL when available.''',
```

---

## 七、SSE / done 事件扩展

`_build_done_payload()` 中增加 `external_results` 字段：

```python
"external_results": [
    {
        "result_id": r.result_id,
        "title": r.title,
        "authors": r.authors,
        "abstract": r.abstract[:400],
        "year": r.year,
        "url": r.url,
        "source": r.source,
        "citation_count": r.citation_count,
    }
    for r in state.external_results
],
```

---

## 八、前端变更

### 8.1 类型定义

```typescript
export interface ExternalResult {
  result_id: string
  title: string
  authors: string[]
  abstract: string
  year: number | null
  url: string
  source: string
  citation_count: number | null
}

// DoneEvent 扩展
export interface DoneEvent {
  // ... 现有字段 ...
  external_results: ExternalResult[]
}
```

### 8.2 EvidencePopover

R1 证据 Popover 中，如果 `evidence.external_result_id` 非空，显示 "View on arXiv ↗" 链接（从 `external_results` 表中查找对应 `url`）。

### 8.3 StepIndicator

在 `NODE_ORDER` 中增加 `external_search`（在 `retrieve` 和 `generate` 之间）。

### 8.4 TracePanel

现有 trace 渲染不变——`external_search: 5 results (arxiv + s2)` 作为 trace 条目正常显示。

---

## 九、配置变更

### config.py

```python
@dataclass
class Config:
    # ... 现有字段 ...
    s2_api_key: str = os.getenv("S2_API_KEY", "")
    arxiv_request_interval: float = float(os.getenv("ARXIV_REQUEST_INTERVAL", "3.0"))
```

---

## 十、文件变更清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `backend/tools/external_search.py` | ExternalResult + ExternalRetriever + _build_search_query |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/agents/supervisor.py` | build_graph 增加 external_search 节点 + 条件路由 + 流式事件 + done 事件扩展 |
| `backend/agents/qa.py` | 新增 external_search_node、generate_node 追加外部 context、observe_node 扩展 |
| `backend/models/state.py` | AgentState 增加 external_retriever, external_results, external_search_error；Evidence 增加 external_result_id |
| `backend/llm/prompts.py` | compare/recommend 的 ANSWER_PROMPTS 更新，新增 SEARCH_QUERY_PROMPT |
| `backend/config.py` | 增加 s2_api_key、arxiv_request_interval 配置 |
| `frontend/src/types/index.ts` | 新增 ExternalResult 接口；DoneEvent 扩展 external_results |
| `frontend/src/components/Evidence/EvidencePopover.tsx` | R1 外部来源显示 arXiv 链接 |
| `frontend/src/components/ChatPanel/StepIndicator.tsx` | NODE_ORDER 增加 external_search |

无新依赖（arxiv 用标准库 xml.etree + urllib，s2 用 httpx 已有）。

---

## 十一、测试策略

| 功能 | 测试内容 |
|------|----------|
| **ExternalResult** | 数据模型创建、默认值、UUID 生成 |
| **ExternalRetriever.search** | arXiv mock 返回解析、空结果、超时处理、S2 降级 |
| **_build_search_query** | LLM mock 返回关键词列表、空 chunks 降级为 user_query |
| **external_search_node** | 正常流程、超时降级、error state 设置、trace 追加 |
| **route_after_retrieve** | compare 走 external_search，summary 跳过 |
| **observe_node 扩展** | 外部结果 <2 触发重试、observe_cycles 上限不变 |
| **generate_node** | 外部结果出现在 context 中、error 提示注入 |
| **done_payload** | external_results 字段正确序列化 |
| **前端类型** | ExternalResult 接口兼容性 |

---

## 十二、风险与应对

| 风险 | 可能性 | 影响 | 应对 |
|------|--------|------|------|
| arXiv API 不稳定 | 中 | 对比分析失败 | 三级降级策略 + 提示"外部检索暂不可用" |
| S2 API key 未配置 | 高 | 无引用数据 | S2 为可选增强，默认跳过 |
| LLM 提取搜索词质量差 | 中 | 搜索不相关 | keyword fallback：如果 LLM 返回 <2 个词，降级为 user_query |
| observe 重试导致外部 API 重复调用 | 中 | 延迟增加 + rate limit 风险 | 重试时使用不同查询（从已搜索结果的 related_titles 扩展关键词） |
| 外部结果 token 超出 LLM context | 低 | generate 失败 | 每条 abstract 截断至 400 字符，总外部 context 不超过 2000 tokens |
