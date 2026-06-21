# Task P6-5: Backend Multi-Thread Chat API

## Status: Implemented

## Changes Made

### 1. `backend/storage/session_store.py`
- Added `list_threads(paper_id)` method — queries sessions grouped by paper, returns session_id/created_at/title. Auto-migrates `thread_title` column via ALTER TABLE if missing.
- Added `set_thread_title(session_id, title)` method — updates `thread_title` column for a given session.

### 2. `backend/app.py`
- Added `GET /api/papers/{paper_id}/threads` — returns all conversation threads for a paper.
- Added `POST /api/threads/{session_id}/title` — sets a custom title for a thread (max 200 chars).

### 3. `backend/agents/supervisor.py`
- After the `init` SSE event in `stream_graph`, auto-generates a thread title from the first user query (truncated to 80 chars + ellipsis). Wrapped in try/except as non-critical.

## Test Results
- **137 passed** (baseline: 137)
- No regressions. All existing tests pass.

## Git Commit
```
commit: pending
```
