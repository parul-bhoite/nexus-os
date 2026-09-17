'use client'

import { useReducedMotion, type Transition, type Variants } from 'framer-motion'

/**
 * The motion system. Every animation in the product resolves to a value here.
 *
 * ## Why tokens rather than per-component numbers
 *
 * The audit found twenty-seven infinite animations running at once on the
 * landing page, four different durations for the same gesture (a card lifting
 * on hover was 300ms in `Button`, 700ms in `Reveal`, unset in three tiles) and
 * an app shell whose mobile drawer had no transition at all. Those are not
 * taste disagreements; they are the absence of a decision. Naming the durations
 * by *role* means a component asks "what kind of change is this?" rather than
 * "how many milliseconds looks right here?", and two components answering the
 * same question get the same answer.
 *
 * ## The durations, and the reasoning behind each
 *
 * - `instant` (80ms) — a colour or border change under the pointer. Long
 *   enough not to snap, short enough that the control feels connected to the
 *   finger. Anything slower reads as lag on the *input*, not polish.
 * - `micro` (140ms) — a press, a checkbox, a chevron rotating. The gesture is
 *   already understood; the motion only confirms it landed.
 * - `base` (200ms) — the default. A tooltip, a dropdown, a tab indicator
 *   sliding, a toast arriving. This is where most things belong.
 * - `emphasis` (320ms) — something entering that changes what the page is
 *   about: a sheet, a modal, a drawer. Long enough to show *where it came
 *   from*, which is the only reason to spend the time.
 * - `slow` (480ms) — reserved for a first paint or a scroll reveal, where the
 *   element has not been on screen before so there is no interaction waiting
 *   on it. **Never** on anything a click is blocked behind.
 *
 * The hard rule, from the brief: motion is never the reason a task takes
 * longer. Nothing that gates input exceeds `emphasis`.
 *
 * ## Easing
 *
 * `out` for entrances, `in` for exits, `inOut` for a move between two
 * positions that are both on screen. An entrance that eases *in* looks like it
 * was dropped; an exit that eases *out* looks like it got stuck on the way out.
 *
 * ## Reduced motion
 *
 * `globals.css` collapses every CSS animation and transition when
 * `prefers-reduced-motion: reduce` is set, which covers hover states, the
 * hero's keyframed entrance and the skeleton sweep. It does **not** cover
 * framer-motion, which animates inline styles the media query cannot reach —
 * so every exported helper here takes the preference into account itself, via
 * `useMotionSafe`. The two mechanisms together are what make the setting
 * actually hold.
 *
 * What reduced motion does *not* do is remove feedback. A drawer still appears
 * and still disappears; it simply arrives at zero duration instead of sliding.
 * Opacity is kept where it is the only signal that something changed, because
 * removing it would leave a state change with no indication at all.
 */

export const duration = {
  instant: 0.08,
  micro: 0.14,
  base: 0.2,
  emphasis: 0.32,
  slow: 0.48,
} as const

export const easing = {
  out: [0.16, 1, 0.3, 1],
  in: [0.4, 0, 1, 1],
  inOut: [0.4, 0, 0.2, 1],
} as const

/**
 * Springs, for the two cases where a duration is the wrong model.
 *
 * A tab indicator and a drag follow a *position*, not a timeline: if the target
 * moves mid-flight a tween restarts and stutters, where a spring simply
 * redirects. Both are critically damped — no overshoot. A bouncing tab
 * indicator draws attention to the indicator instead of to the tab.
 */
export const spring = {
  indicator: { type: 'spring', stiffness: 420, damping: 38, mass: 0.7 },
  panel: { type: 'spring', stiffness: 320, damping: 34, mass: 0.9 },
} as const satisfies Record<string, Transition>

/**
 * Whether motion may be used, as a boolean rather than a hook result to be
 * interpreted at each call site.
 *
 * `useReducedMotion()` returns `true` when the user wants *less* motion, which
 * inverts at every call site and is read wrong about half the time. This
 * returns what the caller actually wants to know.
 */
export function useMotionSafe(): boolean {
  return !useReducedMotion()
}

/** A transition, built from the tokens, honouring the preference. */
export function useTransition(
  kind: keyof typeof duration = 'base',
  ease: keyof typeof easing = 'out',
  delay = 0,
): Transition {
  const safe = useMotionSafe()
  return {
    duration: safe ? duration[kind] : 0,
    delay: safe ? delay : 0,
    ease: easing[ease],
  }
}

/** Distances. Small on purpose: the brief asks for low amplitude. */
export const travel = {
  // A reveal. 16px, not the 28px the old `Reveal` used — at 28px a card looks
  // like it is being thrown into place, and on a page of twelve cards that is
  // twelve things moving a long way.
  reveal: 16,
  // A tooltip or dropdown leaving its trigger.
  pop: 6,
  // A sheet from the edge. Expressed as a percentage at the call site.
  sheet: 24,
} as const

/* ── Variants ──────────────────────────────────────────────────────────────
   Shared so that two dropdowns in different features cannot disagree about
   what opening looks like. Each takes the reduced-motion decision as an
   argument rather than calling the hook, so they stay plain data and can be
   used inside `AnimatePresence` children and in tests. */

