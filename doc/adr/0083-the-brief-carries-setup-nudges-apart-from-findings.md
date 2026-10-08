# 0083. The morning brief carries finish-your-setup nudges, kept apart from the findings

- **Status:** Proposed
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

After onboarding, a founder lands on the dashboard and should be prompted to
finish setting up by connecting the tools they declared they run — the doc/09 §3
conversion mechanism ("Connect Google Analytics — turns on six Marketing
capabilities"). The product already computes this honestly: `connections.gaps_for`
turns each *declared but unconnected* tool into a named gap with a named unlock,
and only the declared ones, because a gap for a tool nobody runs is noise.

The natural home for the prompt is the morning brief — the first region of the
common surface. But the brief has a hard design rule (ADR 0029): it is **a
ranking, not a recommendation**. Its items say *what was observed* and never *what
to do*; the test suite pins that a finding's label is used verbatim and never
turned into advice. A connect-your-tools prompt is, by nature, an action — so
putting it into the findings list would break the one rule the brief exists to
hold.

## Options considered

### A. A separate `nudges` field on the brief (chosen)
Add `BriefNudge` and a `nudges` tuple to `Brief`, independent of `items` and of
`state`. Findings stay a pure ranking; nudges carry the call to action. The route
builds nudges from `gaps_for(declared_providers)`; the brief module stays
dependency-light (it takes pre-built nudges, importing nothing new).

### B. Make nudges `BriefItem`s in the ranking
One list, simplest wire. Rejected: it puts a recommendation into the ranking,
directly violating ADR 0029, and the "label used verbatim, never negated" tests
have no sensible meaning for an action.

### C. Put the prompt elsewhere on the surface, not in the brief
A separate region. Defensible, but the product intent (and the user's request) is
specifically that the brief does the nudging, and the brief is where a founder's
eye lands first. A second region competing for that slot is worse than one brief
that carries both, cleanly separated.

## Decision

Option A. The brief gains a `nudges: tuple[BriefNudge, ...]` field (default empty)
alongside `items`:

- A `BriefNudge` is `headline` (the catalogue's "Connecting HubSpot"), `unlocks`
  (the capability sentence, from the tool catalogue, never invented), and `href`
  (`/settings`).
- `compose(..., nudges=())` sets them in **every** state — a workspace with no
  crawl (`NOT_MEASURED`) still has declared tools worth connecting.
- The `/surface` route reads declared providers once (added to the `Observed`
  dependency) and maps `gaps_for(...)` → `BriefNudge` → `BriefNudgeOut`.
- The web `MorningBrief` renders a "Finish setting up" block, each nudge linking
  to the settings portal, in every state; nothing renders when there is nothing
  to connect.

A nudge is grounded in a **fact the customer gave us** ("we run HubSpot") and the
capability the catalogue says its connection unlocks — not advice nobody computed.
That is why it does not cross the line ADR 0029 draws: the ranking stays free of
recommendations, and the action lives in its own field.

## Reasoning

A keeps both invariants intact at once: the findings ranking stays pure (the thing
ADR 0029 protects), and the brief still carries the one call to action the product
has always made honestly (the thing doc/09 §3 needs). B was the least code and the
most wrong — it would have put advice into the ranking. C splits a single mental
region ("the brief") into two, for no benefit, against the explicit intent that
the brief is where the nudge belongs.

## Consequences

- A declared-but-unconnected tool appears on the dashboard's first region as a
  prompt with its unlock, linking to Settings — the P4/P5 connect flow then turns
  it into a real insight.
- The `Observed` dependency does one extra small read (declared providers) per
  surface load; a `WHERE` clause on the Neon link, not a new page-load cost worth
  avoiding.
- `OAUTH_READY` is empty today, so every declared tool is "unconnected" and will
  nudge; as connectors land and move into `OAUTH_READY`, `gaps_for` drops them
  automatically and the nudge disappears without any brief change.
- `BriefOut` and the web `Brief` type gain a `nudges` field; a stale client that
  ignores it simply shows no nudges.

## Revisit trigger

Reopen if: the brief gains a third class of content and `items`/`nudges` is no
longer the right cut; nudges need ordering or de-duplication logic the route's
simple map cannot express; or a dedicated "setup" surface is introduced and the
nudge should move off the brief.
