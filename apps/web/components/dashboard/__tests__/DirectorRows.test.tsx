import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DirectorRows } from '@/components/dashboard/DirectorRows'
import type { DirectorRow } from '@/lib/dashboard-client'

/**
 * The directors block — `doc/14` step 6.
 *
 * Ordering and copy are the API's (`test_director_rows.py`). What is left for
 * the screen is the thing the tab rail got wrong and this must not repeat:
 * **a department the caller cannot open is absent, not dimmed.** Drawing seven
 * and greying six advertises what somebody cannot have, on every page load.
 */

function row(overrides: Partial<DirectorRow> = {}): DirectorRow {
  return {
    department: 'marketing',
    label: 'Marketing',
    path: '/dashboard/marketing',
    measuring: 2,
    unanswered: 5,
    state: 'measuring',
    line: "2 of this department's capabilities produce a figure today.",
    ...overrides,
  }
}

describe('what the block shows', () => {
  it('renders one entry per department it was given, in the order given', () => {
    render(
      <DirectorRows
        rows={[
          row(),
          row({ department: 'sales', label: 'Sales', state: 'answerable', path: '/dashboard/sales' }),
        ]}
      />,
    )

    const links = screen.getAllByRole('link')
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/dashboard/marketing',
      '/dashboard/sales',
    ])
  })

  it('shows only what the caller can open, and counts them honestly', () => {
    // A Marketing-only contributor: one row, and the heading says "director",
    // not "the 7 directors".
    render(<DirectorRows rows={[row()]} />)

    expect(screen.getByText('Your director')).toBeTruthy()
    expect(screen.queryByText('Finance')).toBeNull()
  })

  it('renders each state under its own chip', () => {
    render(
      <DirectorRows
        rows={[
          row(),
          row({ department: 'sales', label: 'Sales', state: 'answerable' }),
          row({ department: 'finance', label: 'Finance', state: 'waiting' }),
        ]}
      />,
    )

    expect(screen.getByText('Measuring')).toBeTruthy()
    expect(screen.getByText('Answerable now')).toBeTruthy()
    expect(screen.getByText('Waiting')).toBeTruthy()
  })

  it('renders the server’s sentence rather than one derived from the state', () => {
    const line = 'Nothing here can be computed yet. Most of it needs your accounting system.'
    render(<DirectorRows rows={[row({ state: 'waiting', line })]} />)

    expect(screen.getByText(line)).toBeTruthy()
  })

  it('disappears entirely for a caller who holds no department', () => {
    // Not an empty grid with a heading over it — the landing page already
    // explains that state, and a headed empty block reads as a failed load.
    const { container } = render(<DirectorRows rows={[]} />)

    expect(container.innerHTML).toBe('')
  })

  it('does not present itself as the navigation', () => {
    // The rail this replaces *was* the navigation. The block is a summary; the
    // left panel is how somebody moves.
    render(<DirectorRows rows={[row()]} />)

    expect(screen.getByText(/A summary, not a menu/)).toBeTruthy()
  })
})
