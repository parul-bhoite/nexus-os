'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'

import {
  type AgentState,
  type NextQuestion,
  ASSEMBLY_LABEL,
  ModelUnavailableError,
  assemblyDone,
  confirmBrief,
  declareTools,
  describeCompany,
  documentsDone,
  finish,
  nextQuestion,
  openDiscovery,
  read,
  readState,
  start,
  submitAnswer,
} from '@/lib/agent-onboarding-client'
import { AuthError } from '@/lib/auth-client'
import { fetchDepartments, saveDepartments, type DepartmentState } from '@/lib/settings-client'
import { useSlowLabel } from '@/lib/slow'
import { duration, easing, useMotionSafe } from '@/lib/motion'
import { BrainPanel } from '@/components/onboarding/BrainPanel'
import { DocumentsStep } from '@/components/onboarding/DocumentsStep'
import { ToolsStep } from '@/components/onboarding/ToolsStep'
import { OnboardingAura, PresenceMark, type AuraState } from '@/components/onboarding/OnboardingAura'
import {
  greetingFor,
  sentence,
  transcript as transcriptMinusLiveQuestion,
} from '@/components/onboarding/AgentOnboarding'

/**
 * Phase 1 of ADR 0069: the chat column + live Company Brain panel, over the
 * existing `onboarding_agent` engine.
 *
 * **This replaces `AgentOnboarding` as the mounted onboarding experience** —
 * see `OnboardingEntry`. `AgentOnboarding` is left in the tree unmodified per
 * the ADR's consequence; nothing here imports its internals except the three
 * functions it already exported for reuse (`greetingFor`, `sentence`,
 * `transcript`).
 *
 * **Department selection happens in the chat**, as quick-reply chips, between
 * the brief being confirmed and the first discovery question — the wireframe's
 * "pick your directors" beat. It is driven by `fetchDepartments`/
 * `saveDepartments`, not by the engine, because department choice is workspace
 * configuration and not a declared field the agent's catalogue owns. `deptStep`
 * tracks it locally so a refresh mid-pick resumes rather than re-asking: it is
 * seeded from `fetchDepartments()` on boot, alongside the agent's own state.
 *
 * **No model, no fabricated conversation.** `ModelUnavailableError` (503) —
 * raised by `start`/`read`/`openDiscovery`/`submitAnswer` — renders `Blocked`:
 * a plain sentence, no retry that cannot work, no catalogue fallback (ADR 0011
 * + 0069).
 */

type Phase = AgentState['phase']

const PHASE_LABEL: Record<Phase, string> = {
  analysing: 'Reading your website',
  brief: 'Checking what we found',
  discovery: 'A few quick questions',
  documents: 'Your documents',
  tools: 'Where your numbers live',
  persona: 'Confirm how we understood you',
  assembling: 'Building your Company Brain',
  ready: 'All set',
}

/**
 * Discrete progress markers, not a fraction over something uncountable.
 *
 * Each number is a real position in a fixed, ordered list of named stages —
 * the same discipline `AgentOnboarding`'s step rail uses for "Question 3 of
 * 5" and refuses for anything without a true denominator. Reading a website
 * has no countable unit, so the bar moves between named stages rather than
 * pretending to measure one.
 */
const PHASE_PROGRESS: Record<Phase, number> = {
  analysing: 10,
  brief: 25,
  discovery: 45,
  documents: 60,
  tools: 72,
  persona: 85,
  assembling: 95,
  ready: 100,
}

const DISCOVERY_FIELD = 'persona.stated_purpose'

type DeptStep =
  | { status: 'loading' }
  | { status: 'choosing'; options: DepartmentState[] }
  | { status: 'done'; selected: string[] }

