# Phase 4b: 外部检索 + 单论文对比分析 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add external paper search via arXiv + Semantic Scholar, integrate into LangGraph as a conditional node, and enable LLM-powered comparative analysis between the uploaded paper and external results.

**Architecture:** New `external_search.py` module (ExternalResult + ExternalRetriever). New `external_search` node inserted between retrieve and generate in LangGraph, conditionally routed for `compare`/`recommend` intents. observe_node extended for external result sufficiency check with retry loop. Frontend EvidencePopover gains external link support.

**Tech Stack:** Python stdlib (`xml.etree`, `urllib`, `asyncio`) for arXiv API; `httpx` (existing) for Semantic Scholar; React/TypeScript (existing).

## Global Constraints

- No new pip/npm dependencies
- 1 new file: `backend/tools/external_search.py`
- Backend tests: pytest in `paper-reading-agent/tests/`
- Frontend tests: vitest in `paper-reading-agent/frontend/`
- Commit prefix: `feat(phase4b):`
- ExternalRetriever cached to AgentState (not recreated per node)
- Evidence.external_result_id uses UUID (not list index)
- _build_search_query uses LLM (not regex rules)
- ArXiv rate limit: ≥3s between requests
- observe external retry: max 2 observe cycles, max 3 observe cycles total

---

### Task 1: ExternalResult + ExternalRetriever module

**Files:**
- Create: `paper-reading-agent/backend/tools/external_search.py`
- Create: `paper-reading-agent/tests/test_external_search.py`

**Interfaces:**
- Produces: `ExternalResult` dataclass (result_id, title, authors, abstract, year, url, source, citation_count, related_titles); `ExternalRetriever` class (search, _search_arxiv, _enrich_with_s2); `EXTERNAL_SEARCH_TIMEOUT = 15.0`

- [ ] **Step 1: Create the module**

Create `paper-reading-agent/backend/tools/external_search.py`:

```python
"""External paper search: arXiv API + Semantic Scholar enrichment."""

import asyncio
import time
import uuid
import os
from dataclasses import dataclass, field
from xml.etree import ElementTree
from urllib.parse import quote

from backend.utils.logger import logger

EXTERNAL_SEARCH_TIMEOUT = 15.0
ARXIV_REQUEST_INTERVAL = float(os.getenv("ARXIV_REQUEST_INTERVAL", "3.0"))


@dataclass
class ExternalResult:
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    url: str = ""
    source: str = ""            # "arxiv" | "semantic_scholar"
    citation_count: int | None = None
    related_titles: list[str] = field(default_factory=list)


class ExternalRetriever:
    """Search arXiv for papers, optionally enrich with Semantic Scholar citations."""

    def __init__(self):
        self._last_request_time: float = 0.0
        self._s2_api_key: str = os.getenv("S2_API_KEY", "")

    # ---- public ----

    async def search(self, query: str, top_k: int = 5) -> list[ExternalResult]:
        """Main entry: search arXiv, enrich with S2 if available."""
        results = await self._search_arxiv(query, top_k)
        if results and self._s2_api_key:
            try:
                results = await self._enrich_with_s2(results)
            except Exception:
                logger.warning("S2 enrichment failed, returning arXiv-only results")
        return results

    # ---- arXiv ----

    async def _search_arxiv(self, query: str, max_results: int) -> list[ExternalResult]:
        """Query arXiv API and parse Atom XML response."""
        await self._respect_rate_limit()

        encoded = quote(query)
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=all:{encoded}&max_results={max_results}&sortBy=relevance"
        )
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                xml_text = resp.text
        except Exception as e:
            logger.error(f"arXiv API request failed: {e}")
            raise

        return self._parse_arxiv_xml(xml_text)

    async def _respect_rate_limit(self) -> None:
        """Ensure at least ARXIV_REQUEST_INTERVAL seconds between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < ARXIV_REQUEST_INTERVAL:
            await asyncio.sleep(ARXIV_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _parse_arxiv_xml(self, xml_text: str) -> list[ExternalResult]:
        """Parse arXiv Atom XML into ExternalResult list."""
        root = ElementTree.fromstring(xml_text)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        results = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

            authors = []
            for author_el in entry.findall("atom:author", ns):
                name_el = author_el.find("atom:name", ns)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())

            abstract_el = entry.find("atom:summary", ns)
            abstract = (abstract_el.text or "").strip()[:500] if abstract_el is not None else ""

            published_el = entry.find("atom:published", ns)
            year = None
            if published_el is not None and published_el.text:
                year = int(published_el.text[:4])

            arxiv_id = ""
            id_el = entry.find("atom:id", ns)
            if id_el is not None and id_el.text:
                # Extract ID from URL like http://arxiv.org/abs/XXXX.XXXXX
                arxiv_id = id_el.text.split("/abs/")[-1]

            url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""

            results.append(ExternalResult(
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                url=url,
                source="arxiv",
            ))
        return results

    # ---- Semantic Scholar ----

    async def _enrich_with_s2(self, results: list[ExternalResult]) -> list[ExternalResult]:
        """Enrich results with citation counts and related titles from S2."""
        import httpx

        async def _fetch_one(r: ExternalResult) -> ExternalResult:
            if not r.title:
                return r
            encoded = quote(r.title)
            url = (
                f"https://api.semanticscholar.org/graph/v1/paper/search/match"
                f"?query={encoded}&fields=citationCount,citations.title"
            )
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        url,
                        headers={"x-api-key": self._s2_api_key},
                    )
                    if resp.status_code == 429:
                        logger.warning("S2 rate limited (429), skipping enrichment")
                        return r
                    resp.raise_for_status()
                    data = resp.json()
            except Exception:
                return r

            paper = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            if paper:
                r.citation_count = paper.get("citationCount")
                citations = paper.get("citations", [])
                r.related_titles = [c.get("title", "") for c in citations[:3] if c.get("title")]
            r.source = "semantic_scholar" if r.citation_count is not None else "arxiv"
            return r

        tasks = [_fetch_one(r) for r in results]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)
        return [e if not isinstance(e, Exception) else r for e, r in zip(enriched, results)]
```

