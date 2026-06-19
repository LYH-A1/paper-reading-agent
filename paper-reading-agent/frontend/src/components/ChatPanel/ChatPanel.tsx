import { useCallback } from 'react'
import StepIndicator from './StepIndicator'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import PlanApprovalBanner from './PlanApprovalBanner'
import { useChatStore } from '@/store/chatStore'
import { useAppStore } from '@/store/appStore'
import { useSSE } from '@/hooks/useSSE'
import { useApproval } from '@/hooks/useApproval'
import { exportReferences } from '@/api/client'
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
  const paper = useAppStore((s) => s.paper)

  const isStreaming = status === 'connecting' || status === 'streaming'
  const isAwaitingApproval = status === 'awaiting_approval'
  const showExport = status === 'complete' && currentSessionId

  const handleSend = useCallback(
    (query: string) => {
      if (!paper) return
      start({ paper_id: paper.paper_id, query })
      const store = useChatStore.getState()
      store.addMessage({
        id: `msg-${Date.now()}`,
        role: 'user',
        content: query,
      })
    },
    [paper, start],
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
      <MessageList />
      {isAwaitingApproval && hitlPlan && (
        <PlanApprovalBanner
          plan={hitlPlan}
          onApprove={handleApprove}
          onReject={handleReject}
          onEdit={handleEdit}
        />
      )}
      <ChatInput onSend={handleSend} disabled={isStreaming || isAwaitingApproval} />
    </div>
  )
}
