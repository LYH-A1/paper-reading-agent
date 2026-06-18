import { useAppStore, type LayoutMode } from '@/store/appStore'
import styles from './Layout.module.css'

const MODES: { mode: LayoutMode; label: string; icon: string }[] = [
  { mode: 'dual', label: 'Dual', icon: '◧' },
  { mode: 'chat', label: 'Chat', icon: '▯' },
  { mode: 'paper', label: 'Paper', icon: '▭' },
]

export default function LayoutToggle() {
  const layout = useAppStore((s) => s.layout)
  const setLayout = useAppStore((s) => s.setLayout)

  return (
    <div className={styles.layoutToggle}>
      {MODES.map(({ mode, label, icon }) => (
        <button
          key={mode}
          className={layout === mode ? styles.active : ''}
          onClick={() => setLayout(mode)}
          aria-label={`Switch to ${label.toLowerCase()} layout`}
          aria-pressed={layout === mode}
        >
          {icon} {label}
        </button>
      ))}
    </div>
  )
}
