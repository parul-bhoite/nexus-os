# 0003. The single brand accent is the logo blue, not amber

- **Status:** Accepted
- **Date:** 2026-10-09
- **Deciders:** @parul-bhoite

## Context

The NEXUS OS web app (`apps/web`) carries exactly one accent colour — the "single
spark" established by ADR 0072: active state, focus ring, key-metric highlight,
and the upper-right arm of the X logo. Every other colour is the monochrome
neutral ladder. That accent was a warm amber (`gold-500 = #E2881F`).

The product's logo was updated to an X whose upper-right arm is a vivid blue.
Parul asked for that blue to replace the amber "across the application", so the
accent and the logo agree.

The accent is defined once, as the `gold` colour scale in
`apps/web/tailwind.config.ts`, and surfaces everywhere through composed token
names (`gold-500`, `bg-gold-100 text-gold-700`, `ring-gold-500`) plus the
`--accent` CSS variable in `globals.css` (which SVG `fill`/`stroke` read, since
Tailwind cannot reach them). Nothing in component code holds a raw accent hex.

## Decision

Redefine the `gold` scale values to the logo blue, in place, keeping the token
name `gold`. The anchor steps:

| Step | Was (amber) | Now (blue) |
|------|-------------|------------|
| 500 (DEFAULT, `--accent`) | `#E2881F` | `#1E6FFF` |
| 600 (`--accent-strong`)   | `#C4710F` | `#0E57DB` |
| 700 (accent text on white)| `#9A560A` | `#0B429E` |
| 400 (filled accent + dark text) | `#E89A3C` | `#4E8BFF` |

Full scale `50–700` updated to a coherent azure ramp. The same values are
mirrored in the two other files allowed to carry literal accent values: the
static favicon `app/icon.svg` (accent arm) and `design-previews/tokens.css`
(the onboarding-preview token mirror). The focus-ring box-shadow literal in
`tailwind.config.ts` was also updated (`#E2881F` → `#1E6FFF`).

The ambient background washes that carried "one breath" of the accent were, at
the time, hardcoded as the amber `rgba(226,136,31,…)` directly in component code
(`Hero.tsx`, `Pillars.tsx` spotlight, `OnboardingAura.tsx` ready-state). Rather
than swap one literal for another, these were moved to
`color-mix(in srgb, var(--accent) N%, transparent)`, so the background shade now
follows the accent token and no raw accent hex remains in component code.

## Options considered

### A. Redefine the `gold` scale values in place (chosen)
The token file's own comment prescribes this: "redefining the values in place
reskins every component that composes these names, so the diff stays in this
file … rather than spreading across the app." One scale edit reskins every
accent surface; the diff is confined to the token sources plus the one static
SVG. The name `gold` becomes a misnomer, mitigated by updating the surrounding
comments to say "the accent (logo blue)".

### B. Rename `gold` → `accent` across the app, then set blue values
The semantically correct end state, and the rename ADR 0072 itself anticipated.
But it touches ~40 component files for a colour change, enlarging the blast
radius and the review surface with no visual difference over Option A. Deferred
to a later naming cleanup (together with `clay` → `warning`).

## Reasoning

The accent is a single source of truth by design, so changing it should be a
single edit, not a sweep. Option A keeps the change auditable and reversible
(revert the scale) and matches the discipline the token layer was built for.
Contrast was verified against the surfaces each step is used on:

- `gold-700` text on white: **9.2:1**; on `gold-100` pills: **7.2:1** (AA, small text).
- `gold-400` fill with `ink-900` text (the one dark-surface filled control,
  the Pricing "Most complete" pill): **5.7:1** (AA, small text).

Verified live against the dev server: `--accent` resolves to `#1E6FFF`, the
logo arm, hero flourish, Company Brain mark and sparkline render blue, and the
computed pill colours match the table above.

## Consequences

- One accent, now blue, matching the logo; no amber remains in the app.
- The token name `gold` no longer describes its value. Comments were updated so
  the file does not misdescribe itself, but the eventual `gold` → `accent`
  rename (Option B) is now more clearly owed.
- `design-previews/tokens.css` and `README.md` were already drifted from the
  post-0072 neutral palette (they still carry the pre-0072 navy/steel values);
  this change corrects only their accent rows, not the wider drift.

## Revisit trigger

Do the `gold` → `accent` (and `clay` → `warning`) rename in a dedicated cleanup,
at which point this value definition moves under the new name. Revisit the scale
if the logo blue itself is re-specified.
