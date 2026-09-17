'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import { Coverage } from '@/components/dashboard/Coverage'
import { BlockCard } from '@/components/dashboard/BlockCard'
import { CompanyBrain } from '@/components/dashboard/CompanyBrain'
import { DirectorRows } from '@/components/dashboard/DirectorRows'
import { MorningBrief } from '@/components/dashboard/MorningBrief'
import { OpenOnYourSide } from '@/components/dashboard/OpenOnYourSide'
import { useDashboards } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'
import { PageBody, PageHeader, Section } from '@/components/ui/Page'
import { BlockGridSkeleton, Bone, Loading, PageHeadSkeleton } from '@/components/ui/Skeleton'
import { Failed } from '@/components/ui/States'
import { AuthError } from '@/lib/auth-client'
import { fetchSurface, type DirectorBlock, type Surface } from '@/lib/dashboard-client'

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
 *
 * ## What the 2026-09 audit changed
 *
 * **The wait has a shape.** `/dashboards/surface` takes twelve to sixteen
 * seconds against Neon, and for all of it this page rendered two lines of plain
 * text on an empty canvas — "Reading what changed…", then "Taking longer than
 * usual". The sentences are good and they are kept; what was missing is any
 * indication of what was coming or how much of it, so the page had no layout to
 * settle into and everything arrived at once by pushing everything else down.
 * It now renders the page's own structure in skeleton, at the sizes the real
 * content will occupy.
 *
 * **A failure can be retried.** The error state was a red box containing the
 * server's sentence and nothing clickable. Retrying meant reloading a page that
 * refetches twenty-five other things.
 *
 * **The order puts the business before the product.** *Where the product is,
 * for you* — the band reporting that 66 of 89 capabilities are not built yet —
 * was the second thing on the page, above every figure. It is honest and it
 * belongs here, but it is a statement about NEXUS rather than about the
 * reader's company, and a dashboard that leads with its own roadmap has told
 * the reader what matters. It moves below the figures, still immediately above
 * the open questions for the reason the original comment gives: its "not built
 * yet" band is what makes "23 more are waiting on us" legible a moment later.
 *
 * **One h1, and one heading step below it.** The page title and every section
 * heading were the same size, so five headings competed and none named the
 * page. `PageHeader` and `Section` own that now.
 */

type State =
  | { status: 'loading' }
  | { status: 'ready'; surface: Surface }
  | { status: 'error'; message: string }

export function DashboardLanding() {
  const router = useRouter()
  const [state, setState] = useState<State>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })

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
  }, [router, attempt])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  if (state.status === 'loading') return <TodaySkeleton />

  if (state.status === 'error') {
    return (
      <Failed title="Today did not load" retry={retry} secondary={{ label: 'Your work', href: '/work' }}>
        {state.message}
      </Failed>
    )
  }

  return (
    <PageBody>
      {/* The page's one h1. It was lost when this route stopped redirecting into
          a director page — that page had `<h1>{director.title}</h1>` and the
          common surface inherited six h2s and no top-level heading, which
          leaves a screen reader with no name for where it is. "Today" rather
          than a greeting, because a greeting needs the reader's name and that
          is another request for a word. */}
      <PageHeader
        title="Today"
        // "where each number came from", not "what it was read from": not every
        // figure here was read from anywhere. A count comes from rows this
        // workspace typed (ADR 0034).
        lede="What needs you, and where each number came from."
      />

      <MorningBrief brief={state.surface.brief} />
      <Measured blocks={state.surface.measured} />
      {/* Still immediately above the questions — the "not built yet" band is
          what makes "23 more are waiting on us" legible a moment later — but
          now below the figures rather than above them. */}
      <Coverage bands={state.surface.coverage} />
      <OpenOnYourSide questions={state.surface.questions} />
      <DirectorRows rows={state.surface.directors} />
      <CompanyBrain />
      <NoDepartment />
    </PageBody>
  )
}

/**
 * The page's own shape, at the sizes it will occupy.
 *
 * Not a generic placeholder: the heading block, one wide card for the brief and
 * a two-column grid of six tiles, because that is what arrives. A skeleton that
 * does not predict the layout is a spinner drawn as rectangles — it neither
 * tells the reader what is coming nor stops the page reflowing when it does.
 */
function TodaySkeleton() {
  return (
    <Loading label="Reading what changed. The database is in another region, so this can take a few seconds.">
      <div className="flex flex-col gap-stack">
        <PageHeadSkeleton />
        <div className="flex flex-col gap-4">
          <Bone className="h-4 w-36" />
          <div className="surface flex flex-col gap-3 px-5 py-5">
            <Bone className="h-4 w-48" />
            <Bone className="h-3 w-full" />
            <Bone className="h-3 w-4/5" />
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <Bone className="h-4 w-40" />
          <BlockGridSkeleton count={6} />
        </div>
      </div>
    </Loading>
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
 *
 * `items-start` on the grid rather than the default stretch. Tiles carry very
 * different amounts — a priorities list against a single count — and stretching
 * them to a shared height left the short ones with a hundred pixels of empty
 * card below their last line. A card is as tall as what is in it.
 */
function Measured({ blocks }: { blocks: DirectorBlock[] }) {
  if (blocks.length === 0) return null

  return (
    <Section
      title="Measured today"
      // **Was "Each with its denominator, the page it was read from."** True of
      // a scored audit and of nothing else: a pipeline has no denominator (ADR
      // 0033) and a count of your own records has neither a denominator nor a
      // page anybody fetched (ADR 0034).
      lede="Each says what it counted, what it left out, and where the number came from."
    >
      <ul className="grid items-start gap-4 lg:grid-cols-2">
        {blocks.map((block) => (
          <BlockCard key={block.key} block={block} department={block.key.split('.')[0]} />
        ))}
      </ul>
    </Section>
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
    <Section title="No department dashboard for you">
      <div className="flex flex-col gap-4 rounded-data border border-ink-100 bg-white px-5 py-5">
        <p className="max-w-read text-body leading-relaxed text-ink-700">
          Each director&rsquo;s page belongs to a department, and your account is not in
          one. That is the normal state for a viewer — you can see company-wide material
          and nothing that belongs to a single department.
        </p>
        <p className="max-w-read text-body leading-relaxed text-ink-500">
          If you expected a dashboard, an owner sets which department an account is in
          when they invite it.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button href="/account" size="sm">
            Your account
          </Button>
          <Button href="/onboarding" size="sm" variant="ghost">
            Workspace setup
          </Button>
        </div>
      </div>
    </Section>
  )
}