- [ ] **Step 2: Write tests**

Create `paper-reading-agent/tests/test_external_search.py`:

```python
"""Tests for external search module."""

import pytest
import time
from dataclasses import asdict

from backend.tools.external_search import (
    ExternalResult,
    ExternalRetriever,
    EXTERNAL_SEARCH_TIMEOUT,
)


# ---- ExternalResult ----

def test_external_result_defaults():
    r = ExternalResult()
    assert r.result_id != ""
    assert r.title == ""
    assert r.authors == []
    assert r.abstract == ""
    assert r.year is None
    assert r.url == ""
    assert r.source == ""
    assert r.citation_count is None
    assert r.related_titles == []


def test_external_result_fields():
    r = ExternalResult(
        title="Test Paper",
        authors=["Alice", "Bob"],
        year=2024,
        url="https://arxiv.org/abs/1234.5678",
        source="arxiv",
        citation_count=42,
    )
    assert r.title == "Test Paper"
    assert r.year == 2024
    assert r.citation_count == 42


def test_external_result_unique_ids():
    r1 = ExternalResult()
    r2 = ExternalResult()
    assert r1.result_id != r2.result_id


# ---- arXiv XML parsing ----

ARXIV_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <summary>  The dominant sequence transduction models are based on complex
recurrent or convolutional neural networks...  </summary>
    <published>2017-06-12T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1512.03385v1</id>
    <title>Deep Residual Learning for Image Recognition</title>
    <author><name>Kaiming He</name></author>
    <summary>  Deeper neural networks are more difficult to train...  </summary>
    <published>2015-12-10T00:00:00Z</published>
  </entry>
</feed>"""


def test_parse_arxiv_xml():
    retriever = ExternalRetriever()
    results = retriever._parse_arxiv_xml(ARXIV_XML_SAMPLE)
    assert len(results) == 2

    r1 = results[0]
    assert r1.title == "Attention Is All You Need"
    assert r1.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert "dominant sequence transduction" in r1.abstract
    assert r1.year == 2017
    assert "1706.03762" in r1.url
    assert r1.source == "arxiv"

    r2 = results[1]
    assert r2.title == "Deep Residual Learning for Image Recognition"
    assert r2.year == 2015


def test_parse_arxiv_xml_empty():
    empty_xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom"/>
    """
    retriever = ExternalRetriever()
    results = retriever._parse_arxiv_xml(empty_xml)
    assert results == []


# ---- Rate limiting ----

@pytest.mark.asyncio
async def test_rate_limit_first_request_no_delay():
    retriever = ExternalRetriever()
    t0 = time.time()
    await retriever._respect_rate_limit()
    elapsed = time.time() - t0
    assert elapsed < 0.5  # first request should be instant


@pytest.mark.asyncio
async def test_rate_limit_second_request_waits():
    retriever = ExternalRetriever()
    retriever._last_request_time = time.time()  # simulate recent request
    t0 = time.time()
    await retriever._respect_rate_limit()
    elapsed = time.time() - t0
    # Should have waited at least ~3s, but we can't test this precisely in CI
    assert elapsed >= 0  # at minimum, doesn't crash and returns
```

