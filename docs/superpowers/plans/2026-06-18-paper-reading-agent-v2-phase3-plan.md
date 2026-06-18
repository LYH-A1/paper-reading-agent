# Paper Reading Agent V2 Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FlashRank cross-encoder reranking, Markdown/JSON conversation export, and user preference persistence (UI + Agent).

**Architecture:** Three independent features: (A) FlashRank reranker as pluggable module integrated into HybridRetriever, (B) export API backed by existing SessionStore + SSE protocol update (init event with session_id), (C) zustand persist for UI preferences + REST API for Agent preferences backed by existing `preferences` table.

**Tech Stack:** flashrank (Python), existing FastAPI + LangGraph + DeepSeek (backend), existing React 18 + TypeScript + zustand (frontend). No new frontend dependencies.

## Global Constraints

- flashrank installed via `pip install flashrank`; model downloaded lazily on first `rerank()` call
- No new frontend npm dependencies — zustand `persist` middleware is built-in
- `preferences` table already exists in SQLite (key-value, created in Phase 1)
- `sessions` and `messages` tables already exist; `SessionStore` has full CRUD
- `RERANKER_BACKEND` env var (default `"flashrank"`) forces fallback in CI/test
- Preference whitelist: `reranker`, `top_k`, `language`, `embedding_model` only
- All tests use pytest (backend) or vitest (frontend), same patterns as Phase 1/2

---

### Task 1: Reranker Module (接口 + FlashRank + BM25 Fallback)

**Files:**
- Create: `backend/tools/reranker.py`
- Create: `tests/test_reranker.py`

**Interfaces:**
- Consumes: `backend.models.state.RetrievedChunk` (chunk_id, text, page, section_heading, source, scores)
- Produces:
  - `class RerankerLoadError(Exception)` — custom exception for model load failures
  - `class Reranker(ABC)` — abstract `rerank(query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]`
  - `class FlashRankReranker(Reranker)` — `__init__(model: str = "ms-marco-MiniLM-L-12-v2")`, lazy `_ensure_loaded()`
  - `class BM25FallbackReranker(Reranker)` — sorts by `passage.scores.get("bm25", 0)` descending
  - `def get_reranker(name: str | None = None) -> Reranker` — factory with env var override and auto-degrade

- [ ] **Step 1: Write failing tests**

```python
# tests/test_reranker.py
import os
import pytest
from backend.models.state import RetrievedChunk


def make_chunk(chunk_id: str, bm25: float = 0.0, dense: float = 0.0, text: str = "") -> RetrievedChunk:
    scores = {}
    if bm25:
        scores["bm25"] = bm25
    if dense:
        scores["dense"] = dense
    return RetrievedChunk(
        chunk_id=chunk_id, text=text or f"text-{chunk_id}", page=1,
        section_heading="Test", source="bm25", scores=scores,
    )


class TestBM25FallbackReranker:
    def test_sorts_by_bm25_descending(self):
        from backend.tools.reranker import BM25FallbackReranker
        reranker = BM25FallbackReranker()
        chunks = [
            make_chunk("a", bm25=0.3),
            make_chunk("b", bm25=0.9),
            make_chunk("c", bm25=0.5),
        ]
        result = reranker.rerank("test query", chunks)
        assert [c.chunk_id for c in result] == ["b", "c", "a"]

    def test_empty_passages_returns_empty(self):
        from backend.tools.reranker import BM25FallbackReranker
        result = BM25FallbackReranker().rerank("query", [])
        assert result == []

    def test_preserves_all_passages(self):
        from backend.tools.reranker import BM25FallbackReranker
        chunks = [make_chunk(str(i), bm25=float(i)) for i in range(5)]
        result = BM25FallbackReranker().rerank("q", chunks)
        assert len(result) == 5


class TestFlashRankReranker:
    def test_lazy_loading_does_not_load_on_init(self):
        """_ranker should be None after construction — no download at init time."""
        from backend.tools.reranker import FlashRankReranker
        r = FlashRankReranker()
        assert r._ranker is None

    def test_ensure_loaded_calls_flashrank(self):
        """_ensure_loaded imports and creates Ranker."""
        from backend.tools.reranker import FlashRankReranker
        import sys
        # Mock flashrank module
        mock_ranker_cls = type("MockRanker", (), {})
        mock_flashrank = type("mock_mod", (), {"Ranker": mock_ranker_cls})()
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "flashrank", mock_flashrank)
            r = FlashRankReranker()
            r._ensure_loaded()
            assert r._ranker is not None
            assert isinstance(r._ranker, mock_ranker_cls)


class TestGetReranker:
    def test_default_returns_flashrank_when_available(self):
        from backend.tools.reranker import get_reranker, FlashRankReranker
        import sys
        mock_ranker_cls = type("MockRanker", (), {})
        mock_flashrank = type("mock_mod", (), {"Ranker": mock_ranker_cls})()
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "flashrank", mock_flashrank)
            r = get_reranker()
            assert isinstance(r, FlashRankReranker)

    def test_env_var_forces_bm25(self):
        from backend.tools.reranker import get_reranker, BM25FallbackReranker
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("RERANKER_BACKEND", "bm25")
            r = get_reranker()
            assert isinstance(r, BM25FallbackReranker)

    def test_explicit_bm25_returns_bm25(self):
        from backend.tools.reranker import get_reranker, BM25FallbackReranker
        r = get_reranker("bm25")
        assert isinstance(r, BM25FallbackReranker)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd paper-reading-agent && python -m pytest tests/test_reranker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.tools.reranker'`

- [ ] **Step 3: Create `backend/tools/reranker.py`**

