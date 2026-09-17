import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BlockCard } from '@/components/dashboard/BlockCard'
import type { DirectorBlock, RateFigure } from '@/lib/dashboard-client'

/**
 * The fourth figure kind — ADR 0036, and the only ops figure that divides.
 *
 * The arithmetic is `calculators/dispatch.py`'s and the gates are
 * `compute_rate_from_ops`'s. What only the browser can get wrong is the
 * rendering, and a rate has more ways to mislead than any other kind here:
 *
 * - **A refusal drawn as 0%.** "0% on time" is a damning figure; the truth is
 *   that we may not divide at all (I10).
 * - **A percentage with no denominator**, which is a claim nobody can check.
 * - **A shared "unavailable" message.** The two gates are different problems —
 *   one takes ten seconds to fix and one does not — so a single sentence would
 *   send half the readers to do the wrong thing.
 * - **A rule left invisible.** A percentage judged by a threshold the reader
 *   cannot see is a percentage they cannot argue with.
 */

function rate(overrides: Partial<RateFigure> = {}): RateFigure {
  return {
    kind: 'rate',
    label: 'Dispatched on time',
    measures: 'Of the orders that actually went out, the share that left on or before the date you promised.',
    percentage: 75,
    numerator: 3,
    denominator: 4,
    outstanding: 3,
    overdue: 2,
    grace_days: 1,
    refused: '',
    self_reported: true,
    complete_as_of: '2026-09-11',
    confirmed_on: '2026-09-14',
    recorded_at: '2026-09-14',
    method: 'calculators.dispatch.on_time_rate',
    ...overrides,
  }
}

function block(figure: RateFigure): DirectorBlock {
  return {
    key: 'operations.on_time_dispatch',
    doc05_id: '',
    name: 'On-time dispatch',
    shows: 'What went out on time against the promised lead time',
    block: 'metric',
    state: 'live',
    unlock: '',
    needs: [],
    figure,
  }
}

describe('when both gates are open', () => {
  it('leads with the percentage and carries its denominator', () => {
    render(<BlockCard block={block(rate())} department="operations" />)

    expect(screen.getByText('75%')).toBeTruthy()
    expect(screen.getByText(/3 of 4 orders that went out/)).toBeTruthy()
  })

  it('states the rule it was computed under', () => {
    render(<BlockCard block={block(rate())} department="operations" />)

    expect(screen.getByText(/Late means more than 1 day past the date you promised/)).toBeTruthy()
  })

  it('agrees in number when a single order is outstanding', () => {
    /** "1 of those are past the promise" was what the first render of this tile
     *  actually said. With one outstanding order there is no "those". */
    render(
      <BlockCard
        block={block(rate({ outstanding: 1, overdue: 1 }))}
        department="operations"
      />,
    )

    expect(screen.getByText(/1 order has not gone out yet, and it is past the promise/)).toBeTruthy()
    expect(screen.queryByText(/of those are/)).toBeNull()
  })

  it('reports the orders it left out rather than folding them in', () => {
    /** Dividing by work that has not happened would report a backlog as
     *  lateness, so outstanding orders sit beside the rate, not inside it. */
    render(<BlockCard block={block(rate())} department="operations" />)

    expect(screen.getByText(/3 orders have not gone out yet/)).toBeTruthy()
    expect(screen.getByText(/2 of those are past the promise/)).toBeTruthy()
  })
})

describe('when a gate is shut', () => {
  it('never draws zero per cent in place of a refusal', () => {
    /** **The worst thing this tile could do.** "0% on time" is a damning
     *  figure, and the truth is that we may not divide at all. */
    const { container } = render(
      <BlockCard
        block={block(rate({ refused: 'unvouched', percentage: null, numerator: null, denominator: null }))}
        department="operations"
      />,
    )

    expect(container.textContent).not.toMatch(/0%/)
    expect(container.textContent).not.toMatch(/\d+%/)
  })

  it('tells an unvouched reader to confirm the record', () => {
    render(
      <BlockCard
        block={block(rate({ refused: 'unvouched', percentage: null, numerator: null, denominator: null, complete_as_of: '' }))}
        department="operations"
      />,
    )

    expect(screen.getByText(/Confirm on Your work that this is all of your orders/)).toBeTruthy()
  })

  it('tells a reader with no rule to set one — a different job', () => {
    /** The two refusals must not share a sentence: one is answerable in ten
     *  seconds and the other needs the founder to vouch for a whole record. */
    render(
      <BlockCard
        block={block(rate({ refused: 'no_rule', percentage: null, numerator: null, denominator: null, grace_days: null }))}
        department="operations"
      />,
    )

    expect(screen.getByText(/Set how many days past the promised date/)).toBeTruthy()
    expect(screen.queryByText(/Confirm on Your work/)).toBeNull()
  })

  it('says plainly when nothing has gone out, and asks for nothing', () => {
    /** The customer has done everything asked. A call to action here would send
     *  them looking for a setting that is already correct. */
    render(
      <BlockCard
        block={block(rate({ refused: 'nothing_sent', percentage: null, numerator: null, denominator: null, outstanding: 3, overdue: 0 }))}
        department="operations"
      />,
    )

    expect(screen.getByText(/Nothing has gone out yet/)).toBeTruthy()
    expect(screen.queryByText(/Confirm on Your work/)).toBeNull()
    expect(screen.queryByText(/Set how many days/)).toBeNull()
  })

  it('still shows the counts, because they are true either way', () => {
    render(
      <BlockCard
        block={block(rate({ refused: 'no_rule', percentage: null, numerator: null, denominator: null, grace_days: null, outstanding: 2, overdue: 1 }))}
        department="operations"
      />,
    )

    expect(screen.getByText(/2 orders have not gone out yet/)).toBeTruthy()
  })

  it('hides the rule line when there is no rule to state', () => {
    render(
      <BlockCard
        block={block(rate({ refused: 'no_rule', percentage: null, numerator: null, denominator: null, grace_days: null }))}
        department="operations"
      />,
    )

    expect(screen.queryByText(/Late means more than/)).toBeNull()
  })
})
