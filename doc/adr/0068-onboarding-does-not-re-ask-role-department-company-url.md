# 0068. The tailored-questions stage does not re-ask role, department, or the website

- **Status:** Accepted
- **Date:** 6 October 2026
- **Deciders:** Parul ("Remove that", on seeing the role/department questions in the walkthrough)
- **Refines:** [ADR 0067](0067-combined-onboarding-flow.md) — the hybrid question engine's filtering of the deterministic catalogue
- **Affects:** `apps/web/components/onboarding/stages/QuestionsStage.tsx` (the `ALREADY_CAPTURED` set); no backend change — the catalogue and `onboarding_answer` contract are untouched

## Context

ADR 0067 made the deterministic catalogue (`app/domain/onboarding.py`) a live
surface: the combined flow serves every catalogue question whose owning
`department` is `null` (company-wide) or one of the chosen Areas of Interest.

Walking the flow showed three of those company-wide questions are things the
earlier stages already captured, so the founder meets them twice:

- **`company_url`** — the website is entered in the Company stage. It is stored on
  the workspace, not as an `onboarding_answer`, so the catalogue returns it
  *unanswered* and the flow would ask for it again one step later.
- **`role`** — the Company stage already asks "Your role" (free-text designation).
  The catalogue `role` question restates it as a dropdown.
- **`department`** (singular, stated) — overlaps in feel with the Areas of Interest
  the founder has just chosen as a multi-select.

Whether these can be dropped turns on what their answers *do*. `role` and
`department` are the names of two facts that elsewhere in the product **do**
authorize (`membership.role`, `membership.departments`). Dropping a question that
set an authorizing field would be a permissions change, which is why this is
recorded rather than treated as copy.

## Decision

The tailored-questions stage excludes `company_url`, `role`, and `department`
from the catalogue it renders (one `ALREADY_CAPTURED` set, applied alongside the
existing `writable` + department-scope filter). Every other catalogue question is
unaffected, and the exclusion is presentation-only: the backend still serves and
would still accept all three.

## Reasoning

**The catalogue `role`/`department` answers do not authorize anything, so not
asking them changes no permission.** `services/api/app/routes/setup.py` is
explicit: these questions "write rows in `onboarding_answer`. Nothing here
touches `membership`, which is the only table `build_scope` reads." They are
self-declared claims that steer what the assistant leads with — the same category
as the Company stage's `designation` — never the authorizing `membership.role` /
`membership.departments`, which are set at company creation and by an inviter.
ADR 0067 already states Areas of Interest is not an authorization input for the
same reason; this is the mirror of that on the question side. Verified by reading
the store path, not assumed.

**Re-asking what the user just entered reads as the product not listening.** The
owner's complaint in ADR 0067 was pacing and redundancy. `company_url` one step
after the website field, and a role dropdown one step after the role text box,
are the sharpest instances of exactly that.

**The exclusion lives in one named set in the client, not scattered.** It is a
deliberate, auditable list with the safety argument in its doc comment, so a
future reader sees *why* each key is excluded and that the reason is "captured
upstream", not "unimportant".

## Consequences

- The question count the founder sees is smaller and never duplicates a Company /
  Areas answer. In the walkthrough the Finance+Marketing+Operations+Sales
  selection dropped from 11 → 8 questions once `company_url`, `role`, and
  `department` were excluded.
- `role` and `department` therefore have **no** `onboarding_answer` row from the
  happy path. Any consumer that expected one must read the authorizing
  `membership` fields (correct) or the Company-stage `designation`, not the
  catalogue answer — none does today.
- The backend is unchanged: Settings and any other caller of the catalogue still
  expose all three questions. This is a first-run presentation choice only.
- A regression test (`QuestionsStage.test.tsx`) asserts all three are filtered out
  even when returned unanswered and company-wide, so re-adding one is a failing
  test, not a silent reappearance.

## Revisit trigger

If a later feature needs the catalogue `role` or `department` *claim* as distinct
data (e.g. the assistant wants the stated department separately from the Areas of
Interest set and the authorizing membership), re-add that key to the stage —
seeded from what the earlier stage captured rather than asked cold — and update
`ALREADY_CAPTURED` with the new reasoning. If the Company stage ever stops
capturing a role/designation, revisit whether the catalogue `role` question should
return.
