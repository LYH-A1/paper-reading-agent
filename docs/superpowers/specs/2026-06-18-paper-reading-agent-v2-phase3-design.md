# 论文阅读 Agent V2 — Phase 3 设计文档

> 日期：2026-06-18 | 状态：已确认  
> 父文档：[V2 整体设计](2026-06-17-paper-reading-agent-v2-design.md)  
> Phase 2 设计：[Phase 2 前端设计](2026-06-18-paper-reading-agent-v2-phase2-design.md)

---

## 一、概述

Phase 3 包含三个独立功能，零耦合，可并行开发测试：

| 功能 | 层级 | 核心改动 |
|------|------|----------|
| **FlashRank 重排序** | 后端 | 新建 `backend/tools/reranker.py`，修改 `retriever.py` |
| **对话导出** | 前后端 | 新 API `/api/sessions/{id}/export` + ChatPanel 导出按钮 |
| **用户偏好持久化** | 前后端 | zustand persist（前端 UI 偏好）+ `/api/preferences` CRUD（后端 Agent 偏好） |

---

## 二、FlashRank 重排序

### 2.1 架构

```
backend/tools/reranker.py
├── Reranker (抽象接口)
│   └── rerank(query: str, passages: list[RetrievedChunk]) → list[RetrievedChunk]
├── FlashRankReranker    → flashrank CrossEncoder，懒加载
├── BM25FallbackReranker → 现有 BM25 排序逻辑（兜底）
└── get_reranker(name?: str) → Reranker（工厂函数）
```

### 2.2 行为规格

**FlashRankReranker：**

- 构造函数接收 `model: str = "ms-marco-MiniLM-L-12-v2"`
- `_ranker` 属性初始为 `None`，首次调用 `rerank()` 时才触发模型下载
- 模型下载期间（`_ensure_loaded()` 被阻塞时）不阻塞服务启动
- 加载失败抛出 `RerankerLoadError`，由工厂函数降级处理

```python
class FlashRankReranker(Reranker):
    def __init__(self, model: str = "ms-marco-MiniLM-L-12-v2"):
        self.model_name = model
        self._ranker = None  # 懒加载

    def _ensure_loaded(self):
        if self._ranker is None:
            try:
                from flashrank import Ranker
                self._ranker = Ranker(model_name=self.model_name)
            except Exception as e:
                raise RerankerLoadError(f"FlashRank model download failed: {e}")

    def rerank(self, query: str, passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
        self._ensure_loaded()
        # 构建 flashrank 输入 → 获取 scores → 排序返回
```

**BM25FallbackReranker：**

- 使用现有 `merged.sort(key=lambda c: c.scores.get("bm25", 0), reverse=True)` 逻辑
- 零外部依赖，始终可用

**工厂函数：**

```python
def get_reranker(name: str | None = None) -> Reranker:
    name = name or os.getenv("RERANKER_BACKEND", "flashrank")
    if name == "flashrank":
        try:
            return FlashRankReranker()
        except RerankerLoadError:
            logger.warning("FlashRank unavailable, falling back to BM25")
            return BM25FallbackReranker()
    return BM25FallbackReranker()
```

环境变量 `RERANKER_BACKEND` 可强制走 BM25，方便 CI/测试环境。

### 2.3 集成点

**修改 `backend/tools/retriever.py`：**

- `HybridRetriever.__init__` 增加 `reranker: Reranker | None = None` 参数
- 默认值：`reranker = get_reranker()`
- `retrieve()` 方法中第 75 行：
  ```python
  # 旧代码：merged.sort(key=lambda c: c.scores.get("bm25", 0), reverse=True)
  # 新代码：
  merged = self.reranker.rerank(query, merged)
  results = merged[:top_k]
  ```
- 低分检测（`avg_score < 0.3` → 扩展 top-10）保留，在 rerank 之后执行

### 2.4 依赖

- `pip install flashrank`（首次运行自动下载 ~50MB 模型）
- 无其他新依赖

---

