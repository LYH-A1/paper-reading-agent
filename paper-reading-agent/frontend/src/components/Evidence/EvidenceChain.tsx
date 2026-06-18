import type { Evidence } from '@/types'
import styles from './Evidence.module.css'

interface EvidenceChainProps {
  evidence: Evidence
  allEvidence: Evidence[]
  depth: number
}

const MAX_DEPTH = 3

export default function EvidenceChain({ evidence, allEvidence, depth }: EvidenceChainProps) {
  if (depth > MAX_DEPTH || evidence.based_on_evidence_ids.length === 0) return null

  const children = evidence.based_on_evidence_ids
    .map((id) => allEvidence.find((e) => e.evidence_id === id))
    .filter(Boolean) as Evidence[]

  return (
    <ul className={styles.chainList}>
      {children.map((child) => (
        <li key={child.evidence_id} className={styles.chainItem}>
          <span
            className={`${styles.miniBadge} ${child.level === 'R0' ? styles.badgeR0 : child.level === 'R1' ? styles.badgeR1 : styles.badgeR2}`}
          >
            {child.level}
          </span>
          <span className={styles.chainClaim}>"{child.claim.slice(0, 100)}"</span>
          {child.based_on_evidence_ids.length > 0 && depth < MAX_DEPTH && (
            <EvidenceChain evidence={child} allEvidence={allEvidence} depth={depth + 1} />
          )}
        </li>
      ))}
    </ul>
  )
}
