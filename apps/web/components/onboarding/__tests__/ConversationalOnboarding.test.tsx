import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ConversationalOnboarding } from '@/components/onboarding/ConversationalOnboarding'
import * as client from '@/lib/agent-onboarding-client'
import { ModelUnavailableError } from '@/lib/agent-onboarding-client'
import * as settings from '@/lib/settings-client'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

vi.mock('@/lib/agent-onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof client>()
  return {
    ...actual,
    readState: vi.fn(),
    start: vi.fn(),
    read: vi.fn(),
    nextQuestion: vi.fn(),
    submitAnswer: vi.fn(),
    openDiscovery: vi.fn(),
    confirmBrief: vi.fn(),
    describeCompany: vi.fn(),
    documentsDone: vi.fn(),
    declareTools: vi.fn(),
    finish: vi.fn(),
  }
})

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof settings>()
  return { ...actual, fetchDepartments: vi.fn(), saveDepartments: vi.fn() }
})

const mocked = vi.mocked(client)
const mockedSettings = vi.mocked(settings)

/** A brief already confirmed, sitting at the start of discovery, no turns yet. */
function atDiscoveryOpening(): client.AgentState {
  return {
    active: true,
    completed: false,
    phase: 'discovery',
    domain: 'acme.om',
    turns: [{ role: 'agent', text: 'Here is what I found.', target: null, scope: null }],
    brief: {
      statements: [
        {
          field: 'brain.profile',
          label: 'Company profile',
          text: 'A logistics company.',
          confidence: 'read',
          source: 'https://acme.om',
        },
      ],
    },
    persona: {},
    context: {},
    answered: 0,
    ceiling: 5,
    pages_read: ['https://acme.om'],
  }
}

const NO_DEPARTMENTS_CHOSEN: settings.Departments = {
  departments: [
    { value: 'executive', label: 'Chief of Staff', running: true, capabilities: 1, answered: 0, unanswered: 0 },
    { value: 'sales', label: 'Sales', running: false, capabilities: 2, answered: 0, unanswered: 2 },
    { value: 'finance', label: 'Finance', running: false, capabilities: 2, answered: 0, unanswered: 2 },
  ],
  may_administer: true,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ConversationalOnboarding — department picker', () => {
  it('asks for departments before the opening discovery question, and saves the choice', async () => {
    mocked.readState.mockResolvedValue(atDiscoveryOpening())
    mockedSettings.fetchDepartments.mockResolvedValue(NO_DEPARTMENTS_CHOSEN)
    mockedSettings.saveDepartments.mockResolvedValue({
      departments: NO_DEPARTMENTS_CHOSEN.departments.map((d) =>
        d.value === 'sales' ? { ...d, running: true } : d,
      ),
      may_administer: true,
    })

    render(<ConversationalOnboarding />)

    // The opening discovery question must not appear until departments are chosen.
    expect(
      await screen.findByRole('group', { name: /choose your departments/i }),
    ).toBeInTheDocument()
    expect(screen.queryByText(/what are you responsible for, day to day\?/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => expect(mockedSettings.saveDepartments).toHaveBeenCalledWith(['sales']))

    // Departments resolved — the opening question now renders.
    expect(await screen.findByText(/what are you responsible for, day to day\?/i)).toBeInTheDocument()
  })

  it('skips the picker on resume when departments were already chosen', async () => {
    mocked.readState.mockResolvedValue(atDiscoveryOpening())
    mockedSettings.fetchDepartments.mockResolvedValue({
      departments: NO_DEPARTMENTS_CHOSEN.departments.map((d) =>
        d.value === 'sales' ? { ...d, running: true } : d,
      ),
      may_administer: true,
    })

    render(<ConversationalOnboarding />)

    expect(await screen.findByText(/what are you responsible for, day to day\?/i)).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: /choose your departments/i })).not.toBeInTheDocument()
    expect(mockedSettings.saveDepartments).not.toHaveBeenCalled()
  })
})

describe('ConversationalOnboarding — no model configured', () => {
  it('degrades honestly instead of fabricating a conversation', async () => {
    mocked.readState.mockRejectedValue(
      new ModelUnavailableError('A language model is not configured for this workspace.'),
    )
    mockedSettings.fetchDepartments.mockResolvedValue(NO_DEPARTMENTS_CHOSEN)

    render(<ConversationalOnboarding />)

    expect(await screen.findByText(/guided onboarding is unavailable/i)).toBeInTheDocument()
    expect(
      screen.getByText(/a language model is not configured for this workspace\./i),
    ).toBeInTheDocument()
    // No retry that cannot work, and no fallback catalogue rendered.
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })
})
