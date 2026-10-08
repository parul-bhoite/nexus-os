'use client'

import { type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { Logo } from '@/components/ui/Logo'
import { AccountMenu } from '@/components/shell/AccountMenu'
import { type AuraState } from '@/components/onboarding/OnboardingAura'
import { StepArt } from '@/components/onboarding/OnboardingStepArt'
import { fadeUp, useMotionSafe } from '@/lib/motion'

/**
 * The visible wizard chrome for the stepped onboarding flow (ADR 0073, layout
 * revised in ADR 0074).
 *
 * The frame is three bands on white: a **frozen header** (logo + "Guided setup"
 * chip) separated by a hairline from a **step-tracker band** of its own, then
 * the scrolling body. The whole thing is locked to the viewport (`h-screen` +
 * `overflow-hidden`) so the header and tracker stay put while only the body
 * scrolls.
 *
 * Each step's body is two columns: a looping illustration on the left
 * (`StepArt`) and the step's own content on the right. The art panel is
 * decoration — `aria-hidden`, and dropped below `lg` where the task needs the
 * width. The chatbot passes `fill` so it can own the right column (its log
 * scrolls, its composer pins to the bottom) instead of being centred.
 */

export type StepId = 'company' | 'areas' | 'chat' | 'documents' | 'tools' | 'brain' | 'payment'

/** The wizard's spine. Order is the flow; the index is 1-based for display. */
export const STEPS: { id: StepId; label: string }[] = [
  { id: 'company', label: 'Company' },
  { id: 'areas', label: 'Areas' },
  { id: 'chat', label: 'Understanding' },
  { id: 'documents', label: 'Documents' },
  { id: 'tools', label: 'Tools' },
  { id: 'brain', label: 'Company Brain' },
  { id: 'payment', label: 'Payment' },
]

export function stepIndex(id: StepId): number {
  return STEPS.findIndex((step) => step.id === id)
}

function Stepper({ current }: { current: StepId }) {
  const activeIndex = stepIndex(current)
  const safe = useMotionSafe()

  return (
    <nav aria-label="Setup progress" className="mx-auto w-full max-w-5xl">
      {/* The accessible statement of position, kept for screen readers; the
          dotted rail carries it visually. */}
      <p className="sr-only">
        Step {activeIndex + 1} of {STEPS.length} — {STEPS[activeIndex].label}
      </p>
      {/* One line: each step is a dot and its label side by side, the dots
          joined by a track that fills as you advance. No numbers — the dot's
          state (filled = done, gold = here, hollow = ahead) carries it, and the
          label is right there to name it. */}
      <ol aria-hidden className="flex items-center gap-2 overflow-x-auto pb-0.5">
        {STEPS.map((step, index) => {
          const done = index < activeIndex
          const here = index === activeIndex
          return (
            <li key={step.id} className="flex min-w-0 flex-1 items-center gap-2 last:flex-none">
              <span className="flex shrink-0 items-center gap-2">
                <span className="relative grid h-3 w-3 shrink-0 place-items-center">
                  {/* The current step breathes — a soft gold ring that reads as
                      "you are here, and it is working" while the step loads. */}
                  {here && safe && (
                    <motion.span
                      aria-hidden
                      className="absolute inset-0 rounded-full bg-gold-500/30"
                      animate={{ scale: [1, 2, 1], opacity: [0.55, 0, 0.55] }}
                      transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
                    />
                  )}
                  <span
                    className={`h-2.5 w-2.5 rounded-full transition-colors duration-300 ${
                      done ? 'bg-ink' : here ? 'bg-gold-500' : 'border border-bone-300 bg-white'
                    }`}
                  />
                </span>
                <span
                  className={`text-xs transition-colors duration-300 ${
                    done ? 'text-ink' : here ? 'font-semibold text-ink' : 'text-ink-300'
                  }`}
                >
                  {step.label}
                </span>
              </span>
              {index < STEPS.length - 1 && (
                <span className="relative h-0.5 flex-1 overflow-hidden rounded-full bg-bone-300">
                  {/* The fill grows into each connector as its step completes —
                      on advance, framer animates this 0 → 100%, so moving on
                      reads as progress loading toward the next step. */}
                  <motion.span
                    aria-hidden
                    className="absolute inset-y-0 left-0 rounded-full bg-ink"
                    initial={false}
                    animate={{ width: done ? '100%' : '0%' }}
                    transition={{ duration: safe ? 0.5 : 0, ease: 'easeInOut' }}
                  />
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

/**
 * The frame every step renders inside. `fill` hands the chatbot the whole right
 * column; otherwise the step's content is centred in a readable measure with a
 * calm `fadeUp` entrance, remounted per step.
 */
export function StepperShell({
  current,
  aura = 'idle',
  fill = false,
  wide = false,
  children,
}: {
  current: StepId
  aura?: AuraState
  fill?: boolean
  /** Drop the decorative art column and let the content span the full width.
   *  Used by the Areas step, whose cards carry their own pricing detail and
   *  want the room (user request). */
  wide?: boolean
  children: ReactNode
}) {
  const safe = useMotionSafe()

  return (
    <main id="main" tabIndex={-1} className="flex h-screen flex-col overflow-hidden bg-white">
      {/* ── Frozen header, separated from the rest by a hairline ── */}
      <header className="flex shrink-0 items-center justify-between border-b border-bone-200 bg-white px-6 py-4 sm:px-8">
        <Logo />
        {/* Identity plus Sign out only — the account and settings pages are not
            reachable until onboarding creates a workspace, so leaving is the one
            honest action here (user request). */}
        <AccountMenu signOutOnly />
      </header>

      {/* ── The step tracker, its own band below the header ── */}
      <div className="shrink-0 bg-white px-6 py-4 sm:px-8">
        <Stepper current={current} />
      </div>

      {/* ── Body: illustration left, step content right (art dropped when wide) ── */}
      <div className="flex min-h-0 flex-1">
        {!wide && (
          <aside
            aria-hidden
            className="hidden items-center justify-center p-10 lg:flex lg:w-[40%]"
          >
            <StepArt key={current} step={current} active={aura === 'thinking'} />
          </aside>
        )}

        {fill ? (
          <section className="flex min-h-0 flex-1 flex-col">{children}</section>
        ) : (
          <section className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <motion.div
              key={current}
              variants={fadeUp(safe)}
              initial="hidden"
              animate="show"
              className={`mx-auto flex min-h-full w-full flex-col justify-center px-6 py-12 sm:px-10 lg:px-14 ${
                wide ? 'max-w-5xl' : 'max-w-2xl'
              }`}
            >
              {children}
            </motion.div>
          </section>
        )}
      </div>
    </main>
  )
}
