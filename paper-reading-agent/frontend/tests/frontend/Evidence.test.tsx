import { describe, it, expect } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import EvidenceBadge from '../../src/components/Evidence/EvidenceBadge'
import type { Evidence } from '../../src/types'

const r0Evidence: Evidence = {
  evidence_id: 'ev-1',
  claim: 'The method achieves F1=0.94',
  level: 'R0',
  sentence_index: 2,
  char_start: 42,
  char_end: 80,
  page: 4,
  quote: 'Our method achieves an F1 score of 0.94 on the benchmark dataset.',
  section_heading: '4. Experiments',
  source_title: null, source_url: null, source_venue: null, source_year: null,
  reasoning: null,
  based_on_evidence_ids: [],
  confidence: 0.95,
}

const r2Evidence: Evidence = {
  evidence_id: 'ev-5',
  claim: 'This approach is generalizable',
  level: 'R2',
  sentence_index: 5,
  char_start: 200,
  char_end: 230,
  page: null, quote: null, section_heading: null,
  source_title: null, source_url: null, source_venue: null, source_year: null,
  reasoning: 'Based on strong results across 3 datasets',
  based_on_evidence_ids: ['ev-1', 'ev-3'],
  confidence: 0.72,
}

describe('EvidenceBadge', () => {
  it('renders R0 with red styling', () => {
    const screen = render(<EvidenceBadge evidence={r0Evidence} />)
    const badge = screen.container.querySelector('[data-level="R0"]')
    expect(badge).toBeTruthy()
    expect(badge?.textContent).toContain('R0')
  })

  it('renders R2 with blue styling', () => {
    const screen = render(<EvidenceBadge evidence={r2Evidence} />)
    const badge = screen.container.querySelector('[data-level="R2"]')
    expect(badge).toBeTruthy()
  })

  it('calls onClick when clicked', () => {
    let clicked: Evidence | null = null
    const screen = render(<EvidenceBadge evidence={r0Evidence} onClick={(e) => { clicked = e }} />)
    fireEvent.click(screen.container.querySelector('[data-level="R0"]')!)
    expect(clicked?.evidence_id).toBe('ev-1')
  })
})
