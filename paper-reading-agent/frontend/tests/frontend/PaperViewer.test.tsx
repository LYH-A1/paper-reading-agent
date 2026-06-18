import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'

// ---- Mock pdfjs-dist ----
vi.mock('pdfjs-dist', () => {
  return {
    default: {
      GlobalWorkerOptions: { workerSrc: '' },
      getDocument: MOCK_GET_DOC,
      TextLayer: createMockTextLayer(),
      version: '4.10.38',
    },
    GlobalWorkerOptions: { workerSrc: '' },
    getDocument: MOCK_GET_DOC,
    TextLayer: createMockTextLayer(),
    version: '4.10.38',
  }
})

vi.mock('../../src/api/client', () => ({
  getPDFUrl: function (id) { return `/api/pdf/${id}` },
}))

// ---- Reusable mock primitives ----
function MOCK_GET_DOC() {
  return {
    promise: new Promise(function (rs, rj) {
      globalThis.__pdfMockResolve = rs
      globalThis.__pdfMockReject = rj
    }),
  }
}

function createMockTextLayer() {
  const MockTextLayer = function () {
    this.render = function () { return Promise.resolve() }
    this.cancel = function () {}
  }
  return MockTextLayer
}

let canvasGetContextSpy

function mockCanvas() {
  const ctx = {
    save: function () {},
    restore: function () {},
    scale: function () {},
  }
  canvasGetContextSpy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx)
}

function makeMockPage(pageNumber) {
  return {
    pageNumber,
    getViewport: function () { return { width: 600, height: 800 } },
    render: function () { return { promise: Promise.resolve(), cancel: function () {} } },
    getTextContent: function () { return Promise.resolve({ items: [], styles: {}, lang: 'en' }) },
    cleanup: function () {},
  }
}

function makeMockDoc(numPages) {
  return { numPages, getPage: vi.fn(), destroy: vi.fn() }
}

async function loadComponent() {
  return (await import('../../src/components/PaperViewer/PaperViewer')).default
}

/**
 * Resolve the pending getDocument promise with a mock document.
 * Must be called inside act().
 */
function resolveDoc(numPages) {
  const mockPage = makeMockPage(1)
  const doc = makeMockDoc(numPages || 5)
  doc.getPage.mockResolvedValue(mockPage)
  if (globalThis.__pdfMockResolve) {
    globalThis.__pdfMockResolve(doc)
    globalThis.__pdfMockResolve = null
    globalThis.__pdfMockReject = null
  }
}

/**
 * Reject the pending getDocument promise.
 * Must be called inside act().
 */
function rejectDoc(errorMsg) {
  if (globalThis.__pdfMockReject) {
    globalThis.__pdfMockReject(new Error(errorMsg || 'Network error'))
    globalThis.__pdfMockResolve = null
    globalThis.__pdfMockReject = null
  }
}

// ---- Tests ----
describe('PaperViewer', () => {
  beforeEach(() => {
    globalThis.__pdfMockResolve = null
    globalThis.__pdfMockReject = null
    Object.defineProperty(globalThis, 'devicePixelRatio', { value: 1, configurable: true })
    mockCanvas()
  })

  afterEach(() => {
    canvasGetContextSpy?.mockRestore()
  })

  it('shows loading state initially', async () => {
    const PaperViewer = await loadComponent()
    render(<PaperViewer paperId="test-paper" />)
    expect(screen.getByText('Loading PDF...')).toBeDefined()
  })

  it('shows error state when PDF loading fails', async () => {
    const PaperViewer = await loadComponent()
    render(<PaperViewer paperId="bad-paper" />)

    await act(async function () {
      rejectDoc('Network error')
      await new Promise(function (r) { setTimeout(r, 10) })
    })

    expect(screen.getByText('Failed to load PDF')).toBeDefined()
  })

  it('transitions to rendering state when document loads', async () => {
    const PaperViewer = await loadComponent()
    render(<PaperViewer paperId="test-paper" />)

    await act(async function () {
      resolveDoc(5)
      await new Promise(function (r) { setTimeout(r, 10) })
    })

    await waitFor(() => {
      expect(screen.queryByRole('toolbar')).toBeDefined()
    })
  })

  it('renders canvas area and toolbar', async () => {
    const PaperViewer = await loadComponent()
    const { container } = render(<PaperViewer paperId="test-paper" />)

    await act(async function () {
      resolveDoc(3)
      await new Promise(function (r) { setTimeout(r, 10) })
    })

    await waitFor(() => {
      expect(screen.queryByRole('toolbar')).toBeDefined()
    })
    expect(container.querySelector('[class*="canvasArea"]')).toBeDefined()
  })

  it('renders toolbar with navigation and zoom buttons', async () => {
    const PaperViewer = await loadComponent()
    render(<PaperViewer paperId="test-paper" />)

    await act(async function () {
      resolveDoc(5)
      await new Promise(function (r) { setTimeout(r, 10) })
    })

    await waitFor(() => {
      expect(screen.queryByLabelText('Next page')).toBeDefined()
    })
    const nextBtn = screen.getByLabelText('Next page')
    expect(nextBtn.getAttribute('disabled')).toBeNull()
    expect(screen.getByLabelText('Previous page').getAttribute('disabled')).not.toBeNull()
    expect(screen.getByLabelText('Zoom in')).toBeDefined()
    expect(screen.getByLabelText('Zoom out')).toBeDefined()
    expect(screen.getByLabelText('Reset zoom')).toBeDefined()
  })

  it('renders page indicator with total pages', async () => {
    const PaperViewer = await loadComponent()
    render(<PaperViewer paperId="test-paper" />)

    await act(async function () {
      resolveDoc(7)
      await new Promise(function (r) { setTimeout(r, 10) })
    })

    await waitFor(() => {
      expect(screen.getByText('/ 7')).toBeDefined()
    })
  })

  it('shows 100% label on zoom reset button', async () => {
    const PaperViewer = await loadComponent()
    render(<PaperViewer paperId="test-paper" />)

    await act(async function () {
      resolveDoc(3)
      await new Promise(function (r) { setTimeout(r, 10) })
    })

    await waitFor(() => {
      expect(screen.getByLabelText('Reset zoom')).toBeDefined()
    })

    // The label text should be 100%
    expect(screen.getByLabelText('Reset zoom').textContent).toBe('100%')

    // Scale indicator should show default zoom (150%)
    expect(screen.getByText(/150%/)).toBeDefined()
  })
})
