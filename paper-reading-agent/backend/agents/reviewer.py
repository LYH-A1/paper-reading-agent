from backend.models.state import AgentState, CompareState, Evidence, EvidenceLevel, QualityScore
from backend.llm.client import llm_client
from backend.llm.prompts import REVIEWER_PROMPT
from backend.utils.logger import logger

async def reviewer_node(state: AgentState) -> AgentState:
    """Annotate R0/R1/R2 evidence + quality scoring."""
    paper_text = state.paper.raw_text[:64000] if state.paper else ""

    try:
        result = await llm_client.chat_json(
            messages=[{"role": "user", "content": f"""Paper text: {paper_text}

Answer to review: {state.answer}

{REVIEWER_PROMPT}"""}],
            system="Respond ONLY with valid JSON. No markdown, no explanation."
        )
    except Exception as e:
        logger.warning(f"Reviewer failed: {e}, using default scores")
        result = {"relevance": 2, "consistency": 2, "completeness": 1, "deductions": [str(e)], "evidence_list": [], "followup_questions": []}

    state.quality_score = QualityScore(
        relevance=result.get("relevance", 2),
        consistency=result.get("consistency", 2),
        completeness=result.get("completeness", 1),
    )

    evidence_list = []
    for ev_data in result.get("evidence_list", []):
        try:
            evidence_list.append(Evidence(
                evidence_id=ev_data.get("evidence_id", ""),
                claim=ev_data.get("claim", ""),
                level=EvidenceLevel(ev_data.get("level", "R2")),
                sentence_index=ev_data.get("sentence_index"),
                char_start=ev_data.get("char_start"),
                char_end=ev_data.get("char_end"),
                page=ev_data.get("page"),
                quote=ev_data.get("quote"),
                section_heading=ev_data.get("section_heading"),
                source_title=ev_data.get("source_title"),
                source_url=ev_data.get("source_url"),
                source_venue=ev_data.get("source_venue"),
                source_year=ev_data.get("source_year"),
                reasoning=ev_data.get("reasoning"),
                based_on_evidence_ids=ev_data.get("based_on_evidence_ids", []),
                confidence=ev_data.get("confidence", 0.5),
            ))
        except Exception as e:
            logger.warning(f"Skipping malformed evidence: {e}")

    state.evidence_list = evidence_list
    state.observation = state.observation or {}
    state.observation["followup_questions"] = result.get("followup_questions", [])
    state.trace.append("reviewer")
    return state

def decide_loop(state: AgentState | CompareState, max_rewrites: int = 1) -> str:
    """Phase 5: accept max_rewrites parameter. Default 1; compare graph also uses 1."""
    if state.quality_score is None:
        return "output"
    if state.quality_score.total >= 7 or state.rewrite_count >= max_rewrites:
        return "output"
    return "rewrite"

async def rewrite_node(state: AgentState) -> AgentState:
    state.rewrite_count += 1
    state.trace.append(f"rewrite({state.rewrite_count})")
    return state

async def output_node(state: AgentState) -> AgentState:
    """Format final output — promote followup_questions from observation to state."""
    state.trace.append("output")
    if state.observation and "followup_questions" in state.observation:
        state.followup_questions = state.observation["followup_questions"]
    return state