```python
"""Pluggable reranker module for HybridRetriever.

- Reranker: abstract interface
- FlashRankReranker: cross-encoder reranker with lazy model loading
- BM25FallbackReranker: zero-dependency fallback using BM25 scores
- get_reranker(): factory with env var override and auto-degrade
"""

import os
from abc import ABC, abstractmethod
from backend.models.state import RetrievedChunk
from backend.utils.logger import logger


class RerankerLoadError(Exception):
    """Raised when a reranker model fails to load (e.g. download failure)."""


class Reranker(ABC):
    """Abstract reranker interface."""

    @abstractmethod
    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Re-rank passages by relevance to query. Returns passages sorted best-first."""


class BM25FallbackReranker(Reranker):
    """Zero-dependency fallback: sort by existing BM25 score descending."""

    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return sorted(
            passages,
            key=lambda c: c.scores.get("bm25", 0),
            reverse=True,
        )


class FlashRankReranker(Reranker):
    """Cross-encoder reranker using the flashrank library.

    Model is downloaded lazily on first ``rerank()`` call so service startup
    is never blocked. If loading fails the factory function degrades to BM25.
    """

    def __init__(self, model: str = "ms-marco-MiniLM-L-12-v2"):
        self.model_name = model
        self._ranker = None  # lazy — loaded on first rerank()

    def _ensure_loaded(self) -> None:
        if self._ranker is None:
            try:
                from flashrank import Ranker
                self._ranker = Ranker(model_name=self.model_name)
            except Exception as e:
                raise RerankerLoadError(
                    f"FlashRank model '{self.model_name}' failed to load: {e}"
                ) from e

    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not passages:
            return []

        self._ensure_loaded()

        # Build flashrank input
        rank_input = [
            {"id": p.chunk_id, "text": p.text}
            for p in passages
        ]

        try:
            scored = self._ranker.rerank(query, rank_input)
        except Exception:
            logger.warning("FlashRank rerank failed, returning original order")
            return passages

        # Map scores back to RetrievedChunk
        score_map: dict[str, float] = {}
        for item in scored:
            score_map[item["id"]] = float(item.get("score", 0))

        for p in passages:
            p.scores["rerank"] = score_map.get(p.chunk_id, 0)

        passages.sort(key=lambda c: c.scores.get("rerank", 0), reverse=True)
        return passages


def get_reranker(name: str | None = None) -> Reranker:
    """Factory: return a reranker instance.

    Resolution order:
    1. Explicit ``name`` argument (``"flashrank"`` or ``"bm25"``)
    2. ``RERANKER_BACKEND`` environment variable (default ``"flashrank"``)
    3. If FlashRank requested but unavailable, auto-degrade to BM25

    Returns:
        Reranker instance.
    """
    backend = name or os.getenv("RERANKER_BACKEND", "flashrank")

    if backend == "flashrank":
        try:
            return FlashRankReranker()
        except RerankerLoadError:
            logger.warning(
                "FlashRank unavailable, falling back to BM25 reranker. "
                "Set RERANKER_BACKEND=bm25 to suppress this warning."
            )
            return BM25FallbackReranker()

    return BM25FallbackReranker()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd paper-reading-agent && python -m pytest tests/test_reranker.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/reranker.py tests/test_reranker.py
git commit -m "feat(backend): add pluggable reranker module — FlashRank with lazy loading + BM25 fallback"
```

---

### Task 2: Integrate Reranker into HybridRetriever

**Files:**
- Modify: `backend/tools/retriever.py:7-9` (import), `:60-86` (retrieve method)
- Modify: `tests/test_retriever.py` (add reranker integration test)

**Interfaces:**
- Consumes: `backend.tools.reranker.Reranker`, `backend.tools.reranker.get_reranker`
- Produces: `HybridRetriever.__init__` gains `reranker: Reranker | None = None` parameter
- `retrieve()` uses `self.reranker.rerank(query, merged)` instead of `merged.sort(key=...)`

- [ ] **Step 1: Write failing integration test**

```python
# Append to tests/test_retriever.py

def test_retriever_uses_reranker(retriever):
    """retrieve() calls reranker.rerank() when a reranker is provided."""
    from backend.tools.reranker import BM25FallbackReranker
    # Inject reranker
    fake_reranker = BM25FallbackReranker()
    retriever.reranker = fake_reranker
    retriever.bm25.get_scores.return_value = [0.9, 0.5, 0.1]
    retriever._dense_search = lambda q, k: []
    results = retriever.retrieve("query", top_k=3)
    assert len(results) == 3
    # BM25 fallback sorts by BM25 score descending
    assert results[0].scores["bm25"] > results[-1].scores["bm25"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd paper-reading-agent && python -m pytest tests/test_retriever.py::test_retriever_uses_reranker -v`
Expected: FAIL — `AttributeError: 'HybridRetriever' object has no attribute 'reranker'`

- [ ] **Step 3: Modify `backend/tools/retriever.py`**

Change the import section (lines 1-6):

```python
import uuid
from backend.models.paper import Paper
from backend.models.state import RetrievedChunk
from backend.utils.text_splitter import split_text
from backend.utils.logger import logger
from backend.tools.reranker import Reranker, get_reranker
```

Change `__init__` signature (line 9):

```python
class HybridRetriever:
    """Hybrid RAG: BM25 + ChromaDB with pluggable reranker."""
    def __init__(self, paper: Paper, embedding_model: str = "auto", reranker: Reranker | None = None):
        self.paper = paper
        self.reranker = reranker if reranker is not None else get_reranker()
        self.chunks = self._build_chunks()
        self._build_indices(embedding_model)
```

Change `retrieve()` method — replace lines 74-76 (the sort + slice after merge):

```python
        # Phase 3: rerank merged results with pluggable reranker
        merged = self.reranker.rerank(query, merged)
        results = merged[:top_k]

        # Low-score detection after rerank
        avg_score = (
            sum(c.scores.get("rerank", c.scores.get("bm25", 0)) for c in results) / len(results)
            if results else 0
        )
        if avg_score < 0.3:
            logger.warning(f"Low average relevance: {avg_score:.2f}, expanding to top-10")
            results = merged[:10]

        for c in results:
            c.source = c.source or "rerank"
```

Remove the old comment line 74 (`# Phase 1: sort by BM25 score (FlashRank replaces this in Phase 3)`) and the old sort line (line 75: `merged.sort(key=lambda c: c.scores.get("bm25", 0), reverse=True)`).

- [ ] **Step 4: Run all retriever tests**

Run: `cd paper-reading-agent && python -m pytest tests/test_retriever.py -v`
Expected: 6 tests PASS (5 existing + 1 new)

- [ ] **Step 5: Run reranker tests too**

Run: `cd paper-reading-agent && python -m pytest tests/test_reranker.py tests/test_retriever.py -v`
Expected: 13 tests PASS (7 reranker + 6 retriever)

- [ ] **Step 6: Commit**

```bash
git add backend/tools/retriever.py tests/test_retriever.py
git commit -m "feat(backend): integrate pluggable reranker into HybridRetriever"
```

---

### Task 3: SSE Protocol Update — init event + session_id + followup_questions

**Files:**
- Modify: `backend/models/state.py:55` (AgentState — add session_id + followup_questions)
- Modify: `backend/agents/supervisor.py:99-261` (stream_graph — init event, session creation, done payload)
- Modify: `backend/agents/reviewer.py:72-75` (output_node — copy followup_questions to state)
- Create: `tests/test_sse_protocol.py`

**Interfaces:**
- Consumes: `backend.storage.session_store.SessionStore` (create_session, add_message)
- Produces:
  - `AgentState` gains `session_id: str = ""` and `followup_questions: list[str] = field(default_factory=list)`
  - `stream_graph` emits `event: init` with `{thread_id, session_id}` at Segment 1 start
  - `_build_done_payload` includes `session_id`, full `quality_score` (4 fields), `followup_questions`, full `evidence_list`
  - `output_node` copies `state.observation["followup_questions"]` → `state.followup_questions`

