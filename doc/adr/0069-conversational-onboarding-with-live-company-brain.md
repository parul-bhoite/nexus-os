# ADR 0069 — Onboarding is a conversation with a live Company Brain, not a form

- Status: Accepted
- Date: 2026-10-06
- Supersedes: [0067](0067-combined-onboarding-flow.md) (the calm one-question-at-a-time
  catalogue). Amends the role of [0068](0068-onboarding-does-not-re-ask-role-department-company-url.md)
  — see *Consequences*.
- Related: ADR 0011 (the language model is optional), ADR 0066 (the onboarding
  research/scan animation), migration 0019 (`company_brain`), migration 0024
  (`onboarding_agent`).

## Context

ADR 0067 replaced the long agent interview with a calm, deterministic catalogue:
one question at a time, suggestion chips, Areas-of-Interest up front. It shipped
and works. But the product owner, holding `doc/prototype/nexus-os-wireframe-v3.html`
and a detailed brief, asked for something the catalogue is not: an **adaptive,
conversational** onboarding that behaves like a research assistant — reading the
company's website first, acknowledging what it already found, asking only for what
it cannot discover, and **building a Company Brain in view, with provenance on
every fact**, which then persists as the company's knowledge base.

The brief's north star: *"Tell us about yourself, and we'll intelligently learn the
rest,"* not *"fill out this questionnaire."* The catalogue is the questionnaire.

A reality check settled the feasibility: most of the engine already exists.
- `company_brain` (migration 0019) already stores profile, products/services,
  target customers, brand voice, goals, competitors, **assumptions and
  provenance** (NOT NULL, with `ck_company_brain_grounded_has_provenance`),
  versioning and `model_id`.
- `app/research/` is a real web crawler (crawler, extract, runner, ssrf,
  worker loop) — the background research.
- `app/grounding/` assembles context and keeps a provenance **ledger**.
- `onboarding_agent` already runs the conversation: reads the site → confirms a
  brief → converses → selects directors → asks threshold questions → assembles the
  Brain. Its state already carries exactly what a live Brain panel needs:
  `brief.statements[] {text, confidence: 'read'|'inferred', source}`,
  `context.facts[] {value, scope}`, `persona.fields[] {value, derived_from}`,
  `pages_read[]`, and the full `turns[]` transcript.

So this is not a rewrite of the engine. It is a **new experience over an engine
that exists**, plus genuinely new pieces (the split chat/Brain UI, an adaptive
questioning policy, the transcript as a first-class Brain source, and a Company
Brain page that grows from a facts table into a relationship graph).

## Decision

**Onboarding becomes a conversation with a live Company Brain beside it**, matching
the v3 wireframe: a chat column on the left and a provenance-tagged Company Brain
panel on the right that fills as the conversation and the website read progress.
It is built over the existing `onboarding_agent`, `research` and `company_brain`,
and it **replaces the ADR 0067 catalogue** as the onboarding path.

Delivered in phases, each independently testable in the running app:

1. **Chat + live Brain panel.** The wireframe's two-column onboarding, wired to the
   agent client (`start`/`read`/`confirmBrief`/`openDiscovery`/`describeCompany`/
   `nextQuestion`/`submitAnswer`/`finish`). The Brain panel renders `brief.statements`,
   `context.facts` and `persona.fields` with their provenance (`read · <source>`,
   `inferred`, `you`, scope `L1–L5`). Director selection and the threshold questions
   happen **inside the chat**. Resume and the no-model path (below) preserved.
2. **Company Brain page** in the app — the facts-with-provenance view (table first,
   then an interactive relationship graph), reading `company_brain` + the grounding
   ledger, with click-through to each fact's source.
3. **Transcript as a first-class source.** The onboarding conversation is stored and
   shown as a Brain source, with node→message links (chat-to-knowledge), and remains
   searchable and correctable after onboarding.
4. **Tool recommendations** from what was gathered, as part of the tools step.

**Adaptivity (the brief's hard requirement):** there is no fixed, numbered question
list shown to the user. The agent asks only what it could not read or infer, caps
itself (the engine already ceilings the interview), and the UI never renders a
"question N of M" counter. Where the agent still needs a bounded answer (a
threshold, a currency), it offers chips inside the chat — a suggestion, not a form
field.

## Reasoning

- **The catalogue optimised the wrong thing.** 0067 made the flow *calm* by making
  it *static* — the same questions in the same order for everyone, including
  questions whose answers the website already gives. That is the "tiring
  questionnaire" the brief rejects. Calm should come from *asking less*, not from
  pacing a fixed list. An adaptive agent that skips what it can discover asks
  strictly fewer questions.
- **Provenance is the product.** NEXUS sells on *never invent a number* and on
  showing where every fact came from. A Company Brain that fills in view, each item
  tagged `read · homepage` / `inferred` / `you`, demonstrates that promise during
  the very first minute — which a form cannot.
- **Reuse over rebuild.** The engine, the crawler, the brain table and the
  provenance ledger already exist and are already tested. Building a bespoke
  conversational backend would duplicate them and split the source of truth. The
  cost here is overwhelmingly front-end and glue.
- **One source of truth.** Making the onboarding conversation a first-class Brain
  source (phase 3) means the knowledge and its evidence live together, with
  traceability from a fact back to the sentence that produced it — the brief's
  core principle, and what the catalogue's bare `onboarding_answer` rows could not
  offer.

## Consequences

- The ADR 0067 `StartFlow` catalogue stages (`CompanyStage`, `AreasStage`,
  `QuestionsStage`, `WrapStage`) are retired from the live path. The code is left in
  the tree until the conversational flow has replaced every route it served, then
  removed in a dedicated change — not deleted blind.
- **0068 is mostly moot by construction.** Its rule (don't re-ask `company_url`,
  `role`, `department`) existed because the catalogue blindly re-served company-level
  questions. The agent already does not ask for what it has read or what earlier
  steps captured, so the de-duplication is the agent's job now, not a hard-coded
  exclusion list. 0068 stands as history; its exclusion set goes with `QuestionsStage`.
- **Hard dependency on the language model.** The adaptive conversation and the
  knowledge extraction require a configured provider. Per ADR 0011 the model stays
  optional at the platform level, so the onboarding must degrade honestly when it is
  absent — a plainly stated "guided setup is unavailable until a model is
  configured, here is the minimum we can still capture" path, never a fabricated
  conversation. The exact degraded path is settled in the phase-1 build and noted
  here when it lands.
- The Company Brain grows from the current structured record (profile, goals,
  competitors, …) toward an entity/relationship graph (phase 2). That graph's
  storage shape, if it needs one beyond the existing table, gets its own ADR when
  phase 2 is designed — this ADR does not pre-commit it.
- A solution-architecture doc (`docs/architecture/solution-architecture.md`) should
  be written for the epic; this ADR records the direction, not the full design.

## Revisit trigger

Revisit if any of:
- Onboarding **completion rate** drops materially against the 0067 catalogue
  baseline, or support/feedback shows the conversation feels slower or more
  effortful than the form it replaced (the brief's whole premise is that it feels
  like *less* work — if it does not, the premise is wrong).
- The **no-model** population is larger than expected, making an LLM-first
  onboarding a barrier for a meaningful share of new workspaces.
- The adaptive questioning proves hard to keep bounded — conversations routinely run
  long or wander — such that a lightly-structured flow would serve users better.
- Phase 2's graph needs a knowledge-model richer than `company_brain` can carry,
  forcing a schema decision that reopens the "reuse vs. build" call made here.
