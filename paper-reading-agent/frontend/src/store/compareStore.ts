import { create } from 'zustand'

interface CompareStore {
  isCompareMode: boolean
  selectedPaperIds: string[]
  toggleCompareMode: () => void
  toggleSelection: (id: string) => void
  clearSelection: () => void
}

export const useCompareStore = create<CompareStore>((set, get) => ({
  isCompareMode: false,
  selectedPaperIds: [],

  toggleCompareMode: () => {
    set((s) => ({
      isCompareMode: !s.isCompareMode,
      selectedPaperIds: s.isCompareMode ? [] : s.selectedPaperIds,
    }))
  },

  toggleSelection: (id: string) => {
    const { selectedPaperIds } = get()
    if (selectedPaperIds.includes(id)) {
      set({ selectedPaperIds: selectedPaperIds.filter((pid) => pid !== id) })
    } else if (selectedPaperIds.length < 5) {
      set({ selectedPaperIds: [...selectedPaperIds, id] })
    }
  },

  clearSelection: () => {
    set({ selectedPaperIds: [], isCompareMode: false })
  },
}))
