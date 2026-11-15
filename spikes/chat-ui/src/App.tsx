import { useCallback, useRef, useState } from 'react'
import { Chat } from './Chat'

// A stand-in for the content area: it only shows which URL the agent navigated to.
export default function App() {
  const [url, setUrl] = useState('/')
  const urlRef = useRef(url)
  const navigate = useCallback((next: string) => {
    urlRef.current = next
    setUrl(next)
  }, [])
  const currentUrl = useCallback(() => urlRef.current, [])

  return (
    <div className="layout">
      <header className="header">出茂市 くらしのサービス案内</header>
      <aside className="chat">
        <Chat onNavigate={navigate} currentUrl={currentUrl} />
      </aside>
      <main className="content">
        <p className="content-label">コンテンツ領域 (検証用の仮表示)</p>
        <p className="content-url" data-testid="content-url">
          表示中: <code>{decodeURI(url)}</code>
        </p>
      </main>
    </div>
  )
}
