'use client'

import { type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { OnboardingAura, type AuraState } from '@/components/onboarding/OnboardingAura'
import { fadeUp, useMotionSafe } from '@/lib/motion'

/**
 * The shell every stage of the combined onboarding flow renders inside.
 *
 * Direction A ("The Letter", `docs/design/design-directions-onboarding.md`)
 * deliberately has **no step rail** — a quiet "Part X of 3" eyebrow is the only
 * progress signal, because the brief that produced this design was "too
 * informative and tiring," and a rail is one more thing competing for
 * attention. `OnboardingAura`'s ambient wash keeps running underneath every
 * stage, per the recommendation's one borrowing from Direction C: it is a
 * real, already-shipped "something is happening" signal that costs nothing
 * once it exists, so there is no reason to drop it just because the page
 * around it changed shape.
 *
 * Each stage is given a single `fadeUp` entrance — "each new screen simply
 * rises in place," never sideways — which is the calmest of the three
 * directions explored and the one explicitly recommended for a flow whose
 * entire brief was "make it feel shorter," not "make it feel more alive."
 */
export function OnboardingShell({
  part,
  eyebrow,
  stageKey,
  children,
  aura = 'idle',
}: {
  /** 1, 2 or 3 — see `StartFlow`'s `PART_FOR_STAGE`. */
  part: 1 | 2 | 3
  /** The text after the dash, e.g. "a minute, then we start learning". */
  eyebrow: string
  /** Remounts the entrance animation when the visible stage changes. */
  stageKey: string
  children: ReactNode
  aura?: AuraState
}) {
  const safe = useMotionSafe()

  return (
    <main id="main" tabIndex={-1} className="min-h-screen bg-bone-50">
      <OnboardingAura state={aura} />
      <motion.div
        key={stageKey}
        variants={fadeUp(safe)}
        initial="hidden"
        animate="show"
        className="mx-auto w-full max-w-read px-6 py-16 sm:py-20"
      >
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-500">
          Part {part} of 3 — {eyebrow}
        </p>
        <div className="mt-3">{children}</div>
      </motion.div>
    </main>
  )
}
