import styles from './ChatPanel.module.css'
import type { Evidence, QualityScore } from '@/types'

interface AssistantMessageProps {
  content: string
  evidenceList: Evidence[]
  qualityScore: QualityScore | null
  trace: string[]
}

export default function AssistantMessage({ content, evidenceList, qualityScore, trace }: AssistantMessageProps) {
  // EvidenceBadge placeholder — full implementation in Task 6
  const r0Count = evidenceList.filter((e) => e.level === 'R0').length
  const r1Count = evidenceList.filter((e) => e.level === 'R1').length
  const r2Count = evidenceList.filter((e) => e.level === 'R2').length

  return (
    <div className={styles.assistantMessage}>
      <div className={styles.bubble}>
        <div className={styles.answerContent}>{content}</div>
        {evidenceList.length > 0 && (
          <div className={styles.evidenceSummary}>
            {r0Count > 0 && <span className={styles.badgeR0}>R0x{r0Count}</span>}
            {r1Count > 0 && <span className={styles.badgeR1}>R1x{r1Count}</span>}
            {r2Count > 0 && <span className={styles.badgeR2}>R2x{r2Count}</span>}
            {qualityScore && <span className={styles.score}>Score: {qualityScore.total}/10</span>}
          </div>
        )}
        {trace.length > 0 && (
          <details className={styles.trace}>
            <summary>Trace ({trace.length} steps)</summary>
            <code>{trace.join(' → ')}</code>
          </details>
        )}
      </div>
    </div>
  )
}
