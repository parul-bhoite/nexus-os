import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AgentOnboarding, greetingFor, sentence } from '@/components/onboarding/AgentOnboarding'
import * as client from '@/lib/agent-onboarding-client'
import { AuthError } from '@/lib/auth-client'
import * as docs from '@/lib/documents-client'

/**
 * Two defects a browser run found and no unit test would have, both in the seam
 * between this component and the API rather than inside either.
 *
 * They are worth a test each because neither produced an exception. One posted
 * an empty string and got a validation error back; the other rendered a screen
 * with nothing on it to click. A component that renders successfully and does
 * the wrong thing is exactly what a render-and-assert test is for.
 */

const replace = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
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
    readTools: vi.fn(),
    declareTools: vi.fn(),
    finish: vi.fn(),
  }
})

vi.mock('@/lib/documents-client', async (importOriginal) => {
  const actual = await importOriginal<typeof docs>()
  return { ...actual, readAsks: vi.fn(), listDocuments: vi.fn(), uploadDocument: vi.fn() }
})

const mocked = vi.mocked(client)
const mockedDocs = vi.mocked(docs)

/** The document asks, as `GET /documents/asks` serves them. */
const ASKS: docs.UploadStage = {
  consent: {
    text: 'I warrant that this workspace has the right to use and index this document.',
    version: '2026-08-18.v1',
  },
  departments: [
    {
      department: 'sales',
      asks: [
        {
          name: 'Your current price list',
          unlocks: 'Quoting at your real prices instead of asking you every time.',
        },
      ],
    },
  ],
  max_file_bytes: 25_000_000,
  max_files_at_onboarding: 10,
  workspace_quota_bytes: 500_000_000,
  bytes_used: 0,
  files_uploaded: 0,
}

/** The tool catalogue. `connectable: false` is the truth for all nine today. */
const TOOL_CATALOGUE: client.ToolCatalogue = {
  tools: [
    {
      id: 'hubspot',
      name: 'HubSpot',
      department: 'sales',
      department_label: 'Sales',
      unlocks: 'Answering pipeline questions from your own deals.',
      kind: 'crm',
      declared: false,
      connectable: false,
    },
  ],
  declared: [],
}

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
    ceiling: 5,
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
        // The agent's opening line, which is a sentence about the read — not a
        // copy of a statement. Keeping them distinct in the fixture is what
        // lets a test tell the transcript and the brief card apart.
        role: 'agent',
        text: 'I have read xebia.com. Here is what I think I know.',
        target: null,
        scope: null,
      },
    ]),
    phase: 'brief',
    brief: {
      statements: [
        {
          field: 'brain.profile',
          // The catalogue label, resolved server-side. The screen used to print
          // `field` — an internal key over a paragraph a founder is being asked
          // to correct.
          label: 'Company profile',
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
  replace.mockClear()
  // The two collection steps fetch on mount. Defaulted here rather than in each
  // test because most tests never reach them, and an unmocked fetch in jsdom
  // fails as a network error rather than as the assertion the test is about.
  mockedDocs.readAsks.mockResolvedValue(ASKS)
  mockedDocs.listDocuments.mockResolvedValue([])
  mocked.readTools.mockResolvedValue(TOOL_CATALOGUE)
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
    mocked.submitAnswer.mockResolvedValue({
      state: interviewing([DISCOVERY_TURN]),
      // The question now rides back with the answer, so the chip's round trip
      // is one request rather than two.
      question: null,
    })

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

    // The human label, never the catalogue key.
    expect(screen.getByText('Company profile')).toBeInTheDocument()
    expect(screen.queryByText('brain.profile')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /something is wrong/i }))
    expect(screen.getByRole('textbox')).toHaveValue(
      'You are a global AI-first consulting company founded in 2001.',
    )
    expect(screen.getByRole('button', { name: /save and keep going/i })).toBeInTheDocument()
  })

  it('carries the provenance exactly once, on the statement it belongs to', async () => {
    // The chips were rendered on both sides of the screen against the same
    // three facts. With the panel gone this card is the only place a statement
    // and its source appear — which is what makes "you outrank the website"
    // true, since a person cannot outrank a reading they were never shown.
    mocked.readState.mockResolvedValue(briefing())

    render(<AgentOnboarding />)

    expect(await screen.findByText(/read · https:\/\/xebia\.com\/about-us/)).toBeInTheDocument()
    expect(screen.getAllByText(/https:\/\/xebia\.com\/about-us/)).toHaveLength(1)
    // Read before it can be corrected: the statement is prose until the editors
    // are asked for, not a textarea nobody was told the contents of.
    expect(
      screen.getByText('You are a global AI-first consulting company founded in 2001.'),
    ).toBeInTheDocument()
  })

  it('shows no Company Brain or Your Persona panel beside the conversation', async () => {
    // Both were live ledgers filling in while the interview ran, which asked a
    // person mid-sentence about their own job to also audit a table in their
    // peripheral vision. What is recorded is still shown — the brief inline,
    // the persona at the end — but never as a second column to keep up with.
    mocked.readState.mockResolvedValue(briefing())

    render(<AgentOnboarding />)

    await screen.findByRole('button', { name: /that is right/i })
    expect(screen.queryByText('Company Brain')).not.toBeInTheDocument()
    expect(screen.queryByText('Your Persona')).not.toBeInTheDocument()
    expect(screen.queryByText(/filled in as we talk/i)).not.toBeInTheDocument()
  })
})

