'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type AgentState,
  ModelUnavailableError,
  type NextQuestion,
  SCOPE_LABEL,
  type Viewer,
  confirmBrief,
  finish,
  nextQuestion,
  openDiscovery,
  read,
  readState,
  start,
  submitAnswer,
} from '@/lib/agent-onboarding-client'
import { useSlowLabel } from '@/lib/slow'

/**
 * Guided onboarding: the agent talks on the left, everything it learns appears
 * on the right as it learns it.
 *
 * **It opens by saying who it is talking to.** The greeting is drawn from what
 * the person typed at sign-up — name, job title, department — and needs no
 * model, so it is on screen before the crawl starts rather than after it ends.
 * That matters twice: it is the first evidence that this is their workspace and
 * not a demo, and it gives the twenty seconds of fetching and inference
 * something true to sit under instead of a progress sentence.
 *
 * **The brief is prose, not a form.** The agent says what it read in a sentence
 * and offers one button. The editable fields exist — a Brain nobody corrected
 * is one nobody has reason to trust — but they are behind "Something is wrong",
 * because a wall of textareas is what a person is asked to face *before* they
 * have been told anything. The per-field provenance lives on the right, once,
 * rather than on both sides of the screen saying the same three things.
 *
 * The right pane is the point. It is the receipt for the conversation, and every
 * row in it names where the value came from — read from the site, inferred, or
 * said by you. A person who cannot see what was recorded cannot correct it, and
 * a Brain nobody corrected is one nobody has reason to trust.
 *
 * Three things this deliberately does **not** do:
 *
 * **It never sends the field an answer belongs to.** The composer posts text.
 * The server reads the target from the agent's own last turn. This component
 * displays the target because seeing where an answer lands is the point; it has
 * no say in choosing it.
 *
 * **It shows no percentage.** Progress is the fact count rising and locked rows
 * converting. A percentage needs a denominator, and the denominator here would
 * be a guess at how much there is to know about a company — the invented number
 * the product exists to refuse.
 *
 * **It does not degrade.** With no model configured the screen says so and stops
 * (ADR 0022). There is no form fallback, because a form that quietly replaces a
 * conversation is a different product wearing the same URL.
 */

type Phase = AgentState['phase']

const PHASES: { key: Phase; label: string }[] = [
  { key: 'analysing', label: 'Read' },
  { key: 'brief', label: 'Brief' },
  { key: 'discovery', label: 'You' },
  { key: 'persona', label: 'Persona' },
  { key: 'ready', label: 'Ready' },
]

/**
 * The field `open_discovery` writes, and the only marker that the opening
 * question has been answered. Not "any user turn" — a brief correction is one
 * of those, and reading it as discovery leaves the screen with nothing to do.
 */
const DISCOVERY_FIELD = 'persona.stated_purpose'

