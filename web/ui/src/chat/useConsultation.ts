// Sends chat actions to the BFF as Responses input and folds the stream into ChatState.
// The OpenAI SDK parses the stream; only the mapping (state.ts) is our own (docs/design.md 3.1).
import OpenAI from 'openai'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  addOpened,
  addUserText,
  answerEnd,
  applyEvent,
  beginResponse,
  endResponse,
  failResponse,
  initialState,
  submitForm,
  type ChatState,
  type StreamEvent,
} from './state.ts'

type Input = OpenAI.Responses.ResponseCreateParams['input']

const client = new OpenAI({ baseURL: `${location.origin}/api`, apiKey: 'unused', dangerouslyAllowBrowser: true })

// Locally the caller picks the session; on Foundry the BFF drops it from the first request
// and the platform's session from the first response is used from then on (docs/design.md 6.2).
const newSession = () => crypto.randomUUID().replaceAll('-', '')

export type Consultation = ReturnType<typeof useConsultation>

export function useConsultation(currentUrl: () => string) {
  const [state, setState] = useState<ChatState>(() => initialState(newSession()))
  // The latest state, for reads inside async callbacks.
  const latest = useRef(state)
  const update = useCallback((fn: (s: ChatState) => ChatState) => {
    latest.current = fn(latest.current)
    setState(latest.current)
  }, [])
  // A card opened while a response is still streaming is reported once the workflow waits again.
  const queuedOpen = useRef<string | null>(null)
  const generation = useRef(0)
  const runRef = useRef<(input: Input) => Promise<void>>(async () => {})

  const run = useCallback(
    async (input: Input) => {
      const before = latest.current.pending
      const mine = generation.current
      update(beginResponse)
      let failed = false
      try {
        const { previousResponseId, sessionId } = latest.current
        const stream = await client.responses.create({
          input,
          stream: true,
          store: true,
          // Foundry rejects explicit nulls, so leave the field out on the first turn.
          ...(previousResponseId ? { previous_response_id: previousResponseId } : {}),
          ...({ agent_session_id: sessionId } as object),
        })
        for await (const event of stream) {
          if (mine !== generation.current) return // restarted meanwhile
          if (event.type === 'response.failed') failed = true
          else update((s) => applyEvent(s, event as StreamEvent))
        }
      } catch {
        failed = true
      }
      if (mine !== generation.current) return
      update((s) => (failed ? failResponse(s, before) : endResponse(s)))
      const pending = latest.current.pending
      if (!failed && queuedOpen.current && pending?.kind === 'message') {
        const url = queuedOpen.current
        queuedOpen.current = null
        void runRef.current([{ type: 'function_call_output', call_id: pending.callId, output: JSON.stringify({ text: '', url, event: 'opened' }) }])
      }
    },
    [update],
  )
  useEffect(() => {
    runRef.current = run
  }, [run])

  const start = useCallback(() => {
    generation.current += 1
    queuedOpen.current = null
    latest.current = initialState(newSession())
    setState(latest.current)
    void run('start')
  }, [run])

  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    start()
  }, [start])

  const sendText = useCallback(
    (text: string) => {
      const pending = latest.current.pending
      if (latest.current.running || pending?.kind !== 'message' || !text.trim()) return
      update((s) => addUserText(s, text))
      void run([{ type: 'function_call_output', call_id: pending.callId, output: JSON.stringify({ text, url: currentUrl() }) }])
    },
    [currentUrl, run, update],
  )

  // The user showed a destination card (F-AGT-23): tell the agent so it can ask whether it helped.
  const opened = useCallback(
    (url: string) => {
      update(addOpened)
      const { pending, running } = latest.current
      if (!running && pending?.kind === 'message') {
        void run([{ type: 'function_call_output', call_id: pending.callId, output: JSON.stringify({ text: '', url, event: 'opened' }) }])
      } else if (running) {
        queuedOpen.current = url
      }
    },
    [run, update],
  )

  const answerForm = useCallback(
    (callId: string, value: Record<string, unknown>) => {
      if (latest.current.running) return
      update((s) => submitForm(s, callId, value))
      void run([{ type: 'function_call_output', call_id: callId, output: JSON.stringify(value) }])
    },
    [run, update],
  )

  const approveEnd = useCallback(
    (approvalId: string, approved: boolean) => {
      if (latest.current.running) return
      update((s) => answerEnd(s, approvalId, approved))
      void run([{ type: 'mcp_approval_response', approval_request_id: approvalId, approve: approved }])
    },
    [run, update],
  )

  return { state, start, sendText, opened, answerForm, approveEnd }
}
