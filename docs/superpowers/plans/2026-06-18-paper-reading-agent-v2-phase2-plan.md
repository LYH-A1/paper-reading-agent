# Paper Reading Agent V2 Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React+TypeScript frontend with dual-panel PDF viewer, evidence highlighting, streaming chat, and HITL plan approval.

**Architecture:** Vite+React SPA consuming FastAPI SSE streams. zustand stores for state management. PDF.js Canvas+TextLayer for PDF rendering with bbox-based highlight overlays. Two-segment SSE protocol with thread_id for HITL reconnect.

**Tech Stack:** React 18.3, TypeScript 5.5, Vite 5.4, pdfjs-dist 4.x, react-markdown 9.x, rehype-raw 7.x, zustand 4.x

## Global Constraints

- React version: ^18.3
- TypeScript version: ^5.5
- Vite version: ^5.4
- pdfjs-dist version: ^4.x
- zustand version: ^4.x (React 18 concurrent mode compatible)
- No new Python dependencies — backend changes use existing Phase 1 packages
- PDF.js worker loaded from CDN (`pdfjs-dist/build/pdf.worker.min.mjs`)
- SSE uses native `EventSource` API (prefer over fetch+ReadableStream for simplicity)
- All components use functional style + hooks, no class components
- CSS: plain CSS modules per component directory (`ComponentName.module.css`)

---

### Task 1: Project Scaffolding & Type System

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/store/appStore.ts`
- Create: `frontend/src/store/chatStore.ts`
- Create: `frontend/src/main.tsx`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `Paper` type — `{ paper_id, title, file_path, parsed_at }`
  - `EvidenceLevel` type — `'R0' | 'R1' | 'R2'`
  - `Evidence` type — `{ evidence_id, claim, level: EvidenceLevel, page?, quote?, char_start?, char_end?, sentence_index?, section_heading?, source_title?, source_url?, reasoning?, based_on_evidence_ids?, confidence }`
  - `QualityScore` type — `{ relevance, consistency, completeness, total }`
  - `PlanStep` type — `{ step, action, tool, target }`
  - `Plan` type — `{ steps: PlanStep[] }`
  - `SSEEvent` type — union of `InitEvent | NodeEvent | HitlEvent | TokenEvent | DoneEvent`
  - `Message` type — `{ id, role: 'user' | 'assistant', content, evidenceList?, qualityScore?, trace? }`
  - `Session` type — `{ id, title, paperId, createdAt }`
  - `useAppStore` — zustand store with `paper, sessions, currentSession, layout, sidebarOpen` + actions
  - `useChatStore` — zustand store with `messages, streamingTokens, stepNodes, currentStep, hitlPlan, threadId, status` + actions

- [ ] **Step 1: Write scaffold test**

```typescript
// tests/frontend/scaffold.test.ts — create this as a quick smoke test
import { describe, it, expect } from 'vitest'

