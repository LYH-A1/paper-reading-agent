import { useChatStore } from '@/store/chatStore'
import UserMessage from './UserMessage'
import AssistantMessage from './AssistantMessage'
import styles from './ChatPanel.module.css'

export default function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const streamingTokens = useChatStore((s) => s.streamingTokens)

  return (
    <div className={styles.messageList}>
      {messages.map((msg) =>
        msg.role === 'user' ? (
          <UserMessage key={msg.id} content={msg.content} />
        ) : (
          <AssistantMessage
            key={msg.id}
            content={msg.content}
            evidenceList={msg.evidenceList}
            qualityScore={msg.qualityScore}
            trace={msg.trace}
          />
        )
      )}
      {streamingTokens && (
        <div className={styles.assistantMessage}>
          <div className={styles.bubble}>{streamingTokens}</div>
        </div>
      )}
    </div>
  )
}
