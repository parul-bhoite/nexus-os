# ADR 0033 — A figure that is not a score

**Status** Accepted
**Date** 17 September 2026
**Decided by** Parul, answering D28 — *"go with C for D28"*. Surfaced by `doc/14` step 9:
the pipeline calculator was written, tested and unrenderable, and widening the figure model
quietly would have been the wrong way to fix that.

## Context

`FigureOut` is an audit's shape and says so:

```python
score: int
max_score: int
percentage: int
checks: list[CheckOut]
checks_passed: int
```

Its own docstring argues the denominator: *"A score on its own is a claim the reader cannot
check; `45 out of 65` lets them count."* Every field earns its place for a scored audit.

`calculators/pipeline.py` produces something else entirely — `23 open deals`,
`OMR 148,000`, `3 unpriced`, `7 closing within ninety days`. **It has no denominator, and
there is no honest way to invent one.** A target to divide by would be a figure the
customer never gave us, which is I1's exact prohibition arriving as a helpful-looking
percentage.

So the calculator ships and no tile can render it. That is the right way round — a
capability with a figure nobody can read is better than a figure that lies about its
shape — but it is not a resting state.

**Three existing rules constrain any answer**, and they are why this is a decision rather
than a widening:

1. **`describes()` (ADR 0028)** decides whether a stored narration still applies, by
   comparing `numerator`, `denominator`, `percentage`, `page` and `window`. An amount
   figure has none of the first three. Left alone, a narration about a pipeline would
   compare five fields that do not exist and never be superseded.
2. **`percentage` is served, not divided in the browser** — so two clients cannot round
   differently. The same must hold for money, and money has more ways to differ: minor
   units, currency placement, grouping.
3. **I10.** `total_minor` is `None` when a pipeline cannot be totalled — no priced deals,
   or two currencies. That must not render as `0`, which would say the pipeline is worth
   nothing.

## The options

**A — One type, optional fields.** Add `amount_minor`, `currency` and `count` to
`FigureOut`; make `score`, `max_score` and `percentage` optional. One field on `BlockOut`,
no new plumbing.

**B — A sibling field.** `BlockOut.figure` stays exactly as it is; add `BlockOut.amount`.
Discriminated by which is present.

**C — A discriminated union.** `figure: ScoreFigure | AmountFigure`, tagged with
`kind: "score" | "amount"`. One field, one explicit branch.

**D — Generalise to "a value with provenance".** One shape: a value, a unit, an optional
denominator, and working. Everything becomes an instance of it.

## Decision

**C — a discriminated union**, `figure: ScoreFigureOut | AmountFigureOut`, tagged
`kind: "score" | "amount"`.

### Reasoning

**Why not A, and this is the strongest argument here.** Making `max_score` optional means
a scored audit can be serialised without a denominator — and `FigureOut`'s whole docstring
is that a score without one is a claim the reader cannot check. An optional field is a
field that will eventually be absent, so A weakens the invariant that the model currently
enforces by construction, in order to describe something that never had it.

**Why not B.** Two sibling fields make a third state representable: a block with both, or
with neither while claiming a figure state. That needs a constraint somewhere, and a
constraint that exists only in prose is one a payload will eventually violate. A union
cannot express the illegal case at all.

**Why not D, yet.** One general shape sounds right and would make every figure slightly
vaguer — `value` and `unit` say less than `score`/`max_score` does, and the drift is the
kind nobody notices until a percentage and a count are rendered the same way. Two concrete
kinds are honest about there being two; a third would be the moment to reconsider.

**Why a tag rather than structural discrimination.** TypeScript narrows on a literal `kind`
exhaustively, so a new kind makes every consumer fail to compile rather than silently fall
through a rendering branch. Inferring the kind from which fields are present is the same
information with none of that.

**What C forces, and should.** `describes()` has to be written per kind. A pipeline's
staleness is not *"did the numerator move"* — it is *"did the total, the count, or the
currency move"*, and the window still matters because a figure from last week's sync is
not this week's. Being made to write that is the point; A and B would let the existing
five-field comparison run against an amount figure and quietly never fire.

## Consequences

- **Every consumer of `figure` branches**: `BlockCard`, the working drawer, the narration
  button, `domain/narration.describes`, and the surface's `measured` list. That is the
  cost, and it is paid once.
- **Money formatting becomes a served concern.** `percentage` is served today so two
  clients cannot round differently; an amount needs the same treatment, and minor units
  plus a currency code is the shape that survives a reporting-currency change.
- **`sales.pipeline_board` becomes renderable**, which is the first capability outside
  Marketing to carry a figure — and the first test of whether `doc/13`'s block kinds
  describe anything beyond an audit.
- **The narration skill needs a second grounding shape.** `narrate-metric`'s `SKILL.md`
  speaks in numerator and denominator; a pipeline sentence grounded in those keys would be
  grounded in nothing.

## Revisit trigger

- **A third figure shape appears** — a rate, a duration, a trend over periods. At that
  point D stops being premature and two concrete kinds start being three.
- **A capability needs both a score and an amount.** The union forbids it, deliberately;
  if that turns out to be a real tile rather than a hypothetical, the constraint is wrong
  rather than the tile.
- **Re-crawling lands (M32)** and figures gain a real delta. A delta on money is a
  different rendering from a delta on a score, and whichever way this ADR is answered will
  be tested by it.
