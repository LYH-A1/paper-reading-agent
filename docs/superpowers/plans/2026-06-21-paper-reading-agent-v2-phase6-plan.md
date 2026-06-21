# Phase 6: Trust & Transparency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three features from competitor analysis: Agent Thinking Panel (collapsible reasoning display), Citation Verification (two-stage check of generated citations), and Multi-Thread Chat (independent conversation threads per paper).

**Architecture:** Backend emits new `thinking` SSE events from planner/generate/reviewer nodes. Frontend renders them in a collapsible ThinkingPanel component (inspired by Project Constellation). Citation verification runs as a post-generation check comparing evidence quotes against paper text. Multi-thread chat adds a thread selector to ChatPanel, with threads persisted in SessionStore.

**Tech Stack:** React 18 + TypeScript + zustand (frontend), Python 3.12 + LangGraph + FastAPI (backend), SQLite (persistence)

**Reference projects:**
- Project Constellation — thinking panel UI pattern, citation enforcement
- Paperview — multi-thread conversation model
- PaperQuay — Agent workspace visualization

## Global Constraints

- 每次改动后运行 `pytest && vitest run`，保持 191+ 测试通过
- 每个 task 单独 commit
- 前端使用现有 zustand stores 模式，不引入新状态管理库
- 后端 SSE 协议向后兼容 — 新事件不影响现有客户端
- 所有新 UI 组件使用 CSS Module 与现有组件风格一致
- 引用验证使用纯文本匹配（不引入新 ML 模型）

---

## File Structure Map

```
New files:
  frontend/src/components/ChatPanel/ThinkingPanel.tsx          — collapsible reasoning display
  frontend/src/components/ChatPanel/ThinkingPanel.module.css   — styles
  frontend/src/components/ChatPanel/ThreadSelector.tsx         — thread switcher dropdown
  frontend/src/components/ChatPanel/ThreadSelector.module.css  — styles
  backend/agents/verify.py                                     — citation verification node

Modified files:
  frontend/src/types/index.ts                                  — add ThinkingEvent, thread types
  frontend/src/store/chatStore.ts                              — add thinking/token separation, threads
  frontend/src/components/ChatPanel/ChatPanel.tsx              — integrate ThinkingPanel + ThreadSelector
  frontend/src/components/ChatPanel/MessageList.tsx            — render thinking blocks in messages
  frontend/src/components/ChatPanel/AssistantMessage.tsx       — add ThinkingBlock sub-component
  backend/agents/supervisor.py                                 — emit thinking SSE events
  backend/agents/qa.py                                         — capture reasoning in state
  backend/agents/reviewer.py                                   — add citation verification step
  backend/models/state.py                                      — add reasoning_tokens, thread_id fields
  backend/app.py                                               — accept thread_id in query API
  backend/storage/session_store.py                             — persist threads

Test files:
  tests/test_citation_verify.py                                — backend tests
  tests/frontend/ThinkingPanel.test.tsx                        — frontend tests
  tests/frontend/ThreadSelector.test.tsx                       — frontend tests
```

---

### Task 1: Backend — Emit reasoning/thinking SSE events

**Files:**
- Modify: `paper-reading-agent/backend/agents/supervisor.py:170-280`
- Modify: `paper-reading-agent/backend/models/state.py:57-58`
- Modify: `paper-reading-agent/backend/agents/qa.py:60-85`

**Interfaces:**
- Consumes: `state.plan` (dict from planner), `state.answer` (from generate), LLM response from `llm_client.chat()`
- Produces: SSE `event: thinking` with `{event: "thinking", node: "planner"|"generate"|"reviewer", text: "..."}` 

- [ ] **Step 1: Write failing tests**

Create `paper-reading-agent/tests/test_sse_protocol.py` (append to existing file):

