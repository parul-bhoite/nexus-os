'use client'

import { useEffect, useState } from 'react'
import { AuthError } from '@/lib/auth-client'
import { fetchAuditLog, type AuditEntry } from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * The workspace's own trail — panel 12 (`doc/13` §14).
 *
 * **Refusals are recorded as well as successes**, which is the whole reason to
 * show it: a log that records only what worked cannot tell you that somebody
 * probed. The prototype says exactly this under its own audit table, and it is
 * the sentence a founder needs to read to understand what the log is for.
 *
 * Two things this panel does not do, deliberately:
 *
 * **It does not resolve the actor to a name.** The API returns a user id, and
 * turning that into an email means a join this endpoint does not do. A UUID is
 * useless to a human, so that is a real gap and it is named on screen rather
 * than papered over with "a user".
 *
 * **It does not offer a filter or a search box.** The API takes a limit with a
 * ceiling and no cursor — paging arrives when something needs it, and an offset
 * would be wrong anyway because rows are inserted while a reader pages. A
 * filter over the most recent fifty would look like a filter over the log.
 */

function when(iso: string): string {
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString()
}

/** `departments_changed` reads better as "departments changed". */
function readable(action: string): string {
  return action.replace(/_/g, ' ')
}

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string; code: number }
  | { status: 'ready'; entries: AuditEntry[] }

export function AuditLogCard() {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    fetchAuditLog()
      .then((page) => live && setState({ status: 'ready', entries: page.entries }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError ? caught.message : 'Could not read the audit log.',
          code: caught instanceof AuthError ? caught.status : 0,
        })
      })
    return () => {
      live = false
    }
  }, [])

  // 403 is the ordinary answer for most people, so it is not an error state.
  // The log is an administrator's surface, and saying so is more useful than a
  // red box telling somebody they are not allowed something they never asked
  // for.
  if (state.status === 'error' && state.code === 403) {
    return null
  }

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <header>
        <h2 className="font-display text-lg text-ink-900">Audit log</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          What happened in this workspace, newest first.{' '}
          <strong>Refusals are recorded as well as successes</strong> — a log that
          records only what worked cannot tell you that somebody probed.
        </p>
      </header>

      {state.status === 'loading' ? (
        <Waiting>Reading the log…</Waiting>
      ) : state.status === 'error' ? (
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : state.entries.length === 0 ? (
        <p className="text-[0.95rem] leading-relaxed text-ink-600">
          Nothing recorded yet. Registering, verifying a domain, inviting somebody and
          changing a setting all land here.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-400">
                  <th className="py-2 pr-4 font-normal">When</th>
                  <th className="py-2 pr-4 font-normal">What</th>
                  <th className="py-2 pr-4 font-normal">Object</th>
                  <th className="py-2 font-normal">Why</th>
                </tr>
              </thead>
              <tbody>
                {state.entries.map((entry, index) => (
                  <tr
                    key={`${entry.at}-${entry.action}-${index}`}
                    className="border-t border-ink-100 align-top"
                  >
                    <td className="whitespace-nowrap py-2.5 pr-4 font-mono text-2xs text-ink-500">
                      {when(entry.at)}
                    </td>
                    <td className="py-2.5 pr-4 text-ink-900">{readable(entry.action)}</td>
                    <td className="py-2.5 pr-4 text-ink-500">
                      {entry.target_type ? (
                        <span className="font-mono text-2xs">
                          {entry.target_type}
                          {entry.target_id ? `:${entry.target_id.slice(0, 20)}` : ''}
                        </span>
                      ) : (
                        // A dash, never a blank. An empty cell reads as data we
                        // lost rather than as an action with no object.
                        <span aria-hidden>—</span>
                      )}
                    </td>
                    <td className="py-2.5 leading-relaxed text-ink-600">
                      {entry.reason ?? <span aria-hidden>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="border-t border-ink-100 pt-3 text-sm text-ink-400">
            The fifty most recent. Who did each one is stored and not shown here yet —
            the log holds an account id, and turning that into a name needs a join this
            endpoint does not make.
          </p>
        </>
      )}
    </section>
  )
}