- [ ] **Step 1: Write failing test**

```python
# tests/test_sse_protocol.py
import json
import pytest


class TestDonePayload:
    def test_includes_session_id_and_followup_questions(self):
        """_build_done_payload includes session_id and followup_questions fields."""
        from backend.models.state import AgentState, QualityScore, Evidence, EvidenceLevel
        from backend.agents.supervisor import _build_done_payload

        state = AgentState(
            session_id="sess-001",
            answer="The answer",
            quality_score=QualityScore(relevance=3, consistency=3, completeness=2),
            evidence_list=[
                Evidence(
                    evidence_id="ev1", claim="claim1", level=EvidenceLevel.R0,
                    page=4, quote="quote text", section_heading="Results",
                    confidence=0.95,
                )
            ],
            trace=["reader", "classify", "planner"],
            followup_questions=["What about X?", "How does Y compare?"],
        )

        payload_str = _build_done_payload(state)
        # Strip SSE prefix
        assert payload_str.startswith("event: done\n")
        json_str = payload_str.split("data: ", 1)[1]
        payload = json.loads(json_str)

        assert payload["event"] == "done"
        assert payload["session_id"] == "sess-001"
        assert payload["answer"] == "The answer"
        assert payload["quality_score"]["relevance"] == 3
        assert payload["quality_score"]["consistency"] == 3
        assert payload["quality_score"]["completeness"] == 2
        assert payload["quality_score"]["total"] == 8
        assert payload["followup_questions"] == ["What about X?", "How does Y compare?"]
        assert len(payload["evidence_list"]) == 1
        assert payload["evidence_list"][0]["quote"] == "quote text"


class TestInitEvent:
    def test_stream_graph_emits_init_on_segment1(self):
        """Segment 1 of stream_graph emits an init event first."""
        # This tests the SSE event structure — we verify the event format
        # without actually running the full graph (which requires LLM calls).
        sse_line = 'event: init\ndata: {"event": "init", "thread_id": "tid-1", "session_id": "sess-1"}\n\n'
        assert 'event: init' in sse_line
        data_part = sse_line.split("data: ")[1].rstrip()
        payload = json.loads(data_part)
        assert payload["event"] == "init"
        assert payload["thread_id"] == "tid-1"
        assert payload["session_id"] == "sess-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd paper-reading-agent && python -m pytest tests/test_sse_protocol.py -v`
Expected: `TestDonePayload` FAIL — `session_id` not in done payload or `followup_questions` missing

- [ ] **Step 3: Add fields to `backend/models/state.py`**

In `AgentState` dataclass (after line 30, before `user_query`):

```python
    session_id: str = ""
```

After `evidence_list` (line 69):

```python
    followup_questions: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Modify `output_node` in `backend/agents/reviewer.py`**

Replace the `output_node` function (lines 72-75):

```python
async def output_node(state: AgentState) -> AgentState:
    """Format final output — promote followup_questions from observation to state."""
    state.trace.append("output")
    if state.observation and "followup_questions" in state.observation:
        state.followup_questions = state.observation["followup_questions"]
    return state
```

- [ ] **Step 5: Modify `stream_graph` in `backend/agents/supervisor.py`**

Add import at top (after line 16):

```python
from backend.storage.session_store import SessionStore
```

In `stream_graph()`, after generating `tid` (line 119), add session creation and init event emission. Replace the initial section before the Segment 1 `astream_events` loop:

```python
    tid = thread_id or str(uuid.uuid4())

    # Create session for this query (Segment 1 only — Segment 2 reuses)
    session_store = SessionStore()
    session_id = thread_id  # reuse thread_id as session_id for Segment 2
    if not thread_id:
        session_id = await session_store.create_session(paper_id)
        # Emit init event with both thread_id and session_id
        init_payload = {
            "event": "init",
            "thread_id": tid,
            "session_id": session_id,
        }
        yield f"event: init\ndata: {json.dumps(init_payload)}\n\n"

    config_dict = {"configurable": {"thread_id": tid}}
