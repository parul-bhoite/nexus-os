'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import {
  fetchDepartments,
  saveDepartments,
  type DepartmentState,
  type Departments,
} from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * Which departments the company runs — panel 7 (`doc/13` §14).
 *
 * The gap this closes: department selection happened once, during onboarding,
 * and never again. A company that hired into a new function could not add its
 * director, and the only writer was a route that advances the onboarding spine.
 *
 * ## Three things the screen has to say
 *
 * **What each one brings.** The capability count comes from the API, derived
 * from the registry — a founder ticking Operations should know it carries
 * fifteen capabilities and five questions before they tick it, not after.
 *
 * **That removing one is a scope change.** The director leaves every nav and
 * the department's figures stop being computed. Its **answers survive** (Q32):
 * a company that stops running Sales has not made its old Sales answers untrue,
 * it has made them historical.
 *
 * **That one is the floor.** Finding F1: a stored selection of none and a
 * company that has not chosen yet both read as "nothing ruled out", which hands
 * back all seven directors — the opposite of what the screen just promised.
 */

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: Departments; chosen: Set<string> }

export function DepartmentsCard() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    let live = true
    fetchDepartments()
      .then((data) => {
        if (!live) return
        setState({
          status: 'ready',
          data,
          chosen: new Set(data.departments.filter((d) => d.running).map((d) => d.value)),
        })
      })
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError ? caught.message : 'Could not read your departments.',
        })
      })
    return () => {
      live = false
    }
  }, [])

  if (state.status === 'loading') return <Waiting>Loading your departments…</Waiting>

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

  const { data, chosen } = state
  const editable = data.may_administer

  const toggle = (value: string) => {
    const next = new Set(chosen)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    setSaved(false)
    setProblem('')
    setState({ ...state, chosen: next })
  }

  const removing = data.departments.filter((d) => d.running && !chosen.has(d.value))
  const adding = data.departments.filter((d) => !d.running && chosen.has(d.value))
  const dirty = removing.length > 0 || adding.length > 0

  const submit = async () => {
    setSaving(true)
    setProblem('')
    try {
      // `Array.from` rather than a spread: the workspace targets a lower
      // `lib`, and `tsc` refuses to iterate a Set without downlevelIteration.
      const fresh = await saveDepartments(Array.from(chosen))
      setState({
        status: 'ready',
        data: fresh,
        chosen: new Set(fresh.departments.filter((d) => d.running).map((d) => d.value)),
      })
      setSaved(true)
    } catch (caught: unknown) {
      setProblem(
        caught instanceof AuthError ? caught.message : 'Could not save your departments.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flex flex-col gap-5 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <header>
        <h2 className="font-display text-lg text-ink-900">Departments</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Each department you run gets a director and a dashboard. The Chief of Staff
          reads the others and is always there, which is why it is not on this list.
        </p>
        {!editable ? (
          <p className="mt-3 rounded-lg border border-ink-100 bg-bone-50 px-3 py-2 text-sm text-ink-500">
            Set by an owner or an executive. You can see them because the nav already
            shows you which ones this company runs.
          </p>
        ) : null}
      </header>

      <ul className="flex flex-col gap-2">
        {data.departments.map((department: DepartmentState) => {
          const on = chosen.has(department.value)
          return (
            <li key={department.value}>
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 transition-colors ${
                  on ? 'border-steel-300 bg-steel-100' : 'border-ink-100 bg-white'
                } ${editable ? '' : 'cursor-default opacity-80'}`}
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={on}
                  disabled={!editable}
                  onChange={() => toggle(department.value)}
                />
                <span>
                  <span className="font-medium text-ink-900">{department.label}</span>
                  <span className="mt-0.5 block text-sm text-ink-500">
                    {department.capabilities} capabilit
                    {department.capabilities === 1 ? 'y' : 'ies'}
                    {department.unanswered > 0 ? (
                      <>
                        {' · '}
                        {department.unanswered} question
                        {department.unanswered === 1 ? '' : 's'} unanswered
                      </>
                    ) : department.answered > 0 ? (
                      <>{' · '}all its questions answered</>
                    ) : null}
                  </span>
                </span>
              </label>
            </li>
          )
        })}
      </ul>

      {/* Stated before it happens, not after. Removing a department takes its
          director off every nav, and the person doing it should read that
          sentence while the checkbox is still theirs to untick. */}
      {removing.length > 0 ? (
        <div className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600">
          <p className="font-medium">
            Removing {removing.map((d) => d.label).join(', ')} takes{' '}
            {removing.length === 1 ? 'its director' : 'those directors'} off the nav and
            stops {removing.length === 1 ? 'its' : 'their'} figures being computed.
          </p>
          <p className="mt-1.5">
            The answers stay. A company that stops running a function has not made its
            old answers untrue — it has made them historical.
          </p>
        </div>
      ) : null}

      {adding.length > 0 ? (
        <div className="rounded-xl border border-steel-300 bg-steel-100 px-4 py-3 text-sm text-steel-700">
          Adding {adding.map((d) => d.label).join(', ')} creates{' '}
          {adding.length === 1 ? 'its director' : 'their directors'} and{' '}
          {adding.length === 1 ? 'its question block' : 'their question blocks'}. Until
          those questions are answered the figures are generic rather than yours.
        </div>
      ) : null}

      {problem ? (
        <p role="alert" className="text-sm font-medium text-clay-600">
          {problem}
        </p>
      ) : null}

      {editable ? (
        <div className="flex flex-wrap items-center gap-4 border-t border-ink-100 pt-4">
          <Button onClick={() => void submit()} disabled={saving || !dirty || chosen.size === 0}>
            {saving ? 'Saving…' : 'Save departments'}
          </Button>
          {chosen.size === 0 ? (
            <span className="text-sm font-medium text-clay-600">
              Keep at least one. With none chosen there is nothing for the Chief of Staff
              to read.
            </span>
          ) : saved ? (
            <span className="text-sm text-steel-600">Saved, and recorded in the audit log.</span>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
