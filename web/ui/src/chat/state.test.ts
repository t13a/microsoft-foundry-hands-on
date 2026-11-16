import { describe, expect, it } from 'vitest'
import { categoryUrl, searchUrl } from '../urls.ts'
import { applyEvent, beginResponse, findPending, initialState, type ChatState, type OutputItem, type StreamEvent } from './state.ts'
import { summarize } from './summary.ts'

const call = (callId: string, name: string, args: unknown): OutputItem => ({
  type: 'function_call',
  call_id: callId,
  name,
  arguments: JSON.stringify(args),
})
const output = (callId: string, value: unknown): OutputItem => ({ type: 'function_call_output', call_id: callId, output: JSON.stringify(value) })
const done = (item: OutputItem): StreamEvent => ({ type: 'response.output_item.done', item })
const delta = (text: string): StreamEvent => ({ type: 'response.output_text.delta', delta: text })
const completed = (id: string, items: OutputItem[], extra: object = {}): StreamEvent => ({
  type: 'response.completed',
  response: { id, output: items, ...extra },
})

function run(state: ChatState, events: StreamEvent[]): ChatState {
  return events.reduce(applyEvent, beginResponse(state))
}

const yobou = categoryUrl(['子育て・教育', '健診・予防接種', '予防接種'], ['予防接種相談窓口'])
const ask = call('req-1', 'request_info', { request_id: 'r', request: { request_type: 'user_message', message: '', metadata: {} } })

describe('chat state', () => {
  it('shows the greeting and the profile form, then waits for the form', () => {
    const form = call('req-0', 'request_info', {
      request_id: 'r',
      request: { request_type: 'form', message: 'プロフィールを教えてください。', metadata: { form: 'profile', schema: { properties: {} } } },
    })
    const state = run(initialState('local'), [delta('ご利用'), delta('ありがとうございます。'), done(form), completed('resp-1', [form], { agent_session_id: 'platform' })])
    expect(state.items.map((i) => i.kind)).toEqual(['assistant', 'assistant', 'form'])
    expect(state.items.slice(0, 2)).toMatchObject([{ text: 'ご利用ありがとうございます。' }, { text: 'プロフィールを教えてください。' }])
    expect(state.pending).toEqual({ kind: 'form', callId: 'req-0' })
    expect(state).toMatchObject({ previousResponseId: 'resp-1', sessionId: 'platform', finished: false })
  })

  it('turns a search and a display proposal into one status line and a card', () => {
    const events = [
      delta('お調べします。'),
      done(call('c1', 'search_services', { query: '予防接種' })),
      done(output('c1', { count: 16 })),
      done(call('c2', 'get_category', { path: [] })),
      done(output('c2', {})),
      done(call('c3', 'propose_display', { urls: [yobou] })),
      done(output('c3', { url: yobou, count: 1 })),
      delta('見つかりました。'),
      done(ask),
      completed('resp-2', [ask]),
    ]
    const state = run(initialState('s'), events)
    // The text written after the card goes in front of it.
    expect(state.items.map((i) => i.kind)).toEqual(['assistant', 'status', 'assistant', 'card'])
    expect(state.items[1]).toMatchObject({ done: true })
    expect(state.items[3]).toMatchObject({ url: yobou, count: 1 })
    expect(state.pending).toEqual({ kind: 'message', callId: 'req-1' })
  })

  it('puts the question in front of its suggestions', () => {
    const state = run(initialState('s'), [
      done(call('c1', 'suggest_replies', { options: ['見つかった'] })),
      delta('お探しのものは'),
      delta('見つかりましたか？'),
    ])
    expect(state.items).toMatchObject([{ kind: 'assistant', text: 'お探しのものは見つかりましたか？' }, { kind: 'suggestions' }])
  })

  it('drops a failed display proposal', () => {
    const state = run(initialState('s'), [done(call('c1', 'propose_display', { urls: ['/c/x'] })), done(output('c1', { error: '表示できませんでした' }))])
    expect(state.items).toEqual([])
  })

  it('shows suggestions, the end confirmation and emergency contacts', () => {
    const approval: OutputItem = { type: 'mcp_approval_request', id: 'appr-1', name: 'propose_end', arguments: '{}' }
    const state = run(initialState('s'), [
      done(call('c1', 'suggest_replies', { options: ['見つかった', '別の条件で探したい'] })),
      done(call('c2', 'show_emergency_contacts', {})),
      done(call('c3', 'propose_end', {})),
      done(approval),
      completed('resp-3', [approval]),
    ])
    expect(state.items.map((i) => i.kind)).toEqual(['suggestions', 'emergency', 'end'])
    expect(state.pending).toEqual({ kind: 'approval', approvalId: 'appr-1' })
  })

  it('finishes when nothing is pending, including after an incomplete response', () => {
    expect(run(initialState('s'), [completed('r', [])]).finished).toBe(true)
    const incomplete: StreamEvent = { type: 'response.incomplete', response: { id: 'r', output: [ask] } }
    expect(run(initialState('s'), [incomplete]).pending).toEqual({ kind: 'message', callId: 'req-1' })
  })

  it('ignores answered input requests', () => {
    expect(findPending([ask, output('req-1', {})])).toBeNull()
  })
})

describe('summary', () => {
  it('summarizes categories and searches from the url', () => {
    expect(summarize(yobou, 1)).toEqual({
      kind: 'category',
      label: 'カテゴリ',
      title: '子育て・教育 › 健診・予防接種 › 予防接種',
      detail: '「予防接種相談窓口」を強調表示',
    })
    expect(summarize(categoryUrl(['A'], ['x', 'y', 'z']), 3)?.detail).toBe('「x」ほか 2 件を強調表示')
    expect(summarize(categoryUrl(['A']), 4)?.detail).toBe('4 件のサービス')
    expect(summarize(searchUrl('予防接種'), 16)).toMatchObject({ kind: 'search', title: '「予防接種」', detail: '16 件' })
  })
})
