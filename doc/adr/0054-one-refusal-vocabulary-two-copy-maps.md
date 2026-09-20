# 0054. One refusal vocabulary, one copy map per surface

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements:** `doc/20` A2
- **Affects:** `app/grounding/pipeline.py`, `app/domain/narration.py`,
  `app/assistant/grounding.py`, `tests/test_refusal_vocabulary.py`,
  `tests/test_narration_copy.py`

## Context

`UnavailableReason` names why there is no answer, and `domain/narration.py` maps
each member to the sentence a reader sees. `tests/test_narration_copy.py` held
that map to four rules, the strictest of which is stated in its own docstring as
*"the whole point of this file"*: **every sentence must mention the score, the
figure or the number.**

That rule is not stylistic. A narration refusal always renders directly beside a
figure that `calculators/audit.py` computed in pure Python with no model
involved. "Something went wrong" beside *45 out of 65* makes a reader distrust
the 45 — so each sentence has to leave the figure explicitly standing.

`doc/20` A2 adds two reasons the assistant produces: `NO_PASSAGE` and
`UNCITED_CLAIM`. **An assistant refusal has no figure beside it.** It is a chat
bubble. Satisfying the rule would mean writing copy that reassures the reader
about a score that is not on their screen.

So the plan's instruction — add two members with their `sentence_for` entries —
could not be carried out as written. Either the rule breaks or the copy is
nonsense.

## Options considered

### A. Two enums, one per surface

Clean separation, no shared constraints. Both still write to
`generation.unavailable_reason`, which is a single `text` column.

### B. One enum, one map, relax the score rule to the reasons it fits

Smallest diff. The rule becomes conditional inside the test.

### C. One enum, one copy map per surface, totality split and reasserted

`NARRATION_REASONS` and `ASSISTANT_REASONS` each get a total map; a separate
test asserts the two together cover the enum.

## Decision

Option C. The vocabulary is shared; the copy is per surface. `sentence_for`
**raises** when called with the other surface's reason rather than returning
something plausible.

## Reasoning

**Against A: one text column, two enums.** `generation.unavailable_reason` is
`text` with only a non-empty check, so nothing at the database level would stop
`no_passage` and `NoPassage` landing in the same column from two independent
enums. Every later query counting refusals would be quietly wrong about one of
them, and quietly is the operative word — there is no error, just a number that
is too low. One vocabulary is what makes the column answerable.

**Against B: it deletes the guarantee it was meant to preserve.** Relaxing the
score rule inside `test_narration_copy.py` leaves a single map where a new reason
gets *a* sentence and nobody is forced to say which screen it appears on. The
totality that made "a reason with no copy" impossible becomes totality over a
map somebody can add anything to.

Option C keeps both properties: a reason with copy on no surface fails
`test_refusal_vocabulary.py`, and a reason on the narration surface still faces
the full score rule. What is lost is the ability to add a reason without
deciding where it renders — which is a question its author should be answering
anyway, so making it mandatory is a gain.

**Why raise rather than fall back.** Returning the other surface's sentence is
the failure mode that survives review: it renders, it reads fine, and it
describes a screen the reader is not looking at. `INVENTED_NUMBER` is the
concrete case — it occurs on both surfaces, and narration's wording ends *"The
score above is unaffected"*, which is true on a tile and false in a chat bubble.
The two sentences are asserted to differ.

## Consequences

- Adding a reason now requires assigning it to a surface and writing copy there.
- `sentence_for` has a partial domain in both modules, and each raises with a
  message naming the other module.
- `INVENTED_NUMBER` is worded twice. That duplication is the point of the split,
  not an oversight, and a test pins the two apart.
- `test_narration_copy.py`'s opening claim — *"seven refusal reasons, and a real
  number is on screen beside every one of them"* — is true again, where it was
  about to become false.
- Reasons the assistant *runtime* produces (absent model, spent budget, disabled
  skill) have no assistant copy yet. `ASSISTANT_REASONS` is deliberately the
  three grounding verdicts only; the rest arrive with the code that emits them,
  rather than being written now against a screen nobody has seen.

## Revisit trigger

If a third surface appears — an emailed digest, an export — three maps is one
too many and the shape to reach for is a reason plus a rendering context, chosen
once. Two surfaces do not justify that machinery; four would.
