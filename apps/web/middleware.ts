import { NextResponse, type NextRequest } from 'next/server'

/**
 * F-23: redirect signed-out visitors before the page renders, for the
 * screens that need a session at all.
 *
 * **A hint, not the authorisation boundary.** Real access control still
 * lives entirely server-side, in the API's own session and permission
 * checks behind `proxyToApi` — this middleware only decides what to render
 * *first*. Before this file existed, every one of these routes rendered its
 * full client component tree, fired its data fetch, got a 401, and only then
 * redirected to `/login` — a flash of the authenticated shell, a wasted round
 * trip, and (per `lib/hooks.ts`'s note on `useLooksSignedIn`) a page that had
 * to be built defensively against rendering the wrong thing on the server.
 * `PROTECTED_PREFIXES` closes that gap for the common case: no cookie at all.
 *
 * **Checked by presence, not validity.** The session cookie is `httponly`,
 * so this can read it but not verify it — a forged or expired cookie still
 * passes this check and still gets the real 401 from the API. That is by
 * design: the API is the only place that can actually resolve a session
 * (`resolve_session` needs the database), and duplicating that resolution
 * here would be a second, easier-to-get-wrong copy of the permission check
 * `retrieval/` already owns for exactly the reason ADR-worthy invariants I2/I3
 * exist.
 *
 * **The cookie name is the API's own** — `session_cookie_name` in
 * `services/api/app/config.py`, currently `"nexus_session"`. Read from one
 * place rather than restated, because a rename on one side with this file
 * unchanged would silently stop protecting everything.
 */
const SESSION_COOKIE = 'nexus_session'

/**
 * Routes that need a session to be worth rendering at all.
 *
 * Deliberately not everything under `app/`: `/scan` is the anonymous Instant
 * Gap Analysis tool and must work signed out; `/invitations/accept` is
 * usable signed out (it renders a "sign in to accept" branch — see
 * `useLooksSignedIn`'s own note about why that page cannot assume a
 * session); `/register`, `/register-company`, `/login`, `/forgot-password`,
 * `/reset-password` and `/verify-email` are the auth flow itself and would
 * be an unreachable loop if gated on already having a session.
 */
const PROTECTED_PREFIXES = [
  '/account',
  '/connections',
  '/dashboard',
  '/documents',
  '/onboarding',
  '/review-queue',
  '/settings',
  '/work',
]

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
  if (!isProtected) return NextResponse.next()

  if (request.cookies.get(SESSION_COOKIE)) return NextResponse.next()

  const signIn = new URL('/login', request.url)
  signIn.searchParams.set('next', pathname + search)
  return NextResponse.redirect(signIn)
}

export const config = {
  matcher: [
    '/account/:path*',
    '/connections/:path*',
    '/dashboard/:path*',
    '/documents/:path*',
    '/onboarding/:path*',
    '/review-queue/:path*',
    '/settings/:path*',
    '/work/:path*',
  ],
}
