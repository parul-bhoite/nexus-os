# ADR 0025 — Fixed per-tile windows, and no period selector at MVP

**Status** Accepted
**Date** 9 September 2026
**Decided by** Parul, answering `doc/13` §25 decision 3.

## Context

`doc/05` §1 puts a **7 / 30 / 90 / custom period selector** in the global shell.
`doc/08` — extracted from the prototype, and the narrower cut — **dropped it**, fixing
each tile's window instead and stating it in the tile's working. `doc/08` §12 lists the
omission as an open item precisely because no decision was ever recorded: the selector
was not rejected, it was simply not there.

This has to be settled before the working drawer is built, because the drawer states the
arithmetic and the window is part of the arithmetic.

## Decision

**Each tile carries its own fixed window, and states it in its working drawer.**

    Enquiry conversion   2.8 %   +0.4pp        [GA4]
      Method       submissions ÷ sessions
      Numerator    236
      Denominator  8,420
      Window       19 Jul – 17 Aug

No selector at MVP. It is reconsidered when there is enough history to select over — a
90-day option in week two offers a customer a comparison the data cannot support.

## Consequences

- **The drawer's arithmetic is unambiguous.** One tile, one window, one numerator, one
  denominator. A selector means every tile restates its working per window, and the
  first inconsistency between two windows is a bug the customer finds.
- **The window is a settings-derived value, not a literal.** Fiscal year start and
  reporting week definition live in settings panel 5 (`doc/13` §14), and changing either
  moves the windows — which triggers the restate rule (`doc/13` §10): affected tiles are
  marked stale and re-derived, the change is logged, and the previous derivation is
  superseded rather than edited.
- **`doc/05` §1 is narrowed, deliberately.** Recorded here so the selector's absence is
  a decision rather than a gap somebody later "fixes" without knowing why it went.
- Comparison against a prior period stays: *"+9.2% vs July"*. What is fixed is the
  window, not the ability to compare — and a zero delta still reads **"unchanged"**.
