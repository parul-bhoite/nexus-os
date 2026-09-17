# 0039 — The ops layer reads in one round trip

**Status:** Accepted
**Date:** 17 September 2026
**Context:** `doc/15` S10.6 — measured after the Today page stopped loading

## Context

`current_ops` grew one statement per slice. By S10.6 it issued nine on a single
connection, one after another: seven record tables, the completeness log, and the
two workspace rules. Each is correct and none is slow; they are sequential.

Measured directly against the API on the development machine, after S10.6:

| Endpoint | Before |
|---|---|
| `GET /dashboards/surface` | **31–37 s** |
| `GET /ops` | **13 s** |

The BFF's proxy timeout is 30 seconds, so the Today page **stopped loading**.
S10.5's dashboard rendered; S10.6 added one read and crossed the line.

The cause is round-trip count, not any one query. This machine reaches its Neon
instance in roughly two seconds per statement — the same latency that makes the
test suite take hours and that `CLAUDE.md` already records. Co-located with the
database the whole page would be well under a second.

**That makes the local number misleading and the shape still wrong.** Fourteen
sequential round trips for one page load is a design problem wherever the
database sits; the latency here only made it visible.

## Decision

**One statement, nine result sets.** `_EVERYTHING` selects nine `json_agg`
subqueries — the same rows, the same `WHERE` clauses, the same `ORDER BY`s — and
`current_ops` converts them into the dataclasses it already returned.

| Endpoint | Before | After |
|---|---|---|
| `GET /dashboards/surface` | 31–37 s | **17–20 s** |
| `GET /ops` | 13 s | **7–9 s** |

**Nothing moved into SQL except the fetching.** `retrieval/ops.py`'s standing
rule is that arithmetic belongs in `calculators/`, where the working drawer can
show it — the module's own docstring rejects `SELECT count(*) … GROUP BY status`
for exactly that reason. `json_agg` is a transport, not a calculation: no
counting, no grouping, no share. The line this ADR draws is **fetching may be
combined; computing may not.**

`COALESCE(…, '[]')` so an empty table arrives as an empty list rather than
`NULL`, leaving the caller one shape. The per-table `ORDER BY` stays inside each
subquery, and `json_agg` over an ordered subquery preserves it — which is what
keeps the lists stable between requests, the reason each ordering carries a
second key.

**The nine superseded constants are deleted, not left behind.** Dead code that
looks live is the thing this codebase keeps warning about.

## Consequences

- **Conversion code now exists, and it is the risk this decision buys.** JSON
  returns strings where the dataclasses hold `UUID`, `date` and `datetime`.
  `_uuid`, `_date` and `_stamp` are deliberately tiny and deliberately tolerant
  of `NULL`, because `project_id`, `assignee_id`, `owner_id` and every optional
  date are genuinely nullable. The 42 ops database tests exercise every one of
  these paths through `/ops`, which is what makes the rewrite checkable rather
  than hopeful.
- **Seventeen seconds is not fast.** Five round trips remain on the surface —
  crawl, deals, typed deals, ops, narrations — plus the connection's own setup.
  The same argument applies to them and they are not addressed here.
- **A tenth ops table costs nothing extra.** That is the point, and also the
  trap: the query is long, and a reader skimming it should not mistake its length
  for complexity.
- **`json_agg` is Postgres-specific.** So is every other statement in
  `retrieval/`, and ADR 0008 pins Postgres.

## Alternatives rejected

**Run the nine concurrently on separate connections.** The largest win — total
time becomes the slowest query rather than the sum — and it needs nine
connections per request against a pool of ten. One page load would exhaust the
pool and the second reader would wait for the first.

**Raise the BFF timeout.** Turns a page that fails into a page that takes thirty
seconds, and removes the only signal that anything is wrong.

**Cache the snapshot.** Faster on the second load and wrong on the first, and it
would put a staleness question in front of figures whose whole claim is that they
say what was recorded.

**Leave it, because production is co-located.** The number here would be fine
elsewhere and the shape would still be fourteen sequential round trips, growing
by one per slice, with nothing to notice it next time.
