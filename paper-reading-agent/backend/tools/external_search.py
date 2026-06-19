"""External paper search: arXiv API + Semantic Scholar enrichment."""

import asyncio
import time
import uuid
import os
from dataclasses import dataclass, field
from xml.etree import ElementTree
from urllib.parse import quote

from backend.utils.logger import logger

EXTERNAL_SEARCH_TIMEOUT = 15.0
ARXIV_REQUEST_INTERVAL = float(os.getenv("ARXIV_REQUEST_INTERVAL", "3.0"))


@dataclass
class ExternalResult:
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    url: str = ""
    source: str = ""            # "arxiv" | "semantic_scholar"
    citation_count: int | None = None
    related_titles: list[str] = field(default_factory=list)


class ExternalRetriever:
    """Search arXiv for papers, optionally enrich with Semantic Scholar citations."""

    def __init__(self):
        self._last_request_time: float = 0.0
        self._s2_api_key: str = os.getenv("S2_API_KEY", "")

    async def search(self, query: str, top_k: int = 5) -> list[ExternalResult]:
        """Main entry: search arXiv, enrich with S2 if available."""
        results = await self._search_arxiv(query, top_k)
        if results and self._s2_api_key:
            try:
                results = await self._enrich_with_s2(results)
            except Exception:
                logger.warning("S2 enrichment failed, returning arXiv-only results")
        return results

    async def _search_arxiv(self, query: str, max_results: int) -> list[ExternalResult]:
        """Query arXiv API and parse Atom XML response."""
        await self._respect_rate_limit()

        encoded = quote(query)
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=all:{encoded}&max_results={max_results}&sortBy=relevance"
        )
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                xml_text = resp.text
        except Exception as e:
            logger.error(f"arXiv API request failed: {e}")
            raise

        return self._parse_arxiv_xml(xml_text)

    async def _respect_rate_limit(self) -> None:
        """Ensure at least ARXIV_REQUEST_INTERVAL seconds between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < ARXIV_REQUEST_INTERVAL:
            await asyncio.sleep(ARXIV_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _parse_arxiv_xml(self, xml_text: str) -> list[ExternalResult]:
        """Parse arXiv Atom XML into ExternalResult list."""
        root = ElementTree.fromstring(xml_text)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        results = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

            authors = []
            for author_el in entry.findall("atom:author", ns):
                name_el = author_el.find("atom:name", ns)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())

            abstract_el = entry.find("atom:summary", ns)
            abstract = (abstract_el.text or "").strip()[:500] if abstract_el is not None else ""

            published_el = entry.find("atom:published", ns)
            year = None
            if published_el is not None and published_el.text:
                year = int(published_el.text[:4])

            arxiv_id = ""
            id_el = entry.find("atom:id", ns)
            if id_el is not None and id_el.text:
                arxiv_id = id_el.text.split("/abs/")[-1]

            url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""

            results.append(ExternalResult(
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                url=url,
                source="arxiv",
            ))
        return results

    async def fetch_by_id(self, arxiv_id: str) -> ExternalResult | None:
        """Fetch a single paper's metadata from arXiv by ID."""
        await self._respect_rate_limit()
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                results = self._parse_arxiv_xml(resp.text)
                return results[0] if results else None
        except Exception as e:
            logger.error(f"arXiv fetch_by_id failed for {arxiv_id}: {e}")
            return None

    async def _enrich_with_s2(self, results: list[ExternalResult]) -> list[ExternalResult]:
        """Enrich results with citation counts and related titles from S2."""
        import httpx

        async def _fetch_one(r: ExternalResult) -> ExternalResult:
            if not r.title:
                return r
            encoded = quote(r.title)
            url = (
                f"https://api.semanticscholar.org/graph/v1/paper/search/match"
                f"?query={encoded}&fields=citationCount,citations.title"
            )
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        url,
                        headers={"x-api-key": self._s2_api_key},
                    )
                    if resp.status_code == 429:
                        logger.warning("S2 rate limited (429), skipping enrichment")
                        return r
                    resp.raise_for_status()
                    data = resp.json()
            except Exception:
                return r

            paper = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            if paper:
                r.citation_count = paper.get("citationCount")
                citations = paper.get("citations", [])
                r.related_titles = [c.get("title", "") for c in citations[:3] if c.get("title")]
            r.source = "semantic_scholar" if r.citation_count is not None else "arxiv"
            return r

        tasks = [_fetch_one(r) for r in results]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)
        return [e if not isinstance(e, Exception) else r for e, r in zip(enriched, results)]
