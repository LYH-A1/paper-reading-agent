"""Compare agent nodes: parallel reader + comparison generation."""

import asyncio
from backend.models.state import CompareState, AgentState
from backend.models.paper import Paper
from backend.agents.reader import reader_node
from backend.llm.client import llm_client
from backend.llm.prompts import COMPARE_PROMPT
from backend.storage.paper_store import PaperStore
from backend.utils.logger import logger


async def reader_all_node(state: CompareState) -> CompareState:
    """Parallel read all selected papers. Handles mix of PDF and no-PDF papers."""
    store = PaperStore()
    papers = []
    for pid in state.paper_ids:
        paper = await store.get_paper(pid)
        if paper is None:
            raise ValueError(f"Paper not found: {pid}")
        papers.append(paper)

    async def read_one(paper: Paper) -> dict:
        if paper.file_path is None:
            # No PDF: generate minimal report from metadata
            return {
                "title": paper.title,
                "authors": paper.authors,
                "abstract_summary": paper.abstract[:500] if paper.abstract else "",
                "method": "",
                "contributions": [],
                "experiments_summary": "",
                "limitations": [],
                "keywords": [],
            }
        # Full PDF: reuse reader_node
        agent_state = AgentState(paper=paper, user_query="")
        try:
            result_state = await reader_node(agent_state)
            if result_state.error:
                logger.warning(f"Reader failed for {paper.title}: {result_state.error}")
                return {
                    "title": paper.title,
                    "authors": paper.authors,
                    "abstract_summary": paper.abstract[:500] or "",
                    "method": "", "contributions": [],
                    "experiments_summary": "", "limitations": [], "keywords": [],
                }
            return result_state.report or {}
        except Exception as e:
            logger.warning(f"Reader exception for {paper.title}: {e}")
            return {
                "title": paper.title,
                "authors": paper.authors,
                "abstract_summary": paper.abstract[:500] or "",
                "method": "", "contributions": [],
                "experiments_summary": "", "limitations": [], "keywords": [],
            }

    reports = await asyncio.gather(*[read_one(p) for p in papers])
    state.papers = papers
    state.reports = reports
    state.trace.append("reader_batch")
    return state


async def compare_generate_node(state: CompareState) -> CompareState:
    """Generate structured comparison report from multi-paper reports."""
    aspects = state.comparison_aspects or ["method", "contribution", "limitation"]
    query_text = state.user_query or ""

    reports_text = "\n\n---\n\n".join([
        f"## Paper {i+1}: {r.get('title', 'Unknown')}\n"
        f"Authors: {', '.join(r.get('authors', []))}\n"
        f"Method: {r.get('method_summary', r.get('method', 'N/A'))}\n"
        f"Contribution: {', '.join(r.get('contributions', [])) if r.get('contributions') else 'N/A'}\n"
        f"Experiments: {r.get('experiments_summary', 'N/A')}\n"
        f"Limitations: {', '.join(r.get('limitations', [])) if r.get('limitations') else 'N/A'}"
        for i, r in enumerate(state.reports)
    ])

    prompt = COMPARE_PROMPT.format(
        aspects=", ".join(aspects),
        query=query_text if query_text else "None",
        reports=reports_text,
    )

    try:
        content, _ = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            system=""
        )
        state.answer = content
    except Exception as e:
        logger.error(f"Compare generation failed: {e}")
        state.error = str(e)
        state.answer = f"Failed to generate comparison: {e}"

    state.trace.append("compare")
    return state
