# 0061. A9's deterministic half measures retrieval, because its other counts need a model

- **Status:** Accepted
- **Date:** 21 September 2026
- **Deciders:** Parul
- **Implements / departs from:** `doc/20` A9
- **Affects:** `evals/test_assistant_measurement.py`,
  `evals/fixtures/assistant/`, and what A12 reads

## Context

`doc/20` A9 asks the measurement half for three counts over an authored fixture
set: how many questions are **answered**, how many are **refused that should
have been answered**, and how many are **answered with a citation that does not
support the claim**. It also asks for two halves — deterministic in CI, live
behind a marker — and says the third count is hand-judged *"because nothing
automates it"*.

Building it surfaced a problem the plan does not address: **none of the three is
computable in the deterministic half.** All three are properties of an answer,
and there is no answer without a model. The deterministic half has a
`ScriptedProvider`, which returns whatever the test hands it — so counting
outcomes over it would count the fixture author's choices, not the product's
behaviour. A green "27 of 33 answered" produced that way would be a fabricated
number wearing a measurement's clothes, in the file whose whole purpose is to
tell A12 whether the assistant is good enough to show a founder.

## Options considered

### A. Script the provider and report the three counts anyway
Runs in CI, produces the numbers the plan names. They measure the script.

### B. Move all three to the live half; the deterministic half asserts only
Honest, and leaves nothing running in CI — so a retrieval regression between
live runs is invisible until somebody pays for a model call to find it.

### C. Deterministic half measures **retrieval**; the three counts move live
Reports recall@N and rank over the same fixture set, with no model and no key.
The three original counts are produced by the live half.

## Decision

Option C. The deterministic half answers one question — **did the document
holding the answer reach the model at all?** — and asserts a floor on it. The
answered / wrongly-refused / wrongly-cited counts belong to the live half, the
third still hand-judged.

## Reasoning

**The three counts rest on the thing C measures, and are unreadable without
it.** A refusal has two causes that look identical on screen: the passage never
arrived, or it arrived and the model did not use it. The first is a retrieval
defect, the second a generation defect, and they have nothing in common — one
is fixed in `retrieval/`, the other in a prompt. A "wrongly refused" count that
does not separate them tells A12 a number and hides which of two teams should
act on it.

**Against A, and this is the decisive objection.** This product's central claim
is that it never states a figure it cannot trace. A measurement file that
reports a confident quality score derived from its own fixtures would be the
same failure, committed by the thing built to prevent it — and it would be more
damaging than an invented number on a tile, because A12 is a decision about
whether to expose the feature at all.

**Against B**, narrowly: retrieval is the half that *can* regress silently
between live runs. `retrieval/` is edited far more often than the prompt, and a
recall collapse would otherwise surface as a mysterious rise in refusals, weeks
later, in a live run somebody paid for.

**The floor is set below the measurement on purpose.** First run: recall@8
31/31, recall@3 28/31, rank-1 25/31; the assertion is 70%. A floor at the
measured value turns any fixture addition into a failure and teaches people to
lower it, which is how a ratchet becomes a rubber stamp.

## Consequences

- A12 reads **four** numbers, not three, and the fourth qualifies the others.
- CI keeps a retrieval regression test that needs no key — but **does** need an
  embedder, and skips loudly without one rather than reporting a recall figure
  over fabricated vectors.
- The fixture corpus is exercised twice, by two halves that measure different
  things over the same questions. Both must be kept in step; a question added
  without a document is caught by a test in the same file.
- `doc/20` A9's wording is now inaccurate about the deterministic half. It is
  annotated rather than rewritten, so the plan's intent and this departure are
  both visible.

## Revisit trigger

If a live run ever reports **wrongly-refused questions whose documents recall
says were retrieved at rank 1–3**, this split has stopped explaining anything:
retrieval is fine and the refusals are elsewhere, so the deterministic half is
measuring a thing that no longer predicts the outcome. At that point the useful
deterministic measurement is probably faithfulness against a fixed set of
passages, which needs a model and therefore a different structure.

Revisit sooner if `PASSAGE_LIMIT` changes: recall is measured at N=8 because
that is what `ask.py` uses, and a figure at a different N describes a product
nobody ships.
