'use client'

import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Overlay'
import { Empty, Failed } from '@/components/ui/States'
import { Waiting } from '@/components/ui/Waiting'
import { AuthError } from '@/lib/auth-client'
import {
  type ApprovalScope,
  type Decision,
  type ReviewItem,
  decideChunk,
  readReviewQueue,
} from '@/lib/review-queue-client'

/**
 * The queue of chunks the classifier would not place on its own.
 *
 * **Why this screen is the other half of ADR 0051.** Wiring `rules.propose` in
 * let the confident, non-sensitive majority reach a department automatically.
 * Everything else — a payroll line, an IBAN, a paragraph whose vocabulary was
 * ambiguous — is withheld to L5 and waits here. Until this screen existed it
 * waited for ever, because no client called the endpoint: withheld content was
 * stranded rather than queued, which made the gate a place documents went to
 * disappear.
 *
 * **It shows the decision, not just the text.** Each item carries the scope the
 * classifier proposed, how sure it was, and which classifier said so, because a
 * reviewer approving forty chunks needs to know whether they are checking a
 * confident guess or a refusal to guess. `classified_by` distinguishes
 * `rules-v1` from `rules-v1:classifier-failed`, and those deserve different
 * amounts of attention.
 *
 * **Nothing here decides authority.** The scope buttons ask; `may_reach_scope`
 * in the API answers, and a refusal is rendered as the API's own sentence
 * against the item that was refused. Filtering the buttons by a guess at the
 * reader's role would either hide a decision they are allowed to make or offer
 * one they are not, and this app does not hold the authority to know which.
 */

const SENSITIVE = new Set(['personal', 'restricted', 'financial'])

/** L5 is where a withheld chunk already sits, so "keep private" is the honest
 *  name for approving without a scope — not "approve to L5", which reads as a
 *  move. */
const CHOICES: { label: string; hint: string; decision: Decision }[] = [
  {
    label: 'Whole company',
    hint: 'Anyone in the workspace can read it',
    decision: { approve: true, scope: 'l2' as ApprovalScope },
  },
  {
    label: 'Its department',
    hint: 'Only the department the classifier identified',
    decision: { approve: true, scope: 'l3' as ApprovalScope },
  },
  {
    label: 'Keep private',
    hint: 'Stays with whoever uploaded it',
    decision: { approve: true, scope: null },
  },
]

function Meta({ item }: { item: ReviewItem }) {
  const sensitive = SENSITIVE.has(item.sensitivity.toLowerCase())
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-mono text-2xs uppercase tracking-[0.14em] text-ink-400">
        {item.filename}
        {item.source_page !== null ? ` · p${item.source_page}` : ''}
      </span>
      {sensitive && (
        <span className="rounded-md bg-clay-100 px-1.5 py-0.5 font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
          {item.sensitivity}
        </span>
      )}
      <span
        className="rounded-md bg-bone-100 px-1.5 py-0.5 font-mono text-2xs text-ink-500"
        // The number and its author together: 1.00 from a pattern match and
        // 0.40 from a vocabulary count are different kinds of claim.
        title={`Classified by ${item.classified_by}`}
      >
        {item.classified_by} · {item.confidence.toFixed(2)}
      </span>
    </div>
  )
}

