# ADR 0023 — GA4 and Search Console are the first connectors

**Status** Accepted
**Date** 9 September 2026
**Decided by** Parul, answering `doc/13` §25 decision 1.

## Context

After the dashboard shell (`doc/12` P15) every director is a complete catalogue of
locked tiles. Which connector lands first decides which director carries real numbers
first, and therefore which screens get built against measured data rather than against
a fixture.

Four candidates were weighed: GA4 + Search Console, a CRM, an accounting system, and the
Operations first-party layer.

## Decision

**GA4 and Search Console, together, first.**

Both are free, both need only **D3** (Google credentials), and between them they turn
Marketing from three audit scores into six live capabilities plus one on Strategy —
and they are what makes Marketing scoreable at all
(`REQUIRED_FOR_SCORING[MARKETING] = (GA4,)`).

`doc/12` P16 already sequences Marketing as the first director end to end, so this
answers "with what data?" in the way that costs least and proves most. PageSpeed is
promoted alongside them from the retired preview path; it was already computing a real
score.

## Consequences

- **D3 becomes the next blocking external decision.** Nothing else in P18 is needed to
  make one director Live, so D10 (the CRM) and the chart-of-accounts mapping both move
  behind it.
- **The connect flow is exercised on a free tool first**, so OAuth, token encryption,
  revocation and the field-completeness check at connect are all proved before a
  customer's ledger is involved.
- **Marketing's audit scores still do not become a Marketing score.** They measure the
  website, not the marketing. GA4 arriving is what makes the score exist, and the audit
  scores stay separate tiles with their own evidence.
- **Verify goals and events are configured at connect** (`doc/05` §3.2). A GA4 property
  with no conversion event configured produces an enquiry count of zero, which is the
  exact failure I10 exists to prevent — so it is caught at connect and reported, not
  rendered.
