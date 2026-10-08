# 0084. A server-side entitlement gate on the dashboard (API 402 + page redirect)

- **Status:** Proposed
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

Onboarding ends in a payment step, and `entitlement_for` already decides whether a
workspace has an active plan or trial (ADR 0076). But that decision was enforced
in exactly one place — the browser, in `OnboardingEntry.tsx`, which redirects an
unentitled founder to pay. Nothing stopped a direct navigation to `/dashboard`,
and nothing stopped a direct call to `/dashboards/*`: `apps/web/middleware.ts`
checks only that a session cookie is *present* (by its own deliberate design, it
cannot resolve a session, let alone an entitlement, without the database), and
the API's dashboard routes had no entitlement check at all.

This is a **billing** gap, not a data-exposure one: row-level security already
makes a workspace's data invisible to every other tenant whether or not anyone
has paid. What was missing was a gate on *use* of the product.

## Options considered

### A. API dependency only
A 402 from `/dashboards/*`. True boundary enforcement, but the dashboard would
paint and then bounce the user when its first fetch returns 402.

### B. Next.js page gate only
Redirect before render in the dashboard layout. Good UX, but a direct API call
from an unentitled session would still be served (the data is RLS-safe, but the
*use* gate would be bypassable).

### C. Both — API 402 + page redirect (chosen)
Defense-in-depth: the API is the authority (402), and the page redirects before
render so the founder never sees a flash of a dashboard they cannot use.

## Decision

Option C.

**API (the authority).** `app/deps_entitlement.py::require_entitled` is a
dependency on the `/dashboards` router. It reads `entitlement_for` in its own short
scoped transaction and raises **402 Payment Required** when the workspace is not
entitled. A 402, not a 403: nothing about the caller's *authority* is wrong — they
may own the workspace; what is missing is a plan. Applied at the router so a new
dashboard route cannot be added outside the paywall by forgetting a per-route
dependency.

**Web (redirect before render).** `apps/web/lib/entitlement-server.ts::serverEntitled`
reads entitlement server-side (forwarding the httponly cookie to `/billing/status`,
which is itself ungated, so there is no circular refusal) and the dashboard layout
redirects an unentitled workspace to `/onboarding/agent` (which resumes at
payment). It **fails open**: on any error it returns `true`, because the API's 402
is the real boundary and a billing-service blip must not lock a paying customer out
of a page the API would serve. The client shell also reacts to a 402 from its data
fetch by redirecting to payment — the belt to the layout's braces.

**Tests.** The gate is proven through the real app against real Postgres
(`test_entitlement_gate.py`): no subscription → 402, a paid row → 200. Every other
dashboard HTTP test overrides `require_entitled` to a no-op, because they are not
testing the paywall — the one explicit place that is, does not.

## Reasoning

C was chosen because the two halves answer two different failure modes: the API
402 is what makes the gate *real* (a direct call cannot drive through it), and the
page redirect is what makes it *pleasant* (no flash of an unusable dashboard). The
cost is the one the user accepted: a ripple across the dashboard HTTP tests (each
now says, in one line, "this is not the paywall's test") and one extra server→API
round trip per dashboard navigation, bounded by a fail-open so it can never be the
thing that breaks a paying session. The entitlement check deliberately did **not**
move onto `ScopedSession`: that would have made every authenticated request —
login, settings, onboarding — pay an entitlement read, and coupled a billing fact
to the authority object, to save a handful of one-line test overrides.

## Consequences

- `/dashboards/*` refuses an unentitled workspace with 402; the web redirects such
  a founder to finish payment before the shell renders, and again if a later fetch
  returns 402.
- Dashboard HTTP tests carry a one-line `require_entitled` override; the hermetic
  ones (no database) especially need it, since the gate reads one.
- The `/billing/*` routes stay ungated (a user mid-payment must reach them), so the
  gate cannot refuse the very endpoint that would lift it.
- RLS remains the data boundary; this changes nothing about what a connected,
  entitled or unentitled workspace can *see* of other tenants — only whether it may
  open its own dashboard.

## Revisit trigger

Reopen if: a second product surface outside `/dashboards` needs the same gate (lift
`require_entitled` to a shared place); entitlement needs to be known on every
request for another reason (reconsider the `ScopedSession` option); or the
per-navigation server→API entitlement read shows up as a latency cost (cache it, or
fold it into the page's existing data fetch).
