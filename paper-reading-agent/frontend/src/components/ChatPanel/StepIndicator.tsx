import { useChatStore } from '@/store/chatStore'
import styles from './ChatPanel.module.css'

const NODE_ORDER = ['reader', 'classify', 'planner', 'retrieve', 'generate', 'observe', 'reviewer', 'output', 'rewrite']

export default function StepIndicator() {
  const stepNodes = useChatStore((s) => s.stepNodes)
  const currentStep = useChatStore((s) => s.currentStep)

  return (
    <div className={styles.stepIndicator}>
      {NODE_ORDER.map((nodeName) => {
        const done = stepNodes.includes(nodeName)
        const active = currentStep === nodeName
        return (
          <span
            key={nodeName}
            className={`${styles.stepNode} ${done ? styles.done : ''} ${active ? styles.active : ''}`}
          >
            {nodeName}
          </span>
        )
      })}
    </div>
  )
}
