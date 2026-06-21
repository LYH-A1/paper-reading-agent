import { create } from 'zustand'
import type { Message, Plan, Evidence, QualityScore, ExternalResult, ThinkingEvent } from '@/types'

export type ChatStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'awaiting_approval'
  | 'complete'
  | 'error'

interface ChatState {
  messages: Message[]
  streamingTokens: string
  stepNodes: string[]
  currentStep: string | null
  hitlPlan: Plan | null
  threadId: string | null
  currentSessionId: string | null
  status: ChatStatus
  errorMessage: string | null
  externalResults: ExternalResult[]
  thinkingEntries: ThinkingEvent[]

  appendToken: (token: string) => void
  addStepNode: (node: string) => void
  setCurrentStep: (step: string) => void
  setHitlPlan: (plan: Plan | null) => void
  setThreadId: (id: string) => void
  setSessionId: (id: string) => void
  setStatus: (status: ChatStatus) => void
  setError: (msg: string) => void
  addMessage: (msg: Message) => void
  finalizeAssistantMessage: (content: string, evidenceList: Evidence[], qualityScore: QualityScore | null, trace: string[], externalResults?: ExternalResult[]) => void
  setExternalResults: (results: ExternalResult[]) => void
  appendThinking: (node: string, text: string) => void
  reset: () => void
}

let nextId = 1
const genId = () => `msg-${nextId++}`

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streamingTokens: '',
  stepNodes: [],
  currentStep: null,
  hitlPlan: null,
  threadId: null,
  currentSessionId: null,
  status: 'idle',
  errorMessage: null,
  externalResults: [],
  thinkingEntries: [],

  appendToken: (token) => set((s) => ({ streamingTokens: s.streamingTokens + token })),

  addStepNode: (node) => set((s) => ({
    stepNodes: [...s.stepNodes, node],
    currentStep: node,
  })),

  setCurrentStep: (step) => set({ currentStep: step }),

  setHitlPlan: (plan) => set({ hitlPlan: plan, status: plan ? 'awaiting_approval' : 'streaming' }),

  setThreadId: (id) => set({ threadId: id }),

  setSessionId: (id) => set({ currentSessionId: id }),

  setStatus: (status) => set({ status }),

  setError: (msg) => set({ errorMessage: msg, status: 'error' }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  finalizeAssistantMessage: (content, evidenceList, qualityScore, trace, externalResults) => set((s) => {
    const msg: Message = {
      id: genId(),
      role: 'assistant',
      content,
      evidenceList,
      qualityScore,
      trace,
    }
    return {
      messages: [...s.messages, msg],
      streamingTokens: '',
      status: 'complete',
      externalResults: externalResults ?? s.externalResults,
    }
  }),

  setExternalResults: (results) => set({ externalResults: results }),

  appendThinking: (node, text) => set((s) => ({
    thinkingEntries: [...s.thinkingEntries, { event: 'thinking', node, text }]
  })),

  reset: () => set({
    messages: [],
    streamingTokens: '',
    stepNodes: [],
    currentStep: null,
    hitlPlan: null,
    threadId: null,
    currentSessionId: null,
    status: 'idle',
    errorMessage: null,
    externalResults: [],
    thinkingEntries: [],
  }),
}))
