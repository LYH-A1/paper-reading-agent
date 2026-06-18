import StepIndicator from './StepIndicator'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import { useChatStore } from '@/store/chatStore'
import styles from './ChatPanel.module.css'

interface ChatPanelProps {
  onSend: (query: string) => void
}

export default function ChatPanel({ onSend }: ChatPanelProps) {
  const status = useChatStore((s) => s.status)
  const isStreaming = status === 'connecting' || status === 'streaming'

  return (
    <div className={styles.panel}>
      <StepIndicator />
      <MessageList />
      <ChatInput onSend={onSend} disabled={isStreaming} />
    </div>
  )
}
