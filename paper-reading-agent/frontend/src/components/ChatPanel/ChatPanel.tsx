import { useCallback, useEffect } from 'react'
import StepIndicator from './StepIndicator'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import PlanApprovalBanner from './PlanApprovalBanner'
import ThreadSelector from './ThreadSelector'
import { useChatStore } from '@/store/chatStore'
import { useAppStore } from '@/store/appStore'
import { useSSE } from '@/hooks/useSSE'
import { useApproval } from '@/hooks/useApproval'
import { exportReferences, getThreads } from '@/api/client'
import type { Thread } from '@/types'
import styles from './ChatPanel.module.css'

function slugify(text: string, maxLen: number = 50): string {
  return text
    .replace(/[^\w一-鿿-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, maxLen)
}

export default function ChatPanel() {
  const { start } = useSSE()
  const { approve, reject } = useApproval()
  const status = useChatStore((s) => s.status)
  const hitlPlan = useChatStore((s) => s.hitlPlan)
  const currentSessionId = useChatStore((s) => s.currentSessionId)
  const threads = useChatStore((s) => s.threads)
  const activeThreadId = useChatStore((s) => s.activeThreadId)
  const setThreads = useChatStore((s) => s.setThreads)
  const setActiveThread = useChatStore((s) => s.setActiveThread)
  const comparePaperIds = useChatStore((s) => s.comparePaperIds)
  const compareReport = useChatStore((s) => s.compareReport)
  const resetStore = useChatStore((s) => s.reset)
  const paper = useAppStore((s) => s.paper)

  const isStreaming = status === 'connecting' || status === 'streaming'
  const isAwaitingApproval = status === 'awaiting_approval'
  const showExport = status === 'complete' && currentSessionId

  useEffect(() => {
    if (paper?.paper_id) {
      getThreads(paper.paper_id).then((data: { threads: Thread[] }) => {
        setThreads(data.threads)
      }).catch(() => {
        // Silently fail — threads are non-critical
      })
    }
  }, [paper?.paper_id])

  const handleCompareFollowup = useCallback(async (query: string, store: ReturnType<typeof useChatStore.getState>) => {
    store.setStatus('streaming')
    store.addMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      evidenceList: [],
      qualityScore: null,
      trace: [],
    })

    try {
      const res = await fetch('/api/compare/followup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paper_ids: store.comparePaperIds,
          question: query,
          comparison_report: store.compareReport,
        }),
      })

      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) continue
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.event === 'token') {
                store.appendToken(data.text)
              } else if (data.event === 'done') {
                store.finalizeAssistantMessage(
                  data.answer,
                  data.evidence_list || [],
                  data.quality_score || null,
                  data.trace || [],
                )
              }
            } catch { /* skip */ }
          }
        }
      }
    } catch (err) {
      store.setStatus('error')
      store.appendToken(`\n\n⚠️ ${err instanceof Error ? err.message : 'Failed'}`)
    }
  }, [])

  const handleSend = useCallback(
    (query: string) => {
      if (!paper) return
      const store = useChatStore.getState()

      // Check if we're in compare followup mode
      if (store.compareReport) {
        store.addMessage({
          id: `msg-${Date.now()}`,
          role: 'user',
          content: query,
        })
        handleCompareFollowup(query, store)
        return
      }

      start({ paper_id: paper.paper_id, query })
      store.addMessage({
        id: `msg-${Date.now()}`,
        role: 'user',
        content: query,
      })
    },
    [paper, start, handleCompareFollowup],
  )

  const handleApprove = useCallback(() => {
    const state = useChatStore.getState()
    if (state.threadId) {
      approve(state.threadId)
    }
  }, [approve])

  const handleReject = useCallback(() => {
    const state = useChatStore.getState()
    if (state.threadId) {
      reject(state.threadId)
    }
  }, [reject])

  const handleEdit = useCallback(
    (feedback: string) => {
      const state = useChatStore.getState()
      if (state.threadId) {
        approve(state.threadId, feedback)
      }
    },
    [approve],
  )

  const handleExport = useCallback(
    async (format: 'md' | 'json') => {
      if (!currentSessionId) return
      const res = await fetch(`/api/sessions/${currentSessionId}/export?format=${format}`)
      if (!res.ok) return
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const titleSlug = slugify(paper?.title || 'export')
      const date = new Date().toISOString().slice(0, 10)
      a.download = `session-${titleSlug}-${date}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    },
    [currentSessionId, paper?.title],
  )

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <StepIndicator />
        <div className={styles.exportGroup}>
          {showExport && (
            <>
              <button
                className={styles.exportBtn}
                onClick={() => handleExport('md')}
                data-testid="export-btn"
                title="Export as Markdown"
              >
                ⬇ .md
              </button>
              <button
                className={styles.exportBtn}
                onClick={() => handleExport('json')}
                title="Export as JSON"
              >
                .json
              </button>
            </>
          )}
          {paper && (
            <button
              className={styles.exportBtn}
              onClick={() => exportReferences(paper.paper_id, paper.title)}
              data-testid="export-bibtex-btn"
              title="Export all references from this paper in BibTeX format"
            >
              .bib
            </button>
          )}
        </div>
      </div>
      <ThreadSelector
        threads={threads}
        activeId={activeThreadId}
        onSelect={(id) => {
          setActiveThread(id)
          const store = useChatStore.getState()
          store.reset()
          // SSE with thread_id=id to resume this thread
        }}
        onNew={() => {
          const store = useChatStore.getState()
          store.reset()
          setActiveThread(null)
        }}
      />
      <MessageList />
      {isAwaitingApproval && hitlPlan && (
        <PlanApprovalBanner
          plan={hitlPlan}
          onApprove={handleApprove}
          onReject={handleReject}
          onEdit={handleEdit}
        />
      )}
      {compareReport && (
        <div className={styles.compareModeBar}>
          <span>📊 Comparing {comparePaperIds.length} papers — ask a follow-up</span>
          <button onClick={() => { resetStore() }} className={styles.compareModeClose}>✕</button>
        </div>
      )}
      <ChatInput onSend={handleSend} disabled={isStreaming || isAwaitingApproval} />
    </div>
  )
}