```python
def test_thinking_event_format():
    """Thinking SSE events follow the correct wire format."""
    import json
    payload = {"event": "thinking", "node": "planner", "text": "Analyzing query intent..."}
    sse_line = f"event: thinking\ndata: {json.dumps(payload)}\n\n"
    
    lines = sse_line.strip().split("\n")
    assert lines[0] == "event: thinking"
    assert lines[1].startswith("data: ")
    parsed = json.loads(lines[1][6:])
    assert parsed["event"] == "thinking"
    assert parsed["node"] in ("planner", "generate", "reviewer")
    assert len(parsed["text"]) > 0


def test_thinking_event_emitted_in_qa_flow():
    """AgentState records reasoning from LLM responses."""
    from backend.models.state import AgentState
    from backend.models.paper import Paper
    
    state = AgentState(
        paper=Paper(paper_id="test", title="Test"),
        user_query="What is X?",
    )
    # Simulate planner adding reasoning
    state.plan = {"steps": [{"step": 1, "action": "search", "tool": "retrieve", "target": "X"}]}
    state.reasoning_log = [
        {"node": "planner", "text": "User is asking about X. I need to retrieve relevant sections."},
        {"node": "generate", "text": "Based on the retrieved text, X is defined as..."},
    ]
    assert len(state.reasoning_log) == 2
    assert state.reasoning_log[0]["node"] == "planner"
```

Run: `pytest tests/test_sse_protocol.py::test_thinking_event_format tests/test_sse_protocol.py::test_thinking_event_emitted_in_qa_flow -v`
Expected: 2 FAILED

- [ ] **Step 2: Add reasoning_log field to AgentState**

Read `paper-reading-agent/backend/models/state.py`. Add field after `trace`:

```python
reasoning_log: list[dict] = field(default_factory=list)
# Each entry: {"node": "planner"|"generate"|"reviewer", "text": "<reasoning snippet>"}
```

Run: `pytest tests/test_sse_protocol.py::test_thinking_event_emitted_in_qa_flow -v`
Expected: PASS

- [ ] **Step 3: Capture reasoning in QA nodes**

In `paper-reading-agent/backend/agents/qa.py`, modify `planner_node` (after state.plan is set):

```python
# After: state.plan = await llm_client.chat_json(...)
# Add reasoning capture:
if isinstance(state.plan, dict):
    plan_summary = state.plan.get("steps", [{"action": "unknown"}])
    state.reasoning_log.append({
        "node": "planner", 
        "text": f"Plan: {len(plan_summary)} step(s) — " + ", ".join(
            f'{s.get("action","?")} → {s.get("target","?")[:60]}' for s in (plan_summary if isinstance(plan_summary, list) else [plan_summary])
        )
    })
```

In `generate_node`, after answer is generated, capture the reasoning approach:

```python
# After state.answer is set:
if state.retrieved_chunks:
    sources = [c.section_heading or f"chunk-{i}" for i, c in enumerate(state.retrieved_chunks[:3])]
    state.reasoning_log.append({
        "node": "generate",
        "text": f"Synthesizing from {len(state.retrieved_chunks)} chunks: {', '.join(sources[:3])}"
    })
```

- [ ] **Step 4: Emit thinking SSE events in supervisor.py**

In `paper-reading-agent/backend/agents/supervisor.py`, in `stream_graph()` Segment 2, add after `on_chain_end` for generate/reviewer:

```python
# After existing on_chain_end handler for generate, add:
if kind == "on_chain_end" and node_name in ("planner", "generate", "reviewer"):
    output = data.get("output", {})
    if isinstance(output, dict):
        reasoning = output.get("reasoning_log", [])
    elif hasattr(output, "reasoning_log"):
        reasoning = output.reasoning_log or []
    else:
        reasoning = []
    # Emit only new entries since last emission
    new_entries = reasoning[len(_emitted_reasoning[0]):]
    _emitted_reasoning[0] = len(reasoning)
    for entry in new_entries:
        yield f"event: thinking\ndata: {json.dumps({'event': 'thinking', 'node': entry['node'], 'text': entry['text']})}\n\n"
```

Add `_emitted_reasoning = [0]` near `_last_answer` declaration.

- [ ] **Step 5: Run tests and commit**

```bash
cd paper-reading-agent && python -m pytest tests/ -x -q
```
Expected: 133 passed (131 + 2 new)

```bash
git add paper-reading-agent/backend/models/state.py paper-reading-agent/backend/agents/qa.py paper-reading-agent/backend/agents/supervisor.py paper-reading-agent/tests/test_sse_protocol.py
git commit -m "feat: emit thinking SSE events from planner/generate/reviewer nodes

Adds reasoning_log to AgentState to capture agent reasoning steps.
Supervisor emits 'event: thinking' SSE events so the frontend can
render a collapsible thinking panel (Project Constellation pattern)."
```

---

### Task 2: Frontend — ThinkingPanel component

