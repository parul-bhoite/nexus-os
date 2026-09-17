# 0040 — Operations shows its drivers and no score

**Status:** Accepted
**Date:** 17 September 2026
**Decides:** D31
**Depends on:** ADR 0029 (the morning brief is a composition), ADR 0030 (coverage is counted by who is blocking), ADR 0035 (completeness)
**Context:** `doc/15` S10.7 — `operations.score_drivers`

## Context

`operations.score_drivers` is declared as a `metric` block showing *"Score,
delta"*, and it would be the **first department score the product draws**. ADR
0029 and ADR 0030 both refused a composite at company level, and D31 asked
whether the same argument survives one level down.

**The argument that applied then does not apply now.** Those ADRs refused a
composite over *thin coverage*: too few capabilities measured for an average to
mean anything. Operations is now the best-covered department in the product —
projects, tasks, milestones, issues, dispatch, stock and suppliers all produce
figures.

**A different argument applies instead, and it is stronger.** Every one of those
seven inputs is the customer's own records. A single number over them does not
measure how well operations run; it measures **how diligently somebody types**.
A founder who records everything and runs a shaky business scores well. One who
runs a tight business and records a third of it scores badly, and the tile would
tell them their operations are the problem.

ADR 0035's completeness gate cannot rescue this. Confirming a list is complete
makes a *rate* over that list honest; it says nothing about whether recording
practice across seven entities is even enough to average. And D29's own framing
is that the ops layer fails on adoption — a score is precisely the figure that
mistakes adoption for performance.

## Decision

**Build the drivers. Do not compute the score.**

`operations.score_drivers` renders the figures it is built from, side by side and
uncombined: what is overdue, what went out on time, what is under its minimum,
how much sits with one supplier. Each one is already computed, already traceable
to records, and already carries its own provenance and refusals.

**This is the shape the product already uses when it can say something true and
something false.** `operations.on_time_dispatch` shows its counts and withholds
its percentage when a gate is shut (ADR 0036); the issue register shows severity
bands and never a share (ADR 0034). A tile that gives the honest half and
declines the rest is the established answer here, not a new compromise.

**The capability's `shows` is narrowed, deliberately and in the open.** It reads
*"Score, delta"* and the tile delivers neither. That is a promise the registry
makes and this decision breaks, so it is written down rather than left for a
reader to notice: `doc/05`'s wording anticipated a department score, and the
product has since learned what its inputs are made of.

**Nothing computes a delta either.** A delta needs a baseline, and the earliest
honest baseline here is the first day somebody recorded anything — which would
compare a fortnight of diligent typing against a week of it.

## Consequences

- **`executive.todays_priorities` is unaffected and ships.** It is a *ranking of
  concrete items*, not a composite: every row points at one record a founder can
  open. ADR 0029 already established that a composition over things that exist is
  not the same as a score over things that might not.
- **`scoreable = True` on `operations.score_drivers` is now misleading**, and is
  left alone rather than quietly flipped. It feeds `scoreable_units` and
  `score_denominator`, which count what the product *intends* to score; changing
  it to make one tile's copy tidy would move a company-level denominator as a side
  effect. `doc/12`'s phase for the composite score is where that belongs.
- **The first department score is still unbuilt**, and the condition for revisiting
  is not "more ops capabilities" but **a measured input** — a connector reporting
  something we did not type. Marketing reaches that first.
- **A reader is told why the number is absent**, in the tile, in the same voice
  every other refusal uses. An empty metric slot with no sentence is the failure
  `doc/13` §7 spends its whole table avoiding.

## Alternatives rejected

**Score it, labelled self-reported.** The label does not survive the screenshot.
`doc/13` §7 makes exactly this point about badges, and a number that will be read
as "how good are your operations" is not rescued by small type saying where it
came from.

**Score only measured inputs, refusing while any is self-reported.** Principled,
and for Operations it renders nothing at all today — the same outcome with a
scoring engine behind it, waiting for a connector that belongs to a later phase.

**Leave the tile unbuilt entirely.** It leaves a named capability delivering
nothing while every one of its inputs exists, which is its own dishonesty toward
a founder reading the catalogue.
