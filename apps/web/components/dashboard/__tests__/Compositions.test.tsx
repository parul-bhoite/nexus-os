import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BlockCard } from '@/components/dashboard/BlockCard'
import type { DirectorBlock, DriversFigure, PrioritiesFigure } from '@/lib/dashboard-client'

/**
 * The two composition tiles — `doc/15` S10.7, ADR 0040 (D31).
 *
 * Both exist to *not* do something, and the rendering is where that could quietly
 * be undone:
 *
 * - **`drivers` must not show a score**, and must say why it does not. `doc/13`
 *   §7 permits a tile with no value only when it says what to do or why.
 * - **`priorities` must not merge its two lists.** The ranked one is ranked
 *   because every row is late in days; merging in a severity or a shortfall
 *   would need a weighting nobody set.
 */

function block(figure: DriversFigure | PrioritiesFigure, key: string): DirectorBlock {
  return {
    key,
    doc05_id: '',
    name: key,
    shows: '',
    block: key.includes('drivers') ? 'metric' : 'cards',
    state: 'live',
    unlock: '',
    needs: [],
    figure,
  }
}

const drivers: DriversFigure = {
  kind: 'drivers',
  label: 'What Operations is described by',
  measures: 'The seven figures below, each counted from your own records.',
  inputs: [
    { key: 'operations.projects_board', name: 'Active projects board' },
    { key: 'operations.stock_levels', name: 'Stock levels' },
  ],
  reason:
    'There is no single Operations score, and that is deliberate. Every figure below is counted from records you keep yourself.',
  method: 'none — this tile composes nothing',
}

const priorities: PrioritiesFigure = {
  kind: 'priorities',
  label: 'What is waiting on you',
  measures: 'Everything past a date you set, worst first.',
  overdue: [
    { kind_of: 'milestone', title: 'Handover', detail: '16 days past' },
    { kind_of: 'task', title: 'Order glazing', detail: '2 days past' },
  ],
  beside: [
    { kind_of: 'issue', title: 'Roof leak', detail: 'high severity, no date' },
    { kind_of: 'stock', title: 'Bolts', detail: '8 short' },
  ],
  recorded_at: '2026-09-17',
  self_reported: true,
  method: 'calculators.priorities.compose',
}

describe('the drivers tile', () => {
  it('draws no score and no delta', () => {
    const { container } = render(
      <BlockCard block={block(drivers, 'operations.score_drivers')} department="operations" />,
    )

    expect(container.textContent).not.toMatch(/\b\d+\s*\/\s*\d+/)
    expect(container.textContent).not.toMatch(/%/)
  })

  it('says why there is no score rather than leaving a blank', () => {
    /** `doc/13` §7 permits a tile with no value only when it says what to do or
     *  why. An empty metric slot is the one thing it never allows. */
    render(
      <BlockCard block={block(drivers, 'operations.score_drivers')} department="operations" />,
    )

    expect(screen.getByText(/no single Operations score, and that is deliberate/)).toBeTruthy()
  })

  it('names the figures it would have averaged', () => {
    render(
      <BlockCard block={block(drivers, 'operations.score_drivers')} department="operations" />,
    )

    expect(screen.getByText('Active projects board')).toBeTruthy()
    expect(screen.getByText('Stock levels')).toBeTruthy()
  })
})

describe('the priorities tile', () => {
  it('keeps the ranked list in the order the server sent', () => {
    /** Asserted by position in the rendered text rather than by DOM index:
     *  `BlockCard`'s own root is an `<li>`, so counting list items counts the
     *  card as well. Order is what "ranked" means, and this measures order. */
    const { container } = render(
      <BlockCard block={block(priorities, 'executive.todays_priorities')} department="executive" />,
    )
    const text = container.textContent ?? ''

    expect(text.indexOf('Handover')).toBeGreaterThan(-1)
    expect(text.indexOf('Handover')).toBeLessThan(text.indexOf('Order glazing'))
  })

  it('never re-sorts the ranking in the browser', () => {
    /** The server ranks by days past. A client that sorted alphabetically, or by
     *  kind, would present a different answer from the working drawer. */
    const { container } = render(
      <BlockCard
        block={block(
          {
            ...priorities,
            overdue: [
              { kind_of: 'task', title: 'Zebra', detail: '9 days past' },
              { kind_of: 'task', title: 'Apple', detail: '1 day past' },
            ],
          },
          'executive.todays_priorities',
        )}
        department="executive"
      />,
    )
    const text = container.textContent ?? ''

    expect(text.indexOf('Zebra')).toBeLessThan(text.indexOf('Apple'))
  })

  it('separates what is not measured in days, and labels the break', () => {
    /** **The refusal.** "high severity" and "8 short" are not days; ranking them
     *  against overdue work would need a rule nobody set. */
    render(
      <BlockCard block={block(priorities, 'executive.todays_priorities')} department="executive" />,
    )

    expect(screen.getByText(/Not measured in days/)).toBeTruthy()
  })

  it('names the unit of every measure it shows', () => {
    render(
      <BlockCard block={block(priorities, 'executive.todays_priorities')} department="executive" />,
    )

    expect(screen.getByText('16 days past')).toBeTruthy()
    expect(screen.getByText('8 short')).toBeTruthy()
  })

  it('totals nothing', () => {
    /** Every row is one record a founder can open. A total would be the score
     *  ADR 0040 refuses, arriving by another route. */
    const { container } = render(
      <BlockCard block={block(priorities, 'executive.todays_priorities')} department="executive" />,
    )

    expect(container.textContent).not.toMatch(/total/i)
    expect(container.textContent).not.toMatch(/score/i)
  })

  it('says plainly when nothing is past its date, and scopes the claim', () => {
    render(
      <BlockCard
        block={block({ ...priorities, overdue: [], beside: [] }, 'executive.todays_priorities')}
        department="executive"
      />,
    )

    expect(screen.getByText(/about what you have written down/)).toBeTruthy()
  })
})
