import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CompanyBrainPage } from '@/components/brain/CompanyBrainPage'
import { fetchBrain, type Brain } from '@/lib/settings-client'
import { fetchQuestions, type Question, type Questions } from '@/lib/onboarding-client'
import { readState, type AgentState, type Turn } from '@/lib/agent-onboarding-client'

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings-client')>()
  return { ...actual, fetchBrain: vi.fn() }
})

vi.mock('@/lib/onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/onboarding-client')>()
  return { ...actual, fetchQuestions: vi.fn() }
})

vi.mock('@/lib/agent-onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/agent-onboarding-client')>()
  return { ...actual, readState: vi.fn() }
})

const mockedFetchBrain = vi.mocked(fetchBrain)
const mockedFetchQuestions = vi.mocked(fetchQuestions)
const mockedReadState = vi.mocked(readState)

function agentState(turns: Turn[] = [], pagesRead: string[] = []): AgentState {
  return {
    active: turns.length > 0,
    completed: turns.length > 0,
    phase: turns.length > 0 ? 'ready' : 'analysing',
    domain: null,
    turns,
    brief: {},
    persona: {},
    context: {},
    answered: turns.length,
    ceiling: 20,
    pages_read: pagesRead,
  }
}

function brain(overrides: Partial<Brain> = {}): Brain {
  return {
    version: 4,
    generated_by: 'agent',
    unavailable_reason: '',
    profile: 'An industrial supplies distributor.',
    products_services: 'Pipes, fittings and tools.',
    target_customers: 'Contractors and facilities teams.',
    goals: null,
    assumptions: ['Fiscal year starts in April.'],
    provenance: ['https://acme.om/about'],
    ...overrides,
  }
}

function question(overrides: Partial<Question> = {}): Question {
  return {
    key: 'marketing_budget',
    prompt: 'What is your monthly marketing budget?',
    stage: 'pass_2',
    answer_type: 'money',
    scope: 'L3',
    department: 'marketing',
    required: false,
    why: 'Sizes campaign recommendations.',
    options: [],
    free_entry: false,
    writable: true,
    value: 'OMR 1,500',
    ...overrides,
  }
}

function questionsResponse(questions: Question[]): Questions {
  return { questions, can_administer: true, members: [] }
}

beforeEach(() => {
  mockedFetchBrain.mockReset()
  mockedFetchQuestions.mockReset()
  mockedReadState.mockReset()
  mockedReadState.mockResolvedValue(agentState())
})

