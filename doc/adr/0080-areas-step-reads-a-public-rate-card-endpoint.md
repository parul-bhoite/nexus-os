# ADR 0080 — The Areas step reads prices and included tools from a public rate-card endpoint

- Status: Accepted
- Date: 2026-10-08
- Related: [0076](0076-onboarding-ends-in-a-payment-step-with-db-pricing-and-entitlement.md)
  (the `price` table and the Payment-step quote this reuses);
  [0073](0073-onboarding-is-a-six-step-wizard-not-a-live-brain-conversation.md)
  (the stepped flow the Areas step belongs to).

## Context

ADR 0076 put prices in a global `price` table and surfaced them only at the end of
onboarding, on the Payment step, via `GET /billing/quote` — a per-workspace bill
computed from what the founder has already selected and declared. The product owner
asked for the price of each area, and the tools each area includes, to be shown
**on the Areas cards at step 2** — before anything is selected — so the cost of a
choice is visible while it is being made.

`/billing/quote` cannot answer this: it is the bill, not the menu. It needs a
selection to price, and it only returns the lines for areas already chosen. Showing
the whole catalogue priced-but-unselected is a different read.

## Decision

Add a read-only endpoint `GET /billing/rate-card` and a Next.js BFF proxy at
`/api/billing/rate-card`. It returns, for every **selectable** department
(`executive` excluded — it is automatic and never billed):

```
{ currency, departments: [ { key, label, amount_minor | null, tools: [ { key, label } ] } ] }
```

- Amounts are read from the `price` table (ADR 0076) — never computed or invented
  (invariant I1); a department with no active price returns `amount_minor: null` so
  the card can say so rather than imply free (I10).
- `tools` is the connections catalogue's own department grouping — the same set
  `quote_for` bills at zero as "included" when that department is selected.
- Auth is the existing `CurrentScope`: any authenticated workspace member, exactly
  like `/billing/quote`. No new auth surface — the `price` table is already
  world-readable to any authenticated tenant (migration 0042's `USING (true)`),
  so this exposes nothing a member could not already read.

The frontend loads it in parallel with the department list and tolerates its
failure: a billing hiccup drops the price/tool detail from the cards but never
blocks area selection.

## Reasoning

- **A separate endpoint, not an overload of `/billing/quote`.** The quote is
  selection-dependent and returns a total; the rate card is the full catalogue with
  no total and no dependence on state. Conflating them would make one endpoint answer
  two questions and force a "price everything as if selected" mode into the bill.
- **Server-side, not a client price table.** The amounts must stay grounded in the
  DB (I1); a second copy of the rate card in the browser would be a figure nobody
  could reproduce and would drift from admin edits (ADR 0077).
- **No new auth decision.** It reuses the member-level scope and the already-decided
  world-readability of `price`; this ADR records the endpoint shape, not a new trust
  boundary.

## Consequences

- The Areas cards show each area's monthly price and included tools, read live from
  the rate card — an admin price edit (ADR 0077) is reflected on the next load.
- One more public billing read to keep in step with the `price` schema and the tool
  catalogue; its response shape is now a contract the Areas step depends on.
- The left illustration column is dropped for the Areas step so the priced cards use
  the full width (a `wide` option on the stepper shell) — layout only, under ADR 0074.

## Revisit trigger

Revisit when: prices become per-workspace or per-region (the rate card stops being a
single global menu and the world-readable `price` assumption changes); tool inclusion
stops being a static per-department catalogue grouping (e.g. plan tiers, add-on
bundles); or the quote and rate card converge enough that one endpoint should serve
both.
