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
import { useDictation } from '@/lib/dictation'
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

/** The longest answer the composer accepts, and the height past which it scrolls. */
const MAX_ANSWER_CHARS = 1000
const MAX_INPUT_HEIGHT = 160

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
  // The answer just sent, shown as a user bubble straight away. The transcript
  // is server-driven — `state.turns` only grows once the round trip returns —
  // so without this the box stayed full and "Thinking…" appeared while what the
  // person had typed was nowhere on screen. Cleared the moment the real turn
  // lands in `state.turns`; left standing on error so the message is still
  // visible above the retry.
  const [pending, setPending] = useState<string | null>(null)
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

  // Resume a reload mid-interview.
  //
  // The pending question lives only in the persisted turns (the last agent
  // turn) — the state has no `question` field — but the composer renders from
  // *this component's* `question`, which starts null on every mount. So after
  // the opener is answered, a refresh left the person staring at the last
  // question with no input and no way to answer: `ask` needs `question`, and
  // nothing had rehydrated it. Re-fetch it once. `/next` is idempotent — it
  // returns the question already pending rather than inventing a new one
  // (verified against a live session), so this restores the interview exactly
  // where it was instead of skipping a turn.
  const resumedRef = useRef(false)
  useEffect(() => {
    if (resumedRef.current || question || busy) return
    if (state.phase !== 'discovery') return
    const openerAnswered = state.turns.some(
      (turn) => turn.role === 'user' && turn.target === DISCOVERY_FIELD,
    )
    if (!openerAnswered) return
    resumedRef.current = true
    void run('Picking up where we left off…', async () => {
      setQuestion(await nextQuestion())
    })
  }, [state.phase, state.turns, question, busy, run])

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
          // Starters, not a closed list. They give someone a way in on the one
          // answer the Brain most wants in their own words — clicking one sends
          // it as-is, but the invitation underneath stays "Or answer in your
          // own words" so the expectation is still prose, not a pick.
          choices: [
            'Leading a team',
            'Client delivery',
            'Sales & growth',
            'Product & strategy',
            'Operations & finance',
          ],
          onSubmit: (text) => {
            setDraft('')
            setPending(text)
            void run('Thinking…', async () => {
              const turn = await openDiscovery(text)
              onState(turn.state)
              setPending(null)
              setQuestion(turn.question ?? (await nextQuestion()))
            })
          },
        }
      : question && !question.done && question.question
        ? {
            question: question.question,
            choices: question.choices,
            onSubmit: (text) => {
              setDraft('')
              setPending(text)
              void run('Thinking…', async () => {
                const turn = await submitAnswer(text)
                onState(turn.state)
                setPending(null)
                setQuestion(turn.question ?? (await nextQuestion()))
              })
            },
          }
        : null

  return (
    <>
      <div
        role="log"
        aria-live="polite"
        aria-label="Conversation with your setup assistant"
        // `min-h-0` is load-bearing: without it this flex child refuses to
        // shrink below its content, so a conversation taller than the viewport
        // grows the log instead of scrolling it — which pushes the sticky
        // composer below the bottom edge and the input vanishes. With it, the
        // log scrolls internally and the composer stays pinned.
        className="min-h-0 flex-1 overflow-y-auto"
      >
        {/* `min-h-full` + `justify-end` keep the conversation anchored to the
            bottom, just above the composer — a short transcript no longer
            floats at the top of a tall screen with the input stranded a
            viewport away. When the thread grows past the height it scrolls
            normally and the newest turn stays in view. */}
        <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col justify-end gap-4 px-6 py-6">
        <Greeting viewer={state.viewer} />

        {scanning && <ScanningCard label={slowLabel} domain={state.domain} pages={state.pages_read} />}

        {state.brief.opening_line && !scanning && !unreadable && (
          <BriefLine line={state.brief.opening_line} />
        )}

        {transcriptMinusLiveQuestion(state.turns, question)
          // The engine appends `opening_line` verbatim as an agent turn
          // (onboarding_agent.read). `BriefLine` already renders that line with
          // its "correct me as we go" reassurance, so drop the raw duplicate
          // rather than show the company summary twice.
          .filter((turn) => !(turn.role !== 'user' && turn.text === state.brief.opening_line))
          .map((turn, index) => (
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

        {pending !== null && (
          <div className="flex animate-rise justify-end">
            <div className="max-w-[34rem] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-bone-50">
              {pending}
            </div>
          </div>
        )}

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

/**
 * A single, compact acknowledgement of what the crawl read — the product owner
 * asked for this instead of the old sectioned brief-confirmation card. It is
 * read-only (the brief is auto-confirmed by the orchestrator; corrections happen
 * as the conversation goes and on the final Brain step), so there are no
 * keep-going / something-is-wrong buttons here. `opening_line` is the
 * second-person one-liner `company-summary` writes.
 */
function BriefLine({ line }: { line: string }) {
  return (
    <AgentBubble>
      <p>{line}</p>
      <p className="mt-1.5 text-ink-500">If any of that is off, just tell me as we go — your version is the one every director works from.</p>
    </AgentBubble>
  )
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
        <div className="flex flex-wrap gap-1.5">
          {choices.map((choice) => (
            <button
              key={choice}
              type="button"
              disabled={disabled}
              onClick={() => onSubmit(choice)}
              className="inline-flex items-center gap-1 rounded-md border border-dashed border-bone-300 bg-transparent px-2 py-1 text-xs text-ink-400 transition-colors hover:border-steel-400 hover:bg-steel-100 hover:text-steel-600 disabled:opacity-50"
            >
              <span aria-hidden className="text-ink-300">
                +
              </span>
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
  // The draft as of this render, read when a phrase is transcribed rather than
  // closed over — `useDictation` holds its callback in a ref, so a closure over
  // `value` would append every phrase to whatever the box held when the mic was
  // switched on and the second sentence would delete the first.
  const latest = useRef(value)
  latest.current = value

  const dictation = useDictation((phrase) => {
    if (!phrase) return
    const current = latest.current
    const next = current.trim() ? `${current.trim()} ${phrase}` : phrase
    latest.current = next
    onChange(next)
  })

  // A disabled composer is a request in flight; leaving the mic open across it
  // would transcribe into a box that is about to be cleared.
  const { listening, stop } = dictation
  useEffect(() => {
    if (disabled && listening) stop()
  }, [disabled, listening, stop])

  // One line to start, growing upward as the answer does. The band is pinned to
  // the floor (`sticky bottom-0`), so a taller textarea extends toward the
  // conversation rather than off-screen. Capped at MAX_LINES; past that it
  // scrolls inside the box instead of swallowing the page.
  const taRef = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_HEIGHT)}px`
  }, [value])

  const nearLimit = value.length >= MAX_ANSWER_CHARS * 0.9

  return (
    <div className="sticky bottom-0 z-10 w-full pb-3 pt-2">
      <div className="mx-auto w-full max-w-2xl px-6">
        <div className="flex items-baseline justify-between">
          <label htmlFor="answer" className="text-xs font-medium text-ink-600">
            {label}
          </label>
          {nearLimit && (
            <span aria-live="polite" className="text-[11px] tabular-nums text-ink-400">
              {value.length}/{MAX_ANSWER_CHARS}
            </span>
          )}
        </div>
        {/* One rounded container holds the field, the mic and Send — a modern
            composer rather than three separate controls. The border lives on
            the shell and lifts on focus; the textarea inside is borderless and
            transparent so the whole thing reads as a single surface. */}
        <div
          className={`mt-1.5 flex items-end gap-1.5 rounded-2xl border bg-white px-2 py-1.5 shadow-e1 transition-colors focus-within:ring-2 focus-within:ring-steel-200 ${
            listening ? 'border-clay-400' : 'border-bone-300 focus-within:border-steel-400'
          }`}
        >
          <textarea
            id="answer"
            ref={taRef}
            rows={1}
            value={value}
            disabled={disabled}
            maxLength={MAX_ANSWER_CHARS}
            placeholder="Type your answer, or tap the mic to speak…"
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                if (value.trim()) onSubmit(value)
              }
            }}
            className="block max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed text-ink placeholder:text-ink-300 focus:outline-none"
          />
          {dictation.supported && (
            <button
              type="button"
              onClick={dictation.toggle}
              disabled={disabled}
              aria-pressed={listening}
              aria-label={listening ? 'Stop recording' : 'Answer by voice'}
              title={listening ? 'Stop recording' : 'Answer by voice'}
              className={`relative grid h-9 w-9 shrink-0 place-items-center rounded-full transition-colors disabled:opacity-40 ${
                listening
                  ? 'bg-clay-100 text-clay-600'
                  : 'text-ink-400 hover:bg-bone-100 hover:text-steel-600'
              }`}
            >
              <MicIcon />
              {listening && (
                <span
                  aria-hidden
                  className="absolute inset-0 animate-pulse-ring rounded-full border border-clay-400"
                />
              )}
            </button>
          )}
          <button
            type="button"
            onClick={() => onSubmit(value)}
            disabled={disabled || !value.trim()}
            aria-label="Send"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-bone-50 transition-opacity hover:opacity-90 disabled:opacity-30"
          >
            <SendIcon />
          </button>
        </div>

        {/* Interim words are shown beside the box, never spliced into it: the
            recogniser rewrites them in place and writing that into a controlled
            textarea makes the caret jump. Only finalised phrases reach the draft. */}
        {listening && (
          <p role="status" aria-live="polite" className="mt-1 text-xs text-clay-600">
            Listening{dictation.interim ? ` — “${dictation.interim}”` : '… speak when ready.'}
          </p>
        )}
        {dictation.error && (
          <p role="alert" className="mt-1 text-xs text-clay-600">
            {dictation.error}
          </p>
        )}
      </div>
    </div>
  )
}

function MicIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      className="h-4 w-4"
    >
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
    >
      <path d="M12 19V5" />
      <path d="M6 11l6-6 6 6" />
    </svg>
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
