import { describe, it, expect, vi, beforeEach } from 'vitest'
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

// ---- Pure function mocks (no import references) ----
function MOCK_GET_DOC() {
  return {
    promise: new Promise(function (rs) {
      globalThis.__pdfMockResolve = rs
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

function mockCanvas() {
  HTMLCanvasElement.prototype.getContext = function () {
    return { save: function () {}, restore: function () {}, scale: function () {} }
  }
}

function makeMockPage(pageNumber) {
  return {
    pageNumber,
    getViewport: function () { return { width: 600, height: 800 } },
    render: function () { return { promise: Promise.resolve(), cancel: function () {} } },
    getTextContent: function () { return Promise.resolve({ items: [], styles: {}, lang: 'en' }) },
  }
}

function makeMockDoc(numPages) {
  return { numPages, getPage: vi.fn(), destroy: vi.fn() }
}

async function loadComponent() {
  return (await import('../../src/components/PaperViewer/PaperViewer')).default
}

async function setupLoadedViewer(paperId, numPages, extraProps) {
  const PaperViewer = await loadComponent()
  const mockPage = makeMockPage(1)
  const doc = makeMockDoc(numPages || 5)
  doc.getPage.mockResolvedValue(mockPage)

  const result = render(<PaperViewer paperId={paperId} {...(extraProps || {})} />)

  await act(async function () {
    if (globalThis.__pdfMockResolve) {
      globalThis.__pdfMockResolve(doc)
      globalThis.__pdfMockResolve = null
    }
    await new Promise(function (r) { setTimeout(r, 10) })
  })

  return result
}

describe('PaperViewer', () => {
  beforeEach(() => {
    globalThis.__pdfMockResolve = null
    Object.defineProperty(globalThis, 'devicePixelRatio', { value: 1, configurable: true })
    mockCanvas()
  })

  it('shows loading state initially', async () => {
    const PaperViewer = await loadComponent()
    render(<PaperViewer paperId="test-paper" />)
    expect(screen.getByText('Loading PDF...')).toBeDefined()
  })

  it('shows error state when PDF loading fails', async () => {
    const pdfjsMod = await import('pdfjs-dist')

    // Catch rejection immediately to avoid unhandled rejection
    const rejectPromise = new Promise(function () {}) // never resolves or rejects
    pdfjsMod.getDocument = function () { return { promise: Promise.reject(new Error('Network error')).catch(function () {}) } }

    const PaperViewer = await loadComponent()

    await act(async () => {
      render(<PaperViewer paperId="bad-paper" />)
      await new Promise(function (r) { setTimeout(r, 10) })
    })

    expect(screen.getByText('Failed to load PDF')).toBeDefined()

    pdfjsMod.getDocument = MOCK_GET_DOC
  })

  it('transitions to rendering state when document loads', async () => {
    await setupLoadedViewer('test-paper', 5)

    await waitFor(() => {
      expect(screen.queryByRole('toolbar')).toBeDefined()
    })
  })

  it('renders canvas area and toolbar', async () => {
    const { container } = await setupLoadedViewer('test-paper', 3)

    await waitFor(() => {
      expect(screen.queryByRole('toolbar')).toBeDefined()
    })
    expect(container.querySelector('[class*="canvasArea"]')).toBeDefined()
  })

  it('renders toolbar with navigation and zoom buttons', async () => {
    await setupLoadedViewer('test-paper', 5)

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
    await setupLoadedViewer('test-paper', 7)

    await waitFor(() => {
      expect(screen.getByText('/ 7')).toBeDefined()
    })
  })
})
