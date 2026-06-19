import asyncio

from backend.models.state import AgentState, RetrievedChunk
from backend.llm.client import llm_client
from backend.llm.prompts import CLASSIFY_PROMPT, PLANNER_PROMPTS, ANSWER_PROMPTS, OBSERVE_PROMPT, KEYWORD_RULES, SEARCH_QUERY_PROMPT
from backend.utils.logger import logger

async def classify_node(state: AgentState) -> AgentState:
    """Classify user intent: summary/qa/compare/recommend."""
    query = state.user_query
    paper = state.paper
    try:
        result = await llm_client.chat_json(
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(query=query, title=paper.title if paper else "")}],
            system="Respond ONLY with JSON."
        )
        state.intent = result.get("intent", "qa")
    except Exception as e:
        logger.warning(f"Classify LLM failed: {e}, using keyword fallback")
        state.intent = _keyword_classify(query)
    state.trace.append("classify")
    return state

async def planner_node(state: AgentState) -> AgentState:
    """Generate execution plan. LangGraph interrupts AFTER this node for HITL approval."""
    prompt = PLANNER_PROMPTS.get(state.intent, PLANNER_PROMPTS["qa"])
    try:
        state.plan = await llm_client.chat_json(
            messages=[{"role": "user", "content": f"Report: {state.report}\n\nQuestion: {state.user_query}\n\n{prompt}"}],
            system="Respond ONLY with JSON."
        )
    except Exception as e:
        logger.warning(f"Planner failed: {e}, using default plan")
        state.plan = {"steps": [{"step": 1, "action": "retrieve relevant context", "tool": "retrieve", "target": state.user_query}]}
    state.trace.append("planner")
    return state

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

async def generate_node(state: AgentState) -> AgentState:
    """Streaming LLM answer generation."""
    prompt = ANSWER_PROMPTS.get(state.intent, ANSWER_PROMPTS["qa"])
    context = "\n\n".join(c.text for c in state.retrieved_chunks[:5]) if state.retrieved_chunks else state.paper.abstract if state.paper else ""

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

    rewrite_feedback = ""
    if state.rewrite_count > 0 and state.quality_score:
        rewrite_feedback = f"\n\nYour previous answer scored {state.quality_score.total}/10. Please improve: {state.quality_score}"

    full_answer = ""
    try:
        # Phase 1: use chat() (more reliable than streaming for now)
        full_answer, _ = await llm_client.chat(
            messages=[{"role": "user", "content": f"Paper report: {state.report}\n\nContext: {context}\n\nQuestion: {state.user_query}{rewrite_feedback}"}],
            system=prompt
        )
    except Exception as e:
        logger.error(f"Generate failed: {e}")
        state.error = f"Generation failed: {e}"

    state.answer = full_answer
    state.trace.append("generate")
    return state

async def observe_node(state: AgentState) -> AgentState:
    """Self-check: is the answer sufficient? Does the plan need revision?"""
    try:
        result = await llm_client.chat_json(
            messages=[{"role": "user", "content": f"Plan: {state.plan}\n\nAnswer: {state.answer}\n\n{OBSERVE_PROMPT}"}],
            system="Respond ONLY with JSON."
        )
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
    except Exception as e:
        logger.warning(f"Observe failed: {e}, defaulting to sufficient=False")
        state.observation = {"plan_valid": True, "sufficient": False, "gaps": ["observe timeout"], "reasoning": str(e)}
    state.trace.append("observe")
    return state

def check_observe_result(state: AgentState) -> str:
    """Conditional edge after observe."""
    obs = state.observation or {}
    # Prevent infinite observe loop: max 3 observe cycles
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

def _keyword_classify(query: str) -> str:
    query_lower = query.lower()
    scores = {}
    for intent, keywords in KEYWORD_RULES.items():
        scores[intent] = sum(1 for kw in keywords if kw in query_lower)
    if not scores or max(scores.values()) == 0:
        return "qa"
    return max(scores, key=scores.get)


# ---- Phase 4b: External Search ----


def route_after_retrieve(state: AgentState) -> str:
    """Conditional routing: compare/recommend -> external_search, else generate."""
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
        terms, _ = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            system="Respond ONLY with the space-separated list of terms, no explanation.",
        )
        terms = terms.strip()
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