```

- [ ] **Step 6: Update `_build_done_payload` in `backend/agents/supervisor.py`**

Replace the function (lines 239-261) with:

```python
def _build_done_payload(state: AgentState) -> str:
    """Build the final SSE done event from AgentState."""
    evidence_summary = []
    for e in state.evidence_list:
        evidence_summary.append({
            "evidence_id": e.evidence_id,
            "level": e.level.value if e.level else "R2",
            "claim": e.claim,
            "sentence_index": e.sentence_index,
            "char_start": e.char_start,
            "char_end": e.char_end,
            "page": e.page,
            "quote": e.quote,
            "section_heading": e.section_heading,
            "source_title": e.source_title,
            "source_url": e.source_url,
            "source_venue": e.source_venue,
            "source_year": e.source_year,
            "reasoning": e.reasoning,
            "based_on_evidence_ids": e.based_on_evidence_ids,
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
        "followup_questions": state.followup_questions,
    }
    return f"event: done\ndata: {json.dumps(payload)}\n\n"
```

- [ ] **Step 7: Record messages to session store in `stream_graph`**

In `stream_graph()`, after the done event is yielded (Segment 1 non-HITL path and Segment 2 path), record messages. Add this helper and insert calls:

```python
async def _record_messages(session_id: str, user_query: str, state: AgentState) -> None:
    """Persist user query + assistant response to session store."""
    store = SessionStore()
    await store.add_message(session_id, "user", user_query, {})
    meta = {
        "evidence_list": [
            {
                "evidence_id": e.evidence_id,
                "level": e.level.value if e.level else "R2",
                "claim": e.claim,
                "sentence_index": e.sentence_index,
                "char_start": e.char_start,
                "char_end": e.char_end,
                "page": e.page,
                "quote": e.quote,
                "section_heading": e.section_heading,
                "source_title": e.source_title,
                "source_url": e.source_url,
                "source_venue": e.source_venue,
                "source_year": e.source_year,
                "reasoning": e.reasoning,
                "based_on_evidence_ids": e.based_on_evidence_ids,
                "confidence": e.confidence,
            }
            for e in state.evidence_list
        ],
        "quality_score": {
            "relevance": state.quality_score.relevance if state.quality_score else 0,
            "consistency": state.quality_score.consistency if state.quality_score else 0,
            "completeness": state.quality_score.completeness if state.quality_score else 0,
            "total": state.quality_score.total if state.quality_score else 0,
        },
        "trace": state.trace,
        "followup_questions": state.followup_questions,
    }
    await store.add_message(session_id, "assistant", state.answer, meta)
```

In `stream_graph()`, after the Segment 1 non-HITL path's `_build_done_payload` yield (around line 199), add:

```python
                if kind == "on_chain_end" and node_name == "output":
                    output = data.get("output", {})
                    if isinstance(output, dict):
                        state = AgentState(**{k: v for k, v in output.items() if k in AgentState.__dataclass_fields__})
                    else:
                        state = output if isinstance(output, AgentState) else AgentState()
                    state.session_id = session_id
                    await _record_messages(session_id, query, state)
                    yield _build_done_payload(state)
                    return
```

And for Segment 2, similarly after the output node (around line 193):

```python
        if kind == "on_chain_end" and node_name == "output":
            output = data.get("output", {})
            if isinstance(output, dict):
                state = AgentState(**{k: v for k, v in output.items() if k in AgentState.__dataclass_fields__})
            else:
                state = output if isinstance(output, AgentState) else AgentState()
            state.session_id = session_id
            await _record_messages(session_id, query, state)
            yield _build_done_payload(state)
            return
```

- [ ] **Step 8: Run tests**

Run: `cd paper-reading-agent && python -m pytest tests/test_sse_protocol.py -v`
Expected: 2 tests PASS

- [ ] **Step 9: Run full backend test suite**

Run: `cd paper-reading-agent && python -m pytest tests/ -v --tb=short`
Expected: all existing 35 tests + 2 new = 37 PASS

- [ ] **Step 10: Commit**

```bash
git add backend/models/state.py backend/agents/supervisor.py backend/agents/reviewer.py tests/test_sse_protocol.py
git commit -m "feat(backend): add SSE init event with session_id, expand done payload with followup_questions and full quality_score"
```

---

### Task 4: Conversation Export API

**Files:**
- Modify: `backend/app.py` (add `/api/sessions/{session_id}/export` endpoint)
- Modify: `backend/storage/session_store.py` (add `get_session_with_paper` method)
- Create: `tests/test_export_api.py`

**Interfaces:**
- Consumes: `SessionStore.get_session()`, `SessionStore.get_session_with_paper()` (new), `PaperStore.get_paper()`
- Produces:
  - `GET /api/sessions/{session_id}/export?format=md` → `StreamingResponse` with `Content-Type: text/markdown; charset=utf-8`
  - `GET /api/sessions/{session_id}/export?format=json` → `StreamingResponse` with `Content-Type: application/json; charset=utf-8`
  - Both set `Content-Disposition: attachment; filename="session-{slug}-{date}.{ext}"`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_export_api.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_session_store():
    """Mock SessionStore with a complete session."""
    session_data = {
        "session_id": "sess-001",
        "paper_id": "paper-001",
        "created_at": "2026-06-18 14:30:00",
        "updated_at": "2026-06-18 14:31:00",
        "messages": [
            {"role": "user", "content": "What is the method?", "meta": {}},
            {
                "role": "assistant",
                "content": "The method uses transformers.",
                "meta": {
                    "evidence_list": [
                        {
                            "evidence_id": "ev1", "level": "R0", "claim": "claim",
                            "page": 4, "quote": "We use transformers.",
                            "section_heading": "Method", "confidence": 0.95,
                            "sentence_index": None, "char_start": None, "char_end": None,
                            "source_title": None, "source_url": None,
                            "source_venue": None, "source_year": None,
                            "reasoning": None, "based_on_evidence_ids": [],
                        }
                    ],
                    "quality_score": {"relevance": 3, "consistency": 3, "completeness": 2, "total": 8},
                    "trace": ["reader", "classify", "planner"],
                    "followup_questions": ["Q1?", "Q2?"],
                },
            },
        ],
    }
    return session_data


class TestExportMarkdown:
    def test_returns_markdown_content_type(self, mock_session_store):
        from backend.app import app
        from backend.storage.session_store import SessionStore
        from backend.storage.paper_store import PaperStore
        from backend.models.paper import Paper

        client = TestClient(app)

        async def mock_get_session(sid):
            return mock_session_store if sid == "sess-001" else None

        async def mock_get_paper(pid):
            return Paper(
                paper_id="paper-001", title="Test Paper", file_path="/tmp/test.pdf"
            )

        with patch.object(SessionStore, "get_session", mock_get_session):
            with patch.object(PaperStore, "get_paper", mock_get_paper):
                response = client.get("/api/sessions/sess-001/export?format=md")

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        # Check markdown content
        body = response.text
        assert "# Session:" in body
        assert "## Q: What is the method?" in body
        assert "**Answer:** The method uses transformers." in body
        assert "[R0]" in body
        assert "**Quality:** 8/10" in body
        assert "## Suggested Follow-ups" in body
        assert "Q1?" in body

    def test_session_not_found_returns_404(self):
        from backend.app import app
        from backend.storage.session_store import SessionStore

        client = TestClient(app)

        async def mock_none(sid):
            return None

        with patch.object(SessionStore, "get_session", mock_none):
            response = client.get("/api/sessions/nonexistent/export?format=md")

        assert response.status_code == 404


class TestExportJSON:
    def test_returns_json_content_type(self, mock_session_store):
        from backend.app import app
        from backend.storage.session_store import SessionStore
        from backend.storage.paper_store import PaperStore
        from backend.models.paper import Paper

        client = TestClient(app)

        async def mock_get_session(sid):
            return mock_session_store if sid == "sess-001" else None

        async def mock_get_paper(pid):
            return Paper(
                paper_id="paper-001", title="Test Paper", file_path="/tmp/test.pdf"
            )

        with patch.object(SessionStore, "get_session", mock_get_session):
            with patch.object(PaperStore, "get_paper", mock_get_paper):
                response = client.get("/api/sessions/sess-001/export?format=json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        body = response.json()
        assert body["session_id"] == "sess-001"
        assert body["paper_title"] == "Test Paper"
        assert "exported_at" in body
        assert len(body["messages"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd paper-reading-agent && python -m pytest tests/test_export_api.py -v`
Expected: FAIL — 404 on `/api/sessions/sess-001/export`

- [ ] **Step 3: Add `get_session_with_paper` to `backend/storage/session_store.py`**

```python
    async def get_session_with_paper(self, session_id: str) -> dict | None:
        """Get session with paper title joined."""
        conn = await db.get_db()
        try:
            async with conn.execute(
                """SELECT s.*, p.title as paper_title
                   FROM sessions s
                   JOIN papers p ON s.paper_id = p.paper_id
                   WHERE s.session_id = ?""",
                (session_id,),
            ) as cursor:
                session_row = await cursor.fetchone()
                if not session_row:
                    return None

            messages = []
            async with conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY message_id",
                (session_id,),
            ) as cursor:
                async for row in cursor:
                    messages.append({
                        "role": row["role"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"]) if row["meta"] else {},
                        "created_at": row["created_at"],
                    })

            return {
                "session_id": session_row["session_id"],
                "paper_id": session_row["paper_id"],
                "paper_title": session_row["paper_title"],
                "created_at": session_row["created_at"],
                "updated_at": session_row["updated_at"],
                "messages": messages,
            }
        finally:
            await conn.close()
```

Note: `json` is already imported at the top of `session_store.py`.

- [ ] **Step 4: Add export endpoint to `backend/app.py`**

Add imports at top:

```python
import re
from datetime import datetime, timezone
from fastapi.responses import Response
from backend.storage.session_store import SessionStore
```

Add endpoint after the existing `/api/pdf/{paper_id}/text` endpoint:

```python
@app.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str, format: str = Query(default="md", regex="^(md|json)$")):
    """Export a session conversation as Markdown or JSON.

    Args:
        session_id: Session identifier (from init event).
        format: ``md`` for Markdown, ``json`` for structured JSON.
    """
    store = SessionStore()
    session = await store.get_session_with_paper(session_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    if format == "json":
        return _export_json(session)
    return _export_markdown(session)


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a safe filename slug."""
    # Keep alphanumeric, Chinese chars, hyphens, underscores
    slug = re.sub(r'[^\w一-鿿-]', '-', text)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:max_len]


def _export_json(session: dict) -> Response:
    data = {
        "session_id": session["session_id"],
        "paper_id": session["paper_id"],
        "paper_title": session["paper_title"],
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "messages": [
            {
                "role": msg["role"],
                "content": msg["content"],
                "evidence_list": msg.get("meta", {}).get("evidence_list", []),
                "quality_score": msg.get("meta", {}).get("quality_score"),
                "trace": msg.get("meta", {}).get("trace", []),
                "followup_questions": msg.get("meta", {}).get("followup_questions", []),
                "timestamp": msg.get("created_at", ""),
            }
            for msg in session["messages"]
        ],
    }
    title_slug = _slugify(session.get("paper_title", "export"))
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"session-{title_slug}-{date_str}.json"

    return Response(
        content=json.dumps(data, indent=2, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export_markdown(session: dict) -> Response:
    lines = []
    lines.append(f"# Session: {session['session_id']}")
    lines.append(
        f"Date: {session.get('created_at', '')} | "
        f"Paper: {session.get('paper_title', 'Unknown')}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    for msg in session["messages"]:
        if msg["role"] == "user":
            lines.append(f"## Q: {msg['content']}")
            lines.append("")
        else:
            lines.append(f"**Answer:** {msg['content']}")
            lines.append("")

            meta = msg.get("meta", {})
            evidence_list = meta.get("evidence_list", [])
            if evidence_list:
                lines.append(f"**Evidence ({len(evidence_list)} items):**")
                for ev in evidence_list:
                    level = ev.get("level", "R2")
                    claim = ev.get("claim", "")
                    details = []
                    if level == "R0":
                        page = ev.get("page")
                        section = ev.get("section_heading")
                        quote = ev.get("quote", "")
                        if page:
                            details.append(f"Page {page}")
                        if section:
                            details.append(f"§{section}")
                        if quote:
                            details.append(f'"{quote}"')
                    elif level == "R1":
                        title = ev.get("source_title")
                        url = ev.get("source_url")
                        if title:
                            details.append(f"Source: {title}")
                        if url:
                            details.append(url)
                    elif level == "R2":
                        based_on = ev.get("based_on_evidence_ids", [])
                        conf = ev.get("confidence", 0)
                        if based_on:
                            details.append(f"Based on {', '.join(based_on)}")
                        details.append(f"confidence: {conf:.0%}")

                    detail_str = " · ".join(details) if details else ""
                    prefix = f"  - [{level}] \"{claim}\""
                    if detail_str:
                        prefix += f" ({detail_str})"
                    lines.append(prefix)
                lines.append("")

            quality = meta.get("quality_score")
            if quality:
                lines.append(
                    f"**Quality:** {quality.get('total', '?')}/10 "
                    f"(Relevance: {quality.get('relevance', '?')}/3, "
                    f"Consistency: {quality.get('consistency', '?')}/4, "
                    f"Completeness: {quality.get('completeness', '?')}/3)"
                )
                lines.append("")

            lines.append("---")
            lines.append("")

    followups = []
    for msg in session["messages"]:
        if msg["role"] == "assistant":
            fu = msg.get("meta", {}).get("followup_questions", [])
            followups.extend(fu)
    if followups:
        lines.append("## Suggested Follow-ups")
        for q in followups:
            lines.append(f"- {q}")
        lines.append("")

    title_slug = _slugify(session.get("paper_title", "export"))
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"session-{title_slug}-{date_str}.md"

    return Response(
        content="\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 5: Run export tests**

Run: `cd paper-reading-agent && python -m pytest tests/test_export_api.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `cd paper-reading-agent && python -m pytest tests/ -v --tb=short`
Expected: all 48 tests PASS (35 Phase1/2 + 7 reranker + 1 retriever + 2 SSE + 3 export)

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/storage/session_store.py tests/test_export_api.py
git commit -m "feat(backend): add conversation export API — Markdown and JSON with evidence, quality, followups"
```

---

### Task 5: Frontend — Export Button + currentSessionId

**Files:**
- Modify: `frontend/src/store/chatStore.ts` (add `currentSessionId` + `setSessionId`)
- Modify: `frontend/src/hooks/useSSE.ts` (parse init event → set session_id)
- Modify: `frontend/src/components/ChatPanel/ChatPanel.tsx` (add export button, apply import updates)
- Modify: `frontend/src/components/ChatPanel/ChatPanel.module.css` (add export button styles)
- Modify: `frontend/src/types/index.ts` (InitEvent add session_id)
- Create: `tests/frontend/ExportButton.test.tsx`

**Interfaces:**
- Consumes: `chatStore.currentSessionId`, `appStore.paper`, `InitEvent.session_id`
- Produces: `<ExportButton />` rendered in ChatPanel when status=complete, clicking downloads via `/api/sessions/{id}/export`

- [ ] **Step 1: Write failing test**

```typescript
// tests/frontend/ExportButton.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useChatStore } from '../../src/store/chatStore'
import { useAppStore } from '../../src/store/appStore'

// Mock fetch for export
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  text: () => Promise.resolve('# Session: test'),
  headers: new Headers({ 'content-type': 'text/markdown' }),
})

