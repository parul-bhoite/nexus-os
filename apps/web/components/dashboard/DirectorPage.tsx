'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { AssistantPanel } from '@/components/dashboard/AssistantPanel'
import { BlockCard } from '@/components/dashboard/BlockCard'
// Still used by `ChooseEntity` below — that is the chooser itself, not the
// header control the shell now owns.
import { EntitySwitcher } from '@/components/dashboard/EntitySwitcher'
import { OfferingTile } from '@/components/dashboard/OfferingTile'
import { SectionRail } from '@/components/dashboard/SectionRail'
import { SetupSection } from '@/components/dashboard/SetupSection'
import { useDashboards } from '@/components/shell/AppShell'
import { AuthError } from '@/lib/auth-client'
import { fetchDirector, type Dashboards, type Director } from '@/lib/dashboard-client'
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
 * **The department tab rail is gone** (`doc/14` step 1). It sat here and gated
 * the surface, so a founder had to pick a department before the product would
 * say anything — and a founder does not think in departments, they think about
 * what needs them today. Navigating between directors is the shell's left
 * panel now, and it still lists only what the caller may open, because the API
 * returns no others.
 *
 * The chrome this file used to draw — logo, header links, entity switcher —
 * belongs to `AppShell`, and `all` arrives through its context rather than
 * from a second fetch of the same endpoint (finding #23).
 */

type State =
  | { status: 'loading' }
  | { status: 'choose' }
  | { status: 'error'; message: string; code: number }
  | { status: 'ready'; director: Director }

export function DirectorPage({ department }: { department: string }) {
  const router = useRouter()
  const all = useDashboards()
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })

    fetchDirector(department)
      .then((director) => {
        if (live) setState({ status: 'ready', director })
      })
      .catch((caught: unknown) => {
        if (!live) return
        // Finding F7, the same as `DashboardLanding`: 401 is somebody whose
        // session ended, and the only useful thing to do with them is send them
        // to sign in — with the page they wanted, so they come back to it.
        // 404 is a different answer entirely and is rendered, not redirected.
        // ADR 0026. "No workspace selected" is not a dead session — it is
        // somebody holding several companies with no active one, and sending
        // them to sign in is a loop: they authenticate, land here, and bounce
        // again. They need the chooser, which is what `EntitySwitcher` is.
        if (caught instanceof AuthError && /workspace selected/i.test(caught.message)) {
          setState({ status: 'choose' })
          return
        }

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

  return state.status === 'loading' ? (
    <Waiting>Loading this dashboard…</Waiting>
  ) : state.status === 'choose' ? (
    <ChooseEntity />
  ) : state.status === 'error' ? (
    <Unavailable message={state.message} code={state.code} />
  ) : (
    <Ready director={state.director} all={all} />
  )
}

function Ready({ director, all }: { director: Director; all: Dashboards | null }) {
  const sections = director.sections ?? []
  // How many capabilities here carry a real computed figure. Used only for the
  // score copy below, which said "no source can be measured yet" for a year and
  // became false the moment the first tile computed one.
  const measured = sections.flatMap((section) => section.blocks).filter((b) => b.figure).length
  const catalogue = director.catalogue ?? []
  // `all` is null while the shell's single fetch is still in flight. Left
  // `undefined` in that case rather than defaulted to 0: the count drives copy
  // that says how much is still unanswered, and a zero standing in for
  // "not known yet" is exactly the substitution I10 forbids.
  const unanswered = all?.directors.find((d) => d.department === director.department)
    ?.unanswered_questions

  // The first tab, which is Overview for every department except the Executive
  // — and the API serves them in order, so "first" is the specification rather
  // than a guess made here.
  // Opens on the first tab with something on it, not on the first tab.
  // On a day-one dashboard that is Setup — and leading with Overview would
  // greet a new customer with five tiles that all say "not built yet" while the
  // one tab with content sits two along. `available` is served, so the browser
  // is reading a count rather than deciding what counts as content.
  const opensOn = sections.find((section) => (section.available ?? 0) > 0) ?? sections[0]
  const [active, setActive] = useState(opensOn?.key ?? '')

  // A `.find` over at most seven sections, computed each render rather than
  // memoised. The memo that was here depended on `sections`, which is a fresh
  // array every render because of the `?? []` above — so it recomputed every
  // time anyway while making the dependency list wrong. `next lint` caught it.
  const current = sections.find((section) => section.key === active) ?? opensOn

  return (
    <>
      {/* The entity switcher and the department rail that used to open this
          page are both the shell's now. The rail in particular was navigation
          that gated a surface, and `doc/14` step 1 removes it: the left panel
          lists the same departments, from the same scoped response, without
          standing between a founder and what they came to read. */}
      <header>
        <h1 className="font-display text-title font-medium text-ink-900">{director.title}</h1>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          {director.remit}
        </p>
      </header>

      {/* Q27. The deferral, made concrete on the director it holds back.
          `unanswered` is `undefined` against an older API, which is why the
          check is a comparison and not a truthiness test: zero must only ever
          mean zero. */}
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
        </div>
      ) : null}

      {/* The score's place, and it is absent rather than empty. A zero would be
          a statement about the business instead of about the data (I10), and a
          synthesis layer is never scored at all — which is why the composite is
          out of six departments and not seven. */}
      <div className="mt-6 rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
        <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
          {!director.scoreable ? 'Never scored' : measured === 0 ? 'Not scored yet' : 'No composite yet'}
        </p>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-800">
          {!director.scoreable ? (
            'This director is a synthesis layer: it reads the others and is never scored. That is why the company health score is out of six departments, not seven.'
          ) : measured === 0 ? (
            'No source behind this department can be measured yet, so there is no score. It is absent rather than zero — a zero would be a verdict on your business rather than a statement about our data.'
          ) : (
            /* **This branch exists because the sentence above became false.**
               It claimed nothing here could be measured, which was true until
               the first tile computed a figure — and a header contradicting
               the tiles beneath it is worse than either statement alone.

               What is still absent is the *composite*, and the reason is not
               that we cannot measure: it is that averaging the two capabilities
               we can measure would score the part of the department we can see
               and label it the whole. That is the same reasoning as the company
               score being out of six departments rather than seven. */
            <>
              <strong>{measured}</strong> of this department&rsquo;s capabilities
              {measured === 1 ? ' is' : ' are'} measured, each with its own figure below. There
              is still no department score: a composite of the {measured} we can see would
              score that much and be read as the whole, which is the same reason the company
              score is out of six departments rather than seven.
            </>
          )}
        </p>
      </div>

      {sections.length > 0 ? (
        <div className="mt-8">
          <SectionRail sections={sections} active={current?.key ?? ''} onSelect={setActive} />

          {current?.key === 'setup' || current?.key === 'watchlist' ? (
            /* The two tabs that are ours, and the only two whose content is
               fetched separately. Finding #23 is that the dashboard already
               spends 25 to 30 round trips; most visits never open these. */
            <div className="mt-6">
              <SetupSection
                department={director.department}
                tab={current.key}
                notAsked={director.not_asked ?? []}
              />
            </div>
          ) : current ? (
            <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {current.blocks.map((block) => (
                <BlockCard key={block.key} block={block} department={director.department} />
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        /* An older API, or a director whose every section is still empty. The
           flat list is the fallback rather than a blank page — and it goes when
           nothing serves `offerings` any more. */
        <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(director.offerings ?? []).map((offering) => (
            <OfferingTile key={offering.id} offering={offering} />
          ))}
        </ul>
      )}

      {catalogue.length > 0 ? (
        <section className="mt-12 border-t border-ink-100 pt-8">
          <h2 className="font-display text-lg text-ink-900">
            Also in this director&rsquo;s remit
          </h2>
          <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
            {catalogue.length} more {catalogue.length === 1 ? 'capability' : 'capabilities'} the
            specification describes and these screens do not draw yet. They are listed rather
            than hidden, and they are <strong>not</strong> waiting on anything you could
            connect — most are generation features, blocked by build order rather than by data.
          </p>
          <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {catalogue.map((block) => (
              <BlockCard key={block.key} block={block} department={director.department} />
            ))}
          </ul>
        </section>
      ) : null}

      {director.assistant ? <AssistantPanel assistant={director.assistant} /> : null}
    </>
  )
}

function ChooseEntity() {
  /* Two or more companies and none active — a first sign-in for somebody who
     holds several, since login only resumes a pointer it can see. Picking one
     for them risks acting in the wrong client's workspace, so they pick. */
  return (
    <div className="max-w-prose">
      <h1 className="font-display text-title font-medium text-ink-900">
        Which company?
      </h1>
      <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-600">
        You hold more than one, and nothing here is shared between them. Choosing is
        yours rather than ours — a dashboard opened in the wrong client&rsquo;s workspace
        is worse than one that asked.
      </p>
      <div className="mt-6">
        <EntitySwitcher />
      </div>
    </div>
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
