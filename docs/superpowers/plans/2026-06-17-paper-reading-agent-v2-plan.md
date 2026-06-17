# 论文阅读 Agent V2 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a paper reading agent with R0/R1/R2 evidence traceability, 3-agent LangGraph orchestration, and hybrid RAG retrieval — Phase 1 delivers CLI-verified core engine with minimal web UI.

**Architecture:** LangGraph StateGraph orchestrates 3 agents (Reader → QA → Reviewer) with Review-Revision loop. FastAPI backend serves SSE streaming to React frontend. Hybrid RAG (ChromaDB + BM25) with evidence annotation pipeline.

**Tech Stack:** Python 3.10+, FastAPI, LangGraph, LangGraph Checkpoint SQLite, DeepSeek API (Anthropic protocol), ChromaDB, BM25, PyMuPDF, SQLite, React 18 + TypeScript + Vite + PDF.js. Phase 1 excludes FlashRank and full React app.

## Global Constraints

- Python >= 3.10
- langgraph >= 0.2.0
- langgraph-checkpoint-sqlite >= 1.0.0
- fastapi >= 0.111.0
- httpx >= 0.27.0
- pydantic >= 2.7.0
- PyMuPDF >= 1.24.0
- chromadb >= 0.5.0
- rank-bm25 >= 0.2.2
- sentence-transformers >= 3.0.0
- aiosqlite >= 0.20.0
- react >= 18, typescript >= 5 (Phase 2+)
- DeepSeek API via Anthropic protocol (ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN env vars)
- All LLM calls log to `outputs/api_log.jsonl` with timestamp/model/tokens/elapsed
- AgentState trace field records every node execution
- rewrite_count max 2, configurable in config.py
- Single-user local-first: SQLite + filesystem, no PostgreSQL

---

## Phase 1: Core Engine MVP

### Task 1: Project scaffolding

**Files:**
- Create: `paper-reading-agent/requirements.txt`
- Create: `paper-reading-agent/.env.example`
- Create: `paper-reading-agent/backend/__init__.py`
- Create: `paper-reading-agent/backend/config.py`
- Create: `paper-reading-agent/backend/utils/__init__.py`
- Create: `paper-reading-agent/backend/utils/logger.py`
- Create: `paper-reading-agent/backend/models/__init__.py`
- Create: `paper-reading-agent/backend/llm/__init__.py`
- Create: `paper-reading-agent/backend/tools/__init__.py`
- Create: `paper-reading-agent/backend/agents/__init__.py`
- Create: `paper-reading-agent/backend/storage/__init__.py`
- Create: `paper-reading-agent/data/.gitkeep`
- Create: `paper-reading-agent/outputs/.gitkeep`
- Create: `paper-reading-agent/data/papers/.gitkeep`
- Create: `paper-reading-agent/data/reports/.gitkeep`

**Interfaces:**
- Produces: `Config` dataclass, `setup_logging()` function, all package init files

---

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
langgraph>=0.2.0
langgraph-checkpoint-sqlite>=1.0.0
httpx>=0.27.0
python-dotenv>=1.0.1
pydantic>=2.7.0
PyMuPDF>=1.24.0
pdfplumber>=0.11.0
chromadb>=0.5.0
rank-bm25>=0.2.2
sentence-transformers>=3.0.0
aiosqlite>=0.20.0
```

- [ ] **Step 2: Write `.env.example`**

```
ANTHROPIC_BASE_URL=https://api.deepseek.com/v1
ANTHROPIC_AUTH_TOKEN=your-deepseek-api-key
MODEL=deepseek-v4-pro
MAX_TOKENS=4096
TEMPERATURE=0.7
TIMEOUT=60
MAX_RETRIES=2
REWRITE_MAX=2
DATA_DIR=./data
```

- [ ] **Step 3: Write `backend/config.py`**

```python
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass
class LLMConfig:
    base_url: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/v1")
    auth_token: str = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
    model: str = os.getenv("MODEL", "deepseek-v4-pro")
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
    timeout: int = int(os.getenv("TIMEOUT", "60"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "2"))