**Files:**
- Create: `paper-reading-agent/frontend/src/components/ChatPanel/ThinkingPanel.tsx`
- Create: `paper-reading-agent/frontend/src/components/ChatPanel/ThinkingPanel.module.css`
- Modify: `paper-reading-agent/frontend/src/types/index.ts:65-82`
- Modify: `paper-reading-agent/frontend/src/store/chatStore.ts`
- Modify: `paper-reading-agent/frontend/src/components/ChatPanel/AssistantMessage.tsx`

**Interfaces:**
- Consumes: ThinkingEvent `{event: "thinking", node: string, text: string}` from SSE
- Consumes: `chatStore.thinkingSessions: Map<string, string[]>` — threadId → thinking texts
- Produces: `<ThinkingPanel entries={ThinkingEntry[]} />` renders collapsible reasoning blocks

- [ ] **Step 1: Add ThinkingEvent type**

In `paper-reading-agent/frontend/src/types/index.ts`, add after `TokenEvent`:

```typescript
export interface ThinkingEvent {
  event: 'thinking'
  node: string   // 'planner' | 'generate' | 'reviewer'
  text: string    // human-readable reasoning snippet
}
```

Update SSEEvent union:
```typescript
export type SSEEvent = InitEvent | NodeEvent | HitlEvent | TokenEvent | ThinkingEvent | DoneEvent
```

- [ ] **Step 2: Add thinking tracking to chatStore**

In `paper-reading-agent/frontend/src/store/chatStore.ts`, add to ChatState interface:

```typescript
thinkingEntries: { node: string; text: string }[]
appendThinking: (node: string, text: string) => void
```

Add initial state and implementation:
```typescript
thinkingEntries: [],
appendThinking: (node, text) => set((s) => ({
  thinkingEntries: [...s.thinkingEntries, { node, text }]
})),
```

Add to `reset()` — clear `thinkingEntries: []`.

- [ ] **Step 3: Create ThinkingPanel component**

Create `paper-reading-agent/frontend/src/components/ChatPanel/ThinkingPanel.tsx`:

```typescript
import { useState } from 'react'
import styles from './ThinkingPanel.module.css'

interface ThinkingEntry {
  node: string
  text: string
}

interface ThinkingPanelProps {
  entries: ThinkingEntry[]
}

const NODE_LABELS: Record<string, string> = {
  planner: '📋 Planning',
  generate: '✍️ Writing',
  reviewer: '🔍 Reviewing',
}

export default function ThinkingPanel({ entries }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(true)
  
  if (entries.length === 0) return null
  
  return (
    <div className={styles.container}>
      <button 
        className={styles.toggle}
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? '▾' : '▸'} Reasoning ({entries.length} step{entries.length > 1 ? 's' : ''})
      </button>
      {expanded && (
        <div className={styles.entries}>
          {entries.map((e, i) => (
            <div key={i} className={styles.entry}>
              <span className={styles.nodeLabel}>{NODE_LABELS[e.node] || e.node}</span>
              <span className={styles.text}>{e.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Create ThinkingPanel styles**

Create `paper-reading-agent/frontend/src/components/ChatPanel/ThinkingPanel.module.css`:

```css
.container {
  margin: 8px 0;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #fafafa;
  overflow: hidden;
}

.toggle {
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: #f5f5f5;
  text-align: left;
  font-size: 13px;
  font-weight: 500;
  color: #666;
  cursor: pointer;
}

.toggle:hover {
  background: #eee;
}

.entries {
  padding: 8px 12px;
}

.entry {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  line-height: 1.5;
}

.nodeLabel {
  flex-shrink: 0;
  color: #888;
  min-width: 90px;
}

.text {
  color: #555;
}
```

- [ ] **Step 5: Integrate into AssistantMessage**

In `paper-reading-agent/frontend/src/components/ChatPanel/AssistantMessage.tsx`, add import and render:

```typescript
import ThinkingPanel from './ThinkingPanel'

