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
  session_id: string
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
