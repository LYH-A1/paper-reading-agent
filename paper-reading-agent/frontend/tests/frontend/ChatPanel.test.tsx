import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useChatStore } from '../../src/store/chatStore'

// Import the ChatInput to test
import ChatInput from '../../src/components/ChatPanel/ChatInput'

describe('ChatInput', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
  })

  it('calls onSend with input value on submit', () => {
    let sent = ''
    const screen = render(<ChatInput onSend={(q) => { sent = q }} disabled={false} />)
    const input = screen.container.querySelector('input')!
    fireEvent.change(input, { target: { value: 'What is the method?' } })
    fireEvent.click(screen.getByText('Ask'))
    expect(sent).toBe('What is the method?')
  })

  it('disables button when disabled prop is true', () => {
    const screen = render(<ChatInput onSend={() => {}} disabled={true} />)
    const btn = screen.getByText('Ask') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})
