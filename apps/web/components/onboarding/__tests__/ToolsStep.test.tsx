import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToolsStep } from '@/components/onboarding/ToolsStep'
import { readTools } from '@/lib/agent-onboarding-client'

/**
 * ADR 0049's rule, at the surface it exists to protect.
 *
 * A tool carries either `unlocks` — a promise, legal only when a capability
 * requires its source — or `records`, which says what ticking it does today.
 * The API enforces that split; these are the two things the *screen* has to get
 * right, and neither is visible to `tsc`:
 *
 * 1. A `records` tool still shows its sentence, rather than rendering a blank
 *    line where every other tool has an explanation.
 * 2. A `records` tool never reaches the "what you turn on" panel. That panel is
 *    a list of promises, and putting a tool there that turns nothing on would
 *    reinvent the exact claim the split was made to remove.
 */

vi.mock('@/lib/agent-onboarding-client', () => ({
  readTools: vi.fn(),
}))

const PROMISES = {
  id: 'ga4',
  name: 'Google Analytics',
  department: 'marketing',
  department_label: 'Marketing',
  unlocks: 'Reporting your real traffic and conversions instead of leaving the tile locked.',
  records: null,
  kind: 'tool',
  declared: false,
  connectable: false,
}

const RECORDS_ONLY = {
  id: 'search_console',
  name: 'Google Search Console',
  department: 'marketing',
  department_label: 'Marketing',
  unlocks: null,
  records: 'Recorded as part of your stack — no tile reads it yet.',
  kind: 'tool',
  declared: false,
  connectable: false,
}

function renderStep() {
  vi.mocked(readTools).mockResolvedValue({
    tools: [PROMISES, RECORDS_ONLY],
    declared: [],
  })
  return render(<ToolsStep onContinue={vi.fn()} disabled={false} />)
}

