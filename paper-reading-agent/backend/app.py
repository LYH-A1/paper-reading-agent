"""FastAPI application — SSE streaming, HITL, PDF endpoints."""

import json
import re
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.agents.supervisor import stream_graph, run_agent
from backend.models.paper import Paper
from backend.storage.paper_store import PaperStore
from backend.storage.session_store import SessionStore
from backend.config import config
from backend.storage.database import db
from backend.tools.bibtex_importer import parse_bibtex
from backend.agents.compare_supervisor import stream_compare
from backend.tools.external_search import ExternalRetriever

app = FastAPI(title="Paper Reading Agent")

frontend_dir = Path(__file__).resolve().parents[1] / "frontend" / "minimal"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
async def index():
    html_path = frontend_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Paper Reading Agent</h1>")


# ---- Preferences ----

PREFERENCE_WHITELIST = {
    "reranker":    {"default": "flashrank", "type": str, "values": {"flashrank", "bm25"}},
    "top_k":       {"default": "5",         "type": int,  "min": 1, "max": 20},
    "language":    {"default": "auto",      "type": str,  "values": {"en", "zh", "auto"}},
    "embedding_model": {"default": "auto",  "type": str},
}


def _coerce_preference(key: str, raw_value: str):
    """Convert stored string to native type based on whitelist."""
    spec = PREFERENCE_WHITELIST[key]
    if spec["type"] == int:
        return int(raw_value)
    return raw_value


PREFERENCE_DEFAULTS = {k: _coerce_preference(k, v["default"]) for k, v in PREFERENCE_WHITELIST.items()}


def _validate_preference(key: str, value) -> str | None:
    """Validate a preference value. Returns error message or None."""
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

    for key, value in body.items():
        error = _validate_preference(key, value)
        if error:
            return JSONResponse({"error": error}, status_code=400)

    conn = await db.get_db()
    try:
        for key, value in body.items():
            await conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        await conn.commit()
        return {"status": "ok"}
    finally:
        await conn.close()


@app.post("/api/upload")
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Please upload a PDF file"}, status_code=400)

    paper_dir = config.paper_dir
    paper_dir.mkdir(parents=True, exist_ok=True)
    file_path = paper_dir / f"{Path(file.filename).stem}_{hash(file.filename)}.pdf"
    content = await file.read()
    file_path.write_bytes(content)

    store = PaperStore()
    paper = Paper(file_path=str(file_path.resolve()), title=file.filename)
    await store.add_paper(paper)

    return {"paper_id": paper.paper_id, "title": paper.title, "file_path": paper.file_path}


@app.get("/api/query")
async def query_paper(
    paper_id: str = Query(default="", description="Paper ID for new queries (Segment 1)"),
    query: str = Query(default="", description="Question about the paper"),
    thread_id: str = Query(default="", description="Thread ID for resume (Segment 2)"),
    session_id: str = Query(default="", description="Session ID for resume (Segment 2) — must match Segment 1 init event"),
):
    """SSE streaming endpoint for agent queries.

    Two-segment protocol:
      Segment 1 (paper_id + query):
        Runs reader -> classify -> planner.
        If intent is compare/recommend, stops with ``event: hitl``.
        Otherwise, runs through to completion.

      Segment 2 (thread_id + session_id):
        Resumes after approval, runs retrieve -> generate -> ... -> done.
        ``session_id`` is required to record messages correctly.
    """
    async def event_stream():
        try:
            async for sse_str in stream_graph(
                paper_id, query,
                thread_id=thread_id or None,
                session_id=session_id or None,
            ):
                yield sse_str
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/approve")
async def approve_plan(request: Request):
    """Approve or reject a HITL plan.

    Expects JSON body:
      {"thread_id": "...", "approved": true/false, "feedback": "..."}

    Returns the next segment URL (the frontend re-opens the SSE connection).
    """
    body = await request.json()
    thread_id = body.get("thread_id", "")
    approved = body.get("approved", False)
    feedback = body.get("feedback", "")

    if not thread_id:
        return JSONResponse({"error": "thread_id required"}, status_code=400)

    # Store approval decision in the checkpointer state so the resumed
    # graph can read it (via state.plan_feedback on resume).
    # The actual resume happens when the frontend re-opens /api/query?thread_id=...
    return JSONResponse({
        "status": "approved" if approved else "rejected",
        "thread_id": thread_id,
        "feedback": feedback,
        "resume_url": f"/api/query?thread_id={thread_id}",
    })


