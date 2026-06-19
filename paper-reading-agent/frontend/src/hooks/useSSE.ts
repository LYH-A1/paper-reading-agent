import { useCallback, useRef } from 'react'
import { useChatStore } from '@/store/chatStore'
import { getSSEUrl } from '@/api/client'
import type { NodeEvent, HitlEvent, TokenEvent, DoneEvent } from '@/types'

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const store = useChatStore

  const connect = useCallback((url: string) => {
    // Close any existing connection
    eventSourceRef.current?.close()

    const es = new EventSource(url)
    eventSourceRef.current = es

    store.getState().setStatus('streaming')

    es.addEventListener('init', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      store.getState().setThreadId(data.thread_id)
      if (data.session_id) {
        store.getState().setSessionId(data.session_id)
      }
    })

    es.addEventListener('node', (e: MessageEvent) => {
      const data: NodeEvent = JSON.parse(e.data)
      store.getState().addStepNode(data.node)
    })

    es.addEventListener('token', (e: MessageEvent) => {
      const data: TokenEvent = JSON.parse(e.data)
      store.getState().appendToken(data.text)
    })

    es.addEventListener('hitl', (e: MessageEvent) => {
      const data: HitlEvent = JSON.parse(e.data)
      store.getState().setHitlPlan(data.plan)
      es.close()
    })

    es.addEventListener('done', (e: MessageEvent) => {
      const data: DoneEvent = JSON.parse(e.data)
      store.getState().finalizeAssistantMessage(
        data.answer,
        data.evidence_list,
        data.quality_score,
        data.trace,
        data.external_results,
      )
      es.close()
    })

    es.onerror = () => {
      // Only set error if not intentionally closed (readyState 2 = CLOSED)
      if (es.readyState !== EventSource.CLOSED) {
        store.getState().setError('Connection lost. Please try again.')
        es.close()
      }
    }
  }, [])

  const start = useCallback((params: { paper_id: string; query: string }) => {
    store.getState().reset()
    store.getState().setStatus('connecting')
    const url = getSSEUrl({ paper_id: params.paper_id, query: params.query })
    connect(url)
  }, [connect])

  const startResume = useCallback((threadId: string, sessionId?: string) => {
    store.getState().setStatus('connecting')
    store.getState().setHitlPlan(null)
    const url = getSSEUrl({ thread_id: threadId, session_id: sessionId })
    connect(url)
  }, [connect])

  const abort = useCallback(() => {
    eventSourceRef.current?.close()
    store.getState().setStatus('idle')
  }, [])

  return { start, startResume, abort }
}
