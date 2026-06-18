import { create } from 'zustand'
import type { Paper, Session } from '@/types'

export type LayoutMode = 'dual' | 'chat' | 'paper'

interface AppState {
  paper: Paper | null
  sessions: Session[]
  currentSession: Session | null
  layout: LayoutMode
  sidebarOpen: boolean

  setPaper: (paper: Paper) => void
  clearPaper: () => void
  setLayout: (layout: LayoutMode) => void
  toggleSidebar: () => void
  addSession: (session: Session) => void
  setCurrentSession: (session: Session) => void
}

export const useAppStore = create<AppState>((set) => ({
  paper: null,
  sessions: [],
  currentSession: null,
  layout: 'dual',
  sidebarOpen: false,

  setPaper: (paper) => set({ paper }),
  clearPaper: () => set({ paper: null }),
  setLayout: (layout) => set({ layout }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
  setCurrentSession: (session) => set({ currentSession: session }),
}))
