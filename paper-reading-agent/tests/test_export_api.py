"""Tests for conversation export API."""
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_session_data():
    return {
        "session_id": "sess-001",
        "paper_id": "paper-001",
        "paper_title": "Test Paper",
        "created_at": "2026-06-18 14:30:00",
        "updated_at": "2026-06-18 14:31:00",
        "messages": [
            {"role": "user", "content": "What is the method?", "meta": {}, "created_at": "2026-06-18 14:30:00"},
            {
                "role": "assistant",
                "content": "The method uses transformers.",
                "meta": {
                    "evidence_list": [
                        {
                            "evidence_id": "ev1", "level": "R0", "claim": "claim",
                            "page": 4, "quote": "We use transformers.",
                            "section_heading": "Method", "confidence": 0.95,
                            "sentence_index": None, "char_start": None, "char_end": None,
                            "source_title": None, "source_url": None,
                            "source_venue": None, "source_year": None,
                            "reasoning": None, "based_on_evidence_ids": [],
                        }
                    ],
                    "quality_score": {"relevance": 3, "consistency": 3, "completeness": 2, "total": 8},
                    "trace": ["reader", "classify", "planner"],
                    "followup_questions": ["Q1?", "Q2?"],
                },
                "created_at": "2026-06-18 14:31:00",
            },
        ],
    }


class TestExportMarkdown:
    def test_returns_markdown_content_type(self, mock_session_data):
        from backend.app import app
        from backend.storage.session_store import SessionStore

        client = TestClient(app)

        async def mock_get(self, sid):
            return mock_session_data if sid == "sess-001" else None

        with patch.object(SessionStore, "get_session_with_paper", mock_get):
            response = client.get("/api/sessions/sess-001/export?format=md")

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        body = response.text
        assert "# Session:" in body
        assert "## Q: What is the method?" in body
        assert "**Answer:** The method uses transformers." in body
        assert "[R0]" in body
        assert "**Quality:** 8/10" in body
        assert "## Suggested Follow-ups" in body
        assert "Q1?" in body

    def test_session_not_found_returns_404(self):
        from backend.app import app
        from backend.storage.session_store import SessionStore

        client = TestClient(app)

        async def mock_none(self, sid):
            return None

        with patch.object(SessionStore, "get_session_with_paper", mock_none):
            response = client.get("/api/sessions/nonexistent/export?format=md")

        assert response.status_code == 404


class TestExportJSON:
    def test_returns_json_content_type(self, mock_session_data):
        from backend.app import app
        from backend.storage.session_store import SessionStore

        client = TestClient(app)

        async def mock_get(self, sid):
            return mock_session_data if sid == "sess-001" else None

        with patch.object(SessionStore, "get_session_with_paper", mock_get):
            response = client.get("/api/sessions/sess-001/export?format=json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        body = response.json()
        assert body["session_id"] == "sess-001"
        assert body["paper_title"] == "Test Paper"
        assert "exported_at" in body
        assert len(body["messages"]) == 2
