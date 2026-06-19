from backend.models.state import AgentState, RetrievedChunk
from backend.llm.client import llm_client
from backend.llm.prompts import CLASSIFY_PROMPT, PLANNER_PROMPTS, ANSWER_PROMPTS, OBSERVE_PROMPT, KEYWORD_RULES
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
        state.observation = result
    except Exception as e:
        logger.warning(f"Observe failed: {e}, defaulting to sufficient=False")
        state.observation = {"plan_valid": True, "sufficient": False, "gaps": ["observe timeout"], "reasoning": str(e)}
    state.trace.append("observe")
    return state

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
