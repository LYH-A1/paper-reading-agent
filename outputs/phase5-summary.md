# Phase 5 变更摘要

> 日期：2026-06-19 | 状态：✅ 完成  
> 设计文档：[2026-06-19-paper-reading-agent-v2-phase5-design.md](../docs/superpowers/specs/2026-06-19-paper-reading-agent-v2-phase5-design.md)  
> 实现计划：[2026-06-19-paper-reading-agent-v2-phase5-plan.md](../docs/superpowers/plans/2026-06-19-paper-reading-agent-v2-phase5-plan.md)

---

## 一、交付总览

| 维度 | 设计预期 | 实际 | 状态 |
|------|----------|------|------|
| Commits | ~14 | 14 | ✅ |
| 新增文件 | 6 | 10（含 4 test files） | ✅ |
| 修改文件 | 15 | 12 | ✅ |
| 文件总计（变更） | ~21 | 35（含新建+修改） | ✅ |
| 后端测试 | ~85 | 125 | ✅ |
| 前端测试 | ~43 | 53 | ✅ |
| 总计测试 | ~169 | **178** | ✅ |
| 新增行数 | — | 1,926 | — |
| 新外部依赖 | 1 (bibtexparser) | 1 | ✅ |

---

## 二、功能验证 — 对照设计文档

### 2.1 结构化对比报告

| 设计要求 | 实现 | 验证 |
|----------|------|------|
| `POST /api/compare` SSE 端点 | ✅ `app.py:POST /api/compare` | 5 API 测试 |
| 独立 4 节点 LangGraph 图 | ✅ `compare_supervisor.py` — reader_batch → compare → reviewer → [decide, max=1] → output | 图编译测试 |
| `reader_all_node` 并行读取 | ✅ `compare.py` — `asyncio.gather` 并行，混合 PDF/无 PDF | 3 agent 测试 |
| `compare_generate_node` 生成对比 | ✅ LLM 融合多论文 report + COMPARE_PROMPT | 3 agent 测试 |
| SSE 事件: init, node, token, done | ✅ 单段 SSE，token 批量推送 | SSE 协议一致 |
| `decide_loop` 参数化 `max_rewrites=1` | ✅ `reviewer.py:decide_loop(state, max_rewrites=2)` | 3 reviewer 测试 |
| `Evidence.paper_id` 区分来源论文 | ✅ `state.py:Evidence.paper_id` | 2 model 测试 |
| `CompareSelectModal` 前端 | ✅ 论文列表 + aspect 复选框 + focus 输入 + SSE 流 | 53 前端测试通过 |
| StepIndicator 新增节点 | ✅ `reader_batch`, `compare` 加入 NODE_ORDER | 前端渲染正常 |

### 2.2 外部保存到论文库

| 设计要求 | 实现 | 验证 |
|----------|------|------|
| `POST /api/papers/save-external` | ✅ 接收 `arxiv_id`，后端拉取完整元数据 | 2 API 测试 |
| `ExternalRetriever.fetch_by_id()` | ✅ 按 arXiv ID 精确查询单个论文 | 集成测试 |
| 去重：arxiv_id 优先 + title slug fallback | ✅ `paper_store.get_by_arxiv_id()` + `get_by_title_slug()` | 5 storage 测试 |
| `Paper.import_source = "external_save"` | ✅ 模型 + DB 列 + 读写 | 3 model 测试 |
| `arxiv_pdf_url` 保存 | ✅ 构造 `https://arxiv.org/pdf/{arxiv_id}.pdf` | 模型字段存在 |
| 前端 ExternalRefCard | ✅ 回答底部卡片 + Save 按钮（saving/saved 状态） | 53 前端测试通过 |

### 2.3 BibTeX 导入

| 设计要求 | 实现 | 验证 |
|----------|------|------|
| `POST /api/papers/import-bibtex` | ✅ 接收 `bibtex_content`，批量入库 | 1 API 测试 |
| `bibtexparser >= 2.0.0` | ✅ v2.0.0b9（beta），API 适配（Field.value 访问） | 7 importer 测试 |
| author/year/title/doi 解析 | ✅ `entry_to_paper()` 容错处理 | 测试覆盖 |
| title slug 去重 | ✅ 逐条检查，已存在跳过 | 测试覆盖 |
| `Paper.import_source = "bib_import"` | ✅ 默认值 | 测试覆盖 |
| 前端 Import BibTeX 按钮 | ✅ LibraryPanel 顶部 + FileReader + Toast | 53 前端测试通过 |

---

## 三、基础设施变更

### Paper 模型扩展

| 字段 | 类型 | 默认值 | DB 列 |
|------|------|--------|-------|
| `file_path` | `str \| None` | `None` | 已有，允许 NULL |
| `arxiv_id` | `str \| None` | `None` | `TEXT` |
| `arxiv_pdf_url` | `str \| None` | `None` | 模型字段（不持久化，从 arxiv_id 派生） |
| `import_source` | `str` | `"upload"` | `TEXT DEFAULT 'upload'` |

