# Paper Reading Agent V2 — 验收后 Bug 修复 + Phase 6 规划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复验收测试中发现的 6 个 bug，使所有核心功能（检索、JSON 解析、Token 流式、前端 UI）正常工作，然后定义 Phase 6 范围。

**Architecture:** 分三个阶段 — (A) 后端关键 bug 修复：DeepSeek API thinking 块处理、token 流式、Retriever；(B) 前端验证 + 剩余场景测试；(C) 基于验收结果定义 Phase 6。

**Tech Stack:** Python 3.12, LangGraph 1.2.5, DeepSeek API (Anthropic 兼容), React 18 + TypeScript, FastAPI, ChromaDB

## Global Constraints

- 每次改动后运行 `pytest && vitest run`，保持 191+ 测试通过
- 每个 bug 单独 commit
- 所有 API 调用使用 `backend.config.config` 中配置的凭据
- 不修改 `.env` 文件中的 API key
- LangGraph msgpack 类型注册仅作 forward-compat，不阻塞当前功能
- Retriever 使用 `sentence-transformers` (all-MiniLM-L6-v2)，已安装

---

## Phase A: 后端关键 Bug 修复

### Task 1: 修复 DeepSeek API thinking 块导致 JSON 解析失败

**诊断根因：**
DeepSeek V4 Pro 模型的 Anthropic 兼容端点返回 content 数组时，推理内容放在 `type: "thinking"` 块中（含 `thinking` 字段），实际回答在 `type: "text"` 块中（含 `text` 字段）。当前 `llm_client.chat()` 仅查找 `type == "text"` 的块 — 当 thinking 块排在前面或 text 块不存在时，content 为空字符串，导致 `json.loads("")` 失败。

受影响节点：classify、planner、generate、reviewer（通过 `chat_json()` 调用）。

**Files:**
- Modify: `paper-reading-agent/backend/llm/client.py:102-109`

**Interfaces:**
- Consumes: `httpx.Response.json()` → `{"content": [{"type": "text", "text": "..."}, ...]}`
- Produces: `chat()` returns `tuple[str, dict]` — content 从所有 text 块拼接

- [ ] **Step 1: 检查当前代码**

```bash
# 查看当前 chat() 方法的 content 提取逻辑
grep -n "type.*text" paper-reading-agent/backend/llm/client.py
```

- [ ] **Step 2: 修复 `chat()` 方法 — 从所有 text 块中提取内容**

当前代码 (`client.py:106-109`):
```python
content = ""
for block in data.get("content", []):
    if block.get("type") == "text":
        content = block.get("text", "")
        break
```

替换为：
```python
text_parts = []
for block in data.get("content", []):
    if block.get("type") == "text":
        text = block.get("text", "")
        if text:
            text_parts.append(text)
content = "\n".join(text_parts) if text_parts else ""
```

Note: 跳过 `type == "thinking"` 块，仅收集 `type == "text"` 块的内容，用换行连接。

- [ ] **Step 3: 同样修复 `chat_stream()` 的 delta 处理**

当前代码 (`client.py:136`):
```python
if delta.get("type") == "text_delta":
```

确认 DeepSeek 流式 API 的 delta type。如果也返回 `thinking_delta`，仅保留 `text_delta` 处理即可（当前代码已正确过滤）。

- [ ] **Step 4: 运行现有测试确认不引入回归**

```bash
cd paper-reading-agent
python -m pytest tests/ -x -q
```
Expected: 131 passed

- [ ] **Step 5: 手动验证修复**

```bash
cd paper-reading-agent && python -c "
import asyncio
from backend.llm.client import llm_client

async def test():
    # 测试简单 JSON 响应
    result = await llm_client.chat_json(
        messages=[{'role': 'user', 'content': 'Reply with JSON: {\"answer\": \"hello\"}'}],
        system='You are a helpful assistant.'
    )
    print(f'Result: {result}')
    assert 'answer' in result, f'Expected answer key, got: {result}'

asyncio.run(test())
"
```
Expected: `Result: {'answer': 'hello'}` 或类似有效 JSON

- [ ] **Step 6: 提交**

```bash
git add paper-reading-agent/backend/llm/client.py
git commit -m "fix: handle DeepSeek thinking blocks in chat() content extraction

DeepSeek V4 Pro returns content blocks with type='thinking' (reasoning)
alongside type='text' blocks. The previous code only matched type='text'
and broke on the first block if it was thinking.

Fix: collect text from ALL type='text' blocks, join with newlines.
Fixes classify/planner/generate/reviewer JSON parse failures."
```

---

