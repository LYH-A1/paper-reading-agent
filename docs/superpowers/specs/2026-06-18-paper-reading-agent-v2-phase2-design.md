# 论文阅读 Agent V2 — Phase 2 前端设计

> 日期：2026-06-18 | 状态：已确认  
> 父文档：[V2 整体设计](2026-06-17-paper-reading-agent-v2-design.md)  
> 对话记录：本轮 Brainstorming 确认了 Phase 2 的三大关键决策

---

## 一、相对于原 V2 设计的变更

原 V2 设计将 PDF 证据高亮和 HITL 审批放在 Phase 3，本设计将其提前至 Phase 2，与 React 前端一并交付。

| 维度 | 原设计 | 新设计 | 理由 |
|------|--------|--------|------|
| PDF 高亮跳转 | Phase 3 | Phase 2 | 核心差异化交互，不与 React 一起交付无法验证 SSE + EvidenceBadge 渲染效果 |
| PDF 渲染方案 | 未明确 | Canvas + 文本层叠加 | 保证视觉保真，透明文本层实现选中和高亮，PDF.js 标准做法 |
| HITL 策略 | 答案审批（未明确位置） | 计划审批（planner 后暂停） | 用户审批计划方向而非逐条审核证据，避免拖慢交互节奏 |

---

## 二、组件架构

### 2.1 组件树

```
App.tsx
├── TopBar
│   ├── PaperTitle（当前论文标题）
│   └── LayoutToggle（双栏 / 全宽对话 / 全宽论文）
│
├── MainContent（flex row）
│   ├── LeftPanel: PaperViewer（可折叠，默认双栏模式下占 45% 宽度）
│   │   ├── PDFToolbar（页码导航、缩放、全文搜索 toggle）
│   │   ├── PDFCanvas（pdf.js Canvas 渲染层）
│   │   ├── PDFTextLayer（透明文本层 — 选中 + 证据高亮叠层）
│   │   └── SectionNav（左侧章节缩略导航，提取 Section headings）
│   │
│   └── RightPanel: ChatPanel
│       ├── StepIndicator（Show Your Work 步骤条，实时显示节点状态）
│       ├── PlanApprovalBanner（HITL 计划审批 — 仅 planner 暂停后出现）
│       ├── MessageList
│       │   ├── UserMessage
│       │   └── AssistantMessage
│       │       ├── AnswerMarkdown（含 EvidenceBadge 内联渲染）
│       │       ├── EvidencePopover（悬停 tooltip + "跳转到原文" 按钮）
│       │       ├── QualityBar（评分分项展示 + R0/R1/R2 计数）
│       │       ├── TracePanel（折叠思考链路）
│       │       └── FollowUpSuggest（追问按钮组）
│       └── ChatInput（含 intent 快捷切换：摘要/问答/对比/推荐）
│
└── Sidebar（抽屉式，右侧滑出）
    ├── LibraryPanel（论文库列表）
    └── SessionHistory（历史对话，按时间倒序）
```

### 2.2 核心交互流

#### 证据高亮跳转

Evidence 中有两套独立的定位坐标，用途不同：

- **`char_start/char_end`**：在 **answer 文本**中的字符偏移，ChatPanel 用它在 answer 中插入 `<EvidenceBadge>`
- **`page + quote`**：在 **PDF 原文**中的位置线索，PDFTextLayer 用它搜索匹配 bbox 坐标实现高亮

两步是完全独立的：`char_start/char_end` 定位徽标插入点，`quote` 文本搜索定位 PDF 高亮区域。

```
1. Reviewer 返回 evidence_list（含 page + quote + char_start/char_end + sentence_index + section_heading）
2. ChatPanel 在 answer Markdown 的 char_start-char_end 位置插入 <EvidenceBadge level={R0}>
3. 用户点击 [R0] 徽标：
   ├── 读取 evidence.page + evidence.quote
   ├── 在 PDF 当前页 TextLayer 中搜索 quote 文本 → 匹配到 sentence bbox 坐标
   │   匹配策略：精确子串匹配 → 模糊匹配（允许 2 字差异）→ 降级为整段高亮
   ├── PaperViewer 切换页面到 evidence.page
   ├── 在匹配到的 bbox 上叠加半透明黄色高亮（`rgba(255, 230, 0, 0.35)`）
   ├── EvidencePopover 弹出原文引用 + 置信度 + section_heading
   └── 再次点击同一徽标 → 取消高亮
4. 用户悬停 [R2] 徽标：
   ├── EvidencePopover 展示推理链：R2 ← based_on [R0(#3), R0(#5)]
   ├── [R0(#3)] 可点击 → 递归展开 + PDF 跳转
   └── 形成证据链导航（上限 3 层递归）
```

