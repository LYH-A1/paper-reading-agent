import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import { useAppStore } from '../../src/store/appStore'
import { useCompareStore } from '../../src/store/compareStore'

const { MOCK_PAPERS } = vi.hoisted(() => ({
  MOCK_PAPERS: [
    {
      paper_id: 'p1', title: 'Attention Is All You Need',
      authors: ['Vaswani, Ashish', 'Shazeer, Noam'],
      abstract_snippet: 'The dominant sequence transduction models are based on...',
      import_source: 'upload', arxiv_id: null, parsed_at: '2017-06-12',
    },
    {
      paper_id: 'p2', title: 'BERT: Pre-training of Deep Transformers',
      authors: ['Devlin, Jacob', 'Chang, Ming-Wei'],
      abstract_snippet: 'We introduce a new language representation model called BERT...',
      import_source: 'bib_import', arxiv_id: '1810.04805', parsed_at: '2018-10-11',
    },
    {
      paper_id: 'p3', title: 'Deep Residual Learning for Image Recognition',
      authors: ['He, Kaiming', 'Zhang, Xiangyu'],
      abstract_snippet: 'Deeper neural networks are more difficult to train...',
      import_source: 'external_save', arxiv_id: '1512.03385', parsed_at: '2015-12-10',
    },
  ],
}))

// Mock API — inline data to avoid hoist issues
vi.mock('@/api/client', () => ({
  listPapers: vi.fn().mockResolvedValue([
    {
      paper_id: 'p1', title: 'Attention Is All You Need',
      authors: ['Vaswani, Ashish', 'Shazeer, Noam'],
      abstract_snippet: 'The dominant sequence transduction models are based on...',
      import_source: 'upload', arxiv_id: null, parsed_at: '2017-06-12',
    },
    {
      paper_id: 'p2', title: 'BERT: Pre-training of Deep Transformers',
      authors: ['Devlin, Jacob', 'Chang, Ming-Wei'],
      abstract_snippet: 'We introduce a new language representation model called BERT...',
      import_source: 'bib_import', arxiv_id: '1810.04805', parsed_at: '2018-10-11',
    },
    {
      paper_id: 'p3', title: 'Deep Residual Learning for Image Recognition',
      authors: ['He, Kaiming', 'Zhang, Xiangyu'],
      abstract_snippet: 'Deeper neural networks are more difficult to train...',
      import_source: 'external_save', arxiv_id: '1512.03385', parsed_at: '2015-12-10',
    },
  ]),
  importBibTeX: vi.fn().mockResolvedValue({ imported: 0, skipped: 0, errors: [], papers: [] }),
}))

import LibraryPanel from '../../src/components/Layout/LibraryPanel'

describe('LibraryPanel search', () => {
  beforeEach(() => {
    useAppStore.setState({
      paper: null, sessions: [], currentSession: null,
      layout: 'dual', sidebarOpen: false,
    })
    useCompareStore.setState({ isCompareMode: false, selectedPaperIds: [] })
    vi.clearAllMocks()
  })

  it('filters papers by title on search', async () => {
    const screen = render(<LibraryPanel />)

    await waitFor(() => {
      expect(screen.getByText('Attention Is All You Need')).toBeTruthy()
    })

    const input = screen.container.querySelector('input[type="text"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'BERT' } })

    expect(screen.queryByText('Attention Is All You Need')).toBeNull()
    expect(screen.getByText('BERT: Pre-training of Deep Transformers')).toBeTruthy()
  })

  it('filters papers by source dropdown', async () => {
    const screen = render(<LibraryPanel />)

    await waitFor(() => {
      expect(screen.getByText('3 papers')).toBeTruthy()
    })

    const selects = screen.container.querySelectorAll('select')
    const sourceSelect = selects[0]  // first select is Source
    fireEvent.change(sourceSelect, { target: { value: 'bib_import' } })

    expect(screen.getByText('1 paper')).toBeTruthy()
    expect(screen.queryByText('Attention Is All You Need')).toBeNull()
    expect(screen.getByText('BERT: Pre-training of Deep Transformers')).toBeTruthy()
  })

  it('shows empty state when no papers match search', async () => {
    const screen = render(<LibraryPanel />)

    await waitFor(() => {
      expect(screen.getByText('3 papers')).toBeTruthy()
    })

    const input = screen.container.querySelector('input[type="text"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'NONEXISTENT PAPER' } })

    expect(screen.getByText('No papers match your search')).toBeTruthy()
  })

  it('sorts papers by date (default - newest first)', async () => {
    const screen = render(<LibraryPanel />)

    await waitFor(() => {
      expect(screen.getByText('3 papers')).toBeTruthy()
    })

    const items = screen.container.querySelectorAll('li')
    const titles = Array.from(items).map(li => li.textContent || '')
    // Default sort is date descending: BERT(2018), Attention(2017), ResNet(2015)
    expect(titles[0]).toContain('BERT')
  })

  it('sorts papers by title when selected', async () => {
    const screen = render(<LibraryPanel />)

    await waitFor(() => {
      expect(screen.getByText('3 papers')).toBeTruthy()
    })

    const selects = screen.container.querySelectorAll('select')
    const sortSelect = selects[1]  // second select is Sort
    fireEvent.change(sortSelect, { target: { value: 'title' } })

    const items = screen.container.querySelectorAll('li')
    const titles = Array.from(items).map(li => li.textContent || '')
    // Sorted by title A-Z: Attention, BERT, Deep Residual
    expect(titles[0]).toContain('Attention')
    expect(titles[1]).toContain('BERT')
    expect(titles[2]).toContain('Deep Residual')
  })

  it('shows source tag for non-upload papers', async () => {
    const screen = render(<LibraryPanel />)

    await waitFor(() => {
      expect(screen.getByText('BERT: Pre-training of Deep Transformers')).toBeTruthy()
    })

    // Source tags render within <span> elements — CSS modules hash class names
    // Look for spans containing the source text directly
    const sourceTexts = Array.from(screen.container.querySelectorAll('span'))
      .map(el => el.textContent?.trim() || '')
      .filter(t => ['BibTeX Import', 'External Save', 'Uploaded'].includes(t))
    // BERT is bib_import → "BibTeX Import" tag
    expect(sourceTexts).toContain('BibTeX Import')
    // ResNet is external_save → "External Save" tag
    expect(sourceTexts).toContain('External Save')
    // Upload paper (Attention) has no tag
    expect(sourceTexts).not.toContain('Uploaded')
  })
})
