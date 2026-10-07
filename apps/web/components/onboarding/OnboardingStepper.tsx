'use client'

import { type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { OnboardingAura, PresenceMark, type AuraState } from '@/components/onboarding/OnboardingAura'
import { fadeUp, useMotionSafe } from '@/lib/motion'

/**
 * The visible wizard chrome for the stepped onboarding flow (ADR 0073).
 *
 * ADR 0069's conversation had only a phase label to say where you were; this
 * replaces it with an explicit stepper so the founder can see how many beats
 * are left. The six steps are a fixed, ordered list with a true denominator —
 * the same discipline the retired step rail used — so "Step 3 of 6" means
 * something, unlike a fraction over an uncountable website read.
 *
 * The shell owns the header (logo + "Guided setup" chip) and the rail; each
 * step renders its own body inside `StepColumn` (centred form) or, for the
 * chatbot, fills the frame itself.
 */

export type StepId = 'company' | 'areas' | 'chat' | 'documents' | 'tools' | 'brain'

/** The wizard's spine. Order is the flow; `index` is 1-based for display. */
export const STEPS: { id: StepId; label: string }[] = [
  { id: 'company', label: 'Company' },
  { id: 'areas', label: 'Areas' },
  { id: 'chat', label: 'Questions' },
  { id: 'documents', label: 'Documents' },
  { id: 'tools', label: 'Tools' },
  { id: 'brain', label: 'Company Brain' },
]

export function stepIndex(id: StepId): number {
  return STEPS.findIndex((step) => step.id === id)
}

function Stepper({ current }: { current: StepId }) {
  const activeIndex = stepIndex(current)

  return (
    <nav aria-label="Setup progress" className="mx-auto mt-3 w-full max-w-2xl">
      {/* The accessible, always-present statement of position. The visual rail
          below is aria-hidden decoration over this. */}
      <p className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-400">
        Step {activeIndex + 1} of {STEPS.length} — {STEPS[activeIndex].label}
      </p>
      <ol aria-hidden className="mt-2 flex items-center gap-1.5">
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
                <span
                  className={`h-px flex-1 transition-colors ${done ? 'bg-ink' : 'bg-bone-300'}`}
                />
              )}
            </li>
          )
        })}
      </ol>
      <ol aria-hidden className="mt-1.5 hidden grid-cols-6 gap-1.5 sm:grid">
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
 * The frame every step renders inside: the aura wash, the header, the stepper,
 * then the step body. `fill` lets the chatbot step take the whole frame (its
 * own scroll + sticky composer) while form steps get a centred, padded column
 * via `StepColumn`.
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
  return (
    <main id="main" tabIndex={-1} className="relative flex min-h-screen flex-col bg-bone-100">
      <OnboardingAura state={aura} />
      <header className="relative z-10 border-b border-bone-200 bg-white/80 px-6 py-4 backdrop-blur-sm">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3">
          <span className="flex items-center gap-2.5 font-display text-base font-semibold text-ink">
            <PresenceMark state={aura} />
            NEXUS <span className="font-normal opacity-60">OS</span>
          </span>
          <span className="rounded-full bg-steel-100 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-steel-700">
            Guided setup
          </span>
        </div>
        <Stepper current={current} />
      </header>
      {fill ? (
        <div className="relative z-10 flex flex-1 flex-col">{children}</div>
      ) : (
        <StepBody stepKey={current}>{children}</StepBody>
      )}
    </main>
  )
}

/** Centred, padded column with the calm `fadeUp` entrance, remounted per step. */
function StepBody({ stepKey, children }: { stepKey: string; children: ReactNode }) {
  const safe = useMotionSafe()
  return (
    <div className="relative z-10 flex-1 overflow-y-auto">
      <motion.div
        key={stepKey}
        variants={fadeUp(safe)}
        initial="hidden"
        animate="show"
        className="mx-auto w-full max-w-read px-6 py-10 sm:py-14"
      >
        {children}
      </motion.div>
    </div>
  )
}
