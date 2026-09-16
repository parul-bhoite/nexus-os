'use client'

import Link from 'next/link'
import type { OpenQuestions } from '@/lib/dashboard-client'

/**
 * What is still open on the founder's side — `doc/14` step 5.
 *
 * This replaces the reference mock's *Risks / Opportunities* columns. Those
 * needed a risk engine nobody has built; every line here comes from the question
 * bank, which has carried a `why` and a declared consumer since it was written.
 *
 * ## Answering informs; it does not unlock
 *
 * The design first claimed seven capabilities were "unlockable by answering".
 * The registry says zero — every fact-consuming tile also needs a source — so
 * the copy makes the smaller, true claim, and the split does the rest of the
 * work: one tier moves a number already on this page, and the other is counted
 * because a founder cannot act on it yet.
 *
 * ## Why the second tier is a number rather than a list
 *
 * Twenty-eight rows of questions whose consumers are not built would bury the
 * one that matters, and would let a founder believe the product is waiting on
 * them when it is mostly waiting on us. ADR 0030 makes the same argument about
 * capabilities; this is it at question level.
 */
export function OpenOnYourSide({ questions }: { questions: OpenQuestions }) {
  // Nothing open at all is a real state and gets no region. Unlike the brief,
  // there is no absence to distinguish here: an empty list means every question
  // has an answer, which is unambiguous and needs no sentence.
  if (questions.total === 0) return null

  return (
    <section aria-labelledby="open-heading">
      <h2 id="open-heading" className="font-display text-title font-medium text-ink-900">
        Open on your side
      </h2>
      <p className="mt-1 max-w-prose text-sm text-ink-500">
        Questions only. What you connect is a different kind of thing and sits above.
      </p>

      <div className="mt-4 rounded-2xl border border-ink-100 bg-bone-100 px-5 py-5">
        {questions.changes_a_figure.length > 0 ? (
          <>
            <p className="font-mono text-2xs uppercase tracking-[0.1em] text-clay-600">
              {questions.changes_a_figure.length === 1
                ? 'One answer would change a figure on this page'
                : `${questions.changes_a_figure.length} answers would change a figure on this page`}
            </p>
            <ul className="mt-3">
              {questions.changes_a_figure.map((question) => (
                <li
                  key={`${question.department}.${question.key}`}
                  className="border-b border-ink-100 py-3 last:border-b-0"
                >
                  <p className="text-[0.95rem] font-medium text-ink-900">{question.prompt}</p>
                  {/* The bank's own sentence about what the answer is for. A
                      question with no stated purpose is a form field (doc 06),
                      and rewriting it here would make two of them. */}
                  <p className="mt-1 max-w-prose text-sm leading-relaxed text-ink-600">
                    {question.why}
                  </p>
                  <p className="mt-1.5 text-2xs text-ink-400">
                    Read by <span className="text-ink-600">{question.consumer_name}</span>
                  </p>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {questions.waiting_on_us > 0 ? (
          <p
            className={`max-w-prose text-sm leading-relaxed text-ink-500 ${
              questions.changes_a_figure.length > 0
                ? 'mt-4 border-t border-ink-100 pt-3'
                : ''
            }`}
          >
            <span className="font-semibold text-ink-800">
              {questions.waiting_on_us} more questions
            </span>{' '}
            are open, and answering them changes nothing yet — the capabilities that read
            them are not built. They are worth answering when you have a moment, not
            before.
          </p>
        ) : null}

        <Link
          href="/onboarding"
          className="mt-4 inline-block text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Answer these in workspace setup
        </Link>
      </div>
    </section>
  )
}
