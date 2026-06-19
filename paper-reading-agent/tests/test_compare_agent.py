import pytest
from unittest.mock import AsyncMock, patch
from backend.agents.compare import reader_all_node, compare_generate_node
from backend.models.state import CompareState
from backend.models.paper import Paper


@pytest.mark.asyncio
async def test_reader_all_node_no_pdf_papers():
    from backend.storage.paper_store import PaperStore

    papers = [
        Paper(paper_id="id-1", title="Paper A", authors=["A. One"], abstract="Abstract A.", file_path=None),
        Paper(paper_id="id-2", title="Paper B", authors=["B. Two"], abstract="Abstract B.", file_path=None),
    ]

    with patch.object(PaperStore, 'get_paper', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = lambda pid: next((p for p in papers if p.paper_id == pid), None)
        state = CompareState(paper_ids=["id-1", "id-2"])
        result = await reader_all_node(state)

    assert len(result.reports) == 2
    assert result.reports[0]["title"] == "Paper A"
    assert result.reports[1]["title"] == "Paper B"
    assert "reader_batch" in result.trace


@pytest.mark.asyncio
async def test_reader_all_node_paper_not_found():
    from backend.storage.paper_store import PaperStore

    with patch.object(PaperStore, 'get_paper', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        state = CompareState(paper_ids=["nonexistent"])
        with pytest.raises(ValueError, match="Paper not found"):
            await reader_all_node(state)


@pytest.mark.asyncio
async def test_reader_all_node_empty_ids():
    state = CompareState(paper_ids=[])
    result = await reader_all_node(state)
    assert result.reports == []
    assert "reader_batch" in result.trace


@pytest.mark.asyncio
async def test_compare_generate_node_basic():
    from backend.llm.client import llm_client

    state = CompareState(
        paper_ids=["id-1", "id-2"],
        reports=[
            {"title": "Paper A", "authors": ["A"], "method_summary": "Method A",
             "contributions": ["C1"], "experiments_summary": "Exp A", "limitations": ["L1"]},
            {"title": "Paper B", "authors": ["B"], "method_summary": "Method B",
             "contributions": ["C2"], "experiments_summary": "Exp B", "limitations": ["L2"]},
        ],
        comparison_aspects=["method", "contribution"],
    )

    with patch.object(llm_client, 'chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = ("## Method Comparison\n...", {})
        result = await compare_generate_node(state)

    assert "## Method Comparison" in result.answer
    assert "compare" in result.trace


@pytest.mark.asyncio
async def test_compare_generate_node_llm_error():
    from backend.llm.client import llm_client

    state = CompareState(
        paper_ids=["id-1"],
        reports=[{"title": "Paper A", "authors": ["A"], "method_summary": "",
                   "contributions": [], "experiments_summary": "", "limitations": []}],
    )

    with patch.object(llm_client, 'chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = RuntimeError("LLM timeout")
        result = await compare_generate_node(state)

    assert "Failed to generate comparison" in result.answer
    assert result.error is not None


@pytest.mark.asyncio
async def test_compare_generate_node_default_aspects():
    from backend.llm.client import llm_client

    state = CompareState(
        paper_ids=["id-1"],
        reports=[{"title": "Paper A", "authors": ["A"], "method_summary": "",
                   "contributions": [], "experiments_summary": "", "limitations": []}],
        comparison_aspects=None,
    )

    with patch.object(llm_client, 'chat', new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = ("report", {})
        await compare_generate_node(state)

    call_arg = mock_chat.call_args[1]["messages"][0]["content"] if mock_chat.call_args else ""
    assert "method" in call_arg.lower()  # default aspects used
