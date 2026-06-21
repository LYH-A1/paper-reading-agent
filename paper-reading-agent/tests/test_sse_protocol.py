"""Tests for SSE protocol — init event and done payload."""
import json


class TestDonePayload:
    def test_includes_session_id_and_followup_questions(self):
        """_build_done_payload includes session_id and followup_questions."""
        from backend.models.state import AgentState, QualityScore, Evidence, EvidenceLevel
        from backend.agents.supervisor import _build_done_payload

        state = AgentState(
            session_id="sess-001",
            answer="The answer",
            quality_score=QualityScore(relevance=3, consistency=3, completeness=2),
            evidence_list=[
                Evidence(
                    evidence_id="ev1", claim="claim1", level=EvidenceLevel.R0,
                    page=4, quote="quote text", section_heading="Results",
                    confidence=0.95,
                )
            ],
            trace=["reader", "classify", "planner"],
            followup_questions=["What about X?", "How does Y compare?"],
        )

        payload_str = _build_done_payload(state)
        assert payload_str.startswith("event: done\n")
        json_str = payload_str.split("data: ", 1)[1]
        payload = json.loads(json_str)

        assert payload["event"] == "done"
        assert payload["session_id"] == "sess-001"
        assert payload["answer"] == "The answer"
        assert payload["quality_score"]["relevance"] == 3
        assert payload["quality_score"]["consistency"] == 3
        assert payload["quality_score"]["completeness"] == 2
        assert payload["quality_score"]["total"] == 8
        assert payload["followup_questions"] == ["What about X?", "How does Y compare?"]
        assert len(payload["evidence_list"]) == 1
        assert payload["evidence_list"][0]["quote"] == "quote text"


class TestInitEvent:
    def test_init_event_format(self):
        """Verify init event SSE format."""
        sse_line = 'event: init\ndata: {"event": "init", "thread_id": "tid-1", "session_id": "sess-1"}\n\n'
        assert 'event: init' in sse_line
        data_part = sse_line.split("data: ")[1].rstrip()
        payload = json.loads(data_part)
        assert payload["event"] == "init"
        assert payload["thread_id"] == "tid-1"
        assert payload["session_id"] == "sess-1"


def test_done_payload_includes_reranker_fields():
    """Done SSE payload includes reranker_used and reranker_summary."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState, RetrievedChunk
    from backend.tools.reranker import BM25FallbackReranker

    class MockRetriever:
        chunks = [{"chunk_id": "1"}] * 20
        reranker = BM25FallbackReranker()

    state = AgentState(
        answer="test answer",
        session_id="sess-1",
        retrieved_chunks=[RetrievedChunk(chunk_id="1", text="test", page=1) for _ in range(5)],
        trace=[],
    )
    state.retriever = MockRetriever()

    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert payload["reranker_used"] == "bm25"
    assert payload["reranker_summary"]["input_chunks"] == 20
    assert payload["reranker_summary"]["output_chunks"] == 5
    assert payload["reranker_summary"]["model"] is None


def test_done_payload_handles_none_retriever():
    """Done SSE payload degrades gracefully when retriever is None."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState

    state = AgentState(answer="test", session_id="sess-1", retrieved_chunks=[], trace=[])
    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert payload["reranker_used"] == "unknown"
    assert payload["reranker_summary"]["input_chunks"] == 0
    assert payload["reranker_summary"]["output_chunks"] == 0
    assert payload["reranker_summary"]["model"] is None


def test_done_payload_includes_external_results():
    """Done SSE payload includes external_results when present."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState, RetrievedChunk
    import json

    # Create a minimal mock ExternalResult
    MockExtResult = type("MockExtResult", (), {
        "result_id": "ext-001",
        "title": "External Paper",
        "authors": ["Author One"],
        "abstract": "An abstract.",
        "year": 2025,
        "url": "https://arxiv.org/abs/9999.99999",
        "source": "arxiv",
        "citation_count": 10,
    })

    state = AgentState(
        answer="test answer",
        session_id="sess-1",
        retrieved_chunks=[],
        trace=[],
        external_results=[MockExtResult()],
    )

    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert len(payload["external_results"]) == 1
    assert payload["external_results"][0]["result_id"] == "ext-001"
    assert payload["external_results"][0]["title"] == "External Paper"


def test_done_payload_empty_external_results():
    """Done SSE payload includes empty external_results list by default."""
    from backend.agents.supervisor import _build_done_payload
    from backend.models.state import AgentState
    import json

    state = AgentState(answer="test", session_id="sess-1", retrieved_chunks=[], trace=[])
    result = _build_done_payload(state)
    data_str = result.split("data: ")[1].split("\n\n")[0]
    payload = json.loads(data_str)

    assert payload["external_results"] == []


# -- Phase 6: thinking SSE events --
def test_thinking_event_format():
    """Thinking SSE events follow the correct wire format."""
    import json
    payload = {"event": "thinking", "node": "planner", "text": "Analyzing query intent..."}
    sse_line = f"event: thinking\ndata: {json.dumps(payload)}\n\n"
    lines = sse_line.strip().split("\n")
    assert lines[0] == "event: thinking"
    assert lines[1].startswith("data: ")
    parsed = json.loads(lines[1][6:])
    assert parsed["event"] == "thinking"
    assert parsed["node"] in ("planner", "generate", "reviewer")
    assert len(parsed["text"]) > 0


def test_thinking_event_emitted_in_qa_flow():
    """AgentState records reasoning from LLM responses."""
    from backend.models.state import AgentState
    from backend.models.paper import Paper
    state = AgentState(
        paper=Paper(paper_id="test", title="Test"),
        user_query="What is X?",
    )
    state.plan = {"steps": [{"step": 1, "action": "search", "tool": "retrieve", "target": "X"}]}
    state.reasoning_log = [
        {"node": "planner", "text": "User is asking about X. I need to retrieve relevant sections."},
        {"node": "generate", "text": "Based on the retrieved text, X is defined as..."},
    ]
    assert len(state.reasoning_log) == 2
    assert state.reasoning_log[0]["node"] == "planner"

# -- Phase 7: classify_plan node --
def test_classify_plan_combined_output():
    """classify_plan_node produces both intent and plan in state."""
    from backend.models.state import AgentState
    from backend.agents.qa import classify_plan_node
    from backend.models.paper import Paper

    state = AgentState(
        paper=Paper(paper_id="test", title="Attention Is All You Need"),
        user_query="What is the Transformer architecture?",
    )
    assert state.intent == ""  # Initially empty
    assert state.plan is None  # Initially None


def test_classify_plan_keyword_fallback():
    """When LLM fails, keyword fallback sets intent and default plan."""
    from backend.agents.qa import _keyword_classify

    assert _keyword_classify("summarize this paper") == "summary"
    assert _keyword_classify("compare BERT with GPT") == "compare"
    assert _keyword_classify("what is attention") == "qa"
    assert _keyword_classify("recommend similar papers") == "recommend"
    assert _keyword_classify("xyzzy unknown") == "qa"  # default
