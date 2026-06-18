import { useState, useCallback, type KeyboardEvent } from 'react'
import styles from './PaperViewer.module.css'

export interface PDFToolbarProps {
  currentPage: number
  numPages: number
  scale: number
  onPageChange: (page: number) => void
  onZoomIn: () => void
  onZoomOut: () => void
  onZoomReset: () => void
}

/**
 * Toolbar for PDF navigation — page input, zoom controls.
 *
 * - Page input: type a page number and press Enter to jump
 * - Zoom: + / - / reset buttons with percentage display
 */
export default function PDFToolbar({
  currentPage,
  numPages,
  scale,
  onPageChange,
  onZoomIn,
  onZoomOut,
  onZoomReset,
}: PDFToolbarProps) {
  const [pageInput, setPageInput] = useState(String(currentPage))

  const handlePageInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setPageInput(e.target.value)
  }, [])

  const handlePageInputKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        const p = parseInt(pageInput, 10)
        if (p >= 1 && p <= numPages) {
          onPageChange(p)
        } else {
          // Reset input to current page on invalid input
          setPageInput(String(currentPage))
        }
      }
    },
    [pageInput, numPages, currentPage, onPageChange],
  )

  // Sync pageInput when currentPage changes externally
  // We use a key or rely on the parent; but to keep it simple we update on blur
  const handlePageInputBlur = useCallback(() => {
    setPageInput(String(currentPage))
  }, [currentPage])

  const percentage = Math.round(scale * 100)
  const canZoomOut = scale > 0.25
  const canZoomIn = scale < 4.0

  return (
    <div className={styles.toolbar} role="toolbar" aria-label="PDF viewer toolbar">
      <button
        className={styles.toolbarBtn}
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage <= 1}
        aria-label="Previous page"
      >
        &#9664;
      </button>

      <span className={styles.pageIndicator}>
        <input
          className={styles.pageInput}
          type="text"
          value={pageInput}
          onChange={handlePageInputChange}
          onKeyDown={handlePageInputKeyDown}
          onBlur={handlePageInputBlur}
          aria-label="Page number"
        />
        <span>&nbsp;/ {numPages}</span>
      </span>

      <button
        className={styles.toolbarBtn}
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage >= numPages}
        aria-label="Next page"
      >
        &#9654;
      </button>

      <span style={{ flex: 1 }} />

      <button
        className={styles.toolbarBtn}
        onClick={onZoomOut}
        disabled={!canZoomOut}
        aria-label="Zoom out"
      >
        &minus;
      </button>

      <span className={styles.scaleIndicator}>{percentage}%</span>

      <button
        className={styles.toolbarBtn}
        onClick={onZoomIn}
        disabled={!canZoomIn}
        aria-label="Zoom in"
      >
        +
      </button>

      <button
        className={styles.toolbarBtn}
        onClick={onZoomReset}
        aria-label="Reset zoom"
      >
        100%
      </button>
    </div>
  )
}
