'use client'

import { useCallback, useId, useRef, useState } from 'react'
import { askGlobal, type GlobalAnswer } from '@/lib/dashboard-client'

/**
 * The global assistant, as a floating widget on every signed-in page (ADR 0086).
 *
 * The shell renders this only when `assistant_enabled` is true, so while the
 * feature is dark nothing appears. It answers from the workspace's own figures,
 * insights and facts — single-turn, because the backend is: one question, one
 * answer or one refusal, with the refusal copy authored server-side (the model
 * never words its own "no").
 *
 * **It states no number the data did not supply.** That guarantee is enforced in
 * the API (`grounding/qa.py`); this component only renders what comes back, and
 * a refusal is rendered as the sentence we were given, never as an error.
 */
type State =
  | { kind: 'idle' }
  | { kind: 'asking' }
  | { kind: 'answer'; answer: GlobalAnswer }
  | { kind: 'error'; message: string }

export function AssistantWidget() {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [state, setState] = useState<State>({ kind: 'idle' })
  const panelId = useId()
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const ask = useCallback(async () => {
    const text = question.trim()
    if (!text || state.kind === 'asking') return
    setState({ kind: 'asking' })
    try {
      const answer = await askGlobal(text)
      setState({ kind: 'answer', answer })
    } catch {
      setState({ kind: 'error', message: 'Could not reach the assistant right now.' })
    }
  }, [question, state.kind])

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      {open ? (
        <section
          id={panelId}
          aria-label="Ask the assistant"
          className="flex w-[min(92vw,22rem)] flex-col gap-3 rounded-data border border-ink-100 bg-white p-4 shadow-e2"
        >
          <header className="flex items-baseline justify-between gap-3">
            <h2 className="font-display text-base text-ink-900">Ask about your numbers</h2>
            <span className="font-mono text-2xs text-ink-400">cites your own data</span>
          </header>

          <div aria-live="polite" className="min-h-[2.5rem] text-sm leading-relaxed text-ink-700">
            {state.kind === 'idle' ? (
              <p className="text-ink-500">
                Ask about a figure, an insight or something you told us. Answers come from your
                own data — nothing is made up.
              </p>
            ) : null}
            {state.kind === 'asking' ? <p className="text-ink-500">Reading your figures…</p> : null}
            {state.kind === 'error' ? <p className="text-clay-600">{state.message}</p> : null}
            {state.kind === 'answer' && state.answer.answered ? (
              <div className="flex flex-col gap-2">
                <p className="text-ink-800">{state.answer.prose}</p>
                {state.answer.grounded_on.length > 0 ? (
                  <p className="font-mono text-2xs text-ink-400">
                    from {state.answer.grounded_on.join(', ')}
                  </p>
                ) : null}
              </div>
            ) : null}
            {state.kind === 'answer' && !state.answer.answered ? (
              <p className="text-ink-600">{state.answer.sentence}</p>
            ) : null}
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault()
              void ask()
            }}
            className="flex flex-col gap-2"
          >
            <textarea
              ref={inputRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void ask()
                }
              }}
              rows={2}
              placeholder="e.g. what is our website performance score?"
              aria-label="Your question"
              className="w-full resize-none rounded-control border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 placeholder:text-ink-300 focus:outline-none focus:ring-2 focus:ring-steel-500"
            />
            <button
              type="submit"
              disabled={state.kind === 'asking' || question.trim().length === 0}
              className="self-end rounded-control bg-ink-900 px-3.5 py-2 text-sm font-medium text-white transition-opacity disabled:opacity-40"
            >
              Ask
            </button>
          </form>
        </section>
      ) : null}

      <button
        type="button"
        onClick={() => {
          setOpen((was) => !was)
          if (!open) window.setTimeout(() => inputRef.current?.focus(), 0)
        }}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex h-12 w-12 items-center justify-center rounded-full bg-ink-900 text-white shadow-e2 transition-transform hover:scale-105"
      >
        <span aria-hidden className="text-lg">
          {open ? '×' : '?'}
        </span>
        <span className="sr-only">{open ? 'Close the assistant' : 'Ask the assistant'}</span>
      </button>
    </div>
  )
}
