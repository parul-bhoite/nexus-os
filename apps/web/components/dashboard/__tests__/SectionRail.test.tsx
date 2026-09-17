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
 *
 * ## The controls are `tab`, not `button`
 *
 * These queries named `button` until the rail became a real tab list. A set of
 * controls that switches panels is `tablist`/`tab` in the WAI pattern, and an
 * explicit `role="tab"` replaces the implicit `button` role — so the role these
 * assertions name changed while everything they assert did not. The behaviour
 * pinned here is unchanged: one control per served section, in the order
 * served, exactly one current, the key reported rather than acted on, and a
 * count of what is on the tab.
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

    const labels = screen.getAllByRole('tab').map((button) => button.textContent ?? '')

    expect(labels[0]).toContain('Overview')
    expect(labels[1]).toContain('Cash & runway')
    // The tell-tale: sorted alphabetically, Approvals would be first.
    expect(labels[0]).not.toContain('Approvals')
  })

  it('marks exactly one tab as current', () => {
    render(<SectionRail sections={FINANCE} active="cash" onSelect={() => {}} />)

    // `aria-selected`, not `aria-current="page"`. A tab inside a page is not a
    // page, and the nav panel uses `aria-current="page"` for the destinations
    // that really are — keeping the two attributes distinct is what stops a
    // screen reader announcing two different "current" things at once.
    const current = screen
      .getAllByRole('tab')
      .filter((tab) => tab.getAttribute('aria-selected') === 'true')

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

    fireEvent.click(screen.getByRole('tab', { name: /receivables/i }))

    expect(onSelect).toHaveBeenCalledWith('receivables')
  })

  it('counts what is on a tab, not what works on it', () => {
    // The count is honest about being a count. Every block says which state it
    // is in on its own card, and a badge that showed "2 live" while nothing is
    // live would be the one number on this page that is invented.
    render(<SectionRail sections={FINANCE} active="overview" onSelect={() => {}} />)

    expect(screen.getByRole('tab', { name: /overview/i }).textContent).toContain('2')
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
