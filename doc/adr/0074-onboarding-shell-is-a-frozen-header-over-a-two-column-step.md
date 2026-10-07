# ADR 0074 — The onboarding shell is a frozen header and tracker over a two-column illustrated step

- Status: Accepted
- Date: 2026-10-07
- Amends: [0073](0073-onboarding-is-a-six-step-wizard-not-a-live-brain-conversation.md)
  (the six-step wizard). This changes only the shell's *layout*, not the steps,
  the flow, or the engine mapping.
- Related: ADR 0072 (monochrome visual system with amber accent).

## Context

ADR 0073's first shell put the logo, the "Guided setup" chip and the step
tracker together in one bordered header, then centred each step's content in a
single column on a `bone-100` ground. Reviewing step 1, the product owner asked
for a different frame: freeze the header, separate it from the tracker with a
thin line, pull the tracker out into its own band, make the background white,
and give each step a two-column layout — a themed animation on the left and the
step's content on the right — the same for every step.

## Decision

The onboarding shell (`OnboardingStepper`) is three bands on **white**, locked
to the viewport (`h-screen` + `overflow-hidden`) so only the body scrolls:

1. **A frozen header** — the shared `Logo` (ADR 0072) and the "Guided setup"
   chip, with a hairline bottom border.
2. **The step tracker in its own band** below that border — "Step N of 6", the
   numbered rail, and the step labels. It is no longer inside the header.
3. **A two-column body** — a decorative, looping illustration on the left
   (`OnboardingStepArt`, one scene per step: a building, department tiles, chat
   bubbles, a document stack, a tool hub, a knowledge graph) and the step's own
   content on the right, divided by a hairline. The left panel is `aria-hidden`
   and drops below `lg`, where the form needs the width.

Every step uses the same frame; the chatbot keeps `fill` so it owns the right
column (its log scrolls, its composer pins to the bottom). The illustrations are
monochrome-plus-amber per ADR 0072, and every loop is gated by `useMotionSafe` —
under `prefers-reduced-motion` each scene renders a still resting state. The
shell passes `active` (agent thinking) so the interview and Brain scenes quicken
during a model call rather than sitting idle.

## Reasoning

- **A frozen header and tracker keep "where am I" on screen** through the steps
  that scroll (the interview, documents, tools), which a tracker that scrolled
  away with the content could not.
- **Separating the tracker from the header** makes each band do one job — brand
  and exit on top, progress below — rather than crowding both into one row.
- **White over the earlier bone ground** is what the owner asked for and reads
  cleaner behind line-art illustrations.
- **An illustration per step** gives the left column a job on wide screens
  beyond whitespace, and makes each step recognisable at a glance. They are
  strictly decorative: `aria-hidden`, reduced-motion-safe, and never the only
  signal of anything — the content and the tracker carry the meaning.

## Consequences

- The ambient `OnboardingAura` wash is dropped from the shell (the ground is
  white now); `OnboardingAura`/`PresenceMark` remain in use inside the chat and
  Brain steps for their thinking/ready marks.
- `StepperShell`'s props are unchanged (`current`, `aura`, `fill`, `children`),
  so the orchestrator needed no change.
- The right column is a readable `max-w-2xl` measure — the width the reused
  `ToolsStep`/`DocumentsStep`/`BrainReview` were already built for in the chat
  column, so they carry over without rework.

## Revisit trigger

Revisit if the `h-screen`/`overflow-hidden` lock fights a step whose content
genuinely needs the whole page to scroll on small laptops, if the illustrations
prove to be noise rather than orientation (the owner or feedback calls them
decoration that distracts), or if a step's content needs more width than the
two-column split leaves it.