def _snippet(text: str, max_len: int = 200) -> str:
    """Truncate text at a word boundary near max_len, append ellipsis if cut."""
    if len(text) <= max_len:
        return text
    cutoff = text.rfind(' ', 0, max_len)
    return text[:cutoff] + '...' if cutoff > 0 else text[:max_len] + '...'


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


@app.get("/api/papers")
async def list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    return [{
        "paper_id": p.paper_id,
        "title": p.title,
        "authors": p.authors,
        "abstract_snippet": _snippet(p.abstract, 200) if p.abstract else "",
        "import_source": p.import_source,
        "arxiv_id": p.arxiv_id,
        "parsed_at": p.parsed_at,
    } for p in papers]


@app.get("/api/pdf/{paper_id}")
async def get_pdf(paper_id: str):
    """Serve PDF binary for PDF.js rendering."""
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper or not Path(paper.file_path).exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    return FileResponse(paper.file_path, media_type="application/pdf")


@app.get("/api/pdf/{paper_id}/text")
async def get_pdf_text(paper_id: str):
    """Return text layer data (pages with sentences and bbox) for PDF highlight overlay."""
    import fitz  # PyMuPDF
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper or not Path(paper.file_path).exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)

    doc = fitz.open(paper.file_path)
    pages = []
    for page_idx in range(min(len(doc), 30)):  # Cap at 30 pages
        page = doc[page_idx]
        rect = page.rect
        # Get text blocks with positions
        blocks = page.get_text("dict")["blocks"]
        sentences = []
        for block in blocks:
            if block.get("type") != 0:  # text block
                continue
            for line in block.get("lines", []):
                text_parts = []
                bbox = None
                for span in line.get("spans", []):
                    text_parts.append(span["text"])
                    if bbox is None:
                        bbox = list(span["bbox"])
                    else:
                        # Expand bbox
                        bbox[2] = max(bbox[2], span["bbox"][2])
                        bbox[3] = max(bbox[3], span["bbox"][3])
                full_text = " ".join(text_parts).strip()
                if full_text and bbox:
                    sentences.append({
                        "text": full_text,
                        "char_start": 0,
                        "char_end": len(full_text),
                        "bbox": bbox,
                    })
        pages.append({
            "page": page_idx + 1,
            "width": rect.width,
            "height": rect.height,
            "sentences": sentences,
        })
    doc.close()
    return {"pages": pages}


