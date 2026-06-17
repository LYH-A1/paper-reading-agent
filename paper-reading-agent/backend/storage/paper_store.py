import json
from backend.models.paper import Paper
from backend.storage.database import db

class PaperStore:
    async def add_paper(self, paper: Paper) -> Paper:
        conn = await db.get_db()
        try:
            await conn.execute(
                """INSERT OR REPLACE INTO papers (paper_id, title, authors, abstract, metadata, raw_text, language, file_path, parsed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (paper.paper_id, paper.title, json.dumps(paper.authors), paper.abstract,
                 json.dumps(paper.metadata), paper.raw_text, paper.language, paper.file_path, paper.parsed_at)
            )
            await conn.commit()
            return paper
        finally:
            await conn.close()

    async def get_paper(self, paper_id: str) -> Paper | None:
        conn = await db.get_db()
        try:
            async with conn.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return Paper(
                    paper_id=row["paper_id"], title=row["title"],
                    authors=json.loads(row["authors"]), abstract=row["abstract"],
                    metadata=json.loads(row["metadata"]), raw_text=row["raw_text"],
                    language=row["language"], file_path=row["file_path"],
                    parsed_at=row["parsed_at"]
                )
        finally:
            await conn.close()

    async def list_papers(self) -> list[Paper]:
        conn = await db.get_db()
        try:
            papers = []
            async with conn.execute("SELECT paper_id, title, authors, parsed_at FROM papers ORDER BY parsed_at DESC") as cursor:
                async for row in cursor:
                    papers.append(Paper(
                        paper_id=row["paper_id"], title=row["title"],
                        authors=json.loads(row["authors"]), parsed_at=row["parsed_at"]
                    ))
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
