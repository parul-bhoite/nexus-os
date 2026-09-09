'use client'

import { useEffect, useState } from 'react'
import { fetchWorkspaces, switchWorkspace, type WorkspaceChoice } from '@/lib/settings-client'

/**
 * Moving between the companies one login holds — ADR 0026.
 *
 * ## Switching is the most dangerous action in this product
 *
 * Every figure on screen, every department in the nav and every fetch already
 * resolved belongs to the entity that was active when it was read. **Entity A's
 * numbers under entity B's name is the worst failure this product can have**,
 * and it is the one failure that would look completely normal — right-shaped
 * figures, plausible deltas, the wrong company's name above them.
 *
 * So this does not update state. It posts, and then does a **full page
 * navigation**:
 *
 *     window.location.assign('/dashboard')
 *
 * A `router.refresh()` or a client-side re-fetch would leave React state,
 * module-level state and any in-flight request from the previous entity alive
 * in the same document. A hard navigation guarantees nothing survives, which is
 * the browser's version of the `_teardown_on_switch` that was deleted with
 * `doc/11` Q9 and whose absence ADR 0026 brought back as I5.
 *
 * The cost is a reload the user sees. That is the correct price.
 *
 * ## It renders nothing for a single-entity account
 *
 * Which is almost everybody. A switcher with one option implies a second
 * company exists somewhere the person cannot see, and offering the control
 * would be a worse answer than not having it — the same reason a department
 * somebody cannot reach is absent rather than greyed out.
 */
export function EntitySwitcher() {
  const [entities, setEntities] = useState<WorkspaceChoice[] | null>(null)
  const [unreadable, setUnreadable] = useState(false)
  const [switching, setSwitching] = useState('')
  const [problem, setProblem] = useState('')
  const [announce, setAnnounce] = useState(false)

  useEffect(() => {
    // **The switch had no visible outcome.** `/dashboard` redirects an Owner
    // to `/dashboard/executive`, so switching *from* a dashboard navigated to
    // the URL the browser was already showing: same address, same layout, a
    // flash of reload, and the only changed pixels were which pill was dark.
    // It read as a control that did nothing, and it cost several minutes of
    // browser verification before I realised the switch had worked (defect
    // 42). For a screen-reader user a same-URL navigation announces nothing
    // at all, which is why the confirmation below is `role="status"`.
    //
    // Read from `window.location` rather than `useSearchParams` so this needs
    // no Suspense boundary, and the flag is a bare `1` — the company's name
    // comes from the session-backed list below, because tenant data does not
    // belong in a URL or in whatever logs it.
    if (new URLSearchParams(window.location.search).get('switched') === '1') {
      setAnnounce(true)
      // So a refresh does not re-announce a switch that happened once.
      const clean = window.location.pathname + window.location.hash
      window.history.replaceState(null, '', clean)
    }

    let live = true
    fetchWorkspaces()
      .then((page) => live && setEntities(page.workspaces))
      .catch(() => {
        if (!live) return
        // **Not silent, and this was a mistake once.** The first version set
        // `[]` here, which renders nothing — so a timeout on this one fetch
        // made the switcher vanish for somebody holding two companies, with
        // nothing on screen saying why. Found in a browser when the proxy
        // returned 503 under load.
        //
        // Still not a red box: it is a navigation control, so the fallback is a
        // route to the panel that lists the same thing and reports its own
        // errors properly.
        setEntities([])
        setUnreadable(true)
      })
    return () => {
      live = false
    }
  }, [])

  if (unreadable) {
    return (
      <p className="text-sm text-ink-400">
        Could not check which companies you hold.{' '}
        <a
          href="/settings"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2"
        >
          Settings lists them
        </a>
        .
      </p>
    )
  }

  // Nothing for a single-entity account, which is almost everybody — and
  // nothing while the list is still in flight, because a control that appears
  // late is better than one that flickers.
  if (entities === null || entities.length < 2) return null

  const active = entities.find((entity) => entity.active)

  const move = async (entity: WorkspaceChoice) => {
    if (entity.active) return
    setSwitching(entity.workspace_id)
    setProblem('')
    try {
      await switchWorkspace(entity.workspace_id)
      // Not `router.push`. See the note at the top: nothing from the previous
      // entity may survive into the next document. `?switched=1` survives the
      // hard navigation precisely because it is in the URL and not in state —
      // it is the only channel that does.
      window.location.assign('/dashboard?switched=1')
    } catch {
      setProblem('Could not switch. You are still in ' + (active?.name ?? 'this company') + '.')
      setSwitching('')
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <nav aria-label="Companies" className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
          Company
        </span>
        {entities.map((entity) => (
          <button
            key={entity.workspace_id}
            type="button"
            onClick={() => void move(entity)}
            disabled={entity.active || switching !== ''}
            aria-current={entity.active ? 'true' : undefined}
            className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
              entity.active
                ? 'bg-ink-800 text-bone-50'
                : 'border border-ink-100 text-ink-600 hover:border-ink-300 hover:text-ink-900'
            }`}
          >
            {switching === entity.workspace_id ? 'Switching…' : entity.name}
          </button>
        ))}
      </nav>

      {/* Named, not "switched successfully". The whole risk this control
          carries is reading one company's figures under another's name, so the
          confirmation has to answer *which* — and it names the entity the
          session says is active, not the one that was clicked. */}
      {announce && active ? (
        <p
          role="status"
          className="text-sm font-medium text-steel-700"
        >
          Now in {active.name}. Every figure below is theirs.
        </p>
      ) : null}

      {problem ? (
        <p role="alert" className="text-sm font-medium text-clay-600">
          {problem}
        </p>
      ) : null}
    </div>
  )
}
