import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * Browser-side calls for the onboarding Payment step (ADR 0076).
 *
 * Like every other client here these go to this app's own `/api/billing/*`
 * routes, never to the API directly — the session cookie is `httponly` and
 * first-party only. **Nothing here sends a price:** the amount is read
 * server-side from the `price` table and snapshotted on pay/trial, so a client
 * cannot choose what it is charged.
 */

export type QuoteLine = {
  kind: 'department' | 'tool'
  key: string
  label: string
  amount_minor: number
  /** A tool that comes free with a selected department. */
  included?: boolean
  /** No active price exists for this item — shown, never silently charged 0. */
  unavailable?: boolean
}

export type Quote = {
  currency: string
  period: 'monthly'
  line_items: QuoteLine[]
  total_minor: number
}

export type Entitlement = {
  entitled: boolean
  kind: 'paid' | 'trial' | null
  trial_expires_at: string | null
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (init.body !== undefined) headers['Content-Type'] = 'application/json'
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  if (response.ok) return (await response.json()) as T

  const payload = await response.json().catch(() => null)
  throw new AuthError(
    messageFrom(payload, `The request failed (${response.status}).`),
    response.status,
    payload?.detail,
  )
}

export function fetchQuote(): Promise<Quote> {
  return call<Quote>('/api/billing/quote')
}

export function fetchEntitlement(): Promise<Entitlement> {
  return call<Entitlement>('/api/billing/status')
}

export function pay(): Promise<Entitlement> {
  return call<Entitlement>('/api/billing/pay', { method: 'POST' })
}

export function startTrial(): Promise<Entitlement> {
  return call<Entitlement>('/api/billing/trial', { method: 'POST' })
}

/**
 * Format a minor-unit amount in its currency, deriving the right number of
 * decimals from the currency itself (OMR has 3, USD 2) rather than assuming
 * two — so `25000` baisa renders as `OMR 25.000`, not `OMR 250.00`.
 */
export function formatMinor(amountMinor: number, currency: string): string {
  const fmt = new Intl.NumberFormat(undefined, { style: 'currency', currency })
  const decimals = fmt.resolvedOptions().maximumFractionDigits ?? 2
  return fmt.format(amountMinor / 10 ** decimals)
}
