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

export type RateCardTool = { key: string; label: string }

export type RateCardDepartment = {
  key: string
  label: string
  /** Monthly price in minor units, or null when no active price exists. */
  amount_minor: number | null
  /** Tools that come included with this area. */
  tools: RateCardTool[]
}

export type RateCard = {
  currency: string
  departments: RateCardDepartment[]
}

/** The price list for the Areas step — what each area costs and includes. */
export function fetchRateCard(): Promise<RateCard> {
  return call<RateCard>('/api/billing/rate-card')
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

/* ── Admin (platform-admin only; the API 403s otherwise) ──────── */

export type AdminPrice = {
  kind: 'department' | 'tool'
  key: string
  amount_minor: number
  currency: string
  active: boolean
  updated_at: string
  updated_by: string | null
}

export function fetchPrices(): Promise<AdminPrice[]> {
  return call<AdminPrice[]>('/api/admin/prices')
}

export function updatePrice(
  kind: string,
  key: string,
  body: { amount_minor: number; active: boolean },
): Promise<AdminPrice> {
  return call<AdminPrice>(
    `/api/admin/prices/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`,
    { method: 'PUT', body: JSON.stringify(body) },
  )
}

/**
 * Parse a major-unit amount a person typed (e.g. "25.5") into minor units for
 * `currency`, inverting `formatMinor` — so an admin edits "25.000" OMR, not
 * 25000 baisa. Returns null when the text is not a non-negative number.
 */
export function parseMajorToMinor(text: string, currency: string): number | null {
  const major = Number(text.trim())
  if (!Number.isFinite(major) || major < 0) return null
  const decimals = new Intl.NumberFormat(undefined, { style: 'currency', currency })
    .resolvedOptions()
    .maximumFractionDigits ?? 2
  return Math.round(major * 10 ** decimals)
}

/** Major-unit value (as a plain number) for prefilling an edit field. */
export function minorToMajor(amountMinor: number, currency: string): number {
  const decimals = new Intl.NumberFormat(undefined, { style: 'currency', currency })
    .resolvedOptions()
    .maximumFractionDigits ?? 2
  return amountMinor / 10 ** decimals
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
