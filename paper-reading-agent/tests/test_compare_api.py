import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app


@pytest.mark.asyncio
async def test_compare_missing_paper_ids():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/compare", json={"paper_ids": []})
        assert resp.status_code == 400
        assert "At least 2 papers" in resp.json()["error"]


@pytest.mark.asyncio
async def test_compare_too_many_papers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/compare", json={"paper_ids": ["1", "2", "3", "4", "5", "6"]})
        assert resp.status_code == 400
        assert "Maximum 5" in resp.json()["error"]


@pytest.mark.asyncio
async def test_save_external_missing_arxiv_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/papers/save-external", json={})
        assert resp.status_code == 400
        assert "arxiv_id" in resp.json()["error"]


@pytest.mark.asyncio
async def test_save_external_invalid_arxiv_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/papers/save-external", json={"arxiv_id": "not-valid"})
        assert resp.status_code == 400
        assert "Invalid arXiv ID" in resp.json()["error"]


@pytest.mark.asyncio
async def test_import_bibtex_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/papers/import-bibtex", json={"bibtex_content": ""})
        assert resp.status_code == 400
        assert "Empty" in resp.json()["error"]
