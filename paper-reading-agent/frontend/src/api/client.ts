import type { UploadResponse, PaperListResponse, ApproveRequest, ApproveResponse, CompareRequest, ImportBibTeXResponse, SaveExternalResponse, Thread } from '@/types'

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

export function getSSEUrl(params: { paper_id?: string; query?: string; thread_id?: string; session_id?: string }): string {
  const sp = new URLSearchParams()
  if (params.paper_id) sp.set('paper_id', params.paper_id)
  if (params.query) sp.set('query', params.query)
  if (params.thread_id) sp.set('thread_id', params.thread_id)
  if (params.session_id) sp.set('session_id', params.session_id)
  return `${BASE}/query?${sp.toString()}`
}

export interface Preferences {
  reranker: string
  top_k: number
  language: string
  embedding_model: string
}

export async function getPreferences(): Promise<Preferences> {
  const res = await fetch(`${BASE}/preferences`)
  if (!res.ok) throw new Error('Failed to fetch preferences')
  return res.json()
}

export async function putPreferences(prefs: Partial<Preferences>): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/preferences`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prefs),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Update failed' }))
    throw new Error(err.error || 'Failed to update preferences')
  }
  return res.json()
}

function slugify(text: string, maxLen: number = 50): string {
  return text
    .replace(/[^\w一-鿿-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, maxLen)
}

export function getReferencesExportUrl(paperId: string): string {
  return `${BASE}/papers/${encodeURIComponent(paperId)}/references/export?format=bib`
}

export async function exportReferences(paperId: string, paperTitle: string): Promise<void> {
  const res = await fetch(getReferencesExportUrl(paperId))
  if (!res.ok) return
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const slug = slugify(paperTitle || 'references')
  const date = new Date().toISOString().slice(0, 10)
  a.download = `${slug}-references-${date}.bib`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export async function comparePapers(req: CompareRequest): Promise<Response> {
  const res = await fetch(`${BASE}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Compare failed')
  }
  return res
}

export async function saveExternal(arxivId: string): Promise<SaveExternalResponse> {
  const res = await fetch(`${BASE}/papers/save-external`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arxiv_id: arxivId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Failed to save paper')
  }
  return res.json()
}

export async function getThreads(paperId: string): Promise<{ paper_id: string; threads: Thread[] }> {
  const res = await fetch(`${BASE}/papers/${encodeURIComponent(paperId)}/threads`)
  if (!res.ok) throw new Error('Failed to fetch threads')
  return res.json()
}

export async function importBibTeX(content: string): Promise<ImportBibTeXResponse> {
  const res = await fetch(`${BASE}/papers/import-bibtex`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bibtex_content: content }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Import failed')
  }
  return res.json()
}
