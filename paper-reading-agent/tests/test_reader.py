import pytest


@pytest.mark.asyncio
async def test_reader_node_no_pdf_creates_minimal_report():
    from backend.agents.reader import reader_node
    from backend.models.state import AgentState
    from backend.models.paper import Paper

    paper = Paper(
        title="Test Paper Without PDF",
        authors=["Author One", "Author Two"],
        abstract="This is a test abstract for a paper without PDF.",
        file_path=None,
    )
    state = AgentState(paper=paper, user_query="")
    result = await reader_node(state)

    assert result.error is None
    assert result.report is not None
    assert result.report["title"] == "Test Paper Without PDF"
    assert "Author One" in result.report["authors"]
    assert "test abstract" in result.report["abstract_summary"]
    assert "reader(metadata)" in result.trace


@pytest.mark.asyncio
async def test_reader_node_no_pdf_empty_abstract():
    from backend.agents.reader import reader_node
    from backend.models.state import AgentState
    from backend.models.paper import Paper

    paper = Paper(title="No Abstract Paper", file_path=None)
    state = AgentState(paper=paper, user_query="")
    result = await reader_node(state)

    assert result.report["abstract_summary"] == ""
    assert result.error is None