@app.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str, format: str = Query(default="md", pattern="^(md|json)$")):
    """Export a session conversation as Markdown or JSON."""
    store = SessionStore()
    session = await store.get_session_with_paper(session_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    if format == "json":
        return _export_json(session)
    return _export_markdown(session)


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a safe filename slug."""
    slug = re.sub(r'[^\w一-鿿-]', '-', text, flags=re.UNICODE)
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
    lines.append(f"Date: {session.get('created_at', '')} | Paper: {session.get('paper_title', 'Unknown')}")
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
                    elif level == "R1":
                        title = ev.get("source_title")
                        url = ev.get("source_url")
                        if title:
                            details.append(f"Source: {title}")
                        if url:
                            details.append(url)
                    elif level == "R2":
                        based_on = ev.get("based_on_evidence_ids", [])
                        conf = ev.get("confidence")
                        conf = 0 if conf is None else conf
                        if based_on:
                            details.append(f"Based on {', '.join(based_on)}")
                        details.append(f"confidence: {conf:.0%}")
                    detail_str = " · ".join(details) if details else ""
                    prefix = f'  - [{level}] "{claim}"'
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


# ---- BibTeX Export ----

@app.get("/api/papers/{paper_id}/references/export")
async def export_references(paper_id: str, format: str = Query(default="bib")):
    """Export paper references as BibTeX (.bib) file."""
    if format != "bib":
        return JSONResponse({"error": "Only bib format is supported"}, status_code=400)

    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper:
        return JSONResponse({"error": "Paper not found"}, status_code=404)

    if not paper.references:
        bib_content = f"% No references found for {paper.title or 'this paper'}"
    else:
        bib_content = _format_bibtex(paper.references)

    title_slug = _slugify(paper.title or "references")
    filename = f"{title_slug}-references.bib"
    return Response(
        content=bib_content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- Compare & Import ----

@app.post("/api/compare")
async def compare_papers(request: Request):
    """Generate a structured comparison report for selected papers (SSE)."""
    body = await request.json()
    paper_ids = body.get("paper_ids", [])
    aspects = body.get("aspects")
    query = body.get("query", "")

    if not paper_ids or len(paper_ids) < 2:
        return JSONResponse({"error": "At least 2 papers required"}, status_code=400)
    if len(paper_ids) > 5:
        return JSONResponse({"error": "Maximum 5 papers allowed"}, status_code=400)

    store = PaperStore()
    for pid in paper_ids:
        paper = await store.get_paper(pid)
        if not paper:
            return JSONResponse({"error": f"Paper not found: {pid}"}, status_code=400)

    async def event_stream():
        try:
            async for sse_str in stream_compare(paper_ids, aspects, query):
                yield sse_str
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/compare/followup")
async def compare_followup(request: Request):
    """Answer a follow-up question about a comparison report."""
    body = await request.json()
    paper_ids = body.get("paper_ids", [])
    question = body.get("question", "")
    comparison_report = body.get("comparison_report", "")

    if not question.strip():
        return JSONResponse({"error": "question is required"}, status_code=400)
    if not comparison_report.strip():
        return JSONResponse({"error": "comparison_report is required"}, status_code=400)

    from backend.llm.client import llm_client

    prompt = (
        "You are a helpful academic research assistant. "
        "Based on the following comparison report, answer the follow-up question.\n\n"
        f"## Comparison Report\n\n{comparison_report}\n\n"
        f"## Follow-up Question\n\n{question}\n\n"
        "Answer the question using information from the comparison report. "
        "If the report doesn't contain enough information, say so clearly."
    )

    async def event_stream():
        try:
            answer, _ = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="You are a helpful academic research assistant.",
            )
            yield f"event: token\ndata: {json.dumps({'event': 'token', 'text': answer})}\n\n"
            yield f"event: done\ndata: {json.dumps({'event': 'done', 'answer': answer, 'evidence_list': [], 'quality_score': None, 'trace': ['compare_followup']})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/papers/save-external")
async def save_external_paper(request: Request):
    """Save an external arXiv paper to the library."""
    body = await request.json()
    arxiv_id = (body.get("arxiv_id", "") or "").strip()

    if not arxiv_id:
        return JSONResponse({"error": "arxiv_id is required"}, status_code=400)
    if not re.match(r'^[\d]{4}\.[\d]{4,}(v\d+)?$', arxiv_id):
        return JSONResponse({"error": "Invalid arXiv ID format"}, status_code=400)

    store = PaperStore()

    existing = await store.get_by_arxiv_id(arxiv_id)
    if existing:
        return {"paper_id": existing.paper_id, "title": existing.title, "already_saved": True}

    retriever = ExternalRetriever()
    result = await retriever.fetch_by_id(arxiv_id)
    if not result:
        return JSONResponse({"error": "arXiv API unavailable, try again later"}, status_code=503)

    from backend.storage.paper_store import _slugify_title
    title_slug = _slugify_title(result.title)
    existing = await store.get_by_title_slug(title_slug)
    if existing:
        return {"paper_id": existing.paper_id, "title": existing.title, "already_saved": True}

    paper = Paper(
        title=result.title,
        authors=result.authors,
        abstract=result.abstract,
        raw_text=result.abstract,
        arxiv_id=arxiv_id,
        arxiv_pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        file_path=None,
        import_source="external_save",
    )
    await store.add_paper(paper)
    return {"paper_id": paper.paper_id, "title": paper.title, "already_saved": False}


@app.post("/api/papers/import-bibtex")
async def import_bibtex(request: Request):
    """Import papers from BibTeX content."""
    body = await request.json()
    bibtex_content = body.get("bibtex_content", "")

    if not bibtex_content.strip():
        return JSONResponse({"error": "Empty BibTeX content"}, status_code=400)

    papers, parse_errors = parse_bibtex(bibtex_content)

    store = PaperStore()
    imported = []
    skipped = 0

    for paper in papers:
        from backend.storage.paper_store import _slugify_title
        title_slug = _slugify_title(paper.title)
        existing = await store.get_by_title_slug(title_slug)
        if existing:
            skipped += 1
            continue

        await store.add_paper(paper)
        imported.append({
            "paper_id": paper.paper_id,
            "title": paper.title,
            "import_source": paper.import_source,
        })

    return {
        "imported": len(imported),
        "skipped": skipped,
        "errors": parse_errors,
        "papers": imported,
    }


def _entry_type(venue: str) -> str:
    """Determine BibTeX entry type from venue name using keyword matching."""
    conference_keywords = [
        "Conference", "Proceedings", "Workshop", "Symposium",
        "CVPR", "ICML", "NeurIPS", "ACL", "EMNLP", "NAACL",
        "ICCV", "ECCV", "ICLR", "AAAI", "IJCAI", "SIGGRAPH",
    ]
    if any(kw.lower() in (venue or "").lower() for kw in conference_keywords):
        return "inproceedings"
    return "article"


def _cite_key(authors: list, year: int | None, title: str) -> str:
    """Generate BibTeX cite key: FirstAuthorSurnameYearTitleWords."""
    surname = ""
    if authors:
        first_author = authors[0].strip()
        parts = first_author.split()
        surname = parts[-1] if parts else first_author
    surname = re.sub(r'[^a-zA-Z0-9]', '', surname).lower()
    if not surname:
        surname = "anonymous"
    title_words = re.findall(r'[a-zA-Z]+', title.lower())
    title_part = "".join(title_words[:3])
    year_str = str(year) if year else "????"
    return f"{surname}{year_str}{title_part}"


def _format_authors(authors: list) -> str:
    """Format authors as 'LastName, FirstName' joined with ' and '."""
    formatted = []
    for a in authors:
        parts = a.strip().split()
        if len(parts) >= 2:
            formatted.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
        else:
            formatted.append(a)
    return " and ".join(formatted)


def _format_bibtex(references: list) -> str:
    """Format a list of Reference objects as BibTeX string."""
    entries = []
    for ref in references:
        entry_type = _entry_type(ref.venue or "")
        key = _cite_key(ref.authors, ref.year, ref.title)

        lines = [f"@{entry_type}{{{key},"]
        lines.append(f"  title = {{{ref.title}}},")
        if ref.authors:
            lines.append(f"  author = {{{_format_authors(ref.authors)}}},")
        if ref.year:
            lines.append(f"  year = {{{ref.year}}},")
        if ref.venue:
            venue_field = "booktitle" if entry_type == "inproceedings" else "journal"
            lines.append(f"  {venue_field} = {{{ref.venue}}},")
        if ref.doi:
            lines.append(f"  doi = {{{ref.doi}}},")
        if ref.url:
            lines.append(f"  url = {{{ref.url}}},")
        # Remove trailing comma from last field line
        lines[-1] = lines[-1].rstrip(",")
        lines.append("}")
        entries.append("\n".join(lines))

    return "\n\n".join(entries) + "\n"
