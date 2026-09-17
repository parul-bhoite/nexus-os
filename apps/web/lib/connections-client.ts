import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * Connecting the tools a workspace is read from — `doc/14` S9.
 *
 * **No permission rule is duplicated here.** Whether this caller may connect is
 * `routes/connections._may_connect`'s decision — Owner or Executive, because
 * connecting grants a read of the whole company's data — and it arrives as a 403
 * carrying a sentence written for a person. A client that hid the button on a
 * guess would be a second copy of the rule, free to disagree with the first.
 */

export type Offerable = {
  provider: string
  /** What the vendor calls itself. "HubSpot", never `provider.title()`. */
  name: string
  connected: boolean
  /**
   * Whether this deployment has the credentials to start an authorisation.
   *
   * **Not the same as `!connected`.** A deployment with no client id cannot
   * offer a Connect button at all, and a screen that offered one anyway would
   * send somebody to a vendor error page carrying our client id.
   */
  configured: boolean
}

export type Connections = {
  providers: string[]
  offerable: Offerable[]
}

async function send<T>(path: string, init: RequestInit, fallback: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
  })

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, fallback), response.status)
  }
  return payload as T
}

export function fetchConnections(): Promise<Connections> {
  return send<Connections>('/connections', { method: 'GET' }, 'Could not read your connections.')
}

/** Returns where to send the browser. The API hands back a URL rather than
 *  redirecting, so the person follows it — not this `fetch`. */
export function startAuthorization(provider: string): Promise<{ url: string }> {
  return send<{ url: string }>(
    `/connections/${encodeURIComponent(provider)}/authorize`,
    { method: 'POST' },
    'Could not start that connection.',
  )
}

export function revokeConnection(
  provider: string,
): Promise<{ provider: string; state: string; message: string }> {
  return send(
    `/connections/${encodeURIComponent(provider)}/revoke`,
    { method: 'POST' },
    'Could not disconnect that.',
  )
}
