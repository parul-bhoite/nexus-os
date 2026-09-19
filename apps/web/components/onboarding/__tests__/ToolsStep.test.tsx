import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
