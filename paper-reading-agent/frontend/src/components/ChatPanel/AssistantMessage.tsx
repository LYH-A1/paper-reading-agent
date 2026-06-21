import { useMemo } from 'react'
import EvidenceBadge from '@/components/Evidence/EvidenceBadge'
import type { Evidence, QualityScore } from '@/types'
import { useChatStore } from '@/store/chatStore'
import ExternalRefCard from './ExternalRefCard'
import ThinkingPanel from './ThinkingPanel'
import styles from './ChatPanel.module.css'

interface AssistantMessageProps {
  content: string
  evidenceList: Evidence[]
  qualityScore: QualityScore | null
  trace: string[]
}

/**
 * Splice EvidenceBadge components into answer text at char_start/char_end offsets.
 *
 * Edge cases handled:
 * - Empty evidence list -> returns plain answer text
 * - char_start/char_end out of bounds -> evidence is skipped
 * - Overlapping evidence -> later evidence is shifted past earlier end positions
 */
function renderAnswerWithBadges(answer: string, evidenceList: Evidence[]): React.ReactNode[] {
  if (evidenceList.length === 0) return [answer]

  // Sort evidence by char_start for left-to-right insertion
  const sorted = [...evidenceList]
    .filter((e) => e.char_start != null && e.char_end != null)
    .sort((a, b) => (a.char_start ?? 0) - (b.char_start ?? 0))

  if (sorted.length === 0) return [answer]

  const nodes: React.ReactNode[] = []
  let cursor = 0
  for (const ev of sorted) {
    const start = ev.char_start ?? 0
    const end = ev.char_end ?? 0

    // Skip out-of-bounds evidence
    if (start < 0 || end > answer.length || start >= end) continue

    // If this evidence overlaps with or is before the cursor, skip it
    if (start < cursor) continue

    // Add text before this evidence
    if (start > cursor) {
      nodes.push(answer.slice(cursor, start))
    }

    // Add the badge for this evidence
    nodes.push(<EvidenceBadge key={ev.evidence_id} evidence={ev} />)

    cursor = Math.max(cursor, end)
  }

  // Add remaining text
  if (cursor < answer.length) {
    nodes.push(answer.slice(cursor))
  }

  return nodes
}

export default function AssistantMessage({ content, evidenceList, qualityScore, trace }: AssistantMessageProps) {
  const r0Count = evidenceList.filter((e) => e.level === 'R0').length
  const r1Count = evidenceList.filter((e) => e.level === 'R1').length
  const r2Count = evidenceList.filter((e) => e.level === 'R2').length

  const renderedContent = useMemo(
    () => renderAnswerWithBadges(content, evidenceList),
    [content, evidenceList],
  )

  const externalResults = useChatStore((s) => s.externalResults)
  const thinkingEntries = useChatStore((s) => s.thinkingEntries)

  return (
    <div className={styles.assistantMessage}>
      <div className={styles.bubble}>
        {thinkingEntries.length > 0 && (
          <ThinkingPanel entries={thinkingEntries} />
        )}
        <div className={styles.answerContent}>{renderedContent}</div>
        {evidenceList.length > 0 && (
          <div className={styles.evidenceSummary}>
            {r0Count > 0 && <span className={styles.badgeR0}>R0x{r0Count}</span>}
            {r1Count > 0 && <span className={styles.badgeR1}>R1x{r1Count}</span>}
            {r2Count > 0 && <span className={styles.badgeR2}>R2x{r2Count}</span>}
            {qualityScore && <span className={styles.score}>Score: {qualityScore.total}/10</span>}
          </div>
        )}
        {/* Phase 5: External References */}
        {externalResults.length > 0 && (
          <div className={styles.externalRefs}>
            <hr />
            {externalResults.map((r, i) => (
              <ExternalRefCard key={r.result_id} result={r} index={i + 1} />
            ))}
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
