import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { AreasStage } from '@/components/onboarding/stages/AreasStage'
import { fetchDepartments, saveDepartments } from '@/lib/settings-client'
import { fetchRateCard } from '@/lib/billing-client'

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/settings-client')>()
  return { ...actual, fetchDepartments: vi.fn(), saveDepartments: vi.fn() }
})

vi.mock('@/lib/billing-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/billing-client')>()
  return { ...actual, fetchRateCard: vi.fn() }
})

const RATE_CARD = {
  currency: 'OMR',
  departments: [
    {
      key: 'marketing',
      label: 'Marketing',
      amount_minor: 40000,
      tools: [
        { key: 'ga4', label: 'Google Analytics' },
        { key: 'search_console', label: 'Google Search Console' },
      ],
    },
    { key: 'sales', label: 'Sales', amount_minor: 30000, tools: [{ key: 'hubspot', label: 'HubSpot' }] },
    { key: 'finance', label: 'Finance', amount_minor: 30000, tools: [{ key: 'stripe', label: 'Stripe' }] },
    { key: 'operations', label: 'Operations', amount_minor: 20000, tools: [] },
    { key: 'hr', label: 'People', amount_minor: 20000, tools: [] },
    { key: 'strategy', label: 'Strategy', amount_minor: 25000, tools: [] },
  ],
}

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
  vi.mocked(fetchRateCard).mockReset()
  // Default: the price list resolves. Individual tests can override.
  vi.mocked(fetchRateCard).mockResolvedValue(RATE_CARD)
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

  it("shows each area's monthly price and the tools it includes", async () => {
    vi.mocked(fetchDepartments).mockResolvedValue({ departments: DEPARTMENTS, may_administer: true })
    render(<AreasStage onComplete={vi.fn()} />)

    // Price from the rate card, formatted in OMR's three decimals.
    expect(await screen.findByText('OMR 40.000')).toBeInTheDocument()
    // Included tools shown as chips on the owning area's card.
    expect(screen.getByText('Google Analytics')).toBeInTheDocument()
    expect(screen.getByText('HubSpot')).toBeInTheDocument()
    // An area with no tools says so rather than showing an empty block.
    expect(screen.getAllByText('No connected tools yet').length).toBeGreaterThan(0)
  })

  it('still lets the founder choose areas when the price list fails to load', async () => {
    vi.mocked(fetchDepartments).mockResolvedValue({ departments: DEPARTMENTS, may_administer: true })
    vi.mocked(fetchRateCard).mockRejectedValue(new Error('billing down'))
    render(<AreasStage onComplete={vi.fn()} />)

    // The cards render and are selectable; only the price detail is absent.
    const marketing = await screen.findByRole('checkbox', { name: /marketing/i })
    expect(marketing).toBeChecked()
    expect(screen.queryByText('OMR 40.000')).not.toBeInTheDocument()
  })

  it('shows a recoverable error when the department list fails to load', async () => {
    vi.mocked(fetchDepartments).mockRejectedValue(new Error('network down'))
    render(<AreasStage onComplete={vi.fn()} />)

    expect(await screen.findByText(/department list didn.t load/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
