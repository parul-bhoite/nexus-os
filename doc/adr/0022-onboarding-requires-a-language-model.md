# ADR 0022 — Onboarding requires a language model

**Status** Accepted
**Date** 4 September 2026
**Decided by** Parul, choosing "require a key for onboarding" over shipping a scripted fallback.
**Amends** ADR 0011 for one path only. ADR 0011 stands everywhere else.

## Context

ADR 0011 says plainly: "**No API key is a supported operating state, not a
degraded one.**" The reasoning was that a generated questionnaire on the signup
path "would make the model load-bearing for the one flow every customer must
complete. Nothing else in the product is."

That reasoning was written when the alternative was a form that worked just as
well. It no longer is. The agent-first onboarding is not a nicer wrapper around a
questionnaire — reading the company, deciding what is already known, choosing
what to ask next from what was just said, and assembling a cited Brain are the
product. A scripted version of it is a different, worse product that happens to
share a URL, and maintaining both means every change lands twice and the
scripted path is exercised by nobody.

## Decision

**Onboarding requires a configured language model. Everything else does not.**

Without a key, `POST /onboarding/agent/start` returns an honest unavailable
state naming what is missing. It does not fall back to a form, and it does not
proceed with plausible defaults.

ADR 0011's other guarantees are untouched and still tested:

- The application starts, serves every other route, and reports
  `language_model: unconfigured` on `/health/ready`.
- Nothing outside `app/ai/` names the vendor.
- `UnavailableProvider` still refuses rather than improvising, and there is still
  no demo mode that returns plausible analysis.

## Consequences

- **A key outage blocks new signups.** It does not affect existing workspaces,
  which read a Brain that is already assembled. This is the cost, stated plainly:
  the blast radius of a provider incident now includes acquisition.
- **Local development and CI need a key, or they skip onboarding.** The runtime
  tests are pure — they exercise the manifest loader, the field catalogue and the
  request builder without a provider — so the invariants stay covered offline.
  End-to-end onboarding does not.
- **`generated_by = 'answers'` loses its main caller.** Migration 0019 admits it
  so a Brain could be assembled with no model at all. That path stays in the
  schema and is now unused by onboarding; it should not be removed, because it is
  what a future scripted importer would write.
- **This is the reversible half.** Re-adding a scripted renderer later means
  adding non-model implementations behind the same command names. The commands,
  the field catalogue and the persistence do not change — which is the reason the
  skill/command split is drawn where it is.
