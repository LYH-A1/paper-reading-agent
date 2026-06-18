import styles from '@/components/Layout/Layout.module.css'

export default function TracePanel({ trace }: { trace: string[] }) {
  if (!trace || trace.length === 0) return null
  return (
    <details className={styles.tracePanel}>
      <summary>Trace ({trace.length} steps)</summary>
      <code>{trace.join(' → ')}</code>
    </details>
  )
}
