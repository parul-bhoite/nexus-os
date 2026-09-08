# ADR 0021 — A generated question must name a declared field

**Status** Accepted
**Date** 4 September 2026
**Decided by** Parul, choosing "generated + declared target" over keeping ADR 0019 as written.
**Amends** ADR 0019, which stands in every other respect.

## Context

ADR 0019 accepted the conversational questionnaire and then imposed one
condition: the model decides *how* to ask — phrasing, order, follow-ups, and
what to skip — but "**never introduces a question that is not in the
catalogue**". The stated reason was precise and correct:

> `doc/08` specifies the question set, and each question carries the scope tag
> that decides whether an answer is stored at L2 or L3. A generated question has
> no scope tag, so its answer has nowhere honest to go.

The agent-first onboarding needs questions that follow from what the person just
said. Some of those are not in `doc/08` and could not be — the catalogue was
written for a form, where every question exists before anyone answers anything.

So the collision is real, and re-reading it shows the ban is a fix for the
failure rather than the failure itself. The failure is **an answer stored at an
unknown sensitivity**. Banning generated questions prevents it. So does making
the tag come from somewhere other than the question.

## Decision

**The model generates the question. The runtime supplies the scope, from a
declared field catalogue.**

`app/ai/runtime/fields.py` declares every field onboarding may write, each with a
scope. The `question-generation` skill must return `{question, target}` where
`target` is a key in that catalogue, chosen from a list the runtime handed it for
that turn. A turn naming anything else is refused before the question reaches a
person, and the model is asked again with the refusal in front of it.

Four consequences, all deliberate:

- **The scope never comes from the model.** It is read off the catalogue entry
  in `_scope_of`. Nothing the model returns can influence it.
- **The prompt never sees a scope.** `fields_for_prompt` emits `key`, `label` and
  `intent` only. A model that could see the tag could reason about which phrasing
  gets an answer stored more permissively; it has no legitimate use for it.
- **A question the catalogue cannot express cannot be asked.** Adding a field is
  an edit to one file, with a scope on it, reviewed. It is not a side effect of a
  model finding a new topic interesting.
- **The answer's target is fixed when the question is asked, not when it is
  answered.** `submit_answer` compares the client's `target` against the agent's
  own last turn and rejects a mismatch. A client that could name the target could
  choose the sensitivity its answer is stored at.

`doc/08` remains the source of truth for what a *complete* onboarding must
establish. The catalogue is the runtime's enforcement surface, and every
`doc/08` question maps onto a field in it.

## Consequences

- **ADR 0019's "two renderers, one catalogue" invariant is unaffected.** There is
  still one declarative source; the conversational renderer now selects from it
  dynamically rather than walking it in order.
- **`obCoverage`-style checking moves server-side and gets stronger.**
  `test_a_question_targeting_an_undeclared_field_is_refused` and
  `test_a_skill_cannot_write_a_field_it_did_not_declare` prove both gates. The
  prototype could only check containment by inspection.
- **The catalogue is now a security-relevant file.** A careless scope on a new
  field writes answers at the wrong sensitivity, which is exactly what RLS exists
  to prevent. It deserves the same review as a migration.
- **`persona_chat.never_asked` is now expressed twice** — as an absence there and
  as `assert_persona_is_not_authorisation()` here, which fails at import. The
  duplication is intentional: an absence is easy to erode by addition.
