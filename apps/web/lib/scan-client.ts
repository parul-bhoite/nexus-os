/**
 * The anonymous Instant Gap Analysis scan. ADR 0046, `doc/18` G9.
 *
 * Mirrors `auth-client.ts`'s `post`/`AuthError` shape — same origin, no
 * credentials to attach (there is no session), `no-store`.
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

function messageFrom(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && typeof (payload as { detail?: unknown }).detail === 'string') {
    return (payload as { detail: string }).detail
  }
  return fallback
}

export async function startScan(url: string): Promise<ScanResult> {
  const response = await fetch('/api/public/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    cache: 'no-store',
  })

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const retryAfter = response.headers.get('retry-after')
    throw new ScanError(
      messageFrom(payload, 'Something went wrong.'),
      response.status,
      retryAfter ? Number(retryAfter) : null,
    )
  }
  return payload as ScanResult
}

export async function deleteScan(id: string): Promise<void> {
  await fetch(`/api/public/scans/${id}`, { method: 'DELETE', cache: 'no-store' })
}
