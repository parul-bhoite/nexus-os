# ADR 0030 — Coverage is counted by who has to move next

**Status** Accepted
**Date** 17 September 2026
**Decided by** The command-surface design session, after deriving every number from
`app/domain/registry.py` instead of estimating it. Recorded because it fixes a
customer-facing denominator, and because the draft it replaces promised something the
product cannot deliver.

## Context

The mock this redraw follows opens with **Company Health 82/100** and seven sub-scores.
ADR 0029's surface refuses a composite — averaging two figures would read as a verdict on
the business and is a verdict on one web page — so the region needed a replacement that
answers the same question, *where is this product for me?*, without being a verdict.

The first draft answered it with "2 / 90 capabilities producing a figure", a stacked bar
over connected sources, and a ladder reading *"connect analytics → 14 capabilities"*.
**Every number in it was estimated.** Deriving them broke three things:

1. **90 counts a `RULE`.** `executive.recommendation_filter` shapes what other
   capabilities say and is not something a customer acquires. `completeness()` already
   excludes it and says why — "putting it in the denominator would make the meter
   unreachable by one for ever". The denominator is **89**.
2. **"7 unlockable by answering" is actually zero.** All 24 fact-consuming tiles also
   require a source, so answering a question never switches a tile on. It changes what a
   tile *counts*.
3. **The ladder was a promise the product cannot keep.** `implemented` is 12, of which 10
   are Setup and Watchlist tabs. Connecting every source in existence would move the
   figure-producing count from 2 to 2, because 77 capabilities have no calculator.

A fourth problem was structural: **bands over sources are not a partition.**
`marketing.seo_gaps` requires `dataforseo` *and* `crawl`, computes today, and is still
missing a source — so it belongs in two bands at once, and a stacked bar would assert it
belongs in one.

## Decision

**Coverage reports who has to move next**, over the 89 tiles `completeness()` already
counts:

    2 / 89   capabilities produce a figure today
    ▮▮▮░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
    2 measuring · 10 reading your answers back · 77 not built yet

    2  — producing a figure           the two audit scores
    10 — reading your answers back    Setup and Watchlist across six directors
    77 — not built yet, which is on us

And beneath it a **source ladder that states what a source is *for*, never what it would
unlock** — ranked by how many capabilities name it as their only requirement, and saying
outright that connecting one today changes nothing.

### Reasoning

**Why this extends `completeness()` rather than replacing it.** That function answers
*what can I open?* and counts `reachable` over tiles — 12 of 89. This region asks the
narrower question *what is measured?* and answers 2. Both are true and they are different
questions, so the region shows both rather than picking one. The denominator is shared on
purpose: two customer-facing coverage numbers with different denominators is the
two-lists failure the registry module exists to end.

**Why the split is `reachable`, sub-divided by `computes()` — not `implemented`.** The
registry keeps `implemented` and `reachable` deliberately separate, and
`completeness()`'s docstring gives the reason: the two came apart once already, when the
audits had a real calculation and no route serving it, and counting `implemented` then
would have told a founder they held two capabilities they could not open. They agree
today at 12. Counting the band that a customer can *act on* keeps the region correct the
next time they diverge.

**Why we name our own side of the line.** The 77 is the honest headline: the constraint
between a founder and this product is our build progress, not their connections. Saying
so costs us the flattering version of the number and buys the only thing that makes the
other two bands mean anything. There is precedent — `planned` tiles already render as
"Not built yet" — so this states at the top what the tiles already say one at a time.

**Why the ladder is a heads-up and not a call to action.** Ranking sources by capability
count reads as "connect this, get ten tiles". None of those ten is built, so it would be
a promise broken on the first click, and it would move the blame for our unbuilt product
onto the customer's unconnected systems. The ladder survives because the counts are real
and knowing what NEXUS will ask for has value on its own; the framing is what changed.
This is the same line ADR 0029 draws for the brief — state what a thing is worth, never
what to do about it.

## Consequences

- **The dashboard states our own build progress to the customer as a headline number.**
  Taken by default here rather than asked, because the tiles already say it individually.
  If that posture is wrong, this ADR is what to amend.
- **Coverage absorbed the separate "Waiting on a source" region** — it was the same
  derivation rendered twice — and "Open on your side" is now questions only. Things you
  answer and things you connect are different kinds of thing and no longer share a column.
- **These counts must be derived, never typed.** They are correct today because they came
  out of the registry, and they will be wrong within a phase if the copy hard-codes them.
  This needs a `coverage()` beside `completeness()` in `domain/registry.py`, with a test,
  before the region ships.
- **A third coverage notion now exists** alongside `completeness()` and
  `openable_count()`. All three must share the 89 denominator, and a test should assert
  that rather than three docstrings agreeing by hand.

## Revisit trigger

Reconsider when any of these becomes true:

- **A calculator lands for a capability whose sources a customer can actually connect.**
  That is the moment the ladder can honestly become actionable, and "connect this, get
  that" should be re-argued rather than inherited from this refusal.
- **`implemented` passes roughly half of 89.** "Not built yet" stops being the honest
  headline once it is no longer the dominant band, and the region should lead with what
  is measured instead.
- **`reachable` and `implemented` diverge again.** The band definitions assume they agree;
  they did not always, and the registry keeps both flags precisely because they can come
  apart.
- **A composite score is granted a threshold.** ADR 0029 and this one both refuse one on
  the same grounds. If coverage ever earns a single number, it supersedes the three bands
  rather than sitting beside them.
