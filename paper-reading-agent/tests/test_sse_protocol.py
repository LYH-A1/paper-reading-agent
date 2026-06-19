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
