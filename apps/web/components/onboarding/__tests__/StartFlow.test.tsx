import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StartFlow } from '@/components/onboarding/StartFlow'
import { AuthError } from '@/lib/auth-client'
import { fetchCompany, fetchDepartments } from '@/lib/settings-client'
import { fetchQuestions } from '@/lib/onboarding-client'
import { start } from '@/lib/agent-onboarding-client'

/**
 * `StartFlow`'s whole job on mount is deciding where a founder actually is —
 * a refresh or a bookmark must resume, never restart (ADR 0067). These tests
 * drive that resolution directly rather than through a full stage render,
 * since the stage components have their own focused tests.
 */

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings-client')>()
  return { ...actual, fetchCompany: vi.fn(), fetchDepartments: vi.fn(), saveDepartments: vi.fn() }
})

vi.mock('@/lib/onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/onboarding-client')>()
  return { ...actual, fetchQuestions: vi.fn(), saveAnswers: vi.fn() }
})

vi.mock('@/lib/agent-onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/agent-onboarding-client')>()
  return { ...actual, start: vi.fn(), read: vi.fn() }
})

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

const DEPARTMENTS_NONE_RUNNING = [
  { value: 'executive', label: 'Chief of Staff', running: true, capabilities: 1, answered: 0, unanswered: 0 },
  { value: 'marketing', label: 'Marketing', running: false, capabilities: 2, answered: 0, unanswered: 2 },
]

const DEPARTMENTS_MARKETING_RUNNING = [
  { value: 'executive', label: 'Chief of Staff', running: true, capabilities: 1, answered: 0, unanswered: 0 },
  { value: 'marketing', label: 'Marketing', running: true, capabilities: 2, answered: 0, unanswered: 2 },
]

beforeEach(() => {
  vi.mocked(fetchCompany).mockReset()
  vi.mocked(fetchDepartments).mockReset()
  vi.mocked(fetchQuestions).mockReset()
  vi.mocked(start).mockReset()
})

describe('StartFlow resume', () => {
  it('resumes at Company when no workspace has been created yet', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('no workspace selected', 403))

    render(<StartFlow />)

    expect(await screen.findByText(/let.s start with your company/i)).toBeInTheDocument()
  })

  it('resumes at Areas of Interest once a company exists but nothing has been selected', async () => {
    vi.mocked(fetchCompany).mockResolvedValue({
      workspace_id: 'w1',
      name: 'Acme',
      domain: 'acme.om',
      website_url: 'https://acme.om',
      domain_verified: false,
      role: 'admin',
      may_administer: true,
    })
    vi.mocked(fetchDepartments).mockResolvedValue({
      departments: DEPARTMENTS_NONE_RUNNING,
      may_administer: true,
    })

    render(<StartFlow />)

    expect(
      await screen.findByText(/which parts of the business should nexus pay attention to/i),
    ).toBeInTheDocument()
  })

  it('resumes at Tailored Questions once areas are chosen but a catalogue question is unanswered', async () => {
    vi.mocked(start).mockRejectedValue(new Error('no model'))
    vi.mocked(fetchCompany).mockResolvedValue({
      workspace_id: 'w1',
      name: 'Acme',
      domain: 'acme.om',
      website_url: 'https://acme.om',
      domain_verified: false,
      role: 'admin',
      may_administer: true,
    })
    vi.mocked(fetchDepartments).mockResolvedValue({
      departments: DEPARTMENTS_MARKETING_RUNNING,
      may_administer: true,
    })
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [
        {
          key: 'currency',
          prompt: 'Which currency do you report in?',
          stage: 'pass_1',
          answer_type: 'single_choice',
          scope: 'L2',
          department: null,
          required: false,
          why: 'Every figure NEXUS shows is in this currency.',
          options: [],
          free_entry: false,
          writable: true,
          value: null,
        },
      ],
      can_administer: true,
      members: [],
    })

    render(<StartFlow />)

    expect(await screen.findByText('Which currency do you report in?')).toBeInTheDocument()
  }, 10_000)

  it('resumes at the wrap-up once every scoped question is already answered', async () => {
    vi.mocked(fetchCompany).mockResolvedValue({
      workspace_id: 'w1',
      name: 'Acme',
      domain: 'acme.om',
      website_url: 'https://acme.om',
      domain_verified: false,
      role: 'admin',
      may_administer: true,
    })
    vi.mocked(fetchDepartments).mockResolvedValue({
      departments: DEPARTMENTS_MARKETING_RUNNING,
      may_administer: true,
    })
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [
        {
          key: 'currency',
          prompt: 'Which currency do you report in?',
          stage: 'pass_1',
          answer_type: 'single_choice',
          scope: 'L2',
          department: null,
          required: false,
          why: 'Every figure NEXUS shows is in this currency.',
          options: [],
          free_entry: false,
          writable: true,
          value: 'OMR',
        },
      ],
      can_administer: true,
      members: [],
    })

    render(<StartFlow />)

    expect(await screen.findByText(/you.re all set/i)).toBeInTheDocument()
  })

  it('shows a recoverable error rather than guessing when resume itself fails', async () => {
    vi.mocked(fetchCompany).mockRejectedValue(new AuthError('Cannot reach the account service.', 500))

    render(<StartFlow />)

    expect(await screen.findByText(/could not reach the account service/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