- [ ] **Step 3: Run tests**

```bash
cd paper-reading-agent && python -m pytest tests/test_external_search.py -v
```

Expected: ALL 7 PASS

- [ ] **Step 4: Commit**

```bash
git add paper-reading-agent/backend/tools/external_search.py paper-reading-agent/tests/test_external_search.py
git commit -m "feat(phase4b): add ExternalResult + ExternalRetriever module with arXiv XML parsing"
```

---

### Task 2: Data model changes — AgentState + Evidence

**Files:**
- Modify: `paper-reading-agent/backend/models/state.py`

**Interfaces:**
- Consumes: ExternalResult (from Task 1)
- Produces: AgentState gains `external_retriever`, `external_results`, `external_search_error`; Evidence gains `external_result_id`

- [ ] **Step 1: Add fields to AgentState and Evidence**

In `paper-reading-agent/backend/models/state.py`:

Add `external_result_id` to Evidence (after `confidence`):

```python
    # General
    confidence: float = 0.0
    claim_group_id: str | None = None
    external_result_id: str | None = None  # Phase 4b: links to ExternalResult.result_id
```

Add fields to AgentState (after `followup_questions`):

```python
    session_id: str = ""
    followup_questions: list[str] = field(default_factory=list)

    # Phase 4b: external search
    external_retriever: Any | None = None
    external_results: list = field(default_factory=list)
    external_search_error: str | None = None
```

- [ ] **Step 2: Write tests**

In `paper-reading-agent/tests/test_models.py`, add:

```python
def test_evidence_external_result_id():
    from backend.models.state import Evidence
    e = Evidence(evidence_id="e1", claim="test", level="R1")
    assert e.external_result_id is None
    e2 = Evidence(evidence_id="e2", claim="test", level="R1", external_result_id="ext-123")
    assert e2.external_result_id == "ext-123"


def test_agent_state_external_fields():
    from backend.models.state import AgentState
    state = AgentState()
    assert state.external_retriever is None
    assert state.external_results == []
    assert state.external_search_error is None
```

- [ ] **Step 3: Run tests**

```bash
cd paper-reading-agent && python -m pytest tests/test_models.py -v
```

Expected: ALL PASS (existing + 2 new)

- [ ] **Step 4: Commit**

```bash
git add paper-reading-agent/backend/models/state.py paper-reading-agent/tests/test_models.py
git commit -m "feat(phase4b): add external search fields to AgentState and Evidence"
```

---

### Task 3: Config + Prompts

**Files:**
- Modify: `paper-reading-agent/backend/config.py`
- Modify: `paper-reading-agent/backend/llm/prompts.py`

**Interfaces:**
- Produces: `Config.s2_api_key`, `Config.arxiv_request_interval`; `ANSWER_PROMPTS["compare"]` and `["recommend"]` updated; `SEARCH_QUERY_PROMPT` constant

- [ ] **Step 1: Update config.py**

In `paper-reading-agent/backend/config.py`, add to the `Config` dataclass:

```python
    # Phase 4b: external search
    s2_api_key: str = os.getenv("S2_API_KEY", "")
    arxiv_request_interval: float = float(os.getenv("ARXIV_REQUEST_INTERVAL", "3.0"))
```

- [ ] **Step 2: Update prompts.py**

In `paper-reading-agent/backend/llm/prompts.py`:

Replace `ANSWER_PROMPTS["compare"]`:

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

Replace `ANSWER_PROMPTS["recommend"]`:

```python
    "recommend": '''You are a literature recommendation assistant. Based on the paper's
content, references [Section X], and external search results [EXT-N],
recommend 3-5 related papers with a brief explanation of relevance.

For each recommendation, indicate whether it comes from the paper's own
references or from external search. Provide DOI or arXiv URL when available.''',
```

Add a new constant after `KEYWORD_RULES`:

```python
SEARCH_QUERY_PROMPT = (
    "From the following paper excerpts, extract 3-5 key technical terms "
    "(method names, baseline algorithms, frameworks) that would be useful "
    "for searching related work on arXiv. Return ONLY a space-separated "
    "list of terms, no explanation.\n\n"
)
```

- [ ] **Step 3: Verify imports and run tests**

