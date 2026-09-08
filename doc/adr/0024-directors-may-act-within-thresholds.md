# ADR 0024 — Directors may act within thresholds, and what must exist first

**Status** Accepted
**Date** 9 September 2026
**Decided by** Parul, answering `doc/13` §25 decision 2.

## Context

The product's own positioning is that every competing tool answers *"what happened?"*
and NEXUS answers *"what should I do about it?"* — **and then does it**. The dashboard
plan asked how far a director agent may go at MVP: narrate only, propose and let a human
send, or act within thresholds.

`doc/12` P20 already specifies the machinery an acting agent needs: read tools and write
tools as separate sets, `wrap_untrusted` as the single entry point for every untrusted
byte, tainted turns, and no externally visible action from a tainted turn without a human
confirming the exact payload. What it did not settle is whether MVP ships with actions at
all.

## Decision

**Directors may act, within thresholds the customer sets — and no agent takes a single
external action until all six preconditions below are green.**

`autonomy` becomes a manifest field with three values (`doc/13` §20): `read`, `propose`,
`act`. Every director ships at `read`, is promoted to `propose` when its narration is
proved, and reaches `act` only per-capability and only once the customer has enabled it.

### The six preconditions, and none of them is optional

1. **Settings panel 11** exists — per-agent autonomy, approval thresholds, spend caps,
   do-not-contact lists, and the kill switch given a surface.
2. **All five `/evals/injection` specs green**, each first proved to fail against a
   deliberately ungated action (`doc/12` P20).
3. **Read tools and write tools are separate sets**, and an `actions = []` manifest
   cannot reach a write tool at all.
4. **A tainted turn cannot act** without a human confirming the exact payload. This is
   not a setting the customer can switch off.
5. **Every action writes an audit row** before it leaves the process, including the
   refusals — a log recording only what worked cannot tell you somebody probed.
6. **Every action is reversible or confirmable.** An irreversible external effect —
   money moved, a message sent to a customer — requires confirmation regardless of
   threshold.

## Consequences

- **The build order changes, and this is the real cost of the decision.** Panel 11 and
  the injection evals move ahead of the first acting capability rather than sitting in
  P20 behind six directors. Choosing `act` does not make agents act sooner; it makes the
  governance layer MVP-blocking rather than post-MVP.
- **`propose` is the honest interim state**, and most of the demo value lives there:
  drafted outreach, drafted proposals, drafted campaigns, a drafted chase email. It is
  what ships while the preconditions are being built.
- **The threshold is the customer's; the confirmation is ours.** A customer may raise a
  spend cap. No customer may switch off payload confirmation on a tainted turn, because
  the risk it guards is not theirs alone.
- **The autonomous tools in `doc/prototype/NEXUS OS Dashboard Tools.xlsx`** — AI ad
  manager, autonomous outreach, voice agents, dynamic pricing, AR/AP chasing — become
  reachable, each one behind these same six preconditions. The sheet's own market note
  records that this category has no dominant governance product; ours is the layer, and
  it must exist before any of them is connected.
- **I8 still holds.** No allowlist anywhere contains a shell tool, and a test asserts it.
