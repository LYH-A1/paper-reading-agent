import { useState } from 'react'
import { saveExternal } from '@/api/client'
import type { ExternalResult } from '@/types'
import styles from './ChatPanel.module.css'

interface ExternalRefCardProps {
  result: ExternalResult
  index: number
}

export default function ExternalRefCard({ result, index }: ExternalRefCardProps) {
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    const match = result.url.match(/\/abs\/(.+)$/)
    const arxivId = match ? match[1] : ''
    if (!arxivId) return

    setSaving(true)
    try {
      await saveExternal(arxivId)
      setSaved(true)
    } catch {
      // silently fail
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.externalRefCard}>
      <div className={styles.extRefHeader}>
        <a href={result.url} target="_blank" rel="noopener noreferrer" className={styles.extRefTitle}>
          [EXT-{index}] {result.title}
        </a>
        <button
          className={`${styles.saveBtn} ${saved ? styles.saved : ''}`}
          onClick={handleSave}
          disabled={saving || saved}
        >
          {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save →'}
        </button>
      </div>
      <p className={styles.extRefMeta}>
        {result.authors?.slice(0, 3).join(', ')} ({result.year || 'n.d.'})
        {result.citation_count != null && ` · Citations: ${result.citation_count}`}
      </p>
    </div>
  )
}
