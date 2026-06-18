import { useEffect, useRef } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFPageProxy } from 'pdfjs-dist'
import styles from './PaperViewer.module.css'

export interface PDFTextLayerProps {
  page: PDFPageProxy
  scale: number
  /** Array of highlight regions in the format [page, x0, y0, x1, y1] */
  highlights?: Array<[number, number, number, number, number]>
  onTextLayerRendered?: () => void
}

/**
 * Renders a transparent text layer over the PDF canvas for text selection
 * and highlighting.
 *
 * - Uses pdfjs-dist's built-in TextLayer class
 * - Applies highlight spans for evidence regions
 */
export default function PDFTextLayer({ page, scale, highlights, onTextLayerRendered }: PDFTextLayerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const textLayerRef = useRef<pdfjsLib.TextLayer | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const viewport = page.getViewport({ scale })

    // Set container dimensions to match canvas
    container.style.width = `${viewport.width}px`
    container.style.height = `${viewport.height}px`
    container.style.left = '0px'
    container.style.top = '0px'

    // Clean up previous text layer
    if (textLayerRef.current) {
      textLayerRef.current.cancel()
      textLayerRef.current = null
    }

    // Clear any previous text spans
    container.innerHTML = ''

    let cancelled = false

    page.getTextContent().then((textContent) => {
      if (cancelled) return

      const textLayer = new pdfjsLib.TextLayer({
        textContentSource: textContent,
        container,
        viewport,
      })

      textLayerRef.current = textLayer

      return textLayer.render().then(() => {
        textLayerRef.current = null
        if (!cancelled) {
          onTextLayerRendered?.()
        }
      })
    }).catch((err: unknown) => {
      if (cancelled) return
      console.error('TextLayer render error:', err)
    })

    return () => {
      cancelled = true
      if (textLayerRef.current) {
        textLayerRef.current.cancel()
        textLayerRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page.pageNumber, scale, onTextLayerRendered])

  // Apply highlights when highlights prop changes
  useEffect(() => {
    const container = containerRef.current
    if (!container || !highlights || highlights.length === 0) return

    // Filter highlights for this page
    const pageHighlights = highlights.filter(([p]) => p === page.pageNumber)
    if (pageHighlights.length === 0) return

    const spans = container.querySelectorAll('span')
    if (spans.length === 0) return

    // Simple highlight approach: find spans that overlap with highlight regions
    // This is a simplified implementation; a production version would use
    // more precise character-level positioning
    pageHighlights.forEach(([, x0, y0, x1, y1]) => {
      spans.forEach((span) => {
        const rect = span.getBoundingClientRect()
        const containerRect = container.getBoundingClientRect()
        const spanLeft = rect.left - containerRect.left
        const spanTop = rect.top - containerRect.top
        const spanRight = spanLeft + rect.width
        const spanBottom = spanTop + rect.height

        // Check if span overlaps with the highlight region
        if (spanLeft < x1 && spanRight > x0 && spanTop < y1 && spanBottom > y0) {
          span.classList.add(styles.highlight)
        }
      })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlights, page.pageNumber])

  return <div ref={containerRef} className={styles.textLayer} />
}
