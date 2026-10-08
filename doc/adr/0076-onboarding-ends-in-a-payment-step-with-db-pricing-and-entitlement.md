# ADR 0076 — Onboarding ends in a Payment step, priced from a DB price table, gated on entitlement

- Status: Accepted
- Date: 2026-10-07
- Supersedes: **A3** (`DECISIONS-REQUIRED.md` — "trial is a flag at workspace
  creation; no paywall; billing beyond a trial flag is out of scope") and the
  `doc/10-FLOW-QUESTIONS.md` Q2 answer ("no plan/pricing selection; pricing page
  informational only").
- Extends: [0073](0073-onboarding-is-a-six-step-wizard-not-a-live-brain-conversation.md)
  (the wizard — now **seven** steps), [0074](0074-onboarding-shell-is-a-frozen-header-over-a-two-column-step.md)
  (the shell), [0075](0075-login-lands-on-the-dashboard-which-gates-unfinished-onboarding.md)
  (the completion gate).
- Related: [0077](0077-interim-platform-admin-via-config-allowlist.md) (who may edit
  prices).

## Context

The product owner wants onboarding to end in a **Payment** step: a costed summary
driven by the areas of interest (departments) and tools the founder selected, then a
(dummy) gateway that opens the dashboard. Exploration found billing is entirely
greenfield — no price fields on tools (`connections.py`, 9 tools) or departments
(`departments.py`, 6 selectable), no billing tables, no provider config; only
illustrative marketing tiers. `workspace.reporting_currency` exists (default `OMR`).

A paywall reverses A3, so this ADR records the reversal. It also has to resolve a
tension from ADR 0075: `onboarding_session.completed` is set when the Brain assembles
(step 6), *before* payment, and both routing gates key off it — so a new signal is
needed or an unpaid founder is waved straight through.

## Decision

**Onboarding gains a seventh step, "Payment", after "Company Brain".** The founder
sees a costed summary and either **pays** (a dummy gateway that always succeeds) or
**starts a 7-day free trial**; either grants entry and the orchestrator opens the
dashboard.

**Pricing is per-item, stored in the database, admin-editable:**
- A global `price(kind, key, amount_minor, currency, active, …)` reference table,
  `kind ∈ {department, tool}`, seeded by us with illustrative OMR prices (admin can
  change them later — ADR 0077). It is reference data, not tenant data: RLS is
  enabled and forced with a `USING (true)` policy (world-readable within the app
  role); admin-only writes are enforced at the application layer.
- The **quote** is computed server-side (`domain/pricing.py`): each selected
  department (minus the automatic `executive`) is billed at its price; a tool is
  **included** (free) when its department is selected, and **additional** (billed at
  its own price) when it is not. Amounts come only from the `price` table — computed,
  never invented (invariant I1); a missing/inactive price is surfaced as
  *unavailable*, never silently charged 0 (I10).
- Currency and period: **monthly, in the workspace's `reporting_currency`** (OMR).

**Entitlement is the new completion signal.** A tenant-scoped
`onboarding_subscription(status ∈ {paid, trial}, trial_expires_at, line_items, …)`
row records the outcome, with the quote snapshotted so the record is auditable
independent of later price edits. A workspace is **entitled** when a `paid` row
exists, or a `trial` row whose `trial_expires_at` is in the future. This supersedes
the 45-day `workspace.trial_ends_at` flag for *gating* (that column stays as legacy
data).

**The gates now require entitlement, not just `completed`** (extending ADR 0075):
the dashboard forwards a `completed` but un-entitled founder to `/onboarding/agent`,
which resumes at the Payment step; `OnboardingEntry` opens the dashboard only when
`completed && entitled`. The two still read the same facts and cannot loop.

## Reasoning

- **Per-item prices in the DB, not in code or on the tool/department records.** The
  owner asked for admin-editable prices; a table edited at runtime is the only shape
  that supports that, and keeping price off the `Tool`/`Department` catalogues keeps
  those pure (a tool knows its department, not its price).
- **Quote computed server-side from the table** keeps the product's "never invent a
  number / always show the source" promise true of its *own* pricing, not only the
  customer's figures: the browser never sends or derives a price.
- **Entitlement, not `completed`, gates the dashboard** because payment happens after
  the Brain is assembled, so `completed` can no longer mean "may enter". Snapshotting
  the charged line items keeps the record meaningful after an admin edits prices.
- **A 7-day trial skip** keeps a low-friction path (the spirit of the retired
  trial-flag) while still making payment the default, explicit act.

## Consequences

- A paywall now stands between onboarding and the dashboard — a deliberate reversal
  of A3. The marketing pricing page stays informational and is not wired to this.
- New surfaces: `price` + `onboarding_subscription` tables, `domain/pricing.py`,
  `routes/billing.py` (`/billing/quote|pay|trial|status`), their BFF proxies under
  `apps/web/app/api/billing/*`, `lib/billing-client.ts`, the `PaymentStep`
  component + its stepper/art entries, and the gate updates in `OnboardingEntry` and
  `DashboardLanding`.
- The dummy gateway charges nothing; wiring a real provider (Stripe etc.) and real
  recurring billing remain out of scope and would get their own ADR.
- Global-reference-table RLS (`USING (true)`) is a deliberate departure from the
  tenant-row RLS every other table uses; verified forced in `pg_class` and explained
  in the migration.

## Revisit trigger

Revisit if: a real payment provider is introduced (recurring billing, webhooks,
refunds change the entitlement model); the 7-day trial proves too short/long or
needs its own expiry UX on the dashboard; prices need to vary per workspace or per
region (the global `price` table would need a scoping dimension); or the snapshot
model for `line_items` conflicts with how an admin price change should affect
existing subscribers.
