'use client'

import { useCallback, useEffect, useState } from 'react'
import { AuditLogCard } from '@/components/settings/AuditLogCard'
import { DepartmentBlockCard } from '@/components/settings/DepartmentBlockCard'
import { BrainCard } from '@/components/settings/BrainCard'
import { PreferencesCard } from '@/components/settings/PreferencesCard'
import { DepartmentsCard } from '@/components/settings/DepartmentsCard'
import { EntitiesCard } from '@/components/settings/EntitiesCard'
import { DomainVerificationCard } from '@/components/settings/DomainVerificationCard'
import { InvitePeople } from '@/components/settings/InvitePeople'
import { ReportingCard } from '@/components/settings/ReportingCard'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchState, type SpineState } from '@/lib/onboarding-client'
import { fetchCompany, type CurrentCompany } from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * Settings: the domain, and the people.
 *
 * Finding F3. `/register-company` said twice that proving the domain "happens
 * in Settings"; the invitation refusal said "Settings has the DNS record to
 * add"; and there was no `/settings` route, no import of the verification card
 * that had already been written, and no screen anywhere that sent an
 * invitation. The gate was real and correctly enforced server-side, which is
 * what made the missing screen expensive rather than cosmetic: the entire
 * multi-user half of the product was unreachable from a browser.
 *
 * Two fetches rather than one. The company answers what the domain is and
 * whether it is proved; the onboarding state answers which departments this
 * company runs, which is the list the invite form assigns from. Neither is
 * derivable from the other, and inventing a combined endpoint for one screen
 * would put a view's shape into the API.
 */

type State =
  | { status: 'loading' }
  | { status: 'ready'; company: CurrentCompany; spine: SpineState | null }
  | { status: 'error'; message: string; code: number }