export function AgentOnboarding() {
  const router = useRouter()
  const [state, setState] = useState<AgentState | null>(null)
  const [question, setQuestion] = useState<NextQuestion | null>(null)
  const [draft, setDraft] = useState('')
  const [corrections, setCorrections] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>('Reading your website…')
  const [error, setError] = useState<string | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const guard = useCallback(async (label: string, work: () => Promise<void>) => {
    setBusy(label)
    setError(null)
    try {
      await work()
    } catch (cause) {
      // A missing model is not a transient failure and Retry cannot fix it, so
      // it takes over the screen rather than appearing as a dismissible error.
      if (cause instanceof ModelUnavailableError) setBlocked(cause.message)
      else setError(cause instanceof Error ? cause.message : 'Something went wrong.')
    } finally {
      setBusy(null)
    }
  }, [])

  // Resume if a journey is already open, otherwise begin one. Refreshing the
  // page or opening a second tab lands on the same conversation, because the
  // transcript lives in the database and not in this component.
  // Resume, finish, or begin — in that order. Refreshing or opening a second
  // tab lands on the same conversation, because the transcript lives in the
  // database. A workspace that already finished is sent to its dashboard
  // rather than quietly starting a second journey over the Brain it has.
  //
  // The latch is load-bearing, not a StrictMode workaround. `start` is the one
  // request that is slow *and* writes: it holds the session row uncommitted for
  // the whole crawl-and-read, so a second one fired a millisecond later blocks
  // on the single-active-session index until the statement times out. Firing it
  // once is the fix; the server's advisory lock is the net under it.
  const booted = useRef(false)

  useEffect(() => {
    if (booted.current) return
    booted.current = true
    void guard('Reading your website…', async () => {
      const existing = await readState()
      if (existing.completed) {
        router.replace('/dashboard')
        return
      }
      let resumed = existing.active ? existing : await start()
      setState(resumed)

      // Two calls, deliberately. `start` fetches the site and returns in about
      // three seconds; the setState above puts those page URLs on the screen so
      // there is something true to look at while `read` — the two model calls,
      // about seventeen seconds — runs behind it.
      if (resumed.phase === 'analysing' && resumed.turns.length === 0) {
        setBusy('Reading what is on those pages…')
        resumed = await read()
        setState(resumed)
      }
      // Resuming into a half-finished interview has to re-ask the server what
      // the outstanding question is: the question lives on its own endpoint and
      // not in the state, so without this the screen resumes with a transcript
      // and nowhere to type.
      if (
        resumed.phase === 'discovery' &&
        resumed.turns.some((t) => t.role === 'user' && t.target === DISCOVERY_FIELD)
      ) {
        // Not "reading your website" — that already happened, and saying it
        // again over a transcript the user can see is the sort of small lie
        // that makes the rest of the screen harder to believe.
        setBusy('Picking up where you left off…')
        setQuestion(await nextQuestion())
      }
    })
  }, [guard, router])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [state?.turns.length, question])

  // The first wait is the longest in the product — a fetch of the site plus two
  // model calls, around twenty seconds — and it used to sit behind one unchanging
  // line. A sentence that never changes for twenty seconds reads as a hang, which
  // is finding F9 in a different place (`useSlowLabel`'s own docstring lists the
  // three submits it was written for; this is the fourth and the slowest).
  //
  // No proportion and no counter: both would be invented precision over a wait
  // whose length depends on how much site there is to read.
  //
  // Keyed on `busy`, not on `state === null`. The fetch sets state, so by the
  // time the Reading screen renders — the one place this label does the most
  // work, over seventeen seconds of model calls — `state === null` is false and
  // `useSlowLabel` was returning its *idle* string. The most informative moment
  // in onboarding said "Loading…".
  const bootLabel = useSlowLabel(
    busy !== null,
    'Loading…',
    busy ?? 'Reading your website…',
    'Still reading. Going through the site and writing up what is there usually takes about half a minute.',
  )

  if (blocked) return <Blocked message={blocked} />
  if (!state) return <Booting label={bootLabel} />

  // The fetch has landed but the read has not. This used to take over the whole
  // screen, which threw away the one thing the wait already had: a greeting
  // that needed no model and was ready immediately. It is a turn in the
  // transcript now, under that greeting — and it still names the pages actually
  // retrieved, because six real URLs is a different experience from a spinner
  // and is the honest answer to "what is it doing" for seventeen seconds.
  const reading = state.phase === 'analysing'

  const phaseIndex = PHASES.findIndex((p) => p.key === state.phase)

  // The server holds `discovery` for the whole interview, not just its opening
  // question, so the phase alone cannot say whether that question has been put.
  // The transcript can — but "any user turn" is the wrong reading of it, because
  // a brief correction is a user turn too. Correcting a line and then arriving
  // in discovery left the composer suppressed and no question fetched: a screen
  // with nothing on it to do.
  //
  // `persona.stated_purpose` is the precise marker. `open_discovery` is the only
  // thing that writes it, and it writes it exactly once.
  const discoveryAnswered = state.turns.some(
    (turn) => turn.role === 'user' && turn.target === DISCOVERY_FIELD,
  )

  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-10 border-b border-bone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-15 max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <span className="font-display text-base font-semibold text-ink">
            NEXUS <span className="font-normal opacity-60">OS</span>
          </span>
          <ol className="flex items-center gap-2">
            {PHASES.map((phase, index) => (
              <li key={phase.key} className="flex items-center gap-2">
                {index > 0 && <span aria-hidden className="h-px w-4 bg-bone-300" />}
                <span
                  aria-current={index === phaseIndex ? 'step' : undefined}
                  className={
                    index === phaseIndex
                      ? 'text-xs font-medium text-ink'
                      : index < phaseIndex
                        ? 'text-xs text-ink-400'
                        : 'text-xs text-ink-300'
                  }
                >
                  {phase.label}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl grid-cols-1 items-start gap-6 px-6 py-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <main className="min-w-0">
          <div className="flex flex-col gap-4">
            <Greeting viewer={state.viewer} />

            {reading && (
              // `busy ? … : null`, not `bootLabel` alone. `useSlowLabel` returns
              // its *idle* string once nothing is in flight, so a bubble that
              // rendered it unconditionally would sit there saying "Loading…"
              // over a list of pages it had already fetched — the same wrong
              // sentence in the same place the label was written to fix.
              <ReadingBubble
                label={busy ? bootLabel : null}
                domain={state.domain}
                pages={state.pages_read}
              />
            )}

            {state.turns.map((turn, index) => (
              <Bubble key={index} turn={turn} />
            ))}

            {state.phase === 'brief' && (
              <BriefConfirm
                state={state}
                corrections={corrections}
                onChange={(field, value) =>
                  setCorrections((prev) => ({ ...prev, [field]: value }))
                }
                disabled={busy !== null}
                onConfirm={() =>
                  void guard('Saving…', async () => {
                    setState(await confirmBrief(corrections))
                    setCorrections({})
                  })
                }
              />
            )}

            {state.phase === 'discovery' && !discoveryAnswered && !question && (
              <Ask
                question="What are you responsible for, day to day?"
                hint="This decides what gets asked next."
                value={draft}
                onChange={setDraft}
                disabled={busy !== null}
                onSubmit={(text) =>
                  void guard('Thinking…', async () => {
                    setState(await openDiscovery(text))
                    setDraft('')
                    setQuestion(await nextQuestion())
                  })
                }
              />
            )}

            {question && !question.done && question.question && (
              <Ask
                question={question.question}
                choices={question.choices}
                hint={
                  question.scope !== null
                    ? `Stored as ${SCOPE_LABEL[question.scope] ?? `L${question.scope}`}`
                    : undefined
                }
                value={draft}
                onChange={setDraft}
                disabled={busy !== null}
                onSubmit={(text) =>
                  void guard('Thinking…', async () => {
                    setState(await submitAnswer(text))
                    setDraft('')
                    setQuestion(await nextQuestion())
                  })
                }
              />
            )}

            {question?.done && state.phase !== 'ready' && (
              <Card>
                <p className="text-sm text-ink-600">
                  That is enough to build on. {question.reason}
                </p>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() =>
                    void guard('Building your Company Brain…', async () => {
                      setState(await finish())
                    })
                  }
                  className="mt-3 rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50 disabled:opacity-50"
                >
                  Build my Company Brain
                </button>
              </Card>
            )}

            {state.phase === 'ready' && <ReadyCard state={state} router={router} />}

            {/* Suppressed while reading: `ReadingBubble` is already showing this
                exact sentence, and the same line twice reads as two things
                happening. */}
            {busy && !reading && <p className="text-xs text-ink-400">{busy}</p>}
            {error && (
              <p role="alert" className="rounded-lg bg-clay-100 px-3 py-2 text-sm text-clay-600">
                {error}
              </p>
            )}
            <div ref={endRef} />
          </div>
        </main>

        <aside className="flex flex-col gap-3 lg:sticky lg:top-24">
          {/* Two headed cards saying "0 facts", "Filling in as we read" and
              "Filled in as we talk" is a receipt for a conversation that has
              not happened — it puts the panel's furniture on screen a full
              half-minute before it has anything to hold, and a zero next to
              "facts" reads as a real and bad result rather than as "not yet".
              The skeleton says the same thing without asserting a count. */}
          {hasRecord(state) ? <KnowledgePanel state={state} /> : <PanelSkeleton />}
        </aside>
      </div>
    </div>
  )
}

