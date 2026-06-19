"""Tests for BibTeX export API endpoint."""
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.models.paper import Paper, Reference
from backend.storage.paper_store import PaperStore


class TestBibtexExport:
    """BibTeX export integration tests using real PaperStore."""

    def test_export_bibtex_empty_references(self):
        """Paper with no references returns comment-only .bib."""
        store = PaperStore()
        paper = Paper(title="Empty Paper", references=[])
        import asyncio
        asyncio.run(store.add_paper(paper))

        client = TestClient(app)
        res = client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
        assert res.status_code == 200
        assert "% No references found" in res.text

    def test_export_bibtex_not_found(self):
        """Non-existent paper returns 404."""
        client = TestClient(app)
        res = client.get("/api/papers/nonexistent-id/references/export?format=bib")
        assert res.status_code == 404

    def test_export_bibtex_article(self):
        """Journal article reference exports correctly."""
        store = PaperStore()
        paper = Paper(
            title="Test Paper",
            references=[
                Reference(
                    title="A Novel Method",
                    authors=["Alice Smith", "Bob Jones"],
                    year=2023,
                    venue="Journal of Testing",
                    doi="10.1234/test.999",
                )
            ],
        )
        import asyncio
        asyncio.run(store.add_paper(paper))

        client = TestClient(app)
        res = client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
        assert res.status_code == 200
        text = res.text
        assert "@article" in text
        assert "A Novel Method" in text
        assert "Smith, Alice" in text
        assert "Jones, Bob" in text
        assert "2023" in text
        assert "Journal of Testing" in text
        assert "10.1234/test.999" in text
        assert "Content-Disposition" in res.headers

    def test_export_bibtex_inproceedings(self):
        """Conference paper detected via keyword in venue."""
        store = PaperStore()
        paper = Paper(
            title="Test",
            references=[
                Reference(
                    title="Deep Learning",
                    authors=["Kaiming He"],
                    year=2016,
                    venue="Proceedings of CVPR",
                )
            ],
        )
        import asyncio
        asyncio.run(store.add_paper(paper))

        client = TestClient(app)
        res = client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
        assert res.status_code == 200
        assert "@inproceedings" in res.text
        assert "booktitle" in res.text

    def test_export_bibtex_chinese_author(self):
        """Chinese author name degrades to anonymous in cite_key."""
        store = PaperStore()
        paper = Paper(
            title="Test",
            references=[
                Reference(title="Some Paper About AI", authors=["张伟"], year=2024)
            ],
        )
        import asyncio
        asyncio.run(store.add_paper(paper))

        client = TestClient(app)
        res = client.get(f"/api/papers/{paper.paper_id}/references/export?format=bib")
        assert res.status_code == 200
        assert "anonymous" in res.text.lower()

    def test_export_bibtex_bad_format(self):
        """Non-bib format returns 400."""
        store = PaperStore()
        paper = Paper(title="Test", references=[])
        import asyncio
        asyncio.run(store.add_paper(paper))

        client = TestClient(app)
        res = client.get(f"/api/papers/{paper.paper_id}/references/export?format=json")
        assert res.status_code == 400
