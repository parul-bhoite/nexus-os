# 0035 — How the ops layer knows it holds everything

**Status:** Accepted
**Date:** 17 September 2026
**Decides:** D29
**Depends on:** ADR 0034 (a figure that is neither a score nor an amount)
**Context:** `doc/15` S10.2 — the slice that is nothing but this answer, applied

## Context

The ops layer is the first source that **fails on adoption rather than on an
API**. Every other source is authoritative about itself: a crawl reads the page
that exists, a CRM knows its own deals. This one holds whatever somebody
remembered to type.

The failure is not an empty screen, it is a half-full one. A founder records
three of twelve projects and `on_time_dispatch` computes *"67% on time"* over a
third of reality — a **wrong number with a plausible denominator**, arriving from
our own feature rather than from a model. Nothing in the database distinguishes
that founder from one who recorded all twelve.

S10.1 shipped counts, which are true either way because they state what was
recorded. Every ops capability after it is a rate.

## Decision

**Both halves of D29's recommendation: an explicit completeness question per
entity, stored with a date, *and* self-reported provenance on every ops figure.**
They answer different questions — the provenance says where the number came
from, the confirmation says whether it covers everything — and either alone
leaves a real way to mislead.

**1. The question, per entity, with a date.** *"Is this all of your projects?"*
is answered per entity kind rather than once for the layer, because somebody can
plausibly have recorded every project and a third of the tasks. A confirmation
is `(workspace, entity, complete_as_of, who, when)` and is **append-only**: the
question is asked again as the business changes, and the history of when
somebody last vouched for the record is the thing a reader needs. We report the
date and never judge its freshness — a threshold for when a confirmation goes
stale would be a number nobody set, which is the failure this ADR exists under.

**2. A rate requires a confirmation.** `completeness.may_compute_a_rate` is the
single gate, and it is written now, with tests, though the first ops rate is
S10.4. A rule added after the code it governs is a rule added once somebody has
already shipped around it.

**3. Provenance travels on the figure, not in the widget state.** This is the
one place the implementation departs from D29's literal wording, and the reason
matters.

`WidgetState.SELF_REPORTED` already exists, and `doc/13` §7 defines its
treatment exactly: *"the founder's words + 'You, 8 September'"*, rendered as a
**`facts` block, never a metric slot**, as quoted text with an attribution line.
`BlockCard.hasFigure` implements that — it returns `false` for `self_reported` —
so setting the state on the ops tiles would **blank the counts entirely** and
undo S10.1.

That treatment is right for what it was built for and wrong here, because the
two cases are not the same thing:

- A **self-reported value** is a number the founder stated — *"revenue was
  45,000"* — and we repeat it back. `doc/05` §0's rule bites hardest here: we
  have no independent knowledge of it at all. D7's manual finance entry is this,
  and the state must keep meaning this.
- An **ops count** is arithmetic *we* performed, in code, over rows they
  entered. The rows are theirs; the calculation is ours and is I1-compliant. The
  population may be incomplete — which is exactly what the confirmation is for —
  but the number is not a claim we are merely relaying.

So ops figures stay `live` and carry `self_reported: true` plus
`complete_as_of` in the payload. `doc/13` §7's actual requirement — that a typed
number and a measured one never look identical, and never by a badge on an
otherwise identical tile — is met structurally by ADR 0034's `kind` discriminator
and by the provenance sentence the tile renders, not by a colour.

**4. The unconfirmed state says so in words.** A tile with no confirmation reads
*"You have not said whether this is all of them, so this counts the record
rather than the company."* Silence is the common case and the most misleading
one, so it gets a sentence rather than an absence.

## Consequences

- **S10.3–S10.7 are unblocked**, and S10.4's on-time dispatch — the first ops
  rate — now has a gate to pass rather than a judgement call to make.
- **A new table**, `ops_completeness`, with RLS enabled and forced like its two
  siblings. Migration 0033.
- **`live` on an ops tile does not mean complete**, and never did. It means
  every required source is present, and the customer's own records are the
  required source. The figure's own fields are what carry the limits.
- **`WidgetState.SELF_REPORTED` stays unused by ops** and keeps its `doc/13` §7
  meaning for D7. If a later slice wants a founder-stated ops *value* — a target,
  a promised lead time — that is the state to use, and this ADR is not in its way.
- **Confirmations can go stale and we do not say so.** A founder who confirmed in
  March and stopped recording in April has a rate computed over a record we were
  told was complete. Reporting the date is the whole mitigation. Inferring
  staleness was D29's third option and was rejected: an accurate record that
  stopped changing is indistinguishable from an abandoned one, and N days is a
  threshold nobody set.

## Alternatives rejected

**Infer completeness from staleness.** Cheapest, asks nothing of the founder, and
cannot tell a finished project list from a forgotten one.

**Counts only, forever.** Honest, and leaves 23 capabilities permanently partly
blocked. It is this decision deferred rather than made.

**Ask, without marking provenance.** A confirmed-complete rate would then render
identically to one fetched from a provider, which is the thing `doc/05` §0 exists
to prevent — and the confirmation makes it *more* dangerous, not less, because it
reads as verification.