describe('project scaffold', () => {
  it('type imports resolve', async () => {
    const mod = await import('../src/types/index')
    expect(mod).toBeDefined()
  })
})
```

- [ ] **Step 2: Create `frontend/package.json`**

```json
{
  "name": "paper-reading-agent-frontend",
  "private": true,
  "version": "0.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "pdfjs-dist": "^4.9.155",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-markdown": "^9.0.1",
    "rehype-raw": "^7.0.0",
    "zustand": "^4.5.5"
  },
  "devDependencies": {
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.5.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "jsdom": "^25.0.0",
    "typescript": "^5.5.4",
    "vite": "^5.4.11",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'  // Note: no @vitejs/plugin-react dependency needed for basic setup
import path from 'path'

export default defineConfig({
  plugins: [],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Paper Reading Agent</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

- [ ] **Step 6: Create `frontend/src/types/index.ts`**

```typescript
// ---- Evidence ----
export type EvidenceLevel = 'R0' | 'R1' | 'R2'

export interface Evidence {
  evidence_id: string
  claim: string
  level: EvidenceLevel
  sentence_index: number | null
  char_start: number | null
  char_end: number | null
  // R0
  page: number | null
  quote: string | null
  section_heading: string | null
  // R1
  source_title: string | null
  source_url: string | null
  source_venue: string | null
  source_year: number | null
  // R2
  reasoning: string | null
  based_on_evidence_ids: string[]
  // General
  confidence: number
}

// ---- Quality ----
export interface QualityScore {
  relevance: number
  consistency: number
  completeness: number
  total: number
}

// ---- Plan ----
export interface PlanStep {
  step: number
  action: string
  tool: string
  target: string
}

export interface Plan {
  steps: PlanStep[]
}

// ---- SSE Events ----
export interface InitEvent {
  event: 'init'
  thread_id: string
}

export interface NodeEvent {
  event: 'node'
  node: string
}

export interface HitlEvent {
  event: 'hitl'
  type: 'plan_approval'
  plan: Plan
}

export interface TokenEvent {
  event: 'token'
  text: string
  node: 'generate'
}

export interface DoneEvent {
  event: 'done'
  answer: string
  quality_score: QualityScore
  evidence_list: Evidence[]
  trace: string[]
  followup_questions: string[]
}

export type SSEEvent = InitEvent | NodeEvent | HitlEvent | TokenEvent | DoneEvent

// ---- Messages ----
export interface UserMessage {
  id: string
  role: 'user'
  content: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  content: string
  evidenceList: Evidence[]
  qualityScore: QualityScore | null
  trace: string[]
}

export type Message = UserMessage | AssistantMessage

// ---- Paper ----
export interface Paper {
  paper_id: string
  title: string
  file_path: string
  parsed_at: string | null
}

// ---- Session ----
export interface Session {
  id: string
  title: string
  paperId: string
  createdAt: string
}

// ---- API ----
export interface UploadResponse {
  paper_id: string
  title: string
  file_path: string
}

export interface PaperListResponse {
  paper_id: string
  title: string
  parsed_at: string | null
}

export interface ApproveRequest {
  thread_id: string
  approved: boolean
  feedback?: string
}

export interface ApproveResponse {
  status: 'resumed' | 'cancelled'
}

export interface PDFTextPage {
  page: number
  width: number
  height: number
  sentences: PDFTextSentence[]
}

export interface PDFTextSentence {
  text: string
  char_start: number
  char_end: number
  bbox: [number, number, number, number]  // [x0, y0, x1, y1]
}
```

- [ ] **Step 7: Create `frontend/src/store/appStore.ts`**

```typescript
import { create } from 'zustand'
import type { Paper, Session } from '@/types'

export type LayoutMode = 'dual' | 'chat' | 'paper'

interface AppState {
  paper: Paper | null
  sessions: Session[]
  currentSession: Session | null
  layout: LayoutMode
  sidebarOpen: boolean

  setPaper: (paper: Paper) => void
  clearPaper: () => void
  setLayout: (layout: LayoutMode) => void
  toggleSidebar: () => void
  addSession: (session: Session) => void
  setCurrentSession: (session: Session) => void
}

export const useAppStore = create<AppState>((set) => ({
  paper: null,
  sessions: [],
  currentSession: null,
  layout: 'dual',
  sidebarOpen: false,

  setPaper: (paper) => set({ paper }),
  clearPaper: () => set({ paper: null }),
  setLayout: (layout) => set({ layout }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
  setCurrentSession: (session) => set({ currentSession: session }),
}))
```

- [ ] **Step 8: Create `frontend/src/store/chatStore.ts`**

```typescript
import { create } from 'zustand'
import type { Message, Plan, Evidence, QualityScore } from '@/types'

export type ChatStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'awaiting_approval'
  | 'complete'
  | 'error'

interface ChatState {
  messages: Message[]
  streamingTokens: string
  stepNodes: string[]
  currentStep: string | null
  hitlPlan: Plan | null
  threadId: string | null
  status: ChatStatus
  errorMessage: string | null

  appendToken: (token: string) => void
  addStepNode: (node: string) => void
  setCurrentStep: (step: string) => void
  setHitlPlan: (plan: Plan) => void
  setThreadId: (id: string) => void
  setStatus: (status: ChatStatus) => void
  setError: (msg: string) => void
  addMessage: (msg: Message) => void
  finalizeAssistantMessage: (content: string, evidenceList: Evidence[], qualityScore: QualityScore | null, trace: string[]) => void
  reset: () => void
}

let nextId = 1
const genId = () => `msg-${nextId++}`

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streamingTokens: '',
  stepNodes: [],
  currentStep: null,
  hitlPlan: null,
  threadId: null,
  status: 'idle',
  errorMessage: null,

  appendToken: (token) => set((s) => ({ streamingTokens: s.streamingTokens + token })),

  addStepNode: (node) => set((s) => ({
    stepNodes: [...s.stepNodes, node],
    currentStep: node,
  })),

  setCurrentStep: (step) => set({ currentStep: step }),

  setHitlPlan: (plan) => set({ hitlPlan: plan, status: 'awaiting_approval' }),

  setThreadId: (id) => set({ threadId: id }),

  setStatus: (status) => set({ status }),

  setError: (msg) => set({ errorMessage: msg, status: 'error' }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  finalizeAssistantMessage: (content, evidenceList, qualityScore, trace) => set((s) => {
    const msg: Message = {
      id: genId(),
      role: 'assistant',
      content,
      evidenceList,
      qualityScore,
      trace,
    }
    return {
      messages: [...s.messages, msg],
      streamingTokens: '',
      status: 'complete',
    }
  }),

  reset: () => set({
    messages: [],
    streamingTokens: '',
    stepNodes: [],
    currentStep: null,
    hitlPlan: null,
    threadId: null,
    status: 'idle',
    errorMessage: null,
  }),
}))
```

- [ ] **Step 9: Create `frontend/src/main.tsx`**

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

- [ ] **Step 10: Create minimal `frontend/src/App.tsx` and `frontend/src/App.css`**

```typescript
// App.tsx
export default function App() {
  return (
    <div className="app">
      <h1>Paper Reading Agent</h1>
    </div>
  )
}
```

```css
/* App.css */
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
.app { max-width: 1400px; margin: 0 auto; padding: 16px; }
```

- [ ] **Step 11: Run test to verify scaffold**

Run: `cd frontend && npm install && npm test`
Expected: scaffold test PASS, app compiles

- [ ] **Step 12: Verify dev server starts**

Run: `cd frontend && npm run dev`
Expected: Vite starts on port 3000, proxy to localhost:8000

- [ ] **Step 13: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold Vite+React+TS project with zustand stores and type definitions"
```

---

### Task 2: API Client & Paper Upload

**Files:**
- Create: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Test: `tests/frontend/api.test.ts`

**Interfaces:**
- Consumes: `@/types` from Task 1 (Paper, UploadResponse, PaperListResponse, ApproveRequest, ApproveResponse, PDFTextPage)
- Produces:
  - `uploadPaper(file: File): Promise<UploadResponse>`
  - `listPapers(): Promise<PaperListResponse[]>`
  - `approvePlan(req: ApproveRequest): Promise<ApproveResponse>`
  - `getPDFUrl(paperId: string): string` — returns `/api/pdf/${paperId}`
  - `getPDFTextUrl(paperId: string): string` — returns `/api/pdf/${paperId}/text`
  - `getSSEUrl(params: { paper_id?: string; query?: string; thread_id?: string }): string` — builds GET SSE URL

- [ ] **Step 1: Write failing test**

```typescript
// tests/frontend/api.test.ts
import { describe, it, expect, vi } from 'vitest'

describe('API client', () => {
  it('uploadPaper sends FormData and returns response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ paper_id: 'p1', title: 'test.pdf', file_path: '/data/papers/test.pdf' }),
    })

    const { uploadPaper } = await import('../src/api/client')
    const file = new File(['fake'], 'test.pdf', { type: 'application/pdf' })
    const result = await uploadPaper(file)

    expect(result.paper_id).toBe('p1')
    expect(fetch).toHaveBeenCalledWith('/api/upload', expect.objectContaining({ method: 'POST' }))
  })

  it('getSSEUrl builds correct query string', async () => {
    const { getSSEUrl } = await import('../src/api/client')
    const url = getSSEUrl({ paper_id: 'p1', query: 'What is the method?' })
    expect(url).toContain('paper_id=p1')
    expect(url).toContain('query=What+is+the+method')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/api.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Create `frontend/src/api/client.ts`**

```typescript
import type { UploadResponse, PaperListResponse, ApproveRequest, ApproveResponse } from '@/types'

const BASE = '/api'

export async function uploadPaper(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Upload failed')
  }
  return res.json()
}

export async function listPapers(): Promise<PaperListResponse[]> {
  const res = await fetch(`${BASE}/papers`)
  if (!res.ok) throw new Error('Failed to fetch papers')
  return res.json()
}

export async function approvePlan(req: ApproveRequest): Promise<ApproveResponse> {
  const res = await fetch(`${BASE}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error('Approval failed')
  return res.json()
}

export function getPDFUrl(paperId: string): string {
  return `${BASE}/pdf/${encodeURIComponent(paperId)}`
}

export function getPDFTextUrl(paperId: string): string {
  return `${BASE}/pdf/${encodeURIComponent(paperId)}/text`
}

export function getSSEUrl(params: { paper_id?: string; query?: string; thread_id?: string }): string {
  const sp = new URLSearchParams()
  if (params.paper_id) sp.set('paper_id', params.paper_id)
  if (params.query) sp.set('query', params.query)
  if (params.thread_id) sp.set('thread_id', params.thread_id)
  return `${BASE}/query?${sp.toString()}`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/frontend/api.test.ts`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ tests/frontend/
git commit -m "feat(frontend): add API client for upload, papers, approve, PDF, and SSE URL builder"
```

---

### Task 3: useSSE Hook

**Files:**
- Create: `frontend/src/hooks/useSSE.ts`
- Test: `tests/frontend/useSSE.test.ts`

**Interfaces:**
- Consumes: `@/types` (SSEEvent, InitEvent, NodeEvent, HitlEvent, TokenEvent, DoneEvent), `@/store/chatStore` (useChatStore), `@/api/client` (getSSEUrl)
- Produces:
  - `useSSE(): { start(params: { paper_id: string; query: string }): void; startResume(threadId: string): void; abort(): void }`
  - Internal event parsing from SSE `data:` lines → dispatches to chatStore

- [ ] **Step 1: Write failing test**

```typescript
// tests/frontend/useSSE.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChatStore } from '../../src/store/chatStore'

// Mock EventSource
class MockEventSource {
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  url: string
  readyState: number = 0
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2

  constructor(url: string) {
    this.url = url
    setTimeout(() => {
      this.readyState = MockEventSource.OPEN
      // Fire init event
      this.onmessage?.({ data: 'event: init\ndata: {"thread_id":"test-thread"}' })
    }, 0)
  }

  close() { this.readyState = MockEventSource.CLOSED }
}

vi.stubGlobal('EventSource', MockEventSource)

// Import hook after mocks
import { useSSE } from '../../src/hooks/useSSE'

describe('useSSE', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
  })

  it('sets thread_id from init event on start', async () => {
    const { result } = renderHook(() => useSSE())
    act(() => { result.current.start({ paper_id: 'p1', query: 'test query' }) })
    // Wait for async EventSource
    await vi.waitFor(() => {
      expect(useChatStore.getState().threadId).toBe('test-thread')
    })
  })

  it('adds step nodes from node events', async () => {
    // Override mock to emit node events
    class NodeEventSource {
      onmessage: ((e: { data: string }) => void) | null = null
      onerror: (() => void) | null = null
      url: string
      readyState = 0
      constructor(url: string) {
        this.url = url
        setTimeout(() => {
          this.readyState = 1
          this.onmessage?.({ data: 'event: node\ndata: {"node":"reader"}' })
          this.onmessage?.({ data: 'event: node\ndata: {"node":"classify"}' })
        }, 0)
      }
      close() { this.readyState = 2 }
    }
    vi.stubGlobal('EventSource', NodeEventSource)

    const { result } = renderHook(() => useSSE())
    act(() => { result.current.start({ paper_id: 'p1', query: 'test' }) })
    await vi.waitFor(() => {
      expect(useChatStore.getState().stepNodes).toContain('reader')
      expect(useChatStore.getState().stepNodes).toContain('classify')
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/useSSE.test.ts`
Expected: FAIL — `useSSE` module not found

- [ ] **Step 3: Create `frontend/src/hooks/useSSE.ts`**

```typescript
import { useCallback, useRef } from 'react'
import { useChatStore } from '@/store/chatStore'
import { getSSEUrl } from '@/api/client'
import type { NodeEvent, HitlEvent, TokenEvent, DoneEvent } from '@/types'

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const store = useChatStore

  const connect = useCallback((url: string) => {
    // Close any existing connection
    eventSourceRef.current?.close()

    const es = new EventSource(url)
    eventSourceRef.current = es

    store.getState().setStatus('streaming')

    es.addEventListener('init', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      store.getState().setThreadId(data.thread_id)
    })

    es.addEventListener('node', (e: MessageEvent) => {
      const data: NodeEvent = JSON.parse(e.data)
      store.getState().addStepNode(data.node)
    })

    es.addEventListener('token', (e: MessageEvent) => {
      const data: TokenEvent = JSON.parse(e.data)
      store.getState().appendToken(data.text)
    })

    es.addEventListener('hitl', (e: MessageEvent) => {
      const data: HitlEvent = JSON.parse(e.data)
      store.getState().setHitlPlan(data.plan)
      es.close()
    })

    es.addEventListener('done', (e: MessageEvent) => {
      const data: DoneEvent = JSON.parse(e.data)
      store.getState().finalizeAssistantMessage(
        data.answer,
        data.evidence_list,
        data.quality_score,
        data.trace,
      )
      es.close()
    })

    es.onerror = () => {
      // Only set error if not intentionally closed (readyState 2 = CLOSED)
      if (es.readyState !== EventSource.CLOSED) {
        store.getState().setError('Connection lost. Please try again.')
        es.close()
      }
    }
  }, [])

  const start = useCallback((params: { paper_id: string; query: string }) => {
    store.getState().reset()
    store.getState().setStatus('connecting')
    const url = getSSEUrl({ paper_id: params.paper_id, query: params.query })
    connect(url)
  }, [connect])

  const startResume = useCallback((threadId: string) => {
    store.getState().setStatus('connecting')
    store.getState().setHitlPlan(null)
    const url = getSSEUrl({ thread_id: threadId })
    connect(url)
  }, [connect])

  const abort = useCallback(() => {
    eventSourceRef.current?.close()
    store.getState().setStatus('idle')
  }, [])

  return { start, startResume, abort }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/frontend/useSSE.test.ts`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSSE.ts tests/frontend/useSSE.test.ts
git commit -m "feat(frontend): add useSSE hook with EventSource, init/node/token/hitl/done event handling"
```

---

### Task 4: PaperViewer — PDF.js Canvas + TextLayer

**Files:**
- Create: `frontend/src/components/PaperViewer/PaperViewer.tsx`
- Create: `frontend/src/components/PaperViewer/PDFCanvas.tsx`
- Create: `frontend/src/components/PaperViewer/PDFTextLayer.tsx`
- Create: `frontend/src/components/PaperViewer/PDFToolbar.tsx`
- Create: `frontend/src/components/PaperViewer/PaperViewer.module.css`
- Test: `tests/frontend/PaperViewer.test.tsx`

**Interfaces:**
- Consumes: `@/types` (Paper, PDFTextPage), `@/store/appStore` (useAppStore.paper), `@/api/client` (getPDFUrl, getPDFTextUrl)
- Produces:
  - `<PaperViewer />` — full-page PDF renderer with toolbar, canvas, text layer
  - `PDFCanvas` props: `{ pdfDoc: PDFDocumentProxy, pageNumber: number, scale: number }`
  - `PDFTextLayer` props: `{ pdfDoc: PDFDocumentProxy, pageNumber: number, scale: number, highlights: HighlightRect[], onHighlightClick: (box: HighlightRect) => void }`
  - `HighlightRect` type: `{ bbox: [number,number,number,number], evidenceId: string, color: string }`
  - `PDFToolbar` props: `{ pageNumber, totalPages, scale, onPageChange, onScaleChange }`

- [ ] **Step 1: Write failing test**

```typescript
// tests/frontend/PaperViewer.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'

// pdfjs-dist must be mocked because it requires a DOM/worker
vi.mock('pdfjs-dist', () => ({
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 3,
      getPage: vi.fn(() => Promise.resolve({
        getViewport: vi.fn(() => ({ width: 612, height: 792 })),
        render: vi.fn(() => ({ promise: Promise.resolve() })),
        getTextContent: vi.fn(() => Promise.resolve({ items: [] })),
      })),
    }),
  })),
  GlobalWorkerOptions: { workerSrc: '' },
}))

import PaperViewer from '../../src/components/PaperViewer/PaperViewer'

