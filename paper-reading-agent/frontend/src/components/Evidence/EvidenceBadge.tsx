import type { Evidence } from '@/types'
import styles from './Evidence.module.css'

interface EvidenceBadgeProps {
  evidence: Evidence
  onClick?: (evidence: Evidence) => void
}

const LEVEL_STYLES: Record<string, { label: string; className: string }> = {
  R0: { label: 'R0', className: styles.badgeR0 },
  R1: { label: 'R1', className: styles.badgeR1 },
  R2: { label: 'R2', className: styles.badgeR2 },
}

export default function EvidenceBadge({ evidence, onClick }: EvidenceBadgeProps) {
  const { label, className } = LEVEL_STYLES[evidence.level] || LEVEL_STYLES.R2

  return (
    <span
      data-level={evidence.level}
      className={`${styles.badge} ${className}`}
      onClick={() => onClick?.(evidence)}
      title={`${label}: ${evidence.claim.slice(0, 80)}`}
    >
      {label}
    </span>
  )
}