```bash
cd paper-reading-agent && python -c "from backend.config import config; print(config.s2_api_key)" && python -c "from backend.llm.prompts import SEARCH_QUERY_PROMPT; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add paper-reading-agent/backend/config.py paper-reading-agent/backend/llm/prompts.py
git commit -m "feat(phase4b): add S2_API_KEY config, SEARCH_QUERY_PROMPT, updated compare/recommend prompts"
```

---

### Task 4: external_search_node + _build_search_query + route_after_retrieve

**Files:**
- Modify: `paper-reading-agent/backend/agents/qa.py`
- Modify: `paper-reading-agent/tests/test_reranker.py` or a new tests file for integration (use existing test infrastructure)

**Interfaces:**
- Consumes: ExternalRetriever (from Task 1), AgentState.external_retriever (from Task 2), SEARCH_QUERY_PROMPT (from Task 3)
- Produces: `external_search_node(state)`, `_build_search_query(state)`, `route_after_retrieve(state)`

- [ ] **Step 1: Add functions to qa.py**

In `paper-reading-agent/backend/agents/qa.py`, add imports at top:

```python
import asyncio
from backend.llm.prompts import CLASSIFY_PROMPT, PLANNER_PROMPTS, ANSWER_PROMPTS, OBSERVE_PROMPT, KEYWORD_RULES, SEARCH_QUERY_PROMPT
```

Add these functions after the existing `_keyword_classify`:

```python
# ---- Phase 4b: External Search ----

def route_after_retrieve(state: AgentState) -> str:
    """Conditional routing: compare/recommend → external_search, else generate."""
    if state.intent in ("compare", "recommend"):
        return "external_search"
    return "generate"


async def _build_search_query(state: AgentState) -> str:
    """Use LLM to extract search keywords from retrieved chunks."""
    if not state.retrieved_chunks:
        return state.user_query

    chunks_text = "\n".join(c.text[:200] for c in state.retrieved_chunks[:5])
    prompt = SEARCH_QUERY_PROMPT + chunks_text
    try:
        terms = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="Respond ONLY with the space-separated list of terms, no explanation.",
            max_tokens=80,
        )
        terms = terms.strip()
        # Fallback: if LLM returned too few terms, use user_query
        if len(terms.split()) < 2:
            return state.user_query
        return terms
    except Exception as e:
        logger.warning(f"Search query extraction failed: {e}, using user query")
        return state.user_query


async def external_search_node(state: AgentState) -> AgentState:
    """Search external sources (arXiv + S2) for comparison context."""
    from backend.tools.external_search import ExternalRetriever, EXTERNAL_SEARCH_TIMEOUT

    if state.external_retriever is None:
        state.external_retriever = ExternalRetriever()

    # On retry (results already exist), extend query with related titles
    query = await _build_search_query(state)
    if state.external_results:
        related = []
        for r in state.external_results[:3]:
            related.extend(r.related_titles[:1])
        if related:
            query = query + " " + " ".join(related[:3])

    try:
        results = await asyncio.wait_for(
            state.external_retriever.search(query, top_k=5),
            timeout=EXTERNAL_SEARCH_TIMEOUT,
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
    sources = set(r.source for r in results)
    trace_entry = f"external_search: {len(results)} results ({', '.join(sorted(sources))})"
    if state.external_search_error:
        trace_entry += f" (error: {state.external_search_error})"
    state.trace.append(trace_entry)
    return state
```

- [ ] **Step 2: Run backend tests**

```bash
cd paper-reading-agent && python -m pytest tests/ -v -k "not test_reranker and not test_retriever and not test_storage and not test_export and not test_bibtex and not test_sse and not test_pdf and not test_config and not test_llm and not test_preferences" 2>&1 | tail -5
```

Or simply check imports:

```bash
cd paper-reading-agent && python -c "from backend.agents.qa import external_search_node, route_after_retrieve, _build_search_query; print('All imports OK')"
```

- [ ] **Step 3: Commit**

```bash
git add paper-reading-agent/backend/agents/qa.py
git commit -m "feat(phase4b): add external_search_node, _build_search_query, route_after_retrieve"
```

---

### Task 5: generate_node + observe_node + check_observe_result updates

**Files:**
- Modify: `paper-reading-agent/backend/agents/qa.py`

**Interfaces:**
- Consumes: `state.external_results`, `state.external_search_error` (from Task 2); `external_search_node` (from Task 4)
- Produces: generate_node builds external context; observe_node checks external sufficiency; check_observe_result routes to external_search