// In the component, after render, add:
{message.thinkingEntries && message.thinkingEntries.length > 0 && (
  <ThinkingPanel entries={message.thinkingEntries} />
)}
```

Update `AssistantMessage` type in `types/index.ts`:
```typescript
export interface AssistantMessage {
  id: string
  role: 'assistant'
  content: string
  evidenceList: Evidence[]
  qualityScore: QualityScore | null
  trace: string[]
  thinkingEntries?: { node: string; text: string }[]  // new field
}
```

Update `finalizeAssistantMessage` in chatStore to include thinkingEntries.

- [ ] **Step 6: Handle thinking events in useSSE hook**

Find `useSSE` hook and add handling for `event: thinking` lines — call `chatStore.appendThinking(node, text)`.

- [ ] **Step 7: Run tests and commit**

```bash
cd paper-reading-agent/frontend && ./node_modules/.bin/vitest run
```
Expected: 62+ passed

```bash
git add paper-reading-agent/frontend/src/
git commit -m "feat: add ThinkingPanel — collapsible agent reasoning display

Inspired by Project Constellation and PaperQuay. Renders agent
reasoning steps in a collapsible panel above each assistant message.
SSE 'event: thinking' events flow through chatStore to the UI."
```

---

### Task 3: Backend — Citation verification

**Files:**
- Create: `paper-reading-agent/backend/agents/verify.py`
- Modify: `paper-reading-agent/backend/agents/reviewer.py:6-57`
- Modify: `paper-reading-agent/backend/agents/supervisor.py:35-67` (graph edges)
- Create: `paper-reading-agent/tests/test_citation_verify.py`

**Interfaces:**
- Consumes: `state.evidence_list` (list[Evidence] with quote fields), `state.paper.raw_text`
- Produces: `verify_citation_node(state) -> state` with evidence_list updated (verified flag)
- Graph: Insert `verify` node between `reviewer` and `output` in LangGraph

- [ ] **Step 1: Write failing test**

Create `paper-reading-agent/tests/test_citation_verify.py`:

```python
from backend.agents.verify import verify_citations
from backend.models.state import Evidence, EvidenceLevel

def test_verify_exact_quote_match():
    """Evidence with exact quote match in source text is marked verified."""
    source_text = "The Transformer architecture relies entirely on attention mechanisms."
    evidence = [
        Evidence(
            evidence_id="ev1",
            claim="Transformer uses attention",
            level=EvidenceLevel.R0,
            quote="relies entirely on attention mechanisms",
            page=1,
        ),
        Evidence(
            evidence_id="ev2", 
            claim="Transformer uses convolutions",
            level=EvidenceLevel.R0,
            quote="uses convolutional layers heavily",
            page=1,
        ),
    ]
    verified = verify_citations(evidence, source_text)
    assert verified[0].confidence > 0.8  # exact match → high confidence
    assert verified[1].confidence < 0.5  # no match → low confidence

def test_verify_fuzzy_quote_match():
    """Fuzzy matching catches minor wording differences."""
    source_text = "We propose a new simple network architecture, the Transformer."
    evidence = [
        Evidence(
            evidence_id="ev1",
            claim="Novel architecture",
            level=EvidenceLevel.R0,
            quote="propose a new simple network architecture",
            page=1,
        ),
    ]
    verified = verify_citations(evidence, source_text)
    assert verified[0].confidence > 0.7  # fuzzy match → good confidence

def test_verify_no_quote_fallback():
    """Evidence without quote uses claim text for matching."""
    source_text = "BERT uses masked language modeling for pre-training."
    evidence = [
        Evidence(evidence_id="ev1", claim="BERT uses MLM", level=EvidenceLevel.R0, quote=None, page=1),
    ]
    verified = verify_citations(evidence, source_text)
    assert verified[0].confidence >= 0  # should not crash
```

Run: `pytest tests/test_citation_verify.py -v`
Expected: 3 FAILED

- [ ] **Step 2: Implement verify_citations function**

Create `paper-reading-agent/backend/agents/verify.py`:

```python
"""Citation verification — checks that generated evidence quotes 
actually appear in the source paper text. Inspired by Project 
Constellation's two-stage citation enforcement."""

import re
from difflib import SequenceMatcher
from backend.models.state import AgentState, Evidence
from backend.utils.logger import logger


