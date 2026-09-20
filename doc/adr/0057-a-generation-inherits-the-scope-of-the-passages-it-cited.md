# 0057. A generation inherits the scope of the passages it cited

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements:** `doc/20` §5 Q6, planned as "ADR E". **Numbered 0057, not the
  0056 the plan proposed** — the numbering shifted during A2 and A3.
- **Blocks:** `doc/20` A4
- **Depends on:** ADR 0056 (citations are rows)
- **Affects:** migration `0040`, `app/retrieval/chunks.py`,
  `app/assistant/ask.py` (A6)

## Context

Migration `0023` states the rule this ADR applies: *"`input_snapshot` inherits
its inputs' scope tag and retention, and that is the load-bearing part. A
snapshot of L4 facts is itself L4: storing the question's inputs in a table with
weaker rules than the facts they came from would be a side door around the whole
scope lattice — read the restricted number once, and it lives on unrestricted
forever."*

For narration, `context.scope_key_for` derives that tag from the departments
whose facts went into the context, and `context.py` argues why it is the inputs
and not the asker: *"a snapshot of Finance facts is a Finance artefact whoever
asked for it, and tagging it with the asker's role would make an Owner's
snapshot of the same inputs less sensitive than a manager's."*

The assistant's inputs are retrieved chunks, and each carries its own `scope`
and `department` on the row — that is what makes the retrieval predicate work at
all (I3). But **`Passage` does not expose them.** It carries
`id, content, document_id, source_page, source_label`, so a caller holding a
passage cannot tell whether it was L2 or L4.

Separately, `retention_until` has existed on `generation` since `0023` and
**nothing has ever written it.** Every generation row in the database has a null
retention, which means the column documents an intention rather than enforcing
one.

## Options considered

### A. Derive `scope_key` from the caller's departments

What `assemble` does today. No schema change, and `ScopedSession` already has
the departments.

### B. Derive it from the cited passages, adding `scope` and `department` to
`Passage`

Two more columns on a `SELECT` that already runs through the predicate.

### C. Derive it from every retrieved passage, cited or not

The full set the model saw, which is arguably what was exposed to the model
rather than what reached the reader.

## Decision

Option B. `Passage` gains `scope: Scope` and `department: tuple[Department, ...]`,
and the `generation` row's `scope_key` is computed from the passages the answer
**cited**.

**And `retention_until` is written**, for the first time, on assistant
generations.

## Reasoning

**Against A, in the words migration 0023 already uses.** The caller's
departments describe who asked, not what was read. A Contributor in Finance and
an Owner can retrieve the same L4 passage; tagging the Owner's generation less
restrictively would make the artefact's sensitivity depend on the reader, which
is the exact inversion `context.py` rejects. It also fails the concrete case:
a caller holding four departments who retrieves one L2 passage would have their
answer tagged as though it touched all four.

**Against C, narrowly.** The retrieved-but-uncited passages were shown to the
model, so there is a real argument that the generation was exposed to them. It
is rejected because `input_snapshot` records what was retrieved — the exposure
is on the row either way — while `scope_key` governs **who may read this
artefact later**, and what the artefact actually contains is the cited material.
Tagging by the wider set would steadily inflate every generation's scope toward
the most restrictive thing retrieval happened to surface, until the tag stopped
discriminating.

**Why this does not touch I2/I3.** Two columns are added to a `SELECT` whose
`WHERE` is unchanged. `search` keeps its signature, takes no `user_id`, and the
predicate stays inside the query. The fields are read *from rows the predicate
already returned*, so they cannot widen what comes back — and
`evals/test_permissions.py` is extended to assert exactly that: a Contributor's
passages carry only scopes they may read. A field that could disagree with the
predicate would be a second source of truth about permission, which is why the
assertion is a permission eval rather than a unit test.

**On `retention_until`.** A column named for a guarantee and never written is
worse than no column: it reads as though retention is handled. Writing it here —
rather than in a later step "once retention is designed" — is what stops the
assistant adding a fourth year of unretained rows to a table already carrying
three. The value is not decided by this ADR beyond requiring that it be
non-null; A6 sets it and `doc/20` A4's acceptance asserts it.

## Consequences

- `Passage` grows two fields. Every construction site must supply them, which
  the type checker enforces.
- `scope_key` for an assistant generation is the **maximum** scope across cited
  passages plus the union of their departments — a single L4 citation makes the
  whole answer L4, which is correct and deliberately blunt.
- An answer citing nothing cannot happen (ADR 0053 makes it a refusal), so there
  is no "cited nothing" case to define a tag for. A refusal's generation row
  takes the scope of what was retrieved, because a refusal is an artefact about
  content the caller could read.
- `retention_until` becomes non-null on new assistant rows and stays null on
  every historical row. Any query reading it must handle both, and a backfill is
  deliberately **not** part of this — inventing a retention date for a row whose
  policy did not exist when it was written would be fabricating a fact.
- The scope lattice now appears in a third place: the chunk row, the retrieval
  predicate, and the generation tag. They must agree, and the permission eval is
  what proves they do.

## Revisit trigger

If `scope_key` proves too blunt — most likely when a common question cites one
L4 passage alongside four L2 ones and the whole answer becomes invisible to
colleagues who could have read four fifths of it — the correction is per-citation
scope on `generation_citation` (the rows exist, per ADR 0056) with the
generation tagged at the minimum readable set, not loosening the maximum rule
here.
