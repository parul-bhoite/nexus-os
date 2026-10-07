# 0067. One combined onboarding flow: company, Areas of Interest, then a hybrid question engine

- **Status:** Accepted
- **Date:** 5 October 2026
- **Deciders:** Parul (session direction, confirmed via the two-question steer)
- **Supersedes in part:** the two-page split of `/register-company` →
  `/onboarding/agent` established implicitly by ADR 0066's flow; the LLM agent
  as the *sole* question engine
- **Affects:** `apps/web/app/register-company/**`, `apps/web/app/onboarding/agent/**`,
  `apps/web/components/auth/RegisterCompanyForm.tsx`,
  `apps/web/components/onboarding/AgentOnboarding.tsx`,
  `apps/web/lib/agent-onboarding-client.ts` / `onboarding-client.ts`;
  no change to the backend phase machine, the `workspace_department` set, or the
  question catalogue contract

## Context

The onboarding journey is two separate pages. `/register-company` collects a
company name, a mandatory website URL, a free-text role and a **single** stated
department, then redirects to `/onboarding/agent` — an eight-phase, server-driven
LLM agent (`analysing → brief → discovery → documents → tools → persona →
assembling → ready`) already grouped into three sections for the person.

The owner's verdict on the result: *too informative and tiring*. The founder is
handed a long, server-paced conversation as the first thing they do, across two
page loads that read as two different products.

Two facts about the existing backend reshape what a fix costs:

- **A multi-department selection already exists.** `workspace_department`,
  `POST /onboarding/departments`, `select_departments` (replace-wholesale, floor
  of one, 3–5 recommended, Chief of Staff automatic) — this is the director set
  that decides which dashboards exist. Nothing in the current UX asks for it as
  an explicit, upfront choice; it is inferred later. The owner wants it surfaced
  first, as a multi-select "Areas of Interest".
- **A deterministic question catalogue already exists** (`app/domain/onboarding.py`):
  every question is tagged with the department that owns its answer, carries
  suggested answers (`options`) and a short `why`, and needs no language model.
  This is a second, dormant question engine alongside the LLM agent.

So the choice is not "build onboarding" — it is how to recompose pieces that
already exist into one calmer flow, and which engine answers the questions once
the Areas of Interest are known. That is an architectural boundary and a
data-flow decision (it moves when the department set is chosen and changes the
question-serving contract the front end talks to), so it is recorded here.

The *visual* direction is deliberately out of scope for this ADR — a
design-exploration pass chooses it separately. This records the flow and engine.

## Options considered

### Engine A. Keep the LLM agent as the only question engine

Reorder it behind the new steps, reskin it. Richest and most grounded — it reads
the real website and writes a brief. But it **requires the Anthropic key**
(ADR 0011 makes "no key" a supported state, and locally it often is unset), it is
heavy, and it is the flow the owner already called tiring.

### Engine B. Deterministic catalogue only, scoped to the selected departments

Drop the agent from the first run. Serve catalogue questions filtered to the
chosen Areas of Interest, each with its suggestion chips. Fast, calm,
key-independent, and the question count scales naturally with the selection. But
it discards the website-grounded brief the agent produces, which is part of why
the product feels like it already knows the company.

### Engine C. Hybrid — optional scan/brief up front, then the catalogue

When a model is configured, keep the website-reading moment (and the scan
animation from ADR 0066) and the brief. Then, for the bulk of the questions,
switch to the deterministic catalogue scoped to the selected departments, with
suggestion chips. When no model is configured, the scan is skipped and the flow
is the catalogue alone — still complete, per ADR 0011.

### Flow A. One route, pre-steps then the agent inline

Fold company details and Areas of Interest into a single wizard route that then
renders the existing onboarding engine **inline** in the same shell.
`/onboarding/agent` redirects into it so existing links and resumes survive. The
server phase machine is untouched — the front end reorganizes and reskins around
it.

### Flow B. Rebuild the flow as one new server contract