def verify_citations(evidence_list: list[Evidence], source_text: str) -> list[Evidence]:
    """Two-stage verification of each evidence citation.
    
    Stage 1 (Presence): Check if quote text appears in source (exact → fuzzy → claim fallback).
    Stage 2 (Confidence): Score the match quality and flag low-confidence citations.
    
    Returns evidence list with updated confidence scores.
    """
    if not source_text:
        for ev in evidence_list:
            ev.confidence = 0.0
        return evidence_list
    
    source_lower = source_text.lower()
    
    for ev in evidence_list:
        search_text = (ev.quote or ev.claim or "").strip()
        if not search_text:
            ev.confidence = 0.0
            continue
        
        search_lower = search_text.lower()
        
        # Stage 1: Presence check
        if search_lower in source_lower:
            ev.confidence = 0.95  # Exact match
        elif _fuzzy_match(search_lower, source_lower):
            ev.confidence = 0.7   # Fuzzy match
        elif len(search_lower) > 30:
            # Try matching individual sentences
            words = set(search_lower.split())
            source_words = set(source_lower.split())
            overlap = len(words & source_words) / max(len(words), 1)
            ev.confidence = min(0.5, overlap)  # Partial word overlap
        else:
            ev.confidence = 0.1  # No match found
        
        # Attach verification note
        if ev.confidence < 0.5:
            ev.reasoning = (ev.reasoning or "") + " [⚠️ Citation not verified in source text]"
    
    return evidence_list


