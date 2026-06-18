import { useEffect, useRef } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import styles from './PaperViewer.module.css'

export interface PDFCanvasProps {
  pdfDoc: PDFDocumentProxy
  pageNumber: number
  scale: number
  onRenderComplete?: () => void
}

/**
 * Renders a single PDF page onto an HTML Canvas element.
 *
 * - Fetches the PDFPageProxy from the document internally
 * - Creates a canvas, sizes it to (viewport.width * scale) x (viewport.height * scale)
 * - Renders the page at the given scale with HiDPI support
 * - Cleans up the canvas if page/scale changes or component unmounts
 */
export default function PDFCanvas({ pdfDoc, pageNumber, scale, onRenderComplete }: PDFCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const renderTaskRef = useRef<pdfjsLib.RenderTask | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let cancelled = false

    async function renderPage() {
      try {
        const page = await pdfDoc.getPage(pageNumber)
        if (cancelled) return

        const viewport = page.getViewport({ scale })
        canvas.width = viewport.width * devicePixelRatio
        canvas.height = viewport.height * devicePixelRatio
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        // Scale the context for HiDPI displays
        ctx.save()
        ctx.scale(devicePixelRatio, devicePixelRatio)

        const renderContext: pdfjsLib.RenderParameters = {
          canvasContext: ctx,
          viewport,
        }

        const task = page.render(renderContext)
        renderTaskRef.current = task

        await task.promise
        renderTaskRef.current = null
        if (!cancelled) {
          onRenderComplete?.()
        }
      } catch (err: unknown) {
        if (cancelled) return
        // Ignore cancellation errors
        if (err instanceof Error && err.message?.includes('cancelled')) return
        console.error('PDF render error:', err)
      }
    }

    renderPage()

    return () => {
      cancelled = true
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel()
        renderTaskRef.current = null
      }
    }
    // We intentionally depend on pageNumber and scale only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageNumber, scale, onRenderComplete])

  return <canvas ref={canvasRef} className={styles.pdfCanvas} />
}
