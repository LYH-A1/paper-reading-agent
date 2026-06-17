# Task 12: LangGraph Supervisor

**Status:** Complete

**Commit:** `cda83ce`

## Summary

Created `paper-reading-agent/backend/agents/supervisor.py` — a LangGraph supervisor that coordinates the full 9-node paper reading pipeline with HITL (human-in-the-loop) interrupt support.

## Graph Topology

| Edge | Type | Condition |
|------|------|-----------|
| START -> reader | fixed | entry point |
| reader -> classify | fixed | |
| classify -> planner | fixed | |
| planner -> retrieve | fixed | HITL interrupt point |
| retrieve -> generate | fixed | |
| generate -> observe | fixed | |
| observe -> planner | conditional | `check_observe_result` — plan invalid |
| observe -> retrieve | conditional | `check_observe_result` — insufficient |
| observe -> reviewer | conditional | `check_observe_result` — sufficient |
| reviewer -> output | conditional | `decide_loop` — score >= 7 or max rewrites |
| reviewer -> rewrite | conditional | `decide_loop` — needs improvement |
| rewrite -> generate | fixed | re-entry for rewrite loop |
| output -> END | fixed | |

## Key Design Decisions

1. **Checkpointer:** Uses `sqlite3.connect()` directly + `SqliteSaver(conn)` rather than `SqliteSaver.from_conn_string()` (which is a `@contextmanager` and returns a generator when used outside a `with` block). Connection stored at `config.db_path` (default: `data/paper-reading.db`).

2. **HITL Interrupt:** `interrupt_after=["planner"]` pauses execution after plan generation. The `run_agent()` async function handles resumption:
   - First `ainvoke` runs through `reader -> classify -> planner` and halts.
   - If `state["plan"]` is populated, a second `ainvoke(None, config)` resumes execution.

3. **Synchronous Wrapper:** `run_agent_sync()` wraps `run_agent()` with `asyncio.run()` for CLI usage.

## Verified

- [x] Syntax valid (`ast.parse`)
- [x] Import resolves (`from backend.agents.supervisor import build_graph`)
- [x] `build_graph()` compiles without error (all 9 nodes + `__start__`)
- [x] `config.db_path` resolves to `paper-reading-agent/data/paper-reading.db`

## Concerns

1. **Import fix applied:** The original task spec imported `Paper` from `backend.models.state`, but `Paper` lives in `backend.models.paper`. Fixed the import.
2. **Checkpointer fix applied:** `SqliteSaver.from_conn_string()` is a `@contextmanager` — calling it without `with` returns a generator, not a valid checkpointer. Changed to `sqlite3.connect(...)` + `SqliteSaver(conn)`.
