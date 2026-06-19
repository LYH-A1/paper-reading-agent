import { useState, useEffect, useRef, useMemo } from 'react'
import { listPapers, importBibTeX } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import { useCompareStore } from '@/store/compareStore'
import type { PaperListResponse } from '@/types'
import styles from './Layout.module.css'

const SOURCE_LABELS: Record<string, string> = {
  all: 'All',
  upload: 'Uploaded',
  bib_import: 'BibTeX Import',
  external_save: 'External Save',
}

export default function LibraryPanel() {
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const setPaper = useAppStore((s) => s.setPaper)
  const { isCompareMode, selectedPaperIds, toggleCompareMode, toggleSelection, clearSelection } = useCompareStore()
  const [importStatus, setImportStatus] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Phase 5.5: search/filter/sort — local state only
  // 预留：如果论文库 >200 条，考虑增加 100ms 防抖
  const [query, setQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [sort, setSort] = useState<'date' | 'title'>('date')

  useEffect(() => {
    listPapers().then(setPapers).catch(() => setPapers([]))
  }, [])

  const refreshPapers = () => {
    listPapers().then(setPapers).catch(() => {})
  }

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
      refreshPapers()
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

  // Phase 5.5: local filter + sort
  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim()
    return papers
      .filter(p => {
        if (q) {
          const inTitle = (p.title || '').toLowerCase().includes(q)
          const inAuthor = (p.authors || []).some(a => a.toLowerCase().includes(q))
          const inAbstract = (p.abstract_snippet || '').toLowerCase().includes(q)
          if (!inTitle && !inAuthor && !inAbstract) return false
        }
        if (sourceFilter !== 'all' && p.import_source !== sourceFilter) return false
        return true
      })
      .sort((a, b) => {
        if (sort === 'title') return (a.title || '').localeCompare(b.title || '')
        return new Date(b.parsed_at || 0).getTime() - new Date(a.parsed_at || 0).getTime()
      })
  }, [papers, query, sourceFilter, sort])

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

      {/* Phase 5.5: search bar */}
      <div className={styles.searchBar}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder="🔍 Search papers..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {/* Phase 5.5: filter + sort row */}
      <div className={styles.filterRow}>
        <label className={styles.filterLabel}>
          Source:
          <select
            className={styles.filterSelect}
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            {Object.entries(SOURCE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className={styles.filterLabel}>
          Sort:
          <select
            className={styles.filterSelect}
            value={sort}
            onChange={(e) => setSort(e.target.value as 'date' | 'title')}
          >
            <option value="date">Date (newest)</option>
            <option value="title">Title (A-Z)</option>
          </select>
        </label>
      </div>

      {isCompareMode && (
        <p className={styles.compareHint}>Select 2-5 papers to compare</p>
      )}
      {importStatus && (
        <p className={styles.importStatus}>{importStatus}</p>
      )}

      <p className={styles.paperCount}>
        {filtered.length} paper{filtered.length !== 1 ? 's' : ''}
        {query && ` matching "${query}"`}
      </p>

      {papers.length === 0 && <p className={styles.empty}>No papers uploaded</p>}
      {papers.length > 0 && filtered.length === 0 && (
        <p className={styles.empty}>No papers match your search</p>
      )}
      <ul>
        {filtered.map((p) => {
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
              <span className={styles.paperTitle}>{p.title}</span>
              {p.authors && p.authors.length > 0 && (
                <span className={styles.paperAuthors}>{p.authors.slice(0, 2).join(', ')}</span>
              )}
              {p.import_source && p.import_source !== 'upload' && (
                <span className={styles.sourceTag}>{SOURCE_LABELS[p.import_source] || p.import_source}</span>
              )}
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
