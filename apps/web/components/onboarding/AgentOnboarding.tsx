'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type AgentState,
  ModelUnavailableError,
  type NextQuestion,
  ASSEMBLY_LABEL,
  SCOPE_LABEL,
  type Viewer,
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
import { useDictation } from '@/lib/dictation'
import { useSlowLabel } from '@/lib/slow'
import { DocumentsStep } from '@/components/onboarding/DocumentsStep'
import { ToolsStep } from '@/components/onboarding/ToolsStep'
import {
  OnboardingAura,
  PresenceMark,
  type AuraState,
} from '@/components/onboarding/OnboardingAura'

/**
 * Guided onboarding: one conversation, on one column, and nothing else.
 *
 * **It is a chat and only a chat.** There used to be a second column beside it
 * — a Company Brain ledger and a Your Persona sheet — filling in fact by fact
 * as the interview ran. The intent was a receipt, and the effect was homework:
 * a person mid-sentence about their own job was also being asked to audit a
 * table being written in their peripheral vision, on the screen where they have
 * the least context in the whole product. What was recorded is still shown and
 * still correctable, but at the moments it means something — the brief, inline,
 * as one decision; and the persona, at the end, as one summary they confirm
 * before the workspace is built.
 *
 * **It opens by saying who it is talking to.** The greeting is drawn from what
 * the person typed at sign-up — name, job title, department — and needs no
 * model, so it is on screen before the crawl starts rather than after it ends.
 * That matters twice: it is the first evidence that this is their workspace and
 * not a demo, and it gives the twenty seconds of fetching and inference
 * something true to sit under instead of a progress sentence.
 *
 * **The brief is prose, not a form.** The agent says what it read and offers one
 * button. The editable fields exist — a Brain nobody corrected is one nobody has
 * reason to trust — but they are behind "Something is wrong", because a wall of
 * textareas is what a person is asked to face *before* they have been told
 * anything.
 *
 * **An answer can be spoken.** These are the longest free-text answers in the
 * product, and the microphone is the cheapest way to make them longer and
 * truer. Transcription is the browser's, so no audio reaches this product — see
 * `lib/dictation`. Where the API does not exist, the button does not render.
 *
 * Three things this deliberately does **not** do:
 *
 * **It never sends the field an answer belongs to.** The composer posts text.
 * The server reads the target from the agent's own last turn. This component
 * displays the target because seeing where an answer lands is the point; it has
 * no say in choosing it.
 *
 * **It shows no percentage.** Progress is the named phase advancing. A
 * percentage needs a denominator, and the denominator here would be a guess at
 * how much there is to know about a company — the invented number the product
 * exists to refuse.
 *
 * **It does not degrade.** With no model configured the screen says so and stops
 * (ADR 0022). There is no form fallback, because a form that quietly replaces a
 * conversation is a different product wearing the same URL.
 */

type Phase = AgentState['phase']

const PHASES: { key: Phase; label: string; hint: string }[] = [
  { key: 'analysing', label: 'Read', hint: 'Reading your website' },
  { key: 'brief', label: 'Brief', hint: 'Your company profile' },
  { key: 'discovery', label: 'You', hint: 'Your role & goals' },
  { key: 'documents', label: 'Documents', hint: 'Your own files' },
  { key: 'tools', label: 'Tools', hint: 'Where your data lives' },
  { key: 'persona', label: 'Confirm', hint: 'Review what we keep' },
  { key: 'ready', label: 'Ready', hint: 'Workspace set up' },
]
/* Seven steps, and the two new ones are the point rather than an addition.
   Everything a person supplies has to be supplied *before* Confirm, because
   Confirm is where the Persona and the Brain stop being drafts — so the rail
   showing Documents and Tools ahead of it is showing the real order, and the
   server refuses `finish` from either of them for the same reason.

   `assembling` is still absent, as it always was: it is a stage of Confirm and
   not a step somebody takes. `phaseIndex` therefore returns -1 while it runs,
   which leaves every step un-highlighted for a few seconds — the same
   behaviour as before, and better than a rail that jumps to a step nobody
   pressed. */

