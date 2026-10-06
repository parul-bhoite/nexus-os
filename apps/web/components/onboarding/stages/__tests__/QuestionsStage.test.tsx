import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QuestionsStage } from '@/components/onboarding/stages/QuestionsStage'
import { fetchQuestions, saveAnswers, type Question } from '@/lib/onboarding-client'
import { ModelUnavailableError, read, start } from '@/lib/agent-onboarding-client'

vi.mock('@/lib/onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/onboarding-client')>()
  return { ...actual, fetchQuestions: vi.fn(), saveAnswers: vi.fn() }
})

vi.mock('@/lib/agent-onboarding-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/agent-onboarding-client')>()
  return { ...actual, start: vi.fn(), read: vi.fn() }
})

function question(overrides: Partial<Question>): Question {
  return {
    key: 'currency',
    prompt: 'Which currency do you report in?',
    stage: 'pass_1',
    answer_type: 'single_choice',
    scope: 'L2',
    department: null,
    required: false,
    why: 'Every figure NEXUS shows is in this currency.',
    options: [
      { value: 'OMR', label: 'OMR' },
      { value: 'AED', label: 'AED' },
    ],
    free_entry: false,
    writable: true,
    value: null,
    ...overrides,
  }
}

const CURRENCY = question({})
const MARKETING_BUDGET = question({
  key: 'marketing_budget',
  prompt: 'What is your monthly marketing budget?',
  answer_type: 'money',
  department: 'marketing',
  why: 'Used to size campaign recommendations.',
  options: [],
})
const SALES_DEAL_SIZE = question({
  key: 'deal_size',
  prompt: "What's your average deal size?",
  answer_type: 'money',
  department: 'sales',
  why: 'Used for pipeline value and forecasting.',
  options: [{ value: 'small', label: 'Under 1,000 OMR' }],
  free_entry: true,
})

beforeEach(() => {
  vi.mocked(fetchQuestions).mockReset()
  vi.mocked(saveAnswers).mockReset()
  vi.mocked(start).mockReset()
  vi.mocked(read).mockReset()
})

