import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { NavPanel, groupsFor, isCurrent } from '@/components/shell/NavPanel'
import type { Dashboards } from '@/lib/dashboard-client'

/**
 * The left panel, and the two rules that are not obvious from looking at it.
 *
 * **It is composed, never greyed.** The API returns only the directors a caller
 * may open, so the panel renders what it is given. A version that drew all
 * seven and disabled six would advertise what somebody cannot have — the same
 * disclosure this codebase refuses every time it chooses 404 over 403 — and it
 * would do so on every page, permanently.
 *
 * **Exactly one entry is the current page.** `/dashboard` is a prefix of every
 * director path, so the naive check lights up *Today* alongside *Marketing* and
 * a screen reader announces two locations.
 *
 * `usePathname` is stubbed rather than routed: this is testing the panel's
 * rules, and standing a router up would test Next's.
 */

vi.mock('next/navigation', () => ({ usePathname: () => '/dashboard/marketing' }))

function dashboards(departments: string[]): Dashboards {
  return {
    directors: departments.map((department) => ({
      department,
      label: department === 'hr' ? 'People' : department[0].toUpperCase() + department.slice(1),
      title: `AI ${department} Director`,
      remit: '',
      scoreable: true,
      path: `/dashboard/${department}`,
      offering_count: 0,
    })),
    landing: null,
    delivered_count: 0,
  }
}

describe('what the panel lists', () => {
  it('shows one entry per department the caller can open, and no others', () => {
    render(<NavPanel all={dashboards(['marketing'])} />)

    expect(screen.getByRole('link', { name: 'Marketing' })).toBeTruthy()
    // The six a Marketing-only contributor cannot reach are absent from the
    // response, so they are absent from the panel — not present and disabled.
    for (const absent of ['Sales', 'Finance', 'Operations', 'People', 'Strategy']) {
      expect(screen.queryByRole('link', { name: absent })).toBeNull()
    }
  })

  it('drops the Directors heading rather than heading an empty list', () => {
    // A caller holding no department is a real state — the landing page handles
    // it — and a heading over nothing reads as a failed load.
    const keys = groupsFor(dashboards([])).map((group) => group.key)

    expect(keys).not.toContain('directors')
    expect(keys).toEqual(['today', 'data', 'settings'])
  })

  it('points only at routes that exist', () => {
    // doc/14 sketched a four-entry "Your data" group. Three of those pages were
    // never built, and a nav entry pointing at a route nobody built is a 404
    // with a friendly name.
    const built = new Set(['/dashboard', '/onboarding', '/settings', '/account'])
    const hrefs = groupsFor(dashboards([]))
      .flatMap((group) => group.items)
      .map((item) => item.href)

    expect(hrefs.every((href) => built.has(href))).toBe(true)
  })

  it('uses the label the API served, not one derived here', () => {
    // Finding F13 counted three spellings of the same department. The API
    // serves the word; deriving a second one here is how a fourth appears.
    render(<NavPanel all={dashboards(['hr'])} />)

    expect(screen.getByRole('link', { name: 'People' })).toBeTruthy()
  })
})

describe('which entry is the current page', () => {
  it('marks exactly one, even though every director path starts with /dashboard', () => {
    render(<NavPanel all={dashboards(['marketing', 'sales'])} />)

    const current = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'page')

    expect(current).toHaveLength(1)
    expect(current[0].textContent).toContain('Marketing')
  })

  it('treats Today as exact and everything else as a prefix', () => {
    // Today must not light up on a director page; Settings must still light up
    // on a sub-route it grows later.
    expect(isCurrent('/dashboard', '/dashboard')).toBe(true)
    expect(isCurrent('/dashboard', '/dashboard/marketing')).toBe(false)
    expect(isCurrent('/settings', '/settings/team')).toBe(true)
  })
})
