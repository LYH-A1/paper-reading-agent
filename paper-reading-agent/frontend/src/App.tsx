import { useAppStore } from '@/store/appStore'
import TopBar from '@/components/Layout/TopBar'
import Sidebar from '@/components/Layout/Sidebar'
import ResizableSplit from '@/components/common/ResizableSplit'
import PaperViewer from '@/components/PaperViewer/PaperViewer'
import ChatPanel from '@/components/ChatPanel/ChatPanel'
import './App.css'

export default function App() {
  const paper = useAppStore((s) => s.paper)
  const layout = useAppStore((s) => s.layout)

  return (
    <div className="app">
      <TopBar />
      <div className="main-content">
        {layout === 'dual' && (
          <ResizableSplit
            left={<PaperViewer paperId={paper?.paper_id || ''} />}
            right={<ChatPanel />}
            leftVisible={!!paper}
            rightVisible={!!paper}
          />
        )}
        {layout === 'chat' && (
          <div className="full-panel">
            <ChatPanel />
          </div>
        )}
        {layout === 'paper' && (
          <div className="full-panel">
            <PaperViewer paperId={paper?.paper_id || ''} />
          </div>
        )}
        {!paper && (
          <div className="empty-state">
            <p>Upload a paper to get started</p>
          </div>
        )}
      </div>
      <Sidebar />
    </div>
  )
}
