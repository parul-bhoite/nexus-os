'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { EntitySwitcher } from '@/components/dashboard/EntitySwitcher'
import { NavPanel } from '@/components/shell/NavPanel'
import { Logo } from '@/components/ui/Logo'
import { AuthError } from '@/lib/auth-client'
import { fetchDashboards, type Dashboards } from '@/lib/dashboard-client'

/**
 * The chrome every signed-in surface renders inside: a thin header, a left
 * panel, and one main region.
 *
 * `doc/14` step 1. Three things it is deliberately responsible for, because
 * each was previously duplicated per page or absent:
 *
 * **One fetch of `/api/dashboards`, shared.** Finding #23 is that the dashboard
 * already spends twenty-five to thirty round trips; a shell that fetched the
 * director list while `DirectorPage` fetched it again would make a known
 * problem worse to draw a sidebar. It is read once here and handed down
 * through context, so the page that needs `unanswered_questions` reads the
 * same response the nav was drawn from and the two cannot disagree.
 *
 * **One place that handles an ended session.** Finding F7: a 401 is somebody
 * whose session expired, and the only useful thing to do is send them to sign
 * in *with the page they wanted* so they come back to it. That was written per
 * page; now the shell does it for every page inside it.
 *
 * **The header carries only who and where you are.** The entity switcher (ADR
 * 0026) and the account link. Not a second navigation — if a third control
 * ever lands here, it belongs in the panel.
 *
 * ## What the shell does not do
 *
 * It does not decide what a page may show. Every scope decision stays in the
 * API: `all.directors` arrives already filtered, so the panel renders what it
 * is given and has no permission logic of its own to drift.
 */

const DashboardsContext = createContext<Dashboards | null>(null)

/**
 * The director list the shell already fetched.
 *
 * `null` while in flight, which a consumer must treat as *not yet known* and
 * never as *none* — a page that rendered "you hold no departments" during a
 * load would be stating an absence it has not established (I10).
 */
export function useDashboards(): Dashboards | null {
  return useContext(DashboardsContext)
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [all, setAll] = useState<Dashboards | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let live = true
    fetchDashboards()
      .then((dashboards) => {
        if (live) setAll(dashboards)
      })
      .catch((caught: unknown) => {
        if (!live) return
        if (caught instanceof AuthError && caught.status === 401) {
          const wanted = `${window.location.pathname}${window.location.search}`
          router.replace(`/login?next=${encodeURIComponent(wanted)}`)
          return
        }
        // Anything else is left to the page. The shell drawing an error over a
        // surface that may have loaded perfectly well would hide working
        // content behind a failure to draw a sidebar.
      })
    return () => {
      live = false
    }
  }, [router])

  const close = useCallback(() => setOpen(false), [])

  return (
    <DashboardsContext.Provider value={all}>
      <div className="min-h-screen bg-bone-50">
        <header className="sticky top-0 z-30 border-b border-ink-100 bg-bone-50/95 backdrop-blur">
          <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
            <button
              type="button"
              onClick={() => setOpen((was) => !was)}
              aria-expanded={open}
              aria-controls="shell-nav"
              className="rounded-lg border border-ink-200 px-3 py-1.5 font-mono text-2xs uppercase tracking-[0.08em] text-ink-600 hover:border-ink-300 hover:text-ink-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-steel-500 lg:hidden"
            >
              Menu
            </button>

            <Link
              href="/dashboard"
              className="inline-flex rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-500"
              aria-label="NEXUS OS dashboard"
            >
              <Logo />
            </Link>

            <div className="ml-auto flex items-center gap-4">
              {/* ADR 0026: a control once a login holds more than one entity,
                  and nothing at all for the almost-everybody who holds one. */}
              <EntitySwitcher />
              <Link
                href="/account"
                className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
              >
                Account
              </Link>
            </div>
          </div>
        </header>

        <div className="mx-auto flex w-full max-w-shell gap-8 px-4 sm:px-6">
          {/* Two renderings of one panel rather than one that moves: a single
              element repositioned by breakpoint would have to be either a
              dialog on desktop or a static list on mobile, and both are wrong
              in the other place. `hidden` keeps the desktop copy out of the
              accessibility tree on small screens. */}
          <aside
            id="shell-nav"
            className="hidden w-56 shrink-0 py-8 lg:block"
            aria-label="Primary"
          >
            <div className="sticky top-20">
              <NavPanel all={all} />
            </div>
          </aside>

          {open ? (
            <div className="fixed inset-0 z-40 lg:hidden">
              <button
                type="button"
                aria-label="Close menu"
                onClick={close}
                className="absolute inset-0 bg-ink-900/30"
              />
              <div className="relative h-full w-64 overflow-y-auto border-r border-ink-100 bg-bone-50 p-4">
                <NavPanel all={all} onNavigate={close} />
              </div>
            </div>
          ) : null}

          <main id="main" className="min-w-0 flex-1 py-8">
            {children}
          </main>
        </div>
      </div>
    </DashboardsContext.Provider>
  )
}
