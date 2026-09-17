# 0036 — The first ops rate, and where "late" comes from

**Status:** Accepted
**Date:** 17 September 2026
**Decides:** D32
**Depends on:** ADR 0035 (completeness), ADR 0034 (a figure that is neither a score nor an amount)
**Context:** `doc/15` S10.4 — `operations.on_time_dispatch`

## Context

Every ops figure so far has been a count, because a count states what was
recorded and is true whether or not the record is complete. `on_time_dispatch`
is the first **rate**, and a rate needs two things the ops layer did not have:

1. **A vouched denominator.** ADR 0035 supplies it — no confirmation, no rate.
2. **A threshold for "late".** This is D32, and it had no answer at all.

`operations.on_time_dispatch` declares `consumes_facts = ('promised_lead_time',
'late_definition')`. Both are asked during onboarding, and both arrive as **free
prose**: `late_definition` is typed `SINGLE_CHOICE` with no choices defined, and
`AnswerShape.DURATION` turns out to be only a *cue* that helps the agent phrase
the question — there is no parser anywhere in the codebase that turns "a day or
two after we said" into a number.

The question bank's own note on `late_definition` reads: *"The definition of
'late'. Every lateness figure is meaningless without it."* It is right, and the
answer it collects cannot be computed with.

## Decision

**A promised date on every dispatch, and a grace period the founder sets as a
number.**

- `ops_dispatch.promised_on` is `NOT NULL` — the date this customer was promised.
  It is the founder's own promise, recorded per order, so nothing about it is
  inferred.
- `workspace.dispatch_grace_days` is a **nullable** `SMALLINT` with **no server
  default**. An order is late once it is more than that many days past
  `promised_on`.
- On time is `dispatched_on <= promised_on + grace`. Nothing is parsed.

**`NULL` is the gate, and the absence of a default is the whole point.** A
`DEFAULT 0` would be a threshold *we* set, silently, for every workspace — and
it would produce a confident percentage computed under a rule the customer never
agreed to. That is precisely the failure this product exists to prevent, so the
column starts empty and the rate refuses until somebody fills it in.

**Two gates, both required, and they refuse for different reasons.** Completeness
missing means we do not know the denominator covers everything. Grace missing
means we do not know what the numerator *means*. The tile says which one is
absent, because "connect nothing, we cannot tell you" and "answer one question,
then we can" are different messages and only one of them is actionable.

**The counts ship regardless.** Dispatches recorded, still outstanding, and past
the promised date are true without either gate, so the tile is useful from the
first record and gains the rate when it is earned.

## The fourth figure kind

`RateFigureOut`, tagged `kind: "rate"`, joining score, amount and count. It
carries `on_time`, `dispatched`, `percentage`, `outstanding`, `overdue` and the
`grace_days` it was computed under.

**`percentage` is served, never divided in the browser**, for `ScoreFigureOut`'s
reason: two clients must not round differently from the drawer showing the
working. It is `null` when the denominator is zero — a workspace that has
recorded dispatches and sent none yet has no rate, and `0%` there would say every
order was late (I10).

**`grace_days` travels with the figure.** A percentage whose rule is invisible is
a percentage nobody can check, and this one is the customer's own rule rather
than ours.

## Consequences

- **A rate is still not narratable, and that is a bounded gap rather than a
  principle.** ADR 0033 refused narration for amounts because `narrate-metric`
  speaks in numerator, denominator and percentage — which a rate genuinely has.
  What stops it today is `domain.narration.describes`: it is typed to
  `Computation` and compares a `page`, which a rate has no equivalent of. Turning
  narration on for rates means extending the staleness contract, and that
  contract is the only thing keeping prose about last week's number from sitting
  beside this week's. It is its own change.
- **`promised_lead_time` is not consumed by the calculation**, though the
  capability declares it. It remains the right question to ask — it is what a
  founder would use to fill in a promised date — but a lead time in prose cannot
  produce one. Recorded here so the declaration and the code can be reconciled
  deliberately rather than discovered as a surprise.
- **`late_definition` is not consumed either**, and the honest fix is to change
  what it collects: a number, or a small set of choices. That is a change to
  onboarding, which this slice does not touch.
- **Confirming completeness now matters for a fifth entity**, `dispatches`.

## Alternatives rejected

**Parse the prose into days.** Fastest, needs nothing new, and is us inventing a
threshold from somebody's sentence — failing silently on wording it does not
recognise, which is the worst available failure mode: a wrong percentage with no
symptom.

**Strict comparison, no grace.** Defensible, since the promised date is the
founder's own. Rejected because it fixes the grace at zero without saying so, and
a founder whose `late_definition` says "a day's grace" would get a figure that
contradicts their own stated rule while looking authoritative.

**Counts only, again.** Honest, and defers the first ops rate a second time. D29
was answered specifically so this could stop being deferred.