### Task 2: 修复 Token 流式传输不工作

**诊断：**
SSE 协议中 `event: token` 事件从未出现。需要检查两个环节：
1. `stream_graph()` 中的 token 拦截逻辑 — `on_chat_model_stream` 事件
2. 后端 LLM 节点是否调用 `chat_stream()` 而非 `chat()`

当前发现：`generate_node` 使用 `llm_client.chat()`（非流式），导致 supervisor 层的 token 拦截无法获取流式数据。

**Files:**
- Modify: `paper-reading-agent/backend/agents/qa.py` — generate_node
- Verify: `paper-reading-agent/backend/agents/supervisor.py` — token 提取

- [ ] **Step 1: 查看 generate_node 的实现**

```bash
grep -n "chat\|chat_stream" paper-reading-agent/backend/agents/qa.py
```

- [ ] **Step 2: 查看当前 generate_node 代码**

读取 `qa.py` 中 generate_node 的实现。

- [ ] **Step 3: 将 generate_node 改为流式输出**

当前使用 `chat()` 非流式调用。需要改为 `chat_stream()` 并通过 LangGraph state 传递 tokens。

注意：LangGraph 的 `on_chat_model_stream` 事件需要 LangChain chat model 对象才能自动触发。当前直接调用 `httpx` 的流式 API，不会产生 `on_chat_model_stream` 事件。

**方案 A（推荐）：在 SSE 层直接包装**

修改 `stream_graph()` 中的 token 处理，直接监听 LangGraph 节点输出中的流式内容。

**方案 B：改用 LangChain DeepSeek 适配器**

使用 `langchain_deepseek` 的 `ChatDeepSeek` 替换自定义 `LLMClient`，自动获得 `on_chat_model_stream` 事件。

**选择方案 A**，改动最小：

在 `stream_graph()` 中，为 generate 节点添加特殊处理 — 不依赖 `on_chat_model_stream`，而是从 state 的 answer 字段增量提取差异。

具体实现：在 `generate_node` 之后，捕获 state.answer 的变化，发送 token 事件。

伪代码：
```python
# In stream_graph(), Segment 2:
last_answer = ""
async for event in graph.astream_events(None, config_dict, version="v2"):
    ...
    # After generate completes, extract answer delta
    if kind == "on_chain_end" and node_name == "generate":
        output = data.get("output", {})
        new_answer = _get_state_field(output, "answer")
        if new_answer and new_answer != last_answer:
            delta = new_answer[len(last_answer):]
            if delta:
                yield f"event: token\ndata: {json.dumps({'event': 'token', 'token': delta})}\n\n"
            last_answer = new_answer
```

实际实现时，在每个 `on_chain_end` 后检查 state.answer 的变化。

- [ ] **Step 4: 实现增量 token 发送**

修改 `stream_graph()` 的 Segment 1 和 Segment 2，添加 answer 变化追踪。

在 supervisor.py 中添加：
```python
_last_answer = [""]  # mutable container for closure

def _emit_answer_delta(data: dict, last_answer: list) -> str | None:
    """Check if answer changed and return delta tokens."""
    output = data.get("output", {})
    new_answer = ""
    if isinstance(output, dict):
        new_answer = output.get("answer", "")
    else:
        new_answer = getattr(output, "answer", "")
    if new_answer and new_answer != last_answer[0]:
        delta = new_answer[len(last_answer[0]):]
        last_answer[0] = new_answer
        return delta
    return None
```

然后在 generate 和 reviewer 的 `on_chain_end` 中调用。

- [ ] **Step 5: 运行测试**

```bash
cd paper-reading-agent
python -m pytest tests/ -x -q
cd frontend && ./node_modules/.bin/vitest run
```
Expected: 131 backend + 60 frontend = 191 passed

- [ ] **Step 6: 提交**

```bash
git add paper-reading-agent/backend/agents/supervisor.py paper-reading-agent/backend/agents/qa.py
git commit -m "fix: emit SSE token events from state answer deltas

LangGraph's on_chat_model_stream event requires LangChain chat models,
but our LLM client uses direct httpx calls. Instead, track answer changes
across node boundaries and emit incremental token events in the SSE stream."
```

---

### Task 3: 验证 Retriever 正常工作

**背景：**
已安装 `sentence-transformers`、`chromadb`、`opentelemetry` 等依赖。首次运行时模型自动下载到 `~/.cache/huggingface/`。需要验证 retriever 索引构建和检索正常。

- [ ] **Step 1: 测试 Retriever 独立运行**

