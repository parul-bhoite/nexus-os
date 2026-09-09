'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import {
  fetchReporting,
  saveReporting,
  type Reporting,
  type ReportingSetting,
} from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * The assumptions every tile's window is cut against.
 *
 * `doc/13` §13, ADR 0025. Doc 05 §1 requires seven global assumptions *before
 * any dashboard renders*, and four of them had nowhere to live — so a working
 * drawer that has to print "Window 19 Jul - 17 Aug · weeks start Sunday" had
 * nothing to print it from. This is the screen that fills them in.
 *
 * **Every field says what it changes, and how many tiles move.** The sentence
 * and the count both come from the API, which derives the count from the
 * capability registry against the departments this company runs. A hand-written
 * "moves 14 tiles" is true on the day somebody counts it; and a browser that
 * counted for itself would be a second place to be wrong.
 *
 * **A read-only reader is not a hidden one.** A Contributor may not change these
 * and can still see them, because a number is only checkable if the assumptions
 * under it are visible to the person checking. That is the opposite of the rule
 * for departments — reach decides whether a *department* is on screen at all —
 * and the difference is that these assumptions are cited in the arithmetic of
 * tiles this person is already allowed to read.
 */

/**
 * The currencies of the GCC, then the two a GCC company most often reports a
 * group in. Not every ISO 4217 code: a list of 180 in a dropdown is a list
 * nobody scrolls, and the API accepts any three letters — so a company
 * reporting in something else is a field to widen rather than a wall.
 */
const CURRENCIES = [
  { value: 'OMR', label: 'OMR — Omani rial' },
  { value: 'AED', label: 'AED — UAE dirham' },
  { value: 'SAR', label: 'SAR — Saudi riyal' },
  { value: 'QAR', label: 'QAR — Qatari riyal' },
  { value: 'KWD', label: 'KWD — Kuwaiti dinar' },
  { value: 'BHD', label: 'BHD — Bahraini dinar' },
  { value: 'USD', label: 'USD — US dollar' },
  { value: 'EUR', label: 'EUR — Euro' },
]

const COUNTRIES = [
  { value: 'OM', label: 'Oman' },
  { value: 'AE', label: 'United Arab Emirates' },
  { value: 'SA', label: 'Saudi Arabia' },
  { value: 'QA', label: 'Qatar' },
  { value: 'KW', label: 'Kuwait' },
  { value: 'BH', label: 'Bahrain' },
]

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

const WEEK_STARTS = [
  'sunday',
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
]

const SCALES: Array<{ value: string; label: string }> = [
  { value: 'units', label: 'In full — 184,600' },
  { value: 'thousands', label: 'Thousands — 184.6K' },
  { value: 'millions', label: 'Millions — 0.2M' },
]

/** Asia/Muscat first, because that is who this product is for. */
const TIMEZONES = ['Asia/Muscat', 'Asia/Dubai', 'Asia/Riyadh', 'Asia/Qatar', 'Asia/Kuwait', 'UTC']

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; reporting: Reporting }

function title(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1)
}

/**
 * The consequence line under a control.
 *
 * **Three shapes, not two**, and the third is the currency. It restates — every
 * figure in the product goes from rials to dirhams — and it recomputes nothing,
 * so `moves_tiles` is zero. The two-branch version rendered *"Moves 0 tiles"*
 * for it: true, and exactly the uselessness the other branch exists to avoid.
 *
 * Saying "moves 0 tiles" about the decimal places would be the same mistake in
 * the other direction, which is why that branch says what it does change.
 */
function Consequence({ setting }: { setting: ReportingSetting }) {
  const where =
    setting.moves_departments.length > 0
      ? ` across ${setting.moves_departments.join(', ')}`
      : ''

  return (
    <p className="mt-1.5 text-sm leading-relaxed text-ink-500">
      {setting.changes}
      {setting.restates && setting.moves_tiles > 0 ? (
        <span className="mt-1 block font-medium text-clay-600">
          Moves {setting.moves_tiles} tile{setting.moves_tiles === 1 ? '' : 's'}
          {where}.
        </span>
      ) : setting.restates ? (
        <span className="mt-1 block font-medium text-clay-600">
          Relabels every figure in the product. Nothing is recomputed.
        </span>
      ) : (
        <span className="mt-1 block text-ink-400">
          Changes how figures are written, not what they are.
        </span>
      )}
    </p>
  )
}

