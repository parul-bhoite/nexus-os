'use client'

import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import {
  departmentLabel,
  fetchQuestions,
  saveAnswers,
  type Question,
} from '@/lib/onboarding-client'
import { ModelUnavailableError, read, start } from '@/lib/agent-onboarding-client'
import type { AuraState } from '@/components/onboarding/OnboardingAura'
import { easing, fadeUp, useMotionSafe } from '@/lib/motion'

/**
 * Part 2 of 3, continued — the hybrid question engine (ADR 0067, Engine C).
 *
 * Two beats, both inside this one stage component:
 *
 * 1. An **optional** scan — `start()` then `read()` from the existing eight-
 *    phase agent client, run best-effort purely for the ambient "reading your
 *    website" moment behind `OnboardingAura`. This deliberately does **not**
 *    drive the agent's phase machine any further: no brief, no discovery turns,
 *    no corrections. `ModelUnavailableError` and any other failure are caught
 *    and swallowed — per ADR 0011, absence of a model is a supported state,
 *    not a degraded one, so the scan simply does not happen and the catalogue
 *    carries the whole stage.
 * 2. The **deterministic catalogue** (`fetchQuestions`), filtered to the
 *    Areas of Interest chosen in the previous stage, rendered one question at
 *    a time with suggestion chips drawn from the question's own `options`.
 */

type Phase = 'scanning' | 'loading' | 'error' | 'empty' | 'asking'

function hasValue(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim() !== ''
  if (Array.isArray(value)) return value.length > 0
  return true
}

/** How long the scanning beat must be visible before moving on — just long
 *  enough to read as a deliberate moment rather than a flash, never a reason
 *  the whole flow waits for a ~17s crawl. Zero under reduced motion: "reduced"
 *  must not mean "the content changes anyway, just make it jarring". */
const MIN_SCAN_MS = 900
/** The most this ambient beat may hold the flow up before giving up on it —
 *  `read()` is measured at ~17s in the best case, and this screen's job is the
 *  catalogue, not the crawl. */
const MAX_SCAN_MS = 6000

/** Catalogue questions the combined flow has already asked, by `key`, so it
 *  does not ask them a second time.
 *
 *  - `company_url` — the website captured in the Company stage (stored on the
 *    workspace, not as an `onboarding_answer`, so it comes back here
 *    unanswered). Asking a founder for their website again, one step after they
 *    typed it, reads as the product not listening.
 *  - `role` — the Company stage already asks "Your role". This catalogue
 *    question only restates it as a dropdown, and it is **safe to drop**: per
 *    `services/api/app/routes/setup.py`, the `role` answer writes an
 *    `onboarding_answer` row and *"Nothing here touches `membership`"* — it is a
 *    stated claim, never the authorising `membership.role`, so not asking it
 *    changes no permission.
 *  - `department` — likewise a stated-claim `onboarding_answer`, and it overlaps
 *    in feel with the Areas of Interest the founder just chose. Same safety:
 *    it is not `membership.departments`.
 *
 *  Removing `role`/`department` was the product owner's call to cut the two
 *  questions that felt like a repeat of the first two stages. */
const ALREADY_CAPTURED = new Set(['company_url', 'role', 'department'])