```bash
cd paper-reading-agent && python -c "
from backend.tools.retriever import HybridRetriever
from backend.models.paper import Paper

# 使用真实论文文本片段
text = '''The Transformer is a novel neural network architecture based solely on attention mechanisms. 
It dispenses with recurrence and convolutions entirely. Experiments on two machine translation tasks 
show these models to be superior in quality while being more parallelizable and requiring significantly 
less time to train. Our model achieves 28.4 BLEU on the WMT 2014 English-to-German translation task.'''

p = Paper(raw_text=text, title='Test Transformer')
try:
    r = HybridRetriever(p)
    chunks = r.retrieve('What is the Transformer architecture?')
    assert len(chunks) > 0, 'Retriever returned no chunks'
    print(f'OK: {len(chunks)} chunks retrieved')
    for c in chunks[:2]:
        print(f'  [{c.source}] {c.text[:80]}...')
except Exception as e:
    print(f'FAILED: {e}')
    import sys; sys.exit(1)
"
```
Expected: retriever 成功返回 >0 个 chunks

- [ ] **Step 2: 重启服务器并测试完整 QA 流程**

```bash
# Kill existing server
python -c "import subprocess; [subprocess.run(['taskkill','/F','/PID',l.split()[-1]],capture_output=True) for l in subprocess.run(['netstat','-ano'],capture_output=True,text=True).stdout.split(chr(10)) if ':8000' in l and 'LISTENING' in l]"

# Start fresh
cd paper-reading-agent
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 &
sleep 3

# Run QA test
python -c "
import asyncio
from backend.agents.supervisor import run_agent
async def test():
    state = await run_agent('1bd7856f-b905-4be3-8a14-8c767271feb0', 'What is this paper about?')
    print(f'Chunks: {len(state.retrieved_chunks)}')
    print(f'Evidence: {len(state.evidence_list)}')
    print(f'Answer: {state.answer[:100]}')
    assert len(state.retrieved_chunks) > 0, 'No chunks! Retriever not working'
    print('PASS: Retriever + QA flow works')
asyncio.run(test())
"
```
Expected: chunks > 0, evidence > 0, answer 非空

- [ ] **Step 3: 提交状态记录**

如果测试通过，记录到 progress 文件中。

---

### Task 4: 修复论文标题存储问题

**问题：**
`PaperStore` 中部分论文的 title 字段存储为文件名的 `.pdf` 后缀版本或 PDF 第一行版权声明（如 "Provided proper attribution is provided, Google hereby grants permission to"），而非真实论文标题。

**根因：**
上传流程 (`app.py:132`) 用 `title=file.filename` 创建 Paper，reader_node 中的 PDF 解析结果（包含正确标题）没有回写到 PaperStore。

- [ ] **Step 1: 在 pdf_parser.py 中添加标题提取方法**

Read `pdf_parser.py` 的 `_parse_pymupdf` 方法，了解 pages 结构。在 `PDFParser` 类中添加：

```python
def _extract_title(self, pages: list[dict]) -> str:
    """Extract paper title from first page text.

    Strategy: find the first meaningful sentence on page 1 that
    doesn't look like a copyright notice, author line, or header.
    """
    if not pages:
        return ""
    sentences = pages[0].get("sentences", [])
    if not sentences:
        return ""
    # Filter out copyright/attribution lines
    skip_patterns = [
        "provided proper attribution",
        "google hereby grants",
        "permission to reproduce",
    ]
    for s in sentences[:6]:
        text = s["text"].strip()
        if not text:
            continue
        if any(p in text.lower() for p in skip_patterns):
            continue
        # Skip lines that look like author emails or URLs
        if "@" in text or "http" in text.lower():
            continue
        # First meaningful line = title
        return text
    return ""
```

- [ ] **Step 2: 在 parse() 中调用 _extract_title**

修改 `pdf_parser.py` 的 `parse()` 方法（~line 19），在 `_parse_pymupdf` 返回后设置 title：

```python
# After: paper = self._parse_pymupdf(path, paper)
# Add:
if not paper.title or paper.title.endswith(".pdf"):
    paper.title = self._extract_title(paper._pages_cache) or paper.title
```

注意：需要在 `_parse_pymupdf` 中将 pages 缓存到 `paper._pages_cache` 以便后续使用。

- [ ] **Step 3: 在 reader_node 中回写更新的标题到 PaperStore**

Read `reader.py`。在 reader_node 完成 PDF 解析后（约 line 30-46），添加：

```python
# Persist extracted title back to DB
if paper.title and not paper.title.endswith(".pdf"):
    from backend.storage.paper_store import PaperStore
    ps = PaperStore()
    await ps.add_paper(paper)
```

