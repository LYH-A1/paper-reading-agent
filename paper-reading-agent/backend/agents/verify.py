"""Citation verification — checks that generated evidence quotes
actually appear in the source paper text. Inspired by Project
Constellation's two-stage citation enforcement."""

from difflib import SequenceMatcher
from backend.models.state import AgentState, Evidence
from backend.utils.logger import logger


def verify_citations(evidence_list: list[Evidence], source_text: str) -> list[Evidence]:
    """Two-stage verification of each evidence citation.

    Stage 1 (Presence): Check if quote text appears in source (exact -> fuzzy -> claim fallback).
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
            # Try matching individual words
            words = set(search_lower.split())
            source_words = set(source_lower.split())
            overlap = len(words & source_words) / max(len(words), 1)
            ev.confidence = min(0.5, overlap)
        else:
            ev.confidence = 0.1  # No match found

        # Attach verification note for low confidence
        if ev.confidence < 0.5:
            ev.reasoning = (ev.reasoning or "") + " [Citation not verified in source text]"

    return evidence_list


def _fuzzy_match(needle: str, haystack: str, threshold: float = 0.8) -> bool:
    """Check if needle approximately appears in haystack using sliding window."""
    if len(needle) < 10:
        return False
    window_size = len(needle)
    step = max(1, window_size // 4)
    for i in range(0, max(1, len(haystack) - window_size // 2), step):
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
    state.trace.append(f"verify({total - low_conf}/{total} ok)")
    return state
