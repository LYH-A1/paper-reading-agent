import { useCallback } from 'react'
import StepIndicator from './StepIndicator'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import PlanApprovalBanner from './PlanApprovalBanner'
import { useChatStore } from '@/store/chatStore'
import { useAppStore } from '@/store/appStore'
import { useSSE } from '@/hooks/useSSE'
import { useApproval } from '@/hooks/useApproval'
import styles from './ChatPanel.module.css'

export default function ChatPanel() {
  const { start, abort } = useSSE()
  const { approve, reject } = useApproval()
  const status = useChatStore((s) => s.status)
  const hitlPlan = useChatStore((s) => s.hitlPlan)
  const threadId = useChatStore((s) => s.threadId)
  const paper = useAppStore((s) => s.paper)

  const isStreaming = status === 'connecting' || status === 'streaming'
  const isAwaitingApproval = status === 'awaiting_approval'

  const handleSend = useCallback(
    (query: string) => {
      if (!paper) return

      // Start SSE first (calls reset internally, clearing previous state)
      start({ paper_id: paper.paper_id, query })

      // Then add user message so it survives the reset
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

  return (
    <div className={styles.panel}>
      <StepIndicator />
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