#### HITL 计划审批（条件触发）

HITL 仅在复杂意图时触发，简单问答自动跳过以避免拖慢交互：

```python
# backend/agents/supervisor.py
def should_interrupt(state: AgentState) -> list[str]:
    if state.intent in ("compare", "recommend"):
        return ["planner"]  # 复杂意图暂停，用户确认计划
    return []               # summary/qa 自动通过，无 HITL
```

触发审批时：

```
1. 后端 planner 节点执行完毕 → should_interrupt 判断后 LangGraph interrupt_after 暂停
2. SSE 发送 event: hitl → 后端主动关闭连接
3. 前端展示 PlanApprovalBanner：
   ├── 执行计划步骤列表（step 1/2/3：action + tool + target）
   ├── [批准] 按钮 → POST /api/approve { thread_id, approved: true }
   ├── [修改] 按钮 → 展开编辑框，修改步骤文字 → POST /api/approve { thread_id, approved: true, feedback: "..." }
   └── [取消] 按钮 → POST /api/approve { thread_id, approved: false }
4. 前端收到 /api/approve 200 OK → 发起新 GET /api/query?thread_id=xxx
5. 后端从 checkpoint 恢复，继续执行 retrieve → generate → ... → done
6. 第二段 SSE 结束，前端移除 PlanApprovalBanner，展示最终结果
```

#### R2 推理链递归展示

```
R2 徽标悬停：
  ┌─────────────────────────────────────┐
  │ R2 · 推论/判断                      │
  │ "该方法在医学影像领域同样适用"        │
  │                                     │
  │ 推理依据：                          │
  │ ├─ R0(#3)  "在 CT 数据集上 F1=0.94" │  ← 点击跳转 PDF
  │ ├─ R0(#5)  "模型在超声图像泛化良好"   │  ← 点击跳转 PDF
  │ └─ 置信度：0.72                     │
  │                                     │
  │ [跳转到 R0(#3) 原文]                │
  └─────────────────────────────────────┘
```

### 2.3 布局模式

| 模式 | 触发 | 效果 |
|------|------|------|
| 双栏（默认） | 默认 | LeftPanel 45% + RightPanel 55%，拖拽分隔条可调比例 |
| 全宽对话 | LayoutToggle 或 PDF 关闭 | PaperViewer 隐藏，ChatPanel 全宽 |
| 全宽论文 | LayoutToggle | ChatPanel 折叠为底部抽屉，PaperViewer 全宽 |
| 窄屏（<768px） | 响应式自动 | 单列堆叠，PaperViewer 和 ChatPanel 用 Tab 切换 |

---

## 三、SSE 协议

### 3.1 两段式连接（核心设计）

HITL 暂停期间 **SSE 连接必须断开**，审批后由前端发起新 SSE 重连。原因：浏览器 SSE 空闲超时 30-60s，代理/CDN 更短，保持长连接挂起必然断连且需要复杂的重连+状态恢复逻辑。

```
第一段 SSE（planner 暂停前）
  前端 GET /api/query?paper_id=xxx&query=yyy → SSE 建立
  event: init    → { thread_id: "uuid-xxx" }         ← 后端生成，前端保存用于重连
  event: node    → { node: "reader" }
  event: node    → { node: "classify" }
  event: node    → { node: "planner" }
  event: hitl    → { type: "plan_approval", plan: { steps: [...] } }
  → 后端关闭连接（HTTP 200 正常结束）

用户操作（HTTP 请求/响应）
  POST /api/approve { thread_id, approved: true, feedback?: string }
  → 200 OK { status: "resumed" }

第二段 SSE（恢复后执行）
  前端 GET /api/query?thread_id=xxx → 新 SSE 建立
  event: node    → { node: "retrieve" }
  event: node    → { node: "generate" }
  event: token   → { text: "The", node: "generate" }
  event: token   → { text: " paper", node: "generate" }
  ...
  event: node    → { node: "observe" }
  event: node    → { node: "reviewer" }
  event: done    → { quality_score, evidence_list, trace, followup_questions }
  → 后端关闭连接
```

