# 0043 — The cut-paper palette is the design system

**Status:** Accepted
**Date:** 18 September 2026
**Depends on:** ADR 0011 (the language model is optional — the same "absence is a
supported state" reasoning shapes the loading and empty states below)
**Context:** A full UI/UX audit and redesign pass across the marketing site and
every signed-in surface, 17–18 September 2026

## Context

The `dev-team` plugin's standing rules, delivered to every session in this repo
as a SessionStart notice, state:

> `--primary` (#E331D0) is the single accent; `--logo-ink` (#150027) is the deep
> ink. There is NO purple gradient — #883E90 and #D242CB are a defect.

That is the **ADF brand**. This repository's design system is the navy-and-gold
cut-paper palette in `apps/web/tailwind.config.ts` — ink `#091F46`, steel
`#37729C`, gold `#EFBF6A`, bone `#E9E4DE`, clay `#A55D35` — with Fraunces, Inter
and JetBrains Mono. The two are different products' identities, and nothing in
the repository said which one governs.

**This is not a cosmetic ambiguity.** The plugin's write guard refuses hex
literals in component code, so an agent that reads the notice literally will be
blocked, will look for the token file, will find a palette that contradicts the
notice, and has to guess. The guess is costly in one direction: the landing
page's hero, the Loop mock, the Company Brain orbit, the auth panel and the
closing CTA are all hand-built SVG in the navy/gold palette. Re-theming to
magenta means redrawing every one of them.

The decision was put to Parul with both options and the redraw cost stated.

## Decision

**The cut-paper palette in `tailwind.config.ts` is the design system for NEXUS
OS. The `dev-team` magenta rules belong to a different product and do not apply
here.**

Three things follow, and they are the substance of this ADR rather than the
colour choice itself.

**The token contract.** Raw values may appear in exactly three places:
`tailwind.config.ts`, `app/globals.css`, and `lib/motion.ts`. Everything else
composes names. The one standing exception is `components/ui/Logo.tsx`, whose
values are SVG `fill` attributes Tailwind cannot reach; it says so in its own
docstring.

**The palette is unchanged; the rules for using it are new.** The audit found
the same three failures everywhere, and each is now a rule rather than a habit:

- **Gold is attention, not decoration.** An accent that appears on every card
  cannot mark the one card that needs reading.
- **Clay is exceptional state only.** Six dashboard tiles carried a clay
  sentence about unconfirmed records *at all times*. A warning that is always on
  is not a warning.
- **One muted grey per surface, and it passes.** `ink-400`, `slate-400` and
  `bone-400` all appeared as "muted text" at 11–14px; two of the three failed
  4.5:1. `ink-400` was darkened from `#5C769E` to `#4A6489` and a `gold-700`
  step added for small type. Measured after: eleven contrast failures, then zero.

**Provenance is ordered, not hidden — and this is the load-bearing constraint.**
The audit's central finding was that a block card was seventeen lines tall and
one of them was the figure. The obvious fix — move `figure.measures` and the
provenance line behind the disclosure with the arithmetic — was implemented, and
it was wrong. `BlockCard`'s own docstring already carried the reason, and the
test suite enforced it: `figure.measures` names what was counted *and what was
not*, so a correct number under a headline promising more than it measured is
"the one dishonest thing this could ship". A disclosure one click away does not
fix a misdescribing headline.

So the rule is: **what changes the meaning of the figure stays on its face; what
explains how the figure was built goes behind one disclosure.** Nothing was
deleted, and the hierarchy was repaired by moving the *other* text down rather
than by making the number much bigger: the figure went 30px → 36px, the
methodology 14px → 13px, and the provenance 14px → 11px in the quietest
foreground the palette has. The completeness caveat went from a clay paragraph
to a two-word badge — and the arithmetic, which nobody reads unless they are
disputing a number, moved into the drawer. The specification ids stayed on the
card face for the
same class of reason: a `planned` tile carries no figure, so it has no
drawer to hide them in, and traceability from a tile to its capability id is a
property the product asserts.

## Consequences

- **A second design direction cannot be introduced by a plugin notice.** An
  agent that reads the `dev-team` rules now has this file to reconcile them
  against, which is the whole point of writing it down.
- **`text-title` is an alias of `text-section`.** Sixteen files already said
  `text-title` for what is a section heading, and pointing the alias at 21px is
  what collapsed the old 30px-against-34px wobble between a page title and a
  section title into a real step. Nothing had to be renamed.
- **Retired tone names still resolve.** `lib/content.ts` names `gold`, `clay`,
  `steel` and `slate` per pillar; Pillars maps all four onto the two neutrals
  that replaced them rather than editing content that carries no meaning.
- **`prefers-reduced-motion` is now enforced in two places, and both are
  needed.** `globals.css` collapses CSS animations and transitions;
  `MotionProvider` sets framer-motion's `reducedMotion="user"` at the root,
  because framer animates inline styles the media query cannot reach. Deciding
  it per component is what caused a hydration mismatch on every revealed
  section — `useReducedMotion()` returns `false` on a server and `true` in a
  browser with the setting on, so React discarded and re-rendered the subtree.
  The setting whose purpose is a calmer page was making it do strictly more
  work, and only for the readers who asked for less.
- **The write guard's file list and this repo's token files disagree on one
  name.** The guard exempts `tokens.css`, `theme.css`, `tokens.ts`; this repo
  uses `tailwind.config.ts` and `globals.css`, which it also exempts. No action
  needed, recorded so the next mismatch is not read as a new problem.

## Revisit trigger

**Revisit if NEXUS OS is brought under the ADF brand as a commercial decision**
— not if another plugin notice repeats the magenta rules, which is the situation
this ADR exists to settle. A rebrand is a product decision with a redraw budget
attached: the five cut-paper illustrations, the wordmark, and the auth panel.

Revisit the provenance rule if a capability ever ships whose `measures` string
is short enough to be a caption. The rule is a response to four-line methodology
paragraphs; a one-line one would not need the same treatment, and the ordering
above should not be applied mechanically to a card it was not written for.

## Alternatives rejected

**Re-theme to ADF magenta.** Rejected on the redraw cost and on the absence of
any evidence NEXUS OS is an ADF-branded product: the repository's own
documentation, its landing copy and its illustrations are consistently the
cut-paper identity, and the plugin notice is the only source saying otherwise.

**Keep both, switched by a theme token.** A second theme nobody has asked to see
is an untested surface that doubles every visual decision, and the illustrations
would still need redrawing for the branch that does not exist yet.

**Treat the plugin notice as authoritative and ask nothing.** The notice is
delivered as a standing rule, so following it silently was available. It would
have replaced the product's identity on the strength of a configuration file,
which is precisely the class of change that should not happen without somebody
choosing it.
