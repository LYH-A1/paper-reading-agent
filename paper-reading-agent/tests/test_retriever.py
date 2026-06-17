"""Tests for HybridRetriever using mocks to skip heavy dependencies."""
import pytest
from unittest.mock import patch, MagicMock
from backend.models.paper import Paper, Section
from backend.models.state import RetrievedChunk

@pytest.fixture
def sample_paper():
    sections = [
        Section(heading="1. Intro", content="Transformers revolutionized NLP.", page_start=1, page_end=1),
        Section(heading="2. Method", content="We use multi-head self-attention.", page_start=2, page_end=2),
    ]
    raw = "Transformers revolutionized NLP.\n\nWe use multi-head self-attention."
    return Paper(title="Test", abstract="Test abstract", sections=sections, raw_text=raw)

@pytest.fixture
def retriever(sample_paper):
    """Build retriever with mocked heavy dependencies."""
    from backend.tools.retriever import HybridRetriever
    # Mock _build_indices to skip chromadb+sentence-transformers download
    with patch.object(HybridRetriever, '_build_indices', return_value=None):
        r = HybridRetriever.__new__(HybridRetriever)
        r.paper = sample_paper
        r.chunks = r._build_chunks()
        r.bm25 = MagicMock()
        r.bm25.get_scores.return_value = []
        r.collection = MagicMock()
        r.embedder = MagicMock()
        r._choose_tokenizer()
        return r

def test_retriever_has_chunks(retriever):
    """Retriever splits paper into chunks."""
    assert len(retriever.chunks) > 0
    assert "chunk_id" in retriever.chunks[0]
    assert "text" in retriever.chunks[0]

def test_bm25_returns_results(retriever):
    """BM25 search returns RetrievedChunk objects."""
    retriever.bm25.get_scores.return_value = [0.5, 0.3, 0.1]
    results = retriever._bm25_search("attention", top_k=2)
    assert len(results) == 2
    assert all(isinstance(r, RetrievedChunk) for r in results)
    assert results[0].source == "bm25"

def test_merge_deduplicates(retriever):
    """Merge removes duplicate chunk_ids."""
    c1 = RetrievedChunk(chunk_id="a", text="t1", page=1, source="bm25", scores={"bm25": 0.9})
    c2 = RetrievedChunk(chunk_id="a", text="t1", page=1, source="dense", scores={"dense": 0.8})
    c3 = RetrievedChunk(chunk_id="b", text="t2", page=2, source="bm25", scores={"bm25": 0.5})
    merged = retriever._merge([c1], [c2, c3])
    assert len(merged) == 2  # a appears once, b once

def test_retrieve_fallback(retriever):
    """When searches return empty, abstract fallback is used."""
    retriever._bm25_search = lambda q, k: []
    retriever._dense_search = lambda q, k: []
    results = retriever.retrieve("xyz", top_k=3)
    assert len(results) == 1
    assert results[0].source == "fallback"
    assert results[0].text == retriever.paper.abstract

def test_is_chinese(retriever):
    """Chinese text detection works."""
    assert retriever._is_chinese("这是什么")
    assert not retriever._is_chinese("what is this")
