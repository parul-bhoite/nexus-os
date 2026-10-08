# 0085. Measured insights are their own region, surfaced on the dashboard and the Brain

- **Status:** Proposed
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

P1 gave measured connector insights a store (`workspace_insight`, ADR 0081) and
P2 wrote the first one (a PageSpeed score on completion, ADR 0082). They now have
to be *shown* — on the dashboard, and in the Company Brain "insight/info section"
the product promised. Two questions had to be answered: where on each surface, and
how the Brain reaches them given it is reviewed before payment.

## Decision

**Insights are their own region, not retrofitted into the calculator tiles.** The
dashboard's `measured` tiles are live-computed figures from `calculators/` over
crawl/ops/CRM rows. An insight is a *persisted* figure a connector read, and the
source ledger records that PageSpeed (and Search Console) unlock **no capability**
today — there is no tile for an insight to light up. Forcing one in would mean
inventing a capability; instead the dashboard gains an `insights` region beside
`measured`, and the Brain page gains an "Insights" section. Each insight is shown
with its **provenance and capture date**, never bare — the honesty the store
exists for.

**Two read paths, one shape:**

- `GET /dashboards/surface` carries `insights` (read once in the `Observed`
  dependency, like the other reads), for the Today page. It is entitlement-gated
  with the rest of that surface (ADR 0084).
- `GET /insights` is a **separate, ungated** endpoint for the Company Brain page.
  The Brain is reviewed *during onboarding, before payment*, so it cannot read the
  gated surface — the same reason `/brain` itself is ungated. Both endpoints map
  through the one `InsightOut` + `_insight_out`, so the two surfaces cannot render
  one insight two ways (the reason `figure_out` is shared).

Both reads go through `retrieval/insights.current_insights` under a
`ScopedSession` (I2/I3); `/insights` exposes only the caller's own workspace.

## Reasoning

Keeping insights a distinct region is the honest reflection of what they are —
measured, not computed; persisted, not live — and it sidesteps inventing a
capability just to have a tile. The separate ungated `/insights` endpoint exists
for one concrete reason: the Brain is a pre-payment surface, so routing its
insights through the entitlement-gated dashboard surface would have hidden them
exactly when a founder is deciding whether to pay. Sharing the wire model and
mapper across both endpoints is the same anti-drift rule the measured tiles follow.

## Consequences

- A stored insight appears on the Today page and the Brain page, each with
  provenance + date; a workspace with none sees no empty frame (both regions
  render nothing when empty).
- Insights never fail either page: the Brain page catches a failed `/insights`
  read to an empty section, as it already does for the agent state.
- A new ungated endpoint (`/insights`) exists; it is scoped and read-only, and
  carries no capability promise.
- When PageSpeed (or another source) later *does* back a capability, that tile can
  read the same store without changing this region — they are complementary.

## Revisit trigger

Reopen if: an insight should drive a capability tile's state (wire it into the
figure path then, not instead of this region); the two endpoints' shapes need to
diverge (promote `InsightOut` to a shared module); or the Brain stops being a
pre-payment surface, at which point `/insights` could fold into the gated surface.
