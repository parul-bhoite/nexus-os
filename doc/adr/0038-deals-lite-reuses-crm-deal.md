# 0038 — Deals-lite reuses `crm_deal`, partitioned by provenance

**Status:** Accepted
**Date:** 17 September 2026
**Decides:** D30
**Depends on:** ADR 0033 (a figure that is not a score)
**Context:** `doc/15` S10.6 — `sales.deals_lite`

## Context

`sales.deals_lite` is *"a minimal deal tracker for customers with no CRM"*, and
`crm_deal` already exists: `workspace_id`, `provider`, `external_id`, `amount_minor`,
`currency`, `stage`, `closes_on`, `fetched_at`, with RLS forced and a unique key
per `(workspace, provider, external_id)`.

Writing hand-typed deals as `provider = 'nexus'` makes `calculators/pipeline.py`
work for both with no new code and no new table. It also puts a typed deal and a
synced one in the same rows, which `doc/05` §0's rule — a number somebody typed
and a number we measured must never look identical — argues against.

## Decision

**Reuse the table, and partition by provenance at every read.**

`provider = 'nexus'` marks a hand-typed deal. There is **no migration**: the
column exists, carries no CHECK, and the unique key already includes it.

The reuse is only safe because of the second half, which is the part that is easy
to skip:

**`retrieval/deals.py` partitions rather than filtering nothing.** Before this,
`current_deals` selected every `crm_deal` row for the workspace and returned them
labelled `provider="crm"`. Adding typed rows to that table without touching the
query would have fed hand-typed deals straight into `sales.pipeline_board` as
though a CRM had reported them — silently, with no symptom, and producing exactly
the blended figure `doc/05` §0 forbids. So:

- `current_deals` reads `provider <> 'nexus'` — what a provider told us.
- `current_typed_deals` reads `provider = 'nexus'` — what somebody wrote down.

Two capabilities, two populations, one table.

**The kind is the same and the provenance differs.** Both figures are amounts
(ADR 0033): a total with a count behind it and no denominator. An amount typed
and an amount synced are the same *shape* of fact with different standing, so
splitting the union again would be spending its one mechanism — a new kind fails
to compile at every consumer — on something that is not a new kind.
`AmountFigureOut` carries `self_reported` instead, and the tile says where the
number came from in words.

**`fetched_at` means "when this row's contents were established".** For a synced
deal that is the moment we asked, which is what `0031` says. For a typed deal it
is the moment somebody saved it. The column's name is now wider than its original
comment, and the honest mitigation is that the *figure* never says "read from
your CRM" about a typed deal — it says recorded, because `self_reported` decides
the sentence.

**`external_id` is generated for a typed deal.** It is `NOT NULL` and part of the
unique key, and a hand-typed deal has no external system to have an id in. A
generated UUID is our own identifier for the row rather than a pretend one from
somewhere else, and the unique key keeps doing its job — a second typed deal
never collides with a first.

## Consequences

- **No new table, no migration, and `calculators/pipeline.py` is untouched.** That
  was the whole argument for reuse and it holds.
- **`sales.pipeline_board` narrows.** It now counts synced deals only. A workspace
  with a CRM sees no change; one with both sees two tiles, each about its own
  population, which is the correct reading of "for customers with no CRM".
- **A workspace can hold both**, and nothing stops it. That is not a state we
  design for, but it is one a founder can reach by connecting a CRM after typing
  deals, and the partition means neither figure quietly absorbs the other.
- **No completeness gate.** An amount is true whether or not the record is
  complete — it states what was recorded, exactly as a count does. D29's gate is
  for rates, and there is no rate over deals yet. When one arrives it will need a
  `deals` entity and the gate.
- **The `self_reported` field is on the figure, not the widget state**, for
  ADR 0035's reason: `WidgetState.SELF_REPORTED` renders quoted text and no figure
  at all, which would blank a tile whose whole job is a total.

## Alternatives rejected

**A separate `deals_lite` table.** Cleanest separation and the most duplication: a
second schema, a second read, a second calculator or a generalised one, and a
migration — to express a distinction one existing column already carries. It
would also make "this customer later connected a CRM" a data migration rather
than a second population.

**Reuse with no partition.** The cheap version of this decision, and the one that
looks identical until somebody types a deal into a workspace that also syncs one.
It is the reason this ADR exists rather than a one-line note.
