// ---- Thread ----
export interface Thread {
  session_id: string
  title: string
  created_at: string
}

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
  external_result_id: string | null
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

export interface ThinkingEvent {
  event: 'thinking'
  node: string   // 'planner' | 'generate' | 'reviewer'
  text: string    // human-readable reasoning snippet
}

// ---- Reranker ----
export interface RerankerSummary {
  input_chunks: number
  output_chunks: number
  model: string | null
}

// ---- External Search ----
export interface ExternalResult {
  result_id: string
  title: string
  authors: string[]
  abstract: string
  year: number | null
  url: string
  source: string
  citation_count: number | null
}

export interface DoneEvent {
  event: 'done'
  answer: string
  session_id?: string
  quality_score: QualityScore
  evidence_list: Evidence[]
  trace: string[]
  followup_questions: string[]
  reranker_used: string
  reranker_summary: RerankerSummary
  external_results: ExternalResult[]
}

export type SSEEvent = InitEvent | NodeEvent | HitlEvent | TokenEvent | ThinkingEvent | DoneEvent

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
  file_path: string | null          // Changed: was string
  parsed_at: string | null
  arxiv_id?: string | null          // New
  arxiv_pdf_url?: string | null     // New
  import_source?: string            // New: "upload" | "bib_import" | "external_save"
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
  authors: string[]
  abstract_snippet: string
  import_source: string          // "upload" | "bib_import" | "external_save"
  arxiv_id: string | null
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

// ---- Compare / Import / Save External ----
export interface CompareRequest {
  paper_ids: string[]
  aspects?: string[]
  query?: string
}

export interface ImportBibTeXResponse {
  imported: number
  skipped: number
  errors: Array<{ line: number; error: string }>
  papers: Array<{ paper_id: string; title: string; import_source: string }>
}

export interface SaveExternalResponse {
  paper_id: string
  title: string
  already_saved: boolean
}
