import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, fireEvent } from '@testing-library/react'
import React from 'react'
import { useChatStore } from '../../src/store/chatStore'
import { useAppStore } from '../../src/store/appStore'
import PlanApprovalBanner from '../../src/components/ChatPanel/PlanApprovalBanner'
import ChatPanel from '../../src/components/ChatPanel/ChatPanel'
import type { Plan } from '../../src/types'

// ---- Mock api/client (use vi.hoisted for factory references) ----
const mockGetSSEUrl = vi.hoisted(() =>
  vi.fn(
    (params: { paper_id?: string; query?: string; thread_id?: string }) => {
      const sp = new URLSearchParams()
      if (params.paper_id) sp.set('paper_id', params.paper_id)
      if (params.query) sp.set('query', params.query)
      if (params.thread_id) sp.set('thread_id', params.thread_id)
      return `/api/query?${sp.toString()}`
    },
  ),
)

vi.mock('../../src/api/client', () => ({
  getSSEUrl: mockGetSSEUrl,
  approvePlan: vi.fn(),
}))

// ---- Mock EventSource ----
class MockEventSource {
  static instances: MockEventSource[] = []
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  listeners: Record<string, ((e: { data: string }) => void)[]> = {}
  url: string
  readyState: number = 0
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (e: { data: string }) => void) {
    if (!this.listeners[type]) this.listeners[type] = []
    this.listeners[type].push(handler)
  }

  close() {
    this.readyState = MockEventSource.CLOSED
  }

  _fire(type: string, data: string) {
    const handlers = this.listeners[type] || []
    const event = { data }
    handlers.forEach((h) => h(event))
  }
}

vi.stubGlobal('EventSource', MockEventSource)

// ---- Helpers ----
const samplePlan: Plan = {
  steps: [
    { step: 1, action: 'read', tool: 'reader', target: 'paper' },
    { step: 2, action: 'classify', tool: 'classifier', target: 'claims' },
  ],
}

function setupBanner(overrides?: {
  onApprove?: () => void
  onReject?: () => void
  onEdit?: (feedback: string) => void
}) {
  const onApprove = overrides?.onApprove ?? vi.fn()
  const onReject = overrides?.onReject ?? vi.fn()
  const onEdit = overrides?.onEdit ?? vi.fn()
  const screen = render(
    <PlanApprovalBanner
      plan={samplePlan}
      onApprove={onApprove}
      onReject={onReject}
      onEdit={onEdit}
    />,
  )
  return { screen, onApprove, onReject, onEdit }
}

// ============================================
// PlanApprovalBanner
// ============================================
describe('PlanApprovalBanner', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
    useAppStore.getState().setPaper({
      paper_id: 'p1',
      title: 'Test Paper',
      file_path: '/papers/test.pdf',
      parsed_at: null,
    })
  })

  it('displays plan steps', () => {
    const { screen } = setupBanner()
    // # and 1 are in separate text nodes inside <span>, so use a function matcher
    expect(screen.getByText((content) => content.includes('#1'))).toBeTruthy()
    expect(screen.getByText((content) => content.includes('#2'))).toBeTruthy()
    // Verify step content is rendered
    expect(screen.getByText('Proposed Plan')).toBeTruthy()
  })

  it('calls onApprove when Approve is clicked', () => {
    useChatStore.getState().setStatus('awaiting_approval')
    const { screen, onApprove } = setupBanner()
    fireEvent.click(screen.getByText('Approve'))
    expect(onApprove).toHaveBeenCalledTimes(1)
  })

  it('calls onReject when Reject is clicked', () => {
    useChatStore.getState().setStatus('awaiting_approval')
    const { screen, onReject } = setupBanner()
    fireEvent.click(screen.getByText('Reject'))
    expect(onReject).toHaveBeenCalledTimes(1)
  })

  it('shows feedback textarea when Edit is clicked', () => {
    useChatStore.getState().setStatus('awaiting_approval')
    const { screen } = setupBanner()
    fireEvent.click(screen.getByText('Edit'))
    expect(screen.container.querySelector('textarea')).toBeTruthy()
  })

  it('calls onEdit with feedback text when Submit Feedback is clicked', () => {
    useChatStore.getState().setStatus('awaiting_approval')
    const { screen, onEdit } = setupBanner()
    fireEvent.click(screen.getByText('Edit'))
    const textarea = screen.container.querySelector('textarea')!
    fireEvent.change(textarea, { target: { value: 'Add more detail' } })
    fireEvent.click(screen.getByText('Submit Feedback'))
    expect(onEdit).toHaveBeenCalledWith('Add more detail')
  })
})

