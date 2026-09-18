# 0044 — One join between two question surfaces, and it is partial

**Status:** Proposed — three questions in `doc/16` §11 are open and block acceptance
**Date:** 18 September 2026
**Context:** `doc/08` §12 item 1, which names this gap and defers it here. Design in `doc/16`.
**Relates to:** ADR 0019 (two renderers, one catalogue), ADR 0021 (a generated question names a declared field), ADR 0020 (the bank), ADR 0030 (coverage is counted by who is blocking)

## Context

The same operating facts are collected by two surfaces that write to two tables in
two key spaces.

`domain/question_bank.py` holds 29 questions, five per department across six, each
declaring the capability that reads it. Its renderer is the department block; its
answers land in `onboarding_answer`, keyed by the bare bank key, carrying a
department, a scope and an `answer_state`.

`ai/runtime/fields.py` holds 35 `FieldSpec`s. Its renderer is the chat interview;
its answers land in `fact`, keyed by the dotted catalogue key, carrying provenance,
precedence and supersession — and **no department, no scope, no review state**.

The only link between them is `FieldSpec.question_key`, a string naming a bank
question. One test proves the names resolve. One read site — `answered_questions`
in `routes/dashboards.py` — uses it, to stop the counter telling a founder they
have not answered something they answered in conversation.

That fixed the counter and left the consumer. `Capability.consumes_facts` holds
**bank** keys, inverted from the bank at import. `grounding/context.assemble` puts
promoted facts into the workspace-wide `facts` group under **catalogue** keys. So
`facts_for` can never match one, and it omits a missing key rather than defaulting
it — correctly.

**The current state is therefore worse than the bug it fixed.** The founder is no
longer named as the blocker (ADR 0030) for a fact the capability still does not
have, and nothing on any screen says so. The old failure was visible. This one is
not.

Two further facts shape any fix:

- `fact` (migration 0022) has workspace-only RLS and no scope column, while every
  `fact.*` department field is declared `scope = 3`. The key-space mismatch is
  currently the *only* thing preventing a cross-department read of an L3 interview
  answer. Joining the spaces naively opens it.
- The interview routes carry `CurrentScope` and CSRF and no role check, so a
  Contributor's interview answer is promoted as binding — routing around
  `state_for_answer` (Q31/D22), which exists precisely so that somebody restricted
  to their own records does not decide what is true for a department.

## Options considered

### A. `question_key` becomes a validated bidirectional link; one module owns the translation
`FieldSpec.question_key` stays where it is. A pure domain module translates both
ways. `answered_questions` delegates to it, and `context.assemble` uses it to
surface promoted facts **under their bank key, inside
`department_facts[spec.department]`** — so `consumes_facts` resolves unchanged and
the existing `_reachable_departments` filter does the department scoping. No
migration. Coverage is 19 of 29 and stays there.

### B. The interview dual-writes into `onboarding_answer`
One store for the counter, one key space, no translation. Costs two rows per
answer with no rule about which wins; `onboarding_answer` has no supersession, so a
re-run appends; and the write has to be taught the review gate, the scope tag and
the department that `fact` does not carry.

### C. Collapse the two catalogues into one
The literal reading of ADR 0019's "two renderers, one catalogue". The two carry
genuinely different fields — `prompt`, `why`, `consumed_by`, `options`, `stage`
against `intent`, `scope`, `answer_shape`, `fallback_question`, `only_you_know` —
and a merged record is the union with most fields empty most of the time.

### D. Do nothing; revert the counter to reading `onboarding_answer` only
Restores the visible failure: a founder who answered everything is asked again.

## Decision

**Option A.** The join stays on `FieldSpec.question_key`, becomes validated in both
directions, moves into one domain module, and is applied at the consumer as well as
at the counter.

**Promoted facts are translated into the bank's key space, never the reverse.**
Inverting the other way would mean rewriting every `consumed_by` in the bank and
every `consumes_facts` in the registry, for no gain — the bank's names are already
the id space `doc/13` chose and the registry validates at import.

**The bridge is partial by design, and the numbers are part of the decision.**

- **19** bank questions have a `fact.*` counterpart and are bridged.
- **10** have none and correctly stay outstanding. Three of those ten —
  `lost_to`, `watched_competitors`, `success_in_twelve_months` — are the same fact
  as `brain.competitors` and `brain.goals`, with wording lifted verbatim between
  the two files. They are **not** bridged here: brain fields promote to
  `company_brain` columns rather than `fact` rows, so `question_key` cannot reach
  them. That is a second mechanism and it is deferred, not overlooked.
- **3** catalogue fields — `fact.executive.*` — have no bank question, because the
  bank has six departments and no executive block. They must never mark one
  answered.

