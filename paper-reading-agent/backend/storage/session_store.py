import json
import uuid
from backend.storage.database import db

class SessionStore:
    async def create_session(self, paper_id: str) -> str:
        session_id = str(uuid.uuid4())
        conn = await db.get_db()
        try:
            await conn.execute("INSERT INTO sessions (session_id, paper_id) VALUES (?, ?)", (session_id, paper_id))
            await conn.commit()
            return session_id
        finally:
            await conn.close()

    async def add_message(self, session_id: str, role: str, content: str, meta: dict | None = None):
        conn = await db.get_db()
        try:
            await conn.execute(
                "INSERT INTO messages (session_id, role, content, meta) VALUES (?, ?, ?, ?)",
                (session_id, role, content, json.dumps(meta or {}))
            )
            await conn.execute("UPDATE sessions SET updated_at = datetime('now') WHERE session_id = ?", (session_id,))
            await conn.commit()
        finally:
            await conn.close()

    async def get_session(self, session_id: str) -> dict | None:
        conn = await db.get_db()
        try:
            async with conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
                session_row = await cursor.fetchone()
                if not session_row:
                    return None
            messages = []
            async with conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY message_id", (session_id,)) as cursor:
                async for row in cursor:
                    messages.append({"role": row["role"], "content": row["content"], "meta": json.loads(row["meta"])})
            return {
                "session_id": session_row["session_id"], "paper_id": session_row["paper_id"],
                "created_at": session_row["created_at"], "updated_at": session_row["updated_at"],
                "messages": messages
            }
        finally:
            await conn.close()

    async def get_session_with_paper(self, session_id: str) -> dict | None:
        """Get session with paper title joined."""
        conn = await db.get_db()
        try:
            async with conn.execute(
                """SELECT s.*, p.title as paper_title
                   FROM sessions s
                   JOIN papers p ON s.paper_id = p.paper_id
                   WHERE s.session_id = ?""",
                (session_id,),
            ) as cursor:
                session_row = await cursor.fetchone()
                if not session_row:
                    return None

            messages = []
            async with conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY message_id",
                (session_id,),
            ) as cursor:
                async for row in cursor:
                    messages.append({
                        "role": row["role"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"]) if row["meta"] else {},
                        "created_at": row["created_at"],
                    })

            return {
                "session_id": session_row["session_id"],
                "paper_id": session_row["paper_id"],
                "paper_title": session_row["paper_title"],
                "created_at": session_row["created_at"],
                "updated_at": session_row["updated_at"],
                "messages": messages,
            }
        finally:
            await conn.close()

    async def list_sessions(self, paper_id: str) -> list[dict]:
        conn = await db.get_db()
        try:
            results = []
            async with conn.execute("SELECT * FROM sessions WHERE paper_id = ? ORDER BY updated_at DESC", (paper_id,)) as cursor:
                async for row in cursor:
                    results.append(dict(row))
            return results
        finally:
            await conn.close()
