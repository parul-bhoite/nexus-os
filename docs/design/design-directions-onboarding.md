# Design directions — the combined onboarding flow

**Feature:** merging `/register-company` and `/onboarding/agent` into one
continuous journey — company details → Areas of Interest (multi-select) →
tailored questions (tap-to-answer) → enter workspace — per ADR 0067 (Engine C
hybrid, Flow A one route, server phases intact).

**Status:** three directions explored and previewed. Awaiting the product
owner's choice. Nothing below has been implemented — previews only.

**Previews:** `apps/web/design-previews/onboarding-a-editorial.html`,
`onboarding-b-board.html`, `onboarding-c-conversation.html`, all linking to
`apps/web/design-previews/tokens.css` (the one file in that folder carrying raw
token values — colour, radius, shadow, motion, type — mirrored verbatim from
`apps/web/tailwind.config.ts` and `apps/web/app/globals.css`). Open any of the
three `.html` files directly in a browser; no build step, no server.

## Grounding — what these previews follow, and why

- **The design system is the cut-paper navy/gold palette in
  `tailwind.config.ts`** (ink, steel, slate, bone, gold, clay — Fraunces +
  Inter + JetBrains Mono), **not** the ADF magenta/aubergine system a generic
  skill notice names. This is settled explicitly in ADR 0043, which exists
  precisely because the two systems can be confused. All three previews use
  only these tokens.
- **No dark theme exists anywhere in this codebase** — no `dark:` classes, no
  theme provider, every screen from the landing page to the dashboard is one
  light paper ground. These previews are single-theme accordingly, rather than
  inventing a second theme the rest of the product does not have.
- **Areas of Interest maps to the real backend**: `workspace_department`,
  `POST /onboarding/departments`, floor of one, 3–5 recommended, Chief of Staff
  (`Department.EXECUTIVE`) automatic and **never shown as a choice** — all per
  `services/api/app/domain/departments.py`. The six selectable cards in every
  direction are Marketing, Sales, Finance, Operations, People, Strategy, using
  the exact accent-per-department mapping already live on the marketing site's
  Directors section (`apps/web/lib/content.ts`), for recognisability rather
  than inventing a new colour code.