export function QuestionsStage({
  selectedDepartments,
  onAuraChange,
  onComplete,
}: {
  selectedDepartments: string[]
  onAuraChange: (state: AuraState) => void
  onComplete: () => void
}) {
  const [phase, setPhase] = useState<Phase>('scanning')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [questions, setQuestions] = useState<Question[]>([])
  const [index, setIndex] = useState(0)
  const [draft, setDraft] = useState<unknown>(null)
  const [freeText, setFreeText] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const safe = useMotionSafe()
  const scanRanRef = useRef(false)
  // `alive` is a ref, not a closure `let`, on purpose. React Strict Mode (dev)
  // mounts this component twice: the first mount starts the scan and its
  // cleanup would flip a closure flag to false, and the second mount — guarded
  // by `scanRanRef` so it does not fire `start()`/`read()` again — would never
  // re-arm it, so the race's completion handler would bail and the scan beat
  // would hang forever. A ref re-armed at the top of every effect run survives
  // that, while `scanRanRef` still prevents a second agent call.
  const aliveRef = useRef(true)

  // ── Beat 1: the optional scan ──────────────────────────────────────────
  useEffect(() => {
    aliveRef.current = true
    if (scanRanRef.current) {
      return () => {
        aliveRef.current = false
      }
    }
    scanRanRef.current = true
    onAuraChange('thinking')

    const started = Date.now()
    const scan = (async () => {
      try {
        await start()
        await read()
      } catch (error) {
        // Best-effort only. `ModelUnavailableError` (no key configured) and
        // any other failure — a timed-out crawl, an already-finished session —
        // are all the same instruction here: skip silently, go to questions.
        void error
      }
    })()

    const timeout = new Promise<void>((resolve) => setTimeout(resolve, MAX_SCAN_MS))

    void Promise.race([scan, timeout]).then(async () => {
      const elapsed = Date.now() - started
      const remaining = safe ? Math.max(0, MIN_SCAN_MS - elapsed) : 0
      if (remaining > 0) await new Promise((resolve) => setTimeout(resolve, remaining))
      if (!aliveRef.current) return
      onAuraChange('idle')
      void loadQuestions()
    })

    return () => {
      aliveRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadQuestions() {
    setPhase('loading')
    setErrorMessage(null)
    try {
      const { questions: all } = await fetchQuestions()
      const relevant = all.filter(
        (q) =>
          q.writable &&
          !ALREADY_CAPTURED.has(q.key) &&
          (q.department === null || selectedDepartments.includes(q.department)),
      )
      setQuestions(relevant)
      setIndex(0)
      if (relevant.length === 0) {
        setPhase('empty')
        return
      }
      seedDraft(relevant[0])
      setPhase('asking')
    } catch (error) {
      setErrorMessage(
        error instanceof AuthError ? error.message : 'Could not reach the account service.',
      )
      setPhase('error')
    }
  }

  function seedDraft(question: Question) {
    setDraft(question.value ?? (question.answer_type === 'multi_choice' ? [] : null))
    setFreeText('')
  }

  const current = phase === 'asking' ? questions[index] : null
  const answeredCount = questions.filter((q) => hasValue(q.value)).length

  function finalValue(question: Question): unknown {
    const typed = freeText.trim()
    if (typed === '') return draft
    if (question.answer_type === 'multi_choice') {
      const arr = Array.isArray(draft) ? (draft as string[]) : []
      return arr.includes(typed) ? arr : [...arr, typed]
    }
    return typed
  }

  /** Shape a raw answer into what the API's validator accepts, or explain why it
   *  cannot. Money is the one type the input cannot satisfy on its own: the field
   *  yields a string, but `validate_answer` requires a JSON number (it rejects
   *  `"5000"` with "must be a number"). Coerce here, and refuse a non-number with
   *  a sentence the founder can act on rather than letting the server answer with
   *  its own. Every other type already matches the contract. */
  function coerceForSave(
    question: Question,
    value: unknown,
  ): { ok: true; value: unknown } | { ok: false; message: string } {
    if (question.answer_type === 'money') {
      const raw = (typeof value === 'number' ? String(value) : String(value ?? '')).trim()
      const amount = Number(raw.replace(/[,\s]/g, ''))
      if (raw === '' || !Number.isFinite(amount)) {
        return { ok: false, message: 'Enter the amount as a number — for example 5000.' }
      }
      if (amount < 0) return { ok: false, message: 'That cannot be a negative number.' }
      return { ok: true, value: amount }
    }
    return { ok: true, value }
  }

  function advance() {
    // Clear any save error before the next question renders. Without this a
    // failure on one question (or a validation message) lingers over the next,
    // which reads as the new question being wrong. `handleContinue` clears it on
    // its own path too; `handleSkip` relies on this.
    setSaveError(null)
    const next = index + 1
    if (next >= questions.length) {
      onComplete()
      return
    }
    setIndex(next)
    seedDraft(questions[next])
  }

  async function handleContinue() {
    if (!current) return
    const raw = finalValue(current)
    if (!hasValue(raw)) {
      advance()
      return
    }
    const coerced = coerceForSave(current, raw)
    if (!coerced.ok) {
      // A local, actionable message — not a round trip to be told the same thing
      // in the server's words. Stay on the question so it can be corrected.
      setSaveError(coerced.message)
      return
    }
    const value = coerced.value
    setSaving(true)
    setSaveError(null)
    try {
      await saveAnswers([{ key: current.key, value }])
      setQuestions((prev) => prev.map((q, i) => (i === index ? { ...q, value } : q)))
      advance()
    } catch (error) {
      setSaveError(
        error instanceof AuthError ? error.message : 'That answer did not save. Your other answers are safe.',
      )
    } finally {
      setSaving(false)
    }
  }

  function handleSkip() {
    advance()
  }

  if (phase === 'scanning') {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display text-page text-ink-900">We&rsquo;re reading your website.</h1>
        <p className="max-w-read text-body text-ink-600">
          This takes a moment. You don&rsquo;t need to wait here — we&rsquo;ll bring you back the
          second it&rsquo;s ready.
        </p>
        <div aria-hidden className="relative mt-4 h-0.5 overflow-hidden rounded-full bg-bone-200">
          <motion.div
            className="absolute inset-y-0 w-2/5 bg-gradient-to-r from-transparent via-steel-500 to-transparent"
            animate={safe ? { x: ['-120%', '320%'] } : { x: '0%' }}
            transition={
              safe
                ? { duration: 2.2, repeat: Infinity, ease: easing.inOut }
                : { duration: 0 }
            }
          />
        </div>
      </div>
    )
  }

  if (phase === 'loading') {
    return (
      <div className="flex flex-col gap-4" aria-hidden>
        <h1 className="font-display text-page text-ink-500">Preparing your questions…</h1>
        <div className="h-6 w-1/2 animate-breathe rounded-full bg-bone-200" />
        <div className="h-9 w-full animate-breathe rounded-control bg-bone-200" />
        <div className="flex gap-2">
          <div className="h-11 w-20 animate-breathe rounded-full bg-bone-200" />
          <div className="h-11 w-20 animate-breathe rounded-full bg-bone-200" />
        </div>
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div role="alert" className="rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
        <h3 className="font-medium text-ink-800">Could not reach the account service</h3>
        <p className="mt-2 text-sm text-clay-600">{errorMessage}</p>
        <Button variant="danger" size="sm" className="mt-4" onClick={() => void loadQuestions()}>
          Retry
        </Button>
      </div>
    )
  }

  if (phase === 'empty') {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display text-page text-ink-900">That&rsquo;s everything for the areas you chose.</h1>
        <p className="text-body text-ink-600">
          Add another area of interest in Settings any time, and NEXUS will ask what it needs then.
        </p>
        <Button size="lg" className="mt-2 self-start" onClick={onComplete}>
          Continue to your workspace
        </Button>
      </div>
    )
  }

  if (!current) return null

  return (
    <div className="flex flex-col gap-6">
      <p className="text-label font-medium text-ink-500">
        Scoped to {selectedDepartments.map(departmentLabel).join(', ') || 'your company'}
      </p>

      <AnimatePresence mode="wait">
        <motion.div
          key={current.key}
          variants={fadeUp(safe)}
          initial="hidden"
          animate="show"
          className="flex flex-col gap-4"
        >
          <p className="text-meta text-ink-500">
            <b className="font-medium text-ink-700">Why we ask —</b> {current.why}
          </p>
          <h2 className="font-display text-[1.4rem] leading-tight text-ink-900">
            {current.prompt}
            {current.department ? (
              <span className="ml-2 text-[0.9rem] font-normal text-ink-400">
                — {departmentLabel(current.department)}
              </span>
            ) : null}
          </h2>

          <AnswerEditor
            question={current}
            value={draft}
            onChange={setDraft}
            freeText={freeText}
            onFreeTextChange={setFreeText}
          />
        </motion.div>
      </AnimatePresence>

      {saveError ? (
        <p role="alert" className="text-sm text-clay-600">
          {saveError}
        </p>
      ) : null}

      <p aria-live="polite" className="font-mono text-2xs uppercase tracking-[0.08em] text-ink-400">
        {answeredCount} of {questions.length} answered — skip any of them
      </p>

      <div className="flex items-center gap-5">
        <Button
          size="lg"
          loading={saving}
          loadingLabel="Saving…"
          onClick={() => void handleContinue()}
        >
          Continue
        </Button>
        <Button variant="quiet" onClick={handleSkip} disabled={saving}>
          Skip this one
        </Button>
      </div>
    </div>
  )
}

function Chip({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean
  onClick: () => void
  children: string
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`inline-flex min-h-[2.75rem] items-center rounded-full border px-4 text-body transition-colors duration-base ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-steel-500 ${
        pressed
          ? 'border-ink-800 bg-ink-800 text-bone-50'
          : 'border-bone-300 bg-white text-ink-700 sm:hover:border-steel-400'
      }`}
    >
      {children}
    </button>
  )
}

