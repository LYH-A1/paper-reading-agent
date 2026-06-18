import styles from './ChatPanel.module.css'

export default function UserMessage({ content }: { content: string }) {
  return (
    <div className={styles.userMessage}>
      <div className={styles.bubble}>{content}</div>
    </div>
  )
}