### 3.2 事件类型规范

| 事件 | 触发节点 | 数据结构 |
|------|---------|----------|
| `init` | SSE 连接建立后 | `{ thread_id: string }` — 后端生成，前端保存用于 HITL 审批和重连 |
| `node` | 每个节点完成后 | `{ node: string }` |
| `hitl` | planner 后暂停（仅 compare/recommend） | `{ type: "plan_approval", plan: { steps: [{ step, action, tool, target }] } }` |
| `token` | generate 流式输出 | `{ text: string, node: "generate" }` |
| `done` | 最终输出完成 | `{ answer: string, quality_score: { total, relevance, consistency, completeness }, evidence_list: Evidence[], trace: string[], followup_questions: string[] }` |

### 3.3 新增与变更的 API 端点

| 端点 | 方法 | 用途 | 变更类型 |
|------|------|------|----------|
| `/api/query` | GET | SSE 流式查询：首次传入 `?paper_id=xxx&query=yyy`，HITL 恢复传入 `?thread_id=xxx` | 改 POST → GET |
| `/api/approve` | POST | HITL 审批：`{ thread_id, approved: bool, feedback?: string }` | **新增** |
| `/api/pdf/{paper_id}` | GET | 返回 PDF 二进制流（`Content-Type: application/pdf`） | **新增** |
| `/api/pdf/{paper_id}/text` | GET | 返回文本层数据：`{ pages: [{ page: int, sentences: [{ text, bbox, char_start, char_end }] }] }` | **新增** |

`/api/pdf/{paper_id}/text` schema：
```json
{
  "pages": [
    {
      "page": 1,
      "width": 612,
      "height": 792,
      "sentences": [
        {
          "text": "The paper proposes a novel method...",
          "char_start": 0,
          "char_end": 41,
          "bbox": [72, 100, 540, 112]
        }
      ]
    }
  ]
}
```

---

## 四、前端数据流

### 4.1 Hooks 设计

#### `useSSE(paperPath, query, threadId?)`

```
状态：
  - nodes: string[]              // 已完成节点列表（StepIndicator 展示）
  - currentStep: string          // 当前执行节点（高亮+旋转）
  - tokens: string               // 流式累积文本
  - hitlPlan: Plan | null        // HITL 暂停时非 null
  - result: QueryResult | null   // done 事件到达后非 null
  - connectionPhase: 1 | 2      // 当前是第几段 SSE
  - status: 'connecting' | 'streaming' | 'awaiting_approval' | 'complete' | 'error'

行为：
  - status='connecting' → 建立 EventSource
  - 收到 event: hitl → status='awaiting_approval'，EventSource.close()
  - 收到 event: done → status='complete'，EventSource.close()
  - error → status='error'，展示重试按钮
```

#### `usePDFJump(paperId)`

```
状态：
  - pdfDoc: PDFDocumentProxy | null
  - currentPage: number
  - highlightedBboxes: BBox[]   // 当前高亮区域

方法：
  - jumpToEvidence(evidence: Evidence): 切页 + 高亮 quote 对应 bbox
  - clearHighlight(): 移除所有高亮
  - searchAndJump(text: string): 全文搜索 + 跳转

实现：
  - 加载：pdfjsLib.getDocument(`/api/pdf/${paperId}`)
  - Canvas 层：page.render({ canvasContext, viewport })
  - TextLayer 层：page.getTextContent() → 渲染透明 span，绑定 bbox
  - 高亮：在 TextLayer 叠层上按 bbox 绘制半透明色块
```

#### `useApproval()`

```
方法：
  - approve(threadId: string): POST /api/approve { approved: true }
  - reject(threadId: string, feedback?: string): POST /api/approve { approved: false, feedback }

返回值：Promise<{ status: "resumed" | "cancelled" }>
```

