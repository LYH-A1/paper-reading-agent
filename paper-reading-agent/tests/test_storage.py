import pytest
from backend.models.paper import Paper
from backend.storage.paper_store import PaperStore
from backend.storage.session_store import SessionStore

@pytest.mark.asyncio
async def test_add_and_get_paper():
    store = PaperStore()
    paper = Paper(title="Test", authors=["Alice"], raw_text="content")
    await store.add_paper(paper)
    retrieved = await store.get_paper(paper.paper_id)
    assert retrieved is not None
    assert retrieved.title == "Test"
    assert retrieved.authors == ["Alice"]

@pytest.mark.asyncio
async def test_create_session_and_add_message():
    store = PaperStore()
    sstore = SessionStore()
    paper = Paper(title="Session Test")
    await store.add_paper(paper)

    session_id = await sstore.create_session(paper.paper_id)
    assert session_id

    await sstore.add_message(session_id, "user", "What is attention?")
    session = await sstore.get_session(session_id)
    assert session is not None
    assert len(session["messages"]) == 1
    assert session["messages"][0]["content"] == "What is attention?"

@pytest.mark.asyncio
async def test_list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    assert isinstance(papers, list)
