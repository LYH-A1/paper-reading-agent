import { useState, useEffect, useRef } from 'react'
import { listPapers, importBibTeX } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import { useCompareStore } from '@/store/compareStore'
import type { PaperListResponse } from '@/types'
import styles from './Layout.module.css'

export default function LibraryPanel() {
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const setPaper = useAppStore((s) => s.setPaper)
  const { isCompareMode, selectedPaperIds, toggleCompareMode, toggleSelection, clearSelection } = useCompareStore()
  const [importStatus, setImportStatus] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listPapers().then(setPapers).catch(() => setPapers([]))
  }, [])

  const handleImportClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      setImportStatus('Importing...')
      const content = await file.text()
      const result = await importBibTeX(content)
      const parts: string[] = []
      if (result.imported > 0) parts.push(`✅ Imported ${result.imported} papers`)
      if (result.skipped > 0) parts.push(`⚠️ ${result.skipped} skipped`)
      if (result.errors.length > 0) parts.push(`❌ ${result.errors.length} errors`)
      setImportStatus(parts.join(' · '))
      listPapers().then(setPapers).catch(() => {})
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Import failed'
      setImportStatus(`❌ ${msg}`)
    }

    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handlePaperClick = (p: PaperListResponse) => {
    if (isCompareMode) {
      toggleSelection(p.paper_id)
    } else {
      setPaper({
        paper_id: p.paper_id,
        title: p.title,
        file_path: '',
        parsed_at: p.parsed_at,
      })
    }
  }

  const canCompare = selectedPaperIds.length >= 2

  return (
    <div className={styles.libraryPanel}>
      <div className={styles.libraryHeader}>
        <h3>📚 Paper Library</h3>
        <div className={styles.libraryActions}>
          <button
            className={`${styles.compareBtn} ${isCompareMode ? styles.active : ''}`}
            onClick={toggleCompareMode}
          >
            {isCompareMode ? 'Exit Compare' : 'Compare'}
          </button>
          <button className={styles.importBtn} onClick={handleImportClick}>
            Import BibTeX
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".bib"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
        </div>
      </div>

      {isCompareMode && (
        <p className={styles.compareHint}>Select 2-5 papers to compare</p>
      )}
      {importStatus && (
        <p className={styles.importStatus}>{importStatus}</p>
      )}

      {papers.length === 0 && <p className={styles.empty}>No papers uploaded</p>}
      <ul>
        {papers.map((p) => {
          const isSelected = selectedPaperIds.includes(p.paper_id)
          return (
            <li
              key={p.paper_id}
              className={`${isCompareMode ? styles.compareItem : ''} ${isSelected ? styles.selected : ''}`}
              onClick={() => handlePaperClick(p)}
            >
              {isCompareMode && (
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleSelection(p.paper_id)}
                  className={styles.checkbox}
                />
              )}
              {p.title}
            </li>
          )
        })}
      </ul>

      {isCompareMode && canCompare && (
        <button className={styles.compareFab}>
          Compare Selected ({selectedPaperIds.length})
        </button>
      )}
    </div>
  )
}
