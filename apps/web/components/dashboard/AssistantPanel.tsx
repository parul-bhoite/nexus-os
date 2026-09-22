'use client'

import { useState } from 'react'
import type { Assistant, AssistantReply } from '@/lib/dashboard-client'
import { askDirector } from '@/lib/dashboard-client'

/**
 * The panel P15 reserved and P20 fills. Q67.
 *
 * **The argument that kept this box out survives it.** For five phases this
 * component rendered a question list and the sentence "not available yet",
 * because *"an input that accepts a question and cannot answer it is worse than
 * none: somebody types the thing they most want to know and gets silence, and
 * the next thing they conclude is that the product does not work."* That is
 * still true. It is recorded here rather than deleted because it is the reason
 * the box took this long, and because it is the argument that should be made
 * again the next time a surface is tempted to ship ahead of its guarantees.
 *
 * What changed is that the guarantees arrived, and they are specific
 * (`doc/20` §5 Q7):
 *
 * 1. Evals that fail when the assistant is wrong — a payload that dictates a
 *    figure, a fabricated citation, a scope leak — not ten assertions over a
 *    dataclass.
 * 2. Refusals authored by us, which the model cannot reword: there is no
 *    free-text reason field in the schema for it to fill.
 * 3. A refusal identical whether or not the content exists, so the wording
 *    cannot be used to probe.
 * 4. A question list the assistant can actually answer (ADR 0052) — documents,
 *    not computed figures.
 *
 * **The questions still come from the API**, not from a list here: they are
 * per-department and they are specification, and a browser inventing a
 * plausible-sounding one would be describing a product nobody built.
 *
 * **A refusal is rendered with no citations and no prose.** The sentence is the
 * whole response — `doc/20` §5 Q6.2 makes it the one string that must not vary
 * with who is asking, so this component must not decorate it, prefix it, or
 * pair it with a "try rephrasing" of its own invention.
 */
export function AssistantPanel({
  assistant,
  department,
}: {
  assistant: Assistant
  department?: string
}) {
  const [question, setQuestion] = useState('')
  const [reply, setReply] = useState<AssistantReply | null>(null)
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  // A0's pin, still green: with `available` false there is no input, no
  // textarea and no form in the tree at all.
  if (!assistant.available) {
    return (
      <aside className="mt-8 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
          Ask the {assistant.director}
        </p>
        <ul className="mt-3 flex flex-col gap-2">
          {assistant.questions.map((q, index) => (
            // F-28: `key={q}` collides whenever the bank asks the same
            // question twice, or repeats the placeholder empty string —
            // falling back to the array index, which is stable here because
            // this list is never reordered or filtered.
            <li key={q || index} className="text-[0.95rem] leading-relaxed text-ink-700">
              &ldquo;{q}&rdquo;
            </li>
          ))}
        </ul>
        <p className="mt-4 border-t border-ink-100 pt-3 text-sm leading-relaxed text-ink-500">
          Not available yet. When it is, it will answer from the documents this workspace has
          uploaded — every answer quoting the passage it came from, and a question your documents
          cannot answer refused with the reason rather than answered thinly.
        </p>
      </aside>
    )
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const asked = question.trim()
    if (!asked || pending || !department) return

    setPending(true)
    setFailed(null)
    setReply(null)
    try {
      setReply(await askDirector(department, asked))
    } catch {
      // Distinct from a refusal on purpose. "We could not reach the assistant"
      // and "your documents do not cover that" are different facts, and
      // collapsing them would teach a founder to distrust the second.
      setFailed('Cannot reach the assistant right now. Nothing was spent — try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <aside className="mt-8 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
        Ask the {assistant.director}
      </p>

      <form onSubmit={submit} className="mt-3 flex flex-col gap-2">
        <label htmlFor="assistant-question" className="sr-only">
          Ask a question about this workspace&rsquo;s documents
        </label>
        <textarea
          id="assistant-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          maxLength={1000}
          placeholder={assistant.questions[0] ?? 'Ask about an uploaded document'}
          className="w-full resize-none rounded-xl border border-ink-200 px-3 py-2 text-[0.95rem] leading-relaxed text-ink-800 focus:border-ink-400 focus:outline-none"
        />
        <div className="flex items-center justify-between gap-3">
          <p className="text-2xs text-ink-400">
            Answers come from documents this workspace has uploaded, quoting the passage.
          </p>
          <button
            type="submit"
            disabled={pending || !question.trim()}
            className="rounded-lg bg-ink-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            {pending ? 'Reading…' : 'Ask'}
          </button>
        </div>
      </form>

      {!reply && !pending && !failed ? (
        <ul className="mt-4 flex flex-col gap-2 border-t border-ink-100 pt-3">
          {assistant.questions.map((q, index) => (
            <li key={q || index}>
              <button
                type="button"
                onClick={() => setQuestion(q)}
                className="text-left text-[0.95rem] leading-relaxed text-ink-600 hover:text-ink-900"
              >
                &ldquo;{q}&rdquo;
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {failed ? (
        <p className="mt-4 border-t border-ink-100 pt-3 text-sm leading-relaxed text-ink-500">
          {failed}
        </p>
      ) : null}

      {reply && !reply.answered ? (
        /* The sentence, alone. No citations, no prose, nothing added. */
        <p
          data-testid="assistant-refusal"
          className="mt-4 border-t border-ink-100 pt-3 text-sm leading-relaxed text-ink-500"
        >
          {reply.sentence}
        </p>
      ) : null}

      {reply?.answered ? (
        <div className="mt-4 border-t border-ink-100 pt-3">
          <p className="text-[0.95rem] leading-relaxed text-ink-800">{reply.prose}</p>
          <ul className="mt-3 flex flex-col gap-1">
            {reply.citations.map((citation, index) => (
              // F-28: `chunkId` defaults to `''` when the server omits it
              // (`c.chunk_id ?? ''` in `dashboard-client.ts`), so two such
              // citations in one answer collided. The index is stable here —
              // this list is rendered once per reply and never reordered.
              <li key={citation.chunkId || index}>
                <a
                  // **`/documents#doc-<id>`, not `/documents/<id>`.** There is
                  // no per-document page: the first version of this linked to
                  // one and every citation 404ed, which a unit test could not
                  // see and a browser found immediately. The library highlights
                  // the row it lands on.
                  href={`/documents#doc-${citation.documentId}`}
                  data-testid="assistant-citation"
                  className="font-mono text-2xs text-ink-500 underline underline-offset-2 hover:text-ink-900"
                >
                  {citation.sourceLabel ?? 'Source'}
                  {citation.sourcePage !== null ? `, page ${citation.sourcePage}` : ''}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </aside>
  )
}
