import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OnboardingEntry } from '@/components/onboarding/OnboardingEntry'
import { AuthError } from '@/lib/auth-client'
import { fetchCompany, fetchDepartments } from '@/lib/settings-client'
import { readState, type AgentState } from '@/lib/agent-onboarding-client'
import { fetchEntitlement } from '@/lib/billing-client'

/**
 * `OnboardingEntry` is now the six-step wizard orchestrator (ADR 0073). Its job
 * here is resuming at the right step — company first, areas when none are
 * chosen, the chatbot once the engine is mid-interview, the dashboard when the
 * session is already complete. The step bodies are stubbed: their own
 * behaviour is covered by their own tests, and exercising them for real would
 * duplicate those mocks for a test that is about which step shows.
 */

const replace = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings-client')>()
  return { ...actual, fetchCompany: vi.fn(), fetchDepartments: vi.fn() }
})

vi.mock('@/lib/agent-onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/agent-onboarding-client')>()
  return {
    ...actual,
    readState: vi.fn(),
    start: vi.fn(),
    read: vi.fn(),
    confirmBrief: vi.fn(),
    finish: vi.fn(),
  }
})

vi.mock('@/components/onboarding/stages/CompanyStage', () => ({
  CompanyStage: () => <div>company step</div>,
}))
vi.mock('@/components/onboarding/stages/AreasStage', () => ({
  AreasStage: () => <div>areas step</div>,
}))
vi.mock('@/components/onboarding/ChatbotStep', () => ({
  ChatbotStep: () => <div>chat step</div>,
}))
vi.mock('@/components/onboarding/DocumentsStep', () => ({
  DocumentsStep: () => <div>documents step</div>,
}))
vi.mock('@/components/onboarding/ToolsStep', () => ({
  ToolsStep: () => <div>tools step</div>,
}))
vi.mock('@/components/onboarding/BrainReview', () => ({
  BrainReview: () => <div>brain step</div>,
}))
vi.mock('@/components/onboarding/PaymentStep', () => ({
  PaymentStep: () => <div>payment step</div>,
}))
vi.mock('@/lib/billing-client', () => ({ fetchEntitlement: vi.fn() }))

const company = {
  workspace_id: 'w1',
  name: 'Acme',
  domain: 'acme.om',
  website_url: 'https://acme.om',
  domain_verified: false,
  role: 'admin',
  may_administer: true,
}

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

function departments(running: string[]) {
  const all = ['marketing', 'sales', 'operations', 'finance', 'hr', 'strategy']
  return {
    may_administer: true,
    departments: all.map((value) => ({
      value,
      label: value[0].toUpperCase() + value.slice(1),
      running: running.includes(value),
      capabilities: 0,
      answered: 0,
      unanswered: 0,
    })),
  }
}

beforeEach(() => {
  replace.mockReset()
  vi.mocked(fetchCompany).mockReset()
  vi.mocked(fetchDepartments).mockReset()
  vi.mocked(readState).mockReset()
  vi.mocked(fetchEntitlement).mockReset()
})

describe('OnboardingEntry resume', () => {
  it('starts at the company step when no workspace exists yet', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('no workspace selected', 403))

    render(<OnboardingEntry />)

    expect(await screen.findByText('company step')).toBeInTheDocument()
    expect(screen.getByText(/step 1 of 7/i)).toBeInTheDocument()
  })

  it('resumes at the areas step when a company exists but no areas are chosen', async () => {
    vi.mocked(fetchCompany).mockResolvedValue(company)
    vi.mocked(readState).mockResolvedValue(agentState({ active: false, phase: 'analysing' }))
    vi.mocked(fetchDepartments).mockResolvedValue(departments([]))

    render(<OnboardingEntry />)

    expect(await screen.findByText('areas step')).toBeInTheDocument()
    expect(screen.getByText(/step 2 of 7/i)).toBeInTheDocument()
  })

  it('resumes at the chatbot step when areas are chosen and the interview is live', async () => {
    vi.mocked(fetchCompany).mockResolvedValue(company)
    vi.mocked(readState).mockResolvedValue(agentState({ phase: 'discovery' }))
    vi.mocked(fetchDepartments).mockResolvedValue(departments(['sales']))

    render(<OnboardingEntry />)

    expect(await screen.findByText('chat step')).toBeInTheDocument()
    expect(screen.getByText(/step 3 of 7/i)).toBeInTheDocument()
  })

  it('goes straight to the dashboard when complete and entitled', async () => {
    vi.mocked(fetchCompany).mockResolvedValue(company)
    vi.mocked(readState).mockResolvedValue(agentState({ completed: true, phase: 'ready' }))
    vi.mocked(fetchDepartments).mockResolvedValue(departments(['sales']))
    vi.mocked(fetchEntitlement).mockResolvedValue({ entitled: true, kind: 'paid', trial_expires_at: null })

    render(<OnboardingEntry />)

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'))
  })

  it('resumes at the payment step when complete but not yet entitled', async () => {
    vi.mocked(fetchCompany).mockResolvedValue(company)
    vi.mocked(readState).mockResolvedValue(agentState({ completed: true, phase: 'ready' }))
    vi.mocked(fetchEntitlement).mockResolvedValue({ entitled: false, kind: null, trial_expires_at: null })

    render(<OnboardingEntry />)

    expect(await screen.findByText('payment step')).toBeInTheDocument()
    expect(screen.getByText(/step 7 of 7/i)).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  it('shows a retryable error on a real failure, rather than guessing which step to show', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('database unavailable', 500))

    render(<OnboardingEntry />)

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })
})