/** What the canvas is headed while each phase is open. */
const PHASE_EYEBROW: Record<Phase, string> = {
  analysing: 'Reading your company',
  brief: 'What we found',
  discovery: 'Getting to know you',
  documents: 'Your own documents',
  tools: 'Where your data lives',
  persona: 'How we understood you',
  assembling: 'Building your workspace',
  ready: 'Your workspace is ready',
}

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
  /**
   * How to re-run whatever just failed.
   *
   * The error used to render as a bare `role="alert"` with nothing to click, so
   * recovery depended on the person guessing that the button they had already
   * pressed would work a second time — and on the assembly path it *does*,
   * because each stage commits and `/finish` resumes at the one that broke.
   *
   * Held here rather than special-cased per action: `guard` already receives
   * the closure, so remembering it covers the brief, an answer, the manual
   * description and every assembly stage at once.
   */
  const [retry, setRetry] = useState<(() => void) | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)
  // Lifted out of the composer only so the background can show it. A live
  // microphone is the one state on this screen worth signalling twice.
  const [listening, setListening] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const guard = useCallback(
    async (label: string, work: () => Promise<void>) => {
      setBusy(label)
      setError(null)
      setRetry(null)
      try {
        await work()
      } catch (cause) {
        // Stored as a thunk returning a thunk: `useState` calls a bare function
        // argument to compute the next state, so `setRetry(fn)` would run the
        // retry immediately instead of storing it.
        setRetry(() => () => void guard(label, work))
        // A missing model is not a transient failure and Retry cannot fix it, so
        // it takes over the screen rather than appearing as a dismissible error.
        if (cause instanceof ModelUnavailableError) {
          setBlocked(cause.message)
          return
        }
        // Finding F7, in the place it does the most damage. `DashboardLanding`
        // already sends an expired session to sign-in; this screen did not, and
        // its failure was worse than a wrong message: the boot request 401s
        // before any state exists, so the component fell through to `Booting`
        // and — with `busy` cleared — `useSlowLabel` returned its *idle* string.
        // A signed-out visitor sat on a centred "Loading…" forever, with the
        // error rendered nowhere and nothing on the page to click.
        //
        // Handled here rather than only at boot because this journey is a dozen
        // requests over several minutes, so a session expiring *mid-interview*
        // is ordinary. Nothing is lost by leaving: the transcript is in the
        // database, and `next` brings them back to the turn they were on.
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

  // Extracted from the effect so Retry can run the same sequence. The effect
  // fires it once behind the latch; the button fires it directly, because a
  // person pressing Retry is one deliberate call and not the double-mount the
  // latch exists to absorb.
  const boot = useCallback(async () => {
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
      // `site_unreadable` means the crawl ran and the site gave nothing, so
      // `read` would 409. The screen asks the founder instead — see
      // `Describe`. Checked before the phase, because the phase is still
      // `analysing` in both cases.
      if (resumed.phase === 'analysing' && resumed.turns.length === 0 && !resumed.site_unreadable) {
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
        const outstanding = await nextQuestion()
        setQuestion(outstanding)
        // `GET /next` is also what *closes* the interview: asked on a session
        // whose agent has nothing left worth asking, it moves the phase to
        // `documents` server-side. The state fetched above therefore says
        // `discovery` while the response says done, and the screen would have
        // rendered neither a question nor the documents step — a resumed
        // journey with nothing on it to do.
        //
        // Re-read only on that branch. It costs one request on the one resume
        // where the phase changed underneath us, rather than on every resume.
        if (outstanding.done) setState(await readState())
      }
  }, [router])

  useEffect(() => {
    if (booted.current) return
    booted.current = true
    void guard('Reading your website…', boot)
  }, [guard, boot])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [state?.turns.length, state?.phase, question])

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
  if (!state)
    return (
      <Booting
        label={bootLabel}
        // Reachable at last. `error` was set on a failed boot and rendered
        // nowhere, because the only branch that drew it was below this early
        // return — so every non-auth failure of the opening request looked
        // identical to a page still loading.
        error={error}
        onRetry={() => void guard('Reading your website…', boot)}
      />
    )

  // The fetch has landed but the read has not. This used to take over the whole
  // screen, which threw away the one thing the wait already had: a greeting
  // that needed no model and was ready immediately. It is a turn in the
  // transcript now, under that greeting — and it still names the pages actually
  // retrieved, because six real URLs is a different experience from a spinner
  // and is the honest answer to "what is it doing" for seventeen seconds.
  // `analysing` covers both "fetching" and "there was nothing to fetch". Only
  // the first gets the reading bubble; the second gets three questions.
  const unreadable = state.phase === 'analysing' && state.site_unreadable === true
  const reading = state.phase === 'analysing' && !unreadable

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

  const aura: AuraState = busy
    ? 'thinking'
    : listening
      ? 'listening'
      : state.phase === 'ready'
        ? 'ready'
        : 'idle'

  /**
   * Walk the assembly to `ready`, one committed stage per request.
   *
   * Not one call. Each `finish` runs a single stage and commits it, so a
   * failure part-way leaves the finished stages on the row and this resumes at
   * the one that broke — the server picks the stage from the phase, so simply
   * clicking again is the retry.
   *
   * `until` is what makes the persona confirmation possible at all: the first
   * run stops as soon as the persona exists, the screen puts it in front of the
   * person, and the second run — after they have confirmed it — carries on to
   * the Brain and the context.
   */
  const assemble = (
    until: (next: AgentState) => boolean,
    /**
     * A write that must land before the assembly starts, if any.
     *
     * The tools step needs one: the declaration has to be on record before
     * `finish` builds the Persona from it. Passed in here rather than chained
     * at the call site so that both live under a single `guard` — which means
     * one busy label for what a person experiences as one action, and one
     * Retry that repeats the whole thing. `declareTools` replaces rather than
     * appends, so repeating it is harmless.
     */
    before?: () => Promise<AgentState>,
  ) => {
    void guard(ASSEMBLY_LABEL[state.phase] ?? 'Building…', async () => {
      if (before) setState(await before())
      let next = await finish()
      setState(next)
      // Bounded, and guarded on the assembly actually moving. The stop
      // condition is `until`, but a server that returned the same state twice
      // would otherwise spin here forever paying for a model call each time.
      //
      // The guard watches `assembly_step`, not the phase alone. The Brain is
      // several committed steps that all leave the phase at `persona`, so a
      // phase-only check read the second group as "nothing moved" and stopped
      // with half a Brain — the exact bug the split would otherwise have
      // introduced. Six attempts covers persona, every Brain group and the
      // context, with room for a group to be added.
      for (let attempt = 0; attempt < 6 && !until(next) && !assemblyDone(next); attempt += 1) {
        const before = next.phase
        const beforeStep = next.assembly_step ?? 0
        setBusy(ASSEMBLY_LABEL[before] ?? 'Building…')
        next = await finish()
        setState(next)
        if (next.phase === before && (next.assembly_step ?? 0) === beforeStep) break
      }
    })
  }

  return (
    /* Two columns: a rail that says where you are, and a canvas that is the
       conversation. The rail replaced a horizontal stepper in a sticky header,
       which had to compress five steps and their meaning into one line and so
       carried neither — "Brief" alone does not tell anybody what is about to
       happen to them. Vertically there is room for the step *and* what it is
       for, and room to say which question you are on.

       No `bg-white` on the wrapper: `body` paints it, and a background here
       would paint over the aura, which sits at `-z-10` — above the page canvas
       and below in-flow content. With one set, the whole animated element
       rendered and was invisible. */
    <div className="relative min-h-screen lg:grid lg:grid-cols-[17.5rem_minmax(0,1fr)]">
      <Rail
        state={state}
        phaseIndex={phaseIndex}
        aura={aura}
        asked={state.answered}
        ceiling={state.ceiling}
      />

      {/* The canvas. Warm rather than white, so the rail reads as chrome and
          this reads as the room the conversation happens in — and so the
          composer, which *is* white, separates from it without a border doing
          the work.

          The width is a reading measure rather than a layout leftover: this is
          prose being read and prose being written, and a bubble that runs the
          width of a desktop monitor is neither. */}
      <main className="relative flex min-h-screen flex-col bg-bone-100">
        <p className="animate-fade-in pt-8 text-center font-mono text-[11px] uppercase tracking-[0.22em] text-ink-400">
          {/* `analysing` covers two screens that say opposite things. When the
              site could not be read, the page below is the manual brief — an
              eyebrow reading "reading your company" over "I could not read
              nosuch.com" is the screen contradicting itself in the first two
              lines a person reads. */}
          {state.phase === 'analysing' && state.site_unreadable
            ? 'Tell me about your company'
            : (PHASE_EYEBROW[state.phase] ?? '')}
        </p>

        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-6 pb-10 pt-6">
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

          {unreadable && (
            <Describe
              domain={state.domain}
              disabled={busy !== null}
              onSubmit={(fields) =>
                void guard('Saving what you told me…', async () => {
                  setState(await describeCompany(fields))
                  // Straight into the interview — this path has no brief step,
                  // so the opening discovery question is what comes next and
                  // the composer needs it now.
                  setQuestion(null)
                })
              }
            />
          )}

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
              // The one question the model does not word. The same string is
              // `persona.stated_purpose.fallback_question` in the catalogue,
              // which is what `/discovery` writes into the transcript as the
              // agent turn this answer replies to —
              // `test_the_opening_question_is_worded_once` reads this file to
              // prove the two have not drifted. Change both or neither.
              question="What are you responsible for, day to day?"
              hint="This decides what gets asked next."
              value={draft}
              onChange={setDraft}
              onListening={setListening}
              disabled={busy !== null}
              onSubmit={(text) =>
                void guard('Thinking…', async () => {
                  const turn = await openDiscovery(text)
                  setState(turn.state)
                  setDraft('')
                  setQuestion(turn.question ?? (await nextQuestion()))
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
              onListening={setListening}
              disabled={busy !== null}
              onSubmit={(text) =>
                void guard('Thinking…', async () => {
                  // One request, not two. The question arrives with the answer;
                  // `nextQuestion()` is the fallback for the case the server
                  // stored the answer but could not generate a question, which
                  // it reports as a null rather than by failing and discarding
                  // the answer. See `AnswerTurn`.
                  const turn = await submitAnswer(text)
                  setState(turn.state)
                  setDraft('')
                  setQuestion(turn.question ?? (await nextQuestion()))
                })
              }
            />
          )}

          {/* The interview closing. It used to carry the button that started the
              assembly; the assembly now waits for the documents and the tools,
              so this says its piece and the next step renders under it.

              Shown on the reason existing rather than on the phase, because
              the reason is the agent's own sentence and lives only in the
              response that closed the interview — a refresh loses it, and the
              documents step below is what the person actually needs. */}
          {question?.done && question.reason && state.phase === 'documents' && (
            <AgentBubble>
              <p className="text-sm text-ink-600">
                That is enough to build on. {sentence(question.reason)}
              </p>
              <p className="mt-2 text-xs text-ink-400">
                Everything else is a question your workspace can ask you later, when it has a
                reason to.
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
              // The declaration and the first assembly stage under one guard:
              // this is the click that starts building, and the two must not be
              // able to land apart. `assemble` stops at the persona rather than
              // running to `ready` — what it understood about the person is the
              // one thing worth putting in front of them before the workspace
              // is built on it.
              onContinue={(providers, skipped) =>
                assemble(
                  (next) => next.phase === 'persona',
                  () => declareTools(providers, skipped),
                )
              }
            />
          )}

          {(state.phase === 'persona' || state.phase === 'assembling') && (
            <PersonaConfirm
              state={state}
              disabled={busy !== null}
              onConfirm={() => assemble(assemblyDone)}
            />
          )}

          {state.phase === 'ready' && <ReadyCard state={state} router={router} />}

          {/* Suppressed while reading: `ReadingBubble` is already showing this
              exact sentence, and the same line twice reads as two things
              happening. */}
          {busy && !reading && <p className="text-xs text-ink-400">{busy}</p>}
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
                  className="mt-2 rounded-full border border-clay-400 px-4 py-1.5 text-sm font-medium text-clay-600 hover:bg-clay-200 disabled:opacity-50"
                >
                  Try again
                </button>
              )}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </main>
    </div>
  )
}

