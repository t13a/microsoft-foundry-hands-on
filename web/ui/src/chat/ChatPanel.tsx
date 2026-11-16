import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from '@assistant-ui/react'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { useNavigate } from 'react-router'
import { AssistantIcon, BackIcon, CloseIcon, MoreIcon } from '../components/icons.tsx'
import { useChat } from './ChatContext.tsx'
import { CardView, EmergencyView, EndView, FormView, SuggestionsView } from './parts.tsx'
import type { Item } from './state.ts'
import { useConsultation, type Consultation } from './useConsultation.ts'

type ChatView = { consultation: Consultation; items: Map<string, Item>; show: (url: string) => void; shown: Set<string>; open: (item: Item & { kind: 'card' }) => void }
const ChatViewContext = createContext<ChatView | null>(null)
// eslint-disable-next-line react-refresh/only-export-components
export const useChatView = () => useContext(ChatViewContext)!

const toMessage = (item: Item): ThreadMessageLike => ({
  id: item.id,
  role: item.kind === 'user' ? 'user' : 'assistant',
  content:
    item.kind === 'assistant' || item.kind === 'user'
      ? [{ type: 'text', text: item.text }]
      : [{ type: 'tool-call', toolCallId: item.id, toolName: item.kind, args: {} }],
})

const isNarrow = () => window.matchMedia('(max-width: 899px)').matches
const currentUrl = () => `${location.pathname}${location.search}${location.hash}`

// The chat area. Loaded lazily because it is opened from the CTA (docs/design.md 3.1).
export default function ChatPanel() {
  const chat = useChat()
  const navigate = useNavigate()
  const consultation = useConsultation(currentUrl)
  const { state } = consultation
  const [shown, setShown] = useState<Set<string>>(new Set())
  const [menuOpen, setMenuOpen] = useState(false)

  const show = useCallback(
    (url: string) => {
      navigate(url)
      // On mobile only one area is visible, so switch to the content (F-UI-04).
      if (isNarrow()) chat.hide()
    },
    [chat, navigate],
  )
  const open = useCallback(
    (card: Item & { kind: 'card' }) => {
      show(card.url)
      if (!shown.has(card.id)) {
        setShown(new Set(shown).add(card.id))
        consultation.opened(card.url)
      }
    },
    [consultation, show, shown],
  )

  const restart = () => {
    setMenuOpen(false)
    setShown(new Set())
    consultation.start()
  }

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const first = message.content[0]
      if (first?.type === 'text') consultation.sendText(first.text)
    },
    [consultation],
  )
  const waitingForMessage = !state.running && state.pending?.kind === 'message'
  const runtime = useExternalStoreRuntime({
    messages: state.items,
    isRunning: state.running,
    isSendDisabled: !waitingForMessage,
    convertMessage: toMessage,
    onNew,
  })
  const items = useMemo(() => new Map(state.items.map((i) => [i.id, i])), [state.items])

  return (
    <section className="chat" aria-label="AI 案内係">
      <header className="chat-header">
        <button type="button" className="chat-back" onClick={chat.hide}>
          <BackIcon />
          サイトに戻る
        </button>
        <span className="chat-title">
          <span className="chat-avatar">
            <AssistantIcon />
          </span>
          AI 案内係
        </span>
        <span className="chat-actions">
          <span className="chat-menu">
            <button type="button" className="icon-button" aria-label="メニュー" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
              <MoreIcon />
            </button>
            {menuOpen && (
              <span className="chat-menu-list" role="menu">
                <button type="button" role="menuitem" onClick={restart}>
                  はじめからやり直す
                </button>
              </span>
            )}
          </span>
          <button type="button" className="icon-button chat-close" aria-label="チャットを閉じる" onClick={chat.hide}>
            <CloseIcon />
          </button>
        </span>
      </header>

      <ChatViewContext.Provider value={{ consultation, items, show, shown, open }}>
        <AssistantRuntimeProvider runtime={runtime}>
          <ThreadPrimitive.Root className="thread">
            <ThreadPrimitive.Viewport className="thread-viewport" role="log" aria-live="polite">
              <ThreadPrimitive.Messages>
                {({ message }) => (
                  <MessagePrimitive.Root className={`message is-${message.role}`}>
                    <MessagePrimitive.Parts>
                      {({ part }) =>
                        part.type === 'text' ? (
                          <TextBubble role={message.role} text={part.text} />
                        ) : part.type === 'tool-call' ? (
                          <ItemView id={part.toolCallId} />
                        ) : null
                      }
                    </MessagePrimitive.Parts>
                  </MessagePrimitive.Root>
                )}
              </ThreadPrimitive.Messages>
              {state.running && <Typing />}
              {state.finished && !state.running && (
                <div className="chat-finished">
                  <p>相談は終わりました。</p>
                  <button type="button" className="button-primary" onClick={restart}>
                    新しい相談を始める
                  </button>
                </div>
              )}
            </ThreadPrimitive.Viewport>
            {waitingForMessage && <Composer />}
          </ThreadPrimitive.Root>
        </AssistantRuntimeProvider>
      </ChatViewContext.Provider>
    </section>
  )
}

function TextBubble({ role, text }: { role: string; text: string }) {
  if (role === 'user') return <p className="bubble is-user">{text}</p>
  // The runtime adds an empty assistant message while a response is running; the typing dots stand for it.
  if (!text) return null
  return (
    <div className="assistant-row">
      <span className="assistant-avatar" aria-hidden="true">
        <AssistantIcon size={18} />
      </span>
      <div className="bubble is-assistant">
        <Markdown>{text}</Markdown>
      </div>
    </div>
  )
}

function Typing() {
  return (
    <div className="typing" aria-label="応答を待っています">
      <span />
      <span />
      <span />
    </div>
  )
}

// Hidden while a form is shown; slides up once free input is possible (F-UI-09).
function Composer() {
  const input = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    if (!isNarrow()) input.current?.focus()
  }, [])
  return (
    <ComposerPrimitive.Root className="composer">
      <label htmlFor="chat-input" className="visually-hidden">
        メッセージ
      </label>
      <ComposerPrimitive.Input id="chat-input" ref={input} className="composer-input" placeholder="メッセージを入力" rows={1} />
      <ComposerPrimitive.Send className="composer-send" aria-label="送信">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 19V5M6 11l6-6 6 6" />
        </svg>
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  )
}

function ItemView({ id }: { id: string }) {
  const { items } = useChatView()
  const item = items.get(id)
  if (!item) return null
  switch (item.kind) {
    case 'status':
      return <p className="chat-note">{item.done ? 'サービスを調べました' : 'サービスを調べています…'}</p>
    case 'opened':
      return <p className="chat-note">表示しました</p>
    case 'card':
      return <CardView item={item} />
    case 'suggestions':
      return <SuggestionsView item={item} />
    case 'form':
      return <FormView item={item} />
    case 'end':
      return <EndView item={item} />
    case 'emergency':
      return <EmergencyView />
    case 'error':
      return <p className="chat-error" role="alert">{item.text}</p>
    default:
      return null
  }
}
