'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { departmentLabel } from '@/lib/onboarding-client'
import type { Dashboards } from '@/lib/dashboard-client'

/**
 * The left panel — how you reach a place, never what decides whether the place
 * will speak to you.
 *
 * `doc/14` §0. This is the navigation that replaces the department **tab rail**,
 * and the two are not the same thing: the rail sat inside a director page and
 * gated the surface, so leaving it in place would have meant a founder choosing
 * a department before the product would say anything. The panel is global, the
 * surface underneath it is common, and every department it lists is one the
 * caller can already open.
 *
 * ## Grouped by what a thing is, not by what it is called
 *
 * The reference mock this replaces carried thirty-two sidebar entries in five
 * feature groups, which is a list that grows once per capability — ninety of
 * them, eventually. These four groups are fixed: a person, their directors,
 * their own data, and their settings. The product filling in does not lengthen
 * it.
 *
 * ## Composed, never greyed
 *
 * `all.directors` is already scoped by the API — a department the caller cannot
 * reach is absent from the response, not flagged in it. So a Marketing-only
 * contributor gets one entry under Directors and the group simply shrinks.
 * Rendering the other six disabled would advertise what somebody cannot have,
 * which is the disclosure this codebase refuses everywhere else it decides
 * between 404 and 403.
 */

type NavItem = { href: string; label: string; hint?: string }
type NavGroup = { key: string; label: string; items: NavItem[] }

/**
 * Every destination is a route that exists.
 *
 * `doc/14` sketched a *Your data* group of four — Company Brain, Documents,
 * Connections, Your answers. Only one of those is a page today; the rest are
 * panels inside setup and settings. A nav entry pointing at a route nobody
 * built is a 404 with a friendly name, so the group holds what is real and
 * grows when the pages do.
 */
export function groupsFor(all: Dashboards | null): NavGroup[] {
  const directors = (all?.directors ?? []).map((entry) => ({
    href: entry.path,
    label: entry.label ?? departmentLabel(entry.department),
  }))

  return [
    {
      key: 'today',
      label: '',
      items: [{ href: '/dashboard', label: 'Today', hint: 'What needs you' }],
    },
    // Omitted entirely rather than rendered empty: a heading over nothing reads
    // as a failed load. A caller holding no department is a real state — the
    // landing page handles it — and it must not look like a broken panel.
    ...(directors.length > 0
      ? [{ key: 'directors', label: 'Directors', items: directors }]
      : []),
    {
      key: 'data',
      label: 'Your data',
      items: [{ href: '/onboarding', label: 'Workspace setup' }],
    },
    {
      key: 'settings',
      label: 'Settings',
      items: [
        { href: '/settings', label: 'Workspace' },
        { href: '/account', label: 'Account' },
      ],
    },
  ]
}

/**
 * Whether this entry is the page being looked at.
 *
 * Exact match, with one exception for `/dashboard` — otherwise *Today* would
 * light up on every director page, because every one of their paths begins with
 * it. Two entries claiming `aria-current="page"` is a screen reader announcing
 * the wrong location.
 */
export function isCurrent(href: string, pathname: string): boolean {
  if (href === '/dashboard') return pathname === '/dashboard'
  return pathname === href || pathname.startsWith(`${href}/`)
}

export function NavPanel({ all, onNavigate }: { all: Dashboards | null; onNavigate?: () => void }) {
  const pathname = usePathname()

  return (
    <nav aria-label="Sections" className="flex flex-col gap-6">
      {groupsFor(all).map((group) => (
        <div key={group.key}>
          {group.label ? (
            <p className="mb-2 px-3 font-mono text-2xs uppercase tracking-[0.1em] text-ink-400">
              {group.label}
            </p>
          ) : null}
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const current = isCurrent(item.href, pathname)
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={current ? 'page' : undefined}
                    className={`block rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-steel-500 ${
                      current
                        ? 'bg-ink-800 font-medium text-bone-50'
                        : 'text-ink-600 hover:bg-bone-200 hover:text-ink-900'
                    }`}
                  >
                    {item.label}
                    {item.hint ? (
                      <span
                        className={`mt-0.5 block text-2xs ${
                          current ? 'text-bone-300' : 'text-ink-400'
                        }`}
                      >
                        {item.hint}
                      </span>
                    ) : null}
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )
}
