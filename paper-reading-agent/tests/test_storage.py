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


@pytest.mark.asyncio
async def test_paper_references_roundtrip():
    """References are persisted and loaded correctly."""
    from backend.models.paper import Paper, Reference
    from backend.storage.paper_store import PaperStore
    store = PaperStore()
    paper = Paper(
        title="Test Paper",
        references=[
            Reference(title="Ref One", authors=["Alice Bob"], year=2020, venue="Test Venue", doi="10.1234/test"),
            Reference(title="Ref Two", authors=["Charlie"], year=2021),
        ],
    )
    await store.add_paper(paper)
    loaded = await store.get_paper(paper.paper_id)
    assert loaded is not None
    assert len(loaded.references) == 2
    assert loaded.references[0].title == "Ref One"
    assert loaded.references[0].authors == ["Alice Bob"]
    assert loaded.references[0].year == 2020
    assert loaded.references[0].venue == "Test Venue"
    assert loaded.references[0].doi == "10.1234/test"
    assert loaded.references[1].title == "Ref Two"


@pytest.mark.asyncio
async def test_paper_empty_references():
    """Paper with no references loads with empty list."""
    from backend.models.paper import Paper
    from backend.storage.paper_store import PaperStore
    store = PaperStore()
    paper = Paper(title="No Refs Paper")
    await store.add_paper(paper)
    loaded = await store.get_paper(paper.paper_id)
    assert loaded is not None
    assert loaded.references == []


@pytest.mark.asyncio
async def test_migration_adds_arxiv_id_column():
    from backend.storage.database import db
    conn = await db.get_db()
    try:
        async with conn.execute("SELECT arxiv_id FROM papers LIMIT 0") as cursor:
            pass  # column exists if no exception
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_migration_adds_import_source_column():
    from backend.storage.database import db
    conn = await db.get_db()
    try:
        async with conn.execute("SELECT import_source FROM papers LIMIT 0") as cursor:
            pass
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_add_paper_with_arxiv_fields():
    from backend.storage.paper_store import PaperStore
    from backend.models.paper import Paper
    store = PaperStore()
    paper = Paper(
        title="Test ArXiv Paper",
        authors=["Smith, J."],
        abstract="Test abstract.",
        arxiv_id="2401.12345",
        arxiv_pdf_url="https://arxiv.org/pdf/2401.12345.pdf",
        import_source="external_save",
        file_path=None,
    )
    saved = await store.add_paper(paper)
    assert saved.arxiv_id == "2401.12345"

    fetched = await store.get_paper(saved.paper_id)
    assert fetched is not None
    assert fetched.arxiv_id == "2401.12345"
    assert fetched.import_source == "external_save"
    assert fetched.file_path is None


@pytest.mark.asyncio
async def test_get_by_arxiv_id_found():
    from backend.storage.paper_store import PaperStore
    from backend.models.paper import Paper
    store = PaperStore()
    paper = Paper(title="Unique Paper", arxiv_id="9999.99999", import_source="external_save")
    await store.add_paper(paper)
    found = await store.get_by_arxiv_id("9999.99999")
    assert found is not None
    assert found.title == "Unique Paper"

@pytest.mark.asyncio
async def test_get_by_arxiv_id_not_found():
    from backend.storage.paper_store import PaperStore
    store = PaperStore()
    found = await store.get_by_arxiv_id("nonexistent.00000")
    assert found is None

@pytest.mark.asyncio
async def test_get_by_title_slug_found():
    from backend.storage.paper_store import PaperStore
    from backend.models.paper import Paper
    store = PaperStore()
    paper = Paper(title="Attention Is All You Need!", import_source="bib_import")
    await store.add_paper(paper)
    found = await store.get_by_title_slug("attention is all you need")
    assert found is not None

@pytest.mark.asyncio
async def test_get_by_title_slug_not_found():
    from backend.storage.paper_store import PaperStore
    store = PaperStore()
    found = await store.get_by_title_slug("nonexistent paper title")
    assert found is None

@pytest.mark.asyncio
async def test_list_papers_returns_full_fields():
    from backend.storage.paper_store import PaperStore
    from backend.models.paper import Paper
    store = PaperStore()
    paper = Paper(
        title="Searchable Paper",
        authors=["Test Author"],
        abstract="This paper discusses testing.",
        import_source="bib_import",
        arxiv_id="2401.99999",
    )
    await store.add_paper(paper)

    papers = await store.list_papers()
    found = next((p for p in papers if p.paper_id == paper.paper_id), None)
    assert found is not None
    assert found.import_source == "bib_import"
    assert found.arxiv_id == "2401.99999"
    assert found.authors == ["Test Author"]


def test_slugify_title():
    from backend.storage.paper_store import _slugify_title
    assert _slugify_title("Attention Is All You Need!") == "attention is all you need"
    assert _slugify_title("BERT: Pre-training of Deep Bidirectional Transformers") == "bert pretraining of deep bidirectional transformers"
    assert _slugify_title("  Extra   Spaces  ") == "extra spaces"
