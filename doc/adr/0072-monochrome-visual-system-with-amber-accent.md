# ADR 0072 — The product's visual system is monochrome, with a single amber accent

- Status: Accepted
- Date: 2026-10-07
- Supersedes: the "cut-paper" visual direction — the navy/bone/gold/clay palette and
  the Fraunces serif display — that the token files (`tailwind.config.ts`,
  `globals.css`, `lib/motion.ts`) and `components/ui/Logo.tsx` carried.
- Related: ADR 0071 (onboarding on a white ground) — consistent with this; the
  white ground stays, the warm bone wash goes.

## Context

The product owner asked for a full visual redesign: minimal, modern, soft,
attractive. A first proposal — a soft blue palette (lifted from the logo) with a
Plus Jakarta Sans + Inter pairing and pastel category tints — was shown and
rejected as *dull*, both the colour and the type.

A second proposal was shown and accepted: a **monochrome** interface where type,
scale, contrast and whitespace carry the design rather than colour. Reviewed live,
the owner approved the direction and the typeface pairing, and made one change to
the colour rule: **do not tie the accent to the logo's blue** (the logo may be
re-coloured) — *"choose a complement colour that goes with the theme."*

The branding anchor is the new **NEXUS** mark: an **X** built from two strokes,
one arm carrying the accent. It replaces the three-layer cut-paper glyph and the
"NEXUS OS" wordmark; the wordmark is now just **NEXUS**.

## Decision

1. **The interface is monochrome.** A cool-biased neutral ladder from near-black
   `#0B0C0E` through greys to white is the entire UI palette. Black is the
   primary action and text colour; greys carry structure, hierarchy and surface
   steps. No colour is used to decorate.

2. **One accent: warm amber `#E2881F`** (with a ramp). It is the single spark —
   active states, focus rings, a key-metric highlight, and the logo's accent arm.
   **Amber never fills a button:** the primary button is black with white text, so
   there is no contrast problem, and the accent stays rare enough to mean
   something. Amber *text* on white uses the darkened `amber-700` step (AA).

3. **Semantic colour is separate and restrained.** A muted warning red is kept for
   genuine error state; direction (up/down) reads through weight and ▲▼ marks, not
   a second palette. Per the design rule, a semantic colour is not "the accent."

4. **Typography is Bricolage Grotesque (display) + Hanken Grotesk (body) +
   JetBrains Mono (figures/tags).** The serif (Fraunces) is retired. The
   characterful grotesque at large sizes is what answers "dull"; the mono keeps
   tabular figures and the "every number is computed" credibility.

5. **Category identity is typographic, not chromatic.** Departments are told
   apart by a bold initial chip, a mono tag and grey surface steps — the pastel
   category tints of the rejected proposal are dropped.

6. **Light only.** No dark mode in this pass. The tokens remain structured so one
   can be added later without re-skinning components.

7. **Implementation is token-first.** The existing colour scales are *redefined*
   in place rather than renamed — `ink`/`bone`/`steel`/`slate` become the neutral
   ladder and surfaces, `gold` becomes the amber accent (it was already the
   "single accent" semantic), `clay` becomes the restrained warning. Because every
   component already reads tokens (the standing design-token rule), the re-skin
   propagates without touching component colour literals; per-page work is layout
   polish, not logic.

## Reasoning

- **Monochrome is the honest answer to "minimal, modern, not dull."** The first
  proposal was dull *because* it leaned on colour to be interesting. Removing
  colour forces the design onto type, scale and space, which is where a premium,
  editorial feel actually comes from — and it suits a product whose whole claim is
  sober, grounded numbers rather than decoration.
- **Amber because the neutrals are cool.** Warm-against-cool is deliberate
  temperature contrast; amber is the complement of the blue-grey cast in the
  ladder, so the one spark reads as *chosen*, not arbitrary. Decoupling it from the
  logo blue was the owner's call and is the stronger move: the logo arm is
  re-coloured to the amber so brand and UI agree on a single accent.
- **Black buttons, amber spark.** An amber fill cannot carry white text at AA and
  reads cheap with dark text; making black the action colour keeps contrast
  perfect and keeps amber rare. "The one spark" only works if it is actually rare.
- **Redefining tokens rather than renaming** is what makes a product-wide reskin
  reviewable: the diff is concentrated in the token files and the logo, and the
  rest of the app inherits it. Renaming scales would have touched every file and
  buried the decision in noise.

## Consequences

- `tailwind.config.ts`, `globals.css`, `lib/motion.ts`, `app/layout.tsx` and
  `components/ui/Logo.tsx` change; a favicon/app-icon is added. Components that
  only compose tokens change appearance with no edit.
- The cut-paper paper-grain texture, the bone focus-offset helper and the
  serif-heading rule are removed or re-pointed.
- Screenshots and mocks that show navy/bone/gold or the serif are now historical.
- `gold`/`clay` token *names* now hold amber/warning values; a later cleanup may
  rename them to `accent`/`warning`, but not in this change — the point here is a
  concentrated, reviewable diff.
- The "Illustrative" tag and the content rule (never invent a number, no invented
  customers/logos) are untouched — this is presentation only; no functionality or
  user-flow changes.

## Revisit trigger

Revisit if any of:
- The monochrome ground reads as *austere* or *clinical* in daily use rather than
  calm — at which point the restrained use of amber (or a second neutral warmth)
  may need to widen.
- Users cannot tell departments apart without colour, i.e. the typographic-only
  category identity fails the glance test the pastel tints were meant to serve.
- Dark mode becomes a requirement — the token structure anticipates it, but the
  amber and the greys will need their own dark values checked for contrast.
- A later decision renames the repurposed `gold`/`clay` scales to `accent`/
  `warning`; this ADR's token-redefinition approach is explicitly an interim.
