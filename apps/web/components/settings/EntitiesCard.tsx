'use client'

import { useEffect, useState } from 'react'
import { AuthError } from '@/lib/auth-client'
import { fetchWorkspaces, switchWorkspace, type WorkspaceChoice } from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * The companies this login holds — panel 4b (`doc/13` §14, ADR 0026).
 *
 * **The panel that explains every other panel.** Everything below it on the
 * settings screen — the domain, the departments, the reporting assumptions, the
 * Brain, the log — belongs to the *active* entity and to no other. Somebody who
 * does not know which one is active is reading eight panels about a company
 * they have not identified.
 *
 * ## Two things it says that the switcher in the shell does not
 *
 * **Which role you hold where.** The list is exactly this person's memberships,
 * and the role can differ per entity: an Owner at one company and a Sales
 * manager at another is the ordinary case for a group finance director. Being
 * an Owner of one grants nothing at the next.
 *
 * **What a group view would cover.** There is no group screen yet — it needs a
 * per-entity figure to roll up and none is computable — so the honest thing is
 * to say what it *would* be built from rather than to link to nothing.
 *
 * ## It renders for a single-entity account too
 *
 * Unlike the shell's switcher. Here the panel is answering *"which company are
 * these settings about?"*, and that question has an answer whether or not there
 * is a second one — where in the shell a lone switcher would imply a company
 * the person cannot see.
 */
type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; entities: WorkspaceChoice[] }

function role(value: string): string {
  return value.replace(/_/g, ' ')
}

export function EntitiesCard() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [switching, setSwitching] = useState('')
  const [problem, setProblem] = useState('')
  const [announce, setAnnounce] = useState(false)

  useEffect(() => {
    // Same reason as the shell's switcher: this navigates to `/settings`, the
    // URL it is already on, so a successful switch changed almost nothing on
    // screen and announced nothing to a screen reader. The flag is a bare `1`
    // and the name comes from the session-backed list, not the URL.
    if (new URLSearchParams(window.location.search).get('switched') === '1') {
      setAnnounce(true)
      window.history.replaceState(null, '', window.location.pathname + window.location.hash)
    }

    let live = true
    fetchWorkspaces()
      .then((page) => live && setState({ status: 'ready', entities: page.workspaces }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError ? caught.message : 'Could not read your companies.',
        })
      })
    return () => {
      live = false
    }
  }, [])

  if (state.status === 'loading') return <Waiting>Loading your companies…</Waiting>

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

  const { entities } = state
  const active = entities.find((entity) => entity.active)

  const move = async (entity: WorkspaceChoice) => {
    setSwitching(entity.workspace_id)
    setProblem('')
    try {
      await switchWorkspace(entity.workspace_id)
      // A full navigation, not a state update. Every panel on this screen was
      // read under the previous entity, and leaving any of them mounted would
      // show one company's settings under another's name.
      window.location.assign('/settings?switched=1')
    } catch (caught: unknown) {
      setProblem(
        caught instanceof AuthError
          ? caught.message
          : 'Could not switch. You are still in ' + (active?.name ?? 'this company') + '.',
      )
      setSwitching('')
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <header>
        <h2 className="font-display text-lg text-ink-900">
          {entities.length > 1 ? 'Your companies' : 'Your company'}
        </h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          {entities.length > 1 ? (
            <>
              Everything else on this screen belongs to the one marked active — the
              domain, the departments, the reporting assumptions and the log are all{' '}
              <strong>{active?.name ?? 'that company'}</strong>&rsquo;s.
            </>
          ) : (
            <>Everything on this screen belongs to it.</>
          )}
        </p>
      </header>

      <ul className="flex flex-col gap-2">
        {entities.map((entity) => (
          <li
            key={entity.workspace_id}
            className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 ${
              entity.active ? 'border-steel-300 bg-steel-100' : 'border-ink-100 bg-white'
            }`}
          >
            <span>
              <span className="font-medium text-ink-900">{entity.name}</span>
              <span className="mt-0.5 block text-sm text-ink-500">
                {/* Per entity, and it can differ. Being an Owner of one company
                    grants nothing at the next. */}
                You are {role(entity.role)} here
                {entity.active ? ' · active' : ''}
              </span>
            </span>

            {entity.active ? null : (
              <button
                type="button"
                onClick={() => void move(entity)}
                disabled={switching !== ''}
                className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm font-medium text-ink-700 hover:border-ink-300 hover:text-ink-900"
              >
                {switching === entity.workspace_id ? 'Switching…' : 'Switch to this'}
              </button>
            )}
          </li>
        ))}
      </ul>

      {announce && active ? (
        <p role="status" className="text-sm font-medium text-steel-700">
          Now in {active.name}. Every panel on this screen is theirs.
        </p>
      ) : null}

      {problem ? (
        <p role="alert" className="text-sm font-medium text-clay-600">
          {problem}
        </p>
      ) : null}

      {entities.length > 1 ? (
        <p className="border-t border-ink-100 pt-3 text-sm text-ink-400">
          A group view across all {entities.length} is not built yet. It needs a figure
          each of them can compute before there is anything to roll up — and when it
          arrives it will state how many entities it covers, not average away the ones
          it could not read.
        </p>
      ) : (
        <p className="border-t border-ink-100 pt-3 text-sm text-ink-400">
          One login can hold several companies, each with its own Brain, tools and
          dashboards. An invitation names one of them — holding a second is not
          something a role grants.
        </p>
      )}
    </section>
  )
}