describe('AgentOnboarding persona confirmation', () => {
  /** The interview is over and the server has said so. */
  function interviewOver(): client.AgentState {
    return interviewing([DISCOVERY_TURN])
  }

  const DONE = {
    done: true,
    question: null,
    target: null,
    scope: null,
    choices: [],
    reason: 'I have what I need to build on.',
  }

  it('stops the assembly at the persona and puts it to the person', async () => {
    // The persona used to be written into a panel while the interview ran and
    // was never actually put to anybody. It is stage one of three, committed on
    // its own, so the run can stop here and carry on once it is confirmed.
    //
    // Driven from the **tools** step, which is where the assembly now starts.
    // It used to start from the interview's closing card; the documents and the
    // declared stack come first, because the persona is built from them.
    mocked.readState.mockResolvedValue({ ...interviewOver(), phase: 'tools' })
    mocked.declareTools.mockResolvedValue({ ...interviewOver(), phase: 'tools' })
    mocked.finish.mockResolvedValue({
      ...interviewOver(),
      phase: 'persona',
      persona: {
        summary: 'You want pipeline risk first, in short form, in English.',
        fields: [
          {
            key: 'persona.priority_topics',
            label: 'Wants first',
            value: 'Pipeline risk',
            derived_from: 'I run the site.',
          },
        ],
      },
    })

    render(<AgentOnboarding />)

    fireEvent.click(await screen.findByRole('button', { name: /i use none of these/i }))

    expect(
      await screen.findByText('You want pipeline risk first, in short form, in English.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Pipeline risk')).toBeInTheDocument()
    // One stage, then a stop. Running on to the Brain would build the workspace
    // on a persona nobody had seen.
    expect(mocked.finish).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: /that is me — finish setup/i })).toBeInTheDocument()
  })

  it('keeps going through every Brain group, which all sit at the same phase', async () => {
    // The Brain is built in groups and each one commits at phase `persona`, so
    // a loop guarding on the phase alone reads the second group as "nothing
    // moved" and stops with half a Brain. `assembly_step` is what makes the
    // difference visible.
    const at = (phase: client.AgentState['phase'], step: number): client.AgentState => ({
      ...interviewing([DISCOVERY_TURN]),
      phase,
      assembly_step: step,
    })
    mocked.readState.mockResolvedValue(at('persona', 1))
    mocked.finish
      .mockResolvedValueOnce(at('persona', 2)) // identity group
      .mockResolvedValueOnce(at('assembling', 3)) // market group — phase moves
      .mockResolvedValueOnce(at('ready', 4))

    render(<AgentOnboarding />)

    fireEvent.click(await screen.findByRole('button', { name: /that is me — finish setup/i }))

    expect(await screen.findByText(/your company brain is live/i)).toBeInTheDocument()
    expect(mocked.finish).toHaveBeenCalledTimes(3)
  })

  it('stops when neither the phase nor the assembly step moves', async () => {
    // The runaway guard. Without it a server returning the same state forever
    // spins here paying for a model call each time.
    const stuck: client.AgentState = {
      ...interviewing([DISCOVERY_TURN]),
      phase: 'persona',
      assembly_step: 2,
    }
    mocked.readState.mockResolvedValue({ ...stuck, assembly_step: 1 })
    mocked.finish.mockResolvedValue(stuck)

    render(<AgentOnboarding />)

    fireEvent.click(await screen.findByRole('button', { name: /that is me — finish setup/i }))

    await waitFor(() => expect(mocked.finish).toHaveBeenCalledTimes(2))
    expect(mocked.finish).toHaveBeenCalledTimes(2)
  })

  it('runs the remaining stages only once the persona is confirmed', async () => {
    mocked.readState.mockResolvedValue({ ...interviewOver(), phase: 'persona' })
    mocked.finish
      .mockResolvedValueOnce({ ...interviewOver(), phase: 'assembling' })
      .mockResolvedValueOnce({ ...interviewOver(), phase: 'ready' })

    render(<AgentOnboarding />)

    fireEvent.click(await screen.findByRole('button', { name: /that is me — finish setup/i }))

    expect(await screen.findByText(/your company brain is live/i)).toBeInTheDocument()
    expect(mocked.finish).toHaveBeenCalledTimes(2)
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

describe('AgentOnboarding when the opening request fails', () => {
  /**
   * Both halves of finding F7, on the screen where it did the most damage.
   *
   * The boot request fails before any state exists, so the component falls
   * through to `Booting` — and `Booting` drew a wait animation and the label
   * `useSlowLabel` returns when nothing is in flight. Whatever went wrong, a
   * visitor got a centred "Loading…" forever with nothing on the page to click,
   * and the error was rendered nowhere because the only branch that drew it sat
   * below that early return.
   */
  it('sends a signed-out visitor to sign in, and back here afterwards', async () => {
    mocked.readState.mockRejectedValue(new AuthError('Not authenticated', 401))

    render(<AgentOnboarding />)

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith('/login?next=%2Fonboarding%2Fagent'),
    )
    // Never started. A journey begun for a session that cannot write it is a
    // row nobody owns.
    expect(mocked.start).not.toHaveBeenCalled()
  })

  it('says what went wrong and offers a retry, rather than loading forever', async () => {
    mocked.readState
      .mockRejectedValueOnce(new AuthError('Could not reach the API.', 500))
      .mockResolvedValueOnce(interviewing([DISCOVERY_TURN, CORRECTION_TURN]))
    mocked.nextQuestion.mockResolvedValue({
      done: false,
      question: 'Who are your customers?',
      target: 'brain.target_customers',
      scope: 2,
      choices: [],
      reason: null,
    })

    render(<AgentOnboarding />)

    expect(await screen.findByText('Could not reach the API.')).toBeInTheDocument()
    // The pulse and the label are gone: two signals disagreeing about whether
    // anything is still happening is worse than either alone.
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    expect(await screen.findByText('Who are your customers?')).toBeInTheDocument()
    expect(screen.queryByText('Could not reach the API.')).not.toBeInTheDocument()
  })
})

describe('sentence', () => {
  // `reason` is written by the model or by the server's fallback, and neither
  // is written to be the second half of somebody else's sentence. On screen it
  // read "That is enough to build on. nothing further worth asking".
  it('makes a fragment into a sentence', () => {
    expect(sentence('nothing further worth asking')).toBe('Nothing further worth asking.')
    expect(sentence('I have what I need.')).toBe('I have what I need.')
    expect(sentence('  enough for now  ')).toBe('Enough for now.')
    expect(sentence('Ready?')).toBe('Ready?')
  })

  it('is empty for nothing, rather than a lone full stop', () => {
    expect(sentence(null)).toBe('')
    expect(sentence(undefined)).toBe('')
    expect(sentence('   ')).toBe('')
  })
})


describe('AgentOnboarding when the site cannot be read', () => {
  /** `/start` ran, the crawl found nothing, and it said so on the state. */
  function unreadable(): client.AgentState {
    return {
      ...interviewing([]),
      phase: 'analysing',
      pages_read: [],
      site_unreadable: true,
    }
  }

  it('asks the founder instead of stranding them', async () => {
    // This screen used to be the end of the road: `/start` returned 422 after
    // the account and company row already existed, and the page said the site
    // was unreadable with nothing on it to do.
    mocked.readState.mockResolvedValue(unreadable())

    render(<AgentOnboarding />)

    expect(await screen.findByText(/could not read books\.toscrape\.com/i)).toBeInTheDocument()
    expect(screen.getByLabelText('What does the company do?')).toBeInTheDocument()
    expect(screen.getByLabelText('Who actually buys from you?')).toBeInTheDocument()
    // `read` would 409 here — the boot effect must not call it.
    expect(mocked.read).not.toHaveBeenCalled()
  })

  it('will not submit until all three are answered', async () => {
    mocked.readState.mockResolvedValue(unreadable())

    render(<AgentOnboarding />)

    const submit = await screen.findByRole('button', { name: /that is us/i })
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText('What does the company do?'), {
      target: { value: 'We sell valves.' },
    })
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Who actually buys from you?'), {
      target: { value: 'Contractors.' },
    })
    fireEvent.change(
      screen.getByLabelText('What would make the next twelve months a success?'),
      { target: { value: 'More service contracts.' } },
    )
    expect(submit).toBeEnabled()
  })

  it('goes straight into the interview, with no brief to confirm', async () => {
    mocked.readState.mockResolvedValue(unreadable())
    mocked.describeCompany.mockResolvedValue({
      ...interviewing([DISCOVERY_TURN]),
      phase: 'discovery',
      turns: [],
    })

    render(<AgentOnboarding />)

    fireEvent.change(await screen.findByLabelText('What does the company do?'), {
      target: { value: 'We sell valves.' },
    })
    fireEvent.change(screen.getByLabelText('Who actually buys from you?'), {
      target: { value: 'Contractors.' },
    })
    fireEvent.change(
      screen.getByLabelText('What would make the next twelve months a success?'),
      { target: { value: 'More service contracts.' } },
    )
    fireEvent.click(screen.getByRole('button', { name: /that is us/i }))

    await waitFor(() => expect(mocked.describeCompany).toHaveBeenCalledOnce())
    expect(mocked.describeCompany).toHaveBeenCalledWith({
      profile: 'We sell valves.',
      target_customers: 'Contractors.',
      goals: 'More service contracts.',
    })
    // The opening discovery question, not a brief card.
    expect(
      await screen.findByText(/what are you responsible for, day to day\?/i),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /that is right/i })).not.toBeInTheDocument()
  })
})