import ChatPanel from '../../src/components/ChatPanel/ChatPanel'

describe('Export button', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
    useAppStore.setState({
      paper: { paper_id: 'p1', title: 'Test Paper', file_path: '', parsed_at: null },
      sessions: [],
      currentSession: null,
      layout: 'dual',
      sidebarOpen: false,
    })
    vi.clearAllMocks()
  })

  it('shows export button when status is complete and sessionId is set', () => {
    useChatStore.setState({ status: 'complete', currentSessionId: 'sess-001' })
    const screen = render(<ChatPanel />)
    const btn = screen.container.querySelector('[data-testid="export-btn"]')
    expect(btn).toBeTruthy()
  })

  it('hides export button when status is not complete', () => {
    useChatStore.setState({ status: 'streaming', currentSessionId: 'sess-001' })
    const screen = render(<ChatPanel />)
    const btn = screen.container.querySelector('[data-testid="export-btn"]')
    expect(btn).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/ExportButton.test.tsx`
Expected: FAIL — no export button rendered

- [ ] **Step 3: Update `frontend/src/types/index.ts` — InitEvent**

Change `InitEvent` (line ~224):

```typescript
export interface InitEvent {
  event: 'init'
  thread_id: string
  session_id: string
}
```

- [ ] **Step 4: Update `frontend/src/store/chatStore.ts` — add currentSessionId**

Add to `ChatState` interface (after `threadId` line):

```typescript
  currentSessionId: string | null
  setSessionId: (id: string) => void
```

Add to initial state:

```typescript
  currentSessionId: null,
```

Add setter:

```typescript
  setSessionId: (id) => set({ currentSessionId: id }),
```

Add to `reset()`:

```typescript
        currentSessionId: null,
```

- [ ] **Step 5: Update `frontend/src/hooks/useSSE.ts` — parse init session_id**

In the `es.addEventListener('init', ...)` handler, after `store.getState().setThreadId(data.thread_id)`:

```typescript
      if (data.session_id) {
        store.getState().setSessionId(data.session_id)
      }
```

- [ ] **Step 6: Update `frontend/src/components/ChatPanel/ChatPanel.tsx`**

Add export button after StepIndicator, before MessageList. Full updated component:

```typescript
import { useCallback } from 'react'
import StepIndicator from './StepIndicator'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import PlanApprovalBanner from './PlanApprovalBanner'
import { useChatStore } from '@/store/chatStore'
import { useAppStore } from '@/store/appStore'
import { useSSE } from '@/hooks/useSSE'
import { useApproval } from '@/hooks/useApproval'
import styles from './ChatPanel.module.css'

function slugify(text: string, maxLen: number = 50): string {
  return text
    .replace(/[^\w一-鿿-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, maxLen)
}

export default function ChatPanel() {
  const { start } = useSSE()
  const { approve, reject } = useApproval()
  const status = useChatStore((s) => s.status)
  const hitlPlan = useChatStore((s) => s.hitlPlan)
  const currentSessionId = useChatStore((s) => s.currentSessionId)
  const paper = useAppStore((s) => s.paper)

  const isStreaming = status === 'connecting' || status === 'streaming'
  const isAwaitingApproval = status === 'awaiting_approval'
  const showExport = status === 'complete' && currentSessionId

  const handleSend = useCallback(
    (query: string) => {
      if (!paper) return
      start({ paper_id: paper.paper_id, query })
      const store = useChatStore.getState()
      store.addMessage({
        id: `msg-${Date.now()}`,
        role: 'user',
        content: query,
      })
    },
    [paper, start],
  )

  const handleApprove = useCallback(() => {
    const state = useChatStore.getState()
    if (state.threadId) {
      approve(state.threadId)
    }
  }, [approve])

  const handleReject = useCallback(() => {
    const state = useChatStore.getState()
    if (state.threadId) {
      reject(state.threadId)
    }
  }, [reject])

  const handleEdit = useCallback(
    (feedback: string) => {
      const state = useChatStore.getState()
      if (state.threadId) {
        approve(state.threadId, feedback)
      }
    },
    [approve],
  )

  const handleExport = useCallback(
    async (format: 'md' | 'json') => {
      if (!currentSessionId) return
      const res = await fetch(`/api/sessions/${currentSessionId}/export?format=${format}`)
      if (!res.ok) return
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const titleSlug = slugify(paper?.title || 'export')
      const date = new Date().toISOString().slice(0, 10)
      a.download = `session-${titleSlug}-${date}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    },
    [currentSessionId, paper?.title],
  )

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <StepIndicator />
        {showExport && (
          <div className={styles.exportGroup}>
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
          </div>
        )}
      </div>
      <MessageList />
      {isAwaitingApproval && hitlPlan && (
        <PlanApprovalBanner
          plan={hitlPlan}
          onApprove={handleApprove}
          onReject={handleReject}
          onEdit={handleEdit}
        />
      )}
      <ChatInput onSend={handleSend} disabled={isStreaming || isAwaitingApproval} />
    </div>
  )
}
```

- [ ] **Step 7: Update `frontend/src/components/ChatPanel/ChatPanel.module.css`**

Add styles:

```css
.panelHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.exportGroup {
  display: flex;
  gap: 4px;
}

.exportBtn {
  padding: 2px 8px;
  font-size: 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #f9fafb;
  cursor: pointer;
  color: #374151;
}

.exportBtn:hover {
  background: #e5e7eb;
}
```

- [ ] **Step 8: Run tests**

Run: `cd frontend && npx vitest run tests/frontend/ExportButton.test.tsx`
Expected: 2 tests PASS

Run: `cd frontend && npx vitest run`
Expected: all 42 tests PASS (40 existing + 2 new)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/store/chatStore.ts frontend/src/hooks/useSSE.ts frontend/src/components/ChatPanel/ChatPanel.tsx frontend/src/components/ChatPanel/ChatPanel.module.css frontend/src/types/index.ts tests/frontend/ExportButton.test.tsx
git commit -m "feat(frontend): add session export button — Markdown and JSON download from ChatPanel"
```

---

### Task 6: Backend — Preferences API

**Files:**
- Modify: `backend/app.py` (add `GET/PUT /api/preferences`)
- Create: `tests/test_preferences_api.py`

**Interfaces:**
- Consumes: existing `preferences` table (key TEXT PRIMARY KEY, value TEXT)
- Produces:
  - `GET /api/preferences` → `{ "reranker": "flashrank", "top_k": 5, "language": "auto", "embedding_model": "auto" }`
  - `PUT /api/preferences` → `{ "status": "ok" }` or `400` for invalid keys/values

- [ ] **Step 1: Write failing tests**

```python
# tests/test_preferences_api.py
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

ALLOWED_KEYS = {"reranker", "top_k", "language", "embedding_model"}
DEFAULTS = {"reranker": "flashrank", "top_k": 5, "language": "auto", "embedding_model": "auto"}


@pytest.fixture
def client():
    from backend.app import app
    return TestClient(app)


class TestGetPreferences:
    def test_returns_defaults_when_empty(self, client):
        """GET returns default values when no preferences are stored."""
        # Mock db.get_db to return a connection with empty preferences
        import aiosqlite

        async def mock_get_db():
            conn = await aiosqlite.connect(":memory:")
            conn.row_factory = aiosqlite.Row
            await conn.execute("CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')")
            return conn

        with patch("backend.app.db.get_db", mock_get_db):
            response = client.get("/api/preferences")
        assert response.status_code == 200
        data = response.json()
        assert data["reranker"] == "flashrank"
        assert data["top_k"] == 5
        assert data["language"] == "auto"
        assert data["embedding_model"] == "auto"


class TestPutPreferences:
    def test_valid_update_returns_ok(self, client):
        import aiosqlite

        async def mock_get_db():
            conn = await aiosqlite.connect(":memory:")
            conn.row_factory = aiosqlite.Row
            await conn.execute("CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')")
            return conn

        with patch("backend.app.db.get_db", mock_get_db):
            response = client.put(
                "/api/preferences",
                json={"reranker": "bm25", "top_k": 10},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_invalid_key_returns_400(self, client):
        response = client.put(
            "/api/preferences",
            json={"invalid_key": "value"},
        )
        assert response.status_code == 400

    def test_invalid_top_k_range_returns_400(self, client):
        response = client.put(
            "/api/preferences",
            json={"top_k": 100},
        )
        assert response.status_code == 400

    def test_invalid_reranker_value_returns_400(self, client):
        response = client.put(
            "/api/preferences",
            json={"reranker": "unknown_reranker"},
        )
        assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd paper-reading-agent && python -m pytest tests/test_preferences_api.py -v`
Expected: FAIL — 404 or 405 on `/api/preferences`

- [ ] **Step 3: Add preferences endpoints to `backend/app.py`**

Add import at top:

```python
from backend.storage.database import db
```

Add endpoints before the final lines of the file:

```python
# ---- Preferences ----

PREFERENCE_WHITELIST = {
    "reranker":    {"default": "flashrank", "type": str, "values": {"flashrank", "bm25"}},
    "top_k":       {"default": "5",         "type": int, "min": 1, "max": 20},
    "language":    {"default": "auto",      "type": str, "values": {"en", "zh", "auto"}},
    "embedding_model": {"default": "auto",  "type": str},
}

PREFERENCE_DEFAULTS = {k: v["default"] for k, v in PREFERENCE_WHITELIST.items()}


def _coerce_preference(key: str, raw_value: str) -> int | str:
    """Convert stored string to native type based on whitelist."""
    spec = PREFERENCE_WHITELIST[key]
    if spec["type"] == int:
        return int(raw_value)
    return raw_value


def _validate_preference(key: str, value) -> str | None:
    """Validate and convert a preference value. Returns error message or None."""
    spec = PREFERENCE_WHITELIST.get(key)
    if spec is None:
        return f"Unknown preference key: {key}"

    if spec["type"] == int:
        try:
            int_val = int(value)
        except (ValueError, TypeError):
            return f"{key} must be an integer"
        if "min" in spec and int_val < spec["min"]:
            return f"{key} must be >= {spec['min']}"
        if "max" in spec and int_val > spec["max"]:
            return f"{key} must be <= {spec['max']}"
    else:
        str_val = str(value)
        if "values" in spec and str_val not in spec["values"]:
            allowed = ", ".join(spec["values"])
            return f"{key} must be one of: {allowed}"

    return None


@app.get("/api/preferences")
async def get_preferences():
    """Get all agent preferences with defaults for unset keys."""
    conn = await db.get_db()
    try:
        result = dict(PREFERENCE_DEFAULTS)
        async with conn.execute("SELECT key, value FROM preferences") as cursor:
            async for row in cursor:
                if row["key"] in PREFERENCE_WHITELIST:
                    result[row["key"]] = _coerce_preference(row["key"], row["value"])
        return result
    finally:
        await conn.close()


@app.put("/api/preferences")
async def put_preferences(request: Request):
    """Update agent preferences. Only whitelisted keys accepted."""
    body = await request.json()

    # Validate all keys and values first
    for key, value in body.items():
        error = _validate_preference(key, value)
        if error:
            return JSONResponse({"error": error}, status_code=400)

    # Upsert into database
    conn = await db.get_db()
    try:
        for key, value in body.items():
            # Store as string
            await conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        await conn.commit()
        return {"status": "ok"}
    finally:
        await conn.close()
```

- [ ] **Step 4: Run tests**

Run: `cd paper-reading-agent && python -m pytest tests/test_preferences_api.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Run full backend test suite**

Run: `cd paper-reading-agent && python -m pytest tests/ -v --tb=short`
Expected: all 53 tests PASS (35 Phase1/2 + 7 reranker + 1 retriever + 2 SSE + 3 export + 5 preferences)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_preferences_api.py
git commit -m "feat(backend): add preferences API — GET/PUT with whitelist validation and type coercion"
```

---

### Task 7: Frontend — zustand persist for UI Preferences

**Files:**
- Modify: `frontend/src/store/appStore.ts` (wrap with persist middleware)

**Interfaces:**
- Consumes: zustand `persist` middleware (built-in)
- Produces: `useAppStore` with localStorage persistence of `layout` and `sidebarOpen`

- [ ] **Step 1: Write failing test**

```typescript
// Append to tests/scaffold.test.ts or create tests/frontend/persist.test.ts

import { describe, it, expect, beforeEach } from 'vitest'

describe('appStore persist', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('persists layout and sidebarOpen to localStorage', () => {
    // Dynamic import to get fresh store
    const { useAppStore } = require('../../src/store/appStore')
    useAppStore.getState().setLayout('chat')
    useAppStore.getState().toggleSidebar()

    const stored = localStorage.getItem('paper-reading-agent-ui')
    expect(stored).toBeTruthy()
    const parsed = JSON.parse(stored!)
    expect(parsed.state.layout).toBe('chat')
    expect(parsed.state.sidebarOpen).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/persist.test.ts`
Expected: FAIL — layout not persisted to localStorage (no persist middleware)

- [ ] **Step 3: Update `frontend/src/store/appStore.ts`**

Replace the entire file:

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Paper, Session } from '@/types'

export type LayoutMode = 'dual' | 'chat' | 'paper'

interface AppState {
  paper: Paper | null
  sessions: Session[]
  currentSession: Session | null
  layout: LayoutMode
  sidebarOpen: boolean

  setPaper: (paper: Paper) => void
  clearPaper: () => void
  setLayout: (layout: LayoutMode) => void
  toggleSidebar: () => void
  addSession: (session: Session) => void
  setCurrentSession: (session: Session) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      paper: null,
      sessions: [],
      currentSession: null,
      layout: 'dual',
      sidebarOpen: false,

      setPaper: (paper) => set({ paper }),
      clearPaper: () => set({ paper: null }),
      setLayout: (layout) => set({ layout }),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
      setCurrentSession: (session) => set({ currentSession: session }),
    }),
    {
      name: 'paper-reading-agent-ui',
      partialize: (state) => ({
        layout: state.layout,
        sidebarOpen: state.sidebarOpen,
      }),
    },
  ),
)
```

- [ ] **Step 4: Run persist test**

Run: `cd frontend && npx vitest run tests/frontend/persist.test.ts`
Expected: PASS

- [ ] **Step 5: Run all frontend tests**

Run: `cd frontend && npx vitest run`
Expected: all PASS (40 existing + 2 export + 1 persist = 43)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/store/appStore.ts tests/frontend/persist.test.ts
git commit -m "feat(frontend): add zustand persist middleware — UI layout and sidebar state survive refreshes"
```

---

### Task 8: Frontend — Settings Panel in Sidebar

**Files:**
- Create: `frontend/src/components/Layout/SettingsPanel.tsx`
- Modify: `frontend/src/components/Layout/Sidebar.tsx` (add SettingsPanel)
- Modify: `frontend/src/components/Layout/Layout.module.css` (add settings styles)
- Modify: `frontend/src/api/client.ts` (add `getPreferences` / `putPreferences`)

**Interfaces:**
- Consumes: `GET /api/preferences`, `PUT /api/preferences` (from Task 6)
- Produces:
  - `SettingsPanel` — expandable panel with form for 4 preference items
  - `api/client.ts` gains `getPreferences()` and `putPreferences(prefs)`

- [ ] **Step 1: Add API client functions**

Append to `frontend/src/api/client.ts`:

```typescript
export interface Preferences {
  reranker: string
  top_k: number
  language: string
  embedding_model: string
}

export async function getPreferences(): Promise<Preferences> {
  const res = await fetch(`${BASE}/preferences`)
  if (!res.ok) throw new Error('Failed to fetch preferences')
  return res.json()
}

export async function putPreferences(prefs: Partial<Preferences>): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/preferences`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prefs),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Update failed' }))
    throw new Error(err.error || 'Failed to update preferences')
  }
  return res.json()
}
```

- [ ] **Step 2: Create `frontend/src/components/Layout/SettingsPanel.tsx`**

```typescript
import { useState, useEffect } from 'react'
import { getPreferences, putPreferences, type Preferences } from '@/api/client'
import styles from './Layout.module.css'

export default function SettingsPanel() {
  const [open, setOpen] = useState(false)
  const [prefs, setPrefs] = useState<Preferences | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (open && !prefs) {
      getPreferences()
        .then(setPrefs)
        .catch(() => setMessage('Failed to load preferences'))
    }
  }, [open, prefs])

  const handleSave = async () => {
    if (!prefs) return
    setSaving(true)
    setMessage('')
    try {
      await putPreferences(prefs)
      setMessage('Saved!')
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Save failed')
    }
    setSaving(false)
  }

  return (
    <div className={styles.settingsPanel}>
      <button
        className={styles.settingsToggle}
        onClick={() => setOpen(!open)}
      >
        {open ? '▼' : '▶'} Settings
      </button>

      {open && prefs && (
        <div className={styles.settingsForm}>
          <label>
            Reranker
            <select
              value={prefs.reranker}
              onChange={(e) => setPrefs({ ...prefs, reranker: e.target.value })}
            >
              <option value="flashrank">FlashRank</option>
              <option value="bm25">BM25</option>
            </select>
          </label>

          <label>
            Top-K Results
            <input
              type="number"
              min={1}
              max={20}
              value={prefs.top_k}
              onChange={(e) => setPrefs({ ...prefs, top_k: Number(e.target.value) })}
            />
          </label>

          <label>
            Language
            <select
              value={prefs.language}
              onChange={(e) => setPrefs({ ...prefs, language: e.target.value })}
            >
              <option value="auto">Auto</option>
              <option value="en">English</option>
              <option value="zh">Chinese</option>
            </select>
          </label>

          <label>
            Embedding Model
            <input
              type="text"
              value={prefs.embedding_model}
              onChange={(e) => setPrefs({ ...prefs, embedding_model: e.target.value })}
            />
          </label>

          <button
            className={styles.settingsSaveBtn}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>

          {message && <span className={styles.settingsMsg}>{message}</span>}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Update `frontend/src/components/Layout/Sidebar.tsx`**

Add SettingsPanel import and render it after SessionHistory:

```typescript
import { useAppStore } from '@/store/appStore'
import LibraryPanel from './LibraryPanel'
import SessionHistory from './SessionHistory'
import SettingsPanel from './SettingsPanel'
import styles from './Layout.module.css'

export default function Sidebar() {
  const sidebarOpen = useAppStore((s) => s.sidebarOpen)
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)

  if (!sidebarOpen) return null

  return (
    <div className={styles.sidebarOverlay} onClick={toggleSidebar}>
      <div className={styles.sidebar} onClick={(e) => e.stopPropagation()}>
        <button className={styles.closeBtn} onClick={toggleSidebar}>×</button>
        <LibraryPanel />
        <SessionHistory />
        <SettingsPanel />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Add settings styles to `frontend/src/components/Layout/Layout.module.css`**

```css
.settingsPanel {
  margin-top: 16px;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
}

.settingsToggle {
  background: none;
  border: none;
  font-size: 0.9rem;
  font-weight: 600;
  color: #555;
  cursor: pointer;
  padding: 4px 0;
}

.settingsForm {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.settingsForm label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.75rem;
  color: #6b7280;
}

.settingsForm select,
.settingsForm input {
  padding: 4px 8px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 0.85rem;
}

.settingsSaveBtn {
  padding: 4px 12px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  margin-top: 4px;
}

.settingsSaveBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.settingsMsg {
  font-size: 0.75rem;
  color: #059669;
}
```

- [ ] **Step 5: Run frontend tests**

Run: `cd frontend && npx vitest run`
Expected: all 43 tests PASS (existing + new persist test)

- [ ] **Step 6: Run backend tests**

Run: `cd paper-reading-agent && python -m pytest tests/ -v --tb=short`
Expected: all 53 tests PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Layout/SettingsPanel.tsx frontend/src/components/Layout/Sidebar.tsx frontend/src/components/Layout/Layout.module.css frontend/src/api/client.ts
git commit -m "feat(frontend): add Settings panel in Sidebar for Agent preferences"
```

---

## Verification

After all 8 tasks, run the full test suite:

```bash
cd paper-reading-agent && python -m pytest tests/ -v --tb=short
cd frontend && npx vitest run
```

Expected: 53 backend tests + 43 frontend tests = **96 tests PASS**
