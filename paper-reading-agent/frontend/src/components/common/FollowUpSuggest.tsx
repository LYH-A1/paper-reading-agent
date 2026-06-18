import styles from '@/components/Layout/Layout.module.css'

interface FollowUpSuggestProps {
  questions: string[]
  onSelect: (question: string) => void
}

export default function FollowUpSuggest({ questions, onSelect }: FollowUpSuggestProps) {
  if (!questions || questions.length === 0) return null
  return (
    <div className={styles.followUp}>
      <h4>Follow-up questions:</h4>
      {questions.map((q, i) => (
        <button key={i} onClick={() => onSelect(q)}>{q}</button>
      ))}
    </div>
  )
}