describe('CompanyBrainPage', () => {
  it('shows a real empty state, not a blank table, when the brain is unavailable', async () => {
    mockedFetchBrain.mockResolvedValue(
      brain({
        unavailable_reason: 'No audit has run yet.',
        profile: null,
        products_services: null,
        target_customers: null,
        goals: null,
        assumptions: [],
      }),
    )
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))

    render(<CompanyBrainPage />)

    expect(await screen.findByText('No audit has run yet')).toBeVisible()
    expect(screen.getByText('No audit has run yet.')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Go to setup' })).toHaveAttribute(
      'href',
      '/onboarding',
    )
  })

  it('renders brain fields and answered questions as one facts table, tagged by source', async () => {
    mockedFetchBrain.mockResolvedValue(brain())
    mockedFetchQuestions.mockResolvedValue(questionsResponse([question()]))

    render(<CompanyBrainPage />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('What the company does')).toBeVisible()
    expect(within(table).getByText('What is your monthly marketing budget?')).toBeVisible()
    // goals was null and must be skipped rather than rendered empty.
    expect(within(table).queryByText('Goals')).not.toBeInTheDocument()

    const readTags = within(table).getAllByText('read')
    expect(readTags.length).toBeGreaterThan(0)
    expect(within(table).getByText('you')).toBeVisible()
  })

  it('shows assumptions in their own prominent block, tagged unconfirmed', async () => {
    mockedFetchBrain.mockResolvedValue(brain())
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))

    render(<CompanyBrainPage />)

    expect(await screen.findByText('Fiscal year starts in April.')).toBeVisible()
    expect(screen.getByText('assumption · unconfirmed')).toBeVisible()
  })

  it('filters the table by search text, client-side', async () => {
    mockedFetchBrain.mockResolvedValue(brain())
    mockedFetchQuestions.mockResolvedValue(questionsResponse([question()]))

    render(<CompanyBrainPage />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('What the company does')).toBeVisible()

    fireEvent.change(screen.getByRole('searchbox', { name: /search facts/i }), {
      target: { value: 'marketing budget' },
    })

    await waitFor(() => {
      expect(within(table).queryByText('What the company does')).not.toBeInTheDocument()
    })
    expect(within(table).getByText('What is your monthly marketing budget?')).toBeVisible()
  })

  it('offers a retry when the fetch itself fails', async () => {
    mockedFetchBrain.mockRejectedValue(new Error('Network down.'))
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))

    render(<CompanyBrainPage />)

    expect(await screen.findByText('Network down.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeVisible()
  })

  it('lists the onboarding conversation as a source, with a count, when there are turns', async () => {
    mockedFetchBrain.mockResolvedValue(brain())
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))
    mockedReadState.mockResolvedValue(
      agentState([
        { role: 'agent', text: 'Who actually buys from you?', target: null, scope: null },
        {
          role: 'user',
          text: 'Contractors and facilities teams, mostly.',
          target: 'brain.target_customers',
          scope: 2,
        },
      ]),
    )

    render(<CompanyBrainPage />)

    expect(await screen.findByText('Where this Brain came from')).toBeVisible()
    expect(screen.getByText('Onboarding conversation')).toBeVisible()
    expect(screen.getByText('2 messages')).toBeVisible()
    expect(screen.getByText('Website')).toBeVisible()
    expect(screen.getByText('You')).toBeVisible()
  })

  it('says there is no conversation on record, rather than erroring, for a catalogue-onboarded workspace', async () => {
    mockedFetchBrain.mockResolvedValue(brain())
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))
    mockedReadState.mockResolvedValue(agentState([]))

    render(<CompanyBrainPage />)

    expect(await screen.findByText('Where this Brain came from')).toBeVisible()
    expect(
      screen.getByText('No onboarding conversation is on record for this workspace.'),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: 'View conversation' })).not.toBeInTheDocument()
  })

  it('opens the conversation tab from the source row, rendering the transcript', async () => {
    mockedFetchBrain.mockResolvedValue(brain())
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))
    mockedReadState.mockResolvedValue(
      agentState([
        { role: 'agent', text: 'Who actually buys from you?', target: null, scope: null },
        {
          role: 'user',
          text: 'Contractors and facilities teams, mostly.',
          target: 'brain.target_customers',
          scope: 2,
        },
      ]),
    )

    render(<CompanyBrainPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'View conversation' }))

    const log = await screen.findByRole('log', { name: /onboarding conversation transcript/i })
    expect(within(log).getByText('Contractors and facilities teams, mostly.')).toBeVisible()
  })

  it('links a fact to the onboarding turn that produced it, and opens the conversation from there', async () => {
    mockedFetchBrain.mockResolvedValue(brain())
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))
    mockedReadState.mockResolvedValue(
      agentState([
        { role: 'agent', text: 'Who actually buys from you?', target: null, scope: null },
        {
          role: 'user',
          text: 'Contractors and facilities teams, mostly.',
          target: 'brain.target_customers',
          scope: 2,
        },
      ]),
    )

    render(<CompanyBrainPage />)

    const table = await screen.findByRole('table')
    fireEvent.click(within(table).getAllByRole('button', { name: 'View source' })[2])

    expect(await screen.findByText('From your onboarding conversation')).toBeVisible()
    expect(screen.getByText('“Contractors and facilities teams, mostly.”')).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Open in conversation' }))

    const log = await screen.findByRole('log', { name: /onboarding conversation transcript/i })
    expect(within(log).getByText('Contractors and facilities teams, mostly.')).toBeVisible()
  })

  it('surfaces the conversation even when the brain has no facts yet, not a bare empty state', async () => {
    // Every agent-onboarded workspace is like this before assembly: the agent
    // has written turns, but the brain has no facts. The conversation is a
    // first-class source and must not be hidden behind "No audit has run yet".
    mockedFetchBrain.mockResolvedValue(
      brain({
        unavailable_reason: 'Nothing has been assembled yet.',
        profile: null,
        products_services: null,
        target_customers: null,
        goals: null,
        assumptions: [],
      }),
    )
    mockedFetchQuestions.mockResolvedValue(questionsResponse([]))
    mockedReadState.mockResolvedValue(
      agentState([
        { role: 'agent', text: 'What are you responsible for, day to day?', target: null, scope: null },
        {
          role: 'user',
          text: 'I run the whole company but spend most time on big deals.',
          target: 'persona.stated_purpose',
          scope: 2,
        },
      ]),
    )

    render(<CompanyBrainPage />)

    // Not the dead-end empty state…
    expect(await screen.findByText('Where this Brain came from')).toBeVisible()
    expect(screen.queryByText('No audit has run yet')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Go to setup' })).not.toBeInTheDocument()

    // …the conversation source is listed, and the page opens on it by default so
    // the user lands on the content that exists.
    expect(screen.getByText('Onboarding conversation')).toBeVisible()
    const log = await screen.findByRole('log', { name: /onboarding conversation transcript/i })
    expect(
      within(log).getByText('I run the whole company but spend most time on big deals.'),
    ).toBeVisible()

    // The facts views say "no facts yet" rather than a misleading search miss.
    fireEvent.click(screen.getByRole('tab', { name: /table/i }))
    expect(await screen.findByText('No facts yet')).toBeVisible()
  })
})
