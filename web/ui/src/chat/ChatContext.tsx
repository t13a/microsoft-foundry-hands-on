import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

type Chat = {
  open: boolean
  started: boolean
  show: () => void
  hide: () => void
  // Whether the top page's first-view CTA is on screen; the bottom button waits until it is not.
  heroCtaVisible: boolean
  setHeroCtaVisible: (visible: boolean) => void
}

const ChatContext = createContext<Chat | null>(null)

// Keeps the chat area's visibility. The conversation itself (S5) lives in memory only,
// so closing the area keeps it and reloading the page discards it (F-WF-04).
export function ChatProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [started, setStarted] = useState(false)
  const [heroCtaVisible, setHeroCtaVisible] = useState(false)
  const value = useMemo<Chat>(
    () => ({
      open,
      started,
      show: () => {
        setOpen(true)
        setStarted(true)
      },
      hide: () => setOpen(false),
      heroCtaVisible,
      setHeroCtaVisible,
    }),
    [open, started, heroCtaVisible],
  )
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useChat(): Chat {
  const chat = useContext(ChatContext)
  if (!chat) throw new Error('useChat must be used inside ChatProvider')
  return chat
}
