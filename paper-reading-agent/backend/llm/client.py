import json
import time
import asyncio
from typing import AsyncGenerator
import httpx
from backend.config import config, LLMConfig
from backend.utils.logger import logger, api_logger


class LLMClient:
    def __init__(self, llm_config: LLMConfig | None = None):
        self.cfg = llm_config or config.llm

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.cfg.auth_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }

    def _body(self, messages: list[dict], system: str, temperature: float | None, stream: bool) -> dict:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        return {
            "model": self.cfg.model,
            "messages": msgs,
            "max_tokens": self.cfg.max_tokens,
            "temperature": temperature if temperature is not None else self.cfg.temperature,
            "stream": stream
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(self.cfg.timeout))

    async def _call(self, body: dict) -> httpx.Response:
        """Non-streaming API call with retry logic. Returns JSON response."""
        last_error = None
        non_stream_headers = {k: v for k, v in self._headers().items() if k != "Accept"}
        for attempt in range(self.cfg.max_retries + 1):
            try:
                async with self._client() as client:
                    return await client.post(
                        f"{self.cfg.base_url}/messages",
                        json=body,
                        headers=non_stream_headers,
                    )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_s = 2 ** attempt
                    logger.warning(f"Rate limited, retrying in {wait_s}s (attempt {attempt+1})")
                    await asyncio.sleep(wait_s)
                    last_error = e
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < self.cfg.max_retries:
                    await asyncio.sleep(2)
                    last_error = e
                    continue
                raise
        raise last_error or RuntimeError("Max retries exceeded")

    async def _call_stream(self, body: dict) -> tuple[httpx.AsyncClient, httpx.Response]:
        """Streaming API call. Returns (client, response).
        The caller MUST close the client after consuming the stream.
        Retries are handled by the caller so the stream can be re-established.
        """
        last_error = None
        for attempt in range(self.cfg.max_retries + 1):
            client = self._client()
            try:
                resp = await client.send(
                    client.build_request("POST", f"{self.cfg.base_url}/messages",
                                         json=body, headers=self._headers()),
                    stream=True
                )
                resp.raise_for_status()
                return client, resp
            except httpx.HTTPStatusError as e:
                await client.aclose()
                if e.response.status_code == 429:
                    wait_s = 2 ** attempt
                    logger.warning(f"Rate limited (stream), retrying in {wait_s}s (attempt {attempt+1})")
                    await asyncio.sleep(wait_s)
                    last_error = e
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                await client.aclose()
                if attempt < self.cfg.max_retries:
                    await asyncio.sleep(2)
                    last_error = e
                    continue
                raise
        raise last_error or RuntimeError("Max retries exceeded")

    async def chat(self, messages: list[dict], system: str = "", temperature: float | None = None) -> tuple[str, dict]:
        t0 = time.monotonic()
        body = self._body(messages, system, temperature, stream=False)
        try:
            resp = await self._call(body)
            data = resp.json()
            text_parts = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)
            content = "\n".join(text_parts) if text_parts else ""
            elapsed = int((time.monotonic() - t0) * 1000)
            usage = data.get("usage", {})
            api_logger.log(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), model=self.cfg.model,
                           messages_count=len(messages), tokens_used=usage.get("output_tokens", 0),
                           elapsed_ms=elapsed, success=True)
            return content, usage
        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            api_logger.log(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), model=self.cfg.model,
                           messages_count=len(messages), tokens_used=0,
                           elapsed_ms=elapsed, success=False, error=str(e))
            raise

    async def chat_stream(self, messages: list[dict], system: str = "") -> AsyncGenerator[str, None]:
        t0 = time.monotonic()
        body = self._body(messages, system, None, stream=True)
        token_count = 0
        client = None
        try:
            client, resp = await self._call_stream(body)
            try:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    token_count += 1
                                    yield text
            finally:
                await resp.aclose()
            elapsed = int((time.monotonic() - t0) * 1000)
            api_logger.log(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), model=self.cfg.model,
                           messages_count=len(messages), tokens_used=token_count,
                           elapsed_ms=elapsed, success=True)
        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            api_logger.log(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), model=self.cfg.model,
                           messages_count=len(messages), tokens_used=token_count,
                           elapsed_ms=elapsed, success=False, error=str(e))
            raise
        finally:
            if client is not None:
                await client.aclose()

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON object string from potentially noisy LLM output."""
        text = text.strip()

        # Strategy 1: Direct parse (cleanest case)
        if text.startswith("{") and text.endswith("}"):
            return text

        # Strategy 2: Find JSON object via balanced brace matching
        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:i+1]

        # Strategy 3: Extract from markdown code block (handles multiple blocks)
        if "```" in text:
            parts = text.split("```")
            # parts[0]: before first ```, parts[1]: content after first ```, etc.
            for i in range(1, len(parts), 2):
                block = parts[i].strip()
                if block.startswith("json"):
                    block = block[4:].strip()
                if block.startswith("{") or block.startswith("["):
                    return block

        return text

    async def chat_json(self, messages: list[dict], system: str = "") -> dict:
        json_system = system + "\n\nYou MUST respond ONLY with valid JSON. No markdown, no explanation outside the JSON object."
        for attempt in range(2):
            try:
                content, _ = await self.chat(messages, json_system, temperature=0.1)
                extracted = self._extract_json(content)
                return json.loads(extracted)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                if attempt == 1:
                    raise
                logger.warning(f"JSON parse failed (attempt {attempt+1}): {e}")
                messages.append({"role": "user", "content": f"The previous response was not valid JSON. Error: {e}. Please respond ONLY with a valid JSON object like {{\"key\": \"value\"}}."})
        return {}


llm_client = LLMClient()
