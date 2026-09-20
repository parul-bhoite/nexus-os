# 0052. The first assistant answers from documents, and the panel promises only that

- **Status:** Accepted
- **Date:** 20 September 2026
- **Deciders:** Parul
- **Implements the first decision in:** `doc/20-ASSISTANT-BUILD-PLAN.md`
- **Depends on:** ADR 0051 (the classifier, which is what makes any chunk
  readable), ADR 0012 (iterative scan, which makes scoped vector search work)
- **Affects:** `app/domain/sections.py`, `app/routes/dashboards.py`,
  `apps/web/components/dashboard/AssistantPanel.tsx`

## Context

`AssistantPanel` has been a reserved region since P15, and its design is
deliberate: it names the director, lists the questions that director will
answer, and says plainly that it is not available yet. Its own docstring gives
the reason — *"a blank region where a feature is coming reads as a bug; a fake
one reads as a lie"* — and it has no input box, because *"an input that accepts
a question and cannot answer it is worse than none"*.

The questions it lists are `doc/08` §2E–§8E **verbatim**, kept unparaphrased
because they were written as what a founder would actually type.

Building the assistant exposed a problem with that list. Of the 28 questions,
almost all are about **computed figures**: *"How long is our runway?"*, *"What
is in the pipeline?"*, *"Who owes us and how late are they?"*, *"What is about
to run out?"*, *"Why is business health 72 and not higher?"*. Answering any of
them needs a calculator and a connected source. The registry says 23 of 90
capabilities are reachable and none of those five is among them.

The assistant that can be built now is a different thing: **retrieval over the
customer's own uploaded documents.** `retrieval/chunks.py` is complete,
permission-scoped inside the query, red-team specified, and — since ADR 0051
connected the classifier — finally has readable chunks to return. It was driven
end to end for the first time on 19 September: a Finance document retrieved by a
caller holding Finance, and not by a caller holding only Executive.

So the two lists describe different products. Shipping the passages-only
assistant under the existing panel would put an input box beneath 28 questions it
structurally cannot answer — the exact failure the panel was built to avoid,
arrived at from the other direction.

**A second finding shapes the sequencing rather than this decision.** The panel's
stated gate is that the injection evals are green, and they are — but they are 10
assertions over `domain/untrusted.py`'s dataclass. No model, no prompt, no
retrieval. "Green" means the taint model is specified, not that an assistant
resists injection. That gate is recorded here as **not** met; see Consequences.

## Options considered

### A. Build toward the existing list

Keep the promise and build the computed-figure assistant. Honest to the panel,
and it is the product `doc/08` describes.

It needs the calculators and connectors behind those questions, which is P10/P11
and the ops layer — the work that 66 unbuilt capabilities are waiting on. The
panel would keep promising for months and the retrieval layer, which is finished
and proven, would keep having no consumer.

### B. Ship passages-only under the existing list

Fastest to something usable. Also the one thing the panel exists to prevent: a
founder types *"how long is our runway?"* into a box beneath that exact sentence
and gets "I could not find anything about that in your documents".

### C. Split the list: the panel advertises what the first assistant does

Serve a separate, smaller set of document-grounded questions. Keep
`ASSISTANT_QUESTIONS` untouched as `doc/08`'s specification of the destination.

## Decision

Option C. The first assistant answers **only** from passages retrieved out of the
customer's own documents, and the panel advertises only that.

`ASSISTANT_QUESTIONS` stays exactly as it is — it is `doc/08` verbatim and
deleting it would destroy the specification. A new `DOCUMENT_QUESTIONS` carries
what a document-grounded assistant can actually answer, per department, and that
is what the route serves and the panel shows.

## Reasoning

**The decisive point is which way the dishonesty runs.** Option B promises what
cannot be delivered, which is the failure mode this product spends most of its
architecture avoiding — it is the same shape as a fabricated number, moved into
the copy. Option A promises nothing false but leaves a finished, proven,
permission-scoped retrieval layer with no consumer for as long as the connector
work takes, and leaves the founder's uploaded documents unreadable by the product
they gave them to.

Option C is the only one where every sentence on the screen is true on the day it
ships. The cost is that the panel advertises less than `doc/08` intends, which is
a loss of ambition rather than a loss of honesty — and it is recoverable exactly
when the capabilities behind the other questions exist.

**Keeping both lists rather than editing one** is what makes that recovery
possible. `doc/08`'s questions are a specification of the destination; the new
list is a statement of the current product. Rewriting the first into the second
would have thrown away the record of what the assistant is for, and the comment
above it in `sections.py` says why they are verbatim in the first place.

**Why not both lists on screen.** A panel showing "these now, those later" is
still promising the later ones, with a hedge. The hedge is what a reader
discounts.

## Consequences

- The panel promises a smaller thing, and can keep the promise.
- `retrieval/chunks.py` gets its first consumer, which is what H1 has been
  missing since it was written.
- A founder who asks a figure question of the first assistant gets a refusal
  naming why. That refusal is a feature and must be enforced in code, not
  requested in a prompt — `doc/20` A2 covers it.
- **The panel's injection gate is not met.** Ten assertions over a dataclass do
  not establish that an assistant resists injection, and no input box may appear
  until evals exist that could fail against a real prompt, real retrieval and a
  real model (`doc/20` A3). This ADR settles *what* the assistant promises; it
  does not open the gate.
- `doc/08` §2E–§8E is now aspirational rather than current for this surface, and
  `sections.py` says so beside the constant rather than in this file alone.

## Addition, 20 September 2026 — a refusal names the capability

**Not a change of decision; the part this ADR left implicit.** `doc/20` A1 could
not define its contracts without it, because the answer decides whether
`AssistantRefusal` carries a capability at all.

**A refusal names the capability that would answer the question, where one
exists.** Asked *"how long is our runway?"*, the assistant does not stop at "I
cannot answer that from your documents" — it says which capability would, and
what that capability is waiting on.

The reason is consistency with every other surface. A locked tile already says
*"Needs projects and tasks in NEXUS"* rather than going blank; `doc/04` §6 rule 1
makes it a rule — *"every locked tile states its unlock… the tile is a call to
action, not a failure"*. An assistant that refused without naming the unlock
would be the one place in the product that goes quiet, and it would be the place
a founder is most likely to be asking precisely because they could not find the
figure anywhere else.

**What this does not license.** Naming a capability requires knowing which one
would answer, and mapping free text to a capability is not something the first
assistant can do reliably. So the contract carries `capability_id` as
**optional**: named when the question is one the product already knows about,
absent when it is not, and never guessed. A wrong capability in a refusal is
worse than no capability — it sends somebody to connect a system that would not
have helped.

**Where the sentence comes from.** `domain/dashboards.unlock_for_sources`
already turns a capability's missing sources into *"Needs X and Y."* The
assistant carries the id; the route renders the sentence with that existing
function. This keeps one wording for unlocks across the product and keeps
`app/assistant/` out of the dashboard domain, which its import allowlist
(`tests/test_assistant_boundary.py`) enforces.

## Revisit trigger

When the first computed-figure capability a listed question depends on becomes
reachable in the registry — Finance's cash position and Operations' stock levels
are the nearest — move that question from `ASSISTANT_QUESTIONS` into the served
list, one at a time, each with the capability that makes it answerable. The lists
converge as the product does; the day they are identical, this ADR is spent.

Revisit sooner if a founder asks for the figure questions back: that would mean
the reduced panel reads as a downgrade rather than as honesty, and the framing —
not the decision — would need rethinking.
