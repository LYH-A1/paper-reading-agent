import type { Evidence } from '@/types'
import styles from './Evidence.module.css'

interface EvidenceBadgeProps {
  evidence: Evidence
  onClick?: (evidence: Evidence) => void
}

function ConfidenceIcon({ confidence }: { confidence: number }) {
  if (confidence === undefined || confidence === null) return null
  if (confidence >= 0.7) return <span title="Citation verified in source" style={{ color: '#2e7d32', fontSize: '10px', marginLeft: '2px' }}>✓</span>
  if (confidence >= 0.3) return <span title="Citation may not be accurate" style={{ color: '#ed6c02', fontSize: '10px', marginLeft: '2px' }}>⚠</span>
  return <span title="Citation not found in source" style={{ color: '#d32f2f', fontSize: '10px', marginLeft: '2px' }}>✗</span>
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
      <ConfidenceIcon confidence={evidence.confidence} />
    </span>
  )
}
