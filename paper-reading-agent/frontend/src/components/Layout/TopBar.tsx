import { useAppStore } from '@/store/appStore'
import LayoutToggle from './LayoutToggle'
import styles from './Layout.module.css'

export default function TopBar() {
  const paper = useAppStore((s) => s.paper)

  return (
    <div className={styles.topBar}>
      <h1 className={styles.title}>{paper?.title || 'Paper Reading Agent'}</h1>
      <div className={styles.topBarRight}>
        <LayoutToggle />
        <button className={styles.menuBtn} onClick={() => useAppStore.getState().toggleSidebar()}>
          ☰ Library
        </button>
      </div>
    </div>
  )
}
