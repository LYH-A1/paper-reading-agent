# Paper Reading Agent V2 — 验收后总结与 Phase 6 范围定义

> 日期：2026-06-21 | 当前版本：v2 Phase 5.5 + Bugfix | 测试：191 passed

---

## 一、本迭代修复总结

### 已修复 Bug (4 commits)

| # | 问题 | 严重度 | Commit | 状态 |
|---|------|--------|--------|------|
| 1 | Paper UUID 被 LangGraph checkpoint 覆盖 | 🔴 | `8035d84` | ✅ |
| 2 | paper_id 在 checkpoint 反序列化后变空 | 🔴 | `2d7cd32` | ✅ |
| 3 | DeepSeek thinking 块导致 JSON 解析失败 | 🔴 | `1263372` | ✅ |
| 4 | Token 流式传输不产生事件 | 🟡 | `c0dc26b` | ✅ |
| 5 | 论文标题存储为版权声明/文件名 | 🟡 | `33392f5` | ✅ |
| 6 | 缺失依赖 (pydantic-settings/opentelemetry/sentence-transformers) | 🟡 | 手动安装 | ✅ |

### 已安装的缺失依赖

- `pydantic-settings` — ChromaDB 依赖
- `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` — ChromaDB 遥测
- `sentence-transformers` — 向量嵌入 (all-MiniLM-L6-v2 ~90MB)
- `pypika` — ChromaDB SQL 构建
- `typer` — ChromaDB CLI

---

## 二、验收测试结果

### API 级别验证 ✅

| 场景 | 结果 | 备注 |
|------|------|------|
| PDF 解析 (标题/作者/章节) | ✅ | 修复后标题正确提取 |
| QA 流程端到端 | ✅ | 回答质量好，有证据引用 |
| 质量评分 | ✅ | 10/10 (relevance 3 + consistency 4 + completeness 3) |
| 证据系统 (R0/R1/R2) | ✅ | 2 条证据生成 |
| 追问生成 | ✅ | 3 个相关追问 |
| Paper ID 正确保存 | ✅ | 修复后 verified |
| SSE 协议 (init/node/done) | ✅ | 事件正确发送 |
| Token 流式 | ✅ | 修复后 answer delta 产生 token 事件 |

### 未完成 (需模型下载)

| 场景 | 状态 | 备注 |
|------|------|------|
| Retriever 检索 | ⏳ | sentence-transformers 模型下载中（~90MB，网速慢） |

### 已知限制 (非阻断)

| 限制 | 影响 | 建议 |
|------|------|------|
| QA 延迟 ~5 分钟 | 高 | DeepSeek API + 多次 LLM 调用 (classify→planner→generate×3→reviewer×3)，需优化调用次数或使用更快的模型 |
| Classify 仍偶发失败 | 低 | 关键词 fallback 兜底正常工作 |
| Retriever 需首次下载模型 | 中 | 一次性成本，后续缓存命中 |
| 论文库数据质量 | 低 | 之前上传的论文标题需要在下次 QA 时自动修复（reader_node 已加入 DB 回写） |
| LangGraph msgpack 类型未注册 | 低 | 仅日志警告，不影响功能 |

---

## 三、Phase 6 候选方向评估

基于验收测试中发现的真实问题，评估以下候选方向：

| 方向 | 评分 | 依据 |
|------|------|------|
| **🔴 LLM 调用优化** | ⭐⭐⭐⭐⭐ | QA 延迟 5 分钟是最大痛点。减少不必要的 LLM 调用（合并 classify+planner，减少 rewrite 循环），考虑使用更快的模型处理简单任务 |
| **🟡 对比报告追问** | ⭐⭐⭐ | Compare 模式已实现但缺少交互式追问能力 |
| **🟡 arXiv PDF 一键下载** | ⭐⭐ | 用户保存外部论文后需要手动到 arXiv 下载 |
| **🟢 Markdown 表格渲染** | ⭐⭐ | 对比报告中的表格在聊天中显示为纯文本 |
| **🟢 论文库标签/分类** | ⭐ | 论文库现在有 117 条（含测试数据），管理需求未显现 |
| **🟢 响应式优化** | ⭐ | 移动端使用场景不明确 |

### 决策

**Phase 6 = LLM 调用优化为主**，附带对比报告追问支持。

理由：
1. QA 延迟 5 分钟是用户可感知的最大问题
2. 优化调用次数后预计可将延迟降低 40-60%（至 2-3 分钟）
3. 对比报告追问是自然延伸，代码量小

---

## 四、Phase 6 初步范围

### P6-1: LLM 调用合并与缓存

- **Classify + Planner 合并**：两个简单 JSON 调用合为一个，减少 1 次 API 往返
- **Classify 结果缓存**：同一 session 内 classify 结果复用
- **Rewrite 上限从 2 降为 1**：实验数据显示第二次 rewrite 的边际收益很低
- **Generate 温度参数**：使用 `temperature=0.3` 替代默认 `0.7`，减少 reviewer 触发的 rewrite 概率

预期效果：QA 延迟从 ~5 分钟降至 ~2-3 分钟。

### P6-2: 对比报告追问

- API: `POST /api/compare/{thread_id}/followup` 在已有对比上下文中追问
- 复用 compare supervisor + state 中的 papers/comparison_report
- 前端: CompareSelectModal 完成后在 ChatPanel 中支持追问输入

### 暂不纳入

- arXiv PDF 下载 (需求不强烈)
- Markdown 表格渲染 (可先用纯文本)
- 论文库标签 (论文数量不足)

---

## 五、执行状态

```
✅ Phase 1-5.5 全部完成
✅ 验收后 Bugfix 完成 (6 bugs fixed)
✅ 191 tests passing
⏳ Retriever 模型下载中
📋 Phase 6 scope defined — LLM optimization + Compare followup
```

下一步：等待 retriever 模型下载完成 → 完整 QA 验证 → 开始 Phase 6 设计。