Anyone reading "the surfaces are bridged" as parity will read ten correct
"outstanding" lines as a defect, which is why the split is in the decision rather
than in a footnote.

**The bridge reads `FieldSpec.department`, never the answerer's
`stated_department`.** The field's department is a structural property of a file
under review. `askable_fields(department)` keeps steering what is *offered*, which
is the whole reason it is allowed to read a self-reported value; nothing in this
decision lets that value influence what is *readable*.

### What this decision does not settle

Three questions are Parul's and hold this ADR at Proposed. They are stated with
options and a recommendation in `doc/16` §11:

1. **Where the department filter goes** when the key spaces join — the read-time
   filter in `context.assemble` (recommended, no migration), or `department` and
   `scope` columns on `fact` with an RLS predicate.
2. **Whether an interview answer closes the block's question or pre-fills it.** A
   product preference, not a technical fact.
3. **Whether an interview answer may bind a department fact at all**, given that
   the interview routes have no role check and `state_for_answer` is not applied.

Question 3 is the one with a security shape and it cannot be answered here: it
turns on whether a Contributor is expected to run the interview, which is product
intent rather than something the code states.

## Consequences

- **The counter and the consumer stop disagreeing** for the 19 bridged questions. A
  tile can say *"you told us"* about an answer given in conversation, with a
  `source_ref` that opens the session transcript.
- **`grounding/context.assemble` is edited**, and it is the single grounding path
  for every capability and every narration. A defect there is company-wide and
  presents as wrong prose beside a right number. The cross-department negative
  assertion is written before the positive one for that reason.
- **The scope of an L3 interview answer becomes enforced by one module at read
  time**, not by the database — unless question 1 is answered with the migration.
  That is a real weakening relative to `onboarding_answer`, whose scope is a column,
  and it is accepted knowingly rather than missed.
- **A new tripwire in the direction the existing test does not cover.** Today a
  `fact.*` field added without `question_key` is silent: the fact stores, the bank
  question stays outstanding, the founder is asked twice. The reverse test fails
  loudly and names the bank question that lost its writer.
- **Conflicting answers become reachable.** Once both spaces resolve, the block and
  the interview can hold different answers to one question. `doc/08` §12 item 3
  says nothing decides which a tile shows, and this decision does not decide it
  either. It will arrive as a support question before it arrives as a design one.
- **The catalogues still drift.** This is a join, not a merge. Two files still have
  to be edited together, and only one direction of that is now checked.
- **No new table, no new dependency, no migration** — on the recommended answer to
  question 1.

## Alternatives rejected

**Dual-write the interview into `onboarding_answer` (B).** It removes the
translation and creates a duplication: two rows for one answer, in stores with
different supersession rules, with nothing deciding which is authoritative. It also
requires inventing a department, a scope and an `answer_state` for a row the
interview does not have them for — which is the mapping problem again, moved into a
write path where getting it wrong is durable rather than recomputed each request.

**Collapse the catalogues (C).** The right end state, and the wrong next step. The
two records differ in almost every field that is not the question text, so the
merge is a union with most columns empty, and it would rewrite a
security-relevant file (ADR 0021) and the registry's id space in the same change.
Worth reopening when a third renderer appears — at that point the cost of the join
is paid three times and the merge is cheaper than the drift.

**Hold the mapping in a table beside either surface.** Already rejected in
`fields.py`'s own docstring and still right: a third thing to keep in step with two
that already drift.

**Leave the counter reading `onboarding_answer` only (D).** Restores a visible
defect to avoid an invisible one, which is an honest trade and a bad one — the
founder is asked twice for something they said, which is exactly what three rounds
of work on *which* questions to ask was for.

**Filter the promoted facts by the answerer's `stated_department`.** Tempting,
because the interview already narrows on it. Refused: `stated_department` and
`designation` are what a person typed about themselves and reach nothing, and
`assert_persona_is_not_authorisation` exists so that stays true by construction.
The field's own department is the only correct source.

## Revisit trigger

- **A third surface collects the same facts** — a settings panel, an import, a
  connector writing a rule. At three, the pairwise joins outnumber the catalogues
  and option C becomes cheaper than the drift.
- **A bank question and an interview answer are found disagreeing in a real
  workspace.** That is `doc/08` §12 item 3 arriving, and it needs a precedence rule
  this ADR deliberately does not supply.
- **An executive block is added to the bank** (`doc/13` defect 26). The three
  `fact.executive.*` fields stop being class C and the 19/10/3 split is wrong.
- **Anything needs to read a `fact.*` row outside `grounding/context.assemble`.**
  The read-time department filter is the whole of the scope enforcement on the
  recommended option; a second reader means the migration in question 1 should be
  taken instead.