describe('QuestionsStage', () => {
  it('filters the catalogue to company-wide questions plus the selected departments', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [CURRENCY, MARKETING_BUDGET, SALES_DEAL_SIZE],
      can_administer: true,
      members: [],
    })

    render(
      <QuestionsStage
        selectedDepartments={['marketing']}
        onAuraChange={vi.fn()}
        onComplete={vi.fn()}
      />,
    )

    // department: null is always included; marketing is selected, sales is not —
    // so the catalogue of 3 narrows to 2 (currency + the marketing question).
    expect(await screen.findByText(CURRENCY.prompt)).toBeInTheDocument()
    expect(screen.getByText(/0 of 2 answered/i)).toBeInTheDocument()
  }, 10_000)

  it('does not re-ask what the earlier stages already captured (company_url, role, department)', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    const companyUrl = question({
      key: 'company_url',
      prompt: 'Your website address',
      answer_type: 'url',
      department: null,
      options: [],
      value: null,
    })
    const role = question({ key: 'role', prompt: 'What is your role?', department: null })
    const dept = question({ key: 'department', prompt: 'Which department is that in?', department: null })
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [companyUrl, role, dept, CURRENCY],
      can_administer: true,
      members: [],
    })

    render(<QuestionsStage selectedDepartments={[]} onAuraChange={vi.fn()} onComplete={vi.fn()} />)

    // All three are company-wide (department: null) and unanswered, yet each is
    // captured by an earlier stage — so of the catalogue of 4 only the currency
    // question survives, and the count is 1, not 4.
    expect(await screen.findByText(CURRENCY.prompt)).toBeInTheDocument()
    expect(screen.queryByText('Your website address')).not.toBeInTheDocument()
    expect(screen.queryByText('What is your role?')).not.toBeInTheDocument()
    expect(screen.queryByText('Which department is that in?')).not.toBeInTheDocument()
    expect(screen.getByText(/0 of 1 answered/i)).toBeInTheDocument()
  }, 10_000)

  it('degrades silently to the catalogue when the scan has no model configured', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    vi.mocked(read).mockRejectedValue(new ModelUnavailableError('no key'))
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [CURRENCY],
      can_administer: true,
      members: [],
    })
    const onAuraChange = vi.fn()

    render(
      <QuestionsStage selectedDepartments={[]} onAuraChange={onAuraChange} onComplete={vi.fn()} />,
    )

    expect(await screen.findByText(CURRENCY.prompt)).toBeInTheDocument()
    expect(onAuraChange).toHaveBeenCalledWith('thinking')
    expect(onAuraChange).toHaveBeenCalledWith('idle')
  }, 10_000)

  it('saves a single string for single_choice and an array for multi_choice', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    const multi = question({
      key: 'tools',
      answer_type: 'multi_choice',
      options: [
        { value: 'a', label: 'A' },
        { value: 'b', label: 'B' },
      ],
    })
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [CURRENCY, multi],
      can_administer: true,
      members: [],
    })
    vi.mocked(saveAnswers).mockResolvedValue(['currency'])

    render(<QuestionsStage selectedDepartments={[]} onAuraChange={vi.fn()} onComplete={vi.fn()} />)

    await screen.findByText(CURRENCY.prompt)
    fireEvent.click(screen.getByRole('button', { name: 'OMR' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() =>
      expect(saveAnswers).toHaveBeenCalledWith([{ key: 'currency', value: 'OMR' }]),
    )

    await screen.findByText(multi.prompt)
    fireEvent.click(screen.getByRole('button', { name: 'A' }))
    fireEvent.click(screen.getByRole('button', { name: 'B' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() =>
      expect(saveAnswers).toHaveBeenCalledWith([{ key: 'tools', value: ['a', 'b'] }]),
    )
  }, 10_000)

  it('saves a money answer as a number, not the string the input holds', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    const deal = question({
      key: 'deal_size',
      prompt: "What's your average deal size?",
      answer_type: 'money',
      options: [],
    })
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [deal],
      can_administer: true,
      members: [],
    })
    vi.mocked(saveAnswers).mockResolvedValue(['deal_size'])

    render(<QuestionsStage selectedDepartments={[]} onAuraChange={vi.fn()} onComplete={vi.fn()} />)

    const input = await screen.findByLabelText("What's your average deal size?")
    fireEvent.change(input, { target: { value: '5,000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    // The API rejects a string with "must be a number"; the value must arrive as 5000.
    await waitFor(() =>
      expect(saveAnswers).toHaveBeenCalledWith([{ key: 'deal_size', value: 5000 }]),
    )
  }, 10_000)

  it('refuses a non-numeric money answer locally, without a round trip', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    const deal = question({
      key: 'deal_size',
      prompt: "What's your average deal size?",
      answer_type: 'money',
      options: [],
    })
    const second = question({ key: 'second', prompt: 'A second question' })
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [deal, second],
      can_administer: true,
      members: [],
    })

    render(<QuestionsStage selectedDepartments={[]} onAuraChange={vi.fn()} onComplete={vi.fn()} />)

    const input = await screen.findByLabelText("What's your average deal size?")
    fireEvent.change(input, { target: { value: 'lots' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    // No save, stays on the question, shows an actionable message.
    expect(saveAnswers).not.toHaveBeenCalled()
    expect(await screen.findByText(/Enter the amount as a number/i)).toBeInTheDocument()
    expect(screen.getByText("What's your average deal size?")).toBeInTheDocument()

    // Skipping clears the message rather than carrying it onto the next question.
    fireEvent.click(screen.getByRole('button', { name: 'Skip this one' }))
    expect(await screen.findByText('A second question')).toBeInTheDocument()
    expect(screen.queryByText(/Enter the amount as a number/i)).not.toBeInTheDocument()
  }, 10_000)

  it('"Skip this one" advances without saving', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    const second = question({ key: 'second', prompt: 'A second question' })
    vi.mocked(fetchQuestions).mockResolvedValue({
      questions: [CURRENCY, second],
      can_administer: true,
      members: [],
    })

    render(<QuestionsStage selectedDepartments={[]} onAuraChange={vi.fn()} onComplete={vi.fn()} />)

    await screen.findByText(CURRENCY.prompt)
    fireEvent.click(screen.getByRole('button', { name: 'Skip this one' }))

    expect(await screen.findByText('A second question')).toBeInTheDocument()
    expect(saveAnswers).not.toHaveBeenCalled()
  }, 10_000)

  it('shows the empty state and still offers a way out when nothing is left to ask', async () => {
    vi.mocked(start).mockRejectedValue(new ModelUnavailableError('no key'))
    vi.mocked(fetchQuestions).mockResolvedValue({ questions: [], can_administer: true, members: [] })
    const onComplete = vi.fn()

    render(<QuestionsStage selectedDepartments={[]} onAuraChange={vi.fn()} onComplete={onComplete} />)

    const button = await screen.findByRole('button', { name: 'Continue to your workspace' })
    fireEvent.click(button)
    expect(onComplete).toHaveBeenCalled()
  }, 10_000)
})
