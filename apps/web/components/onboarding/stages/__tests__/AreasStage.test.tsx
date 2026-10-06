import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { AreasStage } from '@/components/onboarding/stages/AreasStage'
import { fetchDepartments, saveDepartments } from '@/lib/settings-client'

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings-client')>()
  return { ...actual, fetchDepartments: vi.fn(), saveDepartments: vi.fn() }
})

const DEPARTMENTS = [
  { value: 'executive', label: 'Chief of Staff', running: true, capabilities: 1, answered: 0, unanswered: 0 },
  { value: 'marketing', label: 'Marketing', running: true, capabilities: 2, answered: 0, unanswered: 2 },
  { value: 'sales', label: 'Sales', running: false, capabilities: 2, answered: 0, unanswered: 2 },
  { value: 'finance', label: 'Finance', running: false, capabilities: 2, answered: 0, unanswered: 2 },
  { value: 'operations', label: 'Operations', running: false, capabilities: 2, answered: 0, unanswered: 2 },
  { value: 'hr', label: 'People', running: false, capabilities: 2, answered: 0, unanswered: 2 },
  { value: 'strategy', label: 'Strategy', running: false, capabilities: 2, answered: 0, unanswered: 2 },
]

beforeEach(() => {
  vi.mocked(fetchDepartments).mockReset()
  vi.mocked(saveDepartments).mockReset()
})

describe('AreasStage', () => {
  it('never renders Chief of Staff as a choice', async () => {
    vi.mocked(fetchDepartments).mockResolvedValue({ departments: DEPARTMENTS, may_administer: true })
    render(<AreasStage onComplete={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Marketing')).toBeInTheDocument())
    expect(screen.queryByText('Chief of Staff')).not.toBeInTheDocument()
  })

  it('pre-selects departments already running, and blocks Continue at a floor of zero', async () => {
    vi.mocked(fetchDepartments).mockResolvedValue({ departments: DEPARTMENTS, may_administer: true })
    render(<AreasStage onComplete={vi.fn()} />)

    const marketing = await screen.findByRole('checkbox', { name: /marketing/i })
    expect(marketing).toBeChecked()

    // Unchecking the only selected area brings the count to zero.
    fireEvent.click(marketing)
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.getByText('Pick at least one area to continue.')).toBeInTheDocument()
  })

  it('saves the replace-set of selected, non-executive values on Continue', async () => {
    vi.mocked(fetchDepartments).mockResolvedValue({ departments: DEPARTMENTS, may_administer: true })
    vi.mocked(saveDepartments).mockResolvedValue({ departments: DEPARTMENTS, may_administer: true })
    const onComplete = vi.fn()
    render(<AreasStage onComplete={onComplete} />)

    const sales = await screen.findByRole('checkbox', { name: /sales/i })
    fireEvent.click(sales)
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => expect(onComplete).toHaveBeenCalled())
    const sent = vi.mocked(saveDepartments).mock.calls[0][0]
    expect(sent).not.toContain('executive')
    expect([...sent].sort()).toEqual(['marketing', 'sales'].sort())
  })

  it('shows a recoverable error when the department list fails to load', async () => {
    vi.mocked(fetchDepartments).mockRejectedValue(new Error('network down'))
    render(<AreasStage onComplete={vi.fn()} />)

    expect(await screen.findByText(/department list didn.t load/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