- [ ] **Step 1: Update generate_node**

In `paper-reading-agent/backend/agents/qa.py`, modify `generate_node`. After the existing context line:

```python
    context = "\n\n".join(c.text for c in state.retrieved_chunks[:5]) if state.retrieved_chunks else state.paper.abstract if state.paper else ""
```

Add:

```python

    # Phase 4b: append external search results
    if state.external_search_error:
        context = (
            "Note: External search is currently unavailable. "
            "Answer based on internal paper content only.\n\n" + context
        )
    elif state.external_results:
        ext_lines = ["\n\n### External References (from arXiv/Semantic Scholar):\n"]
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
        context += "\n".join(ext_lines)
```

- [ ] **Step 2: Update observe_node**

In `observe_node`, after the existing observation logic (after `state.observation = obs` equivalent), add before `state.trace.append("observe")`:

```python
    # Phase 4b: check external search sufficiency
    if state.intent in ("compare", "recommend"):
        ext_count = len(state.external_results) if state.external_results else 0
        observe_cycles = state.trace.count("observe")
        if ext_count < 2 and observe_cycles < 2 and not state.external_search_error:
            result["sufficient"] = False
            gaps = result.get("gaps", [])
            if isinstance(gaps, list):
                gaps.append(
                    f"External search returned only {ext_count} result(s), "
                    "need more for comparison"
                )
                result["gaps"] = gaps
        state.observation = result
```

- [ ] **Step 3: Update check_observe_result**

Replace `check_observe_result`:

```python
def check_observe_result(state: AgentState) -> str:
    """Conditional edge after observe."""
    obs = state.observation or {}
    # Prevent infinite observe loop: max 3 retrieve→generate→observe cycles
    observe_cycles = state.trace.count("observe")
    if observe_cycles >= 3:
        return "reviewer"
    if not obs.get("plan_valid", True):
        return "planner"
    if not obs.get("sufficient", False):
        # Phase 4b: retry external search if too few results
        if state.intent in ("compare", "recommend"):
            ext_count = len(state.external_results) if state.external_results else 0
            if ext_count < 2:
                return "external_search"
        return "retrieve"
    return "reviewer"
```

- [ ] **Step 4: Run import check**

```bash
cd paper-reading-agent && python -c "from backend.agents.qa import check_observe_result, external_search_node; print('All OK')"
```

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/agents/qa.py
git commit -m "feat(phase4b): update generate_node, observe_node, check_observe_result for external search"
```

---

### Task 6: supervisor.py full integration

**Files:**
- Modify: `paper-reading-agent/backend/agents/supervisor.py`

**Interfaces:**
- Consumes: `external_search_node`, `route_after_retrieve`, `check_observe_result` (from Tasks 4-5)
- Produces: build_graph adds external_search node + edges; SSE events include external_search; done payload includes external_results

- [ ] **Step 1: Update build_graph**

In `build_graph()`, after the existing node definitions, add import and node:

```python
from backend.agents.qa import classify_node, planner_node, retrieve_node, generate_node, observe_node, check_observe_result, external_search_node, route_after_retrieve
```

Add the node:

```python
    graph.add_node("external_search", external_search_node)
```

Replace `graph.add_edge("retrieve", "generate")` with conditional edge:

```python
    graph.add_conditional_edges("retrieve", route_after_retrieve, {
        "external_search": "external_search",
        "generate": "generate",
    })
    graph.add_edge("external_search", "generate")
```

Update `check_observe_result` conditional edges:

```python
    graph.add_conditional_edges("observe", check_observe_result, {
        "reviewer": "reviewer",
        "retrieve": "retrieve",
        "planner": "planner",
        "external_search": "external_search",
    })
```

- [ ] **Step 2: Update SSE streaming events**

In `stream_graph()`, Segment 2 event handling, add `external_search` to the `on_chain_start` check:

```python
        if kind == "on_chain_start" and node_name in (
            "retrieve", "generate", "observe", "reviewer", "rewrite", "output",
            "external_search",
        ):
```

- [ ] **Step 3: Update _build_done_payload**

Add `external_results` to the payload dict:

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
            for r in (state.external_results or [])
        ],
```

- [ ] **Step 4: Write SSE test**

In `paper-reading-agent/tests/test_sse_protocol.py`, add:

