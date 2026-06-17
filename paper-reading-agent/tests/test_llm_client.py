import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.llm.client import LLMClient
from backend.config import LLMConfig


@pytest.fixture
def client():
    cfg = LLMConfig(base_url="https://test.api/v1", auth_token="test-key", model="test-model")
    return LLMClient(cfg)


@pytest.mark.asyncio
async def test_chat_basic(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "content": [{"text": "Hello, world!"}],
        "usage": {"output_tokens": 10}
    }
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        content, usage = await client.chat([{"role": "user", "content": "Hi"}])
        assert content == "Hello, world!"
        assert usage["output_tokens"] == 10
