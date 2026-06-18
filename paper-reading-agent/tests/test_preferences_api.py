"""Tests for preferences API."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.app import app
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock the database to have an in-memory preferences table."""
    import aiosqlite

    async def make_conn():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')"
        )
        await conn.commit()
        return conn

    return make_conn


class TestGetPreferences:
    def test_returns_defaults_when_empty(self, client, mock_db):
        with patch("backend.app.db.get_db", mock_db):
            response = client.get("/api/preferences")
        assert response.status_code == 200
        data = response.json()
        assert data["reranker"] == "flashrank"
        assert data["top_k"] == 5
        assert data["language"] == "auto"
        assert data["embedding_model"] == "auto"


class TestPutPreferences:
    def test_valid_update_returns_ok(self, client, mock_db):
        with patch("backend.app.db.get_db", mock_db):
            response = client.put("/api/preferences", json={"reranker": "bm25", "top_k": 10})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_invalid_key_returns_400(self, client, mock_db):
        with patch("backend.app.db.get_db", mock_db):
            response = client.put("/api/preferences", json={"invalid_key": "value"})
        assert response.status_code == 400

    def test_invalid_top_k_range_returns_400(self, client, mock_db):
        with patch("backend.app.db.get_db", mock_db):
            response = client.put("/api/preferences", json={"top_k": 100})
        assert response.status_code == 400

    def test_invalid_reranker_value_returns_400(self, client, mock_db):
        with patch("backend.app.db.get_db", mock_db):
            response = client.put("/api/preferences", json={"reranker": "unknown"})
        assert response.status_code == 400
