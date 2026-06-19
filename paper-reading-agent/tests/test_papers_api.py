import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app, _snippet


def test_snippet_no_truncation():
    assert _snippet("Hello world", 200) == "Hello world"


def test_snippet_truncates_at_word_boundary():
    result = _snippet("Hello world this is a test of the emergency broadcast system", 30)
    assert len(result) <= 33
    assert result.endswith("...")


def test_snippet_short_max_len():
    result = _snippet("Supercalifragilisticexpialidocious", 10)
    assert result.endswith("...")


@pytest.mark.asyncio
async def test_list_papers_returns_new_fields():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/papers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            paper = data[0]
            assert "authors" in paper
            assert "abstract_snippet" in paper
            assert "import_source" in paper
            assert "arxiv_id" in paper


@pytest.mark.asyncio
async def test_list_papers_import_source_values():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/papers")
        data = resp.json()
        for paper in data:
            assert paper["import_source"] in ("upload", "bib_import", "external_save")