## 三、对话导出

### 3.1 API

```
GET /api/sessions/{session_id}/export?format=md|json
```

**Markdown 输出（`Content-Type: text/markdown`）：**

```markdown
# Session: <session_id>
Date: 2026-06-18 14:30 | Paper: <paper title>

---

## Q: What methodology does the paper use?

**Answer:** The paper proposes a novel...

**Evidence (3 items):**
- [R0] "Our method achieves F1=0.94..." (Page 4, §4. Experiments)
- [R1] "Consistent with Smith et al. (2023)..." (Source: ACL 2023)
- [R2] "This approach is generalizable..." (Based on R0#1, R0#3, confidence: 72%)

**Quality:** 8/10 (Relevance: 3/3, Consistency: 3/4, Completeness: 2/3)

---

## Q: What are the limitations?
...

---

## Suggested Follow-ups
- How does this compare to method X?
- What datasets were used in the experiments?
```

**JSON 输出（`Content-Type: application/json`）：**

```json
{
  "session_id": "...",
  "paper_id": "...",
  "paper_title": "...",
  "exported_at": "2026-06-18T14:30:00Z",
  "messages": [
    {
      "role": "user",
      "content": "...",
      "timestamp": "..."
    },
    {
      "role": "assistant",
      "content": "...",
      "evidence_list": [...],
      "quality_score": {...},
      "trace": [...],
      "followup_questions": [...],
      "timestamp": "..."
    }
  ]
}
```

### 3.2 SSE 协议变更

**init 事件补充 `session_id`：**

```
event: init → { thread_id: "uuid-xxx", session_id: "uuid-yyy" }
```

- `thread_id` — LangGraph checkpoint 标识（后端生成，用于 HITL 重连）
- `session_id` — 业务会话标识（后端生成，用于导出和历史）
- Segment 1 开头即发送，Segment 2 不重复发送

**done 事件补充 `session_id` 和 `followup_questions`：**

```json
{
  "event": "done",
  "answer": "...",
  "session_id": "uuid-yyy",
  "quality_score": {
    "total": 8,
    "relevance": 3,
    "consistency": 3,
    "completeness": 2
  },
  "evidence_list": [...],
  "trace": [...],
  "followup_questions": ["Q1?", "Q2?"]
}
```

### 3.3 前端改动

**ChatPanel.tsx：** 顶部增加一个 `⬇ Export` 按钮
- 仅在 `status === 'complete'` 且有 `currentSessionId` 时显示
- 点击弹出下拉：`Markdown (.md)` / `JSON (.json)`
- 选择后 fetch API → 触发浏览器下载
- 文件名：`session-{slugify(paperTitle)}-{date}.md` 或 `.json`

**chatStore.ts：** 增加 `currentSessionId: string | null` 字段
- `init` 事件中设置
- `reset()` 时清空

**文件名 slugify 规则：**
- 保留 a-z, A-Z, 0-9, 中文, -, _
- 其他字符替换为 `-`
- 连续 `-` 合并为一个
- 截断至 50 字符

### 3.4 后端实现

- 使用现有 `SessionStore.get_session()` 获取消息列表
- Markdown：字符串拼接，`Content-Disposition: attachment` 头触发下载
- JSON：`json.dumps()` + `Content-Disposition` 头
- 同时更新 `SessionStore` 支持在 done 事件后将 evidence_list、quality_score、trace 存入消息的 meta 字段

---

## 四、用户偏好持久化

### 4.1 前端 — zustand persist（UI 偏好）

**修改 `appStore.ts`：**

```typescript
import { persist } from 'zustand/middleware'

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({ ... }),
    {
      name: 'paper-reading-agent-ui',
      partialize: (state) => ({
        layout: state.layout,
        sidebarOpen: state.sidebarOpen,
      }),
    }
  )
)
```

持久化范围（可后续扩展）：
- `layout` — `'dual' | 'chat' | 'paper'`
- `sidebarOpen` — `boolean`

### 4.2 后端 — Agent 偏好 API

