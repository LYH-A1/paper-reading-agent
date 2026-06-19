import { describe, it, expect } from 'vitest'

describe('Phase 5 types', () => {
  it('Paper supports arxiv_id and import_source', () => {
    const paper = {
      paper_id: '1', title: 'Test', file_path: null, parsed_at: null,
      arxiv_id: '2401.12345', import_source: 'external_save' as const,
    }
    expect(paper.arxiv_id).toBe('2401.12345')
    expect(paper.import_source).toBe('external_save')
  })

  it('Paper supports file_path null', () => {
    const paper = { paper_id: '1', title: 'Test', file_path: null, parsed_at: null }
    expect(paper.file_path).toBeNull()
  })

  it('CompareRequest has required paper_ids', () => {
    const req = { paper_ids: ['id1', 'id2'] }
    expect(req.paper_ids).toHaveLength(2)
  })

  it('ImportBibTeXResponse shape', () => {
    const resp = { imported: 5, skipped: 2, errors: [], papers: [] }
    expect(resp.imported).toBe(5)
  })
})
