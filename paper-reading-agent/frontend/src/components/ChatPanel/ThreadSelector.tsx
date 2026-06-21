import type { Thread } from '@/types'
import styles from './ThreadSelector.module.css'

interface Props {
  threads: Thread[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}

export default function ThreadSelector({ threads, activeId, onSelect, onNew }: Props) {
  return (
    <div className={styles.container}>
      <select
        className={styles.select}
        value={activeId || ''}
        onChange={(e) => e.target.value && onSelect(e.target.value)}
      >
        {threads.length === 0 && (
          <option value="">No threads yet</option>
        )}
        {threads.map((t) => (
          <option key={t.session_id} value={t.session_id}>
            {t.title}
          </option>
        ))}
      </select>
      <button
        className={styles.newBtn}
        onClick={onNew}
        title="Start a new conversation thread"
      >
        +
      </button>
    </div>
  )
}
