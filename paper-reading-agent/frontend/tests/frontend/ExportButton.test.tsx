import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { useChatStore } from '../../src/store/chatStore'
import { useAppStore } from '../../src/store/appStore'

// Mock fetch for export
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  blob: () => Promise.resolve(new Blob(['# Session: test'])),
  headers: new Headers({ 'content-type': 'text/markdown' }),
})

// Mock URL.createObjectURL and revokeObjectURL
global.URL.createObjectURL = vi.fn(() => 'blob:test')
global.URL.revokeObjectURL = vi.fn()

import ChatPanel from '../../src/components/ChatPanel/ChatPanel'

describe('Export button', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
    useAppStore.setState({
      paper: { paper_id: 'p1', title: 'Test Paper', file_path: '', parsed_at: null },
      sessions: [],
      currentSession: null,
      layout: 'dual',
      sidebarOpen: false,
    })
    vi.clearAllMocks()
  })

  it('shows export button when status is complete and sessionId is set', () => {
    useChatStore.setState({ status: 'complete', currentSessionId: 'sess-001' })
    const screen = render(<ChatPanel />)
    const btn = screen.container.querySelector('[data-testid="export-btn"]')
    expect(btn).toBeTruthy()
  })

  it('hides export button when status is not complete', () => {
    useChatStore.setState({ status: 'streaming', currentSessionId: 'sess-001' })
    const screen = render(<ChatPanel />)
    const btn = screen.container.querySelector('[data-testid="export-btn"]')
    expect(btn).toBeNull()
  })
})
