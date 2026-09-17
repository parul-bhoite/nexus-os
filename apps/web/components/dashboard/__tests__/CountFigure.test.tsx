import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BlockCard } from '@/components/dashboard/BlockCard'
import type { CountFigure, DirectorBlock } from '@/lib/dashboard-client'

/**
 * The third figure kind on screen — ADR 0034.
 *
 * The counting is `calculators/ops.py`'s and is asserted there. What only the
 * browser can get wrong is the rendering, and every case here is a way of
 * looking right while saying something false:
 *
 * - **A percentage.** The ops layer holds what somebody remembered to type, so
 *   any ratio over these rows is a wrong number with a plausible denominator.
 *   Nothing on this tile may divide, and the drawer may not either.
 * - **A count passing for a measurement.** `doc/13` §7 says a typed number and a
 *   measured one must never look identical, and rejects a badge on an otherwise
 *   identical tile. The body has to read as a tally of a record.
 * - **"Read from" copy borrowed from the other kinds.** Nothing was fetched.
 * - **Undated work folded into "on track"**, which hides how much of the open
 *   pile could never have been counted as late (I10).
 * - **An Explain button.** A count has no numerator and no denominator, so
 *   `narrate-metric` has nothing to be grounded in and the API refuses it.
 */

function count(overrides: Partial<CountFigure> = {}): CountFigure {
  return {
    kind: 'count',
    label: 'Projects recorded',
    measures:
      'Every project recorded in NEXUS, counted. Not a completion rate and not an on-time percentage.',
    noun: 'projects',
    open_label: 'still open',
    recorded: 12,
    open_items: 7,
    overdue: 2,
    undated: 3,
    recorded_at: '2026-09-14',
    self_reported: true,
    complete_as_of: '',
    confirmed_on: '',
    breakdown: [],
    method: 'calculators.ops.count_items',
    ...overrides,
  }
}

function block(figure: CountFigure | null = count()): DirectorBlock {
  return {
    key: 'operations.projects_board',
    doc05_id: '6.2',
    name: 'Active projects board',
    shows: 'Status, progress, on-time or at-risk',
    block: 'board',
    state: 'live',
    unlock: '',
    needs: [],
    figure,
  }
}

describe('what a count figure shows', () => {
  it('leads with how many were recorded and how many are open', () => {
    render(<BlockCard block={block()} department="operations" />)

    expect(screen.getByText('12')).toBeTruthy()
    expect(screen.getByText(/projects recorded, 7 still open/)).toBeTruthy()
  })

  it('says what is past a date somebody set', () => {
    render(<BlockCard block={block()} department="operations" />)

    expect(screen.getByText(/2 are past a date you set/)).toBeTruthy()
  })

  it('states the undated work rather than folding it into the rest', () => {
    /** Nobody named a day, so nothing is late. A reader weighing "2 overdue"
     *  needs to know three more could never have been counted in it. */
    render(<BlockCard block={block()} department="operations" />)

    expect(screen.getByText(/3 have no due date/)).toBeTruthy()
  })

  it('says nothing about overdue or undated when there is none of either', () => {
    render(
      <BlockCard block={block(count({ overdue: 0, undated: 0 }))} department="operations" />,
    )

    expect(screen.queryByText(/past a date/)).toBeNull()
    expect(screen.queryByText(/no due date/)).toBeNull()
  })

  it('attributes the figure to the record, not to a measurement', () => {
    /** The other two kinds read "Read <date> from your CRM". Nothing was
     *  fetched here, and borrowing that word would claim a provenance the tile
     *  does not have. */
    render(<BlockCard block={block()} department="operations" />)

    expect(screen.getByText(/Counted from what your workspace recorded/)).toBeTruthy()
    expect(screen.queryByText(/^Read /)).toBeNull()
  })

  it('draws no percentage anywhere on the tile', () => {
    /** **The rule this kind exists under.** Twelve recorded and seven open is
     *  one division away from "58% open" in any component that has both numbers
     *  and a habit. */
    const { container } = render(<BlockCard block={block()} department="operations" />)

    expect(container.textContent).not.toMatch(/%/)
    expect(container.textContent).not.toMatch(/\bout of\b/)
    expect(container.textContent).not.toMatch(/\d+\s*\/\s*\d+/)
  })

  it('offers no way to explain a number that cannot be narrated', () => {
    /** `narrate-metric` speaks in numerator, denominator and percentage. A
     *  count has none, the API refuses it with a 404, and a button that always
     *  fails is worse than no button. */
    render(<BlockCard block={block()} department="operations" />)

    expect(screen.queryByRole('button', { name: /explain/i })).toBeNull()
  })
})