describe('PaperViewer', () => {
  it('renders PDFToolbar with page info', async () => {
    const screen = render(<PaperViewer paperId="test-paper" />)
    // Should show loading initially, then toolbar after load
    expect(screen.container.querySelector('.paper-viewer')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/PaperViewer.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create `frontend/src/components/PaperViewer/PDFToolbar.tsx`**

```typescript
import styles from './PaperViewer.module.css'

interface PDFToolbarProps {
  pageNumber: number
  totalPages: number
  scale: number
  onPageChange: (page: number) => void
  onScaleChange: (scale: number) => void
}

const SCALES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const

export default function PDFToolbar({ pageNumber, totalPages, scale, onPageChange, onScaleChange }: PDFToolbarProps) {
  return (
    <div className={styles.toolbar}>
      <button onClick={() => onPageChange(pageNumber - 1)} disabled={pageNumber <= 1}>◀</button>
      <span>{pageNumber} / {totalPages}</span>
      <button onClick={() => onPageChange(pageNumber + 1)} disabled={pageNumber >= totalPages}>▶</button>
      <select value={scale} onChange={(e) => onScaleChange(Number(e.target.value))}>
        <option value="auto">Fit</option>
        {SCALES.map(s => <option key={s} value={s}>{Math.round(s * 100)}%</option>)}
      </select>
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/PaperViewer/PDFCanvas.tsx`**

```typescript
import { useRef, useEffect } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'

interface PDFCanvasProps {
  pdfDoc: PDFDocumentProxy
  pageNumber: number
  scale: number
}

export default function PDFCanvas({ pdfDoc, pageNumber, scale }: PDFCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let cancelled = false
    const renderPage = async () => {
      const page = await pdfDoc.getPage(pageNumber)
      const viewport = page.getViewport({ scale: scale === 0 ? 1 : scale })
      const canvas = canvasRef.current
      if (!canvas || cancelled) return

      canvas.width = viewport.width
      canvas.height = viewport.height
      const ctx = canvas.getContext('2d')!
      await page.render({ canvasContext: ctx, viewport }).promise
    }
    renderPage()
    return () => { cancelled = true }
  }, [pdfDoc, pageNumber, scale])

  return <canvas ref={canvasRef} />
}
```

- [ ] **Step 5: Create `frontend/src/components/PaperViewer/PDFTextLayer.tsx`**

```typescript
import { useRef, useEffect, useState } from 'react'
import type { PDFDocumentProxy, TextItem, TextMarkedContent } from 'pdfjs-dist'
import styles from './PaperViewer.module.css'

export interface HighlightRect {
  bbox: [number, number, number, number]
  evidenceId: string
  color: string
}

interface PDFTextLayerProps {
  pdfDoc: PDFDocumentProxy
  pageNumber: number
  scale: number
  highlights: HighlightRect[]
  onTextContentReady?: (items: TextItem[]) => void
}

interface SpanData {
  text: string
  bbox: [number, number, number, number]  // viewport coords
}

export default function PDFTextLayer({ pdfDoc, pageNumber, scale, highlights, onTextContentReady }: PDFTextLayerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [spans, setSpans] = useState<SpanData[]>([])
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    let cancelled = false
    const loadText = async () => {
      const page = await pdfDoc.getPage(pageNumber)
      const viewport = page.getViewport({ scale: scale === 0 ? 1 : scale })
      const tc = await page.getTextContent()
      if (cancelled) return

      const items: TextItem[] = (tc.items as (TextItem | TextMarkedContent)[])
        .filter((item): item is TextItem => 'str' in item && item.str.trim().length > 0)

      const spanList: SpanData[] = items.map((item) => {
        const tx = item.transform
        const x0 = tx[4] * scale
        const y0 = viewport.height - tx[5] * scale
        const w = item.width * scale
        const h = item.height * scale
        return {
          text: item.str,
          bbox: [x0, y0 - h, x0 + w, y0] as [number, number, number, number],
        }
      })

      setSpans(spanList)
      setContainerSize({ width: viewport.width, height: viewport.height })
      onTextContentReady?.(items)
    }
    loadText()
    return () => { cancelled = true }
  }, [pdfDoc, pageNumber, scale])

  // Find which spans match highlight bboxes (within 2px tolerance)
  const highlightedSpanIndices = new Set<number>()
  for (const hl of highlights) {
    for (let i = 0; i < spans.length; i++) {
      const sb = spans[i].bbox
      if (
        Math.abs(sb[0] - hl.bbox[0]) < 2 &&
        Math.abs(sb[1] - hl.bbox[1]) < 2 &&
        Math.abs(sb[2] - hl.bbox[2]) < 2 &&
        Math.abs(sb[3] - hl.bbox[3]) < 2
      ) {
        highlightedSpanIndices.add(i)
      }
    }
  }

  return (
    <div
      ref={containerRef}
      className={styles.textLayer}
      style={{ width: containerSize.width, height: containerSize.height }}
    >
      {spans.map((span, i) => (
        <span
          key={i}
          className={`${styles.textSpan} ${highlightedSpanIndices.has(i) ? styles.highlighted : ''}`}
          style={{
            left: span.bbox[0],
            top: span.bbox[1],
            width: span.bbox[2] - span.bbox[0],
            height: span.bbox[3] - span.bbox[1],
          }}
        >
          {span.text}
        </span>
      ))}
    </div>
  )
}
```

- [ ] **Step 6: Create `frontend/src/components/PaperViewer/PaperViewer.tsx`**

```typescript
import { useState, useEffect } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import PDFCanvas from './PDFCanvas'
import PDFTextLayer from './PDFTextLayer'
import PDFToolbar from './PDFToolbar'
import { getPDFUrl } from '@/api/client'
import type { HighlightRect } from './PDFTextLayer'
import styles from './PaperViewer.module.css'

// Set worker from CDN
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.9.155/pdf.worker.min.mjs'

export { type HighlightRect }

interface PaperViewerProps {
  paperId: string
  highlights?: HighlightRect[]
  onPageChange?: (page: number) => void
}

export default function PaperViewer({ paperId, highlights = [], onPageChange }: PaperViewerProps) {
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [scale, setScale] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    pdfjsLib.getDocument(getPDFUrl(paperId)).promise
      .then((doc) => {
        setPdfDoc(doc)
        setTotalPages(doc.numPages)
        setPageNumber(1)
        setLoading(false)
      })
      .catch((err) => {
        setError(`Failed to load PDF: ${err.message}`)
        setLoading(false)
      })
  }, [paperId])

  const handlePageChange = (newPage: number) => {
    const clamped = Math.max(1, Math.min(newPage, totalPages))
    setPageNumber(clamped)
    onPageChange?.(clamped)
  }

  if (loading) return <div className={styles.container}>Loading PDF...</div>
  if (error) return <div className={styles.container}>{error}</div>
  if (!pdfDoc) return null

  return (
    <div className={styles.container}>
      <PDFToolbar
        pageNumber={pageNumber}
        totalPages={totalPages}
        scale={scale}
        onPageChange={handlePageChange}
        onScaleChange={setScale}
      />
      <div className={styles.pageContainer} style={{ position: 'relative' }}>
        <PDFCanvas pdfDoc={pdfDoc} pageNumber={pageNumber} scale={scale} />
        <PDFTextLayer
          pdfDoc={pdfDoc}
          pageNumber={pageNumber}
          scale={scale}
          highlights={highlights}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Create `frontend/src/components/PaperViewer/PaperViewer.module.css`**

```css
.container { display: flex; flex-direction: column; align-items: center; gap: 8px; background: #e5e5e5; min-height: 400px; padding: 8px; }

.toolbar { display: flex; align-items: center; gap: 8px; background: #fff; padding: 6px 12px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.toolbar button { padding: 4px 10px; border: 1px solid #ccc; border-radius: 3px; background: #fff; cursor: pointer; }
.toolbar button:disabled { opacity: 0.4; cursor: default; }
.toolbar select { padding: 4px 8px; border: 1px solid #ccc; border-radius: 3px; }

.pageContainer { position: relative; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
.pageContainer canvas { display: block; }

.textLayer { position: absolute; top: 0; left: 0; overflow: hidden; }
.textSpan { position: absolute; color: transparent; cursor: text; white-space: pre; font-size: 1px; }
.textSpan::selection { background: rgba(0,0,255,0.2); }
.textSpan.highlighted { background: rgba(255,230,0,0.35) !important; }
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/frontend/PaperViewer.test.tsx`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/PaperViewer/ tests/frontend/PaperViewer.test.tsx
git commit -m "feat(frontend): add PaperViewer with PDF.js Canvas+TextLayer, toolbar, and highlight support"
```

---

### Task 5: ChatPanel — StepIndicator, MessageList, ChatInput

**Files:**
- Create: `frontend/src/components/ChatPanel/ChatPanel.tsx`
- Create: `frontend/src/components/ChatPanel/StepIndicator.tsx`
- Create: `frontend/src/components/ChatPanel/MessageList.tsx`
- Create: `frontend/src/components/ChatPanel/UserMessage.tsx`
- Create: `frontend/src/components/ChatPanel/AssistantMessage.tsx`
- Create: `frontend/src/components/ChatPanel/ChatInput.tsx`
- Create: `frontend/src/components/ChatPanel/ChatPanel.module.css`
- Test: `tests/frontend/ChatPanel.test.tsx`

**Interfaces:**
- Consumes: `@/store/chatStore` (useChatStore), `@/types` (Message, UserMessage as type, AssistantMessage as type), `useSSE` hook
- Produces:
  - `<ChatPanel />` — wraps StepIndicator + MessageList + PlanApprovalBanner (Task 7) + ChatInput
  - `<StepIndicator />` — reads `stepNodes` and `currentStep` from chatStore
  - `<MessageList />` — renders UserMessage and AssistantMessage from `messages`
  - `<ChatInput onSend={(query: string) => void} disabled: boolean />`

- [ ] **Step 1: Write failing test**

```typescript
// tests/frontend/ChatPanel.test.tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useChatStore } from '../../src/store/chatStore'

// Import the ChatInput to test
import ChatInput from '../../src/components/ChatPanel/ChatInput'

describe('ChatInput', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
  })

  it('calls onSend with input value on submit', () => {
    let sent = ''
    const screen = render(<ChatInput onSend={(q) => { sent = q }} disabled={false} />)
    const input = screen.container.querySelector('input')!
    fireEvent.change(input, { target: { value: 'What is the method?' } })
    fireEvent.click(screen.getByText('Ask'))
    expect(sent).toBe('What is the method?')
  })

  it('disables button when disabled prop is true', () => {
    const screen = render(<ChatInput onSend={() => {}} disabled={true} />)
    const btn = screen.getByText('Ask') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/ChatPanel.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create `frontend/src/components/ChatPanel/StepIndicator.tsx`**

```typescript
import { useChatStore } from '@/store/chatStore'
import styles from './ChatPanel.module.css'

const NODE_ORDER = ['reader', 'classify', 'planner', 'retrieve', 'generate', 'observe', 'reviewer', 'output', 'rewrite']

export default function StepIndicator() {
  const stepNodes = useChatStore((s) => s.stepNodes)
  const currentStep = useChatStore((s) => s.currentStep)

  return (
    <div className={styles.stepIndicator}>
      {NODE_ORDER.map((nodeName) => {
        const done = stepNodes.includes(nodeName)
        const active = currentStep === nodeName
        return (
          <span
            key={nodeName}
            className={`${styles.stepNode} ${done ? styles.done : ''} ${active ? styles.active : ''}`}
          >
            {nodeName}
          </span>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/ChatPanel/UserMessage.tsx`**

```typescript
import styles from './ChatPanel.module.css'

export default function UserMessage({ content }: { content: string }) {
  return (
    <div className={styles.userMessage}>
      <div className={styles.bubble}>{content}</div>
    </div>
  )
}
```

- [ ] **Step 5: Create `frontend/src/components/ChatPanel/AssistantMessage.tsx`**

```typescript
import styles from './ChatPanel.module.css'
import type { Evidence, QualityScore } from '@/types'

interface AssistantMessageProps {
  content: string
  evidenceList: Evidence[]
  qualityScore: QualityScore | null
  trace: string[]
}

export default function AssistantMessage({ content, evidenceList, qualityScore, trace }: AssistantMessageProps) {
  // EvidenceBadge placeholder — full implementation in Task 6
  const r0Count = evidenceList.filter((e) => e.level === 'R0').length
  const r1Count = evidenceList.filter((e) => e.level === 'R1').length
  const r2Count = evidenceList.filter((e) => e.level === 'R2').length

  return (
    <div className={styles.assistantMessage}>
      <div className={styles.bubble}>
        <div className={styles.answerContent}>{content}</div>
        {evidenceList.length > 0 && (
          <div className={styles.evidenceSummary}>
            {r0Count > 0 && <span className={styles.badgeR0}>R0×{r0Count}</span>}
            {r1Count > 0 && <span className={styles.badgeR1}>R1×{r1Count}</span>}
            {r2Count > 0 && <span className={styles.badgeR2}>R2×{r2Count}</span>}
            {qualityScore && <span className={styles.score}>Score: {qualityScore.total}/10</span>}
          </div>
        )}
        {trace.length > 0 && (
          <details className={styles.trace}>
            <summary>Trace ({trace.length} steps)</summary>
            <code>{trace.join(' → ')}</code>
          </details>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Create `frontend/src/components/ChatPanel/ChatInput.tsx`**

```typescript
import { useState } from 'react'
import styles from './ChatPanel.module.css'

interface ChatInputProps {
  onSend: (query: string) => void
  disabled: boolean
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (trimmed && !disabled) {
      onSend(trimmed)
      setValue('')
    }
  }

  return (
    <div className={styles.chatInput}>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
        placeholder="Ask a question about the paper..."
        disabled={disabled}
      />
      <button onClick={handleSubmit} disabled={disabled || !value.trim()}>Ask</button>
    </div>
  )
}
```

- [ ] **Step 7: Create `frontend/src/components/ChatPanel/MessageList.tsx`**

```typescript
import { useChatStore } from '@/store/chatStore'
import UserMessage from './UserMessage'
import AssistantMessage from './AssistantMessage'
import styles from './ChatPanel.module.css'

export default function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const streamingTokens = useChatStore((s) => s.streamingTokens)

  return (
    <div className={styles.messageList}>
      {messages.map((msg) =>
        msg.role === 'user' ? (
          <UserMessage key={msg.id} content={msg.content} />
        ) : (
          <AssistantMessage
            key={msg.id}
            content={msg.content}
            evidenceList={msg.evidenceList}
            qualityScore={msg.qualityScore}
            trace={msg.trace}
          />
        )
      )}
      {streamingTokens && (
        <div className={styles.assistantMessage}>
          <div className={styles.bubble}>{streamingTokens}</div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 8: Create `frontend/src/components/ChatPanel/ChatPanel.tsx`**

```typescript
import StepIndicator from './StepIndicator'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import { useChatStore } from '@/store/chatStore'
import styles from './ChatPanel.module.css'

interface ChatPanelProps {
  onSend: (query: string) => void
}

export default function ChatPanel({ onSend }: ChatPanelProps) {
  const status = useChatStore((s) => s.status)
  const isStreaming = status === 'connecting' || status === 'streaming'

  return (
    <div className={styles.panel}>
      <StepIndicator />
      <MessageList />
      <ChatInput onSend={onSend} disabled={isStreaming} />
    </div>
  )
}
```

- [ ] **Step 9: Create `frontend/src/components/ChatPanel/ChatPanel.module.css`**

```css
.panel { display: flex; flex-direction: column; height: 100%; gap: 8px; }

.stepIndicator { display: flex; flex-wrap: wrap; gap: 4px; padding: 8px; background: #fff; border-radius: 8px; }
.stepNode { padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; background: #f0f0f0; color: #999; }
.stepNode.done { background: #d1fae5; color: #065f46; }
.stepNode.active { background: #e0e7ff; color: #4338ca; animation: pulse 1s infinite; }

@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

.messageList { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding: 8px; }

.userMessage { display: flex; justify-content: flex-end; }
.assistantMessage { display: flex; justify-content: flex-start; }

.bubble { max-width: 85%; padding: 10px 14px; border-radius: 12px; line-height: 1.5; }
.userMessage .bubble { background: #2563eb; color: #fff; }
.assistantMessage .bubble { background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }

.answerContent { white-space: pre-wrap; word-break: break-word; }

.evidenceSummary { display: flex; gap: 6px; margin-top: 8px; font-size: 0.8rem; }
.badgeR0 { background: #fee2e2; color: #991b1b; padding: 1px 6px; border-radius: 3px; }
.badgeR1 { background: #fef3c7; color: #92400e; padding: 1px 6px; border-radius: 3px; }
.badgeR2 { background: #dbeafe; color: #1e40af; padding: 1px 6px; border-radius: 3px; }
.score { color: #6b7280; }

.trace { margin-top: 8px; font-size: 0.75rem; color: #6b7280; }
.trace summary { cursor: pointer; }
.trace code { font-size: 0.7rem; }

.chatInput { display: flex; gap: 8px; padding: 8px; background: #fff; border-radius: 8px; }
.chatInput input { flex: 1; padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; }
.chatInput button { padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
.chatInput button:disabled { background: #93a8e0; cursor: not-allowed; }
```

- [ ] **Step 10: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/frontend/ChatPanel.test.tsx`
Expected: 2 tests PASS

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/ChatPanel/ tests/frontend/ChatPanel.test.tsx
git commit -m "feat(frontend): add ChatPanel with StepIndicator, MessageList, ChatInput, streaming display"
```

---

### Task 6: Evidence System — Badge, Popover, Chain & PDF Highlight Jump

**Files:**
- Create: `frontend/src/components/Evidence/EvidenceBadge.tsx`
- Create: `frontend/src/components/Evidence/EvidencePopover.tsx`
- Create: `frontend/src/components/Evidence/EvidenceChain.tsx`
- Create: `frontend/src/components/Evidence/Evidence.module.css`
- Modify: `frontend/src/components/ChatPanel/AssistantMessage.tsx` — integrate EvidenceBadge into answer text
- Test: `tests/frontend/Evidence.test.tsx`

**Interfaces:**
- Consumes: `@/types` (Evidence, EvidenceLevel), `PaperViewer.HighlightRect` (from Task 4)
- Produces:
  - `<EvidenceBadge evidence={Evidence} onClick={handler} />` — colored badge
  - `<EvidencePopover evidence={Evidence} onJumpToPDF={handler} onClose={handler} />` — tooltip popover
  - `<EvidenceChain evidence={Evidence} allEvidence={Evidence[]} depth={number} />` — recursive R2 chain
  - `insertBadgesIntoAnswer(answer: string, evidenceList: Evidence[]): ReactNode[]` — utility to splice badges into answer text at char_start/char_end offsets

- [ ] **Step 1: Write failing test**

```typescript
// tests/frontend/Evidence.test.tsx
import { describe, it, expect } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import EvidenceBadge from '../../src/components/Evidence/EvidenceBadge'
import type { Evidence } from '../../src/types'

const r0Evidence: Evidence = {
  evidence_id: 'ev-1',
  claim: 'The method achieves F1=0.94',
  level: 'R0',
  sentence_index: 2,
  char_start: 42,
  char_end: 80,
  page: 4,
  quote: 'Our method achieves an F1 score of 0.94 on the benchmark dataset.',
  section_heading: '4. Experiments',
  source_title: null, source_url: null, source_venue: null, source_year: null,
  reasoning: null,
  based_on_evidence_ids: [],
  confidence: 0.95,
}

const r2Evidence: Evidence = {
  evidence_id: 'ev-5',
  claim: 'This approach is generalizable',
  level: 'R2',
  sentence_index: 5,
  char_start: 200,
  char_end: 230,
  page: null, quote: null, section_heading: null,
  source_title: null, source_url: null, source_venue: null, source_year: null,
  reasoning: 'Based on strong results across 3 datasets',
  based_on_evidence_ids: ['ev-1', 'ev-3'],
  confidence: 0.72,
}

describe('EvidenceBadge', () => {
  it('renders R0 with red styling', () => {
    const screen = render(<EvidenceBadge evidence={r0Evidence} />)
    const badge = screen.container.querySelector('[data-level="R0"]')
    expect(badge).toBeTruthy()
    expect(badge?.textContent).toContain('R0')
  })

  it('renders R2 with blue styling', () => {
    const screen = render(<EvidenceBadge evidence={r2Evidence} />)
    const badge = screen.container.querySelector('[data-level="R2"]')
    expect(badge).toBeTruthy()
  })

  it('calls onClick when clicked', () => {
    let clicked: Evidence | null = null
    const screen = render(<EvidenceBadge evidence={r0Evidence} onClick={(e) => { clicked = e }} />)
    fireEvent.click(screen.container.querySelector('[data-level="R0"]')!)
    expect(clicked?.evidence_id).toBe('ev-1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/Evidence.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create `frontend/src/components/Evidence/EvidenceBadge.tsx`**

```typescript
import type { Evidence } from '@/types'
import styles from './Evidence.module.css'

interface EvidenceBadgeProps {
  evidence: Evidence
  onClick?: (evidence: Evidence) => void
}

const LEVEL_STYLES: Record<string, { label: string; className: string }> = {
  R0: { label: 'R0', className: styles.badgeR0 },
  R1: { label: 'R1', className: styles.badgeR1 },
  R2: { label: 'R2', className: styles.badgeR2 },
}

export default function EvidenceBadge({ evidence, onClick }: EvidenceBadgeProps) {
  const { label, className } = LEVEL_STYLES[evidence.level] || LEVEL_STYLES.R2

  return (
    <span
      data-level={evidence.level}
      className={`${styles.badge} ${className}`}
      onClick={() => onClick?.(evidence)}
      title={`${label}: ${evidence.claim.slice(0, 80)}`}
    >
      {label}
    </span>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/Evidence/EvidencePopover.tsx`**

```typescript
import { useState } from 'react'
import type { Evidence } from '@/types'
import EvidenceChain from './EvidenceChain'
import styles from './Evidence.module.css'

interface EvidencePopoverProps {
  evidence: Evidence
  allEvidence: Evidence[]
  onJumpToPDF: (evidence: Evidence) => void
  onClose: () => void
}

export default function EvidencePopover({ evidence, allEvidence, onJumpToPDF, onClose }: EvidencePopoverProps) {
  const [showChain, setShowChain] = useState(false)

  return (
    <div className={styles.popover}>
      <div className={styles.popoverHeader}>
        <span className={styles.popoverLevel}>{evidence.level} · {evidence.level === 'R0' ? 'Paper Source' : evidence.level === 'R1' ? 'External Source' : 'Inference'}</span>
        <button className={styles.closeBtn} onClick={onClose}>×</button>
      </div>

      <p className={styles.popoverClaim}>"{evidence.claim}"</p>

      {evidence.level === 'R0' && (
        <div className={styles.popoverDetails}>
          {evidence.quote && <p className={styles.quote}>"{evidence.quote}"</p>}
          {evidence.page != null && <p>Page {evidence.page}{evidence.section_heading ? ` · ${evidence.section_heading}` : ''}</p>}
          <button className={styles.jumpBtn} onClick={() => onJumpToPDF(evidence)}>
            📄 Jump to PDF
          </button>
        </div>
      )}

      {evidence.level === 'R1' && (
        <div className={styles.popoverDetails}>
          {evidence.source_title && <p>{evidence.source_title}</p>}
          {evidence.source_url && <a href={evidence.source_url} target="_blank" rel="noopener">Open source</a>}
        </div>
      )}

      {evidence.level === 'R2' && (
        <div className={styles.popoverDetails}>
          {evidence.reasoning && <p className={styles.reasoning}>💡 {evidence.reasoning}</p>}
          {evidence.based_on_evidence_ids.length > 0 && (
            <>
              <button className={styles.chainToggle} onClick={() => setShowChain(!showChain)}>
                {showChain ? '▾' : '▸'} Based on {evidence.based_on_evidence_ids.length} evidence
              </button>
              {showChain && <EvidenceChain evidence={evidence} allEvidence={allEvidence} depth={1} />}
            </>
          )}
          <p>Confidence: {(evidence.confidence * 100).toFixed(0)}%</p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Create `frontend/src/components/Evidence/EvidenceChain.tsx`**

```typescript
import type { Evidence } from '@/types'
import styles from './Evidence.module.css'

interface EvidenceChainProps {
  evidence: Evidence
  allEvidence: Evidence[]
  depth: number
}

const MAX_DEPTH = 3

export default function EvidenceChain({ evidence, allEvidence, depth }: EvidenceChainProps) {
  if (depth > MAX_DEPTH || evidence.based_on_evidence_ids.length === 0) return null

  const children = evidence.based_on_evidence_ids
    .map((id) => allEvidence.find((e) => e.evidence_id === id))
    .filter(Boolean) as Evidence[]

  return (
    <ul className={styles.chainList}>
      {children.map((child) => (
        <li key={child.evidence_id} className={styles.chainItem}>
          <span className={`${styles.miniBadge} ${child.level === 'R0' ? styles.badgeR0 : child.level === 'R1' ? styles.badgeR1 : styles.badgeR2}`}>
            {child.level}
          </span>
          <span className={styles.chainClaim}>"{child.claim.slice(0, 100)}"</span>
          {child.based_on_evidence_ids.length > 0 && depth < MAX_DEPTH && (
            <EvidenceChain evidence={child} allEvidence={allEvidence} depth={depth + 1} />
          )}
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 6: Create `frontend/src/components/Evidence/Evidence.module.css`**

```css
.badge { display: inline-block; font-size: 0.7rem; font-weight: 700; padding: 1px 5px; border-radius: 3px; margin: 0 1px; vertical-align: middle; cursor: pointer; }
.badge:hover { opacity: 0.8; }

.badgeR0 { background: #fee2e2; color: #991b1b; }
.badgeR1 { background: #fef3c7; color: #92400e; }
.badgeR2 { background: #dbeafe; color: #1e40af; }

.popover { position: absolute; z-index: 100; width: 320px; max-height: 400px; overflow-y: auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); padding: 12px; font-size: 0.85rem; }
.popoverHeader { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.popoverLevel { font-weight: 600; }
.closeBtn { background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #6b7280; }
.popoverClaim { font-style: italic; margin-bottom: 8px; color: #333; }
.popoverDetails { border-top: 1px solid #e5e7eb; padding-top: 8px; }
.quote { color: #6b7280; font-size: 0.8rem; margin-bottom: 4px; }
.jumpBtn { margin-top: 6px; padding: 4px 10px; background: #2563eb; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
.reasoning { color: #6b7280; margin-bottom: 4px; }
.chainToggle { background: none; border: none; color: #2563eb; cursor: pointer; font-size: 0.8rem; padding: 2px 0; }

.chainList { list-style: none; padding-left: 16px; margin: 4px 0; }
.chainItem { margin: 4px 0; font-size: 0.8rem; }
.miniBadge { display: inline-block; font-size: 0.65rem; padding: 0px 4px; border-radius: 2px; margin-right: 4px; }
.chainClaim { color: #555; }
```

- [ ] **Step 7: Modify `AssistantMessage.tsx` to insert badges into answer text**

Replace the plain answer content rendering with badge-aware rendering:

```typescript
// Add to AssistantMessage.tsx imports:
import { useMemo, Fragment } from 'react'
import EvidenceBadge from '@/components/Evidence/EvidenceBadge'
import type { Evidence } from '@/types'

// Add helper (inside component or as module-level):
function renderAnswerWithBadges(answer: string, evidenceList: Evidence[]): React.ReactNode[] {
  if (evidenceList.length === 0) return [answer]

  // Sort evidence by char_start for left-to-right insertion
  const sorted = [...evidenceList]
    .filter((e) => e.char_start != null && e.char_end != null)
    .sort((a, b) => (a.char_start ?? 0) - (b.char_start ?? 0))

  if (sorted.length === 0) return [answer]

  const nodes: React.ReactNode[] = []
  let cursor = 0
  for (const ev of sorted) {
    const start = ev.char_start ?? 0
    const end = ev.char_end ?? 0
    if (start > cursor) {
      nodes.push(answer.slice(cursor, start))
    }
    nodes.push(<EvidenceBadge key={ev.evidence_id} evidence={ev} />)
    cursor = Math.max(cursor, end)
  }
  if (cursor < answer.length) {
    nodes.push(answer.slice(cursor))
  }
  return nodes
}

// In the component, replace:
// <div className={styles.answerContent}>{content}</div>
// with:
// <div className={styles.answerContent}>{renderAnswerWithBadges(content, evidenceList)}</div>
```

- [ ] **Step 8: Run test to verify**

Run: `cd frontend && npx vitest run tests/frontend/Evidence.test.tsx`
Expected: 3 tests PASS

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/Evidence/ frontend/src/components/ChatPanel/AssistantMessage.tsx tests/frontend/Evidence.test.tsx
git commit -m "feat(frontend): add EvidenceBadge, EvidencePopover, EvidenceChain with badge insertion into answer text"
```

---

### Task 7: HITL — PlanApprovalBanner, useApproval, Two-Segment Reconnect

**Files:**
- Create: `frontend/src/components/ChatPanel/PlanApprovalBanner.tsx`
- Create: `frontend/src/hooks/useApproval.ts`
- Modify: `frontend/src/components/ChatPanel/ChatPanel.tsx` — wire PlanApprovalBanner + approval flow
- Test: `tests/frontend/HITL.test.tsx`

**Interfaces:**
- Consumes: `@/store/chatStore` (hitlPlan, status, threadId), `@/api/client` (approvePlan), `useSSE` (startResume)
- Produces:
  - `<PlanApprovalBanner plan={Plan} onApprove={() => void} onReject={(feedback?) => void} onEdit={(steps) => void} />`
  - `useApproval(): { approve(threadId: string): Promise<void>; reject(threadId: string, feedback?: string): Promise<void> }`

- [ ] **Step 1: Write failing test**

```typescript
// tests/frontend/HITL.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useChatStore } from '../../src/store/chatStore'
import type { Plan } from '../../src/types'

const samplePlan: Plan = {
  steps: [
    { step: 1, action: 'Retrieve Section 3', tool: 'retrieve', target: 'Section 3' },
    { step: 2, action: 'Extract parameters', tool: 'retrieve', target: 'table 1' },
  ],
}

import PlanApprovalBanner from '../../src/components/ChatPanel/PlanApprovalBanner'

describe('PlanApprovalBanner', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
  })

  it('renders plan steps and approve/cancel buttons', () => {
    const screen = render(<PlanApprovalBanner plan={samplePlan} onApprove={vi.fn()} onReject={vi.fn()} onEdit={vi.fn()} />)
    expect(screen.getByText('Retrieve Section 3')).toBeTruthy()
    expect(screen.getByText('Extract parameters')).toBeTruthy()
    expect(screen.getByText(/批准执行/)).toBeTruthy()
    expect(screen.getByText(/取消/)).toBeTruthy()
  })

  it('calls onApprove when approve button clicked', () => {
    const onApprove = vi.fn()
    const screen = render(<PlanApprovalBanner plan={samplePlan} onApprove={onApprove} onReject={vi.fn()} onEdit={vi.fn()} />)
    fireEvent.click(screen.getByText(/批准执行/))
    expect(onApprove).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/frontend/HITL.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create `frontend/src/components/ChatPanel/PlanApprovalBanner.tsx`**

```typescript
import { useState } from 'react'
import type { Plan } from '@/types'
import styles from './ChatPanel.module.css'

interface PlanApprovalBannerProps {
  plan: Plan
  onApprove: () => void
  onReject: (feedback?: string) => void
  onEdit: (steps: Plan['steps']) => void
}

export default function PlanApprovalBanner({ plan, onApprove, onReject, onEdit }: PlanApprovalBannerProps) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(
    plan.steps.map((s) => `${s.step}. ${s.action} [${s.tool}: ${s.target}]`).join('\n')
  )

  const handleEditSave = () => {
    const steps = editText.split('\n').filter(Boolean).map((line, i) => {
      const match = line.match(/^\d+\.\s*(.+?)\s*\[(.+?):\s*(.+)\]$/)
      return {
        step: i + 1,
        action: match?.[1]?.trim() || line.trim(),
        tool: match?.[2]?.trim() || 'retrieve',
        target: match?.[3]?.trim() || line.trim(),
      }
    })
    onEdit(steps)
    setEditing(false)
  }

  return (
    <div className={styles.approvalBanner}>
      <div className={styles.approvalHeader}>🔍 Agent Plan</div>

      {editing ? (
        <textarea
          className={styles.approvalEdit}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          rows={6}
        />
      ) : (
        <ol className={styles.approvalSteps}>
          {plan.steps.map((step) => (
            <li key={step.step}>{step.action} <span className={styles.stepMeta}>[{step.tool}: {step.target}]</span></li>
          ))}
        </ol>
      )}

      <div className={styles.approvalActions}>
        {editing ? (
          <>
            <button onClick={handleEditSave}>💾 Save</button>
            <button onClick={() => setEditing(false)}>Cancel</button>
          </>
        ) : (
          <>
            <button onClick={() => setEditing(true)}>✏️ Edit</button>
            <button className={styles.approveBtn} onClick={onApprove}>✅ Approve</button>
            <button className={styles.rejectBtn} onClick={() => onReject()}>❌ Cancel</button>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/hooks/useApproval.ts`**

```typescript
import { useCallback } from 'react'
import { approvePlan } from '@/api/client'

export function useApproval() {
  const approve = useCallback(async (threadId: string, feedback?: string) => {
    const res = await approvePlan({ thread_id: threadId, approved: true, feedback })
    return res
  }, [])

  const reject = useCallback(async (threadId: string, feedback?: string) => {
    const res = await approvePlan({ thread_id: threadId, approved: false, feedback })
    return res
  }, [])

  return { approve, reject }
}
```

- [ ] **Step 5: Modify `ChatPanel.tsx` to wire PlanApprovalBanner and approval flow**

```typescript
// Updated ChatPanel.tsx
import { useCallback } from 'react'
import StepIndicator from './StepIndicator'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import PlanApprovalBanner from './PlanApprovalBanner'
import { useChatStore } from '@/store/chatStore'
import { useApproval } from '@/hooks/useApproval'
import { useSSE } from '@/hooks/useSSE'
import styles from './ChatPanel.module.css'

interface ChatPanelProps {
  paperId: string
}

export default function ChatPanel({ paperId }: ChatPanelProps) {
  const status = useChatStore((s) => s.status)
  const hitlPlan = useChatStore((s) => s.hitlPlan)
  const threadId = useChatStore((s) => s.threadId)
  const isStreaming = status === 'connecting' || status === 'streaming'
  const isAwaitingApproval = status === 'awaiting_approval'

  const { start, startResume } = useSSE()
  const { approve, reject } = useApproval()

  const handleSend = useCallback((query: string) => {
    useChatStore.getState().addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
    })
    start({ paper_id: paperId, query })
  }, [paperId, start])

  const handleApprove = useCallback(async () => {
    if (!threadId) return
    await approve(threadId)
    startResume(threadId)
  }, [threadId, approve, startResume])

  const handleReject = useCallback(async (feedback?: string) => {
    if (!threadId) return
    await reject(threadId, feedback)
    useChatStore.getState().reset()
  }, [threadId, reject])

  const handleEditPlan = useCallback(async (steps: Plan['steps']) => {
    if (!threadId) return
    await approve(threadId, `User edited plan: ${JSON.stringify(steps)}`)
    startResume(threadId)
  }, [threadId, approve, startResume])

  return (
    <div className={styles.panel}>
      <StepIndicator />
      {isAwaitingApproval && hitlPlan && (
        <PlanApprovalBanner
          plan={hitlPlan}
          onApprove={handleApprove}
          onReject={handleReject}
          onEdit={handleEditPlan}
        />
      )}
      <MessageList />
      {isStreaming && !isAwaitingApproval && (
        <div className={styles.streamingIndicator}>Agent is working...</div>
      )}
      <ChatInput onSend={handleSend} disabled={isStreaming || isAwaitingApproval} />
    </div>
  )
}
```

- [ ] **Step 6: Run test to verify**

Run: `cd frontend && npx vitest run tests/frontend/HITL.test.tsx`
Expected: 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ChatPanel/PlanApprovalBanner.tsx frontend/src/hooks/useApproval.ts frontend/src/components/ChatPanel/ChatPanel.tsx tests/frontend/HITL.test.tsx
git commit -m "feat(frontend): add HITL plan approval with PlanApprovalBanner, useApproval, and two-segment SSE reconnect"
```

---

### Task 8: Layout — TopBar, Sidebar, LibraryPanel, Responsive

**Files:**
- Create: `frontend/src/components/Layout/TopBar.tsx`
- Create: `frontend/src/components/Layout/Sidebar.tsx`
- Create: `frontend/src/components/Layout/LibraryPanel.tsx`
- Create: `frontend/src/components/Layout/SessionHistory.tsx`
- Create: `frontend/src/components/Layout/LayoutToggle.tsx`
- Create: `frontend/src/components/Layout/Layout.module.css`
- Create: `frontend/src/components/common/TracePanel.tsx`
- Create: `frontend/src/components/common/FollowUpSuggest.tsx`
- Create: `frontend/src/components/common/ResizableSplit.tsx`
- Create: `frontend/src/components/common/LoadingSpinner.tsx`
- Modify: `frontend/src/App.tsx` — compose full layout
- Modify: `frontend/src/App.css` — responsive breakpoints

**Interfaces:**
- Consumes: `@/store/appStore`, `@/store/chatStore`, all previous components
- Produces:
  - `<App />` — final composition: TopBar + ResizableSplit(PaperViewer, ChatPanel) + Sidebar
  - `<TopBar paperTitle={string} onToggleSidebar={() => void} />`
  - `<Sidebar open={boolean} onClose={() => void} />`
  - `<LibraryPanel />` — lists papers via API, allows selection
  - `<SessionHistory />` — lists past sessions
  - `<LayoutToggle layout={LayoutMode} onChange={(m) => void} />`
  - `<TracePanel trace={string[]} />`
  - `<FollowUpSuggest questions={string[]} onSelect={(q) => void} />`
  - `<ResizableSplit left={ReactNode} right={ReactNode} defaultRatio={0.45} />`

- [ ] **Step 1: Create Layout components**

All layout components follow the same pattern — create each file with full implementation:

```typescript
// TopBar.tsx
import { useAppStore } from '@/store/appStore'
import LayoutToggle from './LayoutToggle'
import styles from './Layout.module.css'

export default function TopBar() {
  const paper = useAppStore((s) => s.paper)

  return (
    <div className={styles.topBar}>
      <h1 className={styles.title}>{paper?.title || 'Paper Reading Agent'}</h1>
      <div className={styles.topBarRight}>
        <LayoutToggle />
        <button className={styles.menuBtn} onClick={() => useAppStore.getState().toggleSidebar()}>
          ☰ Library
        </button>
      </div>
    </div>
  )
}
```

```typescript
// LayoutToggle.tsx
import { useAppStore, type LayoutMode } from '@/store/appStore'
import styles from './Layout.module.css'

const MODES: { mode: LayoutMode; label: string; icon: string }[] = [
  { mode: 'dual', label: 'Dual', icon: '◧' },
  { mode: 'chat', label: 'Chat', icon: '▯' },
  { mode: 'paper', label: 'Paper', icon: '▭' },
]

export default function LayoutToggle() {
  const layout = useAppStore((s) => s.layout)
  const setLayout = useAppStore((s) => s.setLayout)

  return (
    <div className={styles.layoutToggle}>
      {MODES.map(({ mode, label, icon }) => (
        <button
          key={mode}
          className={layout === mode ? styles.active : ''}
          onClick={() => setLayout(mode)}
        >
          {icon} {label}
        </button>
      ))}
    </div>
  )
}
```

```typescript
// Sidebar.tsx
import { useAppStore } from '@/store/appStore'
import LibraryPanel from './LibraryPanel'
import SessionHistory from './SessionHistory'
import styles from './Layout.module.css'

export default function Sidebar() {
  const sidebarOpen = useAppStore((s) => s.sidebarOpen)
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)

  if (!sidebarOpen) return null

  return (
    <div className={styles.sidebarOverlay} onClick={toggleSidebar}>
      <div className={styles.sidebar} onClick={(e) => e.stopPropagation()}>
        <button className={styles.closeBtn} onClick={toggleSidebar}>×</button>
        <LibraryPanel />
        <SessionHistory />
      </div>
    </div>
  )
}
```

```typescript
// LibraryPanel.tsx
import { useState, useEffect } from 'react'
import { listPapers } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import type { PaperListResponse } from '@/types'
import styles from './Layout.module.css'

export default function LibraryPanel() {
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const setPaper = useAppStore((s) => s.setPaper)

  useEffect(() => {
    listPapers().then(setPapers).catch(() => setPapers([]))
  }, [])

  return (
    <div className={styles.libraryPanel}>
      <h3>📚 Paper Library</h3>
      {papers.length === 0 && <p className={styles.empty}>No papers uploaded</p>}
      <ul>
        {papers.map((p) => (
          <li key={p.paper_id} onClick={() => setPaper({
            paper_id: p.paper_id,
            title: p.title,
            file_path: '',
            parsed_at: p.parsed_at,
          })}>
            {p.title}
          </li>
        ))}
      </ul>
    </div>
  )
}
```

```typescript
// SessionHistory.tsx
import { useAppStore } from '@/store/appStore'
import styles from './Layout.module.css'

export default function SessionHistory() {
  const sessions = useAppStore((s) => s.sessions)

  return (
    <div className={styles.sessionHistory}>
      <h3>💬 Sessions</h3>
      {sessions.length === 0 && <p className={styles.empty}>No sessions yet</p>}
      <ul>
        {sessions.map((s) => (
          <li key={s.id}>
            <span className={styles.sessionTitle}>{s.title}</span>
            <span className={styles.sessionDate}>{new Date(s.createdAt).toLocaleDateString()}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

```typescript
// ResizableSplit.tsx
import { useState, useCallback, type ReactNode } from 'react'
import styles from './Layout.module.css' // common components share Layout.module.css

interface ResizableSplitProps {
  left: ReactNode
  right: ReactNode
  defaultRatio?: number
  minRatio?: number
  maxRatio?: number
  leftVisible?: boolean
  rightVisible?: boolean
}

export default function ResizableSplit({
  left, right,
  defaultRatio = 0.45,
  minRatio = 0.25,
  maxRatio = 0.75,
  leftVisible = true,
  rightVisible = true,
}: ResizableSplitProps) {
  const [ratio, setRatio] = useState(defaultRatio)

  const handleMouseDown = useCallback(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const container = document.querySelector(`.${styles.split}`) as HTMLElement
      if (!container) return
      const rect = container.getBoundingClientRect()
      const newRatio = (e.clientX - rect.left) / rect.width
      setRatio(Math.max(minRatio, Math.min(maxRatio, newRatio)))
    }
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [minRatio, maxRatio])

  if (!leftVisible) return <div className={styles.split}>{right}</div>
  if (!rightVisible) return <div className={styles.split}>{left}</div>

  return (
    <div className={styles.split}>
      <div className={styles.splitLeft} style={{ width: `${ratio * 100}%` }}>
        {left}
      </div>
      <div className={styles.splitHandle} onMouseDown={handleMouseDown} />
      <div className={styles.splitRight} style={{ width: `${(1 - ratio) * 100}%` }}>
        {right}
      </div>
    </div>
  )
}
```

```typescript
// TracePanel.tsx
import styles from './Layout.module.css' // reuse common styles

export default function TracePanel({ trace }: { trace: string[] }) {
  if (!trace || trace.length === 0) return null
  return (
    <details className={styles.tracePanel}>
      <summary>Trace ({trace.length} steps)</summary>
      <code>{trace.join(' → ')}</code>
    </details>
  )
}
```

```typescript
// FollowUpSuggest.tsx
import styles from './Layout.module.css'

interface FollowUpSuggestProps {
  questions: string[]
  onSelect: (question: string) => void
}

export default function FollowUpSuggest({ questions, onSelect }: FollowUpSuggestProps) {
  if (!questions || questions.length === 0) return null
  return (
    <div className={styles.followUp}>
      <h4>Follow-up questions:</h4>
      {questions.map((q, i) => (
        <button key={i} onClick={() => onSelect(q)}>{q}</button>
      ))}
    </div>
  )
}
```

```typescript
// LoadingSpinner.tsx
export default function LoadingSpinner({ message = 'Loading...' }: { message?: string }) {
  return <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>{message}</div>
}
```

- [ ] **Step 2: Create Layout CSS**

```css
/* Layout.module.css */
.topBar { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #fff; border-bottom: 1px solid #e5e7eb; }
.title { font-size: 1.1rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 60%; }
.topBarRight { display: flex; gap: 8px; align-items: center; }
.menuBtn { padding: 4px 10px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; }

.layoutToggle { display: flex; gap: 2px; }
.layoutToggle button { padding: 4px 8px; border: 1px solid #ccc; background: #fff; cursor: pointer; font-size: 0.8rem; border-radius: 4px; }
.layoutToggle button.active { background: #2563eb; color: #fff; border-color: #2563eb; }

.sidebarOverlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.3); z-index: 200; }
.sidebar { position: fixed; top: 0; right: 0; width: 320px; height: 100%; background: #fff; overflow-y: auto; padding: 16px; box-shadow: -2px 0 8px rgba(0,0,0,0.1); }
.closeBtn { background: none; border: none; font-size: 1.5rem; cursor: pointer; float: right; }

.libraryPanel h3, .sessionHistory h3 { margin-bottom: 8px; font-size: 0.9rem; color: #555; }
.libraryPanel ul, .sessionHistory ul { list-style: none; }
.libraryPanel li, .sessionHistory li { padding: 6px 8px; cursor: pointer; border-radius: 4px; font-size: 0.85rem; }
.libraryPanel li:hover, .sessionHistory li:hover { background: #f3f4f6; }
.empty { color: #9ca3af; font-size: 0.8rem; }
.sessionTitle { display: block; }
.sessionDate { font-size: 0.7rem; color: #9ca3af; }

.split { display: flex; flex: 1; overflow: hidden; }
.splitLeft, .splitRight { overflow: hidden; }
.splitHandle { width: 6px; cursor: col-resize; background: #e5e7eb; flex-shrink: 0; }
.splitHandle:hover { background: #2563eb; }

.tracePanel { margin-top: 8px; font-size: 0.75rem; color: #6b7280; }
.tracePanel summary { cursor: pointer; }

.followUp { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.followUp h4 { font-size: 0.8rem; color: #6b7280; width: 100%; margin-bottom: 2px; }
.followUp button { padding: 4px 10px; background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 16px; cursor: pointer; font-size: 0.8rem; }
.followUp button:hover { background: #e0e7ff; }
```

- [ ] **Step 3: Update `App.tsx` — final composition**

```typescript
import { useCallback } from 'react'
import { useAppStore, type LayoutMode } from '@/store/appStore'
import { useChatStore } from '@/store/chatStore'
import TopBar from '@/components/Layout/TopBar'
import Sidebar from '@/components/Layout/Sidebar'
import ResizableSplit from '@/components/common/ResizableSplit'
import PaperViewer from '@/components/PaperViewer/PaperViewer'
import ChatPanel from '@/components/ChatPanel/ChatPanel'
import FollowUpSuggest from '@/components/common/FollowUpSuggest'
import './App.css'

export default function App() {
  const paper = useAppStore((s) => s.paper)
  const layout = useAppStore((s) => s.layout)

  const handleFollowUp = useCallback((question: string) => {
    // Trigger the same flow as ChatInput.onSend — but ChatPanel handles this internally
    // For now, dispatch directly to chat store and use SSE
    if (!paper) return
    useChatStore.getState().addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: question,
    })
  }, [paper])

  return (
    <div className="app">
      <TopBar />
      <div className="main-content">
        {layout === 'dual' && (
          <ResizableSplit
            left={<PaperViewer paperId={paper?.paper_id || ''} />}
            right={<ChatPanel paperId={paper?.paper_id || ''} />}
            leftVisible={!!paper}
            rightVisible={!!paper}
          />
        )}
        {layout === 'chat' && (
          <div className="full-panel">
            <ChatPanel paperId={paper?.paper_id || ''} />
          </div>
        )}
        {layout === 'paper' && (
          <div className="full-panel">
            <PaperViewer paperId={paper?.paper_id || ''} />
          </div>
        )}
        {!paper && (
          <div className="empty-state">
            <p>Upload a paper to get started</p>
          </div>
        )}
      </div>
      <Sidebar />
    </div>
  )
}
```

- [ ] **Step 4: Update `App.css` with responsive and layout styles**

```css
/* Add after existing rules */
.main-content { display: flex; flex: 1; overflow: hidden; min-height: 0; }
.full-panel { flex: 1; overflow: hidden; }
.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; color: #9ca3af; font-size: 1.1rem; }

@media (max-width: 768px) {
  .app { padding: 8px; }
  .topBar { flex-wrap: wrap; gap: 4px; }
  .split { flex-direction: column; }
  .splitHandle { width: 100%; height: 4px; cursor: row-resize; }
  .layoutToggle button { font-size: 0.7rem; padding: 2px 6px; }
}
```

- [ ] **Step 5: Run all frontend tests**

Run: `cd frontend && npx vitest run`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Layout/ frontend/src/components/common/ frontend/src/App.tsx frontend/src/App.css
git commit -m "feat(frontend): add full layout with TopBar, Sidebar, LayoutToggle, responsive ResizableSplit"
```

---

### Task 9: Backend — SSE Streaming, HITL Interrupt, New Endpoints

**Files:**
- Modify: `backend/app.py` — rewrite `/api/query` as GET with SSE streaming, add `/api/approve`, `/api/pdf/{paper_id}`, `/api/pdf/{paper_id}/text`
- Modify: `backend/agents/supervisor.py` — replace `graph.invoke` with `graph.astream_events`, add `should_interrupt`, add token streaming

**Interfaces:**
- Consumes: All existing backend modules (models, llm, agents, config)
- Produces:
  - `GET /api/query?paper_id=xxx&query=yyy` — SSE stream with init/node/hitl/token/done events
  - `GET /api/query?thread_id=xxx` — resume SSE from checkpoint
  - `POST /api/approve` — `{ thread_id, approved, feedback? }` → `{ status }`
  - `GET /api/pdf/{paper_id}` — binary PDF stream
  - `GET /api/pdf/{paper_id}/text` — `{ pages: [{ page, width, height, sentences }] }`

- [ ] **Step 1: Modify `backend/agents/supervisor.py` — add `should_interrupt` and `stream_agent`**

Add after `build_graph()`:

```python
def should_interrupt(state: AgentState) -> list[str]:
    """Only trigger HITL for complex intents (compare/recommend).
    Summary and QA intents auto-pass without user intervention."""
    if state.intent in ("compare", "recommend"):
        return ["planner"]
    return []


async def stream_graph(paper_path: str, query: str, thread_id: str | None = None):
    """Stream agent execution via graph.astream_events().
    Yields SSE-formatted strings for each event."""
    import json
    from backend.models.state import AgentState
    from backend.models.paper import Paper

    graph = await build_graph()

    config_dict = {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}

    # Determine if this is a resume (thread_id exists and has checkpoints)
    if thread_id:
        # Resume from existing checkpoint
        state_snapshot = await graph.aget_state(config_dict)
        if state_snapshot and state_snapshot.values:
            # Continue execution
            async for event in graph.astream_events(None, config_dict, version="v2"):
                kind = event.get("event")
                if kind == "on_chain_start":
                    name = event.get("name", "")
                    if name in NODE_NAMES:
                        yield f"event: node\ndata: {json.dumps({'node': name})}\n\n"
                elif kind == "on_chain_end":
                    name = event.get("name", "")
                    if name == "generate":
                        # Get final answer from state
                        final_state = await graph.aget_state(config_dict)
                        if final_state and final_state.values:
                            s = AgentState(**{k: v for k, v in final_state.values.items() if k in AgentState.__dataclass_fields__})
                            yield f"event: done\ndata: {json.dumps(_build_done_payload(s))}\n\n"
            return

    # New execution
    initial_state = AgentState(
        paper=Paper(file_path=str(Path(paper_path).resolve())),
        user_query=query
    )

    yield f"event: init\ndata: {json.dumps({'thread_id': config_dict['configurable']['thread_id']})}\n\n"

    # First pass: reader → classify → planner (may interrupt)
    async for event in graph.astream_events(initial_state, config_dict, version="v2"):
        kind = event.get("event")
        if kind == "on_chain_start":
            name = event.get("name", "")
            if name in NODE_NAMES:
                yield f"event: node\ndata: {json.dumps({'node': name})}\n\n"
        elif kind == "on_chain_end":
            name = event.get("name", "")
            if name == "planner":
                # Check if we should interrupt
                state_snapshot = await graph.aget_state(config_dict)
                if state_snapshot and state_snapshot.values:
                    s = AgentState(**{k: v for k, v in state_snapshot.values.items() if k in AgentState.__dataclass_fields__})
                    if should_interrupt(s):
                        yield f"event: hitl\ndata: {json.dumps({'type': 'plan_approval', 'plan': s.plan})}\n\n"
                        return  # End first SSE segment — client will POST /api/approve
            elif name == "generate":
                # Done
                final_state = await graph.aget_state(config_dict)
                if final_state and final_state.values:
                    s = AgentState(**{k: v for k, v in final_state.values.items() if k in AgentState.__dataclass_fields__})
                    yield f"event: done\ndata: {json.dumps(_build_done_payload(s))}\n\n"


def _build_done_payload(state: AgentState) -> dict:
    return {
        "answer": state.answer,
        "quality_score": {
            "total": state.quality_score.total if state.quality_score else 0,
            "relevance": state.quality_score.relevance if state.quality_score else 0,
            "consistency": state.quality_score.consistency if state.quality_score else 0,
            "completeness": state.quality_score.completeness if state.quality_score else 0,
        },
        "evidence_list": [
            {
                "evidence_id": e.evidence_id,
                "level": e.level.value,
                "claim": e.claim,
                "page": e.page,
                "quote": e.quote,
                "char_start": e.char_start,
                "char_end": e.char_end,
                "sentence_index": e.sentence_index,
                "section_heading": e.section_heading,
                "source_title": e.source_title,
                "source_url": e.source_url,
                "source_venue": e.source_venue,
                "source_year": e.source_year,
                "reasoning": e.reasoning,
                "based_on_evidence_ids": e.based_on_evidence_ids,
                "confidence": e.confidence,
            }
            for e in state.evidence_list
        ],
        "trace": state.trace,
        "followup_questions": state.observation.get("followup_questions", []) if state.observation else [],
    }
```

- [ ] **Step 2: Modify `backend/app.py` — rewrite endpoints**

Replace existing `/api/query` and add new endpoints:

```python
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.agents.supervisor import stream_graph
from backend.models.paper import Paper
from backend.storage.paper_store import PaperStore
from backend.config import config

app = FastAPI(title="Paper Reading Agent")

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

@app.get("/api/query")
async def query_paper(
    paper_id: str = Query(default=""),
    query: str = Query(default=""),
    thread_id: str = Query(default=""),
):
    """SSE streaming endpoint for agent queries.
    First call: pass paper_id + query → returns init event with thread_id.
    Resume call: pass thread_id → continues from checkpoint.
    """
    async def event_stream():
        async for sse_line in stream_graph(
            paper_path=paper_id,
            query=query,
            thread_id=thread_id or None,
        ):
            yield sse_line
    return StreamingResponse(event_stream(), media_type="text/event-stream")


class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool = True
    feedback: str | None = None

@app.post("/api/approve")
async def approve_plan(req: ApproveRequest):
    """Handle HITL approval. If approved, the caller should then GET /api/query?thread_id=xxx to resume."""
    if not req.approved:
        return {"status": "cancelled"}
    return {"status": "resumed"}


@app.get("/api/pdf/{paper_id}")
async def get_pdf(paper_id: str):
    """Serve PDF binary for PDF.js rendering."""
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper or not Path(paper.file_path).exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    return FileResponse(paper.file_path, media_type="application/pdf")


@app.get("/api/pdf/{paper_id}/text")
async def get_pdf_text(paper_id: str):
    """Return text layer data (pages with sentences and bbox) for PDF highlight overlay."""
    import fitz  # PyMuPDF
    store = PaperStore()
    paper = await store.get_paper(paper_id)
    if not paper or not Path(paper.file_path).exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)

    doc = fitz.open(paper.file_path)
    pages = []
    for page_idx in range(min(len(doc), 30)):  # Cap at 30 pages
        page = doc[page_idx]
        rect = page.rect
        # Get text blocks with positions
        blocks = page.get_text("dict")["blocks"]
        sentences = []
        for block in blocks:
            if block.get("type") != 0:  # text block
                continue
            for line in block.get("lines", []):
                text_parts = []
                bbox = None
                for span in line.get("spans", []):
                    text_parts.append(span["text"])
                    if bbox is None:
                        bbox = list(span["bbox"])
                    else:
                        # Expand bbox
                        bbox[2] = max(bbox[2], span["bbox"][2])
                        bbox[3] = max(bbox[3], span["bbox"][3])
                full_text = " ".join(text_parts).strip()
                if full_text and bbox:
                    sentences.append({
                        "text": full_text,
                        "char_start": 0,
                        "char_end": len(full_text),
                        "bbox": bbox,
                    })
        pages.append({
            "page": page_idx + 1,
            "width": rect.width,
            "height": rect.height,
            "sentences": sentences,
        })
    doc.close()
    return {"pages": pages}


@app.get("/api/papers")
async def list_papers():
    store = PaperStore()
    papers = await store.list_papers()
    return [{"paper_id": p.paper_id, "title": p.title, "parsed_at": p.parsed_at} for p in papers]
```

- [ ] **Step 3: Add `import uuid` at top of `backend/agents/supervisor.py`**

- [ ] **Step 4: Run backend tests to verify no regressions**

Run: `cd paper-reading-agent && python -m pytest tests/ -v`
Expected: 24+ tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/agents/supervisor.py
git commit -m "feat(backend): add SSE streaming with astream_events, conditional HITL interrupt, PDF text endpoint"
```

---

### Task 10: Upload Flow & App Integration

**Files:**
- Modify: `frontend/src/App.tsx` — add upload widget
- Create: `frontend/src/components/Layout/UploadWidget.tsx`
- Test: `tests/frontend/UploadWidget.test.tsx`

**Interfaces:**
- Consumes: `@/api/client` (uploadPaper), `@/store/appStore` (setPaper)
- Produces:
  - `<UploadWidget onUploaded={(paper) => void} />` — file input + upload button + status

- [ ] **Step 1: Write failing test for UploadWidget**

```typescript
// tests/frontend/UploadWidget.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'

global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve({ paper_id: 'p1', title: 'test.pdf', file_path: '/data/test.pdf' }),
})

import UploadWidget from '../../src/components/Layout/UploadWidget'

describe('UploadWidget', () => {
  it('renders file input and upload button', () => {
    const screen = render(<UploadWidget onUploaded={vi.fn()} />)
    expect(screen.container.querySelector('input[type="file"]')).toBeTruthy()
    expect(screen.getByText('Upload')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Create `UploadWidget.tsx`**

```typescript
import { useState, useRef } from 'react'
import { uploadPaper } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import type { Paper, UploadResponse } from '@/types'
import styles from './Layout.module.css'

export default function UploadWidget({ onUploaded }: { onUploaded?: (paper: Paper) => void }) {
  const [uploading, setUploading] = useState(false)
  const [status, setStatus] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) { setStatus('Select a PDF'); return }
    setUploading(true)
    setStatus('Uploading...')
    try {
      const result: UploadResponse = await uploadPaper(file)
      const paper: Paper = {
        paper_id: result.paper_id,
        title: result.title,
        file_path: result.file_path,
        parsed_at: null,
      }
      useAppStore.getState().setPaper(paper)
      setStatus(`Uploaded: ${result.title}`)
      onUploaded?.(paper)
    } catch (e: any) {
      setStatus(`Error: ${e.message}`)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className={styles.uploadWidget}>
      <input type="file" ref={fileRef} accept=".pdf" />
      <button onClick={handleUpload} disabled={uploading}>Upload</button>
      {status && <span className={styles.uploadStatus}>{status}</span>}
    </div>
  )
}
```

- [ ] **Step 3: Integrate UploadWidget into App.tsx**

Add to the empty state and TopBar area:

```typescript
// In App.tsx, add import:
import UploadWidget from '@/components/Layout/UploadWidget'

// Replace the empty state with:
{!paper && (
  <div className="empty-state">
    <UploadWidget />
  </div>
)}
```

- [ ] **Step 4: Run all tests**

Run: `cd frontend && npx vitest run`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Layout/UploadWidget.tsx frontend/src/App.tsx tests/frontend/UploadWidget.test.tsx
git commit -m "feat(frontend): add upload widget and integrate with app store"
```

---

### Task 11: Integration & End-to-End Verification

**Files:** None (verify only)

**Test:** Manual verification checklist

- [ ] **Step 1: Start backend server**

Run: `cd paper-reading-agent && python -m backend`
Expected: Uvicorn running on http://localhost:8000

- [ ] **Step 2: Start frontend dev server**

Run: `cd frontend && npm run dev`
Expected: Vite running on http://localhost:3000, API calls proxied to :8000

- [ ] **Step 3: Upload a test PDF**

- Open http://localhost:3000
- Click file input → select `tests/fixtures/sample.pdf`
- Click Upload
Expected: Paper title appears in TopBar, dual-panel layout shows

- [ ] **Step 4: Test summary query (no HITL)**

- Type: "What is this paper about?"
- Click Ask
Expected: StepIndicator shows reader→classify→planner→retrieve→generate→observe→reviewer→output, answer appears with evidence badges

- [ ] **Step 5: Test compare query (HITL triggered)**

- Type: "Compare this with other methods in the field"
- Click Ask
Expected: StepIndicator shows reader→classify→planner, PlanApprovalBanner appears with plan steps, SSE disconnects. Click Approve → new SSE resumes → final answer.

- [ ] **Step 6: Test PDF highlight**

- In an answer with R0 badges, click an R0 badge
Expected: PDF switches to evidence page, highlight appears on matching text, EvidencePopover shows quote

- [ ] **Step 7: Test layout modes**

- Toggle layout between Dual/Chat/Paper
Expected: Layout switches accordingly, responsive on narrow viewport

- [ ] **Step 8: Run full test suite**

Run: `cd paper-reading-agent && python -m pytest tests/ -v && cd frontend && npx vitest run`
Expected: All backend + frontend tests PASS

- [ ] **Step 9: Commit any final fixes**

```bash
git add -A
git commit -m "chore: integration fixes and final adjustments"
```