export function ConversationalOnboarding() {
  const router = useRouter()
  const motionSafe = useMotionSafe()
  const [state, setState] = useState<AgentState | null>(null)
  const [question, setQuestion] = useState<NextQuestion | null>(null)
  const [draft, setDraft] = useState('')
  const [corrections, setCorrections] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>('Reading your website…')
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState<(() => void) | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)
  const [deptStep, setDeptStep] = useState<DeptStep>({ status: 'loading' })
  const [deptPicking, setDeptPicking] = useState<Set<string>>(new Set())
  const endRef = useRef<HTMLDivElement>(null)

  const guard = useCallback(async (label: string, work: () => Promise<void>) => {
    setBusy(label)
    setError(null)
    setRetry(null)
    try {
      await work()
    } catch (cause) {
      setRetry(() => () => void guard(label, work))
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
  }, [router])

  const booted = useRef(false)

  const boot = useCallback(async () => {
    const existing = await readState()
    if (existing.completed) {
      router.replace('/dashboard')
      return
    }
    let resumed = existing.active ? existing : await start()
    setState(resumed)

    if (resumed.phase === 'analysing' && resumed.turns.length === 0 && !resumed.site_unreadable) {
      setBusy('Reading what is on those pages…')
      resumed = await read()
      setState(resumed)
    }
    if (
      resumed.phase === 'discovery' &&
      resumed.turns.some((t) => t.role === 'user' && t.target === DISCOVERY_FIELD)
    ) {
      setBusy('Picking up where you left off…')
      const outstanding = await nextQuestion()
      setQuestion(outstanding)
      if (outstanding.done) setState(await readState())
    }

    // Seeded alongside the agent's own state so a refresh mid-pick resumes at
    // the chip screen rather than skipping it or re-asking it.
    const { departments } = await fetchDepartments()
    const selectable = departments.filter((d) => d.value !== 'executive')
    const alreadyChosen = selectable.filter((d) => d.running).map((d) => d.value)
    setDeptStep(
      alreadyChosen.length > 0
        ? { status: 'done', selected: alreadyChosen }
        : { status: 'choosing', options: selectable },
    )
  }, [router])

  useEffect(() => {
    if (booted.current) return
    booted.current = true
    void guard('Reading your website…', boot)
  }, [guard, boot])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [state?.turns.length, state?.phase, question, deptStep.status])

  const bootLabel = useSlowLabel(
    busy !== null,
    'Loading…',
    busy ?? 'Reading your website…',
    'Still reading. Going through the site and writing up what is there usually takes about half a minute.',
  )

  if (blocked) return <Blocked message={blocked} />
  if (!state) {
    return (
      <Booting
        label={bootLabel}
        error={error}
        onRetry={() => void guard('Reading your website…', boot)}
      />
    )
  }

  const unreadable = state.phase === 'analysing' && state.site_unreadable === true
  const reading = state.phase === 'analysing' && !unreadable

  const discoveryAnswered = state.turns.some(
    (turn) => turn.role === 'user' && turn.target === DISCOVERY_FIELD,
  )

  // The department beat sits between the brief closing and the interview's
  // opening question — the engine has already moved its own `phase` to
  // `discovery` by the time the brief is confirmed, so "has this beat
  // happened yet" is tracked here rather than read off `phase`.
  const showDeptPicker =
    deptStep.status === 'choosing' &&
    (state.phase === 'discovery' || state.phase === 'documents' || state.phase === 'tools')

  const ask: {
    question: string
    choices?: string[]
    hint?: string
    onSubmit: (text: string) => void
  } | null =
    showDeptPicker
      ? null
      : state.phase === 'discovery' && !discoveryAnswered && !question
        ? {
            question: 'What are you responsible for, day to day?',
            hint: 'This decides what gets asked next.',
            onSubmit: (text) =>
              void guard('Thinking…', async () => {
                const turn = await openDiscovery(text)
                setState(turn.state)
                setDraft('')
                setQuestion(turn.question ?? (await nextQuestion()))
              }),
          }
        : question && !question.done && question.question
          ? {
              question: question.question,
              choices: question.choices,
              hint: question.scope !== null ? `Stored as L${question.scope}` : undefined,
              onSubmit: (text) =>
                void guard('Thinking…', async () => {
                  const turn = await submitAnswer(text)
                  setState(turn.state)
                  setDraft('')
                  setQuestion(turn.question ?? (await nextQuestion()))
                }),
            }
          : null

  const aura: AuraState = busy ? 'thinking' : state.phase === 'ready' ? 'ready' : 'idle'

  const assemble = (
    until: (next: AgentState) => boolean,
    before?: () => Promise<AgentState>,
  ) => {
    void guard(ASSEMBLY_LABEL[state.phase] ?? 'Building…', async () => {
      if (before) setState(await before())
      let next = await finish()
      setState(next)
      for (let attempt = 0; attempt < 6 && !until(next) && !assemblyDone(next); attempt += 1) {
        const beforePhase = next.phase
        const beforeStep = next.assembly_step ?? 0
        setBusy(ASSEMBLY_LABEL[beforePhase] ?? 'Building…')
        next = await finish()
        setState(next)
        if (next.phase === beforePhase && (next.assembly_step ?? 0) === beforeStep) break
      }
    })
  }

  const chosenDepartments = deptStep.status === 'done' ? deptStep.selected : []

  return (
    <div className="relative flex min-h-screen flex-col lg:flex-row">
      <main
        id="main"
        tabIndex={-1}
        className="relative flex min-h-screen flex-1 flex-col bg-bone-100"
      >
        <OnboardingAura state={aura} />

        {/* `.obtop` — logo, the "Guided setup" chip, the phase label, the bar. */}
        <header className="relative z-10 border-b border-bone-200 bg-white/80 px-6 py-4 backdrop-blur-sm">
          <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3">
            <span className="flex items-center gap-2.5 font-display text-base font-semibold text-ink">
              <PresenceMark state={aura} />
              NEXUS <span className="font-normal opacity-60">OS</span>
            </span>
            <span className="rounded-full bg-steel-100 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-steel-700">
              Guided setup
            </span>
          </div>
          <div className="mx-auto mt-3 w-full max-w-2xl">
            <p className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-400">
              {PHASE_LABEL[state.phase]}
            </p>
            <div
              role="progressbar"
              aria-valuenow={PHASE_PROGRESS[state.phase]}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Setup progress"
              className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-bone-200"
            >
              <motion.div
                className="h-full rounded-full bg-gold-500"
                initial={false}
                animate={{ width: `${PHASE_PROGRESS[state.phase]}%` }}
                transition={{ duration: motionSafe ? duration.base : 0, ease: easing.out }}
              />
            </div>
          </div>
        </header>

        {/* `.chatscroll` — an aria-live region so new turns are announced. */}
        <div
          role="log"
          aria-live="polite"
          aria-label="Conversation with your setup assistant"
          className="relative z-10 mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 overflow-y-auto px-6 py-6"
        >
          <Greeting viewer={state.viewer} />

          {reading && (
            <ReadingBubble label={busy ? bootLabel : null} domain={state.domain} pages={state.pages_read} />
          )}

          {transcriptMinusLiveQuestion(state.turns, question).map((turn, index) => (
            <Bubble key={index} turn={turn} />
          ))}

          {unreadable && (
            <Describe
              domain={state.domain}
              disabled={busy !== null}
              onSubmit={(fields) =>
                void guard('Saving what you told me…', async () => {
                  setState(await describeCompany(fields))
                  setQuestion(null)
                })
              }
            />
          )}

          {state.phase === 'brief' && (
            <BriefConfirm
              state={state}
              corrections={corrections}
              onChange={(field, value) => setCorrections((prev) => ({ ...prev, [field]: value }))}
              disabled={busy !== null}
              onConfirm={() =>
                void guard('Saving…', async () => {
                  setState(await confirmBrief(corrections))
                  setCorrections({})
                })
              }
            />
          )}

          {showDeptPicker && deptStep.status === 'choosing' && (
            <DeptPicker
              options={deptStep.options}
              picking={deptPicking}
              onToggle={(value) =>
                setDeptPicking((prev) => {
                  const next = new Set(prev)
                  if (next.has(value)) next.delete(value)
                  else next.add(value)
                  return next
                })
              }
              disabled={busy !== null}
              onConfirm={() =>
                void guard('Saving your directors…', async () => {
                  const values = Array.from(deptPicking)
                  await saveDepartments(values)
                  setDeptStep({ status: 'done', selected: values })
                })
              }
            />
          )}

          {ask && <Ask question={ask.question} choices={ask.choices} onSubmit={ask.onSubmit} disabled={busy !== null} />}

          {question?.done && question.reason && state.phase === 'documents' && (
            <AgentBubble>
              <p className="text-sm text-ink-600">
                That is enough to build on. {sentence(question.reason)}
              </p>
            </AgentBubble>
          )}

          {state.phase === 'documents' && (
            <DocumentsStep
              disabled={busy !== null}
              onContinue={(skipped) =>
                void guard('Saving…', async () => {
                  setState(await documentsDone(skipped))
                })
              }
            />
          )}

          {state.phase === 'tools' && (
            <ToolsStep
              disabled={busy !== null}
              recommendedDepartments={chosenDepartments}
              onContinue={(providers, skipped) =>
                assemble(
                  (next) => next.phase === 'persona',
                  () => declareTools(providers, skipped),
                )
              }
            />
          )}

          {state.phase === 'persona' &&
            (busy !== null ? (
              <Assembling phase={state.phase} label={busy} />
            ) : (
              <PersonaConfirm state={state} disabled={false} onConfirm={() => assemble(assemblyDone)} />
            ))}

          {state.phase === 'assembling' && <Assembling phase={state.phase} label={busy ?? 'Building…'} />}

          {state.phase === 'ready' && <ReadyCard state={state} onOpen={() => router.replace('/dashboard')} />}

          {busy && !reading && state.phase !== 'persona' && state.phase !== 'assembling' && (
            <TypingBubble label={busy} />
          )}

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
            hint={ask.hint}
          />
        )}
      </main>

      <BrainPanel state={state} departments={chosenDepartments} />
    </div>
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
  const mine = turn.role === 'user'
  if (!mine) return <AgentBubble>{turn.text}</AgentBubble>
  return (
    <div className="flex justify-end">
      <div className="max-w-[34rem] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-bone-50">
        {turn.text}
      </div>
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

function ReadingBubble({ label, domain, pages }: { label: string | null; domain: string | null; pages: string[] }) {
  return (
    <AgentBubble>
      <p>{domain ? `Reading ${domain} now.` : 'Reading your website now.'}</p>
      {label && <p className="mt-1 text-ink-500">{label}</p>}
      {pages.length > 0 && (
        <>
          <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-ink-400">
            {pages.length === 1 ? '1 page fetched' : `${pages.length} pages fetched`}
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
    </AgentBubble>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-bone-300 bg-white/90 p-4 backdrop-blur-sm">{children}</div>
}

/** The brief, as one decision instead of a form — same contract as `AgentOnboarding`'s. */
function BriefConfirm({
  state,
  corrections,
  onChange,
  onConfirm,
  disabled,
}: {
  state: AgentState
  corrections: Record<string, string>
  onChange: (field: string, value: string) => void
  onConfirm: () => void
  disabled: boolean
}) {
  const [editing, setEditing] = useState(false)
  const statements = state.brief.statements ?? []
  const assumptions = state.brief.assumptions ?? []

  return (
    <Card>
      <p className="text-sm text-ink-600">
        You outrank the website. If any of that is wrong, say so — your version is what every
        director works from.
      </p>
      <ul className="mt-3 divide-y divide-bone-200">
        {statements.map((statement) => (
          <li key={statement.field} className="py-3">
            <label htmlFor={`fix-${statement.field}`} className="text-xs font-medium text-ink-600">
              {statement.label ?? statement.field}
            </label>
            {editing ? (
              <textarea
                id={`fix-${statement.field}`}
                rows={3}
                disabled={disabled}
                defaultValue={statement.text}
                onChange={(event) => onChange(statement.field, event.target.value)}
                className="mt-1 w-full rounded-lg border border-bone-300 px-3 py-2 text-sm text-ink"
              />
            ) : (
              <p className="mt-0.5 text-sm text-ink-500">{statement.text}</p>
            )}
            <span
              className={
                statement.confidence === 'read'
                  ? 'mt-1 inline-block rounded bg-steel-100 px-2 py-0.5 font-mono text-[10px] text-steel-700'
                  : 'mt-1 inline-block rounded bg-gold-100 px-2 py-0.5 font-mono text-[10px] text-gold-600'
              }
            >
              {statement.confidence}
              {statement.source ? ` · ${statement.source}` : ''}
            </span>
          </li>
        ))}
      </ul>

      {assumptions.length > 0 && (
        <div className="mt-3 rounded-xl border border-dashed border-bone-400 bg-bone-50 p-3">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-400">
            Proceeding on these assumptions
          </p>
          <ul className="mt-2 space-y-1">
            {assumptions.map((assumption) => (
              <li key={assumption.text} className="text-xs text-ink-500">
                {assumption.text} — <span className="text-ink-300">{assumption.evidence}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={disabled}
          className="min-h-[2.75rem] rounded-full bg-ink px-5 text-sm font-medium text-bone-50 disabled:opacity-50"
        >
          {editing ? 'Save and keep going' : "That's right — keep going"}
        </button>
        {!editing && statements.length > 0 && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            disabled={disabled}
            className="min-h-[2.75rem] rounded-full border border-bone-300 px-5 text-sm text-ink-600 hover:border-steel-400 disabled:opacity-50"
          >
            Something is wrong
          </button>
        )}
      </div>
    </Card>
  )
}

/**
 * "Pick your directors" — the wireframe's `obDepts` beat, as quick-reply
 * chips. Excludes `executive`: Chief of Staff is automatic (never a choice)
 * per `services/api/app/domain/departments.py`, the same rule `AreasStage`
 * follows.
 */
function DeptPicker({
  options,
  picking,
  onToggle,
  onConfirm,
  disabled,
}: {
  options: DepartmentState[]
  picking: Set<string>
  onToggle: (value: string) => void
  onConfirm: () => void
  disabled: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <AgentBubble>
        <p>Who should I build directors for? Pick what you actually run — you can change this later.</p>
      </AgentBubble>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Choose your departments">
        {options.map((option) => {
          const checked = picking.has(option.value)
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={checked}
              disabled={disabled}
              onClick={() => onToggle(option.value)}
              className={`min-h-[2.75rem] rounded-full border px-4 text-sm font-medium transition-colors disabled:opacity-50 ${
                checked
                  ? 'border-ink bg-ink text-bone-50'
                  : 'border-bone-300 bg-white/70 text-ink-600 hover:border-steel-400'
              }`}
            >
              {option.label}
            </button>
          )
        })}
      </div>
      <button
        type="button"
        onClick={onConfirm}
        disabled={disabled || picking.size === 0}
        className="mt-1 min-h-[2.75rem] w-fit rounded-full bg-ink px-5 text-sm font-medium text-bone-50 disabled:opacity-50"
      >
        Continue
      </button>
    </div>
  )
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
        <p className="mt-2 text-ink-500">
          That is not a problem. Tell me the three things I would have looked for.
        </p>
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
  hint,
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  label: string
  hint?: string
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
        {hint && <p className="mt-2 text-[11px] text-ink-400">{hint}</p>}
      </div>
    </div>
  )
}

function Assembling({ phase, label }: { phase: Phase; label: string }) {
  const stages: { from: Phase; text: string }[] = [
    { from: 'tools', text: 'Building your Persona' },
    { from: 'persona', text: 'Building your Company Brain' },
    { from: 'assembling', text: 'Personalising your workspace' },
  ]
  const at = stages.findIndex((stage) => stage.from === phase)

  return (
    <Card>
      <div className="flex items-center gap-3">
        <PresenceMark state="thinking" size={26} />
        <h2 className="font-display text-lg text-ink">Building your workspace</h2>
      </div>
      <ol className="mt-4 flex flex-col gap-2.5">
        {stages.map((stage, index) => {
          const done = at > index
          const here = at === index
          return (
            <li key={stage.from} className="flex items-center gap-3">
              <span
                aria-hidden
                className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border ${
                  done
                    ? 'border-ink bg-ink text-bone-50'
                    : here
                      ? 'border-steel-400 bg-white text-steel-600'
                      : 'border-bone-300 bg-white text-ink-300'
                }`}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
              </span>
              <span className={`text-sm ${here ? 'font-medium text-ink' : done ? 'text-ink-500' : 'text-ink-300'}`}>
                {stage.text}
              </span>
            </li>
          )
        })}
      </ol>
      <p role="status" aria-live="polite" className="mt-4 text-xs text-ink-400">
        {label}
      </p>
    </Card>
  )
}

function PersonaConfirm({
  state,
  onConfirm,
  disabled,
}: {
  state: AgentState
  onConfirm: () => void
  disabled: boolean
}) {
  const fields = state.persona.fields ?? []
  const summary = state.persona.summary?.trim()

  return (
    <Card>
      <h2 className="font-display text-lg text-ink">Here is how I understood you</h2>
      <p className="mt-2 text-sm text-ink-600">
        {summary || 'This is what I will use to decide what your workspace shows you first.'}
      </p>
      <ul className="mt-3 divide-y divide-bone-200">
        {fields.length === 0 && (
          <li className="py-2 text-sm italic text-ink-400">
            Nothing specific yet — your workspace will start from your role and learn the rest.
          </li>
        )}
        {fields.map((field) => (
          <li key={field.key} className="py-2">
            <p className="text-xs font-medium text-ink-600">{field.label}</p>
            <p className="mt-0.5 text-sm text-ink-500">{field.value}</p>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={onConfirm}
        disabled={disabled}
        className="mt-4 min-h-[2.75rem] rounded-full bg-ink px-5 text-sm font-medium text-bone-50 disabled:opacity-50"
      >
        That is me — finish setup
      </button>
    </Card>
  )
}

function ReadyCard({ state, onOpen }: { state: AgentState; onOpen: () => void }) {
  const facts = state.context.facts ?? []
  return (
    <div className="flex flex-col gap-5">
      <div className="animate-rise-scale rounded-2xl border border-bone-300 bg-white/90 p-6 text-center backdrop-blur-sm">
        <div className="flex justify-center">
          <PresenceMark state="ready" size={44} />
        </div>
        <h2 className="mt-4 font-display text-title text-ink">Your Company Brain is live</h2>
        <p className="mx-auto mt-2 max-w-prose text-sm leading-relaxed text-ink-600">
          Every director reads this. You can correct any of it in Settings.
        </p>
        <button
          type="button"
          onClick={onOpen}
          className="mt-5 min-h-[2.75rem] rounded-full bg-ink px-7 text-sm font-medium text-bone-50 shadow-paper transition-transform hover:scale-[1.03]"
        >
          Open my workspace
        </button>
      </div>
      {facts.length > 0 && (
        <Card>
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">What it knows</p>
          <ul className="mt-2 flex flex-col gap-2">
            {facts.map((fact) => (
              <li key={fact.key} className="text-sm leading-relaxed text-ink-700">
                {fact.value} <span className="ml-2 font-mono text-2xs uppercase text-ink-400">L{fact.scope}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

function Booting({ label, error, onRetry }: { label: string; error?: string | null; onRetry?: () => void }) {
  if (error) {
    return (
      <div className="relative grid min-h-screen place-items-center px-6">
        <OnboardingAura state="idle" />
        <div className="max-w-md rounded-2xl border border-bone-300 bg-white/90 p-6 backdrop-blur-sm">
          <h1 className="font-display text-lg text-ink">Setup could not start</h1>
          <p role="alert" className="mt-2 text-sm text-ink-600">
            {error}
          </p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-4 min-h-[2.75rem] rounded-full bg-ink px-5 text-sm font-medium text-bone-50"
            >
              Try again
            </button>
          )}
        </div>
      </div>
    )
  }
  return (
    <div className="relative grid min-h-screen place-items-center px-6">
      <OnboardingAura state="thinking" />
      <div role="status" aria-live="polite" className="flex flex-col items-center gap-5">
        <PresenceMark state="thinking" size={56} />
        <p className="max-w-md text-center text-sm text-ink-400">{label}</p>
      </div>
    </div>
  )
}

function Blocked({ message }: { message: string }) {
  return (
    <div className="grid min-h-screen place-items-center px-6">
      <div className="max-w-md rounded-2xl border border-bone-300 bg-white p-6">
        <h1 className="font-display text-lg text-ink">Guided onboarding is unavailable</h1>
        <p className="mt-2 text-sm text-ink-600">{message}</p>
        <p className="mt-3 text-xs text-ink-400">
          Sign-in and every existing workspace are unaffected. There is deliberately no fallback
          form — a questionnaire that quietly replaced the assistant would collect less and look
          the same.
        </p>
      </div>
    </div>
  )
}
