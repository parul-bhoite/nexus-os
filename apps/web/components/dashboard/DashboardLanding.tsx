'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { MorningBrief } from '@/components/dashboard/MorningBrief'
import { useDashboards } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchSurface, type Surface } from '@/lib/dashboard-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * Today — the common surface, and where signing in now lands.
 *
 * **This used to be a redirect.** It read the caller's membership and forwarded
 * them to their own director page, because a department page was the only thing
 * there was to land on. `doc/14` makes the surface common: a founder does not
 * think in departments, and being bounced into one before the product says
 * anything is the tab rail's problem wearing a different hat. The left panel
 * still reaches every director.
 *
 * The one case that survives unchanged is somebody in **no** department. Doc 06
 * §2.3 gives a Viewer company-wide material and no L3 at all, so there is no
 * director to send them to and inventing one would mean putting them in a
 * department nobody assigned. They get the brief — which is scope-composed and
 * will simply be thin — and the explanation below it.
 */

type State =
  | { status: 'loading' }
  | { status: 'ready'; surface: Surface }
  | { status: 'error'; message: string }

export function DashboardLanding() {
  const router = useRouter()
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    fetchSurface()
      .then((surface) => {
        if (live) setState({ status: 'ready', surface })
      })
      .catch((caught: unknown) => {
        if (!live) return
        // Finding F7. A signed-out visitor used to get the API's own
        // `"Not authenticated"` rendered verbatim in a box with nothing
        // clickable in it. The refusal was right; leaving somebody on a dead
        // page was not, and session expiry is the ordinary way into this state.
        if (caught instanceof AuthError && (caught.status === 401 || caught.status === 403)) {
          router.replace('/login?next=/dashboard')
          return
        }
        setState({
          status: 'error',
          message:
            caught instanceof AuthError
              ? caught.message
              : 'Could not reach the dashboard service. Is the API running?',
        })
      })
    return () => {
      live = false
    }
  }, [router])

  if (state.status === 'loading') {
    return <Waiting>Reading what changed…</Waiting>
  }

  if (state.status === 'error') {
    return (
      <div
        role="alert"
        className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
      >
        {state.message}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-10">
      <MorningBrief brief={state.surface.brief} />
      <NoDepartment />
    </div>
  )
}

/**
 * Shown only to somebody in no department at all.
 *
 * A Viewer is the ordinary case and not an error: doc 06 §2.3 gives them
 * company-wide material and no L3. Drawn under the brief rather than instead of
 * it, because the brief is scope-composed and has already told them the truth
 * about what can be seen — this explains *why* it is thin.
 */
function NoDepartment() {
  const all = useDashboards()
  // `null` is still loading, and rendering "you hold no department" during a
  // fetch would state an absence nobody has established yet (I10).
  if (all === null || all.directors.length > 0) return null

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
          No department dashboard for you
        </p>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-800">
          Each director&rsquo;s page belongs to a department, and your account is not in
          one. That is the normal state for a viewer — you can see company-wide material
          and nothing that belongs to a single department.
        </p>
        <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
          If you expected a dashboard, an owner sets which department an account is in
          when they invite it.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button href="/account" size="lg">
          Your account
        </Button>
        <Link
          href="/onboarding"
          className="self-center text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Workspace setup
        </Link>
      </div>
    </div>
  )
}
