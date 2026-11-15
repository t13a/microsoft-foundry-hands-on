import { lazy, Suspense, useEffect } from 'react'
import { useLocation } from 'react-router'
import { useChat } from './chat/ChatContext.tsx'
import ConsultButton from './components/ConsultButton.tsx'
import Header from './components/Header.tsx'
import CategoryPage from './pages/CategoryPage.tsx'
import NotFoundPage from './pages/NotFoundPage.tsx'
import SearchPage from './pages/SearchPage.tsx'
import TopPage from './pages/TopPage.tsx'
import { parseParts } from './urls.ts'

const ChatPanel = lazy(() => import('./chat/ChatPanel.tsx'))

// The screen state lives entirely in the URL (F-SITE-07), so routing parses it directly.
function Content() {
  const { pathname, search, hash } = useLocation()
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0)
  }, [pathname, search, hash])

  if (pathname === '/') return <TopPage />
  const location = parseParts(pathname, search, hash)
  if (location?.kind === 'category') return <CategoryPage key={location.path.join('/')} path={location.path} highlights={location.highlights} />
  if (location?.kind === 'search') return <SearchPage query={location.query} />
  return <NotFoundPage />
}

export default function App() {
  const chat = useChat()
  return (
    <div className={`layout${chat.open ? ' chat-open' : ''}`}>
      <Header />
      <div className="layout-body">
        {chat.started && (
          <aside className="layout-chat" hidden={!chat.open}>
            <Suspense fallback={null}>
              <ChatPanel />
            </Suspense>
          </aside>
        )}
        <div className="layout-content">
          <Content />
          <ConsultButton />
        </div>
      </div>
    </div>
  )
}
