import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BlockCard } from '@/components/dashboard/BlockCard'
import type { AmountFigure, DirectorBlock } from '@/lib/dashboard-client'

/**
 * The second figure kind on screen — ADR 0033.
 *
 * The arithmetic is `calculators/pipeline.py`'s and is asserted there. What only
 * the browser can get wrong is the rendering, and every case here is a way of
 * looking right while saying something false:
 *
 * - **A null total drawn as zero.** "OMR 0" says the pipeline is worth nothing;
 *   the truth is that nothing in it could be added up (I10).
 * - **A denominator borrowed from the scored layout.** `23 / 148000` would read
 *   as a fraction, and a pipeline is not a fraction of anything.
 * - **A total that does not say what it omitted**, which is a total presented as
 *   complete.
 * - **A working drawer with an invented checklist.** A sum of rows has no nine
 *   weighted observations behind it.
 */

function amount(overrides: Partial<AmountFigure> = {}): AmountFigure {
  return {
    kind: 'amount',
    label: 'Open pipeline',
    measures: 'Every deal not closed won or lost, counted, with the priced ones totalled.',
    count: 23,
    total_minor: 148_000_00,
    currency: 'OMR',
    uncounted: 3,
    uncounted_label: 'unpriced',
    source: 'CRM',
    measured_at: '2026-09-17',
    method: 'calculators.pipeline.compute_pipeline',
    ...overrides,
  }
}

function block(figure: AmountFigure | null = amount()): DirectorBlock {
  return {
    key: 'sales.pipeline_board',
    doc05_id: '4.2',
    name: 'Pipeline overview',
    shows: 'Value by stage',
    block: 'board',
    state: 'partial',
    unlock: '',
    needs: ['crm'],
    figure,
  }
}

describe('what an amount figure shows', () => {
  it('leads with the money and says how many deals it came from', () => {
    render(<BlockCard block={block()} department="sales" />)

    expect(screen.getByText(/OMR/)).toBeTruthy()
    expect(screen.getByText(/across 23 deals/)).toBeTruthy()
  })

  it('never draws a denominator', () => {
    // The scored layout reads `30 / 65`. Borrowing it and putting the count
    // where a denominator goes would read as a fraction, and a pipeline is not
    // a fraction of anything.
    const { container } = render(<BlockCard block={block()} department="sales" />)

    expect(container.textContent).not.toMatch(/\/\s*23/)
    expect(container.textContent).not.toMatch(/23\s*\//)
    expect(container.textContent).not.toMatch(/%/)
  })

  it('says what the total leaves out', () => {
    render(<BlockCard block={block()} department="sales" />)

    expect(screen.getByText(/3 of these are unpriced/)).toBeTruthy()
  })

  it('stays silent about omissions when there are none', () => {
    const { container } = render(<BlockCard block={block(amount({ uncounted: 0 }))} department="sales" />)

    expect(container.textContent).not.toMatch(/unpriced, so/)
  })

  it('names where it was read from rather than linking a page', () => {
    // A CRM record has no URL a founder can open, so the scored figure's
    // "Measured … from <link>" would be a link to nowhere.
    const { container } = render(<BlockCard block={block()} department="sales" />)

    expect(screen.getByText(/Read 2026-09-17 from your CRM/)).toBeTruthy()
    expect(container.querySelector('a[target="_blank"]')).toBeNull()
  })
})

describe('the total that could not be computed', () => {
  it('shows the count rather than a zero when nothing could be added up', () => {
    // **The failure this whole kind exists to avoid.** "OMR 0" says the
    // pipeline is worth nothing; the truth is that two currencies cannot be
    // added, and the count is still true.
    const { container } = render(
      <BlockCard
        block={block(amount({ total_minor: null, currency: null }))}
        department="sales"
      />,
    )

    expect(container.textContent).not.toMatch(/OMR\s*0\b/)
    expect(screen.getByText('23')).toBeTruthy()
    expect(screen.getByText(/no total, because nothing here could be added up/)).toBeTruthy()
  })

  it('does not print a currency it was not given', () => {
    const { container } = render(
      <BlockCard block={block(amount({ total_minor: null, currency: null }))} department="sales" />,
    )

    expect(container.textContent).not.toContain('OMR')
  })
})

describe('the working drawer', () => {
  it('shows the counts it was built from, not an invented checklist', () => {
    // A sum of rows has no nine weighted observations behind it. Filling the
    // space would be the drawer showing working that never happened.
    render(<BlockCard block={block()} department="sales" />)
    fireEvent.click(screen.getByRole('button', { name: '+ why this number' }))

    expect(screen.getByText(/23 counted, 20 added/)).toBeTruthy()
  })
})

describe('narration', () => {
  it('is not offered for an amount figure', () => {
    // narrate-metric speaks in numerator and denominator, so a pipeline
    // sentence grounded in those keys would be grounded in nothing. The API
    // refuses it; the button must not be there to press (ADR 0033).
    render(<BlockCard block={block()} department="sales" />)

    expect(screen.queryByRole('button', { name: /Explain/ })).toBeNull()
  })
})