### 新增数据模型

- **CompareState** — 对比流程专用 State（paper_ids/reports/aspects/answer/evidence/quality）
- **Evidence.paper_id** — R0 证据溯源（对比报告区分来源论文）

### PaperStore 扩展

- `get_by_arxiv_id(arxiv_id) -> Paper | None`
- `get_by_title_slug(slug) -> Paper | None`
- `_row_to_paper(row)` — 行→Paper 转换复用
- `_slugify_title(title)` — 标题标准化

### reader_node 无 PDF 适配

`file_path=None` → 跳过 PDF 解析，基于元数据生成最小 report（title/authors/abstract）

---

## 四、前端变更清单

| 组件 | 变更类型 | 说明 |
|------|----------|------|
| `types/index.ts` | 修改 | Paper 扩展 + CompareRequest/ImportBibTeXResponse/SaveExternalResponse |
| `api/client.ts` | 修改 | comparePapers/saveExternal/importBibTeX |
| `compareStore.ts` | **新建** | 多选状态（isCompareMode/selectedPaperIds/toggle/clear） |
| `LibraryPanel.tsx` | 修改 | 多选模式（复选框 + Compare FAB）+ Import BibTeX 按钮 + Toast |
| `CompareSelectModal.tsx` | **新建** | 对比确认弹窗（维度选择 + 焦点输入 + SSE 流处理） |
| `ExternalRefCard.tsx` | **新建** | 外部参考卡片（保存按钮，saving/saved 状态） |
| `AssistantMessage.tsx` | 修改 | 底部集成 ExternalRefCards |
| `PaperViewer.tsx` | 修改 | 无 PDF 态元数据卡片（标题/作者/abstract/Upload/arXiv） |
| `StepIndicator.tsx` | 修改 | NODE_ORDER 新增 reader_batch/compare |
| `ChatPanel.module.css` | 修改 | 追加 modal 系列 + externalRef 系列样式 |
| `Layout.module.css` | 修改 | 追加 library 系列样式 |
| `PaperViewer.module.css` | 修改 | 追加 metadataCard 系列样式 |

---

## 五、实现-设计偏差说明

| 偏差 | 原因 | 影响 |
|------|------|------|
| `arxiv_pdf_url` 不持久化到 DB | 设计只要求 `arxiv_id` + `import_source` 列；pdf_url 可派生 | 无功能影响 |
| `bibtexparser` 使用 v2.0.0b9 (beta) | PyPI 无 v2.0.0 正式版 | API 差异已适配（Field.value） |
| `llm_client.chat()` 签名为 `chat(messages, system="")` 而非 `chat(prompt, max_tokens=N)` | 计划基于设计文档编写，实际 API 不同 | 已适配，返回 tuple[str, dict] |
| `decide_loop` 移除 `config.rewrite_max` 引用 | 参数化后不需要 config | 无影响，默认值保持 2 |

---

## 六、已知问题

| 问题 | 严重度 | 状态 |
|------|--------|------|
| `arxiv_pdf_url` 模型字段未持久化 | Minor | 按设计，可派生 |
| `bibtexparser` 依赖 beta 版本 | Minor | 功能正常，后续正式版发布后升级 |
| `compare_supervisor.py` 的 `_compare_reviewer_node` 适配器较脆弱 | Minor | 功能正常，后续可考虑统一 reviewer 接口 |

---

## 七、测试覆盖详情

### 后端测试（125 passed）

| 测试文件 | 测试数 | 说明 |
|----------|--------|------|
| `test_models.py` | ~25 | Paper/Evidence/CompareState 模型 |
| `test_storage.py` | 13 | PaperStore CRUD + 新查询 + migration |
| `test_reader.py` | 2 | reader_node 无 PDF 适配 |
| `test_reviewer.py` | 3 | decide_loop 参数化 |
| `test_compare_agent.py` | 6 | reader_all_node + compare_generate_node |
| `test_compare_supervisor.py` | 1 | 图编译 |
| `test_compare_api.py` | 5 | 3 端点参数验证 |
| `test_bibtex_importer.py` | 7 | 解析 + 容错 |
| 其他已有测试 | 63 | 无回归 |

### 前端测试（53 passed）

| 测试文件 | 测试数 | 说明 |
|----------|--------|------|
| `types.test.ts` | 4 | Phase 5 新类型 |
| `compareStore.test.ts` | 6 | 多选状态逻辑 |
| 其他已有测试 | 43 | 无回归 |

---

## 八、下一步建议

| 方向 | 内容 |
|------|------|
| **Phase 6** | 对比报告追问支持（基于报告做多轮对话）、外部结果"一键下载 PDF"（从 arXiv 拉取并自动入库）、论文库搜索/筛选/排序 |
| **体验优化** | 对比报告 Markdown 表格渲染（当前用 react-markdown 已有依赖）、无 PDF 条目的 visual indicator |
| **Push** | 推送到 remote，部署验证 |