### 4.2 状态管理

使用 zustand v4（React 18 并发模式兼容），拆分为两个 store：

```typescript
// store/appStore.ts
import { create } from 'zustand'

interface AppState {
  paper: Paper | null
  sessions: Session[]
  currentSession: Session | null
  layout: 'dual' | 'chat' | 'paper'
  sidebarOpen: boolean
  setPaper: (paper: Paper) => void
  setLayout: (layout: 'dual' | 'chat' | 'paper') => void
  toggleSidebar: () => void
}

const useAppStore = create<AppState>((set) => ({
  paper: null,
  sessions: [],
  currentSession: null,
  layout: 'dual',
  sidebarOpen: false,
  setPaper: (paper) => set({ paper }),
  setLayout: (layout) => set({ layout }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}))

// store/chatStore.ts
type ChatStatus = 'idle' | 'connecting' | 'streaming' | 'awaiting_approval' | 'complete' | 'error'

interface ChatState {
  messages: Message[]
  streamingTokens: string
  stepNodes: string[]
  currentStep: string | null
  hitlPlan: Plan | null
  threadId: string | null
  status: ChatStatus
  appendToken: (token: string) => void
  addStepNode: (node: string) => void
  setCurrentStep: (step: string) => void
  setHitlPlan: (plan: Plan) => void
  setThreadId: (id: string) => void
  setStatus: (status: ChatStatus) => void
  addMessage: (msg: Message) => void
  reset: () => void
}

const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streamingTokens: '',
  stepNodes: [],
  currentStep: null,
  hitlPlan: null,
  threadId: null,
  status: 'idle',
  appendToken: (token) => set((s) => ({ streamingTokens: s.streamingTokens + token })),
  addStepNode: (node) => set((s) => ({ stepNodes: [...s.stepNodes, node] })),
  setCurrentStep: (step) => set({ currentStep: step }),
  setHitlPlan: (plan) => set({ hitlPlan: plan, status: 'awaiting_approval' }),
  setThreadId: (id) => set({ threadId: id }),
  setStatus: (status) => set({ status }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  reset: () => set({
    messages: [], streamingTokens: '', stepNodes: [],
    currentStep: null, hitlPlan: null, threadId: null, status: 'idle',
  }),
}))
```

---

## 五、关键组件规格

### 5.1 PaperViewer

| 属性 | 说明 |
|------|------|
| **渲染引擎** | PDF.js 3.x，Canvas 模式 + 透明 TextLayer |
| **高亮实现** | 在 TextLayer 上方额外叠一层 SVG/Canvas，按 bbox 绘制半透明色块（`rgba(255, 230, 0, 0.35)`） |
| **高亮动画** | 淡入 200ms + 缩放脉冲 300ms（吸引注意力） |
| **切页** | `pageNumber` 变化 → `page.render()` 重新绘制 Canvas + TextLayer |
| **缩放** | 默认 `page-fit`，支持 `25%/50%/75%/100%/125%/150%/200%` 和 `auto` |
| **章节导航** | 从 `/api/pdf/{paper_id}/text` 返回的 sentences 中提取 section headings，列表展示，点击跳转 |
| **性能** | `renderInteractiveForms: false`，`renderAnnotationLayer: false`。虚拟滚动（TextLayer 仅渲染可视区句子）|

### 5.2 EvidenceBadge & EvidencePopover

| 属性 | R0 | R1 | R2 |
|------|----|----|-----|
| **颜色** | 红 `#991b1b` 底 `#fee2e2` | 橙 `#92400e` 底 `#fef3c7` | 蓝 `#1e40af` 底 `#dbeafe` |
| **图标** | 📄 论文页码 | 🌐 外部来源 | 💡 推理 |
| **Popover 内容** | 原文引用 + 页码 + 章节标题 | 来源标题 + 链接 | 推理链（递归展开 based_on） |
| **交互** | 点击跳转 PDF bbox | 点击打开来源 URL | 悬停展开推理链 |

### 5.3 PlanApprovalBanner

