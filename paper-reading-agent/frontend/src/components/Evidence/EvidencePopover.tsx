import { useState } from 'react'
import type { Evidence } from '@/types'
import { useChatStore } from '@/store/chatStore'
import EvidenceChain from './EvidenceChain'
import styles from './Evidence.module.css'

interface EvidencePopoverProps {
  evidence: Evidence
  allEvidence: Evidence[]
  onJumpToPDF: (evidence: Evidence) => void
  onClose: () => void
}

export default function EvidencePopover({ evidence, allEvidence, onJumpToPDF, onClose }: EvidencePopoverProps) {
  const [showChain, setShowChain] = useState(false)
  const externalResults = useChatStore((s) => s.externalResults)

  const extResult = evidence.level === 'R1' && evidence.external_result_id
    ? externalResults.find((r) => r.result_id === evidence.external_result_id)
    : undefined

  return (
    <div className={styles.popover}>
      <div className={styles.popoverHeader}>
        <span className={styles.popoverLevel}>
          {evidence.level} · {evidence.level === 'R0' ? 'Paper Source' : evidence.level === 'R1' ? 'External Source' : 'Inference'}
        </span>
        <button className={styles.closeBtn} onClick={onClose}>x</button>
      </div>

      <p className={styles.popoverClaim}>"{evidence.claim}"</p>

      {evidence.level === 'R0' && (
        <div className={styles.popoverDetails}>
          {evidence.quote && <p className={styles.quote}>"{evidence.quote}"</p>}
          {evidence.page != null && (
            <p>Page {evidence.page}{evidence.section_heading ? ` · ${evidence.section_heading}` : ''}</p>
          )}
          <button className={styles.jumpBtn} onClick={() => onJumpToPDF(evidence)}>
            Jump to PDF
          </button>
        </div>
      )}

      {evidence.level === 'R1' && (
        <div className={styles.popoverDetails}>
          {evidence.source_title && <p>{evidence.source_title}</p>}
          {evidence.source_url && (
            <a href={evidence.source_url} target="_blank" rel="noopener noreferrer">
              Open source
            </a>
          )}
          {extResult?.url && (
            <a href={extResult.url} target="_blank" rel="noopener noreferrer"
               style={{ display: 'block', marginTop: 4, color: '#1976d2' }}>
              View on arXiv ↗
            </a>
          )}
        </div>
      )}

      {evidence.level === 'R2' && (
        <div className={styles.popoverDetails}>
          {evidence.reasoning && <p className={styles.reasoning}>{evidence.reasoning}</p>}
          {evidence.based_on_evidence_ids.length > 0 && (
            <>
              <button className={styles.chainToggle} onClick={() => setShowChain(!showChain)}>
                {showChain ? 'v' : '>'} Based on {evidence.based_on_evidence_ids.length} evidence
              </button>
              {showChain && <EvidenceChain evidence={evidence} allEvidence={allEvidence} depth={1} />}
            </>
          )}
          <p>Confidence: {(evidence.confidence * 100).toFixed(0)}%</p>
        </div>
      )}

      {evidence.confidence !== undefined && evidence.confidence < 0.5 && (
        <div style={{
          marginTop: '8px',
          padding: '6px 8px',
          background: '#fff3e0',
          borderLeft: '3px solid #ed6c02',
          borderRadius: '4px',
          fontSize: '12px',
          color: '#666',
        }}>
          <strong>⚠️ Unverified citation</strong>
          <p style={{ margin: '4px 0 0 0' }}>
            This citation could not be verified in the source text.
            {evidence.quote && (
              <code style={{
                display: 'block',
                marginTop: '4px',
                padding: '4px',
                background: '#f5f5f5',
                borderRadius: '3px',
                fontSize: '11px',
                wordBreak: 'break-all',
              }}>
                &ldquo;{evidence.quote.slice(0, 150)}{evidence.quote.length > 150 ? '...' : ''}&rdquo;
              </code>
            )}
          </p>
        </div>
      )}
    </div>
  )
}