export function ReviewQueue() {
  const [queue, setQueue] = useState<{ items: ReviewItem[]; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [refused, setRefused] = useState<Record<string, string>>({})
  // F-05: the item awaiting a confirmed rejection — a one-click "Reject"
  // discarded knowledge with the consequence stated only in a `title`
  // tooltip, which a touch or keyboard user never sees.
  const [confirmReject, setConfirmReject] = useState<ReviewItem | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setQueue(await readReviewQueue())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load the review queue.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // F-02: the endpoint is paged (`limit`, no offset — see `readReviewQueue`'s
  // own doc comment); as items are decided and removed from the visible page
  // locally, `queue.items` can empty while `queue.total` is still positive.
  // The old code rendered `Empty` in that case — "nothing is waiting" while
  // dozens of chunks still were. Fetching again pulls the next batch of
  // whatever remains, since a decided chunk never comes back.
  useEffect(() => {
    if (queue && queue.items.length === 0 && queue.total > 0) {
      void load()
    }
  }, [queue, load])

  async function decide(item: ReviewItem, decision: Decision) {
    setBusy(item.chunk_id)
    setRefused((prev) => {
      const next = { ...prev }
      delete next[item.chunk_id]
      return next
    })
    try {
      await decideChunk(item.chunk_id, decision)
      // Removed locally rather than by refetching: the queue is paged, so a
      // refetch would pull an unrelated item into the gap and move everything
      // under the reader's cursor mid-review.
      setQueue((prev) =>
        prev === null
          ? prev
          : {
              items: prev.items.filter((i) => i.chunk_id !== item.chunk_id),
              total: Math.max(0, prev.total - 1),
            },
      )
    } catch (cause) {
      const message =
        cause instanceof AuthError
          ? cause.message
          : 'That decision did not save. Nothing was changed.'
      setRefused((prev) => ({ ...prev, [item.chunk_id]: message }))
    } finally {
      setBusy(null)
    }
  }

  if (error !== null) {
    return (
      <Failed title="The review queue did not load" retry={() => void load()}>
        {error}
      </Failed>
    )
  }

  if (queue === null) {
    return <Waiting>Loading what is waiting for you.</Waiting>
  }

  if (queue.items.length === 0 && queue.total > 0) {
    // F-02: more remain — the effect above is already re-fetching them.
    // Rendered as a wait rather than nothing, so this reads as "loading
    // more" and not as a flash of the empty state before it corrects itself.
    return <Waiting>Loading what else is waiting.</Waiting>
  }

  if (queue.items.length === 0) {
    return (
      <Empty
        title="Nothing is waiting for a decision"
        action={{ label: 'Upload a document', href: '/onboarding' }}
      >
        Chunks appear here when the classifier will not place them on its own —
        anything it reads as personal or financial, and anything it is not
        confident enough about to file.
      </Empty>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-500">
        {queue.items.length === queue.total
          ? `${queue.total} waiting for a decision.`
          : `${queue.items.length} of ${queue.total} waiting for a decision.`}{' '}
        Each one is withheld from everyone but its uploader until you place it.
      </p>

      <ul className="flex flex-col gap-3">
        {queue.items.map((item) => (
          <li
            key={item.chunk_id}
            className="rounded-2xl border border-bone-300 bg-white/90 p-4 shadow-paper"
          >
            <Meta item={item} />

            <p className="mt-2.5 whitespace-pre-wrap text-sm leading-relaxed text-ink-700">
              {item.excerpt}
            </p>

            <div className="mt-3.5 flex flex-wrap items-center gap-2 border-t border-bone-200 pt-3">
              {CHOICES.map((choice) => (
                <Button
                  key={choice.label}
                  size="sm"
                  variant="secondary"
                  disabled={busy === item.chunk_id}
                  title={choice.hint}
                  onClick={() => void decide(item, choice.decision)}
                >
                  {choice.label}
                </Button>
              ))}
              <Button
                size="sm"
                variant="quiet"
                disabled={busy === item.chunk_id}
                onClick={() => setConfirmReject(item)}
              >
                Reject
              </Button>
              {busy === item.chunk_id && (
                <span className="font-mono text-2xs text-ink-400">Saving…</span>
              )}
            </div>

            {refused[item.chunk_id] && (
              <p
                role="alert"
                className="mt-2.5 rounded-lg bg-clay-100 px-3 py-2 text-sm text-clay-600"
              >
                {refused[item.chunk_id]}
              </p>
            )}
          </li>
        ))}
      </ul>

      {/* F-05: confirm before discarding knowledge — the consequence used to
          live only in a `title` tooltip, invisible to touch and keyboard. */}
      <Dialog
        open={confirmReject !== null}
        onClose={() => setConfirmReject(null)}
        title="Reject this passage?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmReject(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={busy === confirmReject?.chunk_id}
              loadingLabel="Rejecting…"
              onClick={() => {
                const item = confirmReject
                if (!item) return
                setConfirmReject(null)
                void decide(item, { approve: false })
              }}
            >
              Reject
            </Button>
          </>
        }
      >
        Removes it from the workspace&rsquo;s knowledge. The document itself is kept.
      </Dialog>
    </div>
  )
}