```
┌─────────────────────────────────────────────────┐
│ 🔍 Agent 计划执行以下步骤：                      │
│                                                 │
│  1. 检索 Section 3 方法描述                      │
│  2. 提取实验配置参数                             │
│  3. 对比表 1 结果数据                            │
│  4. 总结方法优势与局限                           │
│                                                 │
│  [✏️ 编辑]    [✅ 批准执行]    [❌ 取消]          │
└─────────────────────────────────────────────────┘
```

- 编辑模式：步骤列表变为可编辑文本区域
- 批准后：Banner 收起动画 → 新 SSE 连接建立 → StepIndicator 继续滚动
- 取消后：返回初始状态，允许重新提问

### 5.4 StepIndicator

```
[reader ✓] → [classify ✓] → [planner ✓] ─── [retrieve ◌] ─── [generate] ─── [observe] ─── [reviewer] ─── [output]

状态：
  ✓ 已完成（绿底）
  ◌ 进行中（蓝底 + 旋转）
  ○ 等待中（灰底）
  ✕ 失败（红底，hover 显示错误信息）
```

### 5.5 QualityBar

```
┌─────────────────────────────────────┐
│ Quality Score: 8/10                 │
│ ████████░░ 相关性 3/3               │
│ ████████░░ 一致性 3/4               │
│ ██████░░░░ 完整性 2/3               │
│                                     │
│ 📄 R0×5  🌐 R1×2  💡 R2×3          │
└─────────────────────────────────────┘
```

---

## 六、技术栈与依赖

### 6.1 前端

| 包 | 版本 | 用途 |
|----|------|------|
| react | ^18.3 | UI 框架 |
| typescript | ^5.5 | 类型系统 |
| vite | ^5.4 | 构建工具 |
| pdfjs-dist | ^4.x | PDF 渲染（Canvas + TextLayer） |
| react-markdown | ^9.x | Markdown 渲染（answer 展示） |
| rehype-raw | ^7.x | Markdown 内联 HTML（EvidenceBadge） |
| zustand | ^4.x | 轻量状态管理（替代 Context 深层传递） |

### 6.2 后端新增

| 包 | 用途 |
|----|------|
| 无新增 | Phase 1 依赖已覆盖，仅新增 API 端点 |

### 6.3 项目结构

```
frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── App.css
│   ├── components/
│   │   ├── PaperViewer/
│   │   │   ├── PaperViewer.tsx          # 主组件
│   │   │   ├── PDFCanvas.tsx            # Canvas 渲染层
│   │   │   ├── PDFTextLayer.tsx         # 透明文本层 + 高亮叠层
│   │   │   ├── PDFToolbar.tsx           # 页码/缩放/搜索
│   │   │   └── SectionNav.tsx           # 章节缩略导航
│   │   ├── ChatPanel/
│   │   │   ├── ChatPanel.tsx            # 主容器
│   │   │   ├── StepIndicator.tsx        # 步骤指示器
│   │   │   ├── PlanApprovalBanner.tsx   # HITL 计划审批
│   │   │   ├── MessageList.tsx          # 消息列表
│   │   │   ├── UserMessage.tsx
│   │   │   ├── AssistantMessage.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   └── FollowUpSuggest.tsx      # 追问按钮组
│   │   ├── Evidence/
│   │   │   ├── EvidenceBadge.tsx        # R0/R1/R2 徽标
│   │   │   ├── EvidencePopover.tsx      # 悬停 tooltip
│   │   │   └── EvidenceChain.tsx        # R2 推理链递归展示
│   │   ├── Quality/
│   │   │   └── QualityBar.tsx           # 评分展示
│   │   ├── Layout/
│   │   │   ├── TopBar.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── LibraryPanel.tsx
│   │   │   ├── SessionHistory.tsx
│   │   │   └── LayoutToggle.tsx
│   │   └── common/
│   │       ├── TracePanel.tsx           # 折叠思考链路
│   │       ├── ResizableSplit.tsx       # 可拖拽分隔条
│   │       └── LoadingSpinner.tsx
│   ├── hooks/
│   │   ├── useSSE.ts
│   │   ├── usePDFJump.ts
│   │   └── useApproval.ts
│   ├── store/
│   │   ├── appStore.ts                  # zustand 全局状态
│   │   └── chatStore.ts                 # zustand 对话状态
│   └── types/
│       └── index.ts                     # Paper, Evidence, Plan, Session 等类型定义
```