- [ ] **Step 4: 更新现有 DB 中的错误标题（一次性脚本）**

创建 `scripts/fix_titles.py`:
```python
"""One-off script to fix paper titles in DB by re-parsing PDFs."""
import asyncio, sys
sys.path.insert(0, '.')
from backend.storage.paper_store import PaperStore
from backend.tools.pdf_parser import PDFParser

async def main():
    store = PaperStore()
    parser = PDFParser()
    papers = await store.list_papers()
    fixed = 0
    for p in papers:
        if p.file_path and (p.title.endswith('.pdf') or 'provided proper' in p.title.lower()):
            parsed = parser.parse(p.file_path)
            if parsed.title and not parsed.title.endswith('.pdf'):
                p.title = parsed.title
                await store.add_paper(p)
                fixed += 1
                print(f'Fixed: {p.paper_id} -> {p.title[:80]}')
    print(f'Fixed {fixed} papers')

asyncio.run(main())
```

运行: `cd paper-reading-agent && python scripts/fix_titles.py`

- [ ] **Step 4: 运行测试**

```bash
cd paper-reading-agent
python -m pytest tests/ -x -q
```

- [ ] **Step 5: 提交**

```bash
git add paper-reading-agent/backend/tools/pdf_parser.py paper-reading-agent/backend/agents/reader.py
git commit -m "fix: extract paper title from PDF text instead of using filename

PDF parser now extracts the actual title from first-page large-font text,
falling back to filename. Reader node persists the extracted title to
PaperStore after parsing."
```

---

## Phase B: 前端验证 + 剩余验收场景

### Task 5: 前端 UI 验证（场景 5-10）

**目标：** 通过浏览器验证剩余验收场景，发现前端集成问题。

- [ ] **Step 1: 构建前端并启动**

```bash
cd paper-reading-agent/frontend
./node_modules/.bin/vite build
# 服务器已在 localhost:8000 运行
```

- [ ] **Step 2: 打开浏览器 http://localhost:8000 验证以下场景**

| # | 场景 | 验证点 |
|---|------|--------|
| 5 | Save external result | 外部论文可保存到论文库 |
| 6 | Import BibTeX | .bib 文件导入正常 |
| 7 | Compare 3 papers | 对比报告生成 |
| 8 | Search "transformer" | 搜索过滤正确 |
| 9 | Filter External Save | 来源筛选正确 |
| 10 | Click no-PDF paper | 元数据卡片显示 |

- [ ] **Step 3: 记录发现的问题**

按 `🔴/🟡/🟢` 严重度分类记录到 issue 中。

- [ ] **Step 4: 提交前端修复（如有）**

```bash
git add paper-reading-agent/frontend/src/
git commit -m "fix: frontend UI issues found during acceptance testing"
```

---

## Phase C: Phase 6 范围定义

### Task 6: 整理验收结果并定义 Phase 6

- [ ] **Step 1: 汇总所有发现**

整理以下内容到设计文档：
- Phase A-D 修复的 bug 列表
- Phase B 发现的前端问题
- 成功验证的功能列表
- 已知限制

- [ ] **Step 2: 评估候选方向**

根据验收测试结果和实际使用体验，评估以下 Phase 6 候选方向：

| 方向 | 触发条件 | 优先级 |
|------|----------|--------|
| 对比报告追问 | 对比后需要追问细分问题 | |
| arXiv PDF 一键下载 | 保存外部论文后需要下载 | |
| Markdown 表格渲染 | 对比报告表格难以阅读 | |
| 响应式优化 | 手机端体验差 | |
| 论文库标签/分类 | 论文超过 50 条管理困难 | |
| LLM 调用优化 | QA 延迟 5 分钟需优化 | |

- [ ] **Step 3: 选择 Phase 6 方向并撰写 Spec**

选择优先级最高的 1-2 个方向，撰写设计文档到 `docs/superpowers/specs/2026-06-XX-paper-reading-agent-v2-phase6-design.md`

- [ ] **Step 4: 提交**

```bash
git add docs/superpowers/specs/
git commit -m "docs: define Phase 6 scope based on acceptance testing findings"
```

---

## 执行顺序

```
Task 1 (fix: thinking blocks) 
  → Task 2 (fix: token streaming) [parallel with Task 3]
  → Task 3 (verify: retriever)
    → Task 4 (fix: paper title)
      → Task 5 (frontend verify)
        → Task 6 (define Phase 6)
```

Task 2 和 Task 3 可并行执行。Task 1 是所有后续工作的前提（JSON 解析修复后 classify/planner/generate/reviewer 才能正常返回数据）。