/* ── Pieces ─────────────────────────────────────────────────── */

/**
 * The rail: where you are, what this step is for, and who you are.
 *
 * It replaced a horizontal stepper in a sticky header. Horizontally there is
 * room for five words and nothing else, so the screen said "Brief" and left the
 * person to guess what was about to happen to them. Vertically each step can
 * carry its own sentence, the current one can say which question you are on,
 * and the whole thing stops competing with the conversation for the top of the
 * page.
 *
 * **The step count is the real one.** `asked` is agent turns carrying a target
 * — the same number the ceiling is checked against — so "Question 3 of 5" and
 * the moment the interview actually ends cannot disagree. It briefly reported
 * "6 of 5" when the wire counted every user turn instead.
 */
function Rail({
  state,
  phaseIndex,
  aura,
  asked,
  ceiling,
}: {
  state: AgentState
  phaseIndex: number
  aura: AuraState
  asked: number
  ceiling: number
}) {
  const viewer = state.viewer
  const initial = viewer?.name?.trim()?.[0]?.toUpperCase() ?? '\u00b7'

  return (
    <aside className="z-10 flex flex-col border-b border-bone-200 bg-white px-6 py-6 lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r lg:py-8">
      <span className="flex items-center gap-2.5 font-display text-base font-semibold text-ink">
        <PresenceMark state={aura} />
        NEXUS <span className="font-normal opacity-60">OS</span>
      </span>

      <ol className="mt-9 flex flex-1 flex-col">
        {PHASES.map((phase, index) => {
          const done = index < phaseIndex
          const here = index === phaseIndex
          return (
            <li
              key={phase.key}
              // Staggered so the rail assembles downward on first paint rather
              // than appearing all at once. Inline because the delay is
              // per-index and Tailwind has no arbitrary-delay-by-loop utility.
              className="animate-rise"
              style={{ animationDelay: `${index * 70}ms` }}
            >
              <div className="flex items-start gap-3">
                <span
                  aria-hidden
                  className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border text-[11px] font-medium transition-colors duration-500 ${
                    done
                      ? 'border-ink bg-ink text-bone-50'
                      : here
                        ? 'border-ink text-ink'
                        : 'border-bone-300 text-ink-300'
                  }`}
                >
                  {done ? <CheckMark /> : index + 1}
                </span>
                <div className="min-w-0 pb-1">
                  <p
                    aria-current={here ? 'step' : undefined}
                    className={`text-sm font-medium transition-colors ${
                      here ? 'text-ink' : done ? 'text-ink-500' : 'text-ink-300'
                    }`}
                  >
                    {phase.label}
                  </p>
                  <p className={`mt-0.5 text-xs ${here || done ? 'text-ink-400' : 'text-ink-300'}`}>
                    {phase.hint}
                  </p>
                  {here && state.phase === 'discovery' && (
                    <p className="mt-1.5 animate-fade-in text-xs font-medium text-steel-600">
                      Question {Math.min(asked + 1, ceiling)} of {ceiling}
                    </p>
                  )}
                </div>
              </div>

              {index < PHASES.length - 1 && (
                <span
                  aria-hidden
                  className={`ml-[0.84rem] block h-5 w-px transition-colors duration-500 ${
                    done ? 'bg-ink/30' : 'bg-bone-300'
                  }`}
                />
              )}
            </li>
          )
        })}
      </ol>

      {/* Who this workspace is being built for. Drawn from the same row as the
          greeting so the two cannot disagree — and `designation`, never `role`,
          because a permission is not small talk. */}
      {viewer?.name && (
        <div className="mt-8 flex items-center gap-3 border-t border-bone-200 pt-5">
          <span
            aria-hidden
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-sm font-medium text-bone-50"
          >
            {initial}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-ink">{viewer.name.split(/\s+/)[0]}</p>
            <p className="truncate text-xs text-ink-400">
              {[viewer.designation, viewer.company].filter(Boolean).join(' \u00b7 ')}
            </p>
          </div>
        </div>
      )}
    </aside>
  )
}

function CheckMark() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-3.5 w-3.5"
    >
      <path d="M4 12.5l5.5 5.5L20 6.5" />
    </svg>
  )
}


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
    <div className="flex animate-rise justify-start">
      <div className="max-w-[38rem] rounded-2xl rounded-bl-md border border-bone-200/70 bg-white/80 px-4 py-3 text-sm leading-relaxed text-ink shadow-paper backdrop-blur-sm">
        {children}
      </div>
    </div>
  )
}

function Bubble({ turn }: { turn: { role: string; text: string; target: string | null; scope: number | null } }) {
  const mine = turn.role === 'user'
  if (!mine) return <AgentBubble>{turn.text}</AgentBubble>
  return (
    <div className="flex justify-end">
      <div className="max-w-[38rem]">
        <div className="rounded-2xl rounded-br-md bg-ink px-4 py-3 text-sm text-bone-50">
          {turn.text}
        </div>
        {turn.scope !== null && <ScopeTag scope={turn.scope} />}
      </div>
    </div>
  )
}

/**
 * Where an answer landed. **Once per exchange, on the answer.**
 *
 * It used to print under the question *and* under the answer — the same words
 * twice per turn, in uppercase monospace, twelve times down a finished
 * transcript. The information is the point of the product and it was the
 * loudest thing on a screen otherwise made of prose, which is how something
 * important starts getting skipped.
 *
 * On the user's turn rather than the agent's, because the claim it makes is
 * about the answer: this is where *your* sentence was filed. The question's
 * intended target is already stated under the composer before you type, which
 * is when knowing it can still change what you write.
 */
function ScopeTag({ scope }: { scope: number }) {
  const label = SCOPE_LABEL[scope] ?? `L${scope}`
  return (
    <p className="mt-1 flex items-center justify-end gap-1.5 text-right text-[11px] text-ink-300">
      <span aria-hidden className="h-1 w-1 rounded-full bg-ink-200" />
      {label}
    </p>
  )
}

/**
 * The brief, as one decision instead of a form.
 *
 * The statements are listed here, read-only, each with the URL it came from.
 * They used to be on a panel beside the conversation and were rendered *again*
 * in this card as textareas — one claim, two receipts, and a wall of inputs to
 * face before being told anything. With the panel gone this is the only place
 * they appear, which is what makes the sentence above them true: a person
 * cannot outrank a reading they were never shown.
 *
 * The editors are still keyed by declared field and still behind a button,
 * because correcting is the minority case and asking for corrections that
 * confidently, that early, mostly gets "keep going" clicked through.
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

      <ul className="mt-3 divide-y divide-bone-200">
        {statements.map((statement) => (
          <li key={statement.field} className="py-3">
            <label
              htmlFor={`fix-${statement.field}`}
              className="text-xs font-medium text-ink-600"
            >
              {statement.label ?? statement.field}
            </label>
            {editing ? (
              /* Three rows, not two. At two, every statement long enough to be
                 worth correcting opened with its own first line scrolled out
                 of sight. */
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
 * Three questions, when the website could not be read.
 *
 * The alternative this replaces was a dead end. `POST /start` returned 422 and
 * the screen said the site was unreadable — after the account and the company
 * row already existed, and with nothing on the page to do about it. An audit of
 * nine real sites hit it twice, once behind Cloudflare. A signup funnel that
 * drops customers whose only fault is bot protection is not an edge case.
 *
 * **A form here is not the form ADR 0022 rules out.** That decision refuses a
 * scripted questionnaire *standing in for the agent* when no model is
 * configured. The agent runs on this path exactly as it always does; the only
 * thing that changes is where its opening facts come from. The brief step
 * already tells people "you outrank the website" — this is the same precedence,
 * applied when there is no website to outrank.
 *
 * Three fields, not a wizard. They are the grounding every later skill
 * declares, and each one is a question the founder can answer without looking
 * anything up.
 */
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
          I could not read {domain ?? 'your website'} — it may be behind bot protection, or
          there may be nothing there yet.
        </p>
        <p className="mt-2 text-ink-500">
          That is not a problem. Tell me the three things I would have looked for and we can
          carry on exactly as we would have.
        </p>
      </AgentBubble>

      <Card>
        <div className="flex flex-col gap-4">
          {(
            [
              ['What does the company do?', profile, setProfile, 'In a sentence or two.'],
              ['Who actually buys from you?', customers, setCustomers, 'The real buyers, not the market.'],
              [
                'What would make the next twelve months a success?',
                goals,
                setGoals,
                'In your words, not a target you would put in a deck.',
              ],
            ] as const
          ).map(([label, value, setValue, hint]) => (
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
              <p className="mt-1 text-xs text-ink-400">{hint}</p>
            </div>
          ))}
        </div>

        <button
          type="button"
          disabled={disabled || !ready}
          onClick={() =>
            onSubmit({
              profile: profile.trim(),
              target_customers: customers.trim(),
              goals: goals.trim(),
            })
          }
          className="mt-4 rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50 disabled:opacity-50"
        >
          That is us — keep going
        </button>
      </Card>
    </>
  )
}

/**
 * The last thing asked before the workspace is built: is this you?
 *
 * The persona used to be written into a panel beside the conversation, field by
 * field, while the person was still answering questions — which meant the one
 * artefact that decides what they see first was assembled in their peripheral
 * vision and never actually put to them. It is a summary now, at the end, with
 * a button that says yes.
 *
 * **It is shown between two committed stages, not held in memory.** The persona
 * is stage one of three; the server commits it and stops at phase `persona`,
 * so this card survives a refresh and a closed tab. Confirming runs the
 * remaining two.
 *
 * The sentence about authorisation is permanent rather than a tooltip.
 * Presentation preference is not permission, and the person is told so in the
 * one place they are being asked to agree to it.
 */
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
      {/* The builder's own sentence, which the API has always returned and the
          old panel never rendered. "Does this sound like you" is a question
          about a sentence; the rows below it are the evidence for the answer. */}
      <p className="mt-2 text-sm text-ink-600">
        {summary || 'This is what I will use to decide what your workspace shows you first.'}
      </p>

      <ul className="mt-3 divide-y divide-bone-200">
        {fields.length === 0 && (
          // The stage committed but wrote nothing worth showing. Saying so beats
          // an empty list, which reads as a real and bad result.
          <li className="py-2 text-sm italic text-ink-400">
            Nothing specific yet — your workspace will start from your role and learn the rest.
          </li>
        )}
        {fields.map((field) => (
          <li key={field.key} className="py-2">
            <p className="text-xs font-medium text-ink-600">{field.label}</p>
            <p className="mt-0.5 text-sm text-ink-500">{field.value}</p>
            {field.derived_from && (
              // The span that produced it, quoted. A summary a person cannot
              // trace back to something they said is a summary they have no
              // grounds to correct.
              <p className="mt-0.5 text-[11px] italic text-ink-300">“{field.derived_from}”</p>
            )}
          </li>
        ))}
      </ul>

      <p className="mt-3 border-l-2 border-gold pl-2 text-[11px] leading-snug text-ink-400">
        This changes what NEXUS shows you first. It never changes what you are allowed to see —
        that comes from your role, which this conversation cannot change.
      </p>

      <button
        type="button"
        onClick={onConfirm}
        disabled={disabled}
        className="mt-4 rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50 disabled:opacity-50"
      >
        That is me — finish setup
      </button>
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
  onListening,
  disabled,
}: {
  question: string
  choices?: string[]
  hint?: string
  value: string
  onChange: (value: string) => void
  onSubmit: (text: string) => void
  onListening: (listening: boolean) => void
  disabled: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <AgentBubble>{question}</AgentBubble>
      {/* The composer is a different kind of thing from a bubble and was sitting
          flush against one. A little air is what says "your turn". */}
      <div className="h-2" aria-hidden />
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
              className="rounded-full border border-bone-300 bg-white/70 px-3 py-1.5 text-sm text-ink-600 hover:border-steel-400 disabled:opacity-50"
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
        onListening={onListening}
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
  onListening,
  disabled,
}: {
  label: string
  hint?: string
  value: string
  onChange: (value: string) => void
  /** Carries the text. See the note on the choice chips above. */
  onSubmit: (text: string) => void
  onListening: (listening: boolean) => void
  disabled: boolean
}) {
  // The draft as of this render, read at the moment a phrase is transcribed
  // rather than closed over. `useDictation` builds its recogniser once and
  // holds the callback in a ref, so a callback that captured `value` would
  // append every phrase to whatever the box contained when the microphone was
  // switched on — the second sentence would silently delete the first.
  const latest = useRef(value)
  latest.current = value

  const dictation = useDictation((phrase) => {
    if (!phrase) return
    const current = latest.current
    const next = current.trim() ? `${current.trim()} ${phrase}` : phrase
    latest.current = next
    onChange(next)
  })

  useEffect(() => {
    onListening(dictation.listening)
  }, [dictation.listening, onListening])

  // A disabled composer is a request in flight. Leaving the microphone open
  // across it would transcribe into a box that is about to be cleared.
  //
  // Destructured rather than depending on `dictation` itself: the hook returns
  // a fresh object every render, so the whole-object dependency would re-run
  // this on every keystroke.
  const { listening, stop } = dictation
  useEffect(() => {
    if (disabled && listening) stop()
  }, [disabled, listening, stop])

  return (
    /* Pinned to the bottom of the canvas rather than sitting wherever the
       transcript happens to end. Where you type should not move as the
       conversation grows, and on a long transcript the inline version put the
       one control on screen below the fold. `-mx-6 px-6` so the band spans the
       canvas while the field keeps the reading measure. */
    <div className="sticky bottom-0 -mx-6 border-t border-bone-200 bg-bone-50/95 px-6 pb-5 pt-4 backdrop-blur">
      <label htmlFor="answer" className="text-xs font-medium text-ink-600">
        {label}
      </label>
      <div className="mt-1 flex items-end gap-2">
        <div className="relative flex-1">
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
            className={`w-full rounded-xl border bg-white px-3 py-2 pr-12 text-sm text-ink transition-colors ${
              dictation.listening ? 'border-clay-400 ring-1 ring-clay-300' : 'border-bone-300'
            }`}
          />
          {dictation.supported && (
            <button
              type="button"
              onClick={dictation.toggle}
              disabled={disabled}
              aria-pressed={dictation.listening}
              // Named, not just drawn. The control that opens a microphone is
              // the last one in a product that should rely on an icon to say
              // what it does.
              aria-label={dictation.listening ? 'Stop recording' : 'Answer by voice'}
              title={dictation.listening ? 'Stop recording' : 'Answer by voice'}
              className={`absolute bottom-2 right-2 grid h-8 w-8 place-items-center rounded-full border transition-colors disabled:opacity-40 ${
                dictation.listening
                  ? 'border-clay-400 bg-clay-100 text-clay-600'
                  : 'border-bone-300 bg-white text-ink-500 hover:border-steel-400 hover:text-steel-600'
              }`}
            >
              <MicIcon />
              {dictation.listening && (
                <span
                  aria-hidden
                  className="absolute inset-0 animate-pulse-ring rounded-full border border-clay-400"
                />
              )}
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => onSubmit(value)}
          disabled={disabled || !value.trim()}
          className="h-10 rounded-full bg-ink px-4 text-sm text-bone-50 disabled:opacity-40"
        >
          Send
        </button>
      </div>

      {/* Interim words are shown beside the box and never spliced into it. The
          recogniser rewrites them in place as it changes its mind, and writing
          that into a controlled textarea makes the caret jump and eats anything
          typed alongside. Only finalised phrases reach the draft. */}
      {dictation.listening && (
        <p role="status" aria-live="polite" className="mt-1 text-xs text-clay-600">
          Listening{dictation.interim ? ` — “${dictation.interim}”` : '… speak when ready.'}
        </p>
      )}
      {dictation.error && (
        <p role="alert" className="mt-1 text-xs text-clay-600">
          {dictation.error}
        </p>
      )}
      {hint && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
          {hint.startsWith('Stored as') ? (
            <>
              <span>Stored as</span>
              {/* A pill with a dot, because where an answer lands is a status
                  and reads as one. It was a grey line that looked like a debug
                  label for the fact it is most important a person believes. */}
              <span className="inline-flex items-center gap-1.5 rounded-full bg-clay-100 px-2.5 py-1 font-medium text-clay-600">
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-clay-400" />
                {hint.replace(/^Stored as /, '')}
              </span>
            </>
          ) : (
            <span>{hint}</span>
          )}
        </p>
      )}
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

/**
 * A fragment made into a sentence, or nothing.
 *
 * `reason` arrives either from the model or from the server's own fallback, and
 * neither is written to be the second half of a sentence somebody else started.
 * The result on screen was "That is enough to build on. nothing further worth
 * asking" — a capital letter and a full stop short of readable, on the last
 * thing the interview says.
 */
export function sentence(text: string | null | undefined): string {
  const trimmed = text?.trim()
  if (!trimmed) return ''
  const capitalised = trimmed[0].toUpperCase() + trimmed.slice(1)
  return /[.!?]$/.test(capitalised) ? capitalised : `${capitalised}.`
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-bone-300 bg-white/90 p-4 backdrop-blur-sm">{children}</div>
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
 * finished loading and has nothing on it. The aura says the process is alive;
 * the sentence says what it is doing and roughly how long — `useSlowLabel`
 * rewrites it once the wait runs past the usual.
 *
 * **The sentence stays.** `globals.css` collapses every animation to a single
 * iteration under `prefers-reduced-motion`, so the motion stops for anyone with
 * that set. A loader that is the *only* signal would go silent for exactly the
 * people least able to guess; motion is decoration here, never the message.
 *
 * `role="status"` rather than a bare div: the label changes mid-wait, and a
 * screen reader should hear that it changed without the focus moving.
 *
 * **It has to be able to stop.** A failure of the opening request leaves this
 * component with no state to render, so this is the screen it falls back to —
 * and a wait animation is exactly the wrong thing to show over a request that
 * has already failed. It said "Loading…" indefinitely, because `useSlowLabel`
 * returns its idle string once nothing is in flight. The error takes the place
 * of the pulse rather than appearing under it: two signals disagreeing about
 * whether anything is still happening is worse than either alone.
 */
function Booting({
  label,
  error,
  onRetry,
}: {
  label: string
  error?: string | null
  onRetry?: () => void
}) {
  if (error) {
    return (
      <div className="relative grid min-h-screen place-items-center px-6">
        <OnboardingAura state="idle" />
        <div className="max-w-md rounded-2xl border border-bone-300 bg-white/90 p-6 backdrop-blur-sm">
          <h1 className="font-display text-lg text-ink">Setup could not start</h1>
          <p role="alert" className="mt-2 text-sm text-ink-600">
            {error}
          </p>
          {/* Not "nothing has been saved" — that read as a contradiction of the
              sentence after it, and it is not true either. Every turn is
              committed as it happens, which is exactly why trying again resumes
              rather than restarts. */}
          <p className="mt-3 text-xs text-ink-400">
            Nothing was lost. Anything you have already answered is saved on your workspace,
            and trying again picks up from there.
          </p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-4 rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50"
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
        {/* The same mark as the header, drawn large. Three staggered dots used
            to sit here saying "something is happening" in triplicate, next to a
            background disc saying it a fourth time. One thing, once. */}
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
          Sign-in and every existing workspace are unaffected. There is deliberately no
          fallback form — a questionnaire that quietly replaced the assistant would collect
          less and look the same.
        </p>
      </div>
    </div>
  )
}
