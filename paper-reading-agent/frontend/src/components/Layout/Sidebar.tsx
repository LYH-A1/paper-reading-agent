import { useAppStore } from '@/store/appStore'
import LibraryPanel from './LibraryPanel'
import SessionHistory from './SessionHistory'
import SettingsPanel from './SettingsPanel'
import styles from './Layout.module.css'

export default function Sidebar() {
  const sidebarOpen = useAppStore((s) => s.sidebarOpen)
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)

  if (!sidebarOpen) return null

  return (
    <div className={styles.sidebarOverlay} onClick={toggleSidebar}>
      <div className={styles.sidebar} onClick={(e) => e.stopPropagation()}>
        <button className={styles.closeBtn} onClick={toggleSidebar}>×</button>
        <LibraryPanel />
        <SessionHistory />
        <SettingsPanel />
      </div>
    </div>
  )
}