export function SettingsPanel() {
  const [state, setState] = useState<State>({ status: 'loading' })

  const load = useCallback(async () => {
    const company = await fetchCompany()
    // The department list is a nicety on this screen, not its subject. If it
    // will not load, the domain card and the invite form are still the whole
    // point of being here, so this failure is absorbed rather than raised.
    const spine = await fetchState().catch(() => null)
    return { company, spine }
  }, [])

  useEffect(() => {
    let live = true
    load()
      .then(({ company, spine }) => live && setState({ status: 'ready', company, spine }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError
              ? caught.message
              : 'Could not reach the account service. Is the API running?',
          code: caught instanceof AuthError ? caught.status : 0,
        })
      })
    return () => {
      live = false
    }
  }, [load])

  // **Only four things on this screen need the two fetches above**: the
  // company's identity line, the domain card, the invite form, and the
  // per-department blocks (which need the spine's department list). The other
  // six panels take no props and read their own endpoints.
  //
  // So gating the whole screen on `fetchCompany` made six independent requests
  // wait for a seventh they do not depend on — one serial round trip to
  // `us-east-2` in front of everything. Found in a browser: a full-page
  // "Loading your settings…", and then, once it cleared, six panels each
  // starting to load. The panels below now mount immediately and fetch in
  // parallel with the company, which is a latency fix and not only a
  // perceptual one.
  //
  // Some failures are still a takeover, because then *nothing* here can load
  // and one sentence with a link beats seven red boxes (finding F7).
  //
  // **The first version of this only took over on 401/403, and a browser
  // immediately showed why that was wrong.** With the API not running,
  // `fetchCompany` fails on transport rather than authorization — `code` is 0,
  // not 401 — so the screen rendered the scoped company error *and* six panels
  // that each then failed on the same dead origin: seven boxes saying the same
  // thing, where the old full-screen gate had said it once.
  //
  // The real question is not "is this person signed out" but **"can anything on
  // this screen load"**, and there are two ways the answer is no:
  //
  //   401 / 403 — not signed in, or not in a company yet. Every panel refuses.
  //   0         — the fetch itself never completed.
  //   503       — **the BFF's own "could not reach the API"**, not the API's.
  //               `auth-proxy.ts` returns it when the upstream call fails, and
  //               every panel on this screen proxies through that same BFF to
  //               that same API. This is the one the browser actually showed
  //               me: with the API stopped, the first fix (0/401/403) still
  //               rendered seven identical boxes, because the code was 503.
  //
  // Anything else is specific to `/companies/current` (a 404, a 500 on that one
  // endpoint) and *is* scoped, because the other six read different endpoints
  // and may genuinely be fine.
  //
  // The cost, stated because it is a real trade: one endpoint timing out under
  // load 503s alone and now takes the screen with it. That was also the old
  // behaviour — the whole screen was gated on this fetch — so it is not a
  // regression, and it is the better of the two failures.
  //
  // A second cost, measured in a browser: because the panels mount on the
  // first render, a signed-out visit fires eight requests and discards six of
  // them as 401s before this takeover replaces them. That is the price of the
  // parallelism, and it is worth paying — it buys a round trip on every
  // signed-in visit, which is the path that happens, in exchange for six cheap
  // refusals on a path that normally redirects before it gets here.
  const signedOut = state.status === 'error' && (state.code === 401 || state.code === 403)
  const unreachable = state.status === 'error' && (state.code === 0 || state.code === 503)
  if (signedOut || unreachable) {
    return (
      <div className="flex max-w-prose flex-col gap-5">
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {signedOut
            ? 'You need to be signed in, in a company, to open settings.'
            : state.status === 'error'
              ? state.message
              : ''}
        </div>
        <div className="flex flex-wrap gap-3">
          <Button href={signedOut ? '/login?next=/settings' : '/account'}>
            {signedOut ? 'Sign in' : 'Your account'}
          </Button>
        </div>
      </div>
    )
  }

  const company = state.status === 'ready' ? state.company : null
  const running =
    state.status === 'ready'
      ? (state.spine?.departments ?? [])
          .filter((d) => d.selected)
          .map((d) => ({ value: d.value, label: d.label ?? d.value }))
      : []

  // The company half failed for a reason that is not "signed out" — the
  // service is down, or the company read itself broke. Scoped to the region
  // that needed it, because the six panels below may well be fine, and
  // replacing the screen would hide six working panels behind one failure.
  const companyRegion =
    state.status === 'error' ? (
      <div className="flex max-w-prose flex-col gap-4">
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message} The domain check and the invite form need it; everything
          below reads its own settings and may still be fine.
        </div>
        <div className="flex flex-wrap gap-3">
          <Button href="/account">Your account</Button>
        </div>
      </div>
    ) : company === null ? (
      <Waiting>Loading your company…</Waiting>
    ) : (
      <>
        <dl className="overflow-hidden rounded-2xl border border-ink-100 bg-white px-5 py-4">
          <dt className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">Company</dt>
          <dd className="mt-1 text-ink-900">
            {company.name}{' '}
            <span className="text-ink-500">
              — {company.domain}
              {company.domain_verified ? ' · verified' : ' · not yet verified'}
            </span>
          </dd>
        </dl>

        <DomainVerificationCard
          domain={company.domain}
          verified={company.domain_verified}
          mayAdminister={company.may_administer}
          // Re-read rather than assumed. The card knows its own check passed;
          // the fact that unlocks the invite form is the workspace's, and the
          // workspace is what the API will consult when the invitation is sent.
          onVerified={() => {
            void load()
              .then(({ company: fresh, spine: freshSpine }) =>
                setState({ status: 'ready', company: fresh, spine: freshSpine }),
              )
              .catch(() => undefined)
          }}
        />

        <InvitePeople
          verified={company.domain_verified}
          mayAdminister={company.may_administer}
          departments={running}
        />
      </>
    )

  return (
    <div className="flex flex-col gap-8">
      {/* Panel 4b, first — and now first in fact rather than second. It names
          which company every panel below it is about, so it is the one panel
          that should never be behind a spinner: somebody who does not know
          which entity is active is reading eight panels about a company they
          have not identified. It takes no props, so it no longer waits. */}
      <EntitiesCard />

      {companyRegion}

      {/*
        Reading its own settings rather than taking them from the two fetches
        above. It is the only panel here that everybody in the workspace may
        read — the domain card and the invite form are administrator surfaces —
        so binding it to `company.may_administer` for *visibility* would hide
        the assumptions a Contributor's own tiles are cited against. It asks the
        API, which answers with `may_administer` for the write half only.
      */}
      {/* Panel 2: the one panel that is entirely this person's, and the only
          one that needs no owner — nothing in it can widen what anybody sees. */}
      <PreferencesCard />

      {/* Panel 3, one per department this company runs. The block is served
          with `may_answer` and `binds` on it, so a Contributor gets a
          read-only view of the thresholds their own figures are measured
          against rather than nothing at all. */}
      {running.map((department) => (
        <DepartmentBlockCard
          key={department.value}
          department={department.value}
          label={department.label}
        />
      ))}

      <ReportingCard />

      {/* Panel 7. The gap it closes: department selection happened once during
          onboarding and never again, and the only writer was a route that
          advances the spine. */}
      <DepartmentsCard />

      {/* Panel 10. Read-only: deleting an item has to fan out to its
          passages, embeddings and derivations, and that is P21's. */}
      <BrainCard />

      {/* Panel 12, last because it is a record of everything above it. It
          renders nothing at all for a caller the API refuses — a red box
          telling somebody they may not read something they never asked for is
          worse than the panel not being there. */}
      <AuditLogCard />
    </div>
  )
}