export function fadeUp(safe: boolean, delay = 0): Variants {
  return {
    hidden: { opacity: 0, y: safe ? travel.reveal : 0 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: safe ? duration.slow : 0, delay: safe ? delay : 0, ease: easing.out },
    },
  }
}

export function fade(safe: boolean, delay = 0): Variants {
  return {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { duration: safe ? duration.base : 0, delay: safe ? delay : 0, ease: easing.out },
    },
  }
}

/**
 * A list that reveals its children in sequence.
 *
 * The stagger is capped by `staggerChildren` being small: 40ms across eight
 * cards is 320ms for the whole group, which is one `emphasis`. The old 80ms
 * stagger across a twelve-tile dashboard was just under a second before the
 * last tile appeared, and the last tile is as important as the first.
 */
export function staggerGroup(safe: boolean, stagger = 0.04): Variants {
  return {
    hidden: {},
    show: { transition: { staggerChildren: safe ? stagger : 0 } },
  }
}

/** An overlay's scrim. Opacity only — a scrim that moves is a distraction. */
export function scrim(safe: boolean): Variants {
  return {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { duration: safe ? duration.base : 0, ease: easing.out } },
    leave: { opacity: 0, transition: { duration: safe ? duration.micro : 0, ease: easing.in } },
  }
}

/**
 * A panel entering from an edge. `from` is a CSS transform percentage so the
 * panel's own width decides the distance and nothing has to be measured.
 */
export function slideIn(safe: boolean, from: 'left' | 'right' | 'bottom'): Variants {
  const axis = from === 'bottom' ? 'y' : 'x'
  const sign = from === 'right' || from === 'bottom' ? 1 : -1
  const hidden = safe ? { [axis]: `${sign * 100}%` } : { opacity: 0 }
  const leaveTo = safe ? { [axis]: `${sign * 100}%` } : { opacity: 0 }

  return {
    hidden,
    show: {
      x: 0,
      y: 0,
      opacity: 1,
      transition: safe ? spring.panel : { duration: 0 },
    },
    leave: {
      ...leaveTo,
      transition: { duration: safe ? duration.base : 0, ease: easing.in },
    },
  }
}

/**
 * A popover: fades and moves a short way *towards* its trigger's edge, so the
 * motion says where it came from. Scale is deliberately absent — a scaling
 * menu reads as a dialog, and a menu is not one.
 */
export function popover(safe: boolean, origin: 'top' | 'bottom' = 'bottom'): Variants {
  const y = origin === 'bottom' ? -travel.pop : travel.pop
  return {
    hidden: { opacity: 0, y: safe ? y : 0 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: safe ? duration.base : 0, ease: easing.out },
    },
    leave: {
      opacity: 0,
      y: safe ? y : 0,
      transition: { duration: safe ? duration.micro : 0, ease: easing.in },
    },
  }
}

/**
 * A dialog. This one *does* scale, because it is a new surface rather than a
 * menu attached to something — and only from 0.98, which reads as settling
 * rather than as zooming.
 */
export function dialog(safe: boolean): Variants {
  return {
    hidden: { opacity: 0, scale: safe ? 0.98 : 1, y: safe ? 8 : 0 },
    show: {
      opacity: 1,
      scale: 1,
      y: 0,
      transition: { duration: safe ? duration.emphasis : 0, ease: easing.out },
    },
    leave: {
      opacity: 0,
      scale: safe ? 0.98 : 1,
      transition: { duration: safe ? duration.micro : 0, ease: easing.in },
    },
  }
}

/**
 * A region opening in place — a disclosure, an accordion row.
 *
 * Height is animated from `auto`, which framer-motion measures. That is a
 * layout-affecting animation and therefore the one exception to the
 * transform-and-opacity rule in the brief; it is allowed here because the
 * alternative — a fixed max-height — either clips content or animates a gap
 * below it, and both are worse than one measured reflow on an explicit click.
 */
export function collapse(safe: boolean): Variants {
  return {
    hidden: { height: 0, opacity: 0 },
    show: {
      height: 'auto',
      opacity: 1,
      transition: {
        height: { duration: safe ? duration.emphasis : 0, ease: easing.out },
        opacity: { duration: safe ? duration.base : 0, delay: safe ? 0.06 : 0 },
      },
    },
    leave: {
      height: 0,
      opacity: 0,
      transition: {
        height: { duration: safe ? duration.base : 0, ease: easing.in },
        opacity: { duration: safe ? duration.instant : 0 },
      },
    },
  }
}

/**
 * A toast. Enters from the edge it is pinned to, leaves the same way.
 *
 * Toasts are the one thing that animates while the user is doing something
 * else, so this is the shortest `emphasis`-class motion in the system and it
 * never blocks a click — the container is `pointer-events-none` except on the
 * toast itself.
 */
export function toast(safe: boolean): Variants {
  return {
    hidden: { opacity: 0, y: safe ? 12 : 0, scale: safe ? 0.98 : 1 },
    show: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: { duration: safe ? duration.base : 0, ease: easing.out },
    },
    leave: {
      opacity: 0,
      y: safe ? 8 : 0,
      transition: { duration: safe ? duration.micro : 0, ease: easing.in },
    },
  }
}
