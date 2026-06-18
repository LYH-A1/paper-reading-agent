"""FastAPI application — SSE streaming, HITL, PDF endpoints."""

import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.agents.supervisor import stream_graph, run_agent
from backend.models.paper import Paper
from backend.storage.paper_store import PaperStore
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
    paper_path: str = Query(..., description="Path to the PDF file"),
    query: str = Query(..., description="Question about the paper"),
    thread_id: str = Query(None, description="Thread ID for resume (Segment 2)"),
):
    """SSE streaming endpoint for agent queries.

    Two-segment protocol:
      Segment 1 (no thread_id):
        Runs reader -> classify -> planner.
        If intent is compare/recommend, stops with ``event: hitl``.
        Otherwise, runs through to completion.

      Segment 2 (with thread_id):
        Resumes after approval, runs retrieve -> generate -> ... -> done.
    """
    async def event_stream():
        try:
            async for sse_str in stream_graph(paper_path, query, thread_id=thread_id):
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
async def get_paper_metadata(paper_id: str):
    """Return paper metadata (title, abstract, authors, sections)."""
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper:
        return JSONResponse({"error": "Paper not found"}, status_code=404)

    return {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "sections": [
            {
                "heading": s.heading,
                "page_start": s.page_start,
                "page_end": s.page_end,
            }
            for s in paper.sections
        ],
    }


@app.get("/api/pdf/{paper_id}/text")
async def get_pdf_text(paper_id: str):
    """Extract text blocks with bounding boxes from the PDF using PyMuPDF.

    Returns a list of blocks, each with:
      - page (int): 1-indexed page number
      - text (str)
      - bbox (list[float]): [x0, y0, x1, y1]
    """
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper:
        return JSONResponse({"error": "Paper not found"}, status_code=404)

    pdf_path = Path(paper.file_path)
    if not pdf_path.exists():
        return JSONResponse({"error": f"PDF file not found: {pdf_path}"}, status_code=404)

    try:
        import fitz  # PyMuPDF — lazy import
    except ImportError:
        return JSONResponse({"error": "PyMuPDF (fitz) not installed"}, status_code=500)

    doc = fitz.open(str(pdf_path))
    blocks = []
    for page_num, page in enumerate(doc):
        page_blocks = page.get_text("blocks")
        for b in page_blocks:
            # block structure: (x0, y0, x1, y1, text, block_no, block_type)
            if len(b) >= 5 and b[4].strip():
                blocks.append({
                    "page": page_num + 1,
                    "text": b[4].strip()[:500],  # truncate long blocks
                    "bbox": list(b[:4]),
                })
    doc.close()

    return {"paper_id": paper_id, "blocks": blocks}
