import { describe, it, expect } from 'vitest'

describe('project scaffold', () => {
  it('type imports resolve', async () => {
    const mod = await import('../src/types/index')
    expect(mod).toBeDefined()
  })
})
