import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Coverage } from '@/components/dashboard/Coverage'
import type { Coverage as Bands } from '@/lib/dashboard-client'

/**
 * The coverage region on screen — ADR 0030.
 *
 * The counting is the API's and is asserted in `test_coverage_bands.py`. What
 * only the browser can get wrong is here:
 *
 * - **Nothing is hard-coded.** The whole point of doc/14 step 2 was that these
 *   numbers were estimated once and every one was wrong. A component that
 *   printed "2 / 89" would be that failure with a nicer font.
 * - **The bar cannot divide by zero.** A total of zero renders `NaN%` widths,
 *   and a bar showing nothing looks exactly like a bar showing a real zero.
 * - **The third band is named as ours.** Without that, two-of-eighty-nine reads
 *   as a product waiting on the customer.
 */

function bands(overrides: Partial<Bands> = {}): Bands {
  return { measuring: 2, reading_back: 10, not_built: 77, total: 89, ...overrides }
}

describe('the numbers come from the server', () => {
  it('renders whatever it is given rather than the figures it was designed against', () => {
    render(<Coverage bands={bands({ measuring: 5, reading_back: 3, not_built: 6, total: 14 })} />)

    expect(screen.getByText('5')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getByText('6')).toBeTruthy()
    expect(screen.getByText(/14 capabilities/)).toBeTruthy()
    // The numbers this component was written against must not survive a
    // payload that says otherwise.
    expect(screen.queryByText('77')).toBeNull()
  })

  it('describes the whole split to a screen reader, not just the bar', () => {
    render(<Coverage bands={bands()} />)
    const meter = screen.getByRole('img')

    expect(meter.getAttribute('aria-label')).toBe(
      '2 measuring, 10 reading your answers back, 77 not built yet, of 89',
    )
  })
})

describe('the things that would render wrong rather than fail', () => {
  it('does not divide by zero when a caller holds no department', () => {
    const { container } = render(
      <Coverage bands={bands({ measuring: 0, reading_back: 0, not_built: 0, total: 0 })} />,
    )

    expect(container.innerHTML).not.toContain('NaN')
    const widths = Array.from(container.querySelectorAll('[style]')).map(
      (node) => (node as HTMLElement).style.width,
    )
    expect(widths.every((width) => width === '0%')).toBe(true)
  })

  it('names the third band as ours, not as something the customer must do', () => {
    render(<Coverage bands={bands()} />)

    expect(screen.getByText(/Ours to fix, not yours/)).toBeTruthy()
    expect(screen.getByText(/no connection you\s+make would switch one on/)).toBeTruthy()
  })

  it('keeps refusing a composite score', () => {
    // ADR 0029 and 0030 refuse one on the same grounds, and this is the copy
    // that says so where a founder is most likely to look for it.
    render(<Coverage bands={bands()} />)

    expect(screen.getByText(/There is no company score/)).toBeTruthy()
  })

  it('never presents the bands as a percentage of done', () => {
    const { container } = render(<Coverage bands={bands()} />)

    // A percentage invites being read as a verdict on the business. The bar
    // carries proportion; the text carries counts.
    expect(container.textContent).not.toMatch(/\d+%/)
  })
})
