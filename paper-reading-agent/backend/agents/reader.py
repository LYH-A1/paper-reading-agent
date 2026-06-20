from backend.models.state import AgentState
from backend.tools.pdf_parser import PDFParser, PDFParseError
from backend.tools.retriever import HybridRetriever
from backend.llm.client import llm_client
from backend.llm.prompts import REPORT_PROMPT
from backend.utils.logger import logger

async def reader_node(state: AgentState) -> AgentState:
    """Parse PDF + generate structured report + build retrieval index (once)."""
    if state.paper is not None and state.report is not None:
        logger.info("Paper already parsed, skipping reader")
        state.trace.append("reader(cached)")
        return state

    # Phase 5: no-PDF path — generate minimal report from metadata
    if state.paper.file_path is None:
        paper = state.paper
        state.report = {
            "title": paper.title,
            "authors": paper.authors,
            "abstract_summary": paper.abstract[:500] if paper.abstract else "",
            "method": "",
            "contributions": [],
            "experiments_summary": "",
            "limitations": [],
            "keywords": [],
        }
        state.trace.append("reader(metadata)")
        return state

    parser = PDFParser()
    try:
        paper = parser.parse(state.paper.file_path)
    except PDFParseError as e:
        state.error = str(e)
        state.trace.append("reader(error)")
        return state

    state.paper = paper

    # Persist corrected title/authors/abstract back to DB
    if paper.title and not paper.title.endswith(".pdf"):
        try:
            from backend.storage.paper_store import PaperStore
            ps = PaperStore()
            await ps.add_paper(paper)
        except Exception:
            pass  # Best-effort — non-critical if DB write fails

    # Build retriever index once, cache in state
    try:
        state.retriever = HybridRetriever(paper)
        logger.info(f"Built retrieval index with {len(state.retriever.chunks)} chunks")
    except Exception as e:
        logger.warning(f"Retriever index build failed: {e}, proceeding without retrieval")
        state.retriever = None

    # Generate structured report via LLM
    try:
        report, _ = await llm_client.chat(
            messages=[{"role": "user", "content": paper.raw_text[:32000]}],
            system=REPORT_PROMPT
        )
        import json
        try:
            state.report = json.loads(report)
        except json.JSONDecodeError:
            state.report = {"raw_report": report}
    except Exception as e:
        logger.warning(f"Report generation failed: {e}, using fallback")
        state.report = {"title": paper.title, "abstract_summary": paper.abstract[:500]}

    state.trace.append("reader")
    return state