// ============================================
// useApproval (integrated via ChatPanel)
// ============================================
describe('useApproval integration', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
    MockEventSource.instances = []
    useAppStore.getState().setPaper({
      paper_id: 'p1',
      title: 'Test Paper',
      file_path: '/papers/test.pdf',
      parsed_at: null,
    })
  })

  it('approve calls approvePlan and starts resume', async () => {
    useChatStore.getState().setThreadId('thread-1')
    useChatStore.getState().setStatus('awaiting_approval')
    useChatStore.getState().setHitlPlan(samplePlan)

    const { approvePlan } = await import('../../src/api/client')
    const mockedApprove = vi.mocked(approvePlan)
    mockedApprove.mockResolvedValue({ status: 'resumed' })

    const screen = render(<ChatPanel />)

    fireEvent.click(screen.getByText('Approve'))

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(mockedApprove).toHaveBeenCalledWith({
      thread_id: 'thread-1',
      approved: true,
      feedback: undefined,
    })
    // startResume clears hitlPlan
    expect(useChatStore.getState().hitlPlan).toBeNull()
  })

  it('reject calls reset via ChatPanel', async () => {
    useChatStore.getState().setThreadId('thread-1')
    useChatStore.getState().setHitlPlan(samplePlan)

    const { approvePlan } = await import('../../src/api/client')
    const mockedApprove = vi.mocked(approvePlan)
    mockedApprove.mockResolvedValue({ status: 'cancelled' })

    const screen = render(<ChatPanel />)

    fireEvent.click(screen.getByText('Reject'))

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(mockedApprove).toHaveBeenCalledWith({
      thread_id: 'thread-1',
      approved: false,
    })
    // reset should clear everything
    const state = useChatStore.getState()
    expect(state.messages).toEqual([])
    expect(state.hitlPlan).toBeNull()
    expect(state.threadId).toBeNull()
    expect(state.status).toBe('idle')
  })
})

// ============================================
// ChatPanel two-segment flow
// ============================================
describe('ChatPanel two-segment SSE flow', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
    useAppStore.getState().clearPaper()
    MockEventSource.instances = []
    useAppStore.getState().setPaper({
      paper_id: 'p1',
      title: 'Test Paper',
      file_path: '/papers/test.pdf',
      parsed_at: null,
    })
  })

  it('sends user message and starts SSE on send', async () => {
    const screen = render(<ChatPanel />)
    const input = screen.container.querySelector('input')!
    fireEvent.change(input, { target: { value: 'What is this about?' } })
    fireEvent.click(screen.getByText('Ask'))

    const messages = useChatStore.getState().messages
    expect(messages.length).toBe(1)
    expect(messages[0].role).toBe('user')
    expect(messages[0].content).toBe('What is this about?')

    // EventSource should be created
    expect(MockEventSource.instances.length).toBe(1)
    expect(mockGetSSEUrl).toHaveBeenCalledWith(
      expect.objectContaining({ paper_id: 'p1', query: 'What is this about?' }),
    )
  })

  it('shows PlanApprovalBanner when status is awaiting_approval', async () => {
    const screen = render(<ChatPanel />)

    // Simulate hitl plan set
    act(() => {
      useChatStore.getState().setHitlPlan(samplePlan)
    })

    // PlanApprovalBanner should render
    expect(screen.getByText('Proposed Plan')).toBeTruthy()
    expect(screen.getByText('Approve')).toBeTruthy()
    expect(screen.getByText('Reject')).toBeTruthy()
    expect(screen.getByText('Edit')).toBeTruthy()
  })

  it('calls approvePlan and resumes SSE on approve', async () => {
    const { approvePlan } = await import('../../src/api/client')
    const mockedApprove = vi.mocked(approvePlan)
    mockedApprove.mockResolvedValue({ status: 'resumed' })

    useChatStore.getState().setThreadId('thread-1')
    useChatStore.getState().setHitlPlan(samplePlan)

    const screen = render(<ChatPanel />)

    fireEvent.click(screen.getByText('Approve'))

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(mockedApprove).toHaveBeenCalledWith({
      thread_id: 'thread-1',
      approved: true,
      feedback: undefined,
    })
    // Should create a new EventSource for resume with thread_id
    expect(mockGetSSEUrl).toHaveBeenCalledWith(
      expect.objectContaining({ thread_id: 'thread-1' }),
    )
  })
})
