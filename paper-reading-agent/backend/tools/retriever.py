import uuid
from backend.models.paper import Paper
from backend.models.state import RetrievedChunk
from backend.utils.text_splitter import split_text
from backend.utils.logger import logger

# Module-level retriever cache to avoid storing non-serializable objects
# (SentenceTransformer, ChromaDB client, BM25 index) in LangGraph state.
_retriever_cache: dict[str, "HybridRetriever"] = {}


def get_cached_retriever(paper: Paper) -> "HybridRetriever | None":
    """Get a cached retriever for the given paper, or build and cache one."""
    key = paper.paper_id or paper.file_path or ""
    if key in _retriever_cache:
        return _retriever_cache[key]
    try:
        retriever = HybridRetriever(paper)
        _retriever_cache[key] = retriever
        return retriever
    except Exception as e:
        logger.warning(f"Retriever index build failed: {e}, proceeding without retrieval")
        return None


def clear_retriever_cache(paper_id: str = "") -> None:
    """Clear cached retriever(s). If paper_id is empty, clear all."""
    if paper_id:
        _retriever_cache.pop(paper_id, None)
    else:
        _retriever_cache.clear()
from backend.tools.reranker import Reranker, get_reranker

class HybridRetriever:
    """Hybrid RAG: BM25 + ChromaDB with pluggable reranker."""
    def __init__(self, paper: Paper, embedding_model: str = "auto", reranker: Reranker | None = None):
        self.paper = paper
        self.reranker = reranker if reranker is not None else get_reranker()
        self.chunks = self._build_chunks()
        self._build_indices(embedding_model)

    def _build_chunks(self) -> list[dict]:
        raw = split_text(self.paper.raw_text, self.paper.sections)
        if not raw:
            return [{"chunk_id": str(uuid.uuid4()), "text": self.paper.abstract, "page": 1, "section_heading": "Abstract"}]
        return raw

    def _build_indices(self, embedding_model: str):
        # BM25
        from rank_bm25 import BM25Okapi
        self._choose_tokenizer()
        tokenized = [self._tokenize(c["text"]) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized)

        # ChromaDB
        import chromadb
        from sentence_transformers import SentenceTransformer
        model_name = "all-MiniLM-L6-v2"
        if self.paper.language == "zh":
            model_name = "BAAI/bge-large-zh-v1.5"
        if embedding_model != "auto":
            model_name = embedding_model
        self.embedder = SentenceTransformer(model_name)
        self.chroma = chromadb.Client()
        try:
            self.chroma.delete_collection("paper_chunks")
        except Exception:
            pass
        self.collection = self.chroma.create_collection("paper_chunks")
        embeddings = self.embedder.encode([c["text"] for c in self.chunks]).tolist()
        self.collection.add(
            ids=[c["chunk_id"] for c in self.chunks],
            documents=[c["text"] for c in self.chunks],
            embeddings=embeddings,
            metadatas=[{"page": c["page"], "section": c["section_heading"]} for c in self.chunks]
        )

    def _choose_tokenizer(self):
        if self.paper.language == "zh":
            try:
                import jieba
                self._tokenize = lambda text: list(jieba.cut(text))
            except ImportError:
                self._tokenize = lambda text: text.split()
        else:
            self._tokenize = lambda text: text.split()

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if self.paper.language == "en" and self._is_chinese(query):
            query = self._translate_query(query)

        bm25_results = self._bm25_search(query, top_k * 4)
        dense_results = self._dense_search(query, top_k * 4)
        merged = self._merge(bm25_results, dense_results)

        if not merged:
            return [RetrievedChunk(
                chunk_id="abstract-fallback", text=self.paper.abstract,
                page=1, section_heading="Abstract", source="fallback", scores={}
            )]

        # Phase 3: rerank merged results with pluggable reranker
        merged = self.reranker.rerank(query, merged)
        results = merged[:top_k]

        # Low-score detection after rerank
        avg_score = (
            sum(c.scores.get("rerank", c.scores.get("bm25", 0)) for c in results) / len(results)
            if results else 0
        )
        if avg_score < 0.3:
            logger.warning(f"Low average relevance: {avg_score:.2f}, expanding to top-10")
            results = merged[:10]

        for c in results:
            c.source = c.source or "rerank"

        return results

    def _bm25_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        tokens = self._tokenize(query)
        scores = self.bm25.get_scores(tokens)
        indexed = [(i, s) for i, s in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        results = []
        for i, score in indexed[:top_k]:
            c = self.chunks[i]
            results.append(RetrievedChunk(
                chunk_id=c["chunk_id"], text=c["text"], page=c["page"],
                section_heading=c.get("section_heading", ""), source="bm25",
                scores={"bm25": float(score)}
            ))
        return results

    def _dense_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        try:
            q_embedding = self.embedder.encode([query]).tolist()
            results = self.collection.query(query_embeddings=q_embedding, n_results=top_k)
            chunks = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                doc = results["documents"][0][i]
                dist = results["distances"][0][i] if "distances" in results else 0
                chunks.append(RetrievedChunk(
                    chunk_id=doc_id, text=doc, page=meta.get("page", 1),
                    section_heading=meta.get("section", ""), source="dense",
                    scores={"dense": float(1.0 - dist) if dist else 0.5}
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Dense search failed: {e}, falling back to BM25 only")
            return []

    def _merge(self, bm25: list[RetrievedChunk], dense: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Merge and deduplicate. No cross-scale sorting."""
        seen: set[str] = set()
        merged = []
        for chunk in bm25 + dense:
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                merged.append(chunk)
        return merged

    def _is_chinese(self, text: str) -> bool:
        return any('一' <= c <= '鿿' for c in text)

    def _translate_query(self, query: str) -> str:
        """Phase 1: passthrough. LLM translation added when client is available."""
        return query
