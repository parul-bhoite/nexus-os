# NEXUS OS — Marketing Site

The public landing page: the first interaction point where a visitor understands
what NEXUS OS offers. Next.js (React on Node), statically prerendered.

```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # production build
npm start        # serve the production build
npm run lint
npm run typecheck
```

## Why Next.js

The architecture document specifies "Next.js; SSR the marketing site for SEO,
dynamic render the dashboard". This app is the marketing half. The whole page
prerenders to static HTML at build time (`○ (Static)` in the build output), so
crawlers get full content and the first paint is immediate — the interactive
pieces hydrate afterwards.

## Design system

The palette is taken verbatim from the supplied design reference — a layered
paper-cut landscape:

| Token   | Hex       | Role                                     |
| ------- | --------- | ---------------------------------------- |
| `ink`   | `#091F46` | Body text, dark panels, primary buttons  |
| `steel` | `#37729C` | Secondary accents, data marks            |
| `slate` | `#7699AE` | Muted text on dark, illustration masses  |
| `bone`  | `#E9E4DE` | Alternating section surfaces, paper edge |
| `gold`  | `#1E6FFF` | The accent (logo blue) — sparingly       |
| `clay`  | `#A55D35` | Warm human accent, gaps and warnings     |

Each is expanded into a tint/shade scale in `tailwind.config.ts` so nothing
off-brand creeps in. The page background stays white; depth comes from bone
surfaces, soft directional shadows (`shadow-paper*`) and a fine SVG paper grain
on `body`.

**Type:** Fraunces (display) · Inter (body) · JetBrains Mono (labels and data
chips — the mono is a deliberate signal that a value came from a real source).

**Illustration:** every graphic is hand-authored inline SVG — no image requests,
no external CDN. `PaperLandscape` separates the scene into depth-ordered `<g>`
layers so each parallaxes independently; that separation is what reads as
stacked paper rather than a flat picture.

## Structure

```
app/
  layout.tsx          fonts, metadata, skip link
  page.tsx            section composition + JSON-LD
  globals.css         base layer, .paper surfaces, motion guards
components/
  sections/           one file per page section
  art/                SVG illustrations, product mocks, icon set
  motion/Reveal.tsx   scroll-reveal primitives
  ui/                 Button, Logo, SectionHeading, ScrollProgress
lib/
  content.ts          every word on the page
  hooks.ts            scroll, pointer-parallax, active-section
```

`lib/content.ts` is the single source of copy. Change wording there, never in a
component.

## Content rule

NEXUS OS sells on *never invent a number*. This page is held to the same
standard: no invented customer counts, logos, testimonials or results. Product
mocks carry a visible `Illustrative` tag, and the pricing block states plainly
that the figures are still being validated.

## Motion

Scroll reveals, the auto-advancing loop stepper, pointer parallax, marquees and
the orbit diagram. All of it is decoration, never information — everything is
wrapped in `motion-safe:` or checks `useReducedMotion()`, and `globals.css`
collapses animation and transition durations under
`prefers-reduced-motion: reduce`.

The loop stepper autoplays only while the section is on screen, and pauses
permanently on first interaction with a visible resume control.

## Accessibility

WCAG 2.1 AA is the target. Verified in-browser: single `h1`, no heading-level
skips, every control has an accessible name, meaningful SVGs carry
`role="img"` + `aria-label`, decorative SVGs are `aria-hidden`, landmarks and a
skip link are present, and all text colour pairs meet 4.5:1 (checked
programmatically against the token values).

The stepper is a real `tablist`/`tab`/`tabpanel` with `aria-selected` and
`aria-controls`; the FAQ is buttons with `aria-expanded`/`aria-controls`.

## Notes for the next change

- `AnimatePresence mode="wait"` for keyed swaps hangs under React 18 Strict
  Mode (the exiting child never completes, so the new one never mounts). The
  loop panel uses a keyed remount instead. Conditional presence
  (`{open ? <motion.div/> : null}`) is fine — the FAQ and mobile menu use it.
- `html, body { overflow-x: clip }` is load-bearing: reveal animations translate
  elements horizontally before they enter the viewport, which otherwise widens
  the document on narrow screens.
