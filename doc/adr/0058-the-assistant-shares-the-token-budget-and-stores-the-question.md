# 0058. The assistant shares the token budget, and the question is stored

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements:** `doc/20` §5 Q5, planned as "ADR D". Numbered 0058, not the
  0055 the plan proposed — the numbering shifted during A2–A4.
- **Blocks:** `doc/20` A7
- **Affects:** `app/assistant/budget.py`, `app/assistant/ask.py`,
  `app/config.py`

## Context

Two questions, both left open by `doc/20` and both about the same table.

**First, whose allowance does asking spend?** `Settings` carries
`tenant_daily_token_budget` (2,000,000) and `user_daily_token_budget` (200,000),
and `ledger.budgets_for` computes what is left from the `generation` rows of the
day. Narration and onboarding already draw on them. The assistant is the first
feature where a human decides how often it runs, so it is the first that can
exhaust a budget deliberately.

**Second — and this is the harder one —** may we store the question?
`doc/20` says plainly: *"A founder's question can be more sensitive than the
answer — 'how much are we paying Ahmed' — and it is free text the customer
typed. Storing it makes the ledger readable; not storing it makes a disputed
answer unreconstructible. This plan does not choose."*

## Options considered

### Budget

**A. Share the existing two budgets.** No new setting. Asking competes with
narration for the same allowance.

**B. A third budget, `assistant_daily_token_budget`.** Isolates the two, so a
busy assistant cannot blank the dashboard's tiles.

### The question

**C. Store it in `input_snapshot`.** The ledger answers *"what was asked and
what did we say?"* — the question a dispute is actually about.

**D. Store a hash, not the text.** Deduplication and rate analysis survive;
the content does not.

**E. Store nothing.** Maximum privacy. A disputed answer cannot be
reconstructed even by the customer asking about their own answer.

## Decision

**A and C.** One shared budget, and the question is stored as text in
`input_snapshot`.

Both are narrowed by things this ADR also fixes:

- A **per-question ceiling** refuses before the call when the assembled
  passages would exceed it, so one pathological question cannot spend a day's
  allowance in a single request.
- A **per-user rate limit** on the ask bucket, returning 429 with
  `Retry-After`.
- `input_snapshot` holds the question, the chunk ids, the ref mapping, the
  taint flag and the passage count. **Never passage text.**

## Reasoning

**On the budget: B protects the wrong thing.** The argument for it is that a
busy assistant should not blank the tiles — but a separate budget does not stop
that, it only changes which number runs out first, and it adds a third figure
nobody can reason about when the bill arrives. The thing that actually bounds
spend is the per-question ceiling and the rate limit, both of which B would
still need. A also keeps one answer to *"how much can this workspace spend
today?"*, which is the question an operator asks.

**On the question, C over E.** The decisive case is a customer disputing an
answer. Under E the ledger holds the passages cited and the prose returned, and
cannot say what was asked — so the one record that exists cannot establish
whether the answer was responsive, which is usually what the dispute is about.
A ledger that cannot settle the disputes it exists for is an expensive
audit trail that helps nobody.

**C over D.** A hash gives up the content and keeps almost none of the benefit:
it cannot be read by the customer, cannot be read in support, and the
deduplication it enables is not a problem this product has. It is the option
that feels careful and buys nothing, which is worth naming as a failure mode
rather than rejecting quietly.

**The sensitivity objection is real and is answered by where it is stored, not
by whether.** *"How much are we paying Ahmed"* is sensitive — and
`generation.scope_key` and `retention_until` exist precisely so a stored
artefact carries the rules of what it touches. ADR 0057 makes the assistant's
rows inherit the scope of the passages cited, and a question about Finance
retrieves Finance passages, so the row is tagged `L3:finance` and is invisible
to somebody who cannot read Finance. The question is protected by the same
lattice as the answer.

**The one case that is genuinely not covered**, and is accepted: a question
whose *text* is more sensitive than anything it retrieves — asked about a topic
the workspace has no documents for, so the row is tagged by an empty or
company-wide scope and is readable more widely than the question deserves. That
is the revisit trigger below.

**Passage text stays out of `input_snapshot` regardless.** `doc/06` §9 calls it
*"a second copy of customer content"* carrying the same scope, retention and
export obligations. On what will be the highest-frequency path in the product,
writing passage bodies there duplicates the corpus into a table with a different
lifecycle — the deletion request that removes a document would leave its text
behind in a thousand generation rows. The chunk ids are already recorded
properly, in `generation_citation`, behind a foreign key.

## Consequences

- No new setting. `budgets_for` is used unchanged.
- A busy assistant **can** exhaust the workspace's day and leave narration
  refusing with `BUDGET_EXHAUSTED`. That is visible, it is worded, and it is
  preferable to a second budget that hides the same event behind a different
  name.
- A per-question ceiling has to exist in code, because the retrieval limit
  alone does not bound passage length.
- The ledger becomes readable — and therefore becomes something an export
  request must include and a deletion request must reach. Both already apply to
  `generation` for `scope_key` reasons.
- A refusal's row stores the question too. That is deliberate: *"what did they
  ask that we could not answer?"* is the single most useful question this table
  can answer about whether the assistant is working.

## Revisit trigger

Reopen on the uncovered case above: if refusals accumulate whose question text
is sensitive and whose `scope_key` is company-wide — the shape of *"we have no
documents about that, and now the asking is on the record"* — then the fix is to
tag a row by the **greater** of the cited scope and a floor derived from the
asker, not to stop storing the text.

Reopen the budget half if a workspace's tiles are seen going `BUDGET_EXHAUSTED`
because of assistant traffic. That is the event option B was for, and seeing it
once is better evidence than the argument above.