当前 SQLite `preferences` 表已存在（key-value），增加 REST API：

```
GET  /api/preferences  → { "reranker": "flashrank", "top_k": 5, "language": "auto", "embedding_model": "auto" }
PUT  /api/preferences  → body: { "reranker": "bm25", "top_k": 10 }
```

**偏好白名单（只允许这些 key）：**

| Key | 默认值 | 类型 | 说明 |
|-----|--------|------|------|
| `reranker` | `"flashrank"` | string | `flashrank` / `bm25` |
| `top_k` | `5` | int | 检索返回数量（1-20） |
| `language` | `"auto"` | string | `en` / `zh` / `auto` |
| `embedding_model` | `"auto"` | string | 嵌入模型名 |

**类型处理：**
- `preferences` 表统一存储字符串（VARCHAR）
- `GET /api/preferences` 返回时自动推断类型：`"5"` → `5`, `"flashrank"` → `"flashrank"`
- `PUT /api/preferences` 接受 JSON 原生类型（string/number），存入前转为字符串
- `HybridRetriever` 使用时：`int(prefs.get("top_k", 5))`

**安全约束：**
- 仅白名单 key 可写入，未知 key 返回 400
- `top_k` 范围校验：1 ≤ top_k ≤ 20
- `reranker` 校验：仅 `flashrank` / `bm25`

### 4.3 前端设置入口

**Sidebar.tsx：** 底部增加 `⚙ Settings` 按钮
- 点击展开简单的 key-value 表单（4 个偏好项）
- `reranker` 和 `language` 用下拉选择
- `top_k` 用数字输入
- `embedding_model` 用文本输入
- 保存后调用 `PUT /api/preferences`

---

## 五、文件变更清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `backend/tools/reranker.py` | Reranker 接口 + FlashRankReranker + BM25FallbackReranker + factory |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/tools/retriever.py` | 集成 Reranker 参数，替换排序逻辑 |
| `backend/agents/supervisor.py` | init 事件增加 session_id，done 事件补充字段，session 创建与消息记录 |
| `backend/app.py` | 新增 `/api/sessions/{id}/export`, `/api/preferences` GET/PUT |
| `backend/storage/session_store.py` | 可能扩展 meta 存储 |
| `frontend/src/store/appStore.ts` | 增加 zustand persist middleware |
| `frontend/src/store/chatStore.ts` | 增加 `currentSessionId` 字段 |
| `frontend/src/components/ChatPanel/ChatPanel.tsx` | 增加导出按钮 |
| `frontend/src/components/Layout/Sidebar.tsx` | 增加 Settings 面板 |

### 新依赖

| 包 | 用途 |
|----|------|
| `flashrank` | 轻量级 CrossEncoder 重排序 |

---

## 六、测试策略

| 功能 | 测试内容 |
|------|----------|
| **FlashRank** | `Reranker` 接口合规、`FlashRankReranker` 懒加载、`BM25FallbackReranker` 排序正确、`get_reranker()` 环境变量覆盖、`RerankerLoadError` 降级 |
| **对话导出** | Markdown 输出结构、JSON 输出结构、session 不存在 404、空消息列表处理、文件名 slugify |
| **用户偏好** | GET 返回默认值、PUT 更新、白名单拒绝、top_k 范围校验、前端 persist 读写 |

---

## 七、风险与应对

| 风险 | 可能性 | 影响 | 应对 |
|------|--------|------|------|
| FlashRank 模型下载慢或失败 | 中 | 首次使用卡顿 | 懒加载 + 自动降级 BM25 + 环境变量强制跳过 |
| 导出大会话 OOM | 低 | 单次对话消息 < 100 条 | JSON 序列化内存可控；必要时加 streaming 导出 |
| 偏好表并发写入冲突 | 低 | 单用户场景 | SQLite WAL 模式已启用，`key PRIMARY KEY` 保证幂等 |
| zustand persist 与 SSR 冲突 | 无 | 纯 SPA | 不涉及 |
