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
        "content": [{"type": "text", "text": "Hello, world!"}],
        "usage": {"output_tokens": 10}
    }
    mock_resp.status_code = 200

    with patch("backend.llm.client.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        content, usage = await client.chat([{"role": "user", "content": "Hi"}])
        assert content == "Hello, world!"
        assert usage["output_tokens"] == 10


class TestExtractJson:
    """Tests for LLMClient._extract_json — the JSON extraction helper."""

    def test_direct_json(self, client):
        assert client._extract_json('{"intent": "qa"}') == '{"intent": "qa"}'

    def test_json_with_surrounding_text(self, client):
        result = client._extract_json('Some text {"intent": "summary", "confidence": 0.9} trailing')
        assert result == '{"intent": "summary", "confidence": 0.9}'

    def test_json_in_markdown_block(self, client):
        result = client._extract_json('```json\n{"key": "value"}\n```')
        assert result == '{"key": "value"}'

    def test_json_in_markdown_block_no_lang(self, client):
        result = client._extract_json('```\n{"key": "value"}\n```')
        assert result == '{"key": "value"}'

    def test_whitespace_only(self, client):
        result = client._extract_json('  \n  {"a": 1}  \n  ')
        assert result == '{"a": 1}'

    def test_nested_braces(self, client):
        result = client._extract_json('{"outer": {"inner": [1, 2, 3]}, "key": "val"}')
        assert result == '{"outer": {"inner": [1, 2, 3]}, "key": "val"}'

    def test_multiple_markdown_blocks(self, client):
        content = '```\nnot json\n```\nThe answer is:\n```json\n{"intent": "qa"}\n```'
        result = client._extract_json(content)
        assert result == '{"intent": "qa"}'

    def test_array_json(self, client):
        result = client._extract_json('Output: ["item1", "item2", "item3"] done')
        assert '[' in result and ']' in result


class TestChatStream:
    """Tests for chat_stream — verify client lifecycle is managed correctly."""

    @staticmethod
    def _make_mock_response(lines: list[str], fail_after: bool = False):
        """Create a mock (client, response) pair for _call_stream."""

        class MockStreamResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            async def aiter_lines(self):
                for line in lines:
                    yield line
                if fail_after:
                    raise ConnectionError("Simulated stream failure")

            async def aclose(self):
                pass

        class MockClient:
            async def aclose(self):
                pass

        return MockClient(), MockStreamResponse()

    @pytest.mark.asyncio
    async def test_stream_chunks_yielded(self, client):
        """Verify SSE chunks are correctly parsed and yielded."""
        sse_lines = [
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}',
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": ", "}}',
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "world!"}}',
        ]

        with patch.object(client, "_call_stream", return_value=self._make_mock_response(sse_lines)):
            chunks = []
            async for chunk in client.chat_stream([{"role": "user", "content": "Hi"}]):
                chunks.append(chunk)

            assert chunks == ["Hello", ", ", "world!"]

    @pytest.mark.asyncio
    async def test_stream_client_closed_on_success(self, client):
        """Verify the HTTP client is closed after successful stream consumption."""
        close_calls = []

        class MockStreamResponse:
            status_code = 200
            def raise_for_status(self): pass
            async def aiter_lines(self):
                yield 'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}}'
            async def aclose(self): close_calls.append("response")

        class MockClient:
            async def aclose(self): close_calls.append("client")

        with patch.object(client, "_call_stream", return_value=(MockClient(), MockStreamResponse())):
            async for _ in client.chat_stream([{"role": "user", "content": "Hi"}]):
                pass

        assert "response" in close_calls, "Response should be closed"
        assert "client" in close_calls, "Client should be closed"

    @pytest.mark.asyncio
    async def test_stream_client_closed_on_error(self, client):
        """Verify the HTTP client is closed even when stream processing fails."""
        close_calls = []

        class MockStreamResponse:
            status_code = 200
            def raise_for_status(self): pass
            async def aiter_lines(self):
                yield 'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}}'
                raise ConnectionError("Simulated stream failure")
            async def aclose(self): close_calls.append("response")

        class MockClient:
            async def aclose(self): close_calls.append("client")

        with patch.object(client, "_call_stream", return_value=(MockClient(), MockStreamResponse())):
            with pytest.raises(ConnectionError):
                async for _ in client.chat_stream([{"role": "user", "content": "Hi"}]):
                    pass

        assert "response" in close_calls, "Response should be closed on error"
        assert "client" in close_calls, "Client should be closed on error"
