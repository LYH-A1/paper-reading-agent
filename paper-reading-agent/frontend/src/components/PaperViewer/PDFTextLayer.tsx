import { useEffect, useRef, useCallback } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
import styles from './PaperViewer.module.css'

export interface HighlightRect {
  bbox: [number, number, number, number]  // [x0, y0, x1, y1] in viewport coords
  evidenceId: string
  color: string
}

export interface PDFTextLayerProps {
  pdfDoc: PDFDocumentProxy
  pageNumber: number
  scale: number
  highlights?: HighlightRect[]
  onHighlightClick?: (box: HighlightRect) => void
  onTextLayerRendered?: () => void
}

const DEFAULT_HIGHLIGHT_COLOR = 'rgba(255, 230, 0, 0.35)'

/**
 * Renders a transparent text layer over the PDF canvas for text selection
 * and highlighting.
 *
 * - Uses pdfjs-dist's built-in TextLayer class
 * - Applies highlight spans for evidence regions
 * - Supports click-to-select on highlighted spans
 */
export default function PDFTextLayer({ pdfDoc, pageNumber, scale, highlights, onHighlightClick, onTextLayerRendered }: PDFTextLayerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const textLayerRef = useRef<pdfjsLib.TextLayer | null>(null)
  const textLayerReadyRef = useRef(false)

  // Store callbacks in refs so effects always get the latest values
  const onHighlightClickRef = useRef(onHighlightClick)
  onHighlightClickRef.current = onHighlightClick
  const onTextLayerRenderedRef = useRef(onTextLayerRendered)
  onTextLayerRenderedRef.current = onTextLayerRendered

  /**
   * Apply highlight spans to the text layer DOM.
   * Extracted so it can be called both when highlights change
   * AND when the text layer finishes rendering (fixes R2 race condition).
   */
  const applyHighlights = useCallback(() => {
    const container = containerRef.current
    if (!container) return

    const spans = container.querySelectorAll('span')
    if (spans.length === 0) return

    // Remove all previous highlight classes and styles
    spans.forEach((span) => {
      span.classList.remove(styles.highlight)
      const el = span as HTMLElement
      el.style.backgroundColor = ''
      el.style.cursor = ''
    })

    if (!highlights || highlights.length === 0) return

    // Simple overlap approach: find spans that overlap with highlight regions
    highlights.forEach((hl) => {
      const [x0, y0, x1, y1] = hl.bbox
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
          const el = span as HTMLElement
          el.style.backgroundColor = hl.color || DEFAULT_HIGHLIGHT_COLOR

          // Add click handler if the callback exists (using data attribute to avoid duplicates)
          if (onHighlightClickRef.current && !span.dataset.evidenceClick) {
            span.dataset.evidenceClick = 'true'
            el.style.cursor = 'pointer'
            span.addEventListener('click', function handler() {
              onHighlightClickRef.current?.(hl)
            })
          }
        }
      })
    })
  }, [highlights, pageNumber])

  // Main effect: render text layer
  useEffect(() => {
    let cancelled = false
    let page: PDFPageProxy | null = null
    textLayerReadyRef.current = false

    async function renderLayer() {
      // Re-read the ref inside async function for TS narrowing
      const container = containerRef.current
      if (!container) return

      try {
        page = await pdfDoc.getPage(pageNumber)
        if (cancelled) return

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

        const textContent = await page.getTextContent()
        if (cancelled) return

        const textLayer = new pdfjsLib.TextLayer({
          textContentSource: textContent,
          container,
          viewport,
        })

        textLayerRef.current = textLayer

        await textLayer.render()
        textLayerRef.current = null

        if (!cancelled) {
          textLayerReadyRef.current = true
          onTextLayerRenderedRef.current?.()
          // Apply highlights now that text layer is rendered (fixes R2 race condition)
          applyHighlights()
        }
      } catch (err: unknown) {
        if (cancelled) return
        console.error('TextLayer render error:', err)
      }
    }

    renderLayer()

    return () => {
      cancelled = true
      if (textLayerRef.current) {
        textLayerRef.current.cancel()
        textLayerRef.current = null
      }
      if (page) {
        page.cleanup()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageNumber, scale])

  // Apply highlights when highlights prop changes (text layer must already be rendered)
  useEffect(() => {
    if (textLayerReadyRef.current) {
      applyHighlights()
    }
  }, [applyHighlights])

  return <div ref={containerRef} className={styles.textLayer} />
}
