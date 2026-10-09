# 0079. Onboarding header exposes Sign out only, not the full account menu

- **Status:** Accepted
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

The onboarding wizard (`StepperShell`, ADR 0073) runs **before a workspace
exists** — registration creates a person, and a workspace is only created
through onboarding itself. Its header carried a static, non-interactive person
glyph: no identity, no action. Two problems followed. A returning founder could
not see which account they were signed in as, and — relevant after the transient
403/500 probe failures seen in this session — there was no way to sign out and
retry as a different account without hand-editing cookies.

The authenticated app shell already has a real control, `AccountMenu`, which
shows the signed-in email with an initials avatar and offers **Your account**,
**Workspace settings**, and **Sign out**. But two of those three destinations do
not exist yet during onboarding: `/settings` is a *workspace* page and there is
no workspace, and `/account` is of marginal use before setup. Offering links that
lead nowhere useful is the thing to avoid.

## Options considered

### A. Reuse `AccountMenu` with a flag that hides the two page links
Identity + Sign out during onboarding; one implementation of session fetch,
sign-out, popover and click-outside. The full menu returns automatically once
the dashboard shell takes over post-onboarding.

### B. Show all links but disable Account/Settings during onboarding
Keeps the menu shape constant, but a disabled row with no explanation is a
worse signal than an absent one, and it invites "why is this greyed out?".

### C. Hide the account control entirely until onboarding completes
Simplest, but it reintroduces the original defect: no identity shown and no way
to sign out mid-onboarding.

### D. Build a separate minimal sign-out component for onboarding
Avoids a prop on `AccountMenu`, at the cost of a second copy of the session
fetch, sign-out and popover logic — two places for one behaviour to drift.

## Decision

Option A. `AccountMenu` gains a `signOutOnly` prop (default `false`, so the app
shell is unchanged). When set, it hides **Your account** and **Workspace
settings** and keeps the "Signed in as <email>" header and **Sign out**. The
onboarding `StepperShell` header renders `<AccountMenu signOutOnly />` in place
of the static glyph. "Until onboarding completes" is satisfied structurally: the
`StepperShell` header is only shown during onboarding; once the founder reaches
`/dashboard`, the app shell's unflagged `AccountMenu` shows the full menu again.

## Reasoning

A beat the alternatives on honesty and single-sourcing. B and C each fail the
original requirement — B shows dead controls, C shows no identity and no escape
hatch. D duplicates security-relevant logic (session read and logout) for no
gain. The prop defaults off, so this is additive: no existing caller changes
behaviour, which is why it is a safe reuse rather than a fork. Hiding the links
is a **presentation** choice only — `/account` and `/settings` still enforce
their own server-side authorization, so nothing here is a security boundary; it
removes affordances that lead nowhere useful yet, not access.

## Consequences

- One component owns identity + sign-out everywhere; onboarding and the app
  shell cannot drift apart.
- A founder can see who they are signed in as and sign out at any onboarding
  step — directly useful when a probe failure leaves them stuck.
- `AccountMenu` now has a mode flag; a future third destination has two call
  sites to consider (shell shows it, onboarding decides whether to).
- The boundary "which links appear" is driven by *which shell renders the menu*,
  not by onboarding state passed into the menu — if onboarding and the dashboard
  shell ever merge, this rule needs re-expressing.

## Revisit trigger

Reopen if onboarding gains a destination that *should* be reachable mid-setup
(e.g. a billing page before the workspace exists), or if the onboarding and
dashboard shells are unified such that one header serves both — at which point
"signOutOnly" would need to become state-driven rather than call-site-driven.