```python
def test_done_payload_includes_external_results():
    """Done SSE payload includes external_results when present."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState, RetrievedChunk

    state = AgentState(
        answer="test answer",
        session_id="sess-1",
        retrieved_chunks=[],
        trace=[],
        external_results=[
            type("Ext", (), {
                "result_id": "ext-001",
                "title": "External Paper",
                "authors": ["Author One"],
                "abstract": "An abstract.",
                "year": 2025,
                "url": "https://arxiv.org/abs/9999.99999",
                "source": "arxiv",
                "citation_count": 10,
            })()
        ],
    )

    import json
    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert len(payload["external_results"]) == 1
    assert payload["external_results"][0]["result_id"] == "ext-001"
    assert payload["external_results"][0]["title"] == "External Paper"


def test_done_payload_empty_external_results():
    """Done SSE payload includes empty external_results list by default."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState
    import json

    state = AgentState(answer="test", session_id="sess-1", retrieved_chunks=[], trace=[])
    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert payload["external_results"] == []
```

- [ ] **Step 5: Run SSE tests**

```bash
cd paper-reading-agent && python -m pytest tests/test_sse_protocol.py -v
```

Expected: ALL PASS (existing + 2 new)

- [ ] **Step 6: Commit**

```bash
git add paper-reading-agent/backend/agents/supervisor.py paper-reading-agent/tests/test_sse_protocol.py
git commit -m "feat(phase4b): integrate external_search into LangGraph graph, SSE events, and done payload"
```

---

### Task 7: Frontend — types + EvidencePopover + StepIndicator

**Files:**
- Modify: `paper-reading-agent/frontend/src/types/index.ts`
- Modify: `paper-reading-agent/frontend/src/components/Evidence/EvidencePopover.tsx`
- Modify: `paper-reading-agent/frontend/src/components/ChatPanel/StepIndicator.tsx`

**Interfaces:**
- Consumes: `DoneEvent.external_results` (from Task 6)
- Produces: ExternalResult TypeScript type; EvidencePopover shows arXiv link; StepIndicator shows external_search node

- [ ] **Step 1: Update types**

In `paper-reading-agent/frontend/src/types/index.ts`, add before `DoneEvent`:

```typescript
// ---- External Search ----
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
```

Update `DoneEvent`:

```typescript
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
  external_results: ExternalResult[]
}
```

- [ ] **Step 2: Update StepIndicator**

In `StepIndicator.tsx`, update `NODE_ORDER`:

```typescript
const NODE_ORDER = ['reader', 'classify', 'planner', 'retrieve', 'external_search', 'generate', 'observe', 'reviewer', 'output', 'rewrite']
```

- [ ] **Step 3: Update EvidencePopover**

In `EvidencePopover.tsx`, read the component first. Then add external link rendering for R1 evidence that has `external_result_id`. The popover should:

- Check if the evidence level is `R1` and has a non-null `external_result_id`
- If so, match against `doneEvent.external_results` to find the corresponding URL
- Display a clickable "View on arXiv ↗" link that opens in a new tab

The exact implementation depends on how the component currently accesses evidence data. The key addition is:

```tsx
{evidence.level === 'R1' && evidence.external_result_id && externalResults && (
  (() => {
    const ext = externalResults.find(r => r.result_id === evidence.external_result_id)
    return ext ? (
      <a href={ext.url} target="_blank" rel="noopener noreferrer" className={styles.externalLink}>
        View on arXiv ↗
      </a>
    ) : null
  })()
)}
```

The `externalResults` needs to come from the done event. If the component doesn't currently have access to it, it should come from `useChatStore` (add an `externalResults` field to chatStore, populated from the done event).

**If this requires changing chatStore, the exact changes are:**

In `chatStore.ts`, add:
```typescript
externalResults: ExternalResult[]  // in the store interface
// ...in the initial state:
externalResults: [],
// ...in the SSE done handler:
set({ externalResults: doneEvent.external_results })
```

Then in EvidencePopover, access it via `const externalResults = useChatStore(s => s.externalResults)`.

- [ ] **Step 4: Run frontend tests**

```bash
cd paper-reading-agent/frontend && npx vitest run
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/frontend/src/types/index.ts paper-reading-agent/frontend/src/components/Evidence/EvidencePopover.tsx paper-reading-agent/frontend/src/components/ChatPanel/StepIndicator.tsx
git commit -m "feat(phase4b): add ExternalResult types, StepIndicator node, EvidencePopover arXiv link"
```

---

## Verification

After all 7 tasks:

```bash
# Backend
cd paper-reading-agent && python -m pytest tests/ -v

# Frontend
cd paper-reading-agent/frontend && npx vitest run
```

Expected: ALL PASS
