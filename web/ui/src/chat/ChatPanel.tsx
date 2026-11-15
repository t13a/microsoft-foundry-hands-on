import { AssistantIcon, BackIcon, CloseIcon, MoreIcon } from '../components/icons.tsx'
import { useChat } from './ChatContext.tsx'

// The chat area. Loaded lazily because it is opened from the CTA (docs/design.md 3.1).
// The conversation is implemented in S5; this is the frame only.
export default function ChatPanel() {
  const chat = useChat()
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
          <button type="button" className="icon-button" aria-label="メニュー">
            <MoreIcon />
          </button>
          <button type="button" className="icon-button chat-close" aria-label="チャットを閉じる" onClick={chat.hide}>
            <CloseIcon />
          </button>
        </span>
      </header>
      <div className="chat-body">
        <p className="chat-placeholder">相談の画面は準備中です。</p>
      </div>
    </section>
  )
}
