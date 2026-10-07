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
  { id: 'chat', label: 'Questions' },
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

  return (
    <nav aria-label="Setup progress" className="mx-auto w-full max-w-4xl">
      {/* The accessible statement of position, kept for screen readers but not
          shown — the numbered rail below carries it visually. */}
      <p className="sr-only">
        Step {activeIndex + 1} of {STEPS.length} — {STEPS[activeIndex].label}
      </p>
      <ol aria-hidden className="flex items-center gap-1.5">
        {STEPS.map((step, index) => {
          const done = index < activeIndex
          const here = index === activeIndex
          return (
            <li key={step.id} className="flex flex-1 items-center gap-1.5">
              <span
                className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border text-[11px] font-medium transition-colors ${
                  done
                    ? 'border-ink bg-ink text-bone-50'
                    : here
                      ? 'border-gold-500 bg-white text-ink'
                      : 'border-bone-300 bg-white text-ink-300'
                }`}
              >
                {done ? (
                  <svg viewBox="0 0 16 16" width="11" height="11" fill="none">
                    <path
                      d="M3 8.5l3 3 7-7"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  index + 1
                )}
              </span>
              {index < STEPS.length - 1 && (
                <span className={`h-px flex-1 transition-colors ${done ? 'bg-ink' : 'bg-bone-300'}`} />
              )}
            </li>
          )
        })}
      </ol>
      <ol aria-hidden className="mt-1.5 hidden grid-cols-7 gap-1.5 sm:grid">
        {STEPS.map((step, index) => (
          <li
            key={step.id}
            className={`text-[10px] leading-tight ${
              index === activeIndex ? 'font-medium text-ink-600' : 'text-ink-300'
            }`}
          >
            {step.label}
          </li>
        ))}
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
  children,
}: {
  current: StepId
  aura?: AuraState
  fill?: boolean
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

      {/* ── Body: illustration left, step content right ── */}
      <div className="flex min-h-0 flex-1">
        <aside
          aria-hidden
          className="hidden items-center justify-center p-10 lg:flex lg:w-[42%]"
        >
          <StepArt key={current} step={current} active={aura === 'thinking'} />
        </aside>

        {fill ? (
          <section className="flex min-h-0 flex-1 flex-col">{children}</section>
        ) : (
          <section className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <motion.div
              key={current}
              variants={fadeUp(safe)}
              initial="hidden"
              animate="show"
              className="mx-auto flex min-h-full w-full max-w-2xl flex-col justify-center px-6 py-12 sm:px-10 lg:px-14"
            >
              {children}
            </motion.div>
          </section>
        )}
      </div>
    </main>
  )
}
