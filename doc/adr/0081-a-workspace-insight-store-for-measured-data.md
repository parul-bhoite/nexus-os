# 0081. A `workspace_insight` store for measured connector data, separate from the Brain

- **Status:** Proposed
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

The product is gaining the ability to fetch from connectors (PageSpeed on
onboarding completion, HubSpot on connect) and turn what it reads into insights
that must (a) show on the dashboard, (b) appear in a Company-Brain insight
section, and (c) be answerable by the forthcoming assistant.

Two existing stores look like candidates and are both wrong for this:

- **`company_brain`** holds *stated* facts a founder told us, with
  `generated_by ∈ {answers, model, unavailable}` and a provenance array. Its whole
  meaning is "what you said about yourself." A measured number from a third party
  is a different kind of thing, and widening `generated_by` to admit it blurs the
  one distinction the Brain exists to keep: stated vs. observed.
- **The dashboard compute path** (`calculators/` + `grounding/compute.py`)
  deliberately **computes figures live and never persists them** (I1). That is
  right for a figure derived from rows already in our database (`crm_deal`,
  `ops_*`), which are reproducible on demand. It is wrong for a figure derived
  from a *remote* fetch — a PageSpeed score for a URL at 09:00 is not
  reproducible later, and recomputing means re-calling the vendor on every page
  load.

So measured insights need a home of their own: workspace-scoped, append-only,
time-stamped, and provenance-bearing.

## Options considered

### A. A new `workspace_insight` table, linked to the Brain by surfacing (chosen)
A dedicated table. The Brain page gains an "Insights" section that *reads* it; the
Brain table is untouched. Measured data stays separate from stated facts; history
is kept for staleness and trend.

### B. Widen `company_brain` to carry insight columns
Add insight/info columns and admit a measured `generated_by`. One surface, but it
changes the Brain's meaning, loosens its check constraints, and couples the
connector cadence to the Brain's supersede-on-rebuild versioning.

### C. No store — recompute on every request
Matches the dashboard's live-compute philosophy, but a remote fetch is not
reproducible and would re-hit the vendor on every load, defeating caching,
staleness and rate limits.

## Decision

Option A. A new `workspace_insight` table:

- `workspace_id` (FK, `ON DELETE CASCADE`), `source` (the `Source` enum value,
  e.g. `pagespeed`, `crm`), `metric_key` (canonical key), one of
  `value_numeric`/`value_text`/`detail` (JSONB), optional `unit`, `provenance`
  (not null), optional `department`, `captured_at` (not null, default `now()`).
- **Append-only, no supersede column.** "Current" is the newest `captured_at` per
  `(workspace_id, source, metric_key)`, exactly as `retrieval/deals.py` treats
  `crm_deal.fetched_at`. History is what lets a tile say STALE or show a trend.
- RLS **enabled and forced** with a `workspace_id` isolation policy, matching
  `crm_deal` (0031) and `page_signals` (0028). `nexus_app` is `NOBYPASSRLS`, so an
  unscoped read returns **zero rows, not an error** — pinned by an isolation test.
- Two check constraints: an insight must carry a value
  (`value_numeric`/`value_text`/`detail` not all null), and a `unit` requires a
  `value_numeric` (a unit with no number describes nothing) — the same shape as
  `ck_crm_deal_amount_currency`.
- Reads go through a scoped retrieval module (`retrieval/insights.py`, takes a
  `ScopedSession`, never a `user_id`); writes go through `domain/insights.py`
  (`record`/`current`), matching the `company_brain` write shape.

## Reasoning

A was chosen because the one property this product cannot give up is that a number
is traceable to how it was produced, and the cleanest way to keep *measured* and
*stated* traceable is to keep them in different tables with different constraints.
B would have been fewer objects but at the cost of the Brain's meaning and its
constraints, and it would have forced the connector write cadence through the
Brain's supersede-on-rebuild versioning. C was rejected because, unlike every
figure the dashboard computes today, a connector insight is derived from a remote
fetch that is not reproducible after the fact — persisting it is what makes the
figure checkable later, which is the same argument `crm_deal` and `page_signals`
already make for landing a provider's rows in our database before a calculator
reads them.

## Consequences

- Measured insights have a scoped, provenance-bearing, time-series home that the
  dashboard, the Brain page and the assistant all read the same way.
- The Brain table and its constraints are unchanged; the "Insights" section is a
  read, not a schema change to the Brain.
- A new table means a new RLS policy to prove — covered by
  `test_workspace_insight_isolation.py`, run as `nexus_app` against real Postgres.
- Append-only growth is unbounded in principle; acceptable at connector cadence
  (a handful of rows per source per day). A retention/rollup policy is deferred
  until volume warrants it (see Revisit).

## Revisit trigger

Reopen if: insight volume per workspace grows enough to need retention or rollup;
a second consumer needs a shape this table cannot express (e.g. multi-dimensional
breakdowns better served by a child table); or the distinction between stated and
measured stops mattering to the Brain's design, at which point B becomes viable.