Collapse the eight phases into a new, smaller server-side flow purpose-built for
the combined journey. Cleanest conceptually; throws away a deliberately-designed,
well-reasoned state machine (resumability, the phase CHECK constraint, the
assembly stepping) and is a large backend change with real regression risk.

## Decision

**Engine C (hybrid) and Flow A (one route, server phases intact).**

- One combined, continuous experience: **company details → Areas of Interest
  (multi-select) → tailored questions → enter workspace.** The entry stays
  `/register-company`; `/onboarding/agent` redirects into the combined flow so
  bookmarks and in-progress resumes keep working.
- **Areas of Interest** is a first-class, upfront multi-select backed by the
  existing `workspace_department` set and `POST /onboarding/departments` (floor
  of one, 3–5 recommended, Chief of Staff automatic and never shown).
- The **question engine is hybrid**: an optional website-scan + brief when a
  model is configured, then the **deterministic department-scoped catalogue**
  with tap-to-answer suggestion chips for the bulk of the questions. With no
  model, the scan is skipped and the catalogue alone carries the flow.
- The **backend phase machine, the department set, and the catalogue contract
  are not changed.** This is a front-end recomposition plus surfacing an existing
  capability earlier.

## Reasoning

**The tiring feeling is a sequencing and pacing problem, not a missing feature.**
Everything the owner asked for — multi-select areas, questions scaled to the
selection, suggested answers, a short journey — already exists in the backend in
pieces. The cheapest honest fix is to recompose those pieces and move the
department choice to the front, not to rebuild a server contract (Flow B) that
works and carries hard-won properties like resumability and the phase constraint.

**Hybrid (Engine C) is the only option that satisfies both the owner and
ADR 0011.** Engine A fails the "no key is a supported state" invariant for the
first-run experience and keeps the heaviness. Engine B is calm but throws away
the website-grounded brief that makes the product feel like it already knows the
company — and the owner specifically values the scan moment (ADR 0066). C keeps
the grounded moment *when it is available* and degrades to a complete,
key-independent catalogue flow when it is not, which is exactly ADR 0011's shape
applied to onboarding.

**Suggested answers are a surfacing decision, not new data.** The catalogue
already carries `options` and a `why` per question; rendering them as chips is
presentation, so it does not touch the contract.

**Areas of Interest is the right centerpiece because it already means
something.** The selected set decides which directors and dashboards exist — so
asking it first both makes the journey feel purposeful and front-loads the fact
the rest of the flow (and the dashboard) is scoped by. It is explicitly **not**
an authorization input: what a member may read still comes from their workspace
membership (`role`, `departments`), never from what they select here.

## Consequences

- `/register-company` becomes a multi-step wizard; `/onboarding/agent` becomes a
  redirect into it. The two-page seam the owner disliked is gone.
- Areas of Interest is now chosen explicitly and early, by the founder, rather
  than inferred later. `POST /onboarding/departments` gains a first real UI
  caller on the happy path.
- The front end must handle both engine states: scan+brief present (model
  configured) and absent. The "no model" path must stay a first-class flow, not a
  visibly degraded one.
- The deterministic catalogue, previously dormant for the agent path, becomes a
  live surface. Its department tagging and `options` are now load-bearing for
  what gets asked and what chips show.
- The server phase machine is unchanged, so resumability and the phase CHECK
  constraint are preserved; the combined route must still resume a journey in
  progress rather than restarting it.
- The visual direction is chosen by a separate design-exploration pass; this ADR
  does not fix colors, layout, or motion beyond requiring token compliance and
  AA accessibility.

## Revisit trigger

If the deterministic catalogue proves too rigid to feel tailored — e.g. founders
report the questions do not reflect what the scan clearly learned about their
company — then the brief should feed *which* catalogue questions are asked (or
rephrase them), moving the hybrid line and making the model more central again;
at that point re-weigh Engine A/C against the ADR 0011 constraint deliberately.
Conversely, if the scan/brief is rarely configured in practice and adds more
branching complexity than value, collapse to Engine B (catalogue only) and retire
the inline agent from the first run.
