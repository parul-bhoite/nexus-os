# ADR 0075 — Login lands on the dashboard, and the dashboard resumes unfinished onboarding

- Status: Accepted
- Date: 2026-10-07
- Related: ADR 0063 (the middleware session gate), ADR 0069/0073 (the onboarding
  flow), migration 0024 (`onboarding_agent`, which persists every step's state).

## Context

Onboarding already persists everything a resume needs: the company and
workspace (`POST /companies`), the chosen departments
(`PUT /companies/current/departments`), and the whole interview — phase, turns,
answers, brief, persona — on the `onboarding_agent` session row. `OnboardingEntry`
already reads that back on mount and renders the exact step a founder left off at
(no company → Company; no departments → Areas; otherwise the engine's phase →
Questions/Documents/Tools/Company Brain), and forwards a **completed** session to
`/dashboard`.

What was missing was the entry point. Login redirected to `/account`, and the
dashboard had no notion of onboarding completeness — so a founder who closed the
tab mid-setup and signed back in did **not** land on their last step. Worse, a
signed-in founder with no workspace yet who reached `/dashboard` got the
surface's 403 routed to `/login` (which they had just passed) rather than to
setup.

## Decision

**Login lands on the dashboard, and the dashboard is the onboarding gate.**

- `LoginForm` defaults its post-login redirect to `/dashboard` (a `next` deep
  link is still honoured first).
- `DashboardLanding` calls `readState()` before it renders. A **completed**
  session proceeds to fetch the surface as before. Anything short of completed
  forwards to `/onboarding/agent`, which resumes at the last incomplete step. A
  `403` ("no workspace selected" — setup never begun) forwards there too; only a
  `401` still goes to `/login`.

`OnboardingEntry` makes the mirror call — a completed session there forwards to
`/dashboard` — so the two gates cannot loop: both read the same
`onboarding_agent.completed`, and only one of them ever redirects for a given
state.

## Reasoning

- **The resume logic already existed; only the front door was missing.** Reusing
  `OnboardingEntry` as the resolver (rather than duplicating "which step" in the
  dashboard) keeps one source of truth for where an unfinished founder belongs.
- **The dashboard is the right gate, not login.** A `next` deep link, a bookmark,
  or a stale session can all land a signed-in person on `/dashboard` without
  passing the login default — gating there catches every path into the
  authenticated surface, where gating only the login redirect would not.
- **`onboarding_agent.completed` is the single completeness signal.** It is what
  the engine sets when the Brain finishes assembling and what `OnboardingEntry`
  already trusts; using the same flag on both sides is what makes them
  consistent by construction.
- **403 is setup-not-started, not access-denied for a human.** A signed-in person
  cannot fix a "no workspace" 403 by signing in again; sending them to onboarding
  is the only move that makes progress.

## Consequences

- Every `/dashboard` load now makes one extra, fast `readState()` call before the
  (much slower) surface fetch. The cost is negligible against the surface's
  round trip and buys a correct gate.
- Deep links to other protected surfaces (`/work`, `/settings`, a director page)
  are **not** gated for onboarding completeness — only the common dashboard
  landing is. Those are edge entries for a mid-onboarding founder; if they prove
  common, the gate generalises to a shared guard.
- The gate is a routing hint, not an authorisation boundary (ADR 0063 still
  holds): the API refuses what a half-set-up workspace may not see regardless of
  where the client routes.

## Revisit trigger

Revisit if mid-onboarding founders routinely reach protected surfaces other than
the dashboard (so the gate needs to move into shared middleware or a layout), or
if the extra `readState()` on every dashboard load shows up as latency worth
folding into the surface response itself.
