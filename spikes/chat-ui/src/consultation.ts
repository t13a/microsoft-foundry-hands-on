// Turns the hosted agent's Responses stream into chat state, and chat actions into Responses input.
import OpenAI from 'openai'
import { useCallback, useRef, useState } from 'react'

export type TextPart = { type: 'text'; text: string }
export type ToolPart = {
  type: 'tool-call'
  toolCallId: string
  toolName: string
  args: Record<string, unknown>
  result?: unknown
  approvalId?: string
  approved?: boolean
}
export type Part = TextPart | ToolPart
export type ChatMessage = { id: string; role: 'user' | 'assistant'; parts: Part[] }

export type InputRequest = {
  request_type: 'user_message' | 'form'
  message: string
  metadata: { form?: string; schema?: JsonSchema }
}
export type JsonSchema = {
  properties: Record<string, { title?: string; type?: string; enum?: string[]; minimum?: number; maximum?: number }>
  required?: string[]
}

const client = new OpenAI({ baseURL: `${location.origin}/api`, apiKey: 'unused', dangerouslyAllowBrowser: true })

type Input = OpenAI.Responses.ResponseCreateParams['input']

export function useConsultation(onNavigate: (url: string) => void, currentUrl: () => string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [finished, setFinished] = useState(false)
  const session = useRef(crypto.randomUUID().replaceAll('-', ''))
  const previous = useRef<string | undefined>(undefined)

  // Mirror of the latest messages for reads inside the streaming loop.
  const messagesRef = useRef<ChatMessage[]>([])
  const update = useCallback(
    (fn: (draft: ChatMessage[]) => ChatMessage[]) =>
      setMessages((prev) => {
        const next = fn(prev)
        messagesRef.current = next
        return next
      }),
    [],
  )

  const run = useCallback(
    async (input: Input) => {
      setIsRunning(true)
      const id = crypto.randomUUID()
      update((m) => [...m, { id, role: 'assistant', parts: [] }])
      const patch = (fn: (parts: Part[]) => Part[]) =>
        update((m) => m.map((msg) => (msg.id === id ? { ...msg, parts: fn(msg.parts) } : msg)))
      // Results and approvals can answer a tool call that arrived in an earlier response.
      const patchAll = (fn: (part: Part) => Part) =>
        update((m) => m.map((msg) => ({ ...msg, parts: msg.parts.map(fn) })))
      let pending = false
      try {
        const stream = await client.responses.create({
          input,
          stream: true,
          store: true,
          previous_response_id: previous.current,
          // Foundry-specific field, passed through as-is.
          ...({ agent_session_id: session.current } as object),
        })
        for await (const event of stream) {
          if (event.type === 'response.output_text.delta') {
            patch((parts) => {
              const last = parts.at(-1)
              return last?.type === 'text'
                ? [...parts.slice(0, -1), { ...last, text: last.text + event.delta }]
                : [...parts, { type: 'text', text: event.delta }]
            })
          } else if (event.type === 'response.output_item.done') {
            const item = event.item as unknown as Record<string, string>
            if (item.type === 'function_call') {
              const args = JSON.parse(item.arguments || '{}')
              const isRequest = item.name === 'request_info'
              patch((parts) => [
                ...parts,
                {
                  type: 'tool-call',
                  toolCallId: item.call_id,
                  toolName: item.name,
                  args: isRequest ? args.request : args,
                },
              ])
            } else if (item.type === 'function_call_output') {
              const result = JSON.parse(item.output || 'null')
              patchAll((p) => (p.type === 'tool-call' && p.toolCallId === item.call_id ? { ...p, result } : p))
              const call = messagesRef.current
                .flatMap((m) => m.parts)
                .find((p): p is ToolPart => p.type === 'tool-call' && p.toolCallId === item.call_id)
              if (call?.toolName === 'propose_display' && result?.url) onNavigate(result.url)
            } else if (item.type === 'mcp_approval_request') {
              // The approval request isn't linked to its function_call by ID; match the latest unpaired call.
              patch((parts) => {
                const index = parts.findLastIndex(
                  (p) => p.type === 'tool-call' && p.toolName === item.name && !p.approvalId,
                )
                return parts.map((p, i) => (i === index ? { ...(p as ToolPart), approvalId: item.id } : p))
              })
            }
          } else if (event.type === 'response.completed') {
            previous.current = event.response.id
            const output = event.response.output as unknown as Record<string, string>[]
            const answered = new Set(output.filter((o) => o.type === 'function_call_output').map((o) => o.call_id))
            pending = output.some(
              (o) =>
                (o.type === 'function_call' && o.name === 'request_info' && !answered.has(o.call_id)) ||
                o.type === 'mcp_approval_request',
            )
          } else if (event.type === 'response.failed') {
            patch((parts) => [...parts, { type: 'text', text: `エラー: ${event.response.error?.message}` }])
          }
        }
      } finally {
        setIsRunning(false)
        if (!pending) setFinished(true)
      }
    },
    [onNavigate, update],
  )

  const start = useCallback(() => run('start'), [run])

  const reply = useCallback(
    (toolCallId: string, value: unknown) =>
      run([{ type: 'function_call_output', call_id: toolCallId, output: JSON.stringify(value) }]),
    [run],
  )

  const sendText = useCallback(
    (text: string) => {
      const request = [...messages]
        .reverse()
        .flatMap((m) => [...m.parts].reverse())
        .find((p): p is ToolPart => p.type === 'tool-call' && p.toolName === 'request_info' && p.result === undefined)
      if (!request || (request.args as InputRequest).request_type !== 'user_message') return Promise.resolve()
      update((m) => [
        ...m.map((msg) => ({
          ...msg,
          parts: msg.parts.map((p) => (p === request ? { ...p, result: { text } } : p)),
        })),
        { id: crypto.randomUUID(), role: 'user', parts: [{ type: 'text', text }] },
      ])
      return reply(request.toolCallId, { text, currentUrl: currentUrl() })
    },
    [messages, reply, update, currentUrl],
  )

  const answerForm = useCallback(
    (toolCallId: string, value: Record<string, unknown>) => {
      update((m) =>
        m.map((msg) => ({
          ...msg,
          parts: msg.parts.map((p) => (p.type === 'tool-call' && p.toolCallId === toolCallId ? { ...p, result: value } : p)),
        })),
      )
      return reply(toolCallId, value)
    },
    [reply, update],
  )

  const approve = useCallback(
    (part: ToolPart, approved: boolean) => {
      update((m) =>
        m.map((msg) => ({
          ...msg,
          parts: msg.parts.map((p) => (p === part ? { ...part, approved } : p)),
        })),
      )
      return run([{ type: 'mcp_approval_response', approval_request_id: part.approvalId!, approve: approved }])
    },
    [run, update],
  )

  const waitingForMessage =
    !isRunning &&
    messages.some((m) =>
      m.parts.some(
        (p) =>
          p.type === 'tool-call' &&
          p.toolName === 'request_info' &&
          p.result === undefined &&
          (p.args as InputRequest).request_type === 'user_message',
      ),
    )

  return { messages, isRunning, finished, waitingForMessage, start, sendText, answerForm, approve }
}
