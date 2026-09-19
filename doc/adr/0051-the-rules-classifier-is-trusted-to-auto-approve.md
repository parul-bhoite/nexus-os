# 0051. The rules classifier is trusted to auto-approve, within the gate it cannot move

- **Status:** Accepted
- **Date:** 2026-09-19
- **Deciders:** Parul
- **Closes:** the first half of `BUILD-STATUS.md` H3 and the symptom in §4.4
- **Related:** invariant I4 (default-deny), `doc/12` P12 (calibration is
  measured, not asserted), D13 (unblocked by this — no model is involved)
- **Affects:** `app/routes/documents.py:_classify_all`

## Context

`_classify_all` hardcoded `classifier_failed=True` on every chunk, so every
upload withheld to L5 and landed in the review queue, and `chunks_indexed` was
structurally always zero. The register described this as "there is no
classifier".

**There is a classifier, and it was already calibrated.**
`app/documents/rules.py:propose` returns a scope, department, sensitivity and
confidence from vocabulary counts and pattern matches.
`tests/test_classifier_calibration.py` carries a 42-sample labelled set and
prints precision and recall per department. It had **no production caller** —
only tests. It was written for this exact call site, whose own docstring said a
classifier "swaps in here without any caller changing", and then nobody swapped
one in.

So the decision was never "build a classifier". It was whether the one already
sitting in the tree is good enough to let content reach a department without a
person approving it.

Measured on that labelled set: **precision 1.00 for all seven departments**;
recall 1.00 for six and **0.50 for operations**; 0.93 overall at confidence
≥ 0.85.

## Options considered

### A. Leave it unwired until a model-backed classifier exists

Nothing can be wrongly published by a classifier that never runs.

It also means the review queue holds 100% of every upload for as long as that
takes. A queue nobody can work through is not a safety control; it is a pile,
and the realistic human response to a pile is bulk-approval without reading —
which is worse than the automation it was standing in for.

**And the queue cannot be worked at all today.** `GET /documents/review-queue`
and `POST /documents/review-queue/{chunk_id}` both exist and are complete,
including the `may_reach_scope` check that stops the queue becoming a
privilege-escalation route. Nothing in `apps/web` calls either — no page, no
component, no client function. That is H4, and it means withheld content is not
"awaiting review" so much as stranded. Option A therefore does not preserve a
human check; it preserves an empty product.

*(Corrected: an earlier draft cited `GET /review` here. That is a different
endpoint — the Company Brain **facts** gate — and not the chunk queue.)*

### B. Wire `propose` in, unchanged

Accept the measured precision, and let the gate do what it was built to do.

### C. Wire it in behind a per-workspace opt-in flag

Safer-sounding, and it adds a setting nobody has asked for to a product whose
whole claim is that it does not ask you to configure your way to correctness.
It also splits behaviour in two, so the queue's contents depend on a flag
somebody set months ago.

## Decision

Option B. `_classify_all` calls `rules.propose(chunk.text)` and passes the
result to the unchanged `classify_chunk`.

## Reasoning

**The decisive point is that the gate, not the classifier, decides what is
visible — and the gate did not change.** `propose` can only *suggest*; every
dangerous suggestion is refused by a rule that predates it:

| `propose` returns | `classify_chunk` does |
|---|---|
| Personal pattern → L5, `PERSONAL`, confidence 1.0 | Review. `REQUIRES_HUMAN` ignores confidence entirely |
| Financial pattern → L4, `FINANCIAL`, confidence 1.0 | Review. L4 is not in `ASSIGNABLE_SCOPES` |
| Department wins by ≥ `CONFIDENT` → L3 + department | **Auto-approve** — the only such path |
| Weak or unrecognised → L5, low confidence | Review. Below `CONFIDENCE_THRESHOLD` |

`propose` never returns L2, so the sole automatic outcome is L3 scoped to one
department, on non-sensitive text, where a single department's vocabulary took
at least 85% of all matches. A wrong answer there is visible to one department
that already holds L3 access — not to the company, and never to the public.

**On the precision figure, honestly.** 1.00 across 42 samples is not a
production number. The rules were written against those samples, so it is
partly self-fulfilling, and 42 is small. It is offered as evidence that the
*shape* is sound — pattern matches beat vocabulary, ambiguity scores low — not
as a measured error rate. The number that would justify more trust is precision
on a **held-out** set nobody tuned against, and that set does not exist yet.

**Why the recall gap does not block this.** Operations at 0.50 means half of
operations content goes to review that need not. That is the failure direction
this product should prefer, and it costs a person some clicks rather than
costing a customer a leak.

**What this rejects.** Option C's flag was tempting and wrong: a safety control
that can be switched off per workspace is a control whose behaviour nobody can
state, and the honest version of "we are not sure this is safe" is not shipping
it.

## Consequences

- Uploaded documents can now reach a department without human approval, for the
  first time. `chunks_indexed` stops being structurally zero.
- **The withheld remainder is still stranded, and this ADR does not fix that.**
  An earlier draft of this section claimed the change "makes the review queue
  workable"; that was wrong and is corrected here rather than quietly deleted.
  There is no review-queue UI (H4), so a chunk the gate withholds today cannot
  be approved by anyone. What changed is the *proportion* that needs one: the
  confident, non-sensitive majority no longer waits on a screen that does not
  exist. **H4 is now the binding constraint on this feature's value, ahead of
  D13** — a classifier that withholds correctly is only half a system while
  nothing can act on what it withheld.
  *(Resolved the same day: `/review-queue` was built, so withheld chunks can
  now be placed or rejected. The paragraph above is kept because the reasoning
  it corrects was published, and because the ordering lesson stands — the
  screen was the binding constraint, not the model.)*
- A classifier mistake is now possible where previously only a human's was.
  Bounded to one department, and `classified_by` records `rules-v1` so every
  decision this version made can be found and re-reviewed.
- No model, no token spend, no D13 dependency, and no new failure mode when the
  language model is unconfigured — the no-model path is unchanged because there
  was never a model on it.

## Revisit trigger

Three, any of which reopens this:

1. **A held-out labelled set exists** and precision on it is below 1.00. Then
   the confidence threshold, the vocabulary, or this decision has to move.
2. **A false auto-approval is reported by a customer.** One is enough — the
   argument above rests on precision, not on recall.
3. **A model-backed classifier lands** (the remaining half of H3). Then
   `classified_by` distinguishes the two, and this ADR governs only the rules
   path. Note the model's own revisit question is different: it can hallucinate
   a department, where the rules can only miscount words.
