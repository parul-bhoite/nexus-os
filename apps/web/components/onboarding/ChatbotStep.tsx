'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import {
  type AgentState,
  type NextQuestion,
  ModelUnavailableError,
  describeCompany,
  nextQuestion,
  openDiscovery,
  submitAnswer,
} from '@/lib/agent-onboarding-client'
import { AuthError } from '@/lib/auth-client'
import { useSlowLabel } from '@/lib/slow'
import { PresenceMark } from '@/components/onboarding/OnboardingAura'
import { greetingFor, transcript as transcriptMinusLiveQuestion } from '@/components/onboarding/AgentOnboarding'

/**
 * Step 3 of the stepped onboarding (ADR 0073): the adaptive interview, and
 * nothing else.
 *
 * Unlike the retired `ConversationalOnboarding`, this step does **not** host
 * department selection, documents, tools, the brief/persona confirmations or a
 * live Brain panel — those are their own steps now, or removed. It handles
 * exactly three things: the "scanning your company" loader while the site is
 * read, the three-question fallback when the site cannot be read, and the
 * agent's discovery questions. When the engine leaves `discovery` for
 * `documents`, the step is done and `onComplete` fires.
 *
 * The brief is auto-confirmed by the orchestrator before this mounts, so this
 * only ever sees `analysing` (loader / describe) or `discovery`.
 */

const DISCOVERY_FIELD = 'persona.stated_purpose'

export function ChatbotStep({
  state,
  onState,
  onComplete,
  onBusyChange,
}: {
  state: AgentState
  onState: (next: AgentState) => void
  onComplete: () => void
  onBusyChange?: (busy: boolean) => void
}) {
  const router = useRouter()
  const [question, setQuestion] = useState<NextQuestion | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState<(() => void) | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    onBusyChange?.(busy !== null)
  }, [busy, onBusyChange])

  const run = useCallback(
    async (label: string, work: () => Promise<void>) => {
      setBusy(label)
      setError(null)
      setRetry(null)
      try {
        await work()
      } catch (cause) {
        setRetry(() => () => void run(label, work))
        if (cause instanceof ModelUnavailableError) {
          setBlocked(cause.message)
          return
        }
        if (cause instanceof AuthError && (cause.status === 401 || cause.status === 403)) {
          router.replace(`/login?next=${encodeURIComponent('/onboarding/agent')}`)
          return
        }
        setError(cause instanceof Error ? cause.message : 'Something went wrong.')
      } finally {
        setBusy(null)
      }
    },
    [router],
  )

  // When the engine reports discovery is finished it has already moved to
  // `documents`; hand control back to the orchestrator rather than rendering an
  // empty chat.
  useEffect(() => {
    if (state.phase === 'documents' || state.phase === 'tools') onComplete()
  }, [state.phase, onComplete])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [state.turns.length, question, busy])

  const slowLabel = useSlowLabel(
    busy !== null,
    'Working…',
    busy ?? 'Scanning your company…',
    'Still reading. Going through the site and writing up what is there usually takes about half a minute.',
  )

  if (blocked) return <Blocked message={blocked} />

  const unreadable = state.phase === 'analysing' && state.site_unreadable === true
  const scanning = state.phase === 'analysing' && !unreadable

  const discoveryAnswered = state.turns.some(
    (turn) => turn.role === 'user' && turn.target === DISCOVERY_FIELD,
  )

  const ask: { question: string; choices?: string[]; onSubmit: (text: string) => void } | null =
    state.phase === 'discovery' && !discoveryAnswered && !question
      ? {
          question: 'What are you responsible for, day to day?',
          onSubmit: (text) =>
            void run('Thinking…', async () => {
              const turn = await openDiscovery(text)
              onState(turn.state)
              setDraft('')
              setQuestion(turn.question ?? (await nextQuestion()))
            }),
        }
      : question && !question.done && question.question
        ? {
            question: question.question,
            choices: question.choices,
            onSubmit: (text) =>
              void run('Thinking…', async () => {
                const turn = await submitAnswer(text)
                onState(turn.state)
                setDraft('')
                setQuestion(turn.question ?? (await nextQuestion()))
              }),
          }
        : null

  return (
    <>
      <div
        role="log"
        aria-live="polite"
        aria-label="Conversation with your setup assistant"
        className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 overflow-y-auto px-6 py-6"
      >
        <Greeting viewer={state.viewer} />

        {scanning && <ScanningCard label={slowLabel} domain={state.domain} pages={state.pages_read} />}

        {transcriptMinusLiveQuestion(state.turns, question).map((turn, index) => (
          <Bubble key={index} turn={turn} />
        ))}

        {unreadable && (
          <Describe
            domain={state.domain}
            disabled={busy !== null}
            onSubmit={(fields) =>
              void run('Saving what you told me…', async () => {
                onState(await describeCompany(fields))
                setQuestion(null)
              })
            }
          />
        )}

        {ask && <Ask question={ask.question} choices={ask.choices} onSubmit={ask.onSubmit} disabled={busy !== null} />}

        {busy && !scanning && <TypingBubble label={busy} />}

        {error && (
          <div className="rounded-lg bg-clay-100 px-3 py-2">
            <p role="alert" className="text-sm text-clay-600">
              {error}
            </p>
            {retry && (
              <button
                type="button"
                onClick={retry}
                disabled={busy !== null}
                className="mt-2 min-h-[2.75rem] rounded-full border border-clay-400 px-4 text-sm font-medium text-clay-600 hover:bg-clay-200 disabled:opacity-50"
              >
                Try again
              </button>
            )}
          </div>
        )}
        <div ref={endRef} />
      </div>

      {ask && (
        <Composer
          label={ask.choices && ask.choices.length > 0 ? 'Or answer in your own words' : 'Answer in your own words'}
          value={draft}
          onChange={setDraft}
          onSubmit={ask.onSubmit}
          disabled={busy !== null}
        />
      )}
    </>
  )
}

