# 0053. A figure is permitted only by the passage the answer cited

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements:** `doc/20` A2
- **Depends on:** ADR 0052 (the assistant answers from documents only)
- **Affects:** `app/assistant/grounding.py`, `evals/test_assistant_grounding.py`

## Context

I1 says every number is fetched or computed in code. `grounding/pipeline.py`
enforces it for narration by comparing every numeral in the model's prose
against the calculators' output — `invented_numbers`, and its `also_permitted`
escape hatch for grounding strings the caller supplied.

ADR 0052 makes the first assistant answer from retrieved passages instead of
from calculators. There are no calculated values at all, so the permitted set is
empty and **every legitimate figure has to arrive through `also_permitted`** —
which is to say, out of a document the customer uploaded.

That leaves one question the pipeline does not answer: when a question retrieves
five passages and the answer cites one, which of the five license a figure?

## Options considered

### A. Every retrieved passage

Anything in the material we put in front of the model. Simple, and it is what
`numerals_supplied` does at its other call site.

### B. Only the passages the answer cited

Narrower. An answer must point at the passage a figure came from before it may
state it.

### C. The prose is checked against the passage nearest the citation marker

Most precise in principle. Needs the model to interleave citations reliably, and
a parser for a format the model controls.

## Decision

Option B. `check` builds the permitted set from the **cited** subset of the
passages that were sent, and a figure appearing only in an uncited passage costs
the whole answer.

## Reasoning

**The deciding question is what the reader does next.** A citation exists so
somebody can open it and check. Under option A an answer can state 43,217, cite
a passage about the Berlin office, and be correct by the guard's standard while
a reader who follows the only citation offered does not find the number there.
That is a citation that survives the check without doing the one job it has, and
`AssistantAnswer`'s own docstring already refuses to let citations be
decoration.

Option A is also the weaker guard in exactly the situation retrieval creates:
the more passages a query returns, the more numerals it permits, so the rule
loosens precisely as the model's opportunity to confuse two documents grows.

Option C was rejected on cost, not on principle. It depends on the model
emitting a citation format faithfully, which is the thing under suspicion — a
guard whose precision rests on the cooperation of the output it is checking is
not a guard. B gets most of C's benefit from a structure the model cannot fake,
because the citation list is validated against the retrieval set independently.

**The accepted cost** is that an answer synthesising across two passages must
cite both. That is a real restriction and it is the correct one: an uncited
source is a source the reader cannot check.

## Consequences

- An answer with no citations has no permitted numerals, so any figure in it is
  an invention. Deliberate, and stated in `AssistantAnswer`'s docstring.
- A model that cites sparsely will have correct answers rejected. The remedy is
  the prompt (`doc/20` A4), never widening this rule.
- `permitted_numerals` wraps `numerals_supplied` rather than reimplementing the
  numeral regex, so "what counts as a figure" has one definition product-wide.
- **The guard does not check faithfulness.** A purely qualitative answer that
  misrepresents its passage has no numeral to catch and passes. That limit is
  named in the eval that demonstrates it, and closing it needs A5.

## Revisit trigger

If the prompt work in A4 cannot get citation coverage high enough to keep the
rejection rate tolerable — measured, not guessed, over the eval set — the
decision to revisit is between adding C's precision and relaxing to A. Relaxing
to A should be argued against the Berlin-office case above, which is the
concrete thing it gives up.


## Addition, 21 September 2026 — amended by ADR 0062

**Not a reversal; one class this rule caught wrongly.** A numeral the *customer
typed into the question* was indistinguishable here from one the model invented,
so *"who can approve a purchase of 3,000 rial?"* over a band of *"500 to 5,000"*
was refused for stating 3,000 — the product calling the reader's own figure
fabricated. Found by A9's first live run: 1 of 26 answerable questions.

**ADR 0062** permits a question's numerals, but only for an answer that cites at
least one passage, and records the echo on the `generation` row. Everything this
ADR says about arithmetic, conversion, rounding and aggregation is unchanged.
