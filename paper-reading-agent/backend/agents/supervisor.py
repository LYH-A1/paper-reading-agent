import aiosqlite
from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from backend.models.state import AgentState
from backend.models.paper import Paper
from backend.agents.reader import reader_node
from backend.agents.qa import classify_node, planner_node, retrieve_node, generate_node, observe_node, check_observe_result
from backend.agents.reviewer import reviewer_node, rewrite_node, decide_loop, output_node
from backend.config import config

async def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("reader", reader_node)
    graph.add_node("classify", classify_node)
    graph.add_node("planner", planner_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("observe", observe_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("output", output_node)

    graph.set_entry_point("reader")
    graph.add_edge("reader", "classify")
    graph.add_edge("classify", "planner")
    graph.add_edge("planner", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "observe")
    graph.add_conditional_edges("observe", check_observe_result, {
        "reviewer": "reviewer",
        "retrieve": "retrieve",
        "planner": "planner",
    })
    graph.add_conditional_edges("reviewer", decide_loop, {
        "output": "output",
        "rewrite": "rewrite",
    })
    graph.add_edge("rewrite", "generate")
    graph.add_edge("output", END)

    # NOTE: SqliteSaver.from_conn_string is a context manager (@contextmanager).
    # Using it outside a 'with' block returns a generator, which is not a valid
    # checkpointer. We create the connection directly instead.
    conn = await aiosqlite.connect(str(config.db_path))
    checkpointer = AsyncSqliteSaver(conn)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=["planner"]  # HITL: pause after plan generation
    )

async def run_agent(paper_path: str, query: str) -> AgentState:
    """Run complete agent pipeline. Returns final AgentState."""
    graph = await build_graph()
    initial_state = AgentState(
        paper=Paper(file_path=str(Path(paper_path).resolve())),
        user_query=query
    )
    config_dict = {"configurable": {"thread_id": initial_state.paper.file_path}}

    # Run through to planner (will interrupt)
    raw_state = await graph.ainvoke(initial_state, config_dict)
    state = AgentState(**{k: v for k, v in raw_state.items() if k in AgentState.__dataclass_fields__})

    # Resume past interrupt (HITL auto-approved in Phase 1)
    if state.plan:
        raw_state = await graph.ainvoke(None, config_dict)
        state = AgentState(**{k: v for k, v in raw_state.items() if k in AgentState.__dataclass_fields__})

    return state

def run_agent_sync(paper_path: str, query: str) -> AgentState:
    """Synchronous wrapper for CLI usage."""
    import asyncio
    return asyncio.run(run_agent(paper_path, query))