- **Tailored-question copy is drawn from the real catalogue** where it exists
  (`services/api/app/domain/onboarding.py`) — "What does your company sell?",
  "Which currency do you report in?", "What is your average deal size?", "What
  is your monthly marketing budget?", fiscal year, etc. — with their real `why`
  strings. Suggestion chips that are not literally in the catalogue excerpt
  reviewed are clearly illustrative UI copy (generic buckets like "1,000–10,000
  OMR"), not a fabricated result, consistent with the product's "never invent a
  number" rule; any text that reads as an inferred finding about the company
  (the scan brief) carries a visible **Illustrative** tag.
- **Engine C (hybrid) is designed for, not assumed.** Every direction's fourth
  screen shows both paths: the scan + brief (model configured) and the
  no-model-configured fallback, per ADR 0011 — absence is a supported state,
  not a degraded one.

## The three directions

### A — The Letter (calm, editorial)

One continuous document the person reads and answers down, a full screen per
stage, no visible step rail — just a quiet "Part 2 of 3" eyebrow. Areas of
Interest is a **vertical list of rows** to check, not a card grid; tailored
questions appear **one prompt at a time** in a large serif (Fraunces) headline
with chips and a "why we ask" line directly beneath it, with a quiet "Skip this
one" always available. The scan moment is a thin sweeping rule and a short list
of what was read, then the brief as one plain paragraph.

**Structural answer:** progressive disclosure, strictly sequential, one
decision asked at a time — closest to reading a well-written letter.

**Optimises for:** the lowest cognitive load per screen; the calmest possible
reading of "too informative and tiring." Generous whitespace, four type sizes,
nothing competing for attention.

**Sacrifices:** overview. There's no way to see all six departments or all
nine questions at a glance, so someone who wants to blitz through quickly has
to click through steps one at a time rather than scanning everything at once.

**Suits:** a founder who is tired, reading on a phone or in a spare five
minutes between meetings, who wants the product to lead rather than to
present a workspace of choices.

**Motion (Framer Motion intent):** each full-screen stage is a single
`fadeUp`-style entrance (`--ease-out`, `duration.slow`) — see `lib/motion.ts`'s
own `fadeUp`. No step transition animates sideways; each new screen simply
rises in place, which is the calmest of the three. Chips and checkboxes use
`duration.micro`/`duration.base` for their own press/select feedback only.

### B — The Board (tactile, card/canvas-driven)

Areas of Interest is a **grid of department tiles** (reusing the paper-cut
"director mark" language from `Directors.tsx`) that the person taps; each
selection **animates into a "your team" tray** at the top of the canvas, so
the founder visibly assembles their executive team rather than ticking boxes.
Tailored questions become a **card deck** — one question centred per card,
chips arranged as a tag cloud, a dotted progress track (not a percentage) and
left/right arrows to move through the deck. The scan moment becomes a small
**orbiting mark** at the centre of the canvas with "found" facts flying in as
chips around it.

**Structural answer:** a spatial board the person manipulates — selecting is
visibly building something, and the question deck is swiped/advanced through
rather than read down a page.

**Optimises for:** delight and a sense of visible progress and "my team is
forming" — the most literal answer to "beautiful" and "less tiring," because
each tap has a small, satisfying payoff (the tray fills in).

**Sacrifices:** density and build cost. It's the most custom interaction
pattern of the three (tray choreography, deck navigation, orbit animation),
the most engineering and motion-review surface, and a founder in a hurry has
to go through the deck one question at a time with no way to see everything
left at once.

**Suits:** a product that wants onboarding itself to be a moment of delight
worth remembering — most apt if NEXUS wants this screen to do some of the
"wow" work the rest of the marketing site already does.

**Motion (Framer Motion intent):** tray chips enter with a `popin`-style
scale-from-0.95 (`duration.emphasis`, `--ease-out`) — never `scale(0)`, per the
house rule. Tile hover lifts by `transform` only (`duration.base`), never
moving neighbours. The question deck's dots use `layout` for the "current"
dot's width change, eased with `--ease-inout` (a reflow, not an entrance). The
orbit rings are the one CSS `animation` left running continuously and must be
justified against the "should this animate at all" table — it is Rare/
first-time (onboarding only), so it's in scope, but it is the first thing to
cut if reduced-motion or review flags it as too much for a form screen.

### C — The Conversation (chat-like, continuous thread)

Everything — company details, the Areas of Interest multi-select, and every
tailored question — renders as **one continuous scrolling transcript**, in the
product's own voice, with rich inline widgets (a multi-select "card" message,
chip rows under a question bubble) rather than page-per-step. The ambient
`OnboardingAura` wash and mark (`components/onboarding/OnboardingAura.tsx`) sit
behind the whole thing exactly as built today, changing state (idle / thinking
/ ready) as the conversation progresses, and the sticky composer band at the
foot is the same shape as the current `Composer`.

**Structural answer:** a chat transcript with inline rich components;
navigation is implicit (scroll, and the composer always at the foot) rather
than an explicit rail or step indicator.

**Optimises for:** continuity with the product's existing investment and
voice — this is the lowest-redesign-delta direction, keeps `OnboardingAura` and
the "it's a chat and only a chat" principle already documented in
`AgentOnboarding.tsx`'s own docstring, and reads as the most literal merge of
the two pages into one artifact.

**Sacrifices:** this is structurally the closest to what the owner already
called tiring, so it only works if the pacing is genuinely compressed — short
agent lines, no restating what was already asked, the multi-select and
questions kept visually light inside the thread (which this preview does, but
it is the direction most at risk of regressing back into "a long scroll")
and it has no overview either: a long transcript cannot be scanned the way a
list or board can.