/* ── Pieces ─────────────────────────────────────────────────── */

function AgentBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex animate-rise justify-start">
      <div className="max-w-[34rem] rounded-2xl rounded-bl-md border border-bone-200/70 bg-white/80 px-4 py-3 text-sm leading-relaxed text-ink shadow-paper backdrop-blur-sm">
        {children}
      </div>
    </div>
  )
}

function Greeting({ viewer }: { viewer?: AgentState['viewer'] }) {
  const line = greetingFor(viewer)
  if (!line) return null
  return <AgentBubble>{line}</AgentBubble>
}

function Bubble({ turn }: { turn: { role: string; text: string; target: string | null; scope: number | null } }) {
  if (turn.role !== 'user') return <AgentBubble>{turn.text}</AgentBubble>
  return (
    <div className="flex justify-end">
      <div className="max-w-[34rem] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-bone-50">{turn.text}</div>
    </div>
  )
}

function TypingBubble({ label }: { label: string }) {
  return (
    <div className="flex animate-rise justify-start" role="status" aria-live="polite">
      <div className="flex max-w-[34rem] items-center gap-3 rounded-2xl rounded-bl-md border border-bone-200/70 bg-white/80 px-4 py-3 shadow-paper backdrop-blur-sm">
        <span aria-hidden className="flex items-end gap-1">
          {[0, 1, 2].map((dot) => (
            <span
              key={dot}
              className="h-1.5 w-1.5 animate-typing-dot rounded-full bg-steel-500"
              style={{ animationDelay: `${dot * 160}ms` }}
            />
          ))}
        </span>
        <span className="text-sm leading-relaxed text-ink-500">{label}</span>
      </div>
    </div>
  )
}

