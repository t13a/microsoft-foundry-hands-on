// Chat state built from the hosted agent's Responses stream (docs/design.md 3.2).
// Pure functions only, so the mapping can be tested without a server.

export type JsonSchemaField = {
  title?: string
  description?: string
  type?: string
  enum?: string[]
  minimum?: number
  maximum?: number
  maxLength?: number
}
export type JsonSchema = { title?: string; properties: Record<string, JsonSchemaField>; required?: string[] }

export type FormName = 'profile' | 'feedback'

export type Item =
  | { kind: 'assistant'; id: string; text: string; response: number }
  | { kind: 'user'; id: string; text: string }
  | { kind: 'status'; id: string; done: boolean; response: number }
  | { kind: 'opened'; id: string }
  | { kind: 'card'; id: string; url: string; count: number; response: number }
  | { kind: 'suggestions'; id: string; options: string[]; response: number }
  | { kind: 'form'; id: string; callId: string; form: FormName; schema: JsonSchema; skippable: boolean; submitted?: Record<string, unknown> }
  | { kind: 'end'; id: string; approvalId: string; approved?: boolean }
  | { kind: 'emergency'; id: string }
  | { kind: 'error'; id: string; text: string }

// What the workflow is waiting for after the latest response.
export type Pending =
  | { kind: 'message'; callId: string }
  | { kind: 'form'; callId: string }
  | { kind: 'approval'; approvalId: string }
  | null

export type ChatState = {
  items: Item[]
  pending: Pending
  running: boolean
  finished: boolean
  response: number // counter of responses, to group streamed text per response
  previousResponseId?: string
  sessionId: string
  calls: Record<string, string> // call_id -> tool name
}

export type OutputItem = { type: string; [key: string]: unknown }

// The subset of Responses stream events the chat reacts to.
type ResponseBody = { id: string; output: OutputItem[]; agent_session_id?: string }
export type StreamEvent = { type: string; delta?: string; item?: OutputItem; response?: ResponseBody }

const SEARCH_TOOLS = new Set(['list_categories', 'get_category', 'search_services'])
export const ERROR_TEXT = 'うまくお答えできませんでした。少し待ってから、もう一度お試しください。'

let counter = 0
const nextId = () => `i${++counter}`

export function initialState(sessionId: string): ChatState {
  return { items: [], pending: null, running: false, finished: false, response: 0, sessionId, calls: {} }
}

export function beginResponse(state: ChatState): ChatState {
  return { ...state, running: true, pending: null, response: state.response + 1 }
}

function parse(text: unknown): unknown {
  try {
    return JSON.parse(String(text ?? 'null'))
  } catch {
    return null
  }
}

// The agent calls its tools before it writes, but the card and the suggestions read as
// following the text, so the response's text goes in front of them.
const FOLLOWS_TEXT = new Set<Item['kind']>(['card', 'suggestions'])

function appendText(state: ChatState, text: string): ChatState {
  if (!text) return state
  const { items } = state
  let end = items.length
  while (end > 0 && FOLLOWS_TEXT.has(items[end - 1].kind) && (items[end - 1] as { response: number }).response === state.response) end--
  const last = items[end - 1]
  const continues = last?.kind === 'assistant' && last.response === state.response
  const merged: Item = continues ? { ...last, text: last.text + text } : { kind: 'assistant', id: nextId(), text, response: state.response }
  return { ...state, items: [...items.slice(0, continues ? end - 1 : end), merged, ...items.slice(end)] }
}

function add(state: ChatState, item: Item): ChatState {
  return { ...state, items: [...state.items, item] }
}

export function applyEvent(state: ChatState, event: StreamEvent): ChatState {
  switch (event.type) {
    case 'response.output_text.delta':
      return appendText(state, (event as { delta: string }).delta)
    case 'response.output_item.done':
      return applyItem(state, (event as { item: OutputItem }).item)
    case 'response.completed':
    case 'response.incomplete': {
      const response = event.response as ResponseBody
      const pending = findPending(response.output)
      return {
        ...state,
        previousResponseId: response.id,
        sessionId: response.agent_session_id || state.sessionId,
        pending,
        finished: pending === null,
      }
    }
    // response.failed is handled by the caller with failResponse.
    default:
      return state
  }
}

