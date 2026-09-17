# 0034 — A figure that is neither a score nor an amount

**Status:** Accepted
**Date:** 17 September 2026
**Extends:** ADR 0033 (a figure that is not a score)
**Context:** `doc/15` S10.1 — the ops layer's first two tiles

## Context

ADR 0033 replaced a single figure shape with a discriminated union, because a
pipeline is not a score: it has no denominator, and inventing one would put a
percentage on screen that divides by a number the customer never gave us. The
union was chosen — over two sibling nullable fields — precisely so that **a
third kind fails to compile at every consumer** rather than falling silently
through a rendering branch.

`operations.projects_board` and `operations.task_queue` are that third kind.

A count of recorded projects is not a score: there are no weighted checks and no
maximum. It is not an amount either: there is no money, no currency, and the
"how many" is the whole figure rather than the population behind a total.
Rendering it through `AmountFigureOut` would mean serving `total_minor: null`
and `currency: null` on every ops tile — a money shape with the money removed —
and leaving `open`, `overdue` and `undated`, which are the actual figures,
nowhere to go.

## Decision

**Add a third arm, `CountFigureOut`, tagged `kind: "count"`.**

It carries `recorded`, `open_items`, `overdue`, `undated`, a plural `noun`, and
`recorded_at`. Its dispatch is `OPS_CENSUSES` in `grounding/compute.py`, beside
`CRAWL_AUDITS` and `PIPELINE_TALLIES`, producing a `CountComputation`.

Four properties are load-bearing.

**1. There is no denominator and none is derived.** `recorded` is the
population, and nothing may be divided by it. The ops layer **fails on adoption,
not on an API**: a founder who recorded three of their twelve projects gives us a
database indistinguishable from one who recorded twelve. A count survives that,
because it states what was recorded. A rate does not — *"67% on time"* over a
third of reality is a wrong number with a plausible denominator, arriving from
our own feature rather than from a model. Whether the record is complete is
**D29**, still open; `doc/15` S10.4 holds the first ops rate behind it.

**2. The label says "recorded".** *"Projects"* is a claim about the company;
*"Projects recorded"* is a claim about the record. Only the second is one we can
stand behind today, and the participle is asserted by a test rather than left to
whoever writes the next census entry.

**3. `recorded_at`, not `measured_at`.** Nobody fetched anything. The other two
kinds carry the moment we read somebody else's system; the only timestamp here is
the moment somebody typed, and borrowing the word "measured" would be the tile
claiming a provenance it does not have.

**4. The kind is what keeps a typed number from looking measured.** `doc/13` §7
requires that a number the founder typed and a number we measured never look
identical, and explicitly rejects a badge on an otherwise identical tile —
*"fails that at a glance and in a screenshot"*. A discriminated kind makes the
difference structural: a client narrows on it and renders a different body, so
there is no rendering in which a count passes for a measured figure.

`doc/13` §7 also says a self-reported value must never occupy a **metric** slot.
That rule is not crossed: both capabilities are declared `block: board` in the
registry, and §7's `SELF_REPORTED` treatment governs values the founder *stated*
— "revenue was 45,000" — which we would be repeating back. A count is arithmetic
**we** performed, in code, over rows they entered. The record is theirs; the
calculation is ours and is I1-compliant.

## Consequences

- **Counts are not narratable.** `_narratable` refuses `COUNT_CAPABILITIES` as it
  refuses `AMOUNT_CAPABILITIES`: `narrate-metric` speaks in numerator,
  denominator and percentage, so a sentence grounded in those keys would be
  grounded in nothing — and `domain.narration.describes` would compare fields
  that do not exist and never mark the sentence stale.
- **`OPS_LAYER` becomes a connected source when rows exist**, which makes these
  the first two capabilities in the product that can reach `live`. `live` means
  every required source is present, and the customer's own records are the
  required source; it does not claim the record is complete, and the label is
  what says so until D29 lands.
- **Every consumer had to be revisited**, which is the property ADR 0033 was
  chosen for working as intended.
- **A fourth kind is now cheaper to add and easier to add carelessly.** The guard
  in `test_grounding_compute.py` iterates the dispatches and separately asserts
  it has not missed one — added here because the "guarded in both directions"
  claim on `PIPELINE_TALLIES` had been in a docstring for a slice without being
  true.

## Alternatives rejected

**Reuse `AmountFigureOut` with `total_minor: null`.** Every ops tile would serve
a money figure with no money, and `open`, `overdue` and `undated` — the figures a
founder actually reads — would have nowhere to live. The shape would describe
what the tile is not.

**A generic `FigureOut` with an untyped `values` map.** It ends the union
problem by ending the union, and with it every guarantee that made 0033 worth
choosing: no client narrows, no consumer fails to compile, and "which keys does
this kind have" moves from the type system into prose.

**Wait for D29 and ship nothing.** `doc/15` S10.1 explicitly does not wait,
because a count of what was recorded is true whether or not it is complete. The
tiles that would have waited are the rates, and they still do.
