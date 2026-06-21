"""Supervisor: build graph, stream events, HITL support."""

import json
import uuid
import aiosqlite
from pathlib import Path
from typing import AsyncGenerator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.models.state import AgentState
from backend.models.paper import Paper
from backend.agents.reader import reader_node
from backend.agents.qa import classify_node, planner_node, retrieve_node, generate_node, observe_node, check_observe_result, external_search_node, route_after_retrieve
from backend.agents.reviewer import reviewer_node, rewrite_node, decide_loop, output_node
from backend.agents.verify import verify_citation_node
from backend.config import config
from backend.storage.session_store import SessionStore
from backend.storage.paper_store import PaperStore


def should_interrupt(state: AgentState) -> list[str]:
    """Return a list of node names to interrupt after.
    Only interrupts for compare/recommend intents; summary and qa pass through.
    Returns ["planner"] to interrupt after planner, or [] to continue.
    """
    if state.intent in ("compare", "recommend"):
        return ["planner"]
    return []


def _restore_paper_identity(state: AgentState, initial_state: AgentState) -> None:
    """Restore paper identity fields that may be lost during checkpoint deserialization.

    LangGraph msgpack serialization may not preserve Paper dataclass fields correctly
    (especially those with defaults), causing paper_id to be lost. This bridges the gap.
    """
    if state.paper is None or initial_state.paper is None:
        return
    src = initial_state.paper
    dst = state.paper
    if not dst.paper_id and src.paper_id:
        dst.paper_id = src.paper_id
    if not dst.title and src.title:
        dst.title = src.title
    if not dst.file_path and src.file_path:
        dst.file_path = src.file_path


