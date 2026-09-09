import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SectionRail } from '@/components/dashboard/SectionRail'
import type { Section } from '@/lib/dashboard-client'

/**
 * The rail's two rules: the order is served, and an empty tab never arrives.
 *
 * `doc/13` §4. Both are decided server-side, so what this asserts is that the
 * browser does not undo either — the failure mode is a component that "helpfully"
 * sorts, which would put Approvals before Cash on the Finance page.
 */

function section(key: string, label: string, count: number): Section {
  return {
    key,
    label,
    blocks: Array.from({ length: count }, (_unused, index) => ({
      key: `finance.tile_${index}`,
      doc05_id: '',
      name: `Tile ${index}`,
      shows: 'Something',
      block: 'metric' as const,
      state: 'planned' as const,
      unlock: '',
      needs: [],
    })),
  }
}

// Finance, as `doc/08` §4C orders it — minus Payables, which the API omits
// because no capability fills it.
const FINANCE: Section[] = [
  section('overview', 'Overview', 2),
  section('cash', 'Cash & runway', 2),
  section('receivables', 'Receivables', 1),
  section('approvals', 'Approvals', 1),
]

describe('SectionRail', () => {
  it('renders the tabs in the order they were served', () => {
    render(<SectionRail sections={FINANCE} active="overview" onSelect={() => {}} />)

    const labels = screen.getAllByRole('button').map((button) => button.textContent ?? '')

    expect(labels[0]).toContain('Overview')
    expect(labels[1]).toContain('Cash & runway')
    // The tell-tale: sorted alphabetically, Approvals would be first.
    expect(labels[0]).not.toContain('Approvals')
  })

  it('marks exactly one tab as current', () => {
    render(<SectionRail sections={FINANCE} active="cash" onSelect={() => {}} />)

    const current = screen
      .getAllByRole('button')
      .filter((button) => button.getAttribute('aria-current') === 'page')

    expect(current).toHaveLength(1)
    expect(current[0].textContent).toContain('Cash & runway')
  })

  it('reports the tab a person picked without deciding anything itself', () => {
    // `fireEvent` rather than `user-event`: the second is not installed, and the
    // repository has no lockfile (finding #16), so every added package is one
    // more thing CI resolves differently from every developer. One click does
    // not earn that.
    const onSelect = vi.fn()
    render(<SectionRail sections={FINANCE} active="overview" onSelect={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /receivables/i }))

    expect(onSelect).toHaveBeenCalledWith('receivables')
  })

  it('counts what is on a tab, not what works on it', () => {
    // The count is honest about being a count. Every block says which state it
    // is in on its own card, and a badge that showed "2 live" while nothing is
    // live would be the one number on this page that is invented.
    render(<SectionRail sections={FINANCE} active="overview" onSelect={() => {}} />)

    expect(screen.getByRole('button', { name: /overview/i }).textContent).toContain('2')
  })

  it('renders nothing at all when there are no sections', () => {
    // A rail with no tabs is not a rail. The director page falls back to the
    // flat list rather than drawing an empty strip.
    const { container } = render(
      <SectionRail sections={[]} active="" onSelect={() => {}} />,
    )

    expect(container.querySelectorAll('button')).toHaveLength(0)
  })
})
