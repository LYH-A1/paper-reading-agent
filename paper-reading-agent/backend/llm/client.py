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

    async def _call(self, body: dict, stream: bool = False) -> httpx.Response:
        last_error = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                client_kwargs = {"timeout": httpx.Timeout(self.cfg.timeout)}
                async with httpx.AsyncClient(**client_kwargs) as client:
                    if stream:
                        return await client.send(
                            client.build_request("POST", f"{self.cfg.base_url}/messages", json=body, headers=self._headers()),
                            stream=True
                        )
                    else:
                        non_stream_headers = {k: v for k, v in self._headers().items() if k != "Accept"}
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

    async def chat(self, messages: list[dict], system: str = "", temperature: float | None = None) -> tuple[str, dict]:
        t0 = time.monotonic()
        body = self._body(messages, system, temperature, stream=False)
        try:
            resp = await self._call(body, stream=False)
            data = resp.json()
            content = data.get("content", [{}])[0].get("text", "")
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
        body["stream"] = True
        token_count = 0
        try:
            resp = await self._call(body, stream=True)
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {}).get("text", "")
                        if delta:
                            token_count += 1
                            yield delta
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

    async def chat_json(self, messages: list[dict], system: str = "") -> dict:
        json_system = system + "\n\nYou MUST respond ONLY with valid JSON. No markdown, no explanation outside the JSON object."
        for attempt in range(2):
            try:
                content, _ = await self.chat(messages, json_system, temperature=0.1)
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                return json.loads(content)
            except (json.JSONDecodeError, KeyError) as e:
                if attempt == 1:
                    raise
                logger.warning(f"JSON parse failed, retrying: {e}")
                messages.append({"role": "user", "content": "The previous response was not valid JSON. Please respond ONLY with a valid JSON object."})
        return {}


llm_client = LLMClient()
