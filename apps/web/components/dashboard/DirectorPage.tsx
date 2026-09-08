'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { OfferingTile } from '@/components/dashboard/OfferingTile'
import { Logo } from '@/components/ui/Logo'
import { AuthError } from '@/lib/auth-client'
import {
  fetchDashboards,
  fetchDirector,
  type Dashboards,
  type Director,
} from '@/lib/dashboard-client'
import { departmentLabel } from '@/lib/onboarding-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * One director's page, inside the global shell doc 05 §1 specifies.
 *
 * The shell is deliberately partial and says which parts are missing. Doc 05 §1
 * lists a score, a data ribbon, an action queue, a period selector and an
 * "Ask this Director" chat; none of those have anything behind them yet, and
 * rendering an empty period selector or a score of `0` would break I10 on the
 * very page built to demonstrate it. What is here is the header, the director
 * switcher, and the offering list with each tile's real state.
 *
 * The switcher shows only the directors this caller may open — the API returns
 * no others, so a department the caller cannot reach is not merely hidden from
 * the nav, it is absent from the response.
 */

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string; code: number }
  | { status: 'ready'; director: Director; all: Dashboards }

export function DirectorPage({ department }: { department: string }) {
  const router = useRouter()
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })

    Promise.all([fetchDirector(department), fetchDashboards()])
      .then(([director, all]) => {
        if (live) setState({ status: 'ready', director, all })
      })
      .catch((caught: unknown) => {
        if (!live) return
        // Finding F7, the same as `DashboardLanding`: 401 is somebody whose
        // session ended, and the only useful thing to do with them is send them
        // to sign in — with the page they wanted, so they come back to it.
        // 404 is a different answer entirely and is rendered, not redirected.
        if (caught instanceof AuthError && (caught.status === 401 || caught.status === 403)) {
          router.replace(`/login?next=/dashboard/${encodeURIComponent(department)}`)
          return
        }
        setState({
          status: 'error',
          message:
            caught instanceof AuthError
              ? caught.message
              : 'Could not reach the dashboard service. Is the API running?',
          code: caught instanceof AuthError ? caught.status : 0,
        })
      })

    return () => {
      live = false
    }
  }, [department, router])

  return (
    <main className="min-h-screen bg-bone-50">
      <div className="mx-auto max-w-6xl px-6 py-8 sm:px-10">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-ink-100 pb-6">
          <Link
            href="/"
            className="inline-flex rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-500"
            aria-label="NEXUS OS home"
          >
            <Logo />
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href="/onboarding"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Workspace setup
            </Link>
            <Link
              href="/settings"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Settings
            </Link>
            <Link
              href="/account"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Account
            </Link>
          </div>
        </header>

        <div className="py-10">
          {state.status === 'loading' ? (
            <Waiting>Loading this dashboard…</Waiting>
          ) : state.status === 'error' ? (
            <Unavailable message={state.message} code={state.code} />
          ) : (
            <Ready director={state.director} all={state.all} />
          )}
        </div>
      </div>
    </main>
  )
}

function Ready({ director, all }: { director: Director; all: Dashboards }) {
  const planned = director.offerings.filter((o) => o.state === 'planned').length
  const unanswered = all.directors.find((d) => d.department === director.department)
    ?.unanswered_questions

  return (
    <>
      <nav aria-label="Directors" className="flex flex-wrap gap-2">
        {all.directors.map((entry) => (
          <Link
            key={entry.department}
            href={entry.path}
            aria-current={entry.department === director.department ? 'page' : undefined}
            className={`rounded-full px-3.5 py-1.5 font-mono text-2xs uppercase tracking-[0.1em] transition-colors ${
              entry.department === director.department
                ? 'bg-ink-800 text-bone-50'
                : 'border border-ink-100 text-ink-500 hover:border-ink-300 hover:text-ink-800'
            }`}
          >
            {/* Served, not derived. This special-cased `hr` into "People" and
                left every other department as its raw key — the third of the
                three spellings finding F13 counted. */}
            {entry.label ?? departmentLabel(entry.department)}
          </Link>
        ))}
      </nav>

      <header className="mt-8">
        <h1 className="font-display text-title font-medium text-ink-900">{director.title}</h1>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          {director.remit}
        </p>
      </header>

      {/* Q27. The deferral, made concrete on the director it holds back.
          A dashboard that cannot compute anything yet should say what would
          turn it on — and the answer is specific and reachable, not "connect
          some data". `unanswered` is `undefined` against an older API, which is
          why the check is a comparison and not a truthiness test: zero must
          only ever mean zero. */}
      {typeof unanswered === 'number' && unanswered > 0 ? (
        <div className="mt-6 rounded-2xl border border-steel-300 bg-steel-100 px-5 py-5">
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-steel-700">
            What turns this on
          </p>
          <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-800">
            <strong>{unanswered}</strong> question{unanswered === 1 ? '' : 's'} about how this
            department works {unanswered === 1 ? 'is' : 'are'} still unanswered, which is why
            this department is thinner than the others.
          </p>
          {/* The button here pointed at `/onboarding/[department]`, a per-department
              questionnaire that has been removed. The count stays because it is true
              and it explains the gap — but it no longer offers a route, because there
              is not one. Answering these needs a way back into the conversation, and
              that does not exist yet. */}
        </div>
      ) : null}

      {/* Doc 05 §1's shell is not built. Saying which parts are missing is the
          honest version of a header strip with an empty score in it. */}
      <div className="mt-6 rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
          A placeholder, and what it is missing
        </p>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-800">
          Every offering below is real — the name, what it will show and what it needs
          all come from the department specification. <strong>None of them is built</strong>:{' '}
          {planned} of {director.offerings.length} say so plainly rather than showing an
          outline you could mistake for a working widget.
        </p>
        <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
          {director.scoreable
            ? 'The department score, data ribbon and period selector belong at the top of this page. They are absent rather than empty — a score of zero would be a statement about your business instead of about the data.'
            : 'This director is a synthesis layer and is never scored. That is why the company health score is out of six departments, not seven.'}
        </p>
      </div>

      <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {director.offerings.map((offering) => (
          <OfferingTile key={offering.id} offering={offering} />
        ))}
      </ul>
    </>
  )
}

function Unavailable({ message, code }: { message: string; code: number }) {
  // 404 is what a department the caller does not hold returns, and it says
  // nothing further on purpose — "this exists and you may not have it" is an
  // existence disclosure about how the company is organised.
  const notFound = code === 404

  return (
    <div className="max-w-prose">
      <h1 className="font-display text-title font-medium text-ink-900">
        {notFound ? 'Not found' : 'That did not load'}
      </h1>
      <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-600">
        {notFound
          ? 'There is no dashboard here for you. If you expected one, ask an owner which department your account is in.'
          : message}
      </p>
      <p className="mt-4 text-sm">
        <Link
          href="/dashboard"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Go to your own dashboard
        </Link>
      </p>
    </div>
  )
}