function AnswerEditor({
  question,
  value,
  onChange,
  freeText,
  onFreeTextChange,
}: {
  question: Question
  value: unknown
  onChange: (value: unknown) => void
  freeText: string
  onFreeTextChange: (value: string) => void
}) {
  const chips = question.options

  if (question.answer_type === 'single_choice') {
    return (
      <>
        <div role="group" aria-label="Suggested answers" className="flex flex-wrap gap-2">
          {chips.map((choice) => (
            <Chip
              key={choice.value}
              pressed={value === choice.value}
              onClick={() => onChange(value === choice.value ? null : choice.value)}
            >
              {choice.label}
            </Chip>
          ))}
        </div>
        {question.free_entry ? (
          <FreeEntry value={freeText} onChange={onFreeTextChange} />
        ) : null}
      </>
    )
  }

  if (question.answer_type === 'multi_choice') {
    const arr = Array.isArray(value) ? (value as string[]) : []
    return (
      <>
        <div role="group" aria-label="Suggested answers" className="flex flex-wrap gap-2">
          {chips.map((choice) => (
            <Chip
              key={choice.value}
              pressed={arr.includes(choice.value)}
              onClick={() =>
                onChange(
                  arr.includes(choice.value)
                    ? arr.filter((v) => v !== choice.value)
                    : [...arr, choice.value],
                )
              }
            >
              {choice.label}
            </Chip>
          ))}
        </div>
        {question.free_entry ? (
          <FreeEntry value={freeText} onChange={onFreeTextChange} />
        ) : null}
      </>
    )
  }

  if (question.answer_type === 'long_text') {
    return (
      <textarea
        aria-label={question.prompt}
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        rows={4}
        className="w-full rounded-control border border-ink-200 bg-white p-4 text-body text-ink-900 shadow-e1 outline-none transition-colors focus:border-steel-500 focus:ring-2 focus:ring-steel-200"
      />
    )
  }

  // money / text / url — an input, with suggestion chips above it when the
  // catalogue carries any (e.g. deal-size buckets for a money question).
  return (
    <>
      {chips.length > 0 ? (
        <div role="group" aria-label="Suggested answers" className="flex flex-wrap gap-2">
          {chips.map((choice) => (
            <Chip key={choice.value} pressed={value === choice.value} onClick={() => onChange(choice.value)}>
              {choice.label}
            </Chip>
          ))}
        </div>
      ) : null}
      <input
        aria-label={question.prompt}
        type={question.answer_type === 'url' ? 'url' : 'text'}
        inputMode={question.answer_type === 'money' ? 'decimal' : undefined}
        // Stringify so a resumed answer prefills — a money value comes back from
        // the API (and is stored locally) as a number, which an `only strings`
        // guard would silently blank out.
        value={value == null ? '' : String(value)}
        onChange={(e) => onChange(e.target.value)}
        placeholder={chips.length > 0 ? 'Or type an exact figure…' : undefined}
        className="h-11 w-full rounded-control border border-ink-200 bg-white px-4 text-body text-ink-900 shadow-e1 outline-none transition-colors focus:border-steel-500 focus:ring-2 focus:ring-steel-200"
      />
    </>
  )
}

function FreeEntry({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Or type your own…"
      className="h-11 w-full rounded-control border border-ink-200 bg-white px-4 text-body text-ink-900 shadow-e1 outline-none transition-colors focus:border-steel-500 focus:ring-2 focus:ring-steel-200"
    />
  )
}
