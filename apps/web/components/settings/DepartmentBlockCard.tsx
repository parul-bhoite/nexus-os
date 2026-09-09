'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import {
  answerBlock,
  fetchBlock,
  type BlockQuestion,
  type DepartmentBlock,
} from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * Your department's questions — panel 3 (`doc/13` §14).
 *
 * Named `DepartmentBlockCard` rather than `BlockCard`: the dashboard already
 * has a `BlockCard`, and it is a different thing entirely — one capability on a
 * director's rail. Two components with one name for two concepts is the
 * collision `connections.Tool` and `sources.SourceEntry` were separated over,
 * and it costs nothing to avoid here.
 *
 * This is the screen the restate rule was built for. Step D's Setup tab reads
 * the answers back; this is where they change, and a **changed** answer moves
 * figures somebody may already have acted on — so the API audits it and names
 * the capabilities that read it. A first answer is not a restatement, which is
 * why that distinction lives server-side where the previous value is known.
 *
 * ## Two authority rules, and neither is guessed here
 *
 * `may_answer` and `binds` are **served**. A UI deciding for itself would be
 * guessing at an authority rule, and the guesses that matter are the wrong
 * ones: a Contributor shown a form that binds, or a Manager shown a read-only
 * block for their own department.
 *
 * - **`may_answer: false`** — read-only, and still shown. Hiding it would leave
 *   somebody unable to see what their own department has been asked, which is
 *   information they are entitled to.
 * - **`binds: false`** — a Contributor's answer is a *proposal* that waits for
 *   a manager at the review gate (Q31/D22). The button says so, because
 *   somebody who thinks they have set a threshold and has not would find out
 *   from a figure that did not move.
 */

function Question({
  question,
  draft,
  editable,
  onChange,
}: {
  question: BlockQuestion
  draft: string | undefined
  editable: boolean
  onChange: (value: string) => void
}) {
  const current =
    draft ?? (typeof question.answer === 'string' ? question.answer : '')

  return (
    <li className="border-t border-ink-100 py-4 first:border-t-0 first:pt-0">
      <label className="block">
        <span className="text-[0.95rem] font-medium text-ink-900">{question.prompt}</span>
        {/* Every question carries its `why`, and it is the sentence that makes
            answering feel worth doing rather than like filling a form. */}
        <span className="mt-1 block text-sm leading-relaxed text-ink-500">
          {question.why}
        </span>
        <input
          type="text"
          className="mt-2 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-ink-900 disabled:bg-bone-100 disabled:text-ink-500"
          value={current}
          disabled={!editable}
          onChange={(event) => onChange(event.target.value)}
          placeholder={editable ? 'Not answered yet' : 'Not answered yet'}
        />
      </label>

      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-400">
        {/* Q33, shown to the person answering: a question with no consumer is a
            form field, and naming the consumer is what makes the difference
            visible rather than a claim in a document. */}
        <span className="font-mono text-2xs tracking-[0.04em]">
          reads it: {question.consumed_by}
        </span>
        {question.proposed ? (
          <span className="font-medium text-clay-600">
            Proposed — waiting for a manager
          </span>
        ) : null}
      </p>
    </li>
  )
}

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string; code: number }
  | { status: 'ready'; block: DepartmentBlock }

export function DepartmentBlockCard({ department, label }: { department: string; label: string }) {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState('')
  const [problem, setProblem] = useState('')

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })
    fetchBlock(department)
      .then((block) => live && setState({ status: 'ready', block }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError ? caught.message : 'Could not read the questions.',
          code: caught instanceof AuthError ? caught.status : 0,
        })
      })
    return () => {
      live = false
    }
  }, [department])

  // 404 is a department this company does not run, or one this caller cannot
  // reach. Either way the panel is absent rather than explaining itself — the
  // same rule the dashboard follows, because how a company is organised is
  // itself a fact about it.
  if (state.status === 'error' && state.code === 404) return null

  if (state.status === 'loading') return <Waiting>Loading the questions…</Waiting>

  if (state.status === 'error') {
    return (
      <div
        role="alert"
        className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
      >
        {state.message}
      </div>
    )
  }

  const { block } = state
  const editable = block.may_answer
  const changed = Object.entries(drafts).filter(([key, value]) => {
    const question = block.questions.find((q) => q.key === key)
    const before = typeof question?.answer === 'string' ? question.answer : ''
    return value !== before
  })

  const submit = async () => {
    setSaving(true)
    setProblem('')
    try {
      const fresh = await answerBlock(
        department,
        changed.map(([key, value]) => ({ key, value })),
      )
      setState({ status: 'ready', block: fresh })
      setDrafts({})
      setSaved(
        block.binds
          ? 'Saved. Any figure computed from a changed answer is recorded as restated.'
          : 'Proposed. A manager sees it at the review gate before it becomes a fact.',
      )
    } catch (caught: unknown) {
      setProblem(
        caught instanceof AuthError ? caught.message : 'Could not save those answers.',
      )
    } finally {
      setSaving(false)
    }
  }

  const answered = block.questions.filter((q) => q.answered).length

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <header>
        <h2 className="font-display text-lg text-ink-900">{label} questions</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          {answered} of {block.questions.length} answered. These are what turn this
          department&rsquo;s figures from generic into yours — a conversion rate means
          nothing until somebody says what counts as a lead.
        </p>
        {!editable ? (
          <p className="mt-3 rounded-lg border border-ink-100 bg-bone-50 px-3 py-2 text-sm text-ink-500">
            Read-only for you. Thresholds and definitions are the department
            manager&rsquo;s to set — they are what your own figures are measured against,
            which is why you can see them.
          </p>
        ) : !block.binds ? (
          <p className="mt-3 rounded-lg border border-gold-300 bg-gold-100 px-3 py-2 text-sm text-clay-600">
            Your answers are <strong>proposals</strong>. A manager confirms them at the
            review gate before they become the department&rsquo;s position.
          </p>
        ) : null}
      </header>

      <ul className="flex flex-col">
        {block.questions.map((question) => (
          <Question
            key={question.key}
            question={question}
            draft={drafts[question.key]}
            editable={editable}
            onChange={(value) => {
              setSaved('')
              setProblem('')
              setDrafts((previous) => ({ ...previous, [question.key]: value }))
            }}
          />
        ))}
      </ul>

      {problem ? (
        <p role="alert" className="text-sm font-medium text-clay-600">
          {problem}
        </p>
      ) : null}

      {editable ? (
        <div className="flex flex-wrap items-center gap-4 border-t border-ink-100 pt-4">
          <Button onClick={() => void submit()} disabled={saving || changed.length === 0}>
            {saving ? 'Saving…' : block.binds ? 'Save answers' : 'Propose answers'}
          </Button>
          {saved ? <span className="text-sm text-steel-600">{saved}</span> : null}
        </div>
      ) : null}
    </section>
  )
}
