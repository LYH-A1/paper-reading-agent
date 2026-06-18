import { describe, it, expect, beforeEach } from 'vitest'

describe('appStore persist', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('persists layout and sidebarOpen to localStorage', async () => {
    const { useAppStore } = await import('../../src/store/appStore')
    useAppStore.getState().setLayout('chat')
    useAppStore.getState().toggleSidebar()

    const stored = localStorage.getItem('paper-reading-agent-ui')
    expect(stored).toBeTruthy()
    const parsed = JSON.parse(stored!)
    expect(parsed.state.layout).toBe('chat')
    expect(parsed.state.sidebarOpen).toBe(true)
  })
})
