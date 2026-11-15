// Chat parts drawn from tool calls and input requests (docs/design.md 3.2).
import { useState, type FormEvent } from 'react'
import { useChatView } from './ChatPanel.tsx'
import { emergencyContacts } from './emergency.ts'
import type { Item, JsonSchemaField } from './state.ts'
import { summarize } from './summary.ts'

const ArrowIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
)

// The destination card, shared by PC and mobile (F-UI-05).
export function CardView({ item }: { item: Item & { kind: 'card' } }) {
  const { open, shown } = useChatView()
  const summary = summarize(item.url, item.count)
  if (!summary) return null
  const isShown = shown.has(item.id)
  return (
    <div className="destination-card">
      <div className="destination-head">
        <span className="destination-icon" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            {summary.kind === 'search' ? (
              <>
                <circle cx="11" cy="11" r="6" />
                <path d="m20 20-4-4" />
              </>
            ) : (
              <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
            )}
          </svg>
        </span>
        <div className="destination-text">
          <p className="destination-label">{summary.label}</p>
          <p className="destination-title">{summary.title}</p>
          <p className="destination-detail">{summary.detail}</p>
        </div>
      </div>
      {isShown ? (
        <div className="destination-shown">
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m5 12 5 5 9-10" />
            </svg>
            表示しました
          </span>
          <button type="button" className="button-outline" onClick={() => open(item)}>
            もう一度表示
          </button>
        </div>
      ) : (
        <button type="button" className="destination-open" onClick={() => open(item)}>
          表示する
          <ArrowIcon />
        </button>
      )}
    </div>
  )
}

export function SuggestionsView({ item }: { item: Item & { kind: 'suggestions' } }) {
  const { consultation } = useChatView()
  const { items, running, pending } = consultation.state
  const index = items.findIndex((i) => i.id === item.id)
  // Only the latest suggestions answer the current question.
  const active = !running && pending?.kind === 'message' && !items.slice(index + 1).some((i) => i.kind === 'user' || i.kind === 'suggestions')
  if (!active) return null
  return (
    <div className="suggestions">
      {item.options.map((option, i) => (
        <button key={option} type="button" className={`suggestion${i === 0 ? ' is-first' : ''}`} onClick={() => consultation.sendText(option)}>
          {option}
        </button>
      ))}
    </div>
  )
}

export function FormView({ item }: { item: Item & { kind: 'form' } }) {
  const { consultation } = useChatView()
  const { running, pending } = consultation.state
  const active = !running && pending?.kind === 'form' && pending.callId === item.callId && !item.submitted
  const [value, setValue] = useState<Record<string, unknown>>({})
  const shownValue = item.submitted ?? value
  const required = item.schema.required ?? []
  const complete = required.every((key) => shownValue[key] !== undefined && shownValue[key] !== '')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (active && complete) consultation.answerForm(item.callId, value)
  }

  if (item.submitted && 'skipped' in item.submitted) return <p className="chat-note">アンケートはスキップしました</p>
  return (
    <form className="chat-form" onSubmit={submit} aria-label={item.schema.title}>
      {item.schema.title && <p className="chat-form-title">{item.form === 'profile' ? 'あなたについて教えてください' : 'アンケート'}</p>}
      {Object.entries(item.schema.properties).map(([key, field]) => (
        <Field key={key} name={key} field={field} value={shownValue[key]} disabled={!active} onChange={(v) => setValue({ ...value, [key]: v })} />
      ))}
      {!item.submitted && (
        <div className="chat-form-actions">
          <button type="submit" className="button-primary" disabled={!active || !complete}>
            {item.form === 'profile' ? '相談をはじめる' : '送信する'}
          </button>
          {item.skippable && (
            <button type="button" className="button-text" disabled={!active} onClick={() => consultation.answerForm(item.callId, { skipped: true })}>
              スキップ
            </button>
          )}
        </div>
      )}
    </form>
  )
}

function Field({ name, field, value, disabled, onChange }: { name: string; field: JsonSchemaField; value: unknown; disabled: boolean; onChange: (v: unknown) => void }) {
  const id = `field-${name}`
  const title = field.title ?? name
  // Short choices and small integer ranges become pill buttons; long lists a select.
  const choices =
    field.enum ??
    (field.type === 'integer' && field.minimum !== undefined && field.maximum !== undefined && field.maximum - field.minimum <= 9
      ? Array.from({ length: field.maximum - field.minimum + 1 }, (_, i) => String(field.minimum! + i))
      : null)
  if (choices && choices.length <= 5) {
    return (
      <fieldset className="chat-field">
        <legend>{title}</legend>
        {field.description && <p className="chat-field-hint">{field.description}</p>}
        <div className="pill-choices">
          {choices.map((choice) => {
            const v = field.type === 'integer' ? Number(choice) : choice
            return (
              <label key={choice} className={`pill-choice${value === v ? ' is-selected' : ''}`}>
                <input type="radio" name={id} checked={value === v} disabled={disabled} onChange={() => onChange(v)} />
                {choice}
              </label>
            )
          })}
        </div>
      </fieldset>
    )
  }
  return (
    <label className="chat-field" htmlFor={id}>
      <span className="chat-field-title">{title}</span>
      {choices ? (
        <select id={id} value={String(value ?? '')} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          <option value="">選んでください</option>
          {choices.map((choice) => (
            <option key={choice}>{choice}</option>
          ))}
        </select>
      ) : (
        <textarea id={id} rows={3} maxLength={field.maxLength} value={String(value ?? '')} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  )
}

export function EndView({ item }: { item: Item & { kind: 'end' } }) {
  const { consultation } = useChatView()
  const { running, pending } = consultation.state
  const active = !running && pending?.kind === 'approval' && pending.approvalId === item.approvalId
  return (
    <div className="end-confirm">
      <p className="bubble is-assistant">相談を終わりにしますか？</p>
      {item.approved === undefined ? (
        <div className="suggestions">
          <button type="button" className="suggestion is-first" disabled={!active} onClick={() => consultation.approveEnd(item.approvalId, true)}>
            終わりにする
          </button>
          <button type="button" className="suggestion" disabled={!active} onClick={() => consultation.approveEnd(item.approvalId, false)}>
            まだ続ける
          </button>
        </div>
      ) : (
        <p className="bubble is-user">{item.approved ? '終わりにする' : 'まだ続ける'}</p>
      )}
    </div>
  )
}

export function EmergencyView() {
  return (
    <div className="emergency" role="note">
      <p className="emergency-title">{emergencyContacts.title}</p>
      <ul>
        {emergencyContacts.contacts.map((c) => (
          <li key={c.phone}>
            <span>
              {c.name} ({c.detail})
            </span>
            <a href={`tel:${c.phone}`}>{c.phone}</a>
          </li>
        ))}
      </ul>
    </div>
  )
}
