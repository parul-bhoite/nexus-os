# 0049. A tool either promises a capability or records a fact, never both

- **Status:** Accepted
- **Date:** 2026-09-19
- **Deciders:** Parul
- **Closes:** `BUILD-STATUS.md` M18, asserted as a failing invariant in
  `tests/test_source_ledger.py`
- **Related:** ADR 0023 (Search Console and GA4 as the first two connectors),
  ADR 0020 (a question nothing consumes is cut)
- **Affects:** `app/domain/connections.py`, `ToolOut` in
  `app/routes/onboarding_agent.py`, `apps/web/components/onboarding/ToolsStep.tsx`

## Context

The onboarding tools step shows a customer nine systems they might run on, each
with a sentence under its name saying what connecting it does. Those sentences
came from one field, `Tool.unlocks`, whose docstring read *"What NEXUS can do
once this is connected. A capability, never a finding."*

One of the nine could not honour its sentence. **Google Search Console** said
*"Telling you which searches you already rank for, from your own data"*, but no
capability in the registry requires `Source.SEARCH_CONSOLE` — so connecting it
would turn on nothing, now or on the day OAuth lands. `test_source_ledger.py`
had recorded this as an assertion pinning the broken state (`unbacked ==
{"search_console"}`) precisely so that closing it had to be deliberate rather
than accidental.

A promise made during onboarding is worse than a locked tile. A locked tile
states what is missing; this states what is *coming*, and the product's whole
claim rests on not saying things it cannot back.

Two facts constrain the fix:

1. **Building the capability is externally blocked.** It needs Google API
   credentials — **D3** in `DECISIONS-REQUIRED.md` — which are not ours to
   produce. So "make the sentence true" was not available in this pass.
2. **The tick is still worth collecting.** Knowing a company runs Search Console
   shapes what the workspace asks and what it reports it cannot see, even with
   no connector. Deleting the tool would throw that away to fix a sentence.

## Options considered

### A. Rewrite the sentence

Change the copy to something honest and leave the model alone. One line, no
schema change, no wire change.

But nothing then prevents the next tool from carrying an unhonourable promise —
the guard would remain a test asserting one hard-coded id, which is a list
somebody has to remember to update.

### B. Remove Search Console from the catalogue

ADR 0020's precedent for a question nothing consumes is to cut it. Clean, and it
makes the promise impossible by removing the thing making it.

It also discards the stack signal, and re-adding the tool when D3 lands means
re-deciding everything about it. The problem is the sentence, not the tool.

### C. Split the field so the type carries the distinction

`unlocks` stays a promise and becomes legal only when a capability requires the
source; a new `records` field carries what ticking it does today. Exactly one is
set, enforced in `__post_init__`.

## Decision

Option C. `Tool.unlocks: str | None` and `Tool.records: str | None`, exactly one
of the two set, enforced at construction. Search Console carries `records`.

The wire follows: `ToolOut.unlocks` becomes nullable and `ToolOut.records` is
added, so the screen can tell a promise from a record rather than inferring it.

## Reasoning

**The decisive constraint was that the guard must survive the next tool, not
just fix this one.** Option A leaves a rule that lives in a test's hard-coded
set; option C makes the rule structural — a tool with no capability behind its
source *cannot* be given an unlock sentence, because `__post_init__` refuses the
construction and `test_source_ledger.py` now asserts the rule rather than the
instance. The tenth tool is checked by the same mechanism as the first nine.

Option B was close, and would have been right if the tick were worthless. It is
not: `connections.declared` feeds what the workspace says it cannot see, and a
company that runs Search Console is a different company from one that does not,
whether or not we can read it yet.

Two behaviours fell out of the split that the copy edit would have left wrong,
and they are the argument for it:

- **`gaps_for` no longer emits a "still locked" line** for a tool with no
  `unlocks`. Nothing is locked behind Search Console, so naming it as a gap
  would have reinvented the promise in the place the founder reads gaps.
- **The step's "what you turn on" panel is fed from `unlocks` alone.** Ticking a
  `records` tool adds nothing to that list, which is exactly right and was
  previously impossible to express.

**What this costs.** `ToolOut` is a breaking change for any client reading
`unlocks` as a non-null string — internally that is one component, updated in
the same change, and the API is not versioned or public. It is recorded here
because "the field went nullable" is invisible in a diff of a copy change, and
because a future external consumer of this endpoint needs to know the field can
be absent.

## Consequences

- A tool nothing reads can be offered honestly, so the catalogue no longer has
  to choose between lying and hiding.
- `unlocks` is now a load-bearing assertion rather than prose: adding a tool
  whose source backs no capability fails the suite until the author picks
  `records` or builds the capability.
- Clients must treat `unlocks` as nullable and fall back to `records`.
- The *connector* is still unbuilt. This ADR closes the promise, not the gap —
  Search Console still turns nothing on.

## Revisit trigger

When **D3** lands and a capability requires `Source.SEARCH_CONSOLE`: move the
tool back to `unlocks` with a sentence naming the tile it turns on. The suite
will not force this — a `records` tool whose source *gains* a capability stays
legal — so it is worth a line in that connector's own work item.

Also revisit if a third state appears: a tool that unlocks something for some
companies and nothing for others. The current model assumes the answer is the
same for everyone, which is true while capability requirements are static.
