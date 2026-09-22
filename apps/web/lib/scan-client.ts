import { HttpError, httpJson } from '@/lib/http'

/**
 * The anonymous Instant Gap Analysis scan. ADR 0046, `doc/18` G9.
 *
 * Routed through the shared `httpJson` (#3) rather than a private copy of the
 * same `fetch`-plus-`messageFrom` shape — see `lib/http.ts` for what that
 * closes here: a timeout ceiling neither call had, and a checked response
 * body where `deleteScan` had none at all (F-10).
 */

export type CheckOut = {
  id: string
  label: string
  evidence: string
  weight: number
}

export type CategoryScoreOut = {
  category: string
  score: number
  max_score: number
  percentage: number
}

export type ScanResult = {
  id: string
  domain: string
  scanned_url: string
  checks: CheckOut[]
  scores: CategoryScoreOut[]
  pages_read: number
  js_rendered: boolean
  created_at: string
  expires_at: string
}

export class ScanError extends Error {
  readonly status: number
  /** Seconds until a limited caller may try again — only set for a 429. */
  readonly retryAfterSeconds: number | null

  constructor(message: string, status: number, retryAfterSeconds: number | null = null) {
    super(message)
    this.status = status
    this.retryAfterSeconds = retryAfterSeconds
  }
}

/**
 * `Retry-After`, in seconds — HTTP allows either a delta-seconds integer or
 * an HTTP-date, and this header can arrive as either.
 *
 * F-26: `Number(retryAfter)` on an HTTP-date (`Wed, 21 Oct 2026 07:28:00 GMT`)
 * is `NaN`, which produced "try again in about NaN minutes". Delta-seconds is
 * tried first because it is what this API actually sends; `Date.parse` is the
 * fallback for the header's other legal shape; and if neither yields a real
 * number, `null` is returned so the caller can drop the sentence rather than
 * print a non-answer.
 */
function retryAfterSeconds(header: string | null): number | null {
  if (!header) return null

  const asDelta = Number(header)
  if (Number.isFinite(asDelta) && asDelta >= 0) return asDelta

  const asDate = Date.parse(header)
  if (!Number.isNaN(asDate)) {
    const seconds = Math.round((asDate - Date.now()) / 1000)
    return seconds >= 0 ? seconds : 0
  }

  return null
}

export async function startScan(url: string): Promise<ScanResult> {
  let retryAfter: string | null = null
  try {
    return await httpJson<ScanResult>('/api/public/scans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
      cache: 'no-store',
      fallbackMessage: 'Something went wrong.',
      // Read before the body — the only way to see `Retry-After` on the 429
      // this call may get back, since it is gone once `httpJson` has thrown.
      onResponse: (response) => {
        retryAfter = response.headers.get('retry-after')
      },
    })
  } catch (error) {
    if (error instanceof HttpError) {
      throw new ScanError(error.message, error.status, retryAfterSeconds(retryAfter))
    }
    throw error
  }
}

export async function deleteScan(id: string): Promise<void> {
  // F-10: this used to be a bare `await fetch(...)` with nothing checking
  // `response.ok` — a failed delete and a successful one looked identical to
  // the caller, which unconditionally showed "deleted" either way.
  await httpJson<void>(`/api/public/scans/${id}`, {
    method: 'DELETE',
    cache: 'no-store',
    allowEmptyBody: true,
    fallbackMessage: 'Could not delete that result.',
  })
}
