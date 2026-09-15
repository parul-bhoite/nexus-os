# ADR 0027 — Onboarding is three sections over eight phases

**Status** Accepted
**Date** 15 September 2026
**Decided by** Parul, directing the onboarding redesign.

## Context

The guided onboarding built in P6–P8 drew a **seven-step rail**: Read, Brief, You,
Documents, Tools, Confirm, Ready. The rail was faithful to `Phase` in
`app/domain/onboarding_sessions.py`, which is the point at which it stopped being
useful — it exposed the server's state machine to somebody meeting the product for
the first time and asked them to hold seven steps in their head before they had
been told anything.

Three specific costs, all visible in a browser:

- **Four of the seven steps are one room.** `analysing`, `brief`, `discovery` and
  `documents` are a single continuous conversation. The rail advanced between them,
  so the screen announced a new step every time the agent finished a sentence, and
  the heading re-ran its entrance animation mid-paragraph.
- **`assembling` had no step at all.** `phaseIndex` returned `-1` for it, so the
  rail went blank for the twenty-odd seconds the Company Brain is being built —
  the longest wait in the journey after the opening read.
- **The tools step rendered under the whole transcript.** The one screen in
  onboarding that asks somebody to make a decision opened with several hundred
  words of their own history above it.

The obvious repair — collapse the phases themselves — is not available. `Phase` has
`ck_onboarding_session_phase` behind it and `test_constraint_enum_parity` comparing
the two on every run; more importantly the ordering it encodes is a **precondition
the server checks**, not a sequence the client is trusted to follow. `finish`
refuses to run from `documents` or `tools` because the Persona and the Brain are
built from whatever is in hand when it runs, and a Brain assembled before the price
list arrived can only be repaired by assembling it a second time and paying for
every model call again.

## Decision

**The screen groups the eight phases into three sections. The phases do not
change.**

| Section | Phases | What it is |
|---|---|---|
| **Conversation** | `analysing`, `brief`, `discovery`, `documents` | One chat: the read, the brief, the interview, the files |
| **Your tools** | `tools` | Select the stack, and see what each choice turns on |
| **Summary** | `persona`, `assembling`, `ready` | Confirm how you were understood, watch it build, open the workspace |

Four consequences follow, and each is asserted by a test:

1. **The rail holds still through a conversation.** The section heading is keyed on
   the section, not the phase, so it no longer restarts under somebody mid-answer.
2. **The granularity moves down, not away.** What the seven steps carried in their
   labels is now a line under the current section — "Question 3 of 5" over the real
   ceiling, and *named* stages where there is nothing countable. Reading a website
   has no denominator, so it is named rather than counted.
3. **`assembling` gets a home.** It belongs to Summary, and while it runs the screen
   draws the three stages the server actually commits rather than a greyed-out card.
4. **The transcript stops at the conversation's edge.** Tools and Summary are
   screens of their own.

**This is a grouping and must stay one.** Nothing is skipped, nothing is reordered,
and the client gains no say over which phase it is in — `sectionIndexFor` is a
lookup, and every request still takes its stage from the row. A session written by
an older build resumes into exactly the phase it left and lands in whichever section
contains it.

## Consequences

**No migration.** `ck_onboarding_session_phase`, `Phase`, and
`test_constraint_enum_parity` are untouched, and in-flight sessions are unaffected.
This is the whole reason the decision is affordable: the same change made in the
database would have been a destructive migration against live onboarding rows.

**The tools step becomes a screen, and selecting becomes configuring.** The
catalogue is drawn as selectable cards with a panel beside it that names what the
current selection unlocks, updating as boxes are ticked. Every line in that panel is
a capability the registry already declares — never a finding and never a figure —
and the checkbox stays a real `input` so the role, the keyboard behaviour and the
announcement survive the restyling.

**What it still does not do is connect.** `connectable` is false for all nine tools
and the honest sentence is rendered from it, so it disappears on its own the day a
real flow lands. A row of Connect buttons that open nothing remains the one thing
this screen cannot ship — see ADR 0023, and `doc/11` §73.

**The rail is no longer a map of the server.** That is the trade: an operator
reading a screenshot can no longer tell `persona` from `assembling` at a glance.
They are distinguishable in the stage list while the assembly runs, and the phase is
on the session row, which is where an operator should be reading it from anyway.

## Alternatives rejected

**Collapse the phases in the database.** Fewer concepts overall, and the ordering
guarantee goes with them — `finish` would no longer be able to refuse running before
the documents are in. It also needs a destructive migration over live rows.

**Keep seven steps and shorten the labels.** The problem is not the wording. Four of
them are one conversation, and no label fixes a rail that advances mid-sentence.

**Show a percentage.** A denominator over "how much there is to know about a
company" is the invented number this product exists to refuse (I1).
