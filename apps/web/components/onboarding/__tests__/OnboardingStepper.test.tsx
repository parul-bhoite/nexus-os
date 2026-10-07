import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StepperShell, STEPS } from '@/components/onboarding/OnboardingStepper'

/**
 * The stepper is the visible difference ADR 0073 adds over the retired
 * conversation: an explicit "where am I" the founder can read. These assert the
 * accessible position statement and that every step is named.
 */
describe('StepperShell', () => {
  it('states the current position as a step out of six', () => {
    render(
      <StepperShell current="chat">
        <div>body</div>
      </StepperShell>,
    )

    expect(screen.getByText(/step 3 of 6 — questions/i)).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
    // The step's illustration panel renders for the current step (ADR 0074).
    expect(screen.getByText('A short conversation')).toBeInTheDocument()
  })

  it('names all six steps and keeps them in flow order', () => {
    render(
      <StepperShell current="company">
        <div />
      </StepperShell>,
    )

    for (const step of STEPS) {
      expect(screen.getAllByText(step.label).length).toBeGreaterThan(0)
    }
    expect(STEPS.map((s) => s.id)).toEqual(['company', 'areas', 'chat', 'documents', 'tools', 'brain'])
  })
})
