# 0063. A middleware session gate before render, not instead of the API check

- **Status:** Accepted
- **Date:** 22 September 2026
- **Deciders:** Parul (from the E2E defect register, F-23)
- **Implements:** E2E defect register F-23; adjacent to F-03 (client-side 401 handling)
- **Affects:** `apps/web/middleware.ts` (new), the per-page client-side 401
  redirects in `apps/web/components/**` and `apps/web/app/**`

## Context

Today no route in `apps/web` is protected before it renders. Every authenticated
page renders in full — chrome, skeletons, the first data fetch — and only then
redirects, from a client-side `catch` on a 401 returned by the BFF. `SettingsPanel`
records the cost in its own comment: a signed-out visit fires eight requests to
discard six. The guard is re-implemented in every page.

The data is not exposed by this: the FastAPI layer enforces authorization on every
call, and multi-tenancy rests on Postgres `FORCE ROW LEVEL SECURITY` (ADR 0008 and
the isolation suite). A signed-out request reaches no rows. What leaks is *chrome
and latency* — the application shell flashes for someone who is not logged in, and
each page pays for a round trip whose only outcome is a redirect.

F-23 asks for one `middleware.ts` that checks the session cookie and redirects
before render. Introducing an enforcement point in the Next.js edge/runtime layer
is an architectural boundary decision, so it is recorded here even though the
register prescribed the fix.

## Options considered

### A. One `middleware.ts` session-cookie gate, API check unchanged

Next middleware inspects the session cookie on authenticated route patterns and
redirects to the login route before the page renders. It is a *presence* check on
the cookie, not a validation of the session — the API remains the authority.

### B. Validate the session in middleware against the API

Middleware calls the API to confirm the session is live before allowing render.
Correct to the letter, but it puts an API round trip on the critical path of every
navigation and makes the edge layer depend on the API being reachable to render
anything — trading the flash for a hard coupling and latency on the happy path.

### C. Leave it: keep the per-page client-side 401 redirect

Costs nothing to build and the data is already safe. It also keeps the flash, the
wasted requests, and the guard duplicated in every page — the exact state the
register flagged.

## Decision

Option A. A single `apps/web/middleware.ts` checks for the presence of the session
cookie on authenticated route patterns and redirects unauthenticated visitors to
the login route before the page renders. **The middleware is a fast pre-render
filter, not the authority.** The API's authorization and RLS remain the only thing
that decides what data anyone can read; the per-page 401 handling stays as the
backstop for an expired or revoked session that still carries a cookie.

## Reasoning

**The middleware removes a UX and cost defect, not a security hole — so it must not
be built as though the security depended on it.** The decisive point against B is
that the app already has a correct authority; a second one that phones home on
every navigation adds latency and a failure mode (edge cannot render if the API
blips) to solve a flash. A cookie-presence check is cheap, runs before render, and
is honest about what it is: it stops the shell appearing for the signed-out, and
nothing more.

**Against C**, the duplication is the real cost. A guard re-implemented per page is
a guard that will be forgotten on the next page; centralizing the pre-render
redirect is what makes "authenticated pages redirect when signed out" a property of
the app rather than a habit.

**Defense in depth, stated plainly.** Two checks now guard an authenticated page:
the cookie gate (fast, pre-render, presence only) and the API/RLS check
(authoritative, per-row). They are not redundant — they answer different questions
("should this shell render?" vs "may this identity read this row?") and neither
weakens if the other is wrong.

## Consequences

- Signed-out visits to authenticated routes redirect before render; no shell flash,
  no burst of requests that only 401.
- The redirect logic has one home. New authenticated pages inherit it from their
  route pattern rather than each re-adding a client-side `catch`.
- The middleware trusts the *presence* of the cookie, so an expired or revoked
  session whose cookie is still in the browser passes the gate and is caught one
  layer later by the API 401 → client redirect. That backstop must stay.
- The set of "authenticated route patterns" is now a thing that must be kept
  correct. A new authenticated route not covered by the matcher falls back to the
  old behaviour (renders, then client-redirects) — degraded, not unsafe.
- The edge layer now reads the session cookie name. That name becomes a small
  shared contract between the BFF that sets it and the middleware that reads it.

## Revisit trigger

If a future requirement needs the gate to distinguish a *valid* session from a
merely *present* cookie before render — e.g. showing different chrome to a signed-in
vs signed-out user at the edge, or a route where a stale-cookie flash is itself
unacceptable — then the presence check is no longer enough and option B (validated
session, with the API round trip and its failure handling designed for
deliberately) becomes the right shape. Until then, adding a validation call to this
middleware is a latency regression solving a problem the API backstop already
solves.