describe('whether anybody has vouched for the list — D29, ADR 0035', () => {
  it('says plainly when nobody has', () => {
    /** **The common case and the most misleading one.** A count with no
     *  confirmation behind it describes the record, and a reader will take it as
     *  describing the company unless the tile says otherwise. */
    render(<BlockCard block={block()} department="operations" />)

    expect(
      screen.getByText(/have not said whether this is all of them/),
    ).toBeTruthy()
  })

  it('reports the date when somebody has', () => {
    render(
      <BlockCard
        block={block(count({ complete_as_of: '2026-09-11', confirmed_on: '2026-09-14' }))}
        department="operations"
      />,
    )

    expect(screen.getByText(/confirmed this is all of them, as of 2026-09-11/)).toBeTruthy()
    expect(screen.queryByText(/have not said whether/)).toBeNull()
  })

  it('still draws no rate once completeness is confirmed', () => {
    /** Confirming unlocks S10.4's rate in the API. It does not turn this count
     *  into one, and the tile must not start dividing because a date arrived. */
    const { container } = render(
      <BlockCard
        block={block(count({ complete_as_of: '2026-09-11', confirmed_on: '2026-09-14' }))}
        department="operations"
      />,
    )

    expect(container.textContent).not.toMatch(/%/)
    expect(container.textContent).not.toMatch(/\bout of\b/)
  })
})

describe('the severity breakdown — the issue register', () => {
  const graded = () =>
    count({
      noun: 'issues',
      label: 'Issues recorded',
      breakdown: [
        { label: 'high', count: 0 },
        { label: 'medium', count: 2 },
        { label: 'low', count: 5 },
      ],
    })

  it('shows every band, in the order the server sent', () => {
    /** Never re-sorted here: alphabetically "high" falls between "low" and
     *  "medium", which on a figure read for triage is worse than no order. */
    const { container } = render(<BlockCard block={block(graded())} department="operations" />)
    const labels = Array.from(container.querySelectorAll('dt'), (node) => node.textContent)

    expect(labels).toEqual(['high', 'medium', 'low'])
  })

  it('shows a band at zero rather than dropping it', () => {
    /** "No high-severity issues" is the reassuring thing somebody came for, and
     *  an absent row makes them count the list to be sure. */
    const { container } = render(<BlockCard block={block(graded())} department="operations" />)
    const counts = Array.from(container.querySelectorAll('dd'), (node) => node.textContent)

    expect(counts).toEqual(['0', '2', '5'])
  })

  it('draws no share, proportion or bar', () => {
    /** Three counts side by side. A stacked bar reads as a share of a whole,
     *  and ADR 0034's rule is that nothing here divides. */
    const { container } = render(<BlockCard block={block(graded())} department="operations" />)

    expect(container.textContent).not.toMatch(/%/)
    expect(container.querySelector('progress')).toBeNull()
  })

  it('renders no breakdown for a record type that has none', () => {
    const { container } = render(<BlockCard block={block()} department="operations" />)

    expect(container.querySelector('dl')).toBeNull()
  })
})

describe('the working, opened', () => {
  it('shows the partition rather than an invented checklist', () => {
    render(<BlockCard block={block()} department="operations" />)
    fireEvent.click(screen.getByRole('button', { name: /why this number/i }))

    expect(screen.getByText(/12 recorded, 5 done, 7 open/)).toBeTruthy()
    expect(screen.getByText(/2 past a date and 3 with no date/)).toBeTruthy()
  })

  it('names the method a reader can go and check, in one place only', () => {
    /** The drawer's provenance footer already carries `method` for every figure
     *  kind. The census summary said it a second time, which is two places for
     *  one string to drift apart — and the duplicate is what this caught. */
    render(<BlockCard block={block()} department="operations" />)
    fireEvent.click(screen.getByRole('button', { name: /why this number/i }))

    expect(screen.getByText('calculators.ops.count_items')).toBeTruthy()
  })

  it('keeps the drawer free of percentages too', () => {
    const { container } = render(<BlockCard block={block()} department="operations" />)
    fireEvent.click(screen.getByRole('button', { name: /why this number/i }))

    expect(container.textContent).not.toMatch(/%/)
  })
})