describe('AgentOnboarding when a step fails', () => {
  /**
   * V5. The error rendered as a bare `role="alert"` with nothing to click, so
   * recovery depended on the person guessing that the button they had already
   * pressed would work a second time. On the assembly path it does — each stage
   * commits and `/finish` resumes at the one that broke — which is exactly why
   * leaving them to guess was the wrong shape.
   */
  function atPersona(): client.AgentState {
    return { ...interviewing([DISCOVERY_TURN]), phase: 'persona' }
  }

  it('offers a retry beside the error, and re-runs the same step', async () => {
    mocked.readState.mockResolvedValue(atPersona())
    mocked.finish
      .mockRejectedValueOnce(new Error('The assistant could not finish this step.'))
      .mockResolvedValueOnce({ ...atPersona(), phase: 'ready' })

    render(<AgentOnboarding />)

    fireEvent.click(await screen.findByRole('button', { name: /that is me — finish setup/i }))

    expect(
      await screen.findByText('The assistant could not finish this step.'),
    ).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: /try again/i })

    fireEvent.click(retry)

    expect(await screen.findByText(/your company brain is live/i)).toBeInTheDocument()
    expect(mocked.finish).toHaveBeenCalledTimes(2)
    // The error and its button go with the success.
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })

  it('offers a retry for an answer too, not only for the assembly', async () => {
    // `guard` remembers the closure, so this is not special-cased per action —
    // the brief, an answer, the manual description and every assembly stage all
    // get it from one place.
    mocked.readState.mockResolvedValue(interviewing([DISCOVERY_TURN]))
    mocked.nextQuestion.mockResolvedValue({
      done: false,
      question: 'Who are your customers?',
      target: 'brain.target_customers',
      scope: 2,
      choices: [],
      reason: null,
    })
    mocked.submitAnswer.mockRejectedValueOnce(new Error('Cannot reach the onboarding service.'))

    render(<AgentOnboarding />)

    const composer = await screen.findByLabelText(/answer in your own words/i)
    fireEvent.change(composer, { target: { value: 'Contractors' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('Cannot reach the onboarding service.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })
})

/**
 * The two steps between the interview and the assembly.
 *
 * Every test here is about *when*, not about what the screens look like. The
 * Persona and the Company Brain are assembled from whatever is in hand when
 * `finish` runs, so a journey that reached the assembly before the documents
 * and the declared stack would produce a Brain that had never read them — and
 * the only repair is assembling a second time, paying for every model call
 * again. The server refuses `finish` from either step; these prove the client
 * does not try.
 */
describe('AgentOnboarding documents and tools', () => {
  const DONE = {
    done: true,
    question: null,
    target: null,
    scope: null,
    choices: [],
    reason: 'I have what I need to build on.',
  }

  it('lands on the documents step when the interview closes, and builds nothing', async () => {
    // The closing card used to carry the button that started the assembly.
    // `GET /next` is what closes the interview *and* moves the phase, so the
    // state fetched before it says `discovery` — hence the second read, and
    // hence this test: without it the screen shows neither a question nor a
    // step, which is a resumed journey with nothing on it to do.
    mocked.readState
      .mockResolvedValueOnce(interviewing([DISCOVERY_TURN]))
      .mockResolvedValueOnce({ ...interviewing([DISCOVERY_TURN]), phase: 'documents' })
    mocked.nextQuestion.mockResolvedValue(DONE)

    render(<AgentOnboarding />)

    expect(await screen.findByText('Your current price list')).toBeInTheDocument()
    expect(screen.getByText(/that is enough to build on/i)).toBeInTheDocument()
    // The whole point. Nothing is assembled until the two steps are done.
    expect(mocked.finish).not.toHaveBeenCalled()
  })

  it('advances past the documents step without uploading anything', async () => {
    // Skippable by design — `doc/09` §6.2 — and the skip is recorded rather
    // than inferred from an empty document list, because "pressed skip" and
    // "uploaded nothing" are the same row and two different product problems.
    mocked.readState.mockResolvedValue({
      ...interviewing([DISCOVERY_TURN]),
      phase: 'documents',
    })
    mocked.documentsDone.mockResolvedValue({
      ...interviewing([DISCOVERY_TURN]),
      phase: 'tools',
    })

    render(<AgentOnboarding />)

    fireEvent.click(await screen.findByRole('button', { name: /skip for now/i }))

    await waitFor(() => expect(mocked.documentsDone).toHaveBeenCalledWith(true))
    // And it moves on rather than sitting there: the tools step is what renders
    // next, from the phase the server returned.
    expect(await screen.findByText('HubSpot')).toBeInTheDocument()
    expect(mocked.finish).not.toHaveBeenCalled()
  })

  it('declares the tools before the first assembly stage, not after it', async () => {
    // Ordering, asserted on the call order rather than on a screen. A
    // declaration that landed after `finish` would be a Brain built without
    // knowing where this company's numbers live — which is the entire reason
    // the step is here and not in settings.
    mocked.readState.mockResolvedValue({ ...interviewing([DISCOVERY_TURN]), phase: 'tools' })
    mocked.declareTools.mockResolvedValue({
      ...interviewing([DISCOVERY_TURN]),
      phase: 'tools',
    })
    mocked.finish.mockResolvedValue({ ...interviewing([DISCOVERY_TURN]), phase: 'persona' })

    render(<AgentOnboarding />)

    fireEvent.click(await screen.findByRole('checkbox', { name: /hubspot/i }))
    fireEvent.click(screen.getByRole('button', { name: /continue with 1 system/i }))

    await waitFor(() => expect(mocked.finish).toHaveBeenCalled())
    expect(mocked.declareTools).toHaveBeenCalledWith(['hubspot'], false)
    expect(mocked.declareTools.mock.invocationCallOrder[0]).toBeLessThan(
      mocked.finish.mock.invocationCallOrder[0],
    )
  })

  it('says a tick is not a connection while no connect flow exists', async () => {
    // The product's whole claim is that it never states what it cannot support.
    // A row of Connect buttons that open nothing would break it on the screen
    // that asks for trust — so the sentence comes from `connectable`, and will
    // disappear on its own when one of these becomes true.
    mocked.readState.mockResolvedValue({ ...interviewing([DISCOVERY_TURN]), phase: 'tools' })

    render(<AgentOnboarding />)

    expect(await screen.findByText(/it does not connect it/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^connect/i })).not.toBeInTheDocument()
  })
})