---

## 七、Phase 2 开发阶段

### 阶段划分（调整后）

| 阶段 | 内容 | 文件数 | 预估 |
|------|------|--------|------|
| **P2.1 项目搭建** | Vite + React + TS 脚手架，zustand store，类型定义，API 封装 | 8 | 2-3h |
| **P2.2 PaperViewer** | PDF.js 集成，Canvas + TextLayer 渲染，缩放/翻页，章节导航 | 5 | 4-5h |
| **P2.3 ChatPanel** | SSE 流式接收，StepIndicator，MessageList，AnswerMarkdown，ChatInput | 7 | 3-4h |
| **P2.4 证据系统** | EvidenceBadge，EvidencePopover，R2 推理链递归，QualityBar，PDF 高亮跳转 | 4 | 4-5h |
| **P2.5 HITL 审批** | PlanApprovalBanner，useApproval，两段 SSE 重连，plan_feedback 回传 | 3 | 2-3h |
| **P2.6 布局 & 周边** | LayoutToggle 三种模式，Sidebar（LibraryPanel + SessionHistory），响应式，TracePanel，FollowUpSuggest | 6 | 3-4h |
| **P2.7 后端适配** | `graph.astream_events()` 替换同步 `graph.invoke()`，SSE token 流式推送，init + hitl 事件，langgraph interrupt 条件处理，`/api/approve` + `/api/pdf/{id}` + `/api/pdf/{id}/text` 端点 | 2 | 3-4h |
| **P2.8 集成 & 测试** | 全链路联调，SSE 两段连接测试，PDF 高亮跳转测试，HITL 流程测试 | — | 2-3h |

总预估：**21-31 小时**（约 1.5-2 周，含调试和学习成本）

---

## 八、依赖关系

```
P2.1 项目搭建 ──→ P2.2 PaperViewer ──→ P2.4 证据系统 + PDF 高亮
              │
              ├──→ P2.3 ChatPanel ──→ P2.5 HITL 审批
              │                           │
              └──→ P2.7 后端适配 ──────────┘
                                         │
                                  P2.6 布局 & 周边
                                         │
                                  P2.8 集成 & 测试
```

- P2.2 和 P2.3 可并行
- P2.4 依赖 P2.2 + P2.3
- P2.5 依赖 P2.3 + P2.7
- P2.6 可与 P2.5 并行

---

## 九、风险与应对

| 风险 | 可能性 | 影响 | 应对 |
|------|--------|------|------|
| PDF.js TextLayer bbox 定位不精确 | 中 | PDF 高亮错位 | 使用 `getTextContent()` 返回的 `transform` 矩阵计算精确坐标，留 2px 容差 |
| SSE 两段重连 state 丢失 | 低 | HITL 恢复后无法继续 | LangGraph checkpointer 从 SQLite 恢复完整 AgentState，thread_id 保证精确匹配 |
| React + PDF.js 首屏性能 | 中 | 加载 > 3s | PDF.js worker 异步加载，React.lazy 分包，PDF 组件独立 chunk |
| SSE token 乱序或丢失 | 低 | 回答文字缺失 | done 事件包含完整 answer，前端做 token 拼接校验 |
| zustand 与 React 18 并发模式兼容性 | 低 | 状态更新丢失 | zustand v4 已适配 React 18，避免在 render 内直接修改 store |

---

## 十、未纳入 Phase 2 的功能（明确排除）

| 功能 | 相位 | 原因 |
|------|------|------|
| FlashRank 重排序 | Phase 3 | 后端优化，不影响前端 |
| 用户偏好持久化 | Phase 3 | 需用户系统 |
| 对话导出 | Phase 3 | Markdown/JSON 导出 |
| 多论文对比 | Phase 4 | 需跨 paper 检索 |
| 外部检索 | Phase 4 | arXiv/Semantic Scholar API |
| 移动端原生适配 | 不计划 | 响应式单列布局已覆盖基本移动场景 |
