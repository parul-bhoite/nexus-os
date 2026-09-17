'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { NavPanel } from '@/components/shell/NavPanel'
import { WorkspaceMenu } from '@/components/shell/WorkspaceMenu'
import { AccountMenu } from '@/components/shell/AccountMenu'
import { Logo } from '@/components/ui/Logo'
import { Sheet } from '@/components/ui/Overlay'
import { ToastProvider } from '@/components/ui/Toast'
import { AuthError } from '@/lib/auth-client'
import { fetchDashboards, type Dashboards } from '@/lib/dashboard-client'
import { fetchWorkspaces, type WorkspaceChoice } from '@/lib/settings-client'

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
 * **The header carries only who and where you are.** The workspace, the entity
 * switcher (ADR 0026) and the account menu. Not a second navigation.
 *
 * ## What the 2026-09 audit changed
 *
 * **The header and the body now share one container.** They did not. The header
 * was full-width with `px-4 sm:px-6`; the body was `max-w-shell mx-auto` with
 * the same padding. At 1440 that put the logo at x=28 and the first nav row at
 * x=120 — two left edges, 92px apart, on the same screen. Both now use
 * `.app-shell`, so there is one.
 *
 * **The workspace is named in the header.** `EntitySwitcher` renders nothing for
 * a single-entity login, which is almost everybody, so the product never said
 * which company you were in. Given that ADR 0026 calls reading one company's
 * figures under another's name the worst failure this product can have, the
 * name belongs on screen at all times — not only when a switcher happens to be
 * there. `WorkspaceMenu` shows it always and becomes a switcher when there is
 * something to switch to.
 *
 * **`/api/auth/workspaces` is fetched here, once.** The audit's network trace
 * showed it four times per page load at six to twelve seconds each. It was
 * called by `EntitySwitcher`, which mounted in the header, and again by
 * `AccountPanel`. It is read once here for the same reason `/api/dashboards`
 * is.
 *
 * **Account is a menu, not a link.** It was a bare underlined text link beside
 * the logo, duplicating the sidebar's own Account row, with no sign-out except
 * on the page it led to.
 *
 * **The mobile drawer is a real dialog.** It was `open ? <div/> : null`: no
 * transition, no close button, no focus trap, no Escape, and a scrim so faint
 * the page behind stayed fully legible. It is now a `Sheet`, which owns all six
 * of those obligations in one place.
 *
 * ## What the shell does not do
 *
 * It does not decide what a page may show. Every scope decision stays in the
 * API: `all.directors` arrives already filtered, so the panel renders what it
 * is given and has no permission logic of its own to drift.
 */

const DashboardsContext = createContext<Dashboards | null>(null)
const WorkspacesContext = createContext<WorkspaceChoice[] | null>(null)

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

/** The companies this login holds. `null` while unknown, for the same reason. */
export function useWorkspaces(): WorkspaceChoice[] | null {
  return useContext(WorkspacesContext)
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [all, setAll] = useState<Dashboards | null>(null)
  const [workspaces, setWorkspaces] = useState<WorkspaceChoice[] | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let live = true

    function expired(caught: unknown): boolean {
      if (caught instanceof AuthError && caught.status === 401) {
        const wanted = `${window.location.pathname}${window.location.search}`
        router.replace(`/login?next=${encodeURIComponent(wanted)}`)
        return true
      }
      return false
    }

    fetchDashboards()
      .then((dashboards) => {
        if (live) setAll(dashboards)
      })
      .catch((caught: unknown) => {
        if (!live || expired(caught)) return
        // Anything else is left to the page. The shell drawing an error over a
        // surface that may have loaded perfectly well would hide working
        // content behind a failure to draw a sidebar.
      })

    fetchWorkspaces()
      .then((page) => {
        if (live) setWorkspaces(page.workspaces)
      })
      .catch((caught: unknown) => {
        if (!live || expired(caught)) return
        // An empty array is *known to be empty*, which is wrong here — the
        // request failed, so we do not know. `WorkspaceMenu` renders the
        // unknown case as a quiet fallback rather than as "no companies".
      })

    return () => {
      live = false
    }
  }, [router])

  // Close the drawer when the route changes. Without this, tapping a director
  // on a phone leaves the panel sitting over the page it just navigated to.
  useEffect(() => setOpen(false), [pathname])

  const close = useCallback(() => setOpen(false), [])

  return (
    <ToastProvider>
      <DashboardsContext.Provider value={all}>
        <WorkspacesContext.Provider value={workspaces}>
          <div className="on-bone min-h-screen bg-bone-50">
            <header className="sticky top-0 z-header border-b border-ink-100 bg-bone-50/90 backdrop-blur-md">
              <div className="app-shell flex h-[var(--app-header-h)] items-center gap-3">
                <button
                  type="button"
                  onClick={() => setOpen(true)}
                  aria-expanded={open}
                  aria-haspopup="dialog"
                  aria-label="Open navigation"
                  // An icon at 44×44, not a 56×30 box labelled "MENU". The old
                  // one was under the touch minimum on both axes and spelled a
                  // word every other app draws.
                  className="-ml-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink-600 transition-colors duration-micro ease-out hover:bg-bone-200 hover:text-ink-900 lg:hidden"
                >
                  <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
                    <path
                      d="M3 5.5h14M3 10h14M3 14.5h14"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>

                <Link
                  href="/dashboard"
                  className="inline-flex shrink-0 rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-4 focus-visible:ring-offset-bone-50"
                  aria-label="NEXUS OS dashboard"
                >
                  <Logo />
                </Link>

                {/* Which company you are in. Always, not only when there are
                    two — see the note above about ADR 0026. */}
                <WorkspaceMenu workspaces={workspaces} className="hidden min-w-0 sm:flex" />

                <div className="ml-auto flex shrink-0 items-center gap-1">
                  <AccountMenu />
                </div>
              </div>
            </header>

            <div className="app-shell flex w-full gap-8">
              <aside
                className="hidden w-[var(--app-nav-w)] shrink-0 py-7 lg:block"
                aria-label="Primary"
              >
                <div className="sticky top-[calc(var(--app-header-h)+1.25rem)]">
                  <NavPanel all={all} />
                </div>
              </aside>

              <main id="main" className="min-w-0 flex-1 py-7">
                {children}
              </main>
            </div>

            {/* One panel, rendered once. The old shell rendered two copies —
                a static aside and a conditional dialog — because a single
                element repositioned by breakpoint is wrong in one of the two
                places. That is true, and the fix is one *component* used twice,
                not one element moved: `NavPanel` is a list, and only this
                wrapper is a dialog. */}
            <Sheet
              open={open}
              onClose={close}
              side="left"
              width="max-w-[17rem]"
              title="Go to"
              description={workspaces?.find((w) => w.active)?.name}
            >
              <NavPanel all={all} onNavigate={close} />
              <div className="mt-6 border-t border-ink-100 pt-4 sm:hidden">
                <WorkspaceMenu workspaces={workspaces} />
              </div>
            </Sheet>
          </div>
        </WorkspacesContext.Provider>
      </DashboardsContext.Provider>
    </ToastProvider>
  )
}
