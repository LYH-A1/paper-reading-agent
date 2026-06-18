import { useState, useEffect } from 'react'
import { listPapers } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import type { PaperListResponse } from '@/types'
import styles from './Layout.module.css'

export default function LibraryPanel() {
  const [papers, setPapers] = useState<PaperListResponse[]>([])
  const setPaper = useAppStore((s) => s.setPaper)

  useEffect(() => {
    listPapers().then(setPapers).catch(() => setPapers([]))
  }, [])

  return (
    <div className={styles.libraryPanel}>
      <h3>📚 Paper Library</h3>
      {papers.length === 0 && <p className={styles.empty}>No papers uploaded</p>}
      <ul>
        {papers.map((p) => (
          <li key={p.paper_id} onClick={() => setPaper({
            paper_id: p.paper_id,
            title: p.title,
            file_path: '',
            parsed_at: p.parsed_at,
          })}>
            {p.title}
          </li>
        ))}
      </ul>
    </div>
  )
}
