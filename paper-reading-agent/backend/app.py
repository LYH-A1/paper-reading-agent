import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.agents.supervisor import run_agent
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

@app.post("/api/query")
async def query_paper(paper_path: str = Form(...), query: str = Form(...)):
    """SSE streaming endpoint for agent queries."""
    async def event_stream():
        state = await run_agent(paper_path, query)
        for node in state.trace:
            yield f"data: {json.dumps({'event': 'node', 'node': node})}\n\n"
        yield f"data: {json.dumps({'event': 'done', 'answer': state.answer, 'quality_score': {'total': state.quality_score.total if state.quality_score else 0}, 'trace': state.trace, 'evidence_list': [{'evidence_id': e.evidence_id, 'level': e.level.value, 'claim': e.claim[:100], 'sentence_index': e.sentence_index, 'char_start': e.char_start, 'char_end': e.char_end} for e in state.evidence_list]})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/api/papers")
async def list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    return [{"paper_id": p.paper_id, "title": p.title, "parsed_at": p.parsed_at} for p in papers]
