import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ChatbotStep } from '@/components/onboarding/ChatbotStep'
import type { AgentState } from '@/lib/agent-onboarding-client'

/**
 * The product owner's instruction (ADR 0073): the chatbot asks the interview
 * and nothing else — no area-of-interest picker, no tools, no live Company
 * Brain panel. These lock that in, and the scan loader the owner asked for.
 */

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }) }))

function agentState(overrides: Partial<AgentState> = {}): AgentState {
  return {
    active: true,
    completed: false,
    phase: 'discovery',
    domain: 'acme.om',
    turns: [],
    brief: {},
    persona: {},
    context: {},
    answered: 0,
    ceiling: 5,
    pages_read: [],
    ...overrides,
  }
}

const noop = () => {}

describe('ChatbotStep', () => {
  it('shows the scanning loader while the site is being read', () => {
    render(
      <ChatbotStep state={agentState({ phase: 'analysing' })} onState={noop} onComplete={noop} />,
    )
    expect(screen.getByText(/scanning acme\.om/i)).toBeInTheDocument()
  })

  it('asks the opening discovery question and offers a composer', () => {
    render(<ChatbotStep state={agentState({ phase: 'discovery' })} onState={noop} onComplete={noop} />)
    expect(screen.getByText(/what are you responsible for, day to day\?/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/answer in your own words/i)).toBeInTheDocument()
  })

  it('does not host department selection, tools, or a live Company Brain', () => {
    render(<ChatbotStep state={agentState({ phase: 'discovery' })} onState={noop} onComplete={noop} />)
    expect(screen.queryByRole('group', { name: /choose your departments/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/company brain/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/which systems do you run on/i)).not.toBeInTheDocument()
  })
})
