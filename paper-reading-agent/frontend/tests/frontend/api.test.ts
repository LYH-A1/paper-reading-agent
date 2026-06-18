import { describe, it, expect, vi } from 'vitest'

describe('API client', () => {
  it('uploadPaper sends FormData and returns response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ paper_id: 'p1', title: 'test.pdf', file_path: '/data/papers/test.pdf' }),
    })

    const { uploadPaper } = await import('../../src/api/client')
    const file = new File(['fake'], 'test.pdf', { type: 'application/pdf' })
    const result = await uploadPaper(file)

    expect(result.paper_id).toBe('p1')
    expect(fetch).toHaveBeenCalledWith('/api/upload', expect.objectContaining({ method: 'POST' }))
  })

  it('getSSEUrl builds correct query string', async () => {
    const { getSSEUrl } = await import('../../src/api/client')
    const url = getSSEUrl({ paper_id: 'p1', query: 'What is the method?' })
    expect(url).toContain('paper_id=p1')
    expect(url).toContain('query=What+is+the+method')
  })
})
