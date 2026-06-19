import { describe, it, expect, beforeEach } from 'vitest'
import { useCompareStore } from '@/store/compareStore'

describe('compareStore', () => {
  beforeEach(() => {
    useCompareStore.setState({ isCompareMode: false, selectedPaperIds: [] })
  })

  it('starts with empty selection', () => {
    const state = useCompareStore.getState()
    expect(state.isCompareMode).toBe(false)
    expect(state.selectedPaperIds).toEqual([])
  })

  it('toggleCompareMode enters and exits', () => {
    useCompareStore.getState().toggleCompareMode()
    expect(useCompareStore.getState().isCompareMode).toBe(true)
    useCompareStore.getState().toggleCompareMode()
    expect(useCompareStore.getState().isCompareMode).toBe(false)
  })

  it('toggleCompareMode clears selection on exit', () => {
    const store = useCompareStore.getState()
    store.toggleCompareMode()
    store.toggleSelection('id-1')
    expect(useCompareStore.getState().selectedPaperIds).toContain('id-1')
    store.toggleCompareMode()
    expect(useCompareStore.getState().selectedPaperIds).toEqual([])
  })

  it('toggleSelection adds and removes', () => {
    useCompareStore.getState().toggleCompareMode()
    const store = useCompareStore.getState()
    store.toggleSelection('id-1')
    expect(useCompareStore.getState().selectedPaperIds).toEqual(['id-1'])
    store.toggleSelection('id-2')
    expect(useCompareStore.getState().selectedPaperIds).toEqual(['id-1', 'id-2'])
    store.toggleSelection('id-1')
    expect(useCompareStore.getState().selectedPaperIds).toEqual(['id-2'])
  })

  it('toggleSelection caps at 5', () => {
    useCompareStore.getState().toggleCompareMode()
    const store = useCompareStore.getState()
    for (let i = 1; i <= 6; i++) {
      store.toggleSelection(`id-${i}`)
    }
    expect(useCompareStore.getState().selectedPaperIds.length).toBe(5)
  })

  it('clearSelection resets everything', () => {
    useCompareStore.getState().toggleCompareMode()
    const store = useCompareStore.getState()
    store.toggleSelection('id-1')
    store.toggleSelection('id-2')
    store.clearSelection()
    expect(useCompareStore.getState().isCompareMode).toBe(false)
    expect(useCompareStore.getState().selectedPaperIds).toEqual([])
  })
})
