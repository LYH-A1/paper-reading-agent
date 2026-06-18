import { useState, useEffect, useCallback, useRef } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { getPDFUrl } from '@/api/client'
import PDFCanvas from './PDFCanvas'
import PDFTextLayer from './PDFTextLayer'
import PDFToolbar from './PDFToolbar'
import styles from './PaperViewer.module.css'

// ---- Worker ----
const PDF_WORKER_SRC = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.mjs`
pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC

export interface PaperViewerProps {
  paperId: string
  highlights?: Array<[number, number, number, number, number]>
  /**
   * Called when the viewer has finished loading and rendering the initial page.
   */
  onReady?: () => void
  /**
   * Called when the user navigates to a different page.
   */
  onPageChange?: (page: number) => void
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
export default function PaperViewer({ paperId, highlights, onReady, onPageChange }: PaperViewerProps) {
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
    setScale(1.5)
  }, [])

  // ---- Page navigation ----
  const goToPage = useCallback((page: number) => {
    setPageNumber(page)
    setCanvasReady(false)
  }, [])

  // ---- Get current page proxy ----
  const currentPageProxy = doc ? doc.getPage(pageNumber) : null

  // ---- Render ----
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
  highlights?: Array<[number, number, number, number, number]>
  onRenderComplete: () => void
}

function PageRenderer({ pageNumber, doc, scale, highlights, onRenderComplete }: PageRendererProps) {
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
      <PDFCanvas page={pageProxy} scale={scale} onRenderComplete={handleRenderComplete} />
      <PDFTextLayer page={pageProxy} scale={scale} highlights={highlights} />
    </>
  )
}