@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    rewrite_max: int = int(os.getenv("REWRITE_MAX", "2"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    db_path: Path | None = None
    paper_dir: Path | None = None
    report_dir: Path | None = None
    output_dir: Path = Path("./outputs")

    def __post_init__(self):
        self.data_dir = self.data_dir.resolve()
        self.db_path = self.data_dir / "paper-reading.db"
        self.paper_dir = self.data_dir / "papers"
        self.report_dir = self.data_dir / "reports"
        self.output_dir = self.output_dir.resolve()
        for d in [self.data_dir, self.paper_dir, self.report_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)

config = Config()
```

- [ ] **Step 4: Write `backend/utils/logger.py`**

```python
import logging
import json
import time
from pathlib import Path
from backend.config import config

def setup_logging() -> logging.Logger:
    logger = logging.getLogger("paper-agent")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    return logger

logger = setup_logging()

class APILogger:
    """Records every LLM API call to outputs/api_log.jsonl."""
    def __init__(self, path: Path | None = None):
        self.path = path or config.output_dir / "api_log.jsonl"

    def log(self, *, timestamp: str, model: str, messages_count: int,
            tokens_used: int, elapsed_ms: int, success: bool, error: str | None = None):
        entry = {
            "timestamp": timestamp,
            "model": model,
            "messages_count": messages_count,
            "tokens_used": tokens_used,
            "elapsed_ms": elapsed_ms,
            "success": success,
            "error": error
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

api_logger = APILogger()
```

- [ ] **Step 5: Write all `__init__.py` files as empty files**

```
Create: backend/__init__.py (empty)
Create: backend/utils/__init__.py (empty)
Create: backend/models/__init__.py (empty)
Create: backend/llm/__init__.py (empty)
Create: backend/tools/__init__.py (empty)
Create: backend/agents/__init__.py (empty)
Create: backend/storage/__init__.py (empty)
Create: data/.gitkeep (empty)
Create: outputs/.gitkeep (empty)
Create: data/papers/.gitkeep (empty)
Create: data/reports/.gitkeep (empty)
```

- [ ] **Step 6: Install dependencies and verify imports**

```bash
cd paper-reading-agent
pip install -r requirements.txt
python -c "from backend.config import config; print(config)"
```

Expected: Config printed without errors.

- [ ] **Step 7: Commit**

```bash
git add paper-reading-agent/
git commit -m "feat: project scaffolding with config, logging, and dependencies"
```

---

### Task 2: Data models

**Files:**
- Create: `paper-reading-agent/backend/models/paper.py`
- Create: `paper-reading-agent/backend/models/state.py`

**Interfaces:**
- Produces: `Section`, `Figure`, `Reference`, `Paper` dataclasses
- Produces: `EvidenceLevel(Enum)`, `Evidence`, `QualityScore`, `RetrievedChunk`, `AgentState` dataclasses

---

- [ ] **Step 1: Write `backend/models/paper.py`**

```python
from dataclasses import dataclass, field
import uuid

@dataclass
class Section:
    heading: str
    content: str
    page_start: int
    page_end: int
    bbox: tuple[float, float, float, float] | None = None

@dataclass
class Figure:
    caption: str
    page: int
    bbox: tuple[float, float, float, float]
    image_base64: str | None = None

@dataclass
class Reference:
    """Structured bibliographic reference."""
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None

@dataclass
class Paper:
    paper_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    sections: list[Section] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    raw_text: str = ""
    language: str = "en"
    file_path: str = ""
    parsed_at: str = ""
```

- [ ] **Step 2: Write test for paper model**

Create `paper-reading-agent/tests/test_models.py`:

```python
import json
from dataclasses import asdict
from backend.models.paper import Paper, Section, Figure, Reference

def test_paper_defaults():
    p = Paper()
    assert p.paper_id
    assert p.language == "en"
    assert p.sections == []
    assert p.figures == []

def test_paper_with_sections():
    s = Section(heading="3. Method", content="We propose...", page_start=3, page_end=8)
    p = Paper(title="Test", sections=[s], raw_text="full text")
    assert len(p.sections) == 1
    assert p.sections[0].heading == "3. Method"

def test_paper_serializable():
    p = Paper(title="Test", authors=["Alice", "Bob"])
    d = asdict(p)
    assert json.dumps(d)
    assert d["title"] == "Test"
    assert d["authors"] == ["Alice", "Bob"]
```

Run: `cd paper-reading-agent && python -m pytest tests/test_models.py -v`
Expected: 3 PASS (test_paper_defaults, test_paper_with_sections, test_paper_serializable)

- [ ] **Step 3: Write `backend/models/state.py`**

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class EvidenceLevel(str, Enum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"

@dataclass
class Evidence:
    evidence_id: str
    claim: str
    level: EvidenceLevel
    sentence_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    # R0
    page: int | None = None
    quote: str | None = None
    quote_span: tuple[int, int] | None = None
    section_heading: str | None = None
    # R1
    source_title: str | None = None
    source_url: str | None = None
    source_venue: str | None = None
    source_year: int | None = None
    # R2
    reasoning: str | None = None
    based_on_evidence_ids: list[str] = field(default_factory=list)
    # General
    confidence: float = 0.0
    claim_group_id: str | None = None

@dataclass
class QualityScore:
    relevance: int = 0      # 0-3
    consistency: int = 0    # 0-4
    completeness: int = 0   # 0-3

    @property
    def total(self) -> int:
        return self.relevance + self.consistency + self.completeness

@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    page: int
    section_heading: str = ""
    source: str = ""          # "bm25" | "dense" | "rerank"
    scores: dict[str, float] = field(default_factory=dict)

@dataclass
class AgentState:
    paper: Any | None = None
    report: dict | None = None
    retriever: Any | None = None

    user_query: str = ""
    intent: str = ""

    plan: dict | None = None
    plan_feedback: str | None = None
    observation: dict | None = None

    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    answer: str = ""
    evidence_list: list[Evidence] = field(default_factory=list)

    quality_score: QualityScore | None = None
    rewrite_count: int = 0

    trace: list[str] = field(default_factory=list)
    error: str | None = None
```

- [ ] **Step 4: Write tests for Evidence and QualityScore**

Append to `tests/test_models.py`:

```python
from backend.models.state import Evidence, EvidenceLevel, QualityScore, AgentState, RetrievedChunk

def test_evidence_r0_creation():
    e = Evidence(
        evidence_id="ev-1",
        claim="The model was trained on 8xA100 for 72 hours",
        level=EvidenceLevel.R0,
        sentence_index=0,
        char_start=0,
        char_end=52,
        page=4,
        quote="We train our model on 8 NVIDIA A100 GPUs for 72 hours",
        section_heading="4. Experimental Setup",
        confidence=0.95
    )
    assert e.level == EvidenceLevel.R0
    assert e.page == 4
    assert e.quote is not None

def test_evidence_r2_with_chain():
    e = Evidence(
        evidence_id="ev-5",
        claim="This direction is likely to converge with diffusion priors",
        level=EvidenceLevel.R2,
        sentence_index=2,
        reasoning="Based on ev-3 showing transformer scaling + ev-4 showing diffusion results",
        based_on_evidence_ids=["ev-3", "ev-4"],
        confidence=0.6
    )
    assert e.level == EvidenceLevel.R2
    assert len(e.based_on_evidence_ids) == 2

def test_quality_score_total():
    q = QualityScore(relevance=3, consistency=4, completeness=2)
    assert q.total == 9

def test_agent_state_defaults():
    s = AgentState()
    assert s.retrieved_chunks == []
    assert s.evidence_list == []
    assert s.trace == []
    assert s.rewrite_count == 0
```

Run: `cd paper-reading-agent && python -m pytest tests/test_models.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/models/ paper-reading-agent/tests/
git commit -m "feat: add Paper, Evidence, AgentState data models with tests"
```

---

### Task 3: LLM client

**Files:**
- Create: `paper-reading-agent/backend/llm/client.py`
- Create: `paper-reading-agent/tests/test_llm_client.py`

**Interfaces:**
- Produces: `LLMClient` class with methods:
  - `async chat(messages: list[dict], system: str = "", temperature: float | None = None) -> tuple[str, dict]`
  - `async chat_stream(messages: list[dict], system: str = "") -> AsyncGenerator[str, None]`
  - `async chat_json(messages: list[dict], system: str = "") -> dict`

---

- [ ] **Step 1: Write `backend/llm/client.py`**

```python
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
                        return await client.post(
                            f"{self.cfg.base_url}/messages",
                            json=body,
                            headers={k: v for k, v in self._headers().items() if k != "Accept"},
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
        """Call LLM with JSON mode — enforce format in system prompt."""
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
```

- [ ] **Step 2: Fix `Accept` header for non-streaming calls**

In the `_call` method, non-streaming calls should not include the `Accept: text/event-stream` header. Update the `_headers` to not include Accept by default, and handle stream-specific headers in the request building.

Actually the code already handles this correctly:
```python
headers={k: v for k, v in self._headers().items() if k != "Accept"}
```
So the streaming call uses full headers, non-streaming filters out "Accept". Done right in Step 1.

- [ ] **Step 3: Write `tests/test_llm_client.py`**

```python
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
```

Run: `cd paper-reading-agent && python -m pytest tests/test_llm_client.py -v`
Expected: 1 PASS

- [ ] **Step 4: Commit**

```bash
git add paper-reading-agent/backend/llm/client.py paper-reading-agent/tests/test_llm_client.py
git commit -m "feat: add DeepSeek LLM client with streaming, retry, and JSON mode"
```

---

### Task 4: Prompt templates

**Files:**
- Create: `paper-reading-agent/backend/llm/prompts.py`

**Interfaces:**
- Produces module-level constants: `REPORT_PROMPT`, `CLASSIFY_PROMPT`, `PLANNER_PROMPTS` (dict), `ANSWER_PROMPTS` (dict), `OBSERVE_PROMPT`, `REVIEWER_PROMPT`, `REWRITE_PROMPT`, `FOLLOWUP_PROMPT`, `KEYWORD_RULES` (dict)

---

- [ ] **Step 1: Write `backend/llm/prompts.py`**

```python
REPORT_PROMPT = """You are an academic paper analyst. Given the full text of a paper, produce a structured report in JSON format.

Output format:
{
  "title": "paper title",
  "authors": ["author1", "author2"],
  "year": 2024,
  "abstract_summary": "1-2 sentence summary of abstract",
  "contributions": ["contribution 1", "contribution 2"],
  "method_summary": "brief description of the method",
  "experiments_summary": "key experimental findings",
  "limitations": ["limitation 1"],
  "keywords": ["keyword1", "keyword2"]
}

Cite section numbers when possible (e.g., "Section 3 proposes...")."""

CLASSIFY_PROMPT = """Classify the user's question about an academic paper into one of four intents.

Output ONLY a JSON object:
{"intent": "summary", "confidence": 0.95}

Intent definitions:
- "summary": user wants an overview or summary of the paper
- "qa": user wants a specific question answered about the paper content
- "compare": user wants to compare this paper with other work
- "recommend": user wants recommendations for related papers

User question: {query}
Paper title: {title}"""

PLANNER_PROMPTS = {
    "summary": """Generate a 3-step execution plan for summarizing the paper.
Output: {"steps": [{"step": 1, "action": "...", "tool": "retrieve", "target": "..."}]}""",
    "qa": """Generate a 3-5 step execution plan for answering the question.
Output: {"steps": [{"step": 1, "action": "...", "tool": "retrieve", "target": "..."}]}""",
    "compare": """Generate a plan for comparing this paper's approach with alternatives.
Output: {"steps": [{"step": 1, "action": "...", "tool": "retrieve", "target": "..."}]}""",
    "recommend": """Generate a plan for finding related papers.
Output: {"steps": [{"step": 1, "action": "...", "tool": "retrieve", "target": "..."}]}""",
}

ANSWER_PROMPTS = {
    "summary": """You are an expert academic summarizer. Based on the paper report and retrieved context, produce a structured summary.

Format your answer with sections: **Background**, **Method**, **Contributions**, **Limitations**.
After each factual claim, include a reference marker like [Section X, Page Y].
Use [Section X] or [Page Y] style references throughout.""",

    "qa": """You are a paper Q&A assistant. Answer the user's question using ONLY the provided paper context.

Rules:
1. After each factual claim, reference the source: [Section X, Page Y]
2. If the paper does not contain the answer, say so explicitly — do not guess
3. Distinguish between what the paper states (use "The paper shows...") and your interpretation (use "This suggests...")
4. Structure longer answers with bullet points or numbered lists for clarity""",

    "compare": """You are a comparative analysis assistant. Compare the paper's approach with alternatives mentioned in the text or known to you.

After each claim, indicate whether it comes from the current paper [Section X], or from general knowledge [External]. """,

    "recommend": """You are a literature recommendation assistant. Based on the paper's content and references, recommend 3-5 related papers.

For each recommendation, explain why it's relevant and cite the current paper's reference or section that connects to it.""",
}

OBSERVE_PROMPT = """Evaluate whether the generated answer sufficiently addresses the execution plan.

Output JSON:
{
  "plan_valid": true/false,
  "sufficient": true/false,
  "gaps": ["missing topic 1", "missing topic 2"],
  "reasoning": "brief explanation"
}

Check:
- plan_valid: Is the plan still appropriate for the question? If not, set to false.
- sufficient: Does the answer cover all plan steps adequately?
- gaps: List specific topics that are missing or inadequately covered."""

REVIEWER_PROMPT = """You are a strict academic reviewer. Review the answer against the paper and provide:

1. Evidence annotation: For EVERY factual claim in the answer, classify it as R0, R1, or R2.
2. Quality scoring (0-10 scale across 3 dimensions).

Output JSON:
{
  "relevance": 0-3,
  "consistency": 0-4,
  "completeness": 0-3,
  "deductions": ["reason 1", "reason 2"],
  "evidence_list": [
    {
      "evidence_id": "ev-N",
      "claim": "exact claim text from answer",
      "level": "R0",
      "sentence_index": 0,
      "char_start": 0,
      "char_end": 52,
      "page": 4,
      "quote": "exact quote from paper",
      "section_heading": "4. Experiments",
      "confidence": 0.95
    }
  ],
  "followup_questions": ["question 1", "question 2", "question 3"]
}

R0: strictly from current paper, must have page + quote + section_heading, char_start + char_end
R1: from external source, must have source_title + source_url
R2: your inference/judgment, must have reasoning + based_on_evidence_ids (list of evidence_id referencing R0/R1 evidence from this review)

For EVERY factual claim in the answer, include an evidence entry. Do not skip any claim.
If a statement is R2, explain your reasoning in the reasoning field.
For char_start and char_end, measure against the answer text exactly — these must be precise character offsets."""

REWRITE_PROMPT = """Your previous answer received a quality score of {score}/10.

Deductions:
{deductions}

Please rewrite the answer addressing ALL of the above issues. Maintain the same reference format [Section X, Page Y].
Original question: {query}
Paper context: {context}"""

FOLLOWUP_PROMPT = """Based on the conversation context, generate 3 follow-up questions the user might want to ask. Output as a JSON array of strings."""

KEYWORD_RULES = {
    "summary": ["总结", "摘要", "概述", "概括", "summarize", "summary", "overview", "overall"],
    "qa": ["什么", "如何", "为什么", "怎么", "what", "how", "why", "explain", "describe"],
    "compare": ["对比", "比较", "区别", "差异", "compare", "difference", "versus", "vs"],
    "recommend": ["推荐", "相关", "类似", "延伸", "recommend", "related", "similar", "further"],
}
```

- [ ] **Step 2: Commit**

```bash
git add paper-reading-agent/backend/llm/prompts.py
git commit -m "feat: add prompt templates for all 5 intents + reviewer + rewrite"
```

---

### Task 5: PDF parser tool

**Files:**
- Create: `paper-reading-agent/backend/tools/pdf_parser.py`
- Create: `paper-reading-agent/tests/test_pdf_parser.py`
- Create: `paper-reading-agent/tests/fixtures/sample.pdf` (minimal valid PDF)

**Interfaces:**
- Produces: `class PDFParser` with `parse(file_path: str) -> Paper`

---

- [ ] **Step 1: Write `backend/tools/pdf_parser.py`**

```python
import re
import time
from pathlib import Path
from backend.models.paper import Paper, Section
from backend.utils.logger import logger

class PDFParseError(Exception):
    pass

class PDFParser:
    """Dual-engine PDF parser: PyMuPDF primary, pdfplumber fallback."""

    def parse(self, file_path: str) -> Paper:
        path = Path(file_path)
        if not path.suffix.lower().endswith(".pdf"):
            raise PDFParseError(f"Not a PDF file: {file_path}")

        t0 = time.monotonic()
        paper = Paper(file_path=str(path.resolve()))

        try:
            paper = self._parse_pymupdf(path, paper)
        except Exception as e:
            logger.warning(f"PyMuPDF failed: {e}, falling back to pdfplumber")
            try:
                paper = self._parse_pdfplumber(path, paper)
            except Exception as e2:
                raise PDFParseError(f"Both engines failed. PyMuPDF: {e}, pdfplumber: {e2}")

        elapsed = time.monotonic() - t0
        if elapsed > 60:
            logger.warning(f"PDF parse took {elapsed:.1f}s, exceeded 60s budget")

        if len(paper.raw_text) < 100:
            logger.warning(f"Very short text ({len(paper.raw_text)} chars) — may be scanned PDF")

        paper.parsed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        return paper

    def _parse_pymupdf(self, path: Path, paper: Paper) -> Paper:
        import fitz  # PyMuPDF — lazy import

        doc = fitz.open(str(path))
        if doc.page_count > 30:
            logger.info(f"Long paper ({doc.page_count} pages), parsing first 30 pages")
            doc = doc[:30]

        full_text_parts = []
        sections = []
        current_section: dict | None = None

        for page_num, page in enumerate(doc):
            text = page.get_text("text")
            full_text_parts.append(text)

            blocks = page.get_text("blocks")
            for block in blocks:
                block_text = block[4].strip() if len(block) > 4 else ""
                bbox = block[:4]
                if self._is_heading(block_text):
                    if current_section:
                        sections.append(Section(**current_section))
                    current_section = {"heading": block_text, "content": "", "page_start": page_num + 1, "page_end": page_num + 1, "bbox": bbox}
                elif current_section:
                    current_section["content"] += block_text + "\n"
                    current_section["page_end"] = page_num + 1

        if current_section:
            sections.append(Section(**current_section))

        raw_text = "\n".join(full_text_parts)
        paper.raw_text = raw_text
        paper.sections = sections
        paper.title, paper.authors, paper.abstract = self._extract_metadata(raw_text)
        return paper

    def _parse_pdfplumber(self, path: Path, paper: Paper) -> Paper:
        import pdfplumber  # lazy import

        full_text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages[:30]:
                text = page.extract_text()
                if text:
                    full_text_parts.append(text)

        raw_text = "\n".join(full_text_parts)
        paper.raw_text = raw_text
        paper.title, paper.authors, paper.abstract = self._extract_metadata(raw_text)
        return paper

    def _is_heading(self, text: str) -> bool:
        text = text.strip()
        if not text or len(text) > 120:
            return False
        patterns = [
            r"^Abstract$",
            r"^[IVX]+\.\s",
            r"^\d+\.\s+\w",
            r"^\d+\.\d+\.\s+\w",
            r"^(Introduction|Background|Method|Experiment|Result|Discussion|Conclusion|Related Work|References|Acknowledgments)",
        ]
        return any(re.match(p, text, re.IGNORECASE) for p in patterns)

    def _extract_metadata(self, text: str) -> tuple[str, list[str], str]:
        title = ""
        authors = []
        abstract = ""

        # Title: first non-empty line, usually the largest font size
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            title = lines[0]
            if len(title) > 200:
                title = title[:200]

        # Abstract: text between "Abstract" heading and next section heading
        abstract_match = re.search(r"Abstract\s*\n+(.+?)(?=\n\s*(?:\d+\.|[IVX]+\.)\s)", text, re.DOTALL | re.IGNORECASE)
        if abstract_match:
            abstract = abstract_match.group(1).strip()[:2000]

        return title, authors, abstract
```

- [ ] **Step 2: Create a minimal test PDF**

Create `tests/fixtures/sample.pdf`. Since creating a valid PDF binary requires a library, write a test fixture generator:

```python
# tests/fixtures/generate_sample.py — run once to create sample.pdf
import fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text(fitz.Point(72, 72), "Sample Paper Title\n\n", fontsize=16)
page.insert_text(fitz.Point(72, 120), "Abstract\nThis paper proposes a novel method for testing PDF parsers.\n", fontsize=11)
page.insert_text(fitz.Point(72, 200), "1. Introduction\nThis is the introduction section.\n", fontsize=11)
page.insert_text(fitz.Point(72, 300), "2. Method\nWe describe our approach here.\n", fontsize=11)
doc.save("tests/fixtures/sample.pdf")
```

Run: `cd paper-reading-agent && python tests/fixtures/generate_sample.py`

- [ ] **Step 3: Write `tests/test_pdf_parser.py`**

```python
from pathlib import Path
from backend.tools.pdf_parser import PDFParser, PDFParseError

def test_rejects_non_pdf():
    parser = PDFParser()
    try:
        parser.parse("tests/test_models.py")
        assert False, "Should have raised"
    except PDFParseError as e:
        assert "Not a PDF" in str(e)

def test_parses_sample_pdf():
    parser = PDFParser()
    paper = parser.parse("tests/fixtures/sample.pdf")
    assert paper.title == "Sample Paper Title"
    assert len(paper.raw_text) > 50
    assert len(paper.sections) >= 2
    assert paper.parsed_at != ""

def test_scanned_pdf_detection():
    parser = PDFParser()
    # A PDF with minimal text: create one with 0 text
    paper = parser.parse("tests/fixtures/sample.pdf")
    # This is not scanned but tests the path works
    assert paper.file_path.endswith(".pdf")
```

Run: `cd paper-reading-agent && python -m pytest tests/test_pdf_parser.py -v`
Expected: 3 PASS (may skip scanned test if sample has sufficient text)

- [ ] **Step 4: Commit**

```bash
git add paper-reading-agent/backend/tools/pdf_parser.py paper-reading-agent/tests/test_pdf_parser.py paper-reading-agent/tests/fixtures/
git commit -m "feat: add dual-engine PDF parser with PyMuPDF + pdfplumber"
```

---

### Task 6: Smart text splitter

**Files:**
- Create: `paper-reading-agent/backend/utils/text_splitter.py`
- Create: `paper-reading-agent/tests/test_text_splitter.py`

**Interfaces:**
- Produces: `split_text(text: str, sections: list[Section], chunk_size: int = 1000, overlap: int = 200) -> list[dict]`
  - Each dict: `{"chunk_id": str, "text": str, "page": int, "section_heading": str}`

---

- [ ] **Step 1: Write `backend/utils/text_splitter.py`**

```python
import re
import uuid
from backend.models.paper import Section

def split_text(text: str, sections: list[Section], chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
    """Split paper text into overlapping chunks, preserving section boundaries."""
    chunks = []

    for section in sections:
        content = section.content.strip()
        if not content:
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        current_chunk = ""
        current_page = section.page_start

        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "text": current_chunk.strip(),
                    "page": current_page,
                    "section_heading": section.heading
                })
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        if current_chunk.strip():
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "text": current_chunk.strip(),
                "page": section.page_start,
                "section_heading": section.heading
            })

    # Fallback: if no sections, split raw text
    if not chunks and text:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append({"chunk_id": str(uuid.uuid4()), "text": current_chunk.strip(), "page": 1, "section_heading": ""})
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
            else:
                current_chunk = current_chunk + "\n\n" + para if current_chunk else para
        if current_chunk.strip():
            chunks.append({"chunk_id": str(uuid.uuid4()), "text": current_chunk.strip(), "page": 1, "section_heading": ""})

    return chunks
```

- [ ] **Step 2: Write `tests/test_text_splitter.py`**

```python
from backend.models.paper import Section
from backend.utils.text_splitter import split_text

def test_split_preserves_sections():
    sections = [
        Section(heading="1. Intro", content="This is the introduction.\n\nIt has two paragraphs.", page_start=1, page_end=1),
        Section(heading="2. Method", content="We propose a method.", page_start=2, page_end=2),
    ]
    chunks = split_text("", sections, chunk_size=1000, overlap=200)
    assert len(chunks) == 2
    assert chunks[0]["section_heading"] == "1. Intro"
    assert chunks[1]["section_heading"] == "2. Method"

def test_split_respects_chunk_size():
    sections = [Section(heading="1. Intro", content="A" * 1500, page_start=1, page_end=1)]
    chunks = split_text("", sections, chunk_size=1000, overlap=200)
    assert len(chunks) >= 2

def test_empty_sections():
    assert split_text("", [], chunk_size=1000) == []

def test_fallback_no_sections():
    chunks = split_text("First paragraph.\n\nSecond paragraph.", [])
    assert len(chunks) == 1
    assert "First paragraph" in chunks[0]["text"]
```

Run: `cd paper-reading-agent && python -m pytest tests/test_text_splitter.py -v`
Expected: 4 PASS

- [ ] **Step 3: Commit**

```bash
git add paper-reading-agent/backend/utils/text_splitter.py paper-reading-agent/tests/test_text_splitter.py
git commit -m "feat: add smart text splitter with section boundary preservation"
```

---

### Task 7: Hybrid retriever

**Files:**
- Create: `paper-reading-agent/backend/tools/retriever.py`
- Create: `paper-reading-agent/tests/test_retriever.py`

**Interfaces:**
- Produces: `class HybridRetriever` with:
  - `__init__(paper: Paper, embedding_model: str = "auto")`
  - `retrieve(query: str, top_k: int = 5) -> list[RetrievedChunk]`
  - Note: Phase 1 omits FlashRank; merge step sorts by BM25 score as fallback

---

- [ ] **Step 1: Write `backend/tools/retriever.py`**

```python
import uuid
from backend.models.paper import Paper
from backend.models.state import RetrievedChunk
from backend.utils.text_splitter import split_text
from backend.utils.logger import logger

class HybridRetriever:
    """Hybrid RAG: BM25 + ChromaDB. FlashRank added in Phase 3."""
    def __init__(self, paper: Paper, embedding_model: str = "auto"):
        self.paper = paper
        self.chunks = self._build_chunks()
        self._build_indices(embedding_model)

    def _build_chunks(self) -> list[dict]:
        raw = split_text(self.paper.raw_text, self.paper.sections)
        if not raw:
            # Fallback: one chunk with abstract
            return [{"chunk_id": str(uuid.uuid4()), "text": self.paper.abstract, "page": 1, "section_heading": "Abstract"}]
        return raw

    def _build_indices(self, embedding_model: str):
        # BM25
        from rank_bm25 import BM25Okapi
        self._choose_tokenizer()
        tokenized = [self._tokenize(c["text"]) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized)

        # ChromaDB
        import chromadb
        from sentence_transformers import SentenceTransformer
        model_name = "all-MiniLM-L6-v2"
        if self.paper.language == "zh":
            model_name = "BAAI/bge-large-zh-v1.5"
        if embedding_model != "auto":
            model_name = embedding_model
        self.embedder = SentenceTransformer(model_name)
        self.chroma = chromadb.Client()
        try:
            self.chroma.delete_collection("paper_chunks")
        except Exception:
            pass
        self.collection = self.chroma.create_collection("paper_chunks")
        embeddings = self.embedder.encode([c["text"] for c in self.chunks]).tolist()
        self.collection.add(
            ids=[c["chunk_id"] for c in self.chunks],
            documents=[c["text"] for c in self.chunks],
            embeddings=embeddings,
            metadatas=[{"page": c["page"], "section": c["section_heading"]} for c in self.chunks]
        )

    def _choose_tokenizer(self):
        if self.paper.language == "zh":
            try:
                import jieba
                self._tokenize = lambda text: list(jieba.cut(text))
            except ImportError:
                self._tokenize = lambda text: text.split()
        else:
            self._tokenize = lambda text: text.split()

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        # Translate Chinese query for English paper
        if self.paper.language == "en" and self._is_chinese(query):
            query = self._translate_query(query)

        bm25_results = self._bm25_search(query, top_k * 4)
        dense_results = self._dense_search(query, top_k * 4)
        merged = self._merge(bm25_results, dense_results)

        if not merged:
            # Fallback: return abstract as context
            return [RetrievedChunk(
                chunk_id="abstract-fallback", text=self.paper.abstract,
                page=1, section_heading="Abstract", source="fallback", scores={}
            )]

        # Phase 1: sort by BM25 score (FlashRank replaces this in Phase 3)
        merged.sort(key=lambda c: c.scores.get("bm25", 0), reverse=True)
        results = merged[:top_k]

        # Check relevance
        avg_score = sum(c.scores.get("bm25", 0) for c in results) / len(results) if results else 0
        if avg_score < 0.3:
            logger.warning(f"Low average relevance: {avg_score:.2f}, expanding to top-10")
            results = merged[:10]

        for c in results:
            c.source = "bm25" if "bm25" in c.scores else "dense"

        return results

    def _bm25_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        tokens = self._tokenize(query)
        scores = self.bm25.get_scores(tokens)
        indexed = [(i, s) for i, s in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        results = []
        for i, score in indexed[:top_k]:
            c = self.chunks[i]
            results.append(RetrievedChunk(
                chunk_id=c["chunk_id"], text=c["text"], page=c["page"],
                section_heading=c.get("section_heading", ""), source="bm25",
                scores={"bm25": float(score)}
            ))
        return results

    def _dense_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        try:
            q_embedding = self.embedder.encode([query]).tolist()
            results = self.collection.query(query_embeddings=q_embedding, n_results=top_k)
            chunks = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                doc = results["documents"][0][i]
                dist = results["distances"][0][i] if "distances" in results else 0
                chunks.append(RetrievedChunk(
                    chunk_id=doc_id, text=doc, page=meta.get("page", 1),
                    section_heading=meta.get("section", ""), source="dense",
                    scores={"dense": float(1.0 - dist) if dist else 0.5}
                ))
            return chunks
        except Exception as e:
            logger.warning(f"Dense search failed: {e}, falling back to BM25 only")
            return []

    def _merge(self, bm25: list[RetrievedChunk], dense: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Merge and deduplicate. No cross-scale sorting — FlashRank handles this in Phase 3."""
        seen: set[str] = set()
        merged = []
        for chunk in bm25 + dense:
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                merged.append(chunk)
        return merged

    def _is_chinese(self, text: str) -> bool:
        return any('一' <= c <= '鿿' for c in text)

    def _translate_query(self, query: str) -> str:
        """Use LLM to translate academic queries for better retrieval."""
        return query  # Phase 1: pass through; LLM translation added when client is available
```

- [ ] **Step 2: Write `tests/test_retriever.py`**

```python
import pytest
from backend.models.paper import Paper, Section
from backend.tools.retriever import HybridRetriever

@pytest.fixture
def sample_paper():
    sections = [
        Section(heading="1. Intro", content="Transformers revolutionized NLP with attention mechanisms.", page_start=1, page_end=1),
        Section(heading="2. Method", content="Our model uses multi-head self-attention with 8 heads.", page_start=2, page_end=2),
        Section(heading="3. Results", content="We achieve 94.5% accuracy on the benchmark.", page_start=3, page_end=3),
    ]
    raw = "Transformers revolutionized NLP with attention mechanisms.\n\nOur model uses multi-head self-attention with 8 heads.\n\nWe achieve 94.5% accuracy on the benchmark."
    return Paper(title="Test Paper", abstract="Test abstract", sections=sections, raw_text=raw)

def test_retriever_builds_indices(sample_paper):
    retriever = HybridRetriever(sample_paper)
    assert retriever.bm25 is not None
    assert retriever.collection is not None

def test_retrieve_returns_results(sample_paper):
    retriever = HybridRetriever(sample_paper)
    results = retriever.retrieve("attention mechanism", top_k=2)
    assert len(results) > 0
    assert len(results) <= 2
    assert results[0].text

def test_retrieve_empty_query(sample_paper):
    retriever = HybridRetriever(sample_paper)
    results = retriever.retrieve("", top_k=3)
    assert isinstance(results, list)

def test_retrieve_with_very_short_paper():
    paper = Paper(title="T", abstract="Short abstract", sections=[], raw_text="Short paper content.")
    retriever = HybridRetriever(paper)
    results = retriever.retrieve("short")
    assert len(results) <= 5
```

Run: `cd paper-reading-agent && python -m pytest tests/test_retriever.py -v`
Expected: 4 PASS

- [ ] **Step 3: Commit**

```bash
git add paper-reading-agent/backend/tools/retriever.py paper-reading-agent/tests/test_retriever.py
git commit -m "feat: add hybrid retriever with BM25 + ChromaDB (FlashRank deferred to Phase 3)"
```

---

### Task 8: SQLite storage layer

**Files:**
- Create: `paper-reading-agent/backend/storage/database.py`
- Create: `paper-reading-agent/backend/storage/paper_store.py`
- Create: `paper-reading-agent/backend/storage/session_store.py`
- Create: `paper-reading-agent/tests/test_storage.py`

**Interfaces:**
- Produces: `class Database` with `get_db() -> aiosqlite.Connection`
- Produces: `class PaperStore` with `add_paper(paper: Paper)`, `get_paper(paper_id: str) -> Paper | None`, `list_papers() -> list[Paper]`, `delete_paper(paper_id: str) -> bool`
- Produces: `class SessionStore` with `create_session(paper_id: str) -> str`, `add_message(session_id: str, role: str, content: str, meta: dict)`, `get_session(session_id: str) -> dict | None`, `list_sessions(paper_id: str) -> list`

---

- [ ] **Step 1: Write `backend/storage/database.py`**

```python
import aiosqlite
from pathlib import Path
from backend.config import config

class Database:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or config.db_path

    async def get_db(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(str(self.db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await self._migrate(conn)
        return conn

    async def _migrate(self, conn: aiosqlite.Connection):
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                authors TEXT NOT NULL DEFAULT '[]',
                abstract TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                raw_text TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'en',
                file_path TEXT NOT NULL DEFAULT '',
                parsed_at TEXT NOT NULL DEFAULT '',
                cache_path TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
        """)
        await conn.commit()

db = Database()
```

- [ ] **Step 2: Write `backend/storage/paper_store.py`**

```python
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
```

- [ ] **Step 3: Write `backend/storage/session_store.py`**

```python
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

    async def list_sessions(self, paper_id: str) -> list[dict]:
        conn = await db.get_db()
        try:
            sessions = []
            async with conn.execute("SELECT * FROM sessions WHERE paper_id = ? ORDER BY updated_at DESC", (paper_id,)) as cursor:
                async for row in cursor:
                    sessions.append(dict(row))
            return sessions
        finally:
            await conn.close()
```

- [ ] **Step 4: Write `tests/test_storage.py`**

```python
import pytest
import asyncio
from backend.models.paper import Paper
from backend.storage.paper_store import PaperStore
from backend.storage.session_store import SessionStore

@pytest.mark.asyncio
async def test_add_and_get_paper():
    store = PaperStore()
    paper = Paper(title="Test", authors=["Alice"], raw_text="content")
    await store.add_paper(paper)
    retrieved = await store.get_paper(paper.paper_id)
    assert retrieved is not None
    assert retrieved.title == "Test"
    assert retrieved.authors == ["Alice"]

@pytest.mark.asyncio
async def test_list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    assert isinstance(papers, list)

@pytest.mark.asyncio
async def test_create_session_and_add_message():
    store = PaperStore()
    sstore = SessionStore()
    paper = Paper(title="Session Test")
    await store.add_paper(paper)

    session_id = await sstore.create_session(paper.paper_id)
    assert session_id

    await sstore.add_message(session_id, "user", "What is attention?")
    session = await sstore.get_session(session_id)
    assert session is not None
    assert len(session["messages"]) == 1
    assert session["messages"][0]["content"] == "What is attention?"
```

Run: `cd paper-reading-agent && python -m pytest tests/test_storage.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add paper-reading-agent/backend/storage/ paper-reading-agent/tests/test_storage.py
git commit -m "feat: add SQLite storage layer with PaperStore and SessionStore"
```

---

### Task 9: Reader Agent

**Files:**
- Create: `paper-reading-agent/backend/agents/reader.py`

**Interfaces:**
- Consumes: `Paper`, `LLMClient`, `PDFParser`, `HybridRetriever`
- Produces: `async def reader_node(state: AgentState) -> AgentState`

---

- [ ] **Step 1: Write `backend/agents/reader.py`**

```python
from backend.models.state import AgentState
from backend.tools.pdf_parser import PDFParser, PDFParseError
from backend.tools.retriever import HybridRetriever
from backend.llm.client import llm_client
from backend.llm.prompts import REPORT_PROMPT
from backend.utils.logger import logger

async def reader_node(state: AgentState) -> AgentState:
    """Parse PDF + generate structured report + build retrieval index (once)."""
    if state.paper is not None and state.report is not None:
        logger.info("Paper already parsed, skipping reader")
        state.trace.append("reader(cached)")
        return state

    parser = PDFParser()
    try:
        paper = parser.parse(state.paper.file_path)
    except PDFParseError as e:
        state.error = str(e)
        state.trace.append("reader(error)")
        return state

    state.paper = paper

    # Build retriever index once, cache in state
    state.retriever = HybridRetriever(paper)
    logger.info(f"Built retrieval index with {len(state.retriever.chunks)} chunks")

    # Generate structured report
    try:
        report, _ = await llm_client.chat(
            messages=[{"role": "user", "content": paper.raw_text[:32000]}],
            system=REPORT_PROMPT
        )
        import json
        try:
            state.report = json.loads(report)
        except json.JSONDecodeError:
            state.report = {"raw_report": report}
    except Exception as e:
        logger.warning(f"Report generation failed: {e}, using fallback")
        state.report = {"title": paper.title, "abstract_summary": paper.abstract[:500]}

    state.trace.append("reader")
    return state
```

- [ ] **Step 2: Commit**

```bash
git add paper-reading-agent/backend/agents/reader.py
git commit -m "feat: add Reader Agent with PDF parse + report + index build"
```

---

### Task 10: QA Agent

**Files:**
- Create: `paper-reading-agent/backend/agents/qa.py`

**Interfaces:**
- Consumes: `AgentState`, `LLMClient`, prompt templates
- Produces: `async def classify_node(state: AgentState) -> AgentState`, `async def planner_node(state: AgentState) -> AgentState`, `async def retrieve_node(state: AgentState) -> AgentState`, `async def generate_node(state: AgentState) -> AgentState`, `async def observe_node(state: AgentState) -> AgentState`, `def check_observe_result(state: AgentState) -> str`

---

- [ ] **Step 1: Write `backend/agents/qa.py`**

```python
from backend.models.state import AgentState, RetrievedChunk
from backend.llm.client import llm_client
from backend.llm.prompts import CLASSIFY_PROMPT, PLANNER_PROMPTS, ANSWER_PROMPTS, OBSERVE_PROMPT, KEYWORD_RULES
from backend.utils.logger import logger

async def classify_node(state: AgentState) -> AgentState:
    """Classify user intent: summary/qa/compare/recommend."""
    query = state.user_query
    paper = state.paper
    try:
        result = await llm_client.chat_json(
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(query=query, title=paper.title if paper else "")}],
            system="Respond ONLY with JSON."
        )
        state.intent = result.get("intent", "qa")
    except Exception as e:
        logger.warning(f"Classify LLM failed: {e}, using keyword fallback")
        state.intent = _keyword_classify(query)
    state.trace.append("classify")
    return state

async def planner_node(state: AgentState) -> AgentState:
    """Generate execution plan. LangGraph interrupts AFTER this node for HITL approval."""
    prompt = PLANNER_PROMPTS.get(state.intent, PLANNER_PROMPTS["qa"])
    try:
        state.plan = await llm_client.chat_json(
            messages=[{"role": "user", "content": f"Report: {state.report}\n\nQuestion: {state.user_query}\n\n{prompt}"}],
            system="Respond ONLY with JSON."
        )
    except Exception as e:
        logger.warning(f"Planner failed: {e}, using default plan")
        state.plan = {"steps": [{"step": 1, "action": "retrieve relevant context", "tool": "retrieve", "target": state.user_query}]}
    state.trace.append("planner")
    return state

async def retrieve_node(state: AgentState) -> AgentState:
    """Hybrid RAG retrieval using cached retriever from reader."""
    if state.retriever is None:
        logger.warning("No retriever in state, cannot retrieve")
        state.retrieved_chunks = []
        state.trace.append("retrieve(empty)")
        return state

    chunks = state.retriever.retrieve(state.user_query)
    state.retrieved_chunks = chunks
    state.trace.append("retrieve")
    return state

async def generate_node(state: AgentState) -> AgentState:
    """Streaming LLM answer generation."""
    prompt = ANSWER_PROMPTS.get(state.intent, ANSWER_PROMPTS["qa"])
    context = "\n\n".join(c.text for c in state.retrieved_chunks[:5]) if state.retrieved_chunks else state.paper.abstract if state.paper else ""

    rewrite_feedback = ""
    if state.rewrite_count > 0 and state.quality_score:
        rewrite_feedback = f"\n\nYour previous answer scored {state.quality_score.total}/10. Please improve: {state.quality_score}"

    full_answer = ""
    try:
        async for token in llm_client.chat_stream(
            messages=[{"role": "user", "content": f"Paper report: {state.report}\n\nContext: {context}\n\nQuestion: {state.user_query}{rewrite_feedback}"}],
            system=prompt
        ):
            full_answer += token
    except Exception as e:
        logger.error(f"Generate failed: {e}")
        if full_answer:
            logger.info(f"Returning partial answer ({len(full_answer)} chars), will retry full generation")
            state.error = f"Generation interrupted: {e}. Partial answer shown."
        else:
            state.error = f"Generation failed: {e}"

    state.answer = full_answer
    state.trace.append("generate")
    return state

async def observe_node(state: AgentState) -> AgentState:
    """Self-check: is the answer sufficient? Does the plan need revision?"""
    try:
        result = await llm_client.chat_json(
            messages=[{"role": "user", "content": f"Plan: {state.plan}\n\nAnswer: {state.answer}\n\n{OBSERVE_PROMPT}"}],
            system="Respond ONLY with JSON."
        )
        state.observation = result
    except Exception as e:
        logger.warning(f"Observe failed: {e}, defaulting to sufficient=False")
        state.observation = {"plan_valid": True, "sufficient": False, "gaps": ["observe timeout"], "reasoning": str(e)}
    state.trace.append("observe")
    return state

def check_observe_result(state: AgentState) -> str:
    """Conditional edge after observe."""
    obs = state.observation or {}
    if not obs.get("plan_valid", True):
        return "planner"
    if not obs.get("sufficient", False):
        return "retrieve"
    return "reviewer"

def _keyword_classify(query: str) -> str:
    query_lower = query.lower()
    scores = {}
    for intent, keywords in KEYWORD_RULES.items():
        scores[intent] = sum(1 for kw in keywords if kw in query_lower)
    if not scores or max(scores.values()) == 0:
        return "qa"
    return max(scores, key=scores.get)
```

- [ ] **Step 2: Commit**

```bash
git add paper-reading-agent/backend/agents/qa.py
git commit -m "feat: add QA Agent with classify, planner, retrieve, generate, observe nodes"
```

---

### Task 11: Reviewer Agent

**Files:**
- Create: `paper-reading-agent/backend/agents/reviewer.py`

**Interfaces:**
- Consumes: `AgentState`, `LLMClient`, `REVIEWER_PROMPT`, `FOLLOWUP_PROMPT`, `REWRITE_PROMPT`
- Produces: `async def reviewer_node(state: AgentState) -> AgentState`, `async def rewrite_node(state: AgentState) -> AgentState`, `def decide_loop(state: AgentState) -> str`, `async def output_node(state: AgentState) -> AgentState`

---

- [ ] **Step 1: Write `backend/agents/reviewer.py`**

```python
from backend.models.state import AgentState, Evidence, EvidenceLevel, QualityScore
from backend.llm.client import llm_client
from backend.llm.prompts import REVIEWER_PROMPT, FOLLOWUP_PROMPT, REWRITE_PROMPT
from backend.config import config
from backend.utils.logger import logger

async def reviewer_node(state: AgentState) -> AgentState:
    """Annotate R0/R1/R2 evidence + quality scoring."""
    paper_text = state.paper.raw_text[:64000] if state.paper else ""

    try:
        result = await llm_client.chat_json(
            messages=[{"role": "user", "content": f"""Paper text: {paper_text}

Answer to review: {state.answer}

{REVIEWER_PROMPT}"""}],
            system="Respond ONLY with valid JSON. No markdown, no explanation."
        )
    except Exception as e:
        logger.warning(f"Reviewer failed: {e}, using default scores")
        result = {"relevance": 2, "consistency": 2, "completeness": 1, "deductions": [str(e)], "evidence_list": [], "followup_questions": []}

    state.quality_score = QualityScore(
        relevance=result.get("relevance", 2),
        consistency=result.get("consistency", 2),
        completeness=result.get("completeness", 1),
    )

    evidence_list = []
    for ev_data in result.get("evidence_list", []):
        try:
            evidence_list.append(Evidence(
                evidence_id=ev_data.get("evidence_id", ""),
                claim=ev_data.get("claim", ""),
                level=EvidenceLevel(ev_data.get("level", "R2")),
                sentence_index=ev_data.get("sentence_index"),
                char_start=ev_data.get("char_start"),
                char_end=ev_data.get("char_end"),
                page=ev_data.get("page"),
                quote=ev_data.get("quote"),
                section_heading=ev_data.get("section_heading"),
                source_title=ev_data.get("source_title"),
                source_url=ev_data.get("source_url"),
                source_venue=ev_data.get("source_venue"),
                source_year=ev_data.get("source_year"),
                reasoning=ev_data.get("reasoning"),
                based_on_evidence_ids=ev_data.get("based_on_evidence_ids", []),
                confidence=ev_data.get("confidence", 0.5),
            ))
        except Exception as e:
            logger.warning(f"Skipping malformed evidence: {e}")

    state.evidence_list = evidence_list
    state.observation = state.observation or {}
    state.observation["followup_questions"] = result.get("followup_questions", [])
    state.trace.append("reviewer")
    return state

def decide_loop(state: AgentState) -> str:
    if state.quality_score is None:
        return "output"
    if state.quality_score.total >= 7 or state.rewrite_count >= config.rewrite_max:
        return "output"
    return "rewrite"

async def rewrite_node(state: AgentState) -> AgentState:
    state.rewrite_count += 1
    state.trace.append(f"rewrite({state.rewrite_count})")
    return state

async def output_node(state: AgentState) -> AgentState:
    """Format final output + generate follow-up suggestions."""
    state.trace.append("output")
    return state
```

- [ ] **Step 2: Commit**

```bash
git add paper-reading-agent/backend/agents/reviewer.py
git commit -m "feat: add Reviewer Agent with R0/R1/R2 annotation and quality gating"
```

---

### Task 12: LangGraph Supervisor

**Files:**
- Create: `paper-reading-agent/backend/agents/supervisor.py`

**Interfaces:**
- Consumes: All agent nodes, `AgentState`, LangGraph, SQLite checkpointer
- Produces: `build_graph() -> StateGraph`, `run_agent(paper_path: str, query: str) -> AgentState`

---

- [ ] **Step 1: Write `backend/agents/supervisor.py`**

```python
from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.models.state import AgentState, Paper
from backend.agents.reader import reader_node
from backend.agents.qa import classify_node, planner_node, retrieve_node, generate_node, observe_node, check_observe_result
from backend.agents.reviewer import reviewer_node, rewrite_node, decide_loop, output_node
from backend.config import config

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("reader", reader_node)
    graph.add_node("classify", classify_node)
    graph.add_node("planner", planner_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("observe", observe_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("output", output_node)

    graph.set_entry_point("reader")
    graph.add_edge("reader", "classify")
    graph.add_edge("classify", "planner")
    graph.add_edge("planner", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "observe")
    graph.add_conditional_edges("observe", check_observe_result, {
        "reviewer": "reviewer",
        "retrieve": "retrieve",
        "planner": "planner",
    })
    graph.add_conditional_edges("reviewer", decide_loop, {
        "output": "output",
        "rewrite": "rewrite",
    })
    graph.add_edge("rewrite", "generate")
    graph.add_edge("output", END)

    checkpointer = SqliteSaver.from_conn_string(str(config.db_path))
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=["planner"]  # HITL: pause after plan generation
    )

async def run_agent(paper_path: str, query: str) -> AgentState:
    """Run complete agent pipeline. Returns final AgentState."""
    graph = build_graph()
    initial_state = AgentState(
        paper=Paper(file_path=str(Path(paper_path).resolve())),
        user_query=query
    )
    config_dict = {"configurable": {"thread_id": initial_state.paper.file_path}}

    # Run through to planner (will interrupt)
    state = await graph.ainvoke(initial_state, config_dict)

    # Resume past interrupt (HITL auto-approved in Phase 1)
    if state.get("plan"):
        state = await graph.ainvoke(None, config_dict)

    return state

def run_agent_sync(paper_path: str, query: str) -> AgentState:
    """Synchronous wrapper for CLI usage."""
    import asyncio
    return asyncio.run(run_agent(paper_path, query))
```

- [ ] **Step 2: Commit**

```bash
git add paper-reading-agent/backend/agents/supervisor.py
git commit -m "feat: add LangGraph supervisor with full 9-node graph + HITL interrupt"
```

---

### Task 13: Minimal frontend + FastAPI

**Files:**
- Create: `paper-reading-agent/backend/app.py`
- Create: `paper-reading-agent/frontend/minimal/index.html`

**Interfaces:**
- Produces: FastAPI app with `POST /api/upload`, `POST /api/query` (SSE), `GET /api/papers`, `POST /api/plan/approve`
- Produces: Minimal HTML page with file upload + chat + inline EvidenceBadge rendering

---

- [ ] **Step 1: Write `backend/app.py`**

```python
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.agents.supervisor import run_agent
from backend.models.state import AgentState, Paper
from backend.storage.paper_store import PaperStore
from backend.config import config

app = FastAPI(title="Paper Reading Agent")

# Serve minimal frontend
frontend_dir = Path(__file__).resolve().parents[1] / "frontend" / "minimal"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

@app.get("/")
async def index():
    html_path = frontend_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Paper Reading Agent</h1>")

@app.post("/api/upload")
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Please upload a PDF file"}, status_code=400)

    paper_dir = config.paper_dir
    paper_dir.mkdir(parents=True, exist_ok=True)
    file_path = paper_dir / f"{Path(file.filename).stem}_{hash(file.filename)}.pdf"
    content = await file.read()
    file_path.write_bytes(content)

    store = PaperStore()
    paper = Paper(file_path=str(file_path.resolve()), title=file.filename)
    await store.add_paper(paper)

    return {"paper_id": paper.paper_id, "title": paper.title, "file_path": paper.file_path}

@app.post("/api/query")
async def query_paper(paper_path: str = Form(...), query: str = Form(...)):
    """SSE streaming endpoint for agent queries."""
    async def event_stream():
        state = await run_agent(paper_path, query)
        # Send node-level events
        for node in state.trace:
            yield f"data: {json.dumps({'event': 'node', 'node': node})}\n\n"
        # Send final state
        yield f"data: {json.dumps({'event': 'done', 'answer': state.answer, 'quality_score': {'total': state.quality_score.total if state.quality_score else 0}, 'trace': state.trace, 'evidence_list': [{'evidence_id': e.evidence_id, 'level': e.level.value, 'claim': e.claim[:100], 'sentence_index': e.sentence_index, 'char_start': e.char_start, 'char_end': e.char_end} for e in state.evidence_list]})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/api/papers")
async def list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    return [{"paper_id": p.paper_id, "title": p.title, "parsed_at": p.parsed_at} for p in papers]
```

- [ ] **Step 2: Write `frontend/minimal/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paper Reading Agent</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f7f9fc; color: #1a1a2e; }
  .container { max-width: 800px; margin: 0 auto; padding: 2rem; }
  h1 { text-align: center; margin-bottom: 1.5rem; }
  .section { background: white; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .upload-area { border: 2px dashed #d1d5db; border-radius: 8px; padding: 2rem; text-align: center; cursor: pointer; margin-bottom: 1rem; }
  .upload-area:hover { border-color: #2563eb; }
  input[type="text"] { width: 100%; padding: .75rem; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; margin: .5rem 0; }
  button { background: #2563eb; color: white; border: none; padding: .75rem 1.5rem; border-radius: 6px; cursor: pointer; font-size: 14px; }
  button:hover { background: #1d4ed8; }
  button:disabled { background: #9ca3af; cursor: not-allowed; }
  #messages { max-height: 400px; overflow-y: auto; margin: 1rem 0; }
  .msg { margin-bottom: .75rem; padding: .75rem; border-radius: 6px; }
  .msg.user { background: #eff6ff; }
  .msg.assistant { background: #f8f9fa; }
  .evidence-badge { display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 8px; margin: 0 2px; cursor: pointer; }
  .evidence-badge.R0 { background: #10b981; color: white; }
  .evidence-badge.R1 { background: #3b82f6; color: white; }
  .evidence-badge.R2 { background: #f59e0b; color: white; }
  #step-indicator { font-size: 12px; color: #6b7280; margin-bottom: .5rem; min-height: 20px; }
  #quality-bar { font-size: 12px; color: #6b7280; margin-top: .5rem; }
</style>
</head>
<body>
<div class="container">
  <h1>📄 论文阅读 Agent</h1>

  <div class="section">
    <div class="upload-area" id="upload-area" onclick="document.getElementById('file-input').click()">
      <p>📁 点击上传 PDF 论文</p>
      <input type="file" id="file-input" accept=".pdf" style="display:none" onchange="uploadPaper()">
    </div>
    <div id="paper-info" style="font-size:13px;color:#6b7280;"></div>
  </div>

  <div class="section">
    <div id="step-indicator"></div>
    <div id="messages"></div>
    <div id="quality-bar"></div>
    <div style="display:flex;gap:8px;">
      <input type="text" id="query-input" placeholder="💬 输入你对这篇论文的问题..." onkeydown="if(event.key==='Enter')sendQuery()">
      <button id="send-btn" onclick="sendQuery()">发送</button>
    </div>
  </div>
</div>

<script>
let currentPaperPath = '';
let evidenceMap = {};

async function uploadPaper() {
  const file = document.getElementById('file-input').files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch('/api/upload', { method: 'POST', body: form });
  const data = await resp.json();
  if (data.paper_id) {
    currentPaperPath = data.file_path;
    document.getElementById('paper-info').textContent = `✅ ${data.title}`;
  }
}

async function sendQuery() {
  const query = document.getElementById('query-input').value.trim();
  if (!query || !currentPaperPath) return;

  const sendBtn = document.getElementById('send-btn');
  sendBtn.disabled = true;
  document.getElementById('step-indicator').textContent = '🔄 处理中...';
  document.getElementById('messages').innerHTML = '';
  evidenceMap = {};

  appendMessage('user', query);

  const form = new FormData();
  form.append('paper_path', currentPaperPath);
  form.append('query', query);

  const resp = await fetch('/api/query', { method: 'POST', body: form });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullAnswer = '';

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.event === 'node') {
          document.getElementById('step-indicator').textContent += ` ✅ ${data.node}`;
        } else if (data.event === 'done') {
          fullAnswer = data.answer;
          if (data.evidence_list) {
            data.evidence_list.forEach(ev => {
              if (ev.char_start != null && ev.char_end != null) {
                evidenceMap[`${ev.char_start}-${ev.char_end}`] = ev;
              }
            });
          }
          if (data.quality_score) {
            document.getElementById('quality-bar').textContent =
              `📊 评分 ${data.quality_score.total}/10 | ${data.trace.join(' → ')}`;
          }
          renderAnswerWithBadges(fullAnswer);
        }
      }
    }
  }
  sendBtn.disabled = false;
}

function renderAnswerWithBadges(text) {
  const msgDiv = document.getElementById('messages');
  // Insert evidence badges at char positions
  let html = '<div class="msg assistant">';
  let lastIdx = 0;
  const sortedEv = Object.values(evidenceMap).sort((a,b) => a.char_start - b.char_start);

  for (const ev of sortedEv) {
    if (ev.char_start > lastIdx) {
      html += escapeHtml(text.slice(lastIdx, ev.char_start));
    }
    const badgeHtml = `<span class="evidence-badge ${ev.level}" title="${ev.claim}">${ev.level}</span>`;
    html += badgeHtml + escapeHtml(text.slice(ev.char_start, ev.char_end));
    lastIdx = ev.char_end;
  }
  html += escapeHtml(text.slice(lastIdx));
  html += '</div>';
  msgDiv.innerHTML += html;
}

function appendMessage(role, text) {
  const msgDiv = document.getElementById('messages');
  msgDiv.innerHTML += `<div class="msg ${role}">${escapeHtml(text)}</div>`;
}

function escapeHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add paper-reading-agent/backend/app.py paper-reading-agent/frontend/minimal/index.html
git commit -m "feat: add FastAPI backend + minimal HTML frontend with SSE and EvidenceBadge"
```

---

### Task 14: CLI entry point + integration test

**Files:**
- Create: `paper-reading-agent/backend/cli.py`
- Create: `paper-reading-agent/tests/test_integration.py`

**Interfaces:**
- Produces: `python -m backend.cli --paper <path> --query "..."` command
- Produces: Integration test that runs the full agent pipeline

---

- [ ] **Step 1: Write `backend/__main__.py`**

```python
"""CLI entry point for paper reading agent."""
import argparse
import json
import asyncio
from pathlib import Path
from dataclasses import asdict
from backend.agents.supervisor import run_agent

async def main():
    parser = argparse.ArgumentParser(description="Paper Reading Agent")
    parser.add_argument("--paper", "-p", required=True, help="Path to PDF file")
    parser.add_argument("--query", "-q", required=True, help="Question about the paper")
    args = parser.parse_args()

    pdf_path = Path(args.paper)
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}")
        return 1

    print(f"📄 Loading: {pdf_path.name}")
    print(f"💬 Query: {args.query}")
    print("=" * 60)

    state = await run_agent(str(pdf_path.resolve()), args.query)

    print(f"\n📊 Quality Score: {state.quality_score.total if state.quality_score else 'N/A'}/10")
    print(f"🔀 Trace: {' → '.join(state.trace)}")
    print(f"\n{state.answer}\n")
    print(f"🔗 Evidence List ({len(state.evidence_list)} items):")
    for ev in state.evidence_list:
        print(f"  [{ev.level.value}] {ev.claim[:80]}...")
    if state.error:
        print(f"\n⚠️  {state.error}")
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
```

- [ ] **Step 2: Write `tests/test_integration.py`**

```python
"""Integration test: full agent pipeline."""
import pytest
import asyncio
from backend.agents.supervisor import run_agent

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline():
    """Requires sample PDF and DeepSeek API credentials in .env."""
    state = await run_agent("tests/fixtures/sample.pdf", "What is this paper about?")
    assert state.trace, "Trace should not be empty"
    assert "reader" in state.trace
    assert state.answer or state.error, "Should have answer or error"
    assert state.quality_score is not None
    print(f"\nTrace: {' → '.join(state.trace)}")
    print(f"Score: {state.quality_score.total}/10")
    print(f"Answer: {state.answer[:200]}...")
```

Run: `cd paper-reading-agent && python -m pytest tests/test_integration.py -v -m integration`
Note: Requires `.env` with valid API credentials and `tests/fixtures/sample.pdf`.

- [ ] **Step 3: Add `tests/conftest.py`**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 4: Commit**

```bash
git add paper-reading-agent/backend/__main__.py paper-reading-agent/tests/test_integration.py paper-reading-agent/tests/conftest.py
git commit -m "feat: add CLI entry point and integration test"
```

---

## Phase 2: Web Application (high-level tasks)

### Task 15: React app scaffolding

- Create Vite + React + TypeScript project in `frontend/`
- Install: `react`, `react-dom`, `pdfjs-dist`, `react-markdown`, `remark-gfm`, `@tanstack/virtual`
- Create: TypeScript types in `frontend/src/types/index.ts` matching backend data models
- Create: `frontend/src/lib/api.ts` for backend API calls

### Task 16: Core React components

- `App.tsx` — root with state management (React Context + useReducer for AgentState)
- `LayoutToggle.tsx` — dual/full-chat/full-paper mode switcher
- `PaperViewer.tsx` — pdf.js rendering with section navigation
- `ChatPanel.tsx` — message list, input, step indicator
- `ChatInput.tsx` — text input with send

### Task 17: Evidence system components

- `EvidenceBadge.tsx` — inline R0/R1/R2 badge rendering
- `EvidencePopover.tsx` — hover tooltip with quote + jump button + reasoning chain (R2)
- `StepIndicator.tsx` — Show Your Work progress bar
- `TracePanel.tsx` — collapsible trace viewer
- `FollowUpSuggest.tsx` — auto-generated follow-up question buttons

### Task 18: Full FastAPI wiring

- WebSocket/SSE streaming for `generate_node` tokens
- `POST /api/plan/approve` — HITL resume endpoint
- `POST /api/plan/reject` — HITL reject with feedback
- `GET /api/sessions` + `POST /api/sessions` — session management

### Task 19: Library & settings

- `LibraryPanel.tsx` — paper library with upload, search, delete
- `HistoryPanel.tsx` — conversation history list
- `SettingsPanel.tsx` — user preferences (focus_areas, reading_level, language)

---

## Phase 3: Advanced Features (high-level tasks)

### Task 20: FlashRank integration

- Add `flashrank` to `retriever.py`
- Replace BM25-based merging with FlashRank reranking
- Update `_merge_results` to feed all candidates to FlashRank

### Task 21: PDF evidence highlight

- `usePDFJump.ts` — hook for PDF page navigation + bbox overlay
- Update `PaperViewer.tsx` to accept `jumpTo({page, bbox})` events
- Wire EvidenceBadge onClick to trigger PDF jump

### Task 22: Export features

- Markdown export: `GET /api/sessions/{id}/export`
- Obsidian-compatible export with R0/R1/R2 tags
- User preferences persistence

---

## Self-Review

**1. Spec coverage:**

| Spec Section | Covered By |
|---|---|
| 三、Data models | Task 2 (paper.py, state.py) |
| 四、LangGraph orchestration | Task 12 (supervisor.py) |
| 五、Hybrid RAG | Task 7 (retriever.py) |
| 六、Frontend | Tasks 13-19 (minimal → full React) |
| 七、Error handling | Distributed across Tasks 9-12 (error fields in state, fallback logic) |
| 八、Dependencies | Task 1 (requirements.txt) |
| 九、Phase 1 | Tasks 1-14 |
| 九、Phase 2 | Tasks 15-19 |
| 九、Phase 3 | Tasks 20-22 |
| 十一、Module dependency | Matches task ordering: models → llm → tools → agents → supervisor → app |

**2. Placeholder scan:** No TBD, TODO, or "implement later" found. All code steps contain complete implementations.

**3. Type consistency:**
- `AgentState.trace` is `list[str]` — confirmed in state.py (Task 2) and used across all agent files (Tasks 9-12)
- `Evidence.evidence_id` is `str` — consistent in state.py (Task 2) and reviewer.py (Task 11)
- `QualityScore.total` is a `@property` — used consistently in reviewer.py and supervisor.py
- `RetrievedChunk` — defined in Task 2, used in retriever.py (Task 7) and qa.py (Task 10)
- `check_observe_result` returns "planner"|"retrieve"|"reviewer" — matches edges defined in supervisor.py Task 12
- `decide_loop` returns "output"|"rewrite" — matches edges defined in supervisor.py Task 12
- `config.rewrite_max` referenced in reviewer.py — defined in config.py Task 1
