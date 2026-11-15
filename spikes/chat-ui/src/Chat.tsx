import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from '@assistant-ui/react'
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ChatMessage, InputRequest, JsonSchema, ToolPart } from './consultation'
import { useConsultation } from './consultation'

type Consultation = ReturnType<typeof useConsultation>
const ConsultationContext = createContext<{ c: Consultation; parts: Map<string, ToolPart>; onShow: (url: string) => void }>(
  null!,
)

const convertMessage = (message: ChatMessage): ThreadMessageLike => ({
  id: message.id,
  role: message.role,
  content: message.parts.map((p) =>
    p.type === 'text'
      ? { type: 'text', text: p.text }
      : { type: 'tool-call', toolCallId: p.toolCallId, toolName: p.toolName, args: p.args as never, result: p.result },
  ),
})

export function Chat({ onNavigate, currentUrl }: { onNavigate: (url: string) => void; currentUrl: () => string }) {
  const c = useConsultation(onNavigate, currentUrl)
  const started = useRef(false)
  useEffect(() => {
    if (!started.current) {
      started.current = true
      void c.start()
    }
  }, [c])

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const first = message.content[0]
      if (first?.type === 'text') await c.sendText(first.text)
    },
    [c],
  )
  const runtime = useExternalStoreRuntime({
    messages: c.messages,
    isRunning: c.isRunning,
    isSendDisabled: !c.waitingForMessage,
    convertMessage,
    onNew,
  })

  const parts = new Map(
    c.messages.flatMap((m) => m.parts.filter((p): p is ToolPart => p.type === 'tool-call').map((p) => [p.toolCallId, p])),
  )

  return (
    <ConsultationContext.Provider value={{ c, parts, onShow: onNavigate }}>
      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root className="thread">
          <ThreadPrimitive.Viewport className="thread-viewport">
            <ThreadPrimitive.Messages>
              {({ message }) => (
                <MessagePrimitive.Root className={`message ${message.role}`}>
                  <MessagePrimitive.Parts>
                    {({ part }) =>
                      part.type === 'text' ? (
                        <p className="bubble">{part.text}</p>
                      ) : part.type === 'tool-call' ? (
                        <ToolView toolCallId={part.toolCallId} />
                      ) : null
                    }
                  </MessagePrimitive.Parts>
                </MessagePrimitive.Root>
              )}
            </ThreadPrimitive.Messages>
          </ThreadPrimitive.Viewport>
          <p className="notice">※個人情報や機密情報は入力しないでください</p>
          {c.finished ? (
            <p className="finished">相談は終了しました。</p>
          ) : (
            <ComposerPrimitive.Root className="composer">
              <ComposerPrimitive.Input className="composer-input" placeholder="メッセージを入力" rows={1} />
              <ComposerPrimitive.Send className="action">送信</ComposerPrimitive.Send>
            </ComposerPrimitive.Root>
          )}
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>
    </ConsultationContext.Provider>
  )
}

function ToolView({ toolCallId }: { toolCallId: string }) {
  const { c, parts, onShow } = useContext(ConsultationContext)
  const part = parts.get(toolCallId)
  if (!part) return null
  const args = part.args as Record<string, never>

  switch (part.toolName) {
    case 'request_info': {
      const request = part.args as InputRequest
      if (request.request_type !== 'form') return null
      return (
        <SchemaForm
          title={request.message}
          schema={request.metadata.schema!}
          submitted={part.result as Record<string, unknown> | undefined}
          disabled={c.isRunning}
          onSubmit={(value) => c.answerForm(part.toolCallId, value)}
        />
      )
    }
    case 'propose_display': {
      const url = (part.result as { url?: string } | undefined)?.url
      return (
        <>
          <Confirm
            question={`${args.summary}が見つかりましたが、表示しますか？`}
            part={part}
            disabled={c.isRunning || !part.approvalId}
            onAnswer={c.approve}
          />
          {url && (
            <button className="action secondary" onClick={() => onShow(url)}>
              {url.startsWith('/search') ? '検索結果を表示' : 'カテゴリを表示'}
            </button>
          )}
        </>
      )
    }
    case 'propose_end':
      return <Confirm question="相談を終了しますか？" part={part} disabled={c.isRunning} onAnswer={c.approve} />
    case 'suggest_replies':
      return (
        <div className="choices">
          {(args.options as string[]).map((option) => (
            <button key={option} className="action" disabled={!c.waitingForMessage} onClick={() => c.sendText(option)}>
              {option}
            </button>
          ))}
        </div>
      )
    default:
      return <p className="tool-status">{part.result === undefined ? '調べています…' : '調べました'}</p>
  }
}

function Confirm({
  question,
  part,
  disabled,
  onAnswer,
}: {
  question: string
  part: ToolPart
  disabled: boolean
  onAnswer: (part: ToolPart, approved: boolean) => void
}) {
  return (
    <div className="confirm">
      <p className="bubble">{question}</p>
      {part.approved === undefined ? (
        <div className="choices">
          <button className="action" disabled={disabled} onClick={() => onAnswer(part, true)}>
            はい
          </button>
          <button className="action" disabled={disabled} onClick={() => onAnswer(part, false)}>
            いいえ
          </button>
        </div>
      ) : (
        <p className="answer">{part.approved ? 'はい' : 'いいえ'}</p>
      )}
    </div>
  )
}

function SchemaForm({
  title,
  schema,
  submitted,
  disabled,
  onSubmit,
}: {
  title: string
  schema: JsonSchema
  submitted?: Record<string, unknown>
  disabled: boolean
  onSubmit: (value: Record<string, unknown>) => void
}) {
  const [value, setValue] = useState<Record<string, unknown>>({})
  const required = schema.required ?? []
  const complete = required.every((key) => value[key] !== undefined && value[key] !== '')
  const done = submitted !== undefined

  return (
    <form
      className="schema-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (complete) onSubmit(value)
      }}
    >
      <p className="bubble">{title}</p>
      {Object.entries(schema.properties).map(([key, field]) => (
        <label key={key} className="field">
          <span>{field.title ?? key}</span>
          {field.enum ? (
            <select
              disabled={done || disabled}
              value={String((submitted ?? value)[key] ?? '')}
              onChange={(e) => setValue({ ...value, [key]: e.target.value })}
            >
              <option value="">選択してください</option>
              {field.enum.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          ) : field.type === 'integer' ? (
            <input
              type="number"
              min={field.minimum}
              max={field.maximum}
              disabled={done || disabled}
              value={String((submitted ?? value)[key] ?? '')}
              onChange={(e) => setValue({ ...value, [key]: e.target.value === '' ? '' : Number(e.target.value) })}
            />
          ) : (
            <textarea
              disabled={done || disabled}
              value={String((submitted ?? value)[key] ?? '')}
              onChange={(e) => setValue({ ...value, [key]: e.target.value })}
            />
          )}
        </label>
      ))}
      {!done && (
        <button className="action" type="submit" disabled={!complete || disabled}>
          送信
        </button>
      )}
    </form>
  )
}