**Suits:** if the product's priority is minimising engineering/design delta and
preserving the existing conversational identity and the ADR 0066 scan
animation investment, with the pacing risk managed deliberately rather than
inherited by accident.

**Motion (Framer Motion intent):** new bubbles enter with `fadeUp`
(`duration.slow`, `--ease-out`) exactly as `AgentOnboarding.tsx` already does;
the aura wash crossfades over `duration.slow`-class time on state change
(mirroring the real component's `transition-[background] duration-1000`,
which is slower than the standard scale because it is atmosphere, not
feedback); the presence mark's outer ring only spins while a request is in
flight — motion means work, never decoration, exactly as the existing
component's docstring argues.

## Mandatory states, covered in every preview

Each `.html` file includes, per data-backed screen (Areas of Interest and
Tailored Questions), a **Ready / Loading / Empty / Error** switch (vanilla JS,
no React, since these are static previews) and, for the selection control used
on that direction (checkbox row, department tile, or inline pill) and for a
suggestion chip, a small **states legend** showing rest / hover / active /
focus-visible / selected explicitly, in addition to the real, working
`:hover`/`:active`/`:focus-visible` behaviour on every live control in the
page. The scan/wrap-up screen in every direction also switches between the
scan-configured path and the "no language model configured" fallback (ADR
0011), plus a scan-failed error state that does not block completing
onboarding.

## Accessibility notes common to all three

- Every selection control (checkbox row, tile, pill) is a real `<input
  type="checkbox">` with an associated `<label>`, not a `div` with a click
  handler — keyboard-operable and correctly announced by construction.
- Touch targets are ≥44px (`min-height:44px` on rows, tiles, pills, chips).
- Focus is visible everywhere via `:focus-visible` using the same
  `--steel-500` ring the rest of the product uses (`Field.tsx`, `.control` in
  `globals.css`), not a new focus style.
- State is never colour-only: selection also carries a check glyph and a
  border-weight change; error states carry an icon-free but explicit heading
  ("Could not reach the account service") rather than relying on the clay
  tint alone.
- `prefers-reduced-motion: reduce` collapses every animation/transition to
  effectively zero in all three files, mirroring `globals.css`'s existing
  global rule.

## Recommendation

**Direction A, The Letter**, with **one piece of Direction C folded in**: keep
`OnboardingAura`'s ambient wash/mark running quietly behind Direction A's pages
rather than discarding it, since it is a real, already-shipped, low-cost
signal of "something is happening" that costs nothing extra once it exists.

Reasoning:

- The owner's verdict was specifically **"too informative and tiring."** That
  is a pacing and density complaint, not a request for more spectacle. Of the
  three, A is the only one that structurally cannot show more than one thing
  at a time — it makes the calm the owner asked for the default rather than
  something the content has to be edited into.
- **B is the most fun but the riskiest against the stated problem.** A tray
  that fills in and a swipeable deck are genuinely delightful, but delight is
  not what was asked for here, and it is the most expensive to build (new tray
  choreography, deck navigation, orbit motion) for a screen whose brief was
  "make it feel shorter," not "make it feel more alive."
- **C keeps the most continuity with existing code but carries the most
  regression risk toward the exact complaint.** A transcript is additive by
  nature — every new message is one more thing on the page — so without
  continuous editorial discipline it tends to regrow into the long scroll the
  owner already rejected. It is the right answer if minimising engineering
  delta is the overriding constraint; it is not the safest answer to "less
  tiring."
- A still benefits from the aura: a quiet ambient wash behind an otherwise
  static page is "something is happening" for free, and reusing it (rather
  than redrawing a new idle/thinking indicator for A) protects the ADR 0066
  investment without inheriting C's pacing risk.

This is a recommendation, not a decision — the choice and final reasoning
belong in the section below once made.

## Decision

*(To be filled in once the product owner chooses: which direction, any
hybrid elements taken from another, and the reasoning. This will also be
logged as a consequential decision requiring an ADR, and handed off to
`frontend-engineer` for implementation — not implemented as part of this
design-exploration pass.)*
