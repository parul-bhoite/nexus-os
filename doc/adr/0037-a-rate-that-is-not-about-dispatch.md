# 0037 — A rate that is not about dispatch

**Status:** Accepted
**Date:** 17 September 2026
**Amends:** ADR 0036 (the first ops rate, and where "late" comes from)
**Context:** `doc/15` S10.5 — `operations.supplier_risk`

## Context

ADR 0036 introduced `RateFigureOut`, the figure union's fourth arm, and described
it as carrying *"`on_time`, `dispatched`, `percentage`, `outstanding`, `overdue`
and the `grace_days` it was computed under"*.

That was the shape of one calculator, not of a rate. `RateComputation` held an
`OnTime` — `calculators/dispatch.py`'s own dataclass — so the figure and the
single thing feeding it were the same object. S10.5's supplier concentration is
also a rate and shares **none** of those fields: it has no outstanding work, no
overdue, and no grace period, and its two halves are money rather than counts.

Left alone, the union would have needed a fifth arm for the second rate and a
sixth for the third. That is precisely the outcome ADR 0033 chose a discriminated
union to avoid.

## Decision

**Three changes, and the third is the one with a real alternative.**

**1. `RateParts` sits between a calculator and the figure.** A normalised
numerator, denominator, percentage and `denominator_label`, plus the counts that
sit beside a rate and are true under every refusal. Each calculator is converted
into it in one place — `_parts_for` — with an explicit branch per capability
rather than a registry of callables: there are two, they have genuinely different
shapes, and indirection bought with nothing is worse than a readable `if`.

**2. The denominator is named in words.** `"orders that went out"`, `"of the
spend you have recorded"`. A rate whose denominator is unlabelled is a number
nobody can check, and the label belongs to the calculator rather than to the
client, which should not have to know which capability it is drawing.

**3. `unit` is served explicitly — `"count"` or `"money"` — and is never inferred
from `currency` being set.**

This is the decision worth recording. `POST /companies` deliberately does not
store `reporting_currency`: the comment there says the fact is *"asked properly
later, by the question catalogue as a constrained choice that arrives with a
scope"*. So a workspace that has not been through reporting settings has
**money with no currency** — a real and ordinary state, not an error.

A client reading `currency === null` as "these are counts" would then print minor
units at somebody as though they were a number of things: `60000 of 100000`
beside a label saying "of the spend you have recorded". Technically true, and
read as an order count by anybody skimming.

With `unit` explicit there are three honest renderings rather than two:

| `unit` | `currency` | What the tile shows |
|---|---|---|
| `count` | — | `3 of 4 orders that went out` |
| `money` | set | `OMR 600 of OMR 1,000 of the spend you have recorded` |
| `money` | `null` | the share alone, and the denominator's name |

**A currency is never defaulted.** `routes/companies.py` uses
`reporting_currency or "OMR"` when *displaying* reporting settings, and that is a
different thing: defaulting a settings form is a convenience, defaulting the
currency a figure is denominated in is a fact nobody gave. The share is true
regardless of whether we can format its halves, so the share is what we show.

## Consequences

- **ADR 0036's description of `RateFigureOut` is superseded by this one.** Its
  reasoning about the two gates, the refusals and the denominator being *what
  went out* all stand; only the field list is replaced.
- **`retrieval/ops.py` now selects `reporting_currency`**, which falsified a
  comment in `routes/companies.py` stating that no SELECT in the codebase named
  it. The comment has been corrected rather than left to be discovered.
- **A third rate is now cheap**, and `_parts_for` is where it goes. When that
  branch reaches four or five capabilities the `if` should become a table; two is
  not that moment.
- **`CountFigureOut` gained `open_label` for the same class of reason.** "12
  projects recorded, 3 still open" is right for work and wrong for stock, where
  the same field counts lines under a level somebody set. The phrase is a fact
  about the record type, so the server carries it.

## Alternatives rejected

**Infer money from `currency` being set.** One less field, and it conflates "these
are counts" with "this is money we cannot format" — the two cases that must
render differently. The bug it produces is silent and reads as a plausible number.

**Default the currency to the workspace's country, or to OMR.** It would make
every figure formattable and some of them wrong, and a founder in Dubai would be
shown their supplier spend in rials without being asked.

**A fifth arm on the union for money rates.** The union exists so a new *kind* of
figure fails to compile at every consumer. A rate over money and a rate over
counts are the same kind, rendered differently; splitting them would spend that
mechanism on a formatting difference and leave a sixth arm waiting for the next
one.
