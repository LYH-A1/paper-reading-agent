import { useAppStore } from '@/store/appStore'
import styles from './Layout.module.css'

export default function SessionHistory() {
  const sessions = useAppStore((s) => s.sessions)

  return (
    <div className={styles.sessionHistory}>
      <h3>💬 Sessions</h3>
      {sessions.length === 0 && <p className={styles.empty}>No sessions yet</p>}
      <ul>
        {sessions.map((s) => (
          <li key={s.id}>
            <span className={styles.sessionTitle}>{s.title}</span>
            <span className={styles.sessionDate}>{new Date(s.createdAt).toLocaleDateString()}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
