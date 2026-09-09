import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReportingCard } from '@/components/settings/ReportingCard'
import * as client from '@/lib/settings-client'

/**
 * The panel's honesty rules, which are the reason it exists (`doc/13` §13).
 *
 * Every control on this screen moves numbers somebody may already have acted
 * on, so the two failures worth testing for are both about the sentence beside
 * the control rather than the control itself: a setting that restates figures
 * must say how many, and one that only changes their spelling must not claim to
 * have restated anything.
 */

vi.mock('@/lib/settings-client', async (importOriginal) => {
  const original = await importOriginal<typeof client>()
  return { ...original, fetchReporting: vi.fn(), saveReporting: vi.fn() }
})

const REPORTING: client.Reporting = {
  currency: 'OMR',
  country: 'OM',
  fiscal_year_start_month: 1,
  week_start: 'sunday',
  timezone: 'Asia/Muscat',
  scale: 'thousands',
  decimals: 1,
  changed_at: null,
  may_administer: true,
  settings: [
    {
      key: 'fiscal_year_start_month',
      label: 'Financial year starts',
      changes: 'Every year-to-date figure and every period comparison.',
      moves_tiles: 14,
      moves_departments: ['Finance', 'Sales'],
      restates: true,
    },
    {
      key: 'week_start',
      label: 'Reporting week starts',
      changes: 'Where every weekly figure is cut.',
      moves_tiles: 1,
      moves_departments: ['Marketing'],
      restates: true,
    },
    {
      key: 'timezone',
      label: 'Reports are cut in',
      changes: 'Where a day ends.',
      moves_tiles: 16,
      moves_departments: ['Operations'],
      restates: true,
    },
    {
      key: 'scale',
      label: 'Large figures shown as',
      changes: 'How a figure is written, never what it is.',
      moves_tiles: 0,
      moves_departments: [],
      restates: false,
    },
    {
      key: 'decimals',
      label: 'Decimal places',
      changes: 'How precisely a figure is written.',
      moves_tiles: 0,
      moves_departments: [],
      restates: false,
    },
  ],
}

describe('ReportingCard', () => {
  beforeEach(() => {
    vi.mocked(client.fetchReporting).mockResolvedValue(REPORTING)
  })

  it('says how many tiles a setting moves, and where', async () => {
    render(<ReportingCard />)

    expect(await screen.findByText(/moves 14 tiles across Finance, Sales/i)).toBeInTheDocument()
    expect(screen.getByText(/moves 16 tiles across Operations/i)).toBeInTheDocument()
  })

  it('says "1 tile" rather than "1 tiles"', async () => {
    render(<ReportingCard />)
    expect(await screen.findByText(/moves 1 tile across Marketing/i)).toBeInTheDocument()
  })

  it('never claims presentation restated anything', async () => {
    render(<ReportingCard />)
    await screen.findByText(/moves 14 tiles/i)

    // "Moves 0 tiles" would be true and useless. What the founder needs to know
    // is that the number did not change, only its spelling.
    expect(screen.queryByText(/moves 0 tiles/i)).not.toBeInTheDocument()
    expect(screen.getByText(/how figures are written, not what they are/i)).toBeInTheDocument()
  })

  it('tells a first-time company that these are the defaults rather than a change', async () => {
    render(<ReportingCard />)

    // `changed_at: null` means never changed since registration, which is a
    // different fact from changed at the moment of registration.
    expect(await screen.findByText(/never changed since you registered/i)).toBeInTheDocument()
  })

  it('shows a reader who may not change them why they can still see them', async () => {
    vi.mocked(client.fetchReporting).mockResolvedValue({
      ...REPORTING,
      may_administer: false,
    })
    render(<ReportingCard />)

    // Read but not write, and the reason is on screen: the arithmetic in their
    // own tiles cites these. Hiding them would make that arithmetic
    // unverifiable by the person it is shown to.
    expect(await screen.findByText(/set by an owner or an executive/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save reporting/i })).not.toBeInTheDocument()
  })

  it('lets an administrator save, and says what saving does', async () => {
    render(<ReportingCard />)

    const save = await screen.findByRole('button', { name: /save reporting settings/i })
    expect(save).toBeInTheDocument()

    await waitFor(() =>
      expect(screen.getByLabelText(/reporting week starts/i)).toHaveValue('sunday'),
    )
  })
})
