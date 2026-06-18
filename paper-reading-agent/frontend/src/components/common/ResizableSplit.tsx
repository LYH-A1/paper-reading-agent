import { useState, useCallback, type ReactNode } from 'react'
import styles from '@/components/Layout/Layout.module.css'

interface ResizableSplitProps {
  left: ReactNode
  right: ReactNode
  defaultRatio?: number
  minRatio?: number
  maxRatio?: number
  leftVisible?: boolean
  rightVisible?: boolean
}

export default function ResizableSplit({
  left, right,
  defaultRatio = 0.45,
  minRatio = 0.25,
  maxRatio = 0.75,
  leftVisible = true,
  rightVisible = true,
}: ResizableSplitProps) {
  const [ratio, setRatio] = useState(defaultRatio)

  const handleMouseDown = useCallback(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const container = document.querySelector(`.${styles.split}`) as HTMLElement
      if (!container) return
      const rect = container.getBoundingClientRect()
      const newRatio = (e.clientX - rect.left) / rect.width
      setRatio(Math.max(minRatio, Math.min(maxRatio, newRatio)))
    }
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [minRatio, maxRatio])

  if (!leftVisible) return <div className={styles.split}>{right}</div>
  if (!rightVisible) return <div className={styles.split}>{left}</div>

  return (
    <div className={styles.split}>
      <div className={styles.splitLeft} style={{ width: `${ratio * 100}%` }}>
        {left}
      </div>
      <div className={styles.splitHandle} onMouseDown={handleMouseDown} />
      <div className={styles.splitRight} style={{ width: `${(1 - ratio) * 100}%` }}>
        {right}
      </div>
    </div>
  )
}
