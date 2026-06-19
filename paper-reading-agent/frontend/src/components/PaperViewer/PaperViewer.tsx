import { useState, useEffect, useCallback, useRef } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { getPDFUrl } from '@/api/client'
import PDFCanvas from './PDFCanvas'
import PDFTextLayer from './PDFTextLayer'
import PDFToolbar from './PDFToolbar'
import type { HighlightRect } from './PDFTextLayer'
import styles from './PaperViewer.module.css'

// ---- Worker ----
const PDF_WORKER_SRC = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.mjs`
pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC

export type { HighlightRect }

export interface PaperViewerProps {
  paperId: string
  highlights?: HighlightRect[]
  /**
   * Called when the user clicks on a highlighted span in the text layer.
   */
  onHighlightClick?: (box: HighlightRect) => void
  /**
   * Called when the viewer has finished loading and rendering the initial page.
   */
  onReady?: () => void
  /**
   * Called when the user navigates to a different page.
   */
  onPageChange?: (page: number) => void
  // Phase 5: no-PDF support
  hasPDF?: boolean
  paperTitle?: string
  paperAuthors?: string[]
  paperAbstract?: string
  paperYear?: number
  arxivPdfUrl?: string | null
  onUploadPDF?: () => void
}

export type ViewerStatus = 'loading' | 'ready' | 'error' | 'empty'

/**
 * PaperViewer — the main PDF viewing component.
 *
 * - Loads a PDF document from the backend API
 * - Renders one page at a time using PDFCanvas + PDFTextLayer
 * - Provides toolbar navigation (page up/down, zoom in/out/reset)
 * - Supports highlights via the text layer
 */
export default function PaperViewer({ paperId, highlights, onHighlightClick, onReady, onPageChange, hasPDF = true, paperTitle, paperAuthors, paperAbstract, paperYear, arxivPdfUrl, onUploadPDF }: PaperViewerProps) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [status, setStatus] = useState<ViewerStatus>('loading')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [pageNumber, setPageNumber] = useState(1)
  const [numPages, setNumPages] = useState(0)
  const [scale, setScale] = useState(1.5)
  const [canvasReady, setCanvasReady] = useState(false)
  const readyFiredRef = useRef(false)
  const pageChangeFiredRef = useRef<number | null>(null)

  // ---- Load document ----
  useEffect(() => {
    let cancelled = false

    async function loadPDF() {
      setStatus('loading')
      setErrorMessage('')
      setDoc(null)
      setPageNumber(1)
      setNumPages(0)
      setCanvasReady(false)
      readyFiredRef.current = false
      pageChangeFiredRef.current = null

      try {
        const url = getPDFUrl(paperId)
        const loadingTask = pdfjsLib.getDocument(url)
        const pdfDoc = await loadingTask.promise

        if (cancelled) {
          pdfDoc.destroy()
          return
        }

        setDoc(pdfDoc)
        setNumPages(pdfDoc.numPages)
        setStatus('ready')
      } catch (err: unknown) {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : 'Unknown error loading PDF'
        setErrorMessage(msg)
        setStatus('error')
      }
    }

    loadPDF()

    return () => {
      cancelled = true
    }
  }, [paperId])

  // ---- Fire onReady once ----
  useEffect(() => {
    if (status === 'ready' && canvasReady && !readyFiredRef.current) {
      readyFiredRef.current = true
      onReady?.()
    }
  }, [status, canvasReady, onReady])

  // ---- Fire onPageChange when page navigates ----
  useEffect(() => {
    if (status === 'ready' && pageChangeFiredRef.current !== pageNumber) {
      pageChangeFiredRef.current = pageNumber
      onPageChange?.(pageNumber)
    }
  }, [pageNumber, status, onPageChange])

  // ---- Zoom handlers ----
  const zoomIn = useCallback(() => {
    setScale((s) => Math.min(s + 0.25, 4.0))
  }, [])

  const zoomOut = useCallback(() => {
    setScale((s) => Math.max(s - 0.25, 0.25))
  }, [])

  const zoomReset = useCallback(() => {
    setScale(1.0)
  }, [])

  // ---- Page navigation ----
  const goToPage = useCallback((page: number) => {
    setPageNumber(page)
    setCanvasReady(false)
  }, [])

  // ---- Render ----
  // Phase 5: No PDF — show metadata card
  if (!hasPDF && paperTitle) {
    return (
      <div className={styles.viewer}>
        <div className={styles.metadataCard}>
          <h2>📄 {paperTitle}</h2>
          {paperAuthors && paperAuthors.length > 0 && (
            <p className={styles.metaAuthors}>Authors: {paperAuthors.join(', ')}</p>
          )}
          {paperYear && <p className={styles.metaYear}>Year: {paperYear}</p>}
          {paperAbstract && (
            <div className={styles.metaAbstract}>
              <h4>Abstract</h4>
              <p>{paperAbstract}</p>
            </div>
          )}
          <div className={styles.metaActions}>
            {onUploadPDF && (
              <button onClick={onUploadPDF} className={styles.uploadBtn}>
                📤 Upload PDF
              </button>
            )}
            {arxivPdfUrl && (
              <a href={arxivPdfUrl} target="_blank" rel="noopener noreferrer" className={styles.arxivBtn}>
                Open on arXiv ↗
              </a>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (status === 'loading') {
    return (
      <div className={styles.viewer}>
        <div className={styles.loading}>Loading PDF...</div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className={styles.viewer}>
        <div className={styles.error}>
          <span>Failed to load PDF</span>
          <span style={{ fontSize: 12, opacity: 0.7 }}>{errorMessage}</span>
        </div>
      </div>
    )
  }

  if (status === 'empty' || !doc) {
    return (
      <div className={styles.viewer}>
        <div className={styles.empty}>No PDF loaded</div>
      </div>
    )
  }

  return (
    <div className={styles.viewer}>
      <PDFToolbar
        currentPage={pageNumber}
        numPages={numPages}
        scale={scale}
        onPageChange={goToPage}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onZoomReset={zoomReset}
      />

      <div className={styles.canvasArea}>
        <div className={styles.pageContainer}>
          <PageRenderer
            pageNumber={pageNumber}
            doc={doc}
            scale={scale}
            highlights={highlights}
            onHighlightClick={onHighlightClick}
            onRenderComplete={() => setCanvasReady(true)}
          />
        </div>
      </div>
    </div>
  )
}

// ---- Internal PageRenderer to handle async page proxy ----
interface PageRendererProps {
  pageNumber: number
  doc: PDFDocumentProxy
  scale: number
  highlights?: HighlightRect[]
  onHighlightClick?: (box: HighlightRect) => void
  onRenderComplete: () => void
}

function PageRenderer({ pageNumber, doc, scale, highlights, onHighlightClick, onRenderComplete }: PageRendererProps) {
  const [pageProxy, setPageProxy] = useState<pdfjsLib.PDFPageProxy | null>(null)
  const renderCompleteRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    renderCompleteRef.current = false

    async function getPage() {
      try {
        const page = await doc.getPage(pageNumber)
        if (!cancelled) {
          setPageProxy(page)
        }
      } catch (err) {
        console.error('Failed to get page:', err)
      }
    }

    getPage()

    return () => {
      cancelled = true
    }
  }, [doc, pageNumber])

  const handleRenderComplete = useCallback(() => {
    if (!renderCompleteRef.current) {
      renderCompleteRef.current = true
      onRenderComplete()
    }
  }, [onRenderComplete])

  if (!pageProxy) {
    return <div className={styles.loading}>Rendering page {pageNumber}...</div>
  }

  return (
    <>
      <PDFCanvas pdfDoc={doc} pageNumber={pageNumber} scale={scale} onRenderComplete={handleRenderComplete} />
      <PDFTextLayer
        pdfDoc={doc}
        pageNumber={pageNumber}
        scale={scale}
        highlights={highlights}
        onHighlightClick={onHighlightClick}
      />
    </>
  )
}
