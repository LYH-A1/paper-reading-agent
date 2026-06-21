import { useState } from 'react'
import styles from './ThinkingPanel.module.css'

interface ThinkingEntry {
  event: 'thinking'
  node: string
  text: string
}

interface ThinkingPanelProps {
  entries: ThinkingEntry[]
}

const NODE_LABELS: Record<string, string> = {
  planner: '📋 Planning',
  generate: '✍️ Writing',
  reviewer: '🔍 Reviewing',
}

export default function ThinkingPanel({ entries }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(true)

  if (entries.length === 0) return null

  return (
    <div className={styles.container}>
      <button
        className={styles.toggle}
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? '▾' : '▸'} Reasoning ({entries.length} step{entries.length > 1 ? 's' : ''})
      </button>
      {expanded && (
        <div className={styles.entries}>
          {entries.map((e, i) => (
            <div key={i} className={styles.entry}>
              <span className={styles.nodeLabel}>{NODE_LABELS[e.node] || e.node}</span>
              <span className={styles.text}>{e.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