/* ── Pieces ─────────────────────────────────────────────────── */

/**
 * The sentence that says whose workspace this is.
 *
 * Assembled here rather than by a model, from the row the person filled in
 * themselves. Nothing is inferred and nothing is filled in from a neighbouring
 * field: each clause appears only if its column has a value, so somebody who
 * never typed a job title is greeted by name and told nothing else, rather than
 * being told something plausible.
 *
 * **`designation`, never `role`.** What is said back is what they claimed —
 * "Lead Designer", "in Design". `membership.role` and `membership.departments`
 * are the authorising pair and are not on this wire at all; a greeting that
 * recited them would be the first place in the product where a permission is
 * treated as small talk.
 *
 * No name, no greeting. An inbox is not a name and "Hallo there" is worse than
 * opening with the finding, which is what the next bubble does anyway.
 */
function Greeting({ viewer }: { viewer?: Viewer }) {
  const line = greetingFor(viewer)
  if (!line) return null
  return <AgentBubble>{line}</AgentBubble>
}

export function greetingFor(viewer?: Viewer): string | null {
  const name = viewer?.name?.trim()
  if (!name) return null
  // First name only, once. "Hallo Parul Bhoite" is how a mail merge talks.
  const first = name.split(/\s+/)[0]

  const company = viewer?.company?.trim()
  const designation = viewer?.designation?.trim()
  const department = viewer?.department?.trim()
  if (!company) return `Hallo ${first}.`

  let where = `you work at ${company}`
  if (designation) where += ` as ${designation}`
  if (department) where += `, in ${department}`
  return `Hallo ${first} — ${where}.`
}

function AgentBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[38rem] rounded-2xl rounded-bl-md bg-bone-100 px-4 py-3 text-sm text-ink">
        {children}
      </div>
    </div>
  )
}

function Bubble({ turn }: { turn: { role: string; text: string; target: string | null; scope: number | null } }) {
  const mine = turn.role === 'user'
  if (!mine && turn.scope === null) return <AgentBubble>{turn.text}</AgentBubble>
  return (
    <div className={mine ? 'flex justify-end' : 'flex justify-start'}>
      <div className="max-w-[38rem]">
        <div
          className={
            mine
              ? 'rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-bone-50'
              : 'rounded-2xl rounded-bl-md bg-bone-100 px-4 py-3 text-sm text-ink'
          }
        >
          {turn.text}
        </div>
        {turn.scope !== null && (
          // Showing where an answer lands is the point of the tag being real.
          <p className="mt-1 text-right font-mono text-[10px] uppercase tracking-wider text-ink-300">
            {SCOPE_LABEL[turn.scope] ?? `L${turn.scope}`}
          </p>
        )}
      </div>
    </div>
  )
}

/**
 * The brief, as one decision instead of a form.
 *
 * What was read is already on screen — the agent said it in a sentence, and the
 * right-hand panel lists it fact by fact with the URL each one came from. This
 * card is only the moment the person is told they outrank all of it.
 *
 * The editors are still here and still keyed by declared field; they are behind
 * a button because they are the minority case. Before, everybody met three
 * textareas and a provenance chip per row before being told anything, duplicated
 * verbatim by the panel beside them — a screen that asks for corrections that
 * confidently before it has earned any trust mostly gets "keep going" clicked
 * through, which is the outcome the correction step exists to avoid.
 */
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
        You outrank the website. If any of that is wrong, say so — your version is what
        every director works from.
      </p>

      {editing && (
        <ul className="mt-3 divide-y divide-bone-200">
          {statements.map((statement) => (
            <li key={statement.field} className="py-3">
              <label
                htmlFor={`fix-${statement.field}`}
                className="text-xs font-medium text-ink-600"
              >
                {statement.field}
              </label>
              {/* Three rows, not two. At two, every statement long enough to be
                  worth correcting opened with its own first line scrolled out
                  of sight. */}
              <textarea
                id={`fix-${statement.field}`}
                rows={3}
                disabled={disabled}
                defaultValue={statement.text}
                onChange={(event) => onChange(statement.field, event.target.value)}
                className="mt-1 w-full rounded-lg border border-bone-300 px-3 py-2 text-sm text-ink"
              />
            </li>
          ))}
        </ul>
      )}

      {assumptions.length > 0 && (
        // Shown, never applied silently — the reason `assumptions` is a column
        // of its own rather than another provenance entry. Always visible, not
        // folded in behind the editors: a thing being quietly assumed is
        // exactly what a person would want to catch without going looking.
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
          className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50 disabled:opacity-50"
        >
          {editing ? 'Save and keep going' : 'That is right — keep going'}
        </button>
        {!editing && statements.length > 0 && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            disabled={disabled}
            className="rounded-full border border-bone-300 px-5 py-2 text-sm text-ink-600 hover:border-steel-400 disabled:opacity-50"
          >
            Something is wrong
          </button>
        )}
      </div>
    </Card>
  )
}


