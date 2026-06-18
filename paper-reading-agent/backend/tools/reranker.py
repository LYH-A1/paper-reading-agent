"""Pluggable reranker module for HybridRetriever.

- Reranker: abstract interface
- FlashRankReranker: cross-encoder reranker with lazy model loading
- BM25FallbackReranker: zero-dependency fallback using BM25 scores
- get_reranker(): factory with env var override and auto-degrade
"""

import os
from abc import ABC, abstractmethod
from backend.models.state import RetrievedChunk
from backend.utils.logger import logger


class RerankerLoadError(Exception):
    """Raised when a reranker model fails to load (e.g. download failure)."""


class Reranker(ABC):
    """Abstract reranker interface."""

    @abstractmethod
    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Re-rank passages by relevance to query. Returns passages sorted best-first."""


class BM25FallbackReranker(Reranker):
    """Zero-dependency fallback: sort by existing BM25 score descending."""

    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return sorted(
            passages,
            key=lambda c: c.scores.get("bm25", 0),
            reverse=True,
        )


class FlashRankReranker(Reranker):
    """Cross-encoder reranker using the flashrank library.

    Model is downloaded lazily on first ``rerank()`` call so service startup
    is never blocked. If loading fails the factory function degrades to BM25.
    """

    def __init__(self, model: str = "ms-marco-MiniLM-L-12-v2"):
        self.model_name = model
        self._ranker = None  # lazy -- loaded on first rerank()

    def _ensure_loaded(self) -> None:
        if self._ranker is None:
            try:
                from flashrank import Ranker
                self._ranker = Ranker(model_name=self.model_name)
            except Exception as e:
                raise RerankerLoadError(
                    f"FlashRank model '{self.model_name}' failed to load: {e}"
                ) from e

    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not passages:
            return []

        self._ensure_loaded()

        # Build flashrank input
        rank_input = [
            {"id": p.chunk_id, "text": p.text}
            for p in passages
        ]

        try:
            scored = self._ranker.rerank(query, rank_input)
        except Exception:
            logger.warning("FlashRank rerank failed, returning original order")
            return passages

        # Map scores back to RetrievedChunk
        score_map: dict[str, float] = {}
        for item in scored:
            score_map[item["id"]] = float(item.get("score", 0))

        for p in passages:
            p.scores["rerank"] = score_map.get(p.chunk_id, 0)

        passages.sort(key=lambda c: c.scores.get("rerank", 0), reverse=True)
        return passages


def get_reranker(name: str | None = None) -> Reranker:
    """Factory: return a reranker instance.

    Resolution order:
    1. Explicit ``name`` argument (``"flashrank"`` or ``"bm25"``)
    2. ``RERANKER_BACKEND`` environment variable (default ``"flashrank"``)
    3. If FlashRank requested but unavailable, auto-degrade to BM25

    Returns:
        Reranker instance.
    """
    backend = name or os.getenv("RERANKER_BACKEND", "flashrank")

    if backend == "flashrank":
        try:
            return FlashRankReranker()
        except RerankerLoadError:
            logger.warning(
                "FlashRank unavailable, falling back to BM25 reranker. "
                "Set RERANKER_BACKEND=bm25 to suppress this warning."
            )
            return BM25FallbackReranker()

    return BM25FallbackReranker()
