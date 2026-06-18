"""Tests for pluggable reranker module."""
import os
import sys
import pytest
from backend.models.state import RetrievedChunk


def make_chunk(chunk_id: str, bm25: float = 0.0, dense: float = 0.0, text: str = "") -> RetrievedChunk:
    scores = {}
    if bm25:
        scores["bm25"] = bm25
    if dense:
        scores["dense"] = dense
    return RetrievedChunk(
        chunk_id=chunk_id, text=text or f"text-{chunk_id}", page=1,
        section_heading="Test", source="bm25", scores=scores,
    )


class TestBM25FallbackReranker:
    def test_sorts_by_bm25_descending(self):
        from backend.tools.reranker import BM25FallbackReranker
        reranker = BM25FallbackReranker()
        chunks = [
            make_chunk("a", bm25=0.3),
            make_chunk("b", bm25=0.9),
            make_chunk("c", bm25=0.5),
        ]
        result = reranker.rerank("test query", chunks)
        assert [c.chunk_id for c in result] == ["b", "c", "a"]

    def test_empty_passages_returns_empty(self):
        from backend.tools.reranker import BM25FallbackReranker
        result = BM25FallbackReranker().rerank("query", [])
        assert result == []

    def test_preserves_all_passages(self):
        from backend.tools.reranker import BM25FallbackReranker
        chunks = [make_chunk(str(i), bm25=float(i)) for i in range(5)]
        result = BM25FallbackReranker().rerank("q", chunks)
        assert len(result) == 5


class TestFlashRankReranker:
    def test_lazy_loading_does_not_load_on_init(self):
        """_ranker should be None after construction -- no download at init time."""
        from backend.tools.reranker import FlashRankReranker
        r = FlashRankReranker()
        assert r._ranker is None

    def test_ensure_loaded_calls_flashrank(self):
        """_ensure_loaded imports and creates Ranker."""
        from backend.tools.reranker import FlashRankReranker
        class MockRanker:
            def __init__(self, **kwargs):
                pass
        mock_flashrank = type("mock_mod", (), {"Ranker": MockRanker})()
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "flashrank", mock_flashrank)
            r = FlashRankReranker()
            r._ensure_loaded()
            assert r._ranker is not None
            assert isinstance(r._ranker, MockRanker)


class TestGetReranker:
    def test_default_returns_flashrank_when_available(self):
        from backend.tools.reranker import get_reranker, FlashRankReranker
        mock_ranker_cls = type("MockRanker", (), {})
        mock_flashrank = type("mock_mod", (), {"Ranker": mock_ranker_cls})()
        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "flashrank", mock_flashrank)
            r = get_reranker()
            assert isinstance(r, FlashRankReranker)

    def test_env_var_forces_bm25(self):
        from backend.tools.reranker import get_reranker, BM25FallbackReranker
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("RERANKER_BACKEND", "bm25")
            r = get_reranker()
            assert isinstance(r, BM25FallbackReranker)

    def test_explicit_bm25_returns_bm25(self):
        from backend.tools.reranker import get_reranker, BM25FallbackReranker
        r = get_reranker("bm25")
        assert isinstance(r, BM25FallbackReranker)
