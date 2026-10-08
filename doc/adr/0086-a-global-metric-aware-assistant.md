# 0086. A global, metric-aware assistant that narrates figures instead of citing documents

- **Status:** Proposed
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

The product has a built, document-grounded assistant: `POST /dashboards/{department}/ask`
(`app/assistant/ask.py`), which answers from a department's uploaded documents,
citing chunks, shipped dark behind `assistant_enabled`. The ask was for something
broader — a **global, always-available** assistant that answers questions about
the dashboard and Company Brain, **including computed metrics** ("what's my
pipeline total?", "what's our performance score?").

Three constraints shaped the design, two of them discovered during build:

1. **I1 — never invent a number.** `app/assistant/` is forbidden by
   `test_assistant_boundary` from importing `calculators/`; its numeral guard
   permits only figures quoted from cited document passages.
2. **The citation table is FK-bound to documents.** `generation_citation` has
   `ON DELETE RESTRICT` foreign keys to `chunk.id` and `document.id` (ADR 0057).
   A computed metric or a stored insight has no chunk to cite — so "state the
   pipeline total and cite it" has nowhere to record the citation. Synthetic
   passages are impossible.
3. **Governance.** Turning the assistant on (A12, `doc/20`) has eval
   preconditions and is a human decision.

## Decision

**A metric answer is narration over a figure bundle — its provenance is the
generation row's trace, not a chunk citation.** This is the path
`app/grounding/answer.py` already uses to state a *computed* number on a tile
I1-safely: the figure comes from `calculators/` (or the insight store), the model
phrases it, and `grounding/pipeline.run` rejects any numeral the grounding did not
supply. The new composition `app/grounding/qa.py` widens that from one figure on
one tile to a bundle (stored insights + Company-Brain facts + live crawl-audit
figures) answering a free-text question.

- **It lives in `app/grounding/`, not `app/assistant/`** — assembling the bundle
  reads `calculators/` and the insight store, which the assistant boundary
  forbids. The strict document assistant is left untouched (its evals do not
  move).
- **I1 is kept exactly as narration keeps it.** `pipeline.run` permits only the
  figures in `Computed.values` plus the numerals of the grounding text
  (`also_permitted`); a figure the bundle did not supply is **refused whole**,
  not corrected. Proven in `test_assistant_global_db.py` (a fabricated `97` is
  refused).
- **No chunk citations.** Provenance is the `generation` row's
  `calculation_trace`/`input_snapshot` — the labels of what was assembled. The
  response carries `grounded_on`, not citations; a computed figure is not a
  document.
- **`POST /assistant/ask`**, global (cross-department, scoped by the caller's
  `ScopedSession`), **dark**: 404 while `assistant_enabled` is off, exactly as the
  per-department endpoint. Nothing here flips the flag.
- **A floating widget** on every signed-in page (`AppShell`), rendered only when
  `assistant_enabled` (surfaced on the `/dashboards` payload). While dark, nothing
  appears.

## Reasoning

Routing metric answers through narration rather than the document assistant
resolves all three constraints at once: it needs no change to the FK-bound
citation table, it keeps `app/assistant/` calculator-free, and it reuses the one
I1 guard the product already trusts. It is also the honest model of the two kinds
of grounding — a *document* answer can point you at the passage to read, a
*computed* answer can only show you the figure and how it was derived, and
conflating them (a synthetic passage with a dead link, or a fabricated chunk row)
would have been dishonest in exactly the way the citation model exists to prevent.

Building dark was non-negotiable: the A12 eval review (red-team, hand-judged
citations) is a human gate, and a phase that flipped the flag would bypass it.

## Consequences

- Two assistants, one surface vocabulary: documents cite chunks
  (`/dashboards/{department}/ask`); figures narrate with a trace
  (`/assistant/ask`). They never blend a computed number into a document citation.
- The global assistant answers from insights + Brain facts + **every computed
  figure the caller may reach**: the crawl audit, the CRM pipeline
  (`compute_from_deals`) and the operations counts and rates
  (`compute_from_ops`, `compute_rate_from_ops`). `qa._assemble` unifies them
  through each computation's `(computed, label)` pair, and **filters by
  `scope.may_reach_department`** — the same filter the dashboard applies to its
  tiles, so the assistant never grounds on a figure the reader's own dashboard
  would not show. Compositions (`score_drivers`, `todays_priorities`) are
  excluded: they rank or explain other figures rather than carrying a headline
  number for the guard to permit. A refused rate (nothing priced, not confirmed)
  is skipped rather than grounded on a percentage that is not shown.
- The feature is **code complete, dark**. Live answer quality is the A12 eval's
  concern; what is proven now (with a `ScriptedProvider`, no real model) is the
  guard and the flow: a supplied figure may be stated, an invented one is refused
  whole, a model "no" becomes an authored refusal, and an empty bundle refuses
  without a model call.

## Revisit trigger

Reopen if: the two endpoints should merge into one that routes by question kind
(needs a classifier, itself model-ish — deferred deliberately); the bundle grows
large enough that assembling every figure per question is too costly (select by
question relevance); or A12 flips the flag and live evals demand a change to the
grounding assembly or the guard.
