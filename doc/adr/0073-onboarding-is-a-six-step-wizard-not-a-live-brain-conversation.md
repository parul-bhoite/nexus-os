# ADR 0073 — Onboarding is a six-step wizard with a visible stepper, not a single conversation with a live Brain

- Status: Accepted
- Date: 2026-10-07
- Supersedes: [0069](0069-conversational-onboarding-with-live-company-brain.md) (the
  single-column chat with a live Company Brain panel beside it). Re-adopts the
  *staged* shape of [0067](0067-combined-onboarding-flow.md) while keeping 0069's
  adaptive chat as **one step inside it**.
- Related: ADR 0011 (the language model is optional), ADR 0022 (onboarding requires a
  model), ADR 0066 (the scan animation), migration 0024 (`onboarding_agent`).

## Context

ADR 0069 made onboarding a single conversational surface: a chat column that handled
the website read, the brief, **department selection, the adaptive interview, documents
and tools all in one scroll**, with a **live Company Brain panel** filling beside it,
then a persona-confirm and assembly. It shipped and works (see
`ConversationalOnboarding`).

The product owner, after walking the built flow, asked for a different shape: an
explicit **multi-step wizard** on `/register-company` with a **visible stepper and
status**, where area-of-interest and tools are their **own steps with their own
sections** rather than beats inside the chat, the **live Brain panel is removed from
the chat**, and the Company Brain is shown as a **read-only view at the end**. A
"scanning your company" loader covers the website read.

This is a deliberate reversal of 0069's "one conversation + live brain" direction. It
is recorded here rather than treated as mere implementation because it changes the
flow's information architecture and retires 0069's signature feature.

## Decision

Onboarding is a **six-step wizard**, mounted at `/register-company` and
`/onboarding/agent`, with a header and a stepper that shows all six steps and marks
each done / current / upcoming:

1. **Company Info** — name, website, role. Reuses `CompanyStage`.
2. **Area of Interest** — the department multi-select, pulled out of the chat.
   Reuses `AreasStage` (`fetchDepartments`/`saveDepartments`). Runs **before** the
   chat.
3. **Chatbot** — the adaptive interview **only**: the "scanning your company" loader
   while the site is read, the three-question fallback when the site is unreadable,
   then the agent's discovery questions. **No department picker, no tools, no live
   Brain panel.**
4. **Documents** — `DocumentsStep`, its own step (the product owner chose a discrete
   step over folding it into the chat).
5. **Tools** — `ToolsStep`, pulled out of the chat.
6. **Company Brain** — a **read-only** view of the assembled Brain (facts grouped by
   provenance, reusing `BrainPanel`) with a single "open my workspace" action to the
   dashboard. Corrections happen later in Settings, not inline here.

The flow is driven by the existing `onboarding_agent` engine; the wizard maps the
engine's phases onto the steps:

| Step | Engine phase(s) |
|---|---|
| 3 Chatbot | `analysing` (loader) → `brief` (auto-confirmed, not shown) → `discovery` |
| 4 Documents | `documents` |
| 5 Tools | `tools` |
| 6 Company Brain | `persona` (auto-confirmed, not shown) → `assembling` → `ready` |

**The crawl is pre-warmed.** The engine is started the moment the company exists
(end of step 1), so the website read runs in the background during step 2 and the
"scanning your company" loader in step 3 is usually brief or already done.

**The `brief` and `persona` confirmation beats are removed from the user flow.** The
product owner chose a read-only Brain view at the end, so the facts the crawl read and
the persona the builder wrote are surfaced read-only in step 6 rather than confirmed
interactively mid-flow. The engine still has both phases; the wizard advances through
them without a user gate (`confirmBrief({})`, then the `finish()` loop).

The no-model path (ADR 0011/0022) is unchanged: a `ModelUnavailableError` still
renders a plainly-stated "guided setup is unavailable" screen, never a fabricated
conversation or a silent catalogue fallback.

## Reasoning

- **The owner holds the flow.** 0069 was itself a product-owner direction; this is the
  same authority revising it after seeing it run. The decision docs (`doc/11`) do not
  pin the chat-vs-wizard shape, so there is nothing here to re-decide against — only to
  record.
- **A stepper is legible in a way a long scroll is not.** The 0069 chat put six
  distinct jobs in one column with only a phase label to say where you were. Discrete
  steps with a status rail tell the user how much is left — the thing a wizard does
  that a conversation cannot.
- **Area-of-interest and tools are selections, not conversation.** Both are
  closed-set multi-selects already built as standalone components (`AreasStage`,
  `ToolsStep`). Giving each its own step is a better fit than a chat beat and removes
  the two least conversational interruptions from the interview.
- **This does not abandon the invariant 0069 defended.** "Never invent a number, show
  the source" still holds: the Brain is still provenance-tagged, still assembled from
  the same engine, and still shown with its sources — now read-only at the end
  (reusing `BrainPanel`) and on the dashboard, rather than live beside the chat.
- **Reuse over rebuild, again.** Every step but the stepper shell and the slimmed chat
  is an existing, tested component. The engine, crawler, brain table and provenance
  ledger are untouched.

## Consequences

- `ConversationalOnboarding` and its live `BrainPanel`-beside-chat layout are retired
  from the live path. Both components stay in the tree until a dedicated removal change
  (the same treatment 0069 gave `AgentOnboarding`), so their tests keep passing.
  `BrainPanel` itself is **not** retired — it is reused, read-only, as step 6.
- `OnboardingEntry` becomes the stepped orchestrator (resume maps the engine phase and
  the saved departments onto the right step).
- The interactive `brief`/`persona` corrections 0069 surfaced are no longer in the
  flow. The only place to correct a Brain fact during first-run is Settings / the
  Company Brain page afterwards. If first-run correction proves important this is the
  thing to revisit.
- A solution-architecture doc (`docs/architecture/solution-architecture.md`) is still
  owed for the onboarding epic; this ADR records the direction, not the full design.

## Revisit trigger

Revisit if any of:
- Completion rate drops against the 0069 conversational baseline, or users report the
  stepper feels more like a form than the chat it replaced (0069's whole premise was
  that onboarding should feel like *less* work).
- Removing the inline `brief`/`persona` confirmation measurably raises the rate of
  wrong facts reaching the dashboard uncorrected — i.e. the read-only end view is not
  enough and first-run correction needs to come back.
- Pre-warming the crawl at step 1 proves unreliable (the read routinely not finished by
  step 3), such that the "scanning" loader becomes a wall rather than a brief wait.
- The engine's fixed phase order (`documents` before `tools` before `persona`) comes to
  conflict with a desired step order, forcing an engine change rather than a UI remap.