function tick(name: RegExp) {
  fireEvent.click(screen.getByRole('checkbox', { name }))
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('ToolsStep', () => {
  it('shows the records sentence, so a tool nothing reads yet is not a blank line', async () => {
    renderStep()

    await waitFor(() => expect(screen.getByText('Google Search Console')).toBeTruthy())
    expect(screen.getByText(/Recorded as part of your stack/)).toBeTruthy()
  })

  it('keeps a records-only tool out of the list of what ticking turns on', async () => {
    renderStep()
    await waitFor(() => expect(screen.getByText('Google Search Console')).toBeTruthy())

    tick(/Google Search Console/)

    // It counts towards the stack — the tick is real and worth collecting …
    await waitFor(() => expect(screen.getByText('1')).toBeTruthy())
    // … but it promises nothing, so its sentence must appear exactly once: on
    // its own card, and not repeated in the panel as something gained.
    expect(screen.getAllByText(/Recorded as part of your stack/)).toHaveLength(1)
  })

  it('does list what a real promise turns on', async () => {
    renderStep()
    await waitFor(() => expect(screen.getByText('Google Analytics')).toBeTruthy())

    tick(/Google Analytics/)

    // Twice now: on the card, and in the panel as a thing gained — which is the
    // behaviour the records case above must not share.
    await waitFor(() =>
      expect(screen.getAllByText(/Reporting your real traffic/).length).toBeGreaterThan(1),
    )
  })
})

const PIPEDRIVE = {
  id: 'pipedrive',
  name: 'Pipedrive',
  department: 'sales',
  department_label: 'Sales',
  unlocks: 'Reporting your real pipeline.',
  records: null,
  kind: 'crm',
  declared: false,
  connectable: false,
}

const HUBSPOT = {
  id: 'hubspot',
  name: 'HubSpot',
  department: 'marketing',
  department_label: 'Marketing',
  unlocks: 'Reporting campaign performance.',
  records: null,
  kind: 'crm',
  declared: false,
  connectable: false,
}

const FINANCE_TOOL = {
  id: 'xero',
  name: 'Xero',
  department: 'finance',
  department_label: 'Finance',
  unlocks: 'Reporting your real invoices.',
  records: null,
  kind: 'tool',
  declared: false,
  connectable: false,
}

function renderStepWith(tools: unknown[], recommendedDepartments?: string[]) {
  vi.mocked(readTools).mockResolvedValue({ tools, declared: [] } as never)
  const onContinue = vi.fn()
  render(
    <ToolsStep
      onContinue={onContinue}
      disabled={false}
      recommendedDepartments={recommendedDepartments}
    />,
  )
  return onContinue
}

describe('ToolsStep recommendations', () => {
  it('renders no recommended section when recommendedDepartments is empty', async () => {
    renderStepWith([PROMISES, FINANCE_TOOL], [])
    await waitFor(() => expect(screen.getByText('Google Analytics')).toBeTruthy())

    expect(screen.queryByText('Recommended for you')).toBeNull()
    expect(screen.queryByText('Recommended')).toBeNull()
  })

  it('recommends a plain tool whose department was chosen', async () => {
    renderStepWith([PROMISES, FINANCE_TOOL], ['marketing'])
    await waitFor(() => expect(screen.getByText('Recommended for you')).toBeTruthy())

    expect(screen.getByText(/For the areas you chose: Marketing/)).toBeTruthy()
    const shelf = screen.getByRole('region', { name: 'Recommended for you' })
    expect(within(shelf).getByText('Google Analytics')).toBeTruthy()
    expect(within(shelf).queryByText('Xero')).toBeNull()
  })

  it('names only chosen areas that produced a recommendation, with canonical casing', async () => {
    // "operations" was chosen but the catalogue has no operations tool, so it
    // must not be named (nothing is being recommended for it) and must never
    // appear off its raw lowercase key. "marketing" has a tool and is named,
    // canonically cased.
    renderStepWith([PROMISES, FINANCE_TOOL], ['marketing', 'operations'])
    await waitFor(() => expect(screen.getByText('Recommended for you')).toBeTruthy())

    const reason = screen.getByText(/For the areas you chose:/)
    expect(reason.textContent).toContain('Marketing')
    expect(reason.textContent).not.toMatch(/operations/i)
  })

  it('recommends the whole CRM group when any one of its departments was chosen', async () => {
    renderStepWith([PIPEDRIVE, HUBSPOT, FINANCE_TOOL], ['sales'])
    await waitFor(() => expect(screen.getByText('Recommended for you')).toBeTruthy())

    const shelf = screen.getByRole('region', { name: 'Recommended for you' })
    // Both CRMs are recommended as a group, even though only "sales" was chosen
    // and HubSpot's own department is "marketing".
    expect(within(shelf).getByText('Pipedrive')).toBeTruthy()
    expect(within(shelf).getByText('HubSpot')).toBeTruthy()
    expect(within(shelf).queryByText('Xero')).toBeNull()
  })

  it('does not pre-tick recommendations, and "Add all recommended" ticks exactly the recommended ids', async () => {
    const onContinue = renderStepWith([PROMISES, RECORDS_ONLY, FINANCE_TOOL], ['marketing'])
    await waitFor(() => expect(screen.getByText('Recommended for you')).toBeTruthy())

    // Nothing ticked yet — recommending is not deciding on the founder's behalf.
    expect(screen.getByText('0')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Add all recommended' }))

    // Google Analytics is in "marketing" and gets recommended; Search Console is
    // also "marketing" so it is recommended too, but Xero ("finance") is not.
    await waitFor(() => expect(screen.getByText('2')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /Continue with 2/ }))
    expect(onContinue).toHaveBeenCalledWith(expect.arrayContaining(['ga4', 'search_console']), false)
    expect(onContinue.mock.calls[0][0]).toHaveLength(2)
  })

  it('still allows ticking an individual recommended tool, and the full catalogue card stays in sync', async () => {
    renderStepWith([PROMISES, FINANCE_TOOL], ['marketing'])
    await waitFor(() => expect(screen.getByText('Recommended for you')).toBeTruthy())

    const shelf = screen.getByRole('region', { name: 'Recommended for you' })
    fireEvent.click(within(shelf).getByRole('checkbox', { name: /Google Analytics/ }))

    await waitFor(() => expect(screen.getByText('1')).toBeTruthy())
    // Both the shelf's checkbox and its twin in the full catalogue — bound to
    // the same tool id — now read as ticked.
    const matches = screen.getAllByRole('checkbox', { name: /Google Analytics/ })
    expect(matches).toHaveLength(2)
    expect(matches.every((el) => (el as HTMLInputElement).checked)).toBe(true)
  })

  it('marks a recommended tool with a visible "Recommended" badge in the full catalogue', async () => {
    renderStepWith([PROMISES, FINANCE_TOOL], ['marketing'])
    // Appears twice on purpose: once in the shelf, once in the full catalogue
    // below it — the two views are meant to agree, not to be deduplicated.
    await waitFor(() => expect(screen.getAllByText('Google Analytics')).toHaveLength(2))

    expect(screen.getAllByText('Recommended').length).toBeGreaterThan(0)
    expect(screen.queryByText('Xero')).toBeTruthy()
  })
})