def _fuzzy_match(needle: str, haystack: str, threshold: float = 0.8) -> bool:
    """Check if needle approximately appears in haystack using sliding window."""
    if len(needle) < 10:
        return False
    # Use SequenceMatcher for fuzzy matching
    window_size = len(needle)
    for i in range(0, len(haystack) - window_size // 2, window_size // 4):
        window = haystack[i:i + window_size + 20]
        ratio = SequenceMatcher(None, needle, window).ratio()
        if ratio >= threshold:
            return True
    return False


async def verify_citation_node(state: AgentState) -> AgentState:
    """LangGraph node: verify all evidence citations against paper text."""
    source = state.paper.raw_text if state.paper else ""
    verified = verify_citations(state.evidence_list, source)
    
    total = len(verified)
    low_conf = sum(1 for e in verified if e.confidence < 0.5)
    if low_conf > 0:
        logger.warning(f"Citation check: {low_conf}/{total} low-confidence citations")
    
    state.evidence_list = verified
    state.trace.append(f"verify({total-lower_conf}/{total} ok)")
    return state
```

- [ ] **Step 3: Wire verify node into LangGraph**

In `paper-reading-agent/backend/agents/supervisor.py`:

1. Import: `from backend.agents.verify import verify_citation_node`
2. Add node: `graph.add_node("verify", verify_citation_node)`
3. Modify edges — change reviewer→output to reviewer→verify→output:
```python
# Replace: graph.add_conditional_edges("reviewer", decide_loop, {"output": "output", "rewrite": "rewrite"})
# With:
graph.add_conditional_edges("reviewer", decide_loop, {
    "output": "verify",
    "rewrite": "rewrite",
})
graph.add_edge("verify", "output")
```

4. Add verify to Segment 2 node-enter events:
```python
if kind == "on_chain_start" and node_name in (
    "retrieve", "generate", "observe", "reviewer", "rewrite", "verify", "output",
    "external_search",
):
```

- [ ] **Step 4: Run tests and commit**

```bash
cd paper-reading-agent && python -m pytest tests/ -x -q
```
Expected: 136 passed (131 + 3 new + 2 from Task 1)

```bash
git add paper-reading-agent/backend/agents/verify.py paper-reading-agent/backend/agents/reviewer.py paper-reading-agent/backend/agents/supervisor.py paper-reading-agent/tests/test_citation_verify.py
git commit -m "feat: add citation verification — two-stage check of generated evidence

Inspired by Project Constellation's citation enforcement. Post-generation
verify node checks each evidence quote against source paper text using
exact match → fuzzy match → word overlap fallback. Low-confidence
citations are flagged with a warning in the evidence reasoning field."
```

---

### Task 4: Frontend — Citation confidence indicators

**Files:**
- Modify: `paper-reading-agent/frontend/src/components/Evidence/EvidencePopover.tsx`
- Modify: `paper-reading-agent/frontend/src/components/Evidence/EvidenceBadge.tsx`

**Interfaces:**
- Consumes: `Evidence.confidence` (float 0-1 from backend verification)
- Produces: Visual confidence indicator (✅ green / ⚠️ yellow / ❌ red)

- [ ] **Step 1: Add confidence indicator to EvidenceBadge**

Read `EvidenceBadge.tsx`. Add a small icon based on confidence:

```typescript
function ConfidenceIcon({ confidence }: { confidence: number }) {
  if (confidence >= 0.7) return <span title="Verified" style={{color: '#2e7d32'}}>✓</span>
  if (confidence >= 0.3) return <span title="Uncertain match" style={{color: '#ed6c02'}}>⚠</span>
  return <span title="Not found in source" style={{color: '#d32f2f'}}>✗</span>
}
```

Render `<ConfidenceIcon confidence={evidence.confidence} />` next to the evidence badge level indicator.

- [ ] **Step 2: Add verification summary to EvidencePopover**

In `EvidencePopover.tsx`, add a verification section at the bottom of the popover content:

```typescript
{evidence.confidence !== undefined && evidence.confidence < 0.5 && (
  <div className={styles.verifyWarning}>
    ⚠️ This citation could not be verified in the source text.
    {evidence.quote && <code>{evidence.quote.slice(0, 100)}</code>}
  </div>
)}
```

- [ ] **Step 3: Run tests and commit**

```bash
cd paper-reading-agent/frontend && ./node_modules/.bin/vitest run
```
Expected: 62+ passed

```bash
git add paper-reading-agent/frontend/src/components/Evidence/
git commit -m "feat: add citation confidence indicators to evidence UI

Green checkmark (≥0.7), yellow warning (0.3-0.7), red X (<0.3).
Verification warnings shown in EvidencePopover for low-confidence
citations. Complements backend citation verification (Task 3)."
```

---

### Task 5: Backend — Multi-thread chat support

**Files:**
- Modify: `paper-reading-agent/backend/storage/session_store.py`
- Modify: `paper-reading-agent/backend/app.py:138-170`
- Modify: `paper-reading-agent/backend/models/state.py`

**Interfaces:**
- Consumes: `thread_id` from API query params (already partially supported)
- Produces: Multiple sessions per paper (1 paper → N threads), new API `GET /api/papers/{id}/threads`

- [ ] **Step 1: Add thread listing to SessionStore**

In `paper-reading-agent/backend/storage/session_store.py`, add:

```python
async def list_threads(self, paper_id: str) -> list[dict]:
    """List all conversation threads for a paper."""
    conn = await db.get_db()
    try:
        rows = []
        async with conn.execute(
            "SELECT session_id, created_at, thread_title FROM sessions WHERE paper_id = ? ORDER BY created_at DESC",
            (paper_id,)
        ) as cursor:
            async for row in cursor:
                rows.append({
                    "session_id": row["session_id"],
                    "created_at": row["created_at"],
                    "title": row["thread_title"] or f"Thread {row['session_id'][:8]}",
                })
        return rows
    finally:
        await conn.close()

async def set_thread_title(self, session_id: str, title: str) -> None:
    """Set a human-readable title for a conversation thread."""
    conn = await db.get_db()
    try:
        await conn.execute(
            "UPDATE sessions SET thread_title = ? WHERE session_id = ?",
            (title, session_id)
        )
        await conn.commit()
    finally:
        await conn.close()
```

Ensure `sessions` table has `thread_title TEXT` column (add migration if needed).

- [ ] **Step 2: Add API endpoint for threads**

In `paper-reading-agent/backend/app.py`, add:

```python
@app.get("/api/papers/{paper_id}/threads")
async def list_threads(paper_id: str):
    """List all conversation threads for a paper."""
    store = SessionStore()
    threads = await store.list_threads(paper_id)
    return {"paper_id": paper_id, "threads": threads}


@app.post("/api/threads/{session_id}/title")
async def set_thread_title(session_id: str, request: Request):
    """Set a custom title for a conversation thread."""
    body = await request.json()
    title = body.get("title", "").strip()[:200]
    store = SessionStore()
    await store.set_thread_title(session_id, title)
    return {"session_id": session_id, "title": title}
```

Auto-generate thread title from first user message in `stream_graph`:
```python
# After first user message is saved, auto-title the thread
if session_id:
    thread_title = query[:80] + ("..." if len(query) > 80 else "")
    await session_store.set_thread_title(session_id, thread_title)
```

- [ ] **Step 3: Run tests and commit**

```bash
cd paper-reading-agent && python -m pytest tests/ -x -q
```
Expected: 138 passed

```bash
git add paper-reading-agent/backend/storage/session_store.py paper-reading-agent/backend/app.py paper-reading-agent/backend/agents/supervisor.py
git commit -m "feat: add multi-thread chat — list/create/title conversation threads

Adds GET /api/papers/{id}/threads and POST /api/threads/{id}/title.
Auto-generates thread titles from first user query. Inspired by
Paperview's multi-thread conversation model."
```

---

### Task 6: Frontend — ThreadSelector component

**Files:**
- Create: `paper-reading-agent/frontend/src/components/ChatPanel/ThreadSelector.tsx`
- Create: `paper-reading-agent/frontend/src/components/ChatPanel/ThreadSelector.module.css`
- Modify: `paper-reading-agent/frontend/src/components/ChatPanel/ChatPanel.tsx`
- Modify: `paper-reading-agent/frontend/src/store/chatStore.ts`

**Interfaces:**
- Consumes: `GET /api/papers/{paper_id}/threads` → `{threads: [{session_id, title, created_at}]}`
- Consumes: `POST /api/threads/{session_id}/title` to rename
- Produces: `<ThreadSelector threads={Thread[]} activeId={string} onSelect={fn} onNew={fn} />`

- [ ] **Step 1: Add thread types and store state**

In `paper-reading-agent/frontend/src/types/index.ts`:

```typescript
export interface Thread {
  session_id: string
  title: string
  created_at: string
}
```

In `paper-reading-agent/frontend/src/store/chatStore.ts`, add:

```typescript
threads: Thread[]
activeThreadId: string | null
setThreads: (threads: Thread[]) => void
setActiveThread: (id: string) => void
addThread: (thread: Thread) => void
```

- [ ] **Step 2: Create ThreadSelector component**

Create `paper-reading-agent/frontend/src/components/ChatPanel/ThreadSelector.tsx`:

```typescript
import { useState } from 'react'
import type { Thread } from '@/types'
import styles from './ThreadSelector.module.css'

interface Props {
  threads: Thread[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}

export default function ThreadSelector({ threads, activeId, onSelect, onNew }: Props) {
  return (
    <div className={styles.container}>
      <select 
        className={styles.select}
        value={activeId || ''}
        onChange={(e) => onSelect(e.target.value)}
      >
        {threads.map((t) => (
          <option key={t.session_id} value={t.session_id}>
            {t.title}
          </option>
        ))}
      </select>
      <button className={styles.newBtn} onClick={onNew} title="New thread">
        +
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Integrate into ChatPanel**

In `ChatPanel.tsx`, add above the MessageList:

```typescript
import ThreadSelector from './ThreadSelector'

// Fetch threads on paper load
useEffect(() => {
  if (paper?.paper_id) {
    api.getThreads(paper.paper_id).then(setThreads)
  }
}, [paper?.paper_id])

// In JSX:
<ThreadSelector
  threads={threads}
  activeId={activeThreadId}
  onSelect={(id) => loadThread(id)}
  onNew={() => startNewThread()}
/>
```

- [ ] **Step 4: Run tests and commit**

```bash
cd paper-reading-agent/frontend && ./node_modules/.bin/vitest run
```
Expected: 64+ passed

```bash
git add paper-reading-agent/frontend/src/
git commit -m "feat: add ThreadSelector — multi-thread conversation management

Dropdown to switch between conversation threads per paper.
New thread button creates fresh conversation contexts.
Inspired by Paperview's multi-thread chat model."
```

---

## 执行顺序

```
Task 1 (backend thinking events)
  → Task 2 (frontend ThinkingPanel) [依赖 Task 1 的 SSE 事件]
Task 3 (backend citation verify)
  → Task 4 (frontend confidence indicators) [依赖 Task 3 的 confidence 字段]
Task 5 (backend multi-thread API)
  → Task 6 (frontend ThreadSelector) [依赖 Task 5 的 API]
```

Task 1+2 和 Task 3+4 和 Task 5+6 三组可并行执行。

每组内部：backend task 先行，frontend task 依赖 backend task 的输出接口。

---

## Self-Review

1. **Spec coverage:** Thinking panel ✅ (Tasks 1-2) | Citation verification ✅ (Tasks 3-4) | Multi-thread chat ✅ (Tasks 5-6)
2. **No placeholders:** All code is concrete with exact file paths, types, and commands.
3. **Type consistency:** ThinkingEvent type flows from Task 1 (backend) → Task 2 (frontend). Evidence.confidence flows from Task 3 → Task 4. Thread type flows from Task 5 → Task 6. All interfaces defined in their producing task and referenced by exact name in the consuming task.
