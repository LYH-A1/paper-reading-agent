import { useState } from 'react'
import styles from './ChatPanel.module.css'

interface ChatInputProps {
  onSend: (query: string) => void
  disabled: boolean
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (trimmed && !disabled) {
      onSend(trimmed)
      setValue('')
    }
  }

  return (
    <div className={styles.chatInput}>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
        placeholder="Ask a question about the paper..."
        disabled={disabled}
      />
      <button onClick={handleSubmit} disabled={disabled || !value.trim()}>Ask</button>
    </div>
  )
}
