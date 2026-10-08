# 0082. PageSpeed is a platform-key source, fetched on completion, wired ahead of Phase 18

- **Status:** Proposed
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

The product needs to show a company real, measured insight the moment onboarding
completes — not only locked tiles with unlock copy. An OAuth connector cannot do
this: OAuth requires the user to click Connect and consent in the vendor's own
screen, so nothing can be fetched "on completion" through an OAuth source.

A validation of the free tools found exactly one that needs **no** per-user
consent: **PageSpeed Insights**. Its API takes a single platform-held API key and
analyses any public URL — and we already hold the company's verified domain from
the crawl. So PageSpeed can be scored automatically, with no Connect step.

The repository, however, had PageSpeed filed with GA4 and Search Console as a
**Phase 18 / D3** future: `NEXUS_PAGESPEED_API_KEY` was listed in the
`test_config_gates.FUTURE` set as "P18 — PageSpeed Insights (D3)", and
`calculators/audit.py` notes Lighthouse metrics are "not wired (D3)". That filing
conflates two different auth models: GA4/Search Console need **OAuth** (the real
content of D3 — a Google OAuth client), whereas PageSpeed needs only an **API
key**. D3 is about OAuth credentials; PageSpeed does not wait on it.

## Options considered

### A. Wire PageSpeed now as its own platform-key source (chosen)
Treat PageSpeed like the language-model and embedding keys (ADR 0011): an optional
platform key, absent is a supported state. Build a dedicated client
(`connectors/pagespeed.py`), a pure calculator, and a best-effort capture that
runs on completion and writes a `workspace_insight`. Promote
`NEXUS_PAGESPEED_API_KEY` from a `FUTURE` key to a real `Settings` field.

### B. Keep PageSpeed in Phase 18, behind D3
Leave it filed with GA4/Search Console. Simpler to the plan's letter, but wrong on
the mechanism (PageSpeed needs no OAuth) and it forgoes the one insight that can
light up on day one with no user action — the exact thing the completion
experience needed.

### C. Model PageSpeed as an OAuth connector in `WIRING`
Force it through the OAuth connector spine for uniformity. Dishonest: it would
render a Connect button for something that needs no connecting, which the registry
explicitly refuses to do ("Connect buttons that authorise us and then do nothing").

## Decision

Option A. PageSpeed is a platform-key source:

- `pagespeed_api_key` is a real optional `Settings` field, not passed through
  `require()`; absent is supported (no insight, never a fabricated score).
- `connectors/pagespeed.py` holds a dedicated client and an httpx transport (PSI
  uses a query-param key, not Bearer, so it does not reuse `RestTransport`). The
  key is never logged and never placed in an exception message — a PSI URL carries
  it.
- `calculators/pagespeed.py` is pure: payload → integer 0..100, raising rather
  than guessing when the score is absent or null (I1).
- `domain/pagespeed.py::capture` fetches, computes and writes one
  `workspace_insight` (ADR 0081), best-effort: provider and shape failures store
  nothing and never raise.
- The onboarding `/finish` route schedules the capture as a **detached task in its
  own scoped transaction**, created **only when a key is configured** — so with no
  key (every environment today) nothing is scheduled and completion is untouched,
  and the live audit never blocks the finish response or holds its transaction.
- The source's **ledger `Origin` is left as `CONNECTOR`**: `test_source_ledger`
  and the connect-screen model already treat PageSpeed that way, and the fetch
  path does not depend on the ledger. Revisit if the ledger grows a key-origin
  distinction.

PageSpeed is **decoupled from D3**, which remains what it always was: the Google
**OAuth** credentials for GA4 and Search Console.

## Reasoning

A was chosen because it is the only option that is both honest about the mechanism
and delivers the completion experience. The repo's Phase-18/D3 filing was a
reasonable shorthand ("all the Google things") that does not survive contact with
the actual auth models: an API key is not OAuth, and treating PageSpeed as if it
waited on an OAuth client would defer the one free insight that needs no waiting.
C was rejected for the same reason the registry refuses dead Connect buttons. B
was rejected because it keeps a true statement (PageSpeed is a Google source) in a
place that makes a false implication (that it needs D3).

This is a deliberate deviation from `doc/12`'s Phase-18 placement for PageSpeed,
made with the user's explicit approval in session, and recorded here so the
sequencing change is traceable rather than silent.

## Consequences

- A company with a crawled site gets a real Marketing performance score on
  completion, as soon as a platform PageSpeed key is configured.
- `NEXUS_PAGESPEED_API_KEY` is now a real setting; `test_config_gates.FUTURE` no
  longer lists it, and the two `.env.example`-drift tests cover it like any other
  optional key.
- The capture is best-effort and off the request path; a PSI outage or a missing
  key degrades to "no insight", never to a wrong one.
- **Live verification is deferred**: no real PSI call is made in tests (fixtures
  only, `/goal` §5). The capture is proven end-to-end against real Postgres with a
  recorded payload; the actual Google round trip is exercised only once a key
  exists.
- Holding a live audit off the finish transaction via a detached task is adequate
  at onboarding cadence; if PageSpeed later runs on a schedule for many
  workspaces, it belongs in a worker, the same note the in-process embedding pass
  carries.

## Revisit trigger

Reopen if: the source ledger gains a first-class key-origin distinction (PageSpeed
would move to it); PageSpeed capture needs to run on a schedule rather than once
on completion (move it to a worker); or Google folds PageSpeed access into the
same OAuth client as GA4, at which point the D3 coupling becomes real.
