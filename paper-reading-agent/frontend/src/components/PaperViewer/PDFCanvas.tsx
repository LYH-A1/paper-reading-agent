import { useEffect, useRef } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFPageProxy } from 'pdfjs-dist'
import styles from './PaperViewer.module.css'

export interface PDFCanvasProps {
  page: PDFPageProxy
  scale: number
  onRenderComplete?: () => void
}

/**
 * Renders a single PDF page onto an HTML Canvas element.
 *
 * - Creates a canvas, sizes it to (viewport.width * scale) x (viewport.height * scale)
 * - Renders the page at the given scale
 * - Cleans up the canvas if scale changes or component unmounts
 */
export default function PDFCanvas({ page, scale, onRenderComplete }: PDFCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const renderTaskRef = useRef<pdfjsLib.RenderTask | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

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

    task.promise.then(() => {
      renderTaskRef.current = null
      onRenderComplete?.()
    }).catch((err: unknown) => {
      // Ignore cancellation errors
      if (err instanceof Error && err.message?.includes('cancelled')) return
      console.error('PDF render error:', err)
    })

    return () => {
      task.cancel()
      renderTaskRef.current = null
      ctx.restore()
    }
    // We intentionally depend on page.pageNumber and scale only.
    // page object identity is stable within a PDFDocumentProxy.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page.pageNumber, scale, onRenderComplete])

  return <canvas ref={canvasRef} className={styles.pdfCanvas} />
}