/**
 * A question, asked the way the agent asks everything else.
 *
 * It used to be a bordered card with the question as a paragraph inside it —
 * the same words as an agent turn, in a shape that said "form". Here the
 * question is an agent bubble in the transcript and the answer lands under it,
 * so an interview reads as one continuous conversation rather than as a
 * conversation that stops and hands over a widget every second turn.
 */
function Ask({
  question,
  choices = [],
  hint,
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  question: string
  choices?: string[]
  hint?: string
  value: string
  onChange: (value: string) => void
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
              // The text goes to `onSubmit` directly rather than via
              // `onChange`. Setting state and submitting in one handler submits
              // the *previous* state: `onSubmit` closes over the draft from this
              // render, which is still empty, so every chip posted "" and the
              // API rejected it on `min_length`. The chips were unusable.
              onClick={() => {
                onChange(choice)
                onSubmit(choice)
              }}
              className="rounded-full border border-bone-300 px-3 py-1.5 text-sm text-ink-600 hover:border-steel-400 disabled:opacity-50"
            >
              {choice}
            </button>
          ))}
        </div>
      )}
      <Composer
        label={choices.length > 0 ? 'Or answer in your own words' : 'Answer in your own words'}
        value={value}
        onChange={onChange}
        onSubmit={onSubmit}
        disabled={disabled}
        hint={hint}
      />
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
  /** Carries the text. See the note on QuestionCard's choice chips. */
  onSubmit: (text: string) => void
  disabled: boolean
}) {
  return (
    <div>
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
          className="flex-1 rounded-xl border border-bone-300 px-3 py-2 text-sm text-ink"
        />
        <button
          type="button"
          onClick={() => onSubmit(value)}
          disabled={disabled || !value.trim()}
          className="h-10 rounded-full bg-ink px-4 text-sm text-bone-50 disabled:opacity-40"
        >
          Send
        </button>
      </div>
      {hint && <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-300">{hint}</p>}
    </div>
  )
}

/**
 * The receipt. Every row names what was recorded and, while the brief is still
 * unconfirmed, where it came from.
 *
 * The provenance chips live here and nowhere else. They used to be rendered on
 * both sides of the screen at once, against the same three facts, which is one
 * chip too many for a claim and two panes saying the same thing.
 */
/**
 * Whether the right pane has anything real to show yet.
 *
 * Facts *or* statements *or* persona fields — any one of them means the panel
 * has content and the skeleton is done. It stays false for the whole read,
 * which is exactly the window the skeleton exists to cover.
 */
function hasRecord(state: AgentState): boolean {
  return (
    (state.context.facts ?? []).length > 0 ||
    (state.brief.statements ?? []).length > 0 ||
    (state.persona.fields ?? []).length > 0
  )
}

/**
 * The right pane while there is nothing in it.
 *
 * Shaped like what replaces it — a card, a heading bar, three rows — so the
 * swap is a fill rather than a reflow. No text and no numbers: the panel's job
 * is to be the receipt, and a receipt that lists placeholder rows before
 * anything was recorded is the one thing it must never do.
 *
 * `role="status"` with a visually-hidden sentence, because `globals.css`
 * collapses looping animations to one iteration under `prefers-reduced-motion`.
 * With the pulse stopped this is a few grey bars; the sr-only line is what
 * still says why.
 */
function PanelSkeleton() {
  return (
    <section
      role="status"
      aria-live="polite"
      className="rounded-2xl border border-bone-300 bg-bone-50 p-4"
    >
      <span className="sr-only">Reading your website. The panel fills in as facts are found.</span>
      <div aria-hidden className="animate-pulse">
        <div className="flex items-baseline justify-between">
          <div className="h-3.5 w-32 rounded bg-bone-300" />
          <div className="h-2.5 w-12 rounded bg-bone-200" />
        </div>
        <div className="mt-2 h-2 w-24 rounded bg-bone-200" />
        <div className="mt-4 flex flex-col gap-4">
          {[0, 1, 2].map((row) => (
            <div key={row} className="flex flex-col gap-1.5">
              <div className="h-2.5 w-28 rounded bg-bone-300" />
              <div className="h-2 w-full rounded bg-bone-200" />
              <div className="h-2 w-4/5 rounded bg-bone-200" />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function KnowledgePanel({ state }: { state: AgentState }) {
  const facts = state.context.facts ?? []
  const gaps = state.context.known_gaps ?? []
  const personaFields = state.persona.fields ?? []
  const statements = state.brief.statements ?? []

  // Assembled facts once they exist, the unconfirmed brief until then. The
  // brief rows carry provenance; an assembled fact has been through
  // confirmation and is no longer "what the website said".
  const rows = facts.length
    ? facts.map((fact) => ({ key: fact.key, value: fact.value, statement: null }))
    : statements.map((statement) => ({
        key: statement.field,
        value: statement.text,
        statement,
      }))

  return (
    <>
      <section className="rounded-2xl border border-bone-300 bg-bone-50 p-4">
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-sm font-semibold text-ink">Company Brain</h2>
          <span className="font-mono text-[10px] text-ink-400">
            {rows.length === 1 ? '1 fact' : `${rows.length} facts`}
          </span>
        </div>
        <p className="mt-0.5 text-[11px] text-ink-400">{state.domain}</p>
        <ul className="mt-3 divide-y divide-bone-200">
          {rows.length === 0 && (
            // The read is still running. Saying so beats an empty list, which
            // reads as a real and bad result.
            <li className="py-2 text-xs italic text-ink-300">Filling in as we read.</li>
          )}
          {rows.map(({ key, value, statement }) => (
            <li key={key} className="py-2">
              <p className="text-xs font-medium text-ink-600">{key}</p>
              <p className="mt-0.5 text-xs text-ink-500">{value}</p>
              {statement && (
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
              )}
            </li>
          ))}
        </ul>
        {gaps.length > 0 && (
          // Locked, with the step that unlocks it — never a zero, which would
          // read as a real and bad result.
          <>
            <p className="mt-3 border-t border-bone-200 pt-3 font-mono text-[10px] uppercase tracking-wider text-ink-300">
              Not known yet
            </p>
            <ul className="mt-1 space-y-1">
              {gaps.map((gap) => (
                <li key={gap.topic} className="text-xs text-ink-400">
                  {gap.topic} — <span className="text-steel-600">{gap.unlocked_by}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="rounded-2xl border border-bone-300 bg-bone-50 p-4">
        <h2 className="font-display text-sm font-semibold text-ink">Your Persona</h2>
        {/* Stated permanently, not as a tooltip. Presentation preference is not
            authorisation, and the person is told so where they can see it. */}
        <p className="mt-1 border-l-2 border-gold pl-2 text-[11px] leading-snug text-ink-400">
          This changes what NEXUS shows you first. It never changes what you are allowed to see —
          that comes from your role, which this conversation cannot change.
        </p>
        <ul className="mt-3 divide-y divide-bone-200">
          {personaFields.length === 0 && (
            <li className="py-2 text-xs italic text-ink-300">Filled in as we talk.</li>
          )}
          {personaFields.map((field) => (
            <li key={field.key} className="py-2">
              <p className="text-xs font-medium text-ink-600">{field.label}</p>
              <p className="mt-0.5 text-xs text-ink-500">{field.value}</p>
              {field.derived_from && (
                <p className="mt-0.5 text-[10px] italic text-ink-300">“{field.derived_from}”</p>
              )}
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}

function ReadyCard({ state, router }: { state: AgentState; router: ReturnType<typeof useRouter> }) {
  return (
    <Card>
      <h2 className="font-display text-lg text-ink">Your Company Brain is live</h2>
      {state.context.preamble && (
        <p className="mt-2 whitespace-pre-line text-sm text-ink-600">{state.context.preamble}</p>
      )}
      {(state.context.known_gaps ?? []).length > 0 && (
        <p className="mt-3 text-xs text-ink-400">
          Still locked:{' '}
          {state.context.known_gaps?.map((gap) => gap.topic).join(' · ')}. Each names its own
          unlock in your workspace.
        </p>
      )}
      <button
        type="button"
        onClick={() => router.replace('/dashboard')}
        className="mt-4 inline-block rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50"
      >
        Open my workspace
      </button>
    </Card>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-bone-300 bg-white p-4">{children}</div>
}

function ReadingBubble({
  label,
  domain,
  pages,
}: {
  label: string | null
  domain: string | null
  pages: string[]
}) {
  return (
    <AgentBubble>
      <p>{domain ? `Reading ${domain} now.` : 'Reading your website now.'}</p>
      {label && <p className="mt-1 text-ink-500">{label}</p>}

      {pages.length > 0 && (
        <>
          {/* A real count of a real array. Never "about a dozen pages". */}
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

/**
 * The first screen, before there is any state to draw.
 *
 * It was one line of centred grey text on white, which for a wait this long
 * (a fetch and two model calls) is indistinguishable from a page that has
 * finished loading and has nothing on it. The dots say the process is alive;
 * the sentence says what it is doing and roughly how long — `useSlowLabel`
 * rewrites it once the wait runs past the usual.
 *
 * **The sentence stays.** `globals.css` collapses every animation to a single
 * iteration under `prefers-reduced-motion`, so the dots stop for anyone with
 * that set. A loader that is the *only* signal would go silent for exactly the
 * people least able to guess; motion is decoration here, never the message.
 *
 * `role="status"` rather than a bare div: the label changes mid-wait, and a
 * screen reader should hear that it changed without the focus moving.
 */
function Booting({ label }: { label: string }) {
  return (
    <div className="grid min-h-screen place-items-center px-6">
      <div role="status" aria-live="polite" className="flex flex-col items-center gap-4">
        <span className="flex items-center gap-1.5" aria-hidden>
          {[0, 1, 2].map((index) => (
            <span
              key={index}
              className="h-2 w-2 animate-pulse rounded-full bg-steel-400"
              // Staggered so the three read as one travelling pulse rather than
              // three things blinking in unison. Inline because the delay is
              // per-index and Tailwind has no arbitrary-delay-by-loop utility.
              style={{ animationDelay: `${index * 160}ms`, animationDuration: '1.1s' }}
            />
          ))}
        </span>
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
          Sign-in and every existing workspace are unaffected. There is deliberately no
          fallback form — a questionnaire that quietly replaced the assistant would collect
          less and look the same.
        </p>
      </div>
    </div>
  )
}
