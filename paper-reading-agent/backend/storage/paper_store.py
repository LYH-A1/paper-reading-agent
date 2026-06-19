import json
import re
from backend.models.paper import Paper, Reference
from backend.storage.database import db


def _ref_to_dict(ref: Reference) -> dict:
    return {
        "title": ref.title,
        "authors": ref.authors,
        "year": ref.year,
        "venue": ref.venue,
        "doi": ref.doi,
        "url": ref.url,
    }


def _dict_to_ref(d: dict) -> Reference:
    return Reference(
        title=d.get("title", ""),
        authors=d.get("authors", []),
        year=d.get("year"),
        venue=d.get("venue"),
        doi=d.get("doi"),
        url=d.get("url"),
    )


def _slugify_title(title: str) -> str:
    """Normalize title for matching: lowercase + remove punctuation/extra whitespace."""
    slug = title.lower()
    slug = re.sub(r'[^\w\s]', '', slug)
    slug = re.sub(r'\s+', ' ', slug).strip()
    return slug


def _row_to_paper(row) -> Paper:
    """Convert a database row (aiosqlite.Row or dict) to a Paper object."""
    refs_raw = row["references"] if "references" in row.keys() else "[]"
    arxiv_id = row["arxiv_id"] if "arxiv_id" in row.keys() else None
    import_source = row["import_source"] if "import_source" in row.keys() else "upload"
    file_path = row["file_path"] or None
    return Paper(
        paper_id=row["paper_id"], title=row["title"],
        authors=json.loads(row["authors"]), abstract=row["abstract"],
        metadata=json.loads(row["metadata"]), raw_text=row["raw_text"],
        language=row["language"], file_path=file_path,
        parsed_at=row["parsed_at"],
        references=[_dict_to_ref(r) for r in json.loads(refs_raw)],
        arxiv_id=arxiv_id,
        import_source=import_source,
    )


class PaperStore:
    async def add_paper(self, paper: Paper) -> Paper:
        conn = await db.get_db()
        try:
            await conn.execute(
                """INSERT OR REPLACE INTO papers
                   (paper_id, title, authors, abstract, metadata, raw_text, language, file_path, parsed_at, "references", arxiv_id, import_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (paper.paper_id, paper.title, json.dumps(paper.authors), paper.abstract,
                 json.dumps(paper.metadata), paper.raw_text, paper.language, paper.file_path,
                 paper.parsed_at, json.dumps([_ref_to_dict(r) for r in paper.references]),
                 paper.arxiv_id, paper.import_source)
            )
            await conn.commit()
            return paper
        finally:
            await conn.close()

    async def get_paper(self, paper_id: str) -> Paper | None:
        conn = await db.get_db()
        try:
            async with conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return _row_to_paper(row)
        finally:
            await conn.close()

    async def list_papers(self) -> list[Paper]:
        conn = await db.get_db()
        try:
            papers = []
            async with conn.execute(
                "SELECT * FROM papers ORDER BY parsed_at DESC"
            ) as cursor:
                async for row in cursor:
                    papers.append(_row_to_paper(row))
            return papers
        finally:
            await conn.close()

    async def delete_paper(self, paper_id: str) -> bool:
        conn = await db.get_db()
        try:
            cursor = await conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def get_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Find paper by arXiv ID. Returns None if not found."""
        conn = await db.get_db()
        try:
            async with conn.execute(
                "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return _row_to_paper(row)
        finally:
            await conn.close()

    async def get_by_title_slug(self, slug: str) -> Paper | None:
        """Find paper by title slug match. Returns None if no match."""
        conn = await db.get_db()
        try:
            async with conn.execute("SELECT * FROM papers") as cursor:
                async for row in cursor:
                    if _slugify_title(row["title"]) == slug:
                        return _row_to_paper(row)
            return None
        finally:
            await conn.close()
