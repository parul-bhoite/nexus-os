# 0059. The assistant is its own route module

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements:** `doc/20` §3 "ADR F". Numbered 0059, not the 0057 the plan
  proposed — the numbering shifted during A2–A4.
- **Blocks:** `doc/20` A8
- **Affects:** `app/routes/assistant.py`, `app/main.py`,
  `tests/test_no_unauthenticated_crawl.py`

## Context

`POST /dashboards/{department}/ask` needs the same three dependencies the
director page uses — `ReachableDirector`, `CurrentScope`, `require_csrf` — and
`reachable_director` lives in `app/routes/dashboards.py`, which is **2,300
lines**.

It also needs things no other dashboard endpoint needs: a provider, the budget
module, the rate limit, and the assistant feature flag.

One more constraint decides more than it looks like it should.
`tests/test_no_unauthenticated_crawl.py` walks imports to prove no unauthenticated
path reaches a fetch, and it **groups by route function but falls back to
module**. A route added to a large module inherits that module's whole import
set for the purposes of that walk.

## Options considered

### A. A third endpoint on `routes/dashboards.py`

The dependencies are already imported there; the URL is already that module's
prefix.

### B. `app/routes/assistant.py`, importing `reachable_director` from dashboards

A new module, mounted at the same prefix.

## Decision

Option B.

## Reasoning

**The import walk is what makes this more than taste.** Under A, the assistant's
imports — a provider, the skill runner — join a module that already imports a
large part of the application, and the crawl walk's module-level fallback then
reasons about the union. The signal it produces gets weaker for every endpoint
in that file, and this is the endpoint where "what can this path reach?" is the
question most worth being able to answer precisely. A module with five imports
gives a sharp answer.

**Sharing the URL prefix is not sharing a module.** The dependency that enforces
the department is imported, so the refusals are literally the same code — a
caller who cannot open Finance is refused by `reachable_director`, not by a
second implementation that has to be kept in step. That was the real risk in
splitting, and importing the dependency removes it.

**2,300 lines is a reason but not the reason.** File size alone would not
justify a module; it justifies it in combination with a different dependency
set and a feature flag that must be readable at a glance.

## Consequences

- `app/routes/assistant.py` imports `reachable_director` from `dashboards.py`.
  That is a route module importing a route module, which is unusual here — the
  alternative is moving `reachable_director` to `app/domain/`, which is the
  better end state and is deliberately **not** done in A8 so the flag can ship
  behind a small diff.
- One more `include_router` in `main.py`.
- The crawl walk sees a module with a small, readable import set.

## Revisit trigger

If a second non-dashboard surface needs `reachable_director` — a scheduled
brief, an export — then two route modules import a third, and the function
should move to `app/domain/directors.py` at that point rather than accumulating
importers.
