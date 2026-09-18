'use client'

import { MotionConfig } from 'framer-motion'
import type { ReactNode } from 'react'

/**
 * One reduced-motion decision, made inside framer-motion rather than by each
 * component.
 *
 * ## The hydration mismatch this fixes
 *
 * `Reveal` used to compute its own initial offset from `useReducedMotion()`.
 * That hook reads a media query, and there is no media query on a server — so
 * it returns `false` during SSR and `true` in a browser that has the setting
 * on. The server therefore emitted `transform: translateY(28px)` and the client
 * expected `transform: none`, which React reports as
 *
 *     Warning: Prop `style` did not match. Server: … Client: …
 *
 * and resolves by throwing away the server's markup for that subtree and
 * re-rendering it. On the landing page that is every section heading and every
 * revealed card — so the one setting whose whole purpose is to make the page
 * calmer made it do strictly more work, and only for the readers who asked for
 * less.
 *
 * `reducedMotion="user"` moves the decision inside the library. Every
 * `motion` component renders the same markup on both sides and framer-motion
 * drops *transform and layout* animations at run time while keeping opacity —
 * which is the right split: opacity is frequently the only signal that
 * something appeared, and removing it would leave a state change with no
 * indication at all.
 *
 * The CSS half of the policy still lives in `globals.css`, because that reaches
 * hover states, the hero's keyframed entrance and the skeleton sweep, none of
 * which framer-motion drives. Both are needed.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>
}
