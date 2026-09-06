import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AgentOnboarding, greetingFor } from '@/components/onboarding/AgentOnboarding'
import * as client from '@/lib/agent-onboarding-client'

/**
 * Two defects a browser run found and no unit test would have, both in the seam
 * between this component and the API rather than inside either.
 *
 * They are worth a test each because neither produced an exception. One posted
 * an empty string and got a validation error back; the other rendered a screen
 * with nothing on it to click. A component that renders successfully and does
 * the wrong thing is exactly what a render-and-assert test is for.
 */

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
    finish: vi.fn(),
  }
})

const mocked = vi.mocked(client)

/** A journey mid-interview: the brief is confirmed and discovery is answered. */
function interviewing(turns: client.AgentState['turns']): client.AgentState {
  return {
    active: true,
    completed: false,
    phase: 'discovery',
    domain: 'books.toscrape.com',
    turns,
    brief: {},
    persona: {},
    context: {},
    answered: turns.filter((t) => t.role === 'user').length,
    ceiling: 14,
    pages_read: ['https://books.toscrape.com'],
    viewer: {
      name: 'Parul Bhoite',
      designation: 'Lead Designer',
      department: 'Design',
      company: 'Xebia',
    },
  }
}

/** A brief on the table, unconfirmed. */
function briefing(): client.AgentState {
  return {
    ...interviewing([
      {
        role: 'agent',
        text: 'You are a global AI-first consulting company founded in 2001.',
        target: null,
        scope: null,
      },
    ]),
    phase: 'brief',
    brief: {
      statements: [
        {
          field: 'brain.profile',
          text: 'You are a global AI-first consulting company founded in 2001.',
          confidence: 'read',
          source: 'https://xebia.com/about-us',
        },
      ],
    },
  }
}

const DISCOVERY_TURN = {
  role: 'user' as const,
  text: 'I run the site.',
  target: 'persona.stated_purpose',
  scope: 5,
}

const CORRECTION_TURN = {
  role: 'user' as const,
  text: 'Plain and factual.',
  target: 'brain.brand_voice',
  scope: 1,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AgentOnboarding', () => {
  it('submits the choice a chip carries, not the empty draft', async () => {
    // The chip used to call `onChange(choice)` and then `onSubmit()`. `onChange`
    // sets state, so `onSubmit` still closed over the draft from the render it
    // was created in — the empty one. Every chip posted "" and the API refused
    // it on `min_length`, which made the offered answers unusable.
    mocked.readState.mockResolvedValue(interviewing([DISCOVERY_TURN]))
    mocked.nextQuestion.mockResolvedValue({
      done: false,
      question: 'What language should we use?',
      target: 'persona.language',
      scope: 5,
      choices: ['English', 'Arabic'],
      reason: null,
    })
    mocked.submitAnswer.mockResolvedValue(interviewing([DISCOVERY_TURN]))

    render(<AgentOnboarding />)
    const chip = await screen.findByRole('button', { name: 'English' })
    fireEvent.click(chip)

    await waitFor(() => expect(mocked.submitAnswer).toHaveBeenCalledOnce())
    expect(mocked.submitAnswer).toHaveBeenCalledWith('English')
  })

  it('still offers the opening question when only the brief was corrected', async () => {
    // A brief correction is a user turn too. Reading "any user turn" as "the
    // opening question has been answered" suppressed the composer and fetched
    // no question, leaving a transcript and no way to continue.
    mocked.readState.mockResolvedValue(interviewing([CORRECTION_TURN]))

    render(<AgentOnboarding />)

    expect(
      await screen.findByText(/what are you responsible for, day to day\?/i),
    ).toBeInTheDocument()
    expect(mocked.nextQuestion).not.toHaveBeenCalled()
  })

  it('resumes a half-finished interview by asking for the outstanding question', async () => {
    mocked.readState.mockResolvedValue(interviewing([CORRECTION_TURN, DISCOVERY_TURN]))
    mocked.nextQuestion.mockResolvedValue({
      done: false,
      question: 'Who are your customers?',
      target: 'brain.target_customers',
      scope: 2,
      choices: [],
      reason: null,
    })

    render(<AgentOnboarding />)

    expect(await screen.findByText('Who are your customers?')).toBeInTheDocument()
    expect(mocked.nextQuestion).toHaveBeenCalledOnce()
  })

  it('starts exactly one journey, even though the effect runs twice in StrictMode', async () => {
    // `start` holds its database row uncommitted across a crawl and two model
    // calls, so a second concurrent one blocks on the single-active-session
    // index until the statement times out. Firing it once is the fix.
    mocked.readState.mockResolvedValue({
      ...interviewing([]),
      active: false,
      phase: 'analysing',
    })
    mocked.start.mockResolvedValue({ ...interviewing([]), phase: 'analysing' })
    mocked.read.mockResolvedValue(interviewing([]))

    const { StrictMode } = await import('react')
    render(
      <StrictMode>
        <AgentOnboarding />
      </StrictMode>,
    )

    await waitFor(() => expect(mocked.start).toHaveBeenCalled())
    expect(mocked.start).toHaveBeenCalledOnce()
    expect(mocked.readState).toHaveBeenCalledOnce()
  })
})

