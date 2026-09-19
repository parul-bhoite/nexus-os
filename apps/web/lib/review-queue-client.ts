import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * The review queue, browser side.
 *
 * Chunks the classifier withheld because it could not place them safely. Until
 * this existed, `rules.propose` (ADR 0051) auto-approved the confident majority
 * and everything else sat in a table no screen read — withheld is not the same
 * as reviewed, and a queue nobody can open is storage, not a control.
 *
 * **Nothing here decides who may see what.** The scope a reviewer asks for is
 * checked against their real authority by the API's `may_reach_scope`; this
 * file sends the request and reports what came back, including the refusal.
 */

export type ReviewItem = {
  chunk_id: string
  document_id: string
  filename: string
  source_page: number | null
  source_label: string | null
  /** Truncated by the API on purpose: enough to judge the classification, not
   *  the whole document — and this is content nobody has yet cleared. */
  excerpt: string
  scope: string
  sensitivity: string
  confidence: number
  /** `rules-v1`, or `rules-v1:classifier-failed` and friends. Which decision
   *  this was lets a reviewer weigh it, and lets one version's decisions be
   *  found again later. */
  classified_by: string
}

export type ReviewQueue = {
  items: ReviewItem[]
  /** May exceed `items.length` — the endpoint is paged. */
  total: number
}

/** Where an approved chunk may be placed. `l4` and `l5` are absent by design:
 *  L4 is reachable only by being named on the item, and L5 is where a chunk
 *  already sits while it waits, so "approve to L5" is the *keep it private*
 *  case and is spelled that way in the UI rather than as a scope. */
export type ApprovalScope = 'l2' | 'l3'

export type Decision =
  | { approve: false }
  | { approve: true; scope: ApprovalScope | null }

export async function readReviewQueue(): Promise<ReviewQueue> {
  const response = await fetch('/api/documents/review-queue', {
    credentials: 'same-origin',
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(
      messageFrom(payload, 'Could not load the review queue.'),
      response.status,
    )
  }
  return payload as ReviewQueue
}

export async function decideChunk(chunkId: string, decision: Decision): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const body = decision.approve
    ? { approve: true, scope: decision.scope }
    : { approve: false }

  const response = await fetch(`/api/documents/review-queue/${chunkId}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (response.status === 204) return

  const payload = await response.json().catch(() => null)
  // The 403 here is a real answer, not a bug: it means this reviewer cannot
  // grant the scope they chose. Surfaced verbatim so the screen says which
  // scope was refused rather than "something went wrong".
  throw new AuthError(messageFrom(payload, 'That decision did not save.'), response.status)
}
