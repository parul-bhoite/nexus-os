# 0056. An answer's citations are rows, not a JSON blob

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements:** `doc/20` §5 Q6, planned as "ADR C". **Numbered 0056, not the
  0054 the plan proposed** — 0054 and 0055 were taken during A2 and A3.
- **Blocks:** `doc/20` A4
- **Affects:** migration `0040`, `app/assistant/ask.py` (A6),
  `app/grounding/ledger.py`

## Context

`generation` already records every model call: the question's inputs, the
calculation trace, the scope tag, the cost, the outcome. It was built for
narration, where the grounding is a set of computed values and
`input_snapshot` holds them as JSON.

The assistant's grounding is different in kind. It is a set of **rows in this
database** — chunks the caller was permitted to read — and the answer points at
a subset of them. ADR 0053 makes those pointers load-bearing: they decide which
numerals the answer may state, so an answer's citations are not a description of
what happened, they are part of what was checked.

Where they are stored decides what can be asked of them later.

## Options considered

### A. Chunk ids inside `input_snapshot`

No migration. The ids travel with the rest of the grounding, in the column built
to hold grounding.

### B. `generation_citation`, a child table

One row per cited chunk, with foreign keys to `chunk` and `document`, its own
RLS, and a unique constraint on `(generation_id, chunk_id)`.

### C. Both — rows for querying, the blob for fidelity

Belt and braces. Two places to keep consistent, and no rule for which wins when
they disagree.

## Decision

Option B. Citations are rows in `generation_citation`, with `workspace_id` on
the row itself.

## Reasoning

**The question that decides it is "which answers quoted this chunk?"** — and
every version of it: a customer asking what an answer was based on, a deletion
request that must find every artefact derived from a document, a review of what
one passage has been used to claim. Under A that question is a JSON scan across
every generation the workspace has ever made, with no index and no referential
integrity. Under B it is an indexed lookup.

**Referential integrity is the part that cannot be retrofitted.** A chunk id in
a JSON blob is a string. Nothing stops it pointing at a chunk in another
workspace, at a chunk that never existed, or at one deleted last month, and
nothing detects it afterwards. A foreign key makes the first two impossible at
write time. That matters more here than it usually would, because ADR 0053 lets
a citation license a figure — a citation the database will not vouch for is a
permission to state a number.

**Against C:** two stores of one fact with no precedence rule is a bug waiting
for the first divergence, and the divergence would be silent.

**`workspace_id` on the row rather than a join to `generation` inside the
policy.** A policy that joins is a second place isolation can be written
wrongly, and RLS failures are the class this codebase has been burned by
repeatedly — `nexus_app` is `NOBYPASSRLS`, so a wrong policy returns **zero rows
rather than an error**, which reads as an empty table. One local column keyed by
the same GUC as `generation`'s own policy is the shape already proved here.

**`ON DELETE RESTRICT` on `chunk_id` is the choice worth arguing about.**
`CASCADE` would erase the evidence exactly when a chunk is deleted, which is the
opposite of what a ledger is for — the answer would remain, its basis gone, and
nothing would record that it had one. `RESTRICT` means a cited chunk cannot be
hard-deleted, and **that will surprise someone**: a document delete will fail
with a foreign key error rather than succeeding.

That cost is accepted rather than dismissed. The mitigation is that `document`
already soft-deletes, so the ordinary path is unaffected; what `RESTRICT`
blocks is a hard delete, which is precisely the operation that should stop and
ask. `generation_id` cascades, because deleting the answer deletes the thing the
citation is about.

## Consequences

- A new table, RLS enabled **and forced**, verified by reading `pg_class` after
  the migration rather than inferred from it having run.
- Hard-deleting a cited chunk fails. Any future purge path must delete the
  generations first, which is the right order and is now enforced rather than
  remembered.
- `input_snapshot` for an assistant generation holds the question and the refs
  issued, not the chunk ids — refs are opaque and per call (ADR 0055), and a
  chunk id in a stored snapshot is a chunk id in an export.
- The export and deletion paths gain a table. `generation`'s own docstring
  already says they must include it for scope reasons; this adds a second.
- `ordinal` records the order the answer cited them in, so an answer can be
  rendered as it was written rather than in insertion order.

## Revisit trigger

If a purge or retention job finds itself routinely defeated by `RESTRICT` — that
is, if hard-deleting chunks becomes an ordinary operation rather than an
exceptional one — the answer is not to switch to `CASCADE` but to decide what
should happen to an answer whose basis is being destroyed. `SET NULL` with a
`deleted_chunk` marker is the shape that keeps the evidence that a citation
existed, and it should be argued for explicitly against this ADR.
