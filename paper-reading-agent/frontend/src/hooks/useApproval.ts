import { useCallback } from 'react'
import { useChatStore } from '@/store/chatStore'
import { useSSE } from '@/hooks/useSSE'
import { approvePlan } from '@/api/client'

export function useApproval() {
  const { startResume } = useSSE()
  const store = useChatStore

  const approve = useCallback(
    async (threadId: string, feedback?: string) => {
      try {
        await approvePlan({ thread_id: threadId, approved: true, feedback })
        startResume(threadId)
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Approval failed'
        store.getState().setError(message)
      }
    },
    [startResume, store],
  )

  const reject = useCallback(
    async (threadId: string) => {
      try {
        await approvePlan({ thread_id: threadId, approved: false })
        store.getState().reset()
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Rejection failed'
        store.getState().setError(message)
      }
    },
    [store],
  )

  return { approve, reject }
}