async def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("reader", reader_node)
    graph.add_node("classify", classify_node)
    graph.add_node("planner", planner_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("observe", observe_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("verify", verify_citation_node)
    graph.add_node("output", output_node)
    graph.add_node("external_search", external_search_node)

    graph.set_entry_point("reader")
    graph.add_edge("reader", "classify")
    graph.add_edge("classify", "planner")
    graph.add_edge("planner", "retrieve")
    graph.add_conditional_edges("retrieve", route_after_retrieve, {
        "external_search": "external_search",
        "generate": "generate",
    })
    graph.add_edge("external_search", "generate")
    graph.add_edge("generate", "observe")
    graph.add_conditional_edges("observe", check_observe_result, {
        "reviewer": "reviewer",
        "retrieve": "retrieve",
        "planner": "planner",
        "external_search": "external_search",
    })
    graph.add_conditional_edges("reviewer", decide_loop, {
        "output": "verify",
        "rewrite": "rewrite",
    })
    graph.add_edge("verify", "output")
    graph.add_edge("rewrite", "generate")
    graph.add_edge("output", END)

    # NOTE: SqliteSaver.from_conn_string is a context manager (@contextmanager).
    # Using it outside a 'with' block returns a generator, which is not a valid
    # checkpointer. We create the connection directly instead.
    conn = await aiosqlite.connect(str(config.db_path))
    checkpointer = AsyncSqliteSaver(conn)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=["planner"],  # HITL: pause after plan generation
    )


async def run_agent(paper_id: str, query: str) -> AgentState:
    """Run complete agent pipeline. Returns final AgentState."""
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if paper is None:
        paper = Paper(paper_id=paper_id, file_path="", title="Unknown")
    graph = await build_graph()
    initial_state = AgentState(
        paper=paper,
        user_query=query
    )
    config_dict = {"configurable": {"thread_id": paper_id or str(uuid.uuid4())}}

    # Run through to planner (will interrupt)
    raw_state = await graph.ainvoke(initial_state, config_dict)
    state = AgentState(**{k: v for k, v in raw_state.items() if k in AgentState.__dataclass_fields__})
    _restore_paper_identity(state, initial_state)

    # Resume past interrupt (HITL auto-approved in Phase 1)
    if state.plan:
        raw_state = await graph.ainvoke(None, config_dict)
        state = AgentState(**{k: v for k, v in raw_state.items() if k in AgentState.__dataclass_fields__})
        _restore_paper_identity(state, initial_state)

    return state


def run_agent_sync(paper_id: str, query: str) -> AgentState:
    """Synchronous wrapper for CLI usage."""
    import asyncio
    return asyncio.run(run_agent(paper_id, query))


async def stream_graph(
    paper_id: str,
    query: str,
    thread_id: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream graph execution as SSE-formatted strings.

    Two-segment protocol:
      Segment 1: runs reader → classify → planner, yields events, stops at
                 ``event: hitl`` (if should_interrupt) or continues to end.
      Segment 2: called with ``thread_id=`` and ``session_id=`` to resume
                 after approval. ``session_id`` must be the value from the
                 Segment 1 init event so messages are recorded correctly.

    Each yielded string is a complete SSE ``data: ...\n\n`` line (or
    ``event: ...\ndata: ...\n\n`` for named events).
    """
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if paper is None:
        paper = Paper(paper_id=paper_id, file_path="", title="Unknown")
    graph = await build_graph()
    initial_state = AgentState(
        paper=paper,
        user_query=query,
    )
    tid = thread_id or str(uuid.uuid4())

    # Create or reuse session
    session_store = SessionStore()
    if not session_id:
        session_id = await session_store.create_session(paper_id)
        init_payload = {
            "event": "init",
            "thread_id": tid,
            "session_id": session_id,
        }
        yield f"event: init\ndata: {json.dumps(init_payload)}\n\n"

        # Auto-title the thread from the first user query
        thread_title = query[:80] + ("..." if len(query) > 80 else "")
        try:
            await session_store.set_thread_title(session_id, thread_title)
        except Exception:
            pass  # Non-critical

    config_dict = {"configurable": {"thread_id": tid}}
    _last_answer = [""]  # mutable container for answer-delta tracking
    _emitted_reasoning = [0]  # mutable counter for already-emitted reasoning entries

    # ----- Segment 1: first pass (reader → classify → planner) -----
    async for event in graph.astream_events(
        initial_state,
        config_dict,
        version="v2",
    ):
        kind = event.get("event", "")
        node_name = event.get("name", "")
        data = event.get("data", {})

        # Yield node-enter events
        if kind == "on_chain_start" and node_name in (
            "reader", "classify", "planner",
        ):
            yield f"event: node\ndata: {json.dumps({'event': 'node', 'node': node_name})}\n\n"

        # Emit token deltas from answer changes across node boundaries
        if kind == "on_chain_end" and node_name in ("reader", "classify", "planner"):
            delta = _emit_answer_delta(data, _last_answer)
            if delta:
                yield f"event: token\ndata: {json.dumps({'event': 'token', 'token': delta})}\n\n"

        # After planner completes, check if we should HITL
        if kind == "on_chain_end" and node_name == "planner":
            # Extract state from output
            output = data.get("output", {})
            if isinstance(output, dict):
                state_intent = output.get("intent", "")
                state_plan = output.get("plan")
            else:
                state_intent = getattr(output, "intent", "")
                state_plan = getattr(output, "plan", None)

            # Emit thinking events from reasoning_log in Segment 1
            if isinstance(output, dict):
                reasoning = output.get("reasoning_log", [])
            elif hasattr(output, "reasoning_log"):
                reasoning = output.reasoning_log or []
            else:
                reasoning = []
            for entry in reasoning:
                yield f"event: thinking\ndata: {json.dumps({'event': 'thinking', 'node': entry['node'], 'text': entry['text']})}\n\n"

            if state_plan is not None and should_interrupt(
                AgentState(
                    paper=Paper(file_path=str(Path(paper_id).resolve())),
                    user_query=query,
                    intent=state_intent or "",
                )
            ):
                yield (
                    f"event: hitl\n"
                    f"data: {json.dumps({'event': 'hitl', 'plan': state_plan, 'thread_id': tid})}\n\n"
                )
                return  # Stop Segment 1 — wait for approval

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

        # Pass through other events in first pass (skip raw chat model stream)
        if kind != "on_chat_model_stream":
            yield _serialize_event(kind, node_name, data)

    # ----- Segment 2: resume after approval (retrieve → generate → …) -----
    async for event in graph.astream_events(
        None,  # Resume with None
        config_dict,
        version="v2",
    ):
        kind = event.get("event", "")
        node_name = event.get("name", "")
        data = event.get("data", {})

        if kind == "on_chain_start" and node_name in (
            "retrieve", "generate", "observe", "reviewer", "rewrite", "verify", "output",
            "external_search",
        ):
            yield f"event: node\ndata: {json.dumps({'event': 'node', 'node': node_name})}\n\n"

        # Intercept token-level streaming for chat model output
        if kind == "on_chat_model_stream":
            token_text = _extract_token_text(data)
            if token_text:
                yield f"event: token\ndata: {json.dumps({'event': 'token', 'token': token_text})}\n\n"

        # Emit token deltas from state answer changes (httpx fallback)
        if kind == "on_chain_end" and node_name in (
            "retrieve", "generate", "observe", "reviewer", "rewrite", "external_search",
        ):
            delta = _emit_answer_delta(data, _last_answer)
            if delta:
                yield f"event: token\ndata: {json.dumps({'event': 'token', 'token': delta})}\n\n"

        # Emit thinking events from reasoning_log
        if kind == "on_chain_end" and node_name in ("planner", "generate", "reviewer"):
            output = data.get("output", {})
            if isinstance(output, dict):
                reasoning = output.get("reasoning_log", [])
            elif hasattr(output, "reasoning_log"):
                reasoning = output.reasoning_log or []
            else:
                reasoning = []
            new_entries = reasoning[_emitted_reasoning[0]:]
            _emitted_reasoning[0] = len(reasoning)
            for entry in new_entries:
                yield f"event: thinking\ndata: {json.dumps({'event': 'thinking', 'node': entry['node'], 'text': entry['text']})}\n\n"

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

        # Skip raw chat model stream events (already handled as tokens above)
        if kind != "on_chat_model_stream":
            yield _serialize_event(kind, node_name, data)


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


def _extract_token_text(data: dict) -> str:
    """Extract token text from an on_chat_model_stream event data dict."""
    try:
        chunk = data.get("chunk", data)
        # LangChain AI message chunk: chunk.content may be a string or list
        content = chunk.get("content", "")
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    parts.append(c.get("text", ""))
                else:
                    parts.append(str(c))
            return "".join(parts)
        return content or ""
    except Exception:
        return ""


def _emit_answer_delta(data: dict, last_answer: list) -> str | None:
    """Check if state answer changed and return incremental token delta.

    Since we use direct httpx calls instead of LangChain chat models,
    on_chat_model_stream does not fire. Instead, track answer changes
    at node boundaries and emit the delta as token events.
    """
    output = data.get("output", {})
    new_answer = ""
    if isinstance(output, dict):
        new_answer = output.get("answer", "")
    elif hasattr(output, "answer"):
        new_answer = output.answer or ""
    if new_answer and new_answer != last_answer[0]:
        delta = new_answer[len(last_answer[0]):]
        last_answer[0] = new_answer
        return delta
    return None


def _serialize_event(kind: str, node_name: str, data: dict) -> str:
    """Serialize a generic astream_events event to SSE string."""
    try:
        payload = {
            "event": kind,
            "node": node_name,
            "data": str(data.get("input", "")),
        }
        return f"event: streaming\ndata: {json.dumps(payload)}\n\n"
    except Exception:
        return "event: streaming\ndata: {}\n\n"


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
    # Get retriever from module cache (preferred) or state (fallback for tests)
    from backend.tools.retriever import get_cached_retriever
    cached_r = get_cached_retriever(state.paper) if state.paper else None
    active_r = cached_r or state.retriever
    reranker = active_r.reranker if active_r else None
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
            "input_chunks": len(active_r.chunks) if active_r else 0,
            "output_chunks": len(state.retrieved_chunks),
            "model": reranker.model_name if reranker and reranker.model_name else None,
        },
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
    }
    return f"event: done\ndata: {json.dumps(payload)}\n\n"
