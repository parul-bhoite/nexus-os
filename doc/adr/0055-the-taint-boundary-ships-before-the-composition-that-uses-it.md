# 0055. The taint boundary ships before the composition that uses it

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements:** `doc/20` A3, by pulling A6 step 5 forward
- **Depends on:** ADR 0052 (the assistant answers from documents only)
- **Affects:** `app/assistant/fence.py`, `app/assistant/ask.py` (A6, unwritten),
  `evals/test_injection.py`

## Context

`doc/20` sequences the assistant as A0–A12. **A6** owns `ask.py`, the
composition, and its step 5 is *"`wrap_untrusted(DOCUMENT, p.content, ref=…)`
and `Turn.read(…)` for each"* — the point at which retrieved passages taint the
turn. **A3**, three steps earlier, is the injection evals, and its stated
centrepiece is `test_every_retrieved_passage_taints_the_turn`: drive the
composition with three passages, assert the `Turn` has three blocks and is
tainted, so *"a future edit that forgets `Turn.read` fails here"*.

A3 is blocked only on A2. So the eval that guards the taint was scheduled to be
written three steps before the code that performs it.

Writing A3 against a harness defined in the eval file satisfies the plan
literally. It also makes that test assert **that the harness calls the function
the harness calls** — green forever, and silent on the day `ask.py` is written
without the loop. That is the failure this build has already made twice in a
different costume: `evals/test_injection.py` reading 10/10 while asserting only a
dataclass, and `BUILD-STATUS.md` concluding from it that the injection gate was
open.

## Options considered

### A. Harness in the eval file; A6 writes the real loop later

Follows the plan's sequencing exactly. The taint eval is decorative until A6,
and nothing marks the date it stops being decorative.

### B. Defer A3 until after A6

Honest, and costs nothing in correctness. It also means A4, A5 and A6 — the
migration, the prompt, and the composition that puts customer text in front of a
model — are all written with no injection eval in the repository, which is the
one ordering `doc/12` P20 explicitly refuses.

### C. Ship the taint boundary now as its own module, and have A6 call it

`app/assistant/fence.py`: `prepare(passages) -> Grounding` performs the fencing
and the taint and issues the refs; `resolve` maps cited refs back. Pure, no IO.
A3 drives it. A6 calls it instead of writing step 5.

## Decision

Option C. `fence.py` exists before `ask.py`, and **A6 calls it rather than
owning that step.**

Scope is deliberately narrow: only step 5 moved. Embedding, retrieval,
`pipeline.run`, the ledger and the citation rows remain A6's.

## Reasoning

**A guard is only worth what it is attached to.** The decisive question was not
where the code reads best but what the test would still catch a month later.
Under A, the answer is nothing — the eval and its subject are the same object.
Under C the eval names a module a future author must edit to break it.

**Against B**, the cost is ordering: P20's rule is that the injection evals come
first, and B writes the three most dangerous steps with none in the tree. C
keeps the plan's order and pays a small structural price for it.

**The price, stated plainly.** A step's responsibility moved before that step was
written, which is a thing to be suspicious of — done casually it is how plans
dissolve into whatever was convenient. It is acceptable here because the moved
unit is pure, has no dependency on anything A6 adds, and would have been
extracted anyway the first time a second caller needed a fenced passage.

**Opaque refs are not a new decision.** `doc/20` A6 already fixes *"refs are
opaque and per-call, never a chunk id"*, and the reason is recorded there: a
chunk id in the prompt is a chunk id in the model's output and eventually in a
log. This ADR moves where that rule is implemented; it does not re-decide it.
The rule does gain teeth it did not have — because the ref→passage mapping is
held in `Grounding` rather than parsed out of the answer, a ref the model
invented resolves to nothing instead of to a row.

## Consequences

- A6 is smaller than `doc/20` describes, and its step 5 reads as a call.
  `doc/20`'s A3 section records this so the discrepancy is not read as drift.
- The taint guarantee is enforced by a test against shipped code from today
  rather than from A6.
- **A6 still owes the other half.** These evals prove the guards hold when a
  payload reaches them; they do not prove the shipped route calls the guards.
  A6's acceptance test is where that lands, and the same gap exists at A2's
  boundary.
- `resolve` returning unknown refs as a *value* rather than dropping them makes
  a fabricated citation a refusal. Dropping them quietly was the tempting bug,
  because the answer usually still reads fine with one citation removed.
- One more module inside `app/assistant/`, already covered by the import
  allowlist in `tests/test_assistant_boundary.py`.

## Revisit trigger

If A6 finds it cannot use `prepare` as it stands — most likely because the real
prompt needs the passages interleaved with something rather than as one block —
then the extraction was premature and the right correction is to inline it back
into `ask.py` and rewrite the taint eval against `ask.py` directly. **What must
not happen is `prepare` surviving as a wrapper nothing calls**, with the taint
eval still pointed at it while the shipped path does its own fencing. That is
option A arrived at by accident, and it would be invisible.