export function ReportingCard() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    let live = true
    fetchReporting()
      .then((reporting) => live && setState({ status: 'ready', reporting }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError
              ? caught.message
              : 'Could not read your reporting settings.',
        })
      })
    return () => {
      live = false
    }
  }, [])

  if (state.status === 'loading') return <Waiting>Reading your reporting settings…</Waiting>

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

  const { reporting } = state
  const editable = reporting.may_administer
  const setting = (key: string) => reporting.settings.find((s) => s.key === key)

  const update = (patch: Partial<Reporting>) => {
    setSaved(false)
    setProblem('')
    setState({ status: 'ready', reporting: { ...reporting, ...patch } })
  }

  const submit = async () => {
    setSaving(true)
    setProblem('')
    try {
      const fresh = await saveReporting({
        currency: reporting.currency,
        country: reporting.country,
        fiscal_year_start_month: reporting.fiscal_year_start_month,
        week_start: reporting.week_start,
        timezone: reporting.timezone,
        scale: reporting.scale,
        decimals: reporting.decimals,
      })
      setState({ status: 'ready', reporting: fresh })
      setSaved(true)
    } catch (caught: unknown) {
      setProblem(
        caught instanceof AuthError ? caught.message : 'Could not save your reporting settings.',
      )
    } finally {
      setSaving(false)
    }
  }

  const field = 'w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-ink-900 disabled:bg-bone-100 disabled:text-ink-500'
  const label = 'font-mono text-2xs uppercase tracking-[0.12em] text-ink-400'

  return (
    <section className="flex flex-col gap-5 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <header>
        <h2 className="font-display text-lg text-ink-900">Reporting</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Every figure on every dashboard is cut against these. Each tile states its own
          window in its working, and this is what that window is measured from — so a
          change here restates numbers rather than restyling them.
        </p>
        {!editable ? (
          <p className="mt-3 rounded-lg border border-ink-100 bg-bone-50 px-3 py-2 text-sm text-ink-500">
            Set by an owner or an executive. You can see them because the arithmetic on
            your tiles cites them.
          </p>
        ) : null}
      </header>

      <div className="flex flex-col gap-5">
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className={label} htmlFor="reporting-currency">
              {setting('currency')?.label ?? 'You report in'}
            </label>
            <select
              id="reporting-currency"
              className={`${field} mt-1.5`}
              disabled={!editable}
              value={reporting.currency}
              onChange={(event) => update({ currency: event.target.value })}
            >
              {CURRENCIES.map((currency) => (
                <option key={currency.value} value={currency.value}>
                  {currency.label}
                </option>
              ))}
            </select>
            {setting('currency') ? <Consequence setting={setting('currency')!} /> : null}
          </div>

          <div>
            <label className={label} htmlFor="reporting-country">
              Country
            </label>
            <select
              id="reporting-country"
              className={`${field} mt-1.5`}
              disabled={!editable}
              value={reporting.country}
              onChange={(event) => update({ country: event.target.value })}
            >
              {COUNTRIES.map((country) => (
                <option key={country.value} value={country.value}>
                  {country.label}
                </option>
              ))}
            </select>
            {/* A company fact rather than a reporting assumption — it belongs
                with the name and the website on panel 4, which is not built.
                It is here because the alternative was asking for it nowhere. */}
            <p className="mt-1.5 text-sm text-ink-400">
              Where the company is. Registration stopped asking for it.
            </p>
          </div>
        </div>

        <div>
          <label className={label} htmlFor="fiscal-year">
            {setting('fiscal_year_start_month')?.label ?? 'Financial year starts'}
          </label>
          <select
            id="fiscal-year"
            className={`${field} mt-1.5`}
            disabled={!editable}
            value={reporting.fiscal_year_start_month}
            onChange={(event) =>
              update({ fiscal_year_start_month: Number(event.target.value) })
            }
          >
            {MONTHS.map((month, index) => (
              <option key={month} value={index + 1}>
                {month}
              </option>
            ))}
          </select>
          {setting('fiscal_year_start_month') ? (
            <Consequence setting={setting('fiscal_year_start_month')!} />
          ) : null}
        </div>

        <div>
          <label className={label} htmlFor="week-start">
            {setting('week_start')?.label ?? 'Reporting week starts'}
          </label>
          <select
            id="week-start"
            className={`${field} mt-1.5`}
            disabled={!editable}
            value={reporting.week_start}
            onChange={(event) => update({ week_start: event.target.value })}
          >
            {WEEK_STARTS.map((day) => (
              <option key={day} value={day}>
                {title(day)}
              </option>
            ))}
          </select>
          {setting('week_start') ? <Consequence setting={setting('week_start')!} /> : null}
        </div>

        <div>
          <label className={label} htmlFor="report-timezone">
            {setting('timezone')?.label ?? 'Reports are cut in'}
          </label>
          <select
            id="report-timezone"
            className={`${field} mt-1.5`}
            disabled={!editable}
            value={reporting.timezone}
            onChange={(event) => update({ timezone: event.target.value })}
          >
            {TIMEZONES.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
          {setting('timezone') ? <Consequence setting={setting('timezone')!} /> : null}
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className={label} htmlFor="report-scale">
              {setting('scale')?.label ?? 'Large figures shown as'}
            </label>
            <select
              id="report-scale"
              className={`${field} mt-1.5`}
              disabled={!editable}
              value={reporting.scale}
              onChange={(event) => update({ scale: event.target.value })}
            >
              {SCALES.map((scale) => (
                <option key={scale.value} value={scale.value}>
                  {scale.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={label} htmlFor="report-decimals">
              {setting('decimals')?.label ?? 'Decimal places'}
            </label>
            <select
              id="report-decimals"
              className={`${field} mt-1.5`}
              disabled={!editable}
              value={reporting.decimals}
              onChange={(event) => update({ decimals: Number(event.target.value) })}
            >
              {[0, 1, 2].map((places) => (
                <option key={places} value={places}>
                  {places}
                </option>
              ))}
            </select>
          </div>
        </div>
        {setting('scale') ? <Consequence setting={setting('scale')!} /> : null}
      </div>

      {problem ? (
        <p role="alert" className="text-sm font-medium text-clay-600">
          {problem}
        </p>
      ) : null}

      {editable ? (
        <div className="flex flex-wrap items-center gap-4 border-t border-ink-100 pt-4">
          <Button onClick={() => void submit()} disabled={saving}>
            {saving ? 'Saving…' : 'Save reporting settings'}
          </Button>
          {saved ? (
            <span className="text-sm text-steel-600">
              Saved. Affected figures will be re-derived rather than edited in place.
            </span>
          ) : null}
        </div>
      ) : null}

      <p className="border-t border-ink-100 pt-4 text-sm text-ink-400">
        {reporting.changed_at
          ? `Last changed ${new Date(reporting.changed_at).toLocaleDateString()}. Every change is in the audit log.`
          : 'Never changed since you registered — these are the defaults for a business in Oman.'}
      </p>
    </section>
  )
}
