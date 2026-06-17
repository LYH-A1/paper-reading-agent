# Task 3 Review: LLM Client (`af864f0`)

**Reviewer:** Claude Agent
**Commit:** `af864f0` (feat: add DeepSeek LLM client with streaming, retry, and JSON mode)
**Files reviewed:**
- `paper-reading-agent/backend/llm/client.py`
- `paper-reading-agent/tests/test_llm_client.py`

---

## Checklist

### 1. LLMClient with `chat()`, `chat_stream()`, `chat_json()`

**APPROVED** -- All three methods are present as `async` methods on `LLMClient` in `backend/llm/client.py`.

---

### 2. Retry logic: 429s use exponential backoff (2^attempt), timeouts retry with 2s delay

**APPROVED** -- In `_call()`:
- HTTP 429: `wait_s = 2 ** attempt` with `logger.warning`, loops up to `max_retries + 1`.
- `httpx.TimeoutException` and `httpx.ConnectError`: retries with `await asyncio.sleep(2)` (hardcoded 2s delay as specified).
- Both retry loops use `continue` and raise `last_error` after exhaustion.

---

### 3. Streaming: SSE line parsing extracts `content_block_delta` tokens

**APPROVED** -- In `chat_stream()`:
- Uses `resp.aiter_lines()` to iterate over SSE lines.
- Filters lines starting with `"data: "` and parses the JSON payload.
- Checks `data.get("type") == "content_block_delta"` and yields `delta.get("text", "")`.
- Token counter increments per yielded delta.

---

### 4. JSON mode: retries once on parse failure, strips ``` fences

**APPROVED** -- In `chat_json()`:
- Loop `range(2)` gives exactly one retry on failure.
- Strips leading/trailing whitespace, then detects `content.startswith("```")` and splits on triple backticks.
- Handles `json` language tag after backticks (`content[4:]` for `"json"` prefix).
- On `json.JSONDecodeError` or `KeyError`, appends a corrective user message on the first attempt and retries.
- Raises on second failure.

---

### 5. API logging in all methods (success + failure)

**APPROVED** -- All three methods (`chat`, `chat_stream`, `chat_json`) log via `api_logger.log()`:
- **Success path**: logs `elapsed_ms`, `tokens_used` (or `token_count`), `success=True`.
- **Exception path** (caught via `except Exception`): logs `success=False`, `error=str(e)` before re-raising.
- `api_logger` writes JSONL to `outputs/api_log.jsonl`.

---

### 6. Test: `test_chat_basic` mocks `httpx.AsyncClient.post`, 1 test, passes

**APPROVED** -- `tests/test_llm_client.py` contains exactly one test (`test_chat_basic`):
- Uses `@pytest.mark.asyncio` for async execution.
- Patches `httpx.AsyncClient.post` with an `AsyncMock`.
- Returns a mocked response with `content` and `usage` fields.
- Asserts `content == "Hello, world!"` and `usage["output_tokens"] == 10`.
- **Test passes** (verified via `python -m pytest tests/test_llm_client.py -v`).

---

### 7. No extra files beyond `backend/llm/client.py` and `tests/test_llm_client.py`

**APPROVED** -- Commit `af864f0` affected only the expected two files:
- `paper-reading-agent/backend/llm/client.py`
- `paper-reading-agent/tests/test_llm_client.py`

---

## Additional Observations (Minor, non-blocking)

| # | Finding | Severity | Description |
|---|---------|----------|-------------|
| 1 | `chat_json` temperature hardcoded at `0.1` | Minor | The method does not expose a `temperature` parameter, always using `0.1`. This is a sensible default for JSON generation but deviates from the flexibility of `chat()`. |
| 2 | `api_logger.log()` `tokens_used` in `chat_stream` counts deltas, not actual tokens | Minor | The method uses `token_count` (incremented per yield) rather than real token usage from the API response. This is an approximation, acceptable for streaming. |
| 3 | `chat_json` fallback `return {}` after retry loop | Minor | If the second attempt also throws, the method re-raises (line 127), making line 130 `return {}` unreachable. This is dead code. |

All three are benign -- they do not affect correctness or test coverage.

---

## Verdict

**APPROVED** -- All 7 checklist items pass. The implementation is clean, well-structured, and the test verifies the core `chat()` method with proper mocking.