/** The "scanning your company" loader the product owner asked for (ADR 0073). */
function ScanningCard({ label, domain, pages }: { label: string; domain: string | null; pages: string[] }) {
  return (
    <div className="flex animate-rise justify-start" role="status" aria-live="polite">
      <div className="max-w-[34rem] rounded-2xl rounded-bl-md border border-bone-200/70 bg-white/80 px-4 py-3 shadow-paper backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <PresenceMark state="thinking" size={26} />
          <p className="text-sm font-medium text-ink">
            {domain ? `Scanning ${domain}…` : 'Scanning your company…'}
          </p>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-ink-500">{label}</p>
        {pages.length > 0 && (
          <>
            <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-ink-400">
              {pages.length === 1 ? '1 page read' : `${pages.length} pages read`}
            </p>
            <ul className="mt-1 flex flex-col gap-0.5">
              {pages.map((url) => (
                <li key={url} className="truncate text-xs text-ink-500">
                  {url}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-bone-300 bg-white/90 p-4 backdrop-blur-sm">{children}</div>
}

function Describe({
  domain,
  onSubmit,
  disabled,
}: {
  domain: string | null
  onSubmit: (fields: { profile: string; target_customers: string; goals: string }) => void
  disabled: boolean
}) {
  const [profile, setProfile] = useState('')
  const [customers, setCustomers] = useState('')
  const [goals, setGoals] = useState('')
  const ready = profile.trim() && customers.trim() && goals.trim()

  return (
    <>
      <AgentBubble>
        <p>
          I could not read {domain ?? 'your website'} — it may be behind bot protection, or there
          may be nothing there yet.
        </p>
        <p className="mt-2 text-ink-500">That is not a problem. Tell me the three things I would have looked for.</p>
      </AgentBubble>
      <Card>
        <div className="flex flex-col gap-4">
          {(
            [
              ['What does the company do?', profile, setProfile],
              ['Who actually buys from you?', customers, setCustomers],
              ['What would make the next twelve months a success?', goals, setGoals],
            ] as const
          ).map(([label, value, setValue]) => (
            <div key={label}>
              <label htmlFor={`describe-${label}`} className="text-sm font-medium text-ink-600">
                {label}
              </label>
              <textarea
                id={`describe-${label}`}
                rows={2}
                value={value}
                disabled={disabled}
                onChange={(event) => setValue(event.target.value)}
                className="mt-1 w-full rounded-xl border border-bone-300 bg-white px-3 py-2 text-sm text-ink"
              />
            </div>
          ))}
        </div>
        <button
          type="button"
          disabled={disabled || !ready}
          onClick={() => onSubmit({ profile: profile.trim(), target_customers: customers.trim(), goals: goals.trim() })}
          className="mt-4 min-h-[2.75rem] rounded-full bg-ink px-5 text-sm font-medium text-bone-50 disabled:opacity-50"
        >
          That is us — keep going
        </button>
      </Card>
    </>
  )
}

function Ask({
  question,
  choices = [],
  onSubmit,
  disabled,
}: {
  question: string
  choices?: string[]
  onSubmit: (text: string) => void
  disabled: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <AgentBubble>{question}</AgentBubble>
      {choices.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {choices.map((choice) => (
            <button
              key={choice}
              type="button"
              disabled={disabled}
              onClick={() => onSubmit(choice)}
              className="min-h-[2.75rem] rounded-full border border-bone-300 bg-white/70 px-4 text-sm text-ink-600 hover:border-steel-400 disabled:opacity-50"
            >
              {choice}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Composer({
  label,
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  onSubmit: (text: string) => void
  disabled: boolean
}) {
  return (
    <div className="sticky bottom-0 z-10 w-full border-t border-bone-200 bg-bone-50/95 pb-5 pt-4 backdrop-blur">
      <div className="mx-auto w-full max-w-2xl px-6">
        <label htmlFor="answer" className="text-xs font-medium text-ink-600">
          {label}
        </label>
        <div className="mt-1 flex items-end gap-2">
          <textarea
            id="answer"
            rows={2}
            value={value}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                if (value.trim()) onSubmit(value)
              }
            }}
            className="w-full flex-1 rounded-xl border border-bone-300 bg-white px-3 py-2 text-sm text-ink"
          />
          <button
            type="button"
            onClick={() => onSubmit(value)}
            disabled={disabled || !value.trim()}
            className="h-11 min-w-[2.75rem] rounded-full bg-ink px-4 text-sm text-bone-50 disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

function Blocked({ message }: { message: string }) {
  return (
    <div className="mx-auto grid w-full max-w-read flex-1 place-items-center px-6 py-16">
      <div className="max-w-md rounded-2xl border border-bone-300 bg-white p-6">
        <h1 className="font-display text-lg text-ink">Guided onboarding is unavailable</h1>
        <p className="mt-2 text-sm text-ink-600">{message}</p>
        <p className="mt-3 text-xs text-ink-400">
          Sign-in and every existing workspace are unaffected. There is deliberately no fallback
          form — a questionnaire that quietly replaced the assistant would collect less and look the
          same.
        </p>
      </div>
    </div>
  )
}
