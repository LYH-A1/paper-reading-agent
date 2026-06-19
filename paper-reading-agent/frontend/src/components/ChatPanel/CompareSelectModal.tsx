import { useState, useEffect } from 'react'
import { useCompareStore } from '@/store/compareStore'
import { useChatStore } from '@/store/chatStore'
import { listPapers, comparePapers } from '@/api/client'
import type { PaperListResponse } from '@/types'
import styles from './ChatPanel.module.css'

interface CompareSelectModalProps {
  onClose: () => void
}

const ASPECT_OPTIONS = [
  { key: 'method', label: 'Method' },
  { key: 'experiment', label: 'Experiment' },
  { key: 'contribution', label: 'Contribution' },
  { key: 'limitation', label: 'Limitation' },
]

export default function CompareSelectModal({ onClose }: CompareSelectModalProps) {
  const { selectedPaperIds, clearSelection } = useCompareStore()
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const [selectedAspects, setSelectedAspects] = useState<string[]>(['method', 'contribution'])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const { setStatus, addMessage, addStepNode, appendToken, finalizeAssistantMessage, setExternalResults, reset } = useChatStore()

  useEffect(() => {
    listPapers().then((all) => {
      setPapers(all.filter((p) => selectedPaperIds.includes(p.paper_id)))
    }).catch(() => setPapers([]))
  }, [selectedPaperIds])

  const toggleAspect = (key: string) => {
    setSelectedAspects((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }

  const handleCompare = async () => {
    setLoading(true)
    reset()
    setStatus('streaming')

    const paperTitles = papers.map((p) => p.title).join(', ')
    addMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: `Comparing ${papers.length} papers: ${paperTitles}`,
      evidenceList: [],
      qualityScore: null,
      trace: [],
    })

    try {
      const response = await comparePapers({
        paper_ids: selectedPaperIds,
        aspects: selectedAspects.length > 0 ? selectedAspects : undefined,
        query: query || undefined,
      })

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) continue
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.event === 'node') {
                addStepNode(data.node)
              } else if (data.event === 'token') {
                appendToken(data.text)
              } else if (data.event === 'done') {
                finalizeAssistantMessage(
                  data.answer,
                  data.evidence_list || [],
                  data.quality_score || null,
                  data.trace || [],
                )
                setExternalResults([])
              }
            } catch { /* skip non-JSON */ }
          }
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Compare failed'
      setStatus('error')
      appendToken(`\n\n⚠️ ${msg}`)
    }

    clearSelection()
    onClose()
  }

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>Compare Papers</h3>

        <div className={styles.modalSection}>
          <p className={styles.label}>Selected:</p>
          <ul className={styles.paperList}>
            {papers.map((p) => (
              <li key={p.paper_id}>📄 {p.title}</li>
            ))}
          </ul>
        </div>

        <div className={styles.modalSection}>
          <p className={styles.label}>Aspects (optional):</p>
          <div className={styles.aspectGrid}>
            {ASPECT_OPTIONS.map((opt) => (
              <label key={opt.key} className={styles.aspectLabel}>
                <input
                  type="checkbox"
                  checked={selectedAspects.includes(opt.key)}
                  onChange={() => toggleAspect(opt.key)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div className={styles.modalSection}>
          <p className={styles.label}>Focus (optional):</p>
          <input
            type="text"
            className={styles.focusInput}
            placeholder="e.g. focus on training efficiency"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className={styles.modalActions}>
          <button onClick={onClose} disabled={loading}>Cancel</button>
          <button onClick={handleCompare} disabled={loading} className={styles.primaryBtn}>
            {loading ? 'Comparing...' : 'Compare →'}
          </button>
        </div>
      </div>
    </div>
  )
}
