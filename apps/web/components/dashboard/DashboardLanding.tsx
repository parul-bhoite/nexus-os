'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Coverage } from '@/components/dashboard/Coverage'
import { BlockCard } from '@/components/dashboard/BlockCard'
import { CompanyBrain } from '@/components/dashboard/CompanyBrain'
import { DirectorRows } from '@/components/dashboard/DirectorRows'
import { MorningBrief } from '@/components/dashboard/MorningBrief'
import { OpenOnYourSide } from '@/components/dashboard/OpenOnYourSide'
import { useDashboards } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchSurface, type DirectorBlock, type Surface } from '@/lib/dashboard-client'
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
      {/* The page's one h1. It was lost when this route stopped redirecting into
          a director page — that page had `<h1>{director.title}</h1>` and the
          common surface inherited six h2s and no top-level heading, which
          leaves a screen reader with no name for where it is. "Today" rather
          than a greeting, because a greeting needs the reader's name and that
          is another request for a word. */}
      <header>
        <h1 className="font-display text-title font-medium text-ink-900">Today</h1>
        <p className="mt-1 text-sm text-ink-500">
          {/* "where each number came from", not "what it was read from": not every
              figure here was read from anywhere. A count comes from rows this
              workspace typed (ADR 0034). */}
          What needs you, and where each number came from.
        </p>
      </header>

      <MorningBrief brief={state.surface.brief} />
      {/* Coverage before the questions, deliberately: its "not built yet" band
          is what makes "28 more are waiting on us" legible a moment later. The
          reverse order reads as a list of chores with the reason arriving too
          late. */}
      <Coverage bands={state.surface.coverage} />
      <Measured blocks={state.surface.measured} />
      <OpenOnYourSide questions={state.surface.questions} />
      <DirectorRows rows={state.surface.directors} />
      <CompanyBrain />
      <NoDepartment />
    </div>
  )
}

/**
 * The tiles that carry a figure, on the common surface.
 *
 * `BlockCard` unchanged — same component, same props, same narration button as
 * the director page. `doc/14` step 7 moves where a number is read and not what
 * it says, and reusing the component rather than writing a compact variant is
 * most of how that stays true.
 *
 * The department passed to each card is the capability's own namespace, because
 * that is where its narration POST has to go: the API refuses a capability id
 * that does not belong to the department in the path.
 */
function Measured({ blocks }: { blocks: DirectorBlock[] }) {
  if (blocks.length === 0) return null

  return (
    <section aria-labelledby="measured-heading">
      <h2 id="measured-heading" className="font-display text-title font-medium text-ink-900">
        Measured today
      </h2>
      <p className="mt-1 max-w-prose text-sm text-ink-500">
        {/* **Was "Each with its denominator, the page it was read from."** True of a
            scored audit and of nothing else: a pipeline has no denominator (ADR
            0033) and a count of your own records has neither a denominator nor a
            page anybody fetched (ADR 0034). A standfirst promising provenance the
            tiles beneath it do not carry is the exact failure the tiles are
            careful about, arriving one line above them. */}
        Each says what it counted, what it left out, and where the number came from.
      </p>
      <ul className="mt-4 grid gap-4 lg:grid-cols-2">
        {blocks.map((block) => (
          <BlockCard
            key={block.key}
            block={block}
            department={block.key.split('.')[0]}
          />
        ))}
      </ul>
    </section>
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
