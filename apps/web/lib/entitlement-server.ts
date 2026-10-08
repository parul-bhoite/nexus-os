import { cookies } from 'next/headers'

/**
 * Server-side entitlement read for the dashboard page gate (ADR 0084).
 *
 * The defense-in-depth half: the dashboard layout calls this and redirects an
 * unentitled founder to finish payment *before the shell renders*, rather than
 * letting it paint and then bounce them when the client's first `/api/dashboards`
 * call comes back 402. The API's 402 remains the authority; this is the
 * redirect-before-render convenience on top of it.
 *
 * Forwards the httponly session cookie to the API's `/billing/status` (which is
 * **not** itself gated, so there is no circular refusal). It **fails open**: on
 * any error — the billing service unreachable, a timeout, a non-JSON answer — it
 * returns `true`, because the API gate is the real boundary and a billing blip
 * must never lock a paying customer out of a page the API would serve. Only a
 * clear `entitled: false` from a healthy response gates.
 */
const API_BASE = process.env.NEXUS_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function serverEntitled(): Promise<boolean> {
  try {
    const cookieHeader = cookies().toString()
    if (!cookieHeader) return true // no session to resolve; let the client/API handle it
    const response = await fetch(`${API_BASE}/billing/status`, {
      headers: { cookie: cookieHeader },
      cache: 'no-store',
    })
    if (!response.ok) return true // fail open — the API's 402 is the backstop
    const body = (await response.json()) as { entitled?: boolean }
    return body.entitled !== false
  } catch {
    return true
  }
}