function applyItem(state: ChatState, item: OutputItem): ChatState {
  if (item.type === 'function_call') {
    const name = String(item.name)
    const callId = String(item.call_id)
    const args = parse(item.arguments) as Record<string, unknown> | null
    const next = { ...state, calls: { ...state.calls, [callId]: name } }
    if (name === 'request_info') {
      const request = (args?.request ?? {}) as { request_type?: string; message?: string; metadata?: Record<string, unknown> }
      // The request's message is its own bubble, apart from text streamed before it.
      const withMessage = request.message
        ? add(next, { kind: 'assistant', id: nextId(), text: request.message, response: state.response })
        : next
      if (request.request_type === 'form') {
        const metadata = request.metadata ?? {}
        return add(withMessage, {
          kind: 'form',
          id: nextId(),
          callId,
          form: metadata.form === 'feedback' ? 'feedback' : 'profile',
          schema: metadata.schema as JsonSchema,
          skippable: metadata.skippable === true,
        })
      }
      return withMessage
    }
    if (name === 'suggest_replies') {
      const options = Array.isArray(args?.options) ? (args.options as unknown[]).map(String) : []
      return options.length ? add(next, { kind: 'suggestions', id: nextId(), options, response: state.response }) : next
    }
    if (name === 'show_emergency_contacts') return add(next, { kind: 'emergency', id: nextId() })
    if (SEARCH_TOOLS.has(name)) {
      // One status line per response, however many searches the agent runs.
      if (state.items.some((i) => i.kind === 'status' && i.response === state.response)) return next
      return add(next, { kind: 'status', id: nextId(), done: false, response: state.response })
    }
    return next
  }
  if (item.type === 'function_call_output') {
    const name = state.calls[String(item.call_id)]
    const result = parse(item.output) as Record<string, unknown> | null
    if (name && SEARCH_TOOLS.has(name)) {
      return {
        ...state,
        items: state.items.map((i) => (i.kind === 'status' && i.response === state.response ? { ...i, done: true } : i)),
      }
    }
    if (name === 'propose_display' && typeof result?.url === 'string') {
      return add(state, { kind: 'card', id: nextId(), url: result.url, count: Number(result.count ?? 0), response: state.response })
    }
    return state
  }
  if (item.type === 'mcp_approval_request' && item.name === 'propose_end') {
    return add(state, { kind: 'end', id: nextId(), approvalId: String(item.id) })
  }
  return state
}

// A request_info call without its output is the workflow waiting for the user.
export function findPending(output: OutputItem[]): Pending {
  const approval = output.find((o) => o.type === 'mcp_approval_request')
  if (approval) return { kind: 'approval', approvalId: String(approval.id) }
  const answered = new Set(output.filter((o) => o.type === 'function_call_output').map((o) => String(o.call_id)))
  const call = output.find((o) => o.type === 'function_call' && o.name === 'request_info' && !answered.has(String(o.call_id)))
  if (!call) return null
  const request = (parse(call.arguments) as { request?: { request_type?: string } } | null)?.request
  return { kind: request?.request_type === 'form' ? 'form' : 'message', callId: String(call.call_id) }
}

// A failed request leaves the workflow where it was, so the user can try again.
export function failResponse(state: ChatState, before: Pending): ChatState {
  return { ...add(state, { kind: 'error', id: nextId(), text: ERROR_TEXT }), running: false, pending: before, finished: false }
}

export function endResponse(state: ChatState): ChatState {
  return { ...state, running: false }
}

export function addUserText(state: ChatState, text: string): ChatState {
  return add(state, { kind: 'user', id: nextId(), text })
}

export function addOpened(state: ChatState): ChatState {
  return add(state, { kind: 'opened', id: nextId() })
}

export function submitForm(state: ChatState, callId: string, value: Record<string, unknown>): ChatState {
  return { ...state, items: state.items.map((i) => (i.kind === 'form' && i.callId === callId ? { ...i, submitted: value } : i)) }
}

export function answerEnd(state: ChatState, approvalId: string, approved: boolean): ChatState {
  return { ...state, items: state.items.map((i) => (i.kind === 'end' && i.approvalId === approvalId ? { ...i, approved } : i)) }
}
