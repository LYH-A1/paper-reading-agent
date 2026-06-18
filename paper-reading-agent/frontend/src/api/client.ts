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
