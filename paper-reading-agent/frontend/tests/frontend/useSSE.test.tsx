import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render } from '@testing-library/react'
import React from 'react'
import { useChatStore } from '../../src/store/chatStore'
import { useSSE } from '../../src/hooks/useSSE'

// ---- Helper component that exercises the hook ----
function SSEHookWrapper({ onReady }: { onReady: (api: ReturnType<typeof useSSE>) => void }) {
  const api = useSSE()
  React.useEffect(() => { onReady(api) }, [api, onReady])
  return null
}

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

  // Helper to fire events in tests
  _fire(type: string, data: string) {
    const handlers = this.listeners[type] || []
    const event = { data }
    handlers.forEach(h => h(event))
  }
}

vi.stubGlobal('EventSource', MockEventSource)

describe('useSSE', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
    MockEventSource.instances = []
  })

  it('sets thread_id from init event on start', async () => {
    const apiRef: { current: ReturnType<typeof useSSE> | null } = { current: null }
    const onReady = (api: ReturnType<typeof useSSE>) => { apiRef.current = api }

    render(<SSEHookWrapper onReady={onReady} />)

    act(() => { apiRef.current!.start({ paper_id: 'p1', query: 'test query' }) })

    // The MockEventSource constructor fires nothing automatically; fire init manually
    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    act(() => { es._fire('init', '{"thread_id":"test-thread"}') })

    expect(useChatStore.getState().threadId).toBe('test-thread')
    expect(useChatStore.getState().status).toBe('streaming')
  })

  it('adds step nodes from node events', async () => {
    const apiRef: { current: ReturnType<typeof useSSE> | null } = { current: null }
    const onReady = (api: ReturnType<typeof useSSE>) => { apiRef.current = api }

    render(<SSEHookWrapper onReady={onReady} />)

    act(() => { apiRef.current!.start({ paper_id: 'p1', query: 'test' }) })

    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    act(() => { es._fire('node', '{"node":"reader"}') })
    act(() => { es._fire('node', '{"node":"classify"}') })

    expect(useChatStore.getState().stepNodes).toContain('reader')
    expect(useChatStore.getState().stepNodes).toContain('classify')
    expect(useChatStore.getState().currentStep).toBe('classify')
  })

  it('appends tokens from token events', async () => {
    const apiRef: { current: ReturnType<typeof useSSE> | null } = { current: null }
    const onReady = (api: ReturnType<typeof useSSE>) => { apiRef.current = api }

    render(<SSEHookWrapper onReady={onReady} />)

    act(() => { apiRef.current!.start({ paper_id: 'p1', query: 'test' }) })

    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    act(() => { es._fire('token', '{"text":"Hello"}') })
    act(() => { es._fire('token', '{"text":" world"}') })

    expect(useChatStore.getState().streamingTokens).toBe('Hello world')
  })

  it('sets hitlPlan on hitl event and closes EventSource', async () => {
    const apiRef: { current: ReturnType<typeof useSSE> | null } = { current: null }
    const onReady = (api: ReturnType<typeof useSSE>) => { apiRef.current = api }

    render(<SSEHookWrapper onReady={onReady} />)

    act(() => { apiRef.current!.start({ paper_id: 'p1', query: 'test' }) })

    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    const planData = { steps: [{ step: 1, action: 'read', tool: 'reader', target: 'paper' }] }
    act(() => { es._fire('hitl', JSON.stringify({ plan: planData })) })

    const state = useChatStore.getState()
    expect(state.hitlPlan).toEqual(planData)
    expect(state.status).toBe('awaiting_approval')
    expect(es.readyState).toBe(EventSource.CLOSED)
  })

  it('finalizes assistant message on done event and closes EventSource', async () => {
    const apiRef: { current: ReturnType<typeof useSSE> | null } = { current: null }
    const onReady = (api: ReturnType<typeof useSSE>) => { apiRef.current = api }

    render(<SSEHookWrapper onReady={onReady} />)

    act(() => { apiRef.current!.start({ paper_id: 'p1', query: 'test' }) })

    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    act(() => {
      es._fire('done', JSON.stringify({
        answer: 'Final answer',
        evidence_list: [{ evidence_id: 'e1', claim: 'claim1', level: 'R0', sentence_index: null, char_start: null, char_end: null, page: null, quote: null, section_heading: null, source_title: null, source_url: null, source_venue: null, source_year: null, reasoning: null, based_on_evidence_ids: [], confidence: 0.9 }],
        quality_score: { relevance: 0.9, consistency: 0.8, completeness: 0.7, total: 0.8 },
        trace: ['step1', 'step2'],
        followup_questions: [],
      }))
    })

    const state = useChatStore.getState()
    expect(state.messages.length).toBe(1)
    expect(state.messages[0].role).toBe('assistant')
    expect(state.messages[0].content).toBe('Final answer')
    expect(state.streamingTokens).toBe('')
    expect(state.status).toBe('complete')
    expect(es.readyState).toBe(EventSource.CLOSED)
  })

  it('abort closes EventSource and sets idle status', async () => {
    const apiRef: { current: ReturnType<typeof useSSE> | null } = { current: null }
    const onReady = (api: ReturnType<typeof useSSE>) => { apiRef.current = api }

    render(<SSEHookWrapper onReady={onReady} />)

    act(() => { apiRef.current!.start({ paper_id: 'p1', query: 'test' }) })

    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    act(() => { apiRef.current!.abort() })

    expect(es.readyState).toBe(EventSource.CLOSED)
    expect(useChatStore.getState().status).toBe('idle')
  })

  it('startResume connects with thread_id and clears hitlPlan', async () => {
    const apiRef: { current: ReturnType<typeof useSSE> | null } = { current: null }
    const onReady = (api: ReturnType<typeof useSSE>) => { apiRef.current = api }

    render(<SSEHookWrapper onReady={onReady} />)

    act(() => { apiRef.current!.startResume('existing-thread') })

    const es = MockEventSource.instances[MockEventSource.instances.length - 1]
    expect(es.url).toContain('thread_id=existing-thread')
    expect(useChatStore.getState().status).toBe('streaming')
    expect(useChatStore.getState().hitlPlan).toBeNull()
  })
})