describe('AgentOnboarding greeting', () => {
  it('says who the person is before the read has produced anything', async () => {
    // The point of assembling it client-side: it needs no model, so it is on
    // screen during the twenty seconds of crawl-and-infer rather than after.
    // This used to be a full-screen takeover that showed only a spinner.
    mocked.readState.mockResolvedValue({
      ...interviewing([]),
      active: false,
      phase: 'analysing',
    })
    mocked.start.mockResolvedValue({ ...interviewing([]), phase: 'analysing' })
    let releaseRead: (s: client.AgentState) => void = () => {}
    mocked.read.mockReturnValue(
      new Promise<client.AgentState>((resolve) => {
        releaseRead = resolve
      }),
    )

    render(<AgentOnboarding />)

    expect(
      await screen.findByText('Hallo Parul — you work at Xebia as Lead Designer, in Design.'),
    ).toBeInTheDocument()
    releaseRead(interviewing([]))
    await waitFor(() => expect(mocked.read).toHaveBeenCalledOnce())
  })

  it('says only the parts it was actually given', () => {
    // Each clause is gated on its own column because all three are nullable.
    // Filling a gap from a neighbouring field is how a greeting starts telling
    // somebody something they never said, on the first line they ever read.
    expect(greetingFor({ name: 'Parul Bhoite', company: 'Xebia' })).toBe(
      'Hallo Parul — you work at Xebia.',
    )
    expect(greetingFor({ name: 'Parul', company: 'Xebia', department: 'Design' })).toBe(
      'Hallo Parul — you work at Xebia, in Design.',
    )
    expect(greetingFor({ name: 'Parul' })).toBe('Hallo Parul.')
    // An inbox is not a name, and "Hallo there" is worse than opening with the
    // finding — which the next bubble does anyway.
    expect(greetingFor({ company: 'Xebia', designation: 'Lead Designer' })).toBeNull()
    expect(greetingFor(undefined)).toBeNull()
    expect(greetingFor({ name: '  ' })).toBeNull()
  })
})

describe('AgentOnboarding brief', () => {
  it('offers one decision, and the editors only when asked for', async () => {
    // Everybody used to meet three textareas before being told anything, each
    // duplicating a row of the panel beside it. The correction path is the
    // point of the screen; facing it first is what got it clicked through.
    mocked.readState.mockResolvedValue(briefing())

    render(<AgentOnboarding />)

    expect(await screen.findByRole('button', { name: /that is right/i })).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /something is wrong/i }))
    expect(screen.getByRole('textbox')).toHaveValue(
      'You are a global AI-first consulting company founded in 2001.',
    )
    expect(screen.getByRole('button', { name: /save and keep going/i })).toBeInTheDocument()
  })

  it('carries the provenance on the panel only, never twice', async () => {
    // The chips were rendered on both sides of the screen against the same
    // three facts. One claim, one receipt.
    mocked.readState.mockResolvedValue(briefing())

    render(<AgentOnboarding />)

    expect(await screen.findByText(/read · https:\/\/xebia\.com\/about-us/)).toBeInTheDocument()
    expect(screen.getAllByText(/https:\/\/xebia\.com\/about-us/)).toHaveLength(1)
  })
})

describe('AgentOnboarding staging', () => {
  it('shows the fetched pages while the read runs', async () => {
    // The reason `/start` and `/read` are two calls. After the fetch there are
    // real URLs to put on screen, and seventeen seconds of model work to cover.
    mocked.readState.mockResolvedValue({
      ...interviewing([]),
      active: false,
      phase: 'analysing',
    })
    mocked.start.mockResolvedValue({
      ...interviewing([]),
      phase: 'analysing',
      pages_read: ['https://books.toscrape.com', 'https://books.toscrape.com/about'],
    })
    let releaseRead: (s: client.AgentState) => void = () => {}
    mocked.read.mockReturnValue(
      new Promise<client.AgentState>((resolve) => {
        releaseRead = resolve
      }),
    )

    render(<AgentOnboarding />)

    // Mid-read: the count is a count of the array, never a rounded phrase.
    expect(await screen.findByText('2 pages fetched')).toBeInTheDocument()
    expect(screen.getByText('https://books.toscrape.com/about')).toBeInTheDocument()
    // The label has to say what is happening. Keyed on the wrong condition it
    // fell back to the idle string and this screen read "Loading…".
    expect(screen.getByText(/reading what is on those pages/i)).toBeInTheDocument()
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument()

    releaseRead(interviewing([]))
    await waitFor(() => expect(mocked.read).toHaveBeenCalledOnce())
  })

  it('does not re-read a session that is already past the fetch', async () => {
    mocked.readState.mockResolvedValue(interviewing([DISCOVERY_TURN]))
    mocked.nextQuestion.mockResolvedValue({
      done: false, question: 'Who are your customers?', target: 'brain.target_customers',
      scope: 2, choices: [], reason: null,
    })

    render(<AgentOnboarding />)

    await waitFor(() => expect(mocked.nextQuestion).toHaveBeenCalled())
    expect(mocked.read).not.toHaveBeenCalled()
    expect(mocked.start).not.toHaveBeenCalled()
  })
})
