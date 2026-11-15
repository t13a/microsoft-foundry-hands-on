import { useChat } from '../chat/ChatContext.tsx'
import { ChatIcon } from './icons.tsx'

// The always-available button at the bottom of the content area (F-UI-02).
export default function ConsultButton() {
  const chat = useChat()
  if (chat.open || chat.heroCtaVisible) return null
  return (
    <div className="consult-dock">
      <button type="button" className="consult-button" onClick={chat.show}>
        <ChatIcon />
        {chat.started ? 'AI 相談を続ける' : 'AI に相談する'}
      </button>
    </div>
  )
}
