"""Compare graph builder + SSE streaming."""

import json
import uuid
from typing import AsyncGenerator

from langgraph.graph import StateGraph, END

from backend.models.state import CompareState, AgentState
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
    """Adapt CompareState for reviewer_node (expects AgentState)."""
    agent_state = AgentState(
        answer=state.answer,
        paper=state.papers[0] if state.papers else None,
        evidence_list=state.evidence_list,
    )
    # Combine text from all papers for reviewer to reference
    if state.papers:
        combined_text = "\n\n---\n\n".join(
            p.raw_text[:16000] for p in state.papers
        )
        if agent_state.paper:
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
    """Final output node."""
    state.trace.append("output")
    return state


async def stream_compare(
    paper_ids: list[str],
    aspects: list[str] | None = None,
    query: str = "",
) -> AsyncGenerator[str, None]:
    """SSE streaming for compare graph."""
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
