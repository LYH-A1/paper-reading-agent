import { useState } from 'react'
import { useChatStore } from '@/store/chatStore'
import type { Plan } from '@/types'
import styles from './PlanApprovalBanner.module.css'

interface PlanApprovalBannerProps {
  plan: Plan
  onApprove: () => void
  onReject: () => void
  onEdit: (feedback: string) => void
}

export default function PlanApprovalBanner({
  plan,
  onApprove,
  onReject,
  onEdit,
}: PlanApprovalBannerProps) {
  const status = useChatStore((s) => s.status)
  const [editing, setEditing] = useState(false)
  const [feedback, setFeedback] = useState('')

  const isWaiting = status === 'awaiting_approval'

  const handleEdit = () => {
    if (editing && feedback.trim()) {
      onEdit(feedback.trim())
      setFeedback('')
      setEditing(false)
    }
  }

  return (
    <div className={styles.banner}>
      <div className={styles.heading}>Proposed Plan</div>
      <div className={styles.steps}>
        {plan.steps.map((step) => (
          <div key={step.step} className={styles.step}>
            <span className={styles.stepNum}>#{step.step}</span>
            {step.action} ({step.tool} → {step.target})
          </div>
        ))}
      </div>
      {editing && (
        <textarea
          className={styles.feedbackArea}
          placeholder="Enter feedback to refine the plan..."
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
      )}
      <div className={styles.actions}>
        {isWaiting && (
          <>
            <button className={styles.approveBtn} onClick={onApprove}>
              Approve
            </button>
            <button className={styles.rejectBtn} onClick={onReject}>
              Reject
            </button>
            {editing ? (
              <button
                className={styles.editBtn}
                onClick={handleEdit}
                disabled={!feedback.trim()}
              >
                Submit Feedback
              </button>
            ) : (
              <button
                className={styles.editBtn}
                onClick={() => setEditing(true)}
              >
                Edit
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
