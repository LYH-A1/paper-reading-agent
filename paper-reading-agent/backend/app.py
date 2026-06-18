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
):
    """SSE streaming endpoint for agent queries.

    Two-segment protocol:
      Segment 1 (paper_id + query):
        Runs reader -> classify -> planner.
        If intent is compare/recommend, stops with ``event: hitl``.
        Otherwise, runs through to completion.

      Segment 2 (thread_id):
        Resumes after approval, runs retrieve -> generate -> ... -> done.
    """
    async def event_stream():
        try:
            async for sse_str in stream_graph(paper_id, query, thread_id=thread_id or None):
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


@app.get("/api/papers")
async def list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    return [{"paper_id": p.paper_id, "title": p.title, "parsed_at": p.parsed_at} for p in papers]


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
                        conf = ev.get("confidence", 0)
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
