'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchPreferences, savePreferences, type Preferences } from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * How NEXUS talks to you — panel 2 (`doc/13` §14).
 *
 * **The one settings panel with no administrator gate**, and the reason is the
 * rule the whole panel is built on: `doc/06` §2.6, *"no persona field is ever an
 * input to the retrieval predicate."* Every field here is a `persona.*` column,
 * so changing any of them cannot widen what anybody sees —
 * `assert_persona_is_not_authorisation` fails the process at import if a
 * role-shaped key is ever added to that namespace.
 *
 * That is worth stating on the screen too. A person who suspects a preference
 * might be a permission will not change it, and the honest version of "detail
 * level" is that it changes how much you are told and not what you are allowed
 * to know.
 *
 * `priority_topics` is shown and not editable. It is what the persona interview
 * inferred from what the founder said would go wrong, and a checkbox list would
 * turn a considered answer into a shopping basket.
 */

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'ar', label: 'العربية — Arabic' },
]

/** Asia/Muscat first, because that is who this product is for. */
const TIMEZONES = ['Asia/Muscat', 'Asia/Dubai', 'Asia/Riyadh', 'Asia/Qatar', 'Asia/Kuwait', 'UTC']

const STYLES = [
  { value: 'brief', label: 'Brief — the answer, then stop' },
  { value: 'standard', label: 'Standard' },
  { value: 'thorough', label: 'Thorough — show me the working' },
]

const LANDINGS = [
  { value: '', label: 'Wherever my role lands me' },
  { value: 'executive', label: 'Chief of Staff' },
  { value: 'marketing', label: 'Marketing' },
  { value: 'sales', label: 'Sales' },
  { value: 'finance', label: 'Finance' },
  { value: 'operations', label: 'Operations' },
  { value: 'hr', label: 'People' },
  { value: 'strategy', label: 'Strategy' },
]

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; prefs: Preferences }

export function PreferencesCard() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    let live = true
    fetchPreferences()
      .then((prefs) => live && setState({ status: 'ready', prefs }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError ? caught.message : 'Could not read your preferences.',
        })
      })
    return () => {
      live = false
    }
  }, [])

  if (state.status === 'loading') return <Waiting>Loading your preferences…</Waiting>

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

  const { prefs } = state
  const update = (patch: Partial<Preferences>) => {
    setSaved(false)
    setProblem('')
    setState({ status: 'ready', prefs: { ...prefs, ...patch } })
  }

  const submit = async () => {
    setSaving(true)
    setProblem('')
    try {
      const fresh = await savePreferences({
        language: prefs.language,
        timezone: prefs.timezone,
        communication_style: prefs.communication_style,
        default_landing_screen: prefs.default_landing_screen,
      })
      setState({ status: 'ready', prefs: fresh })
      setSaved(true)
    } catch (caught: unknown) {
      setProblem(
        caught instanceof AuthError ? caught.message : 'Could not save your preferences.',
      )
    } finally {
      setSaving(false)
    }
  }

  const field =
    'mt-1.5 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-ink-900'
  const label = 'font-mono text-2xs uppercase tracking-[0.12em] text-ink-400'

  return (
    <section className="flex flex-col gap-5 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <header>
        <h2 className="font-display text-lg text-ink-900">How NEXUS talks to you</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Yours alone, and they change how much you are told —{' '}
          <strong>never what you are allowed to know</strong>. None of these can widen
          what you see, which is why they are the only settings here that do not need an
          owner.
        </p>
      </header>

      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor="pref-language">
            Language
          </label>
          <select
            id="pref-language"
            className={field}
            value={prefs.language}
            onChange={(event) => update({ language: event.target.value })}
          >
            {LANGUAGES.map((language) => (
              <option key={language.value} value={language.value}>
                {language.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={label} htmlFor="pref-timezone">
            Your timezone
          </label>
          <select
            id="pref-timezone"
            className={field}
            value={prefs.timezone}
            onChange={(event) => update({ timezone: event.target.value })}
          >
            {TIMEZONES.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
          {/* The distinction that would otherwise collapse. Panel 5's report
              timezone decides where a *day* ends for the whole company; this
              decides what time a date is shown to one person in. */}
          <p className="mt-1.5 text-sm text-ink-400">
            Where you read from. Where reports are <em>cut</em> is the company&rsquo;s,
            under Reporting.
          </p>
        </div>

        <div>
          <label className={label} htmlFor="pref-style">
            Detail level
          </label>
          <select
            id="pref-style"
            className={field}
            value={prefs.communication_style ?? 'standard'}
            onChange={(event) => update({ communication_style: event.target.value })}
          >
            {STYLES.map((style) => (
              <option key={style.value} value={style.value}>
                {style.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={label} htmlFor="pref-landing">
            Opens on
          </label>
          <select
            id="pref-landing"
            className={field}
            value={prefs.default_landing_screen ?? ''}
            onChange={(event) =>
              update({ default_landing_screen: event.target.value || null })
            }
          >
            {LANDINGS.map((landing) => (
              <option key={landing.value} value={landing.value}>
                {landing.label}
              </option>
            ))}
          </select>
          {/* Landing is resolved from the membership, never from this. A
              preference for a department somebody does not hold would 404 them
              on sign-in, so the API decides and this only expresses a wish. */}
          <p className="mt-1.5 text-sm text-ink-400">
            Only a department you hold. Your role decides what you can reach.
          </p>
        </div>
      </div>

      {prefs.priority_topics.length > 0 ? (
        <div className="rounded-xl border border-ink-100 bg-bone-50 px-4 py-3">
          <p className={label}>What you said you wanted first</p>
          <p className="mt-1.5 text-[0.95rem] leading-relaxed text-ink-700">
            {prefs.priority_topics.join(' · ')}
          </p>
          <p className="mt-1.5 text-sm text-ink-400">
            Taken from what you said would go wrong. Change it by telling the product,
            not by ticking a box — a list of checkboxes would turn a considered answer
            into a shopping basket.
          </p>
        </div>
      ) : null}

      {problem ? (
        <p role="alert" className="text-sm font-medium text-clay-600">
          {problem}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-4 border-t border-ink-100 pt-4">
        <Button onClick={() => void submit()} disabled={saving}>
          {saving ? 'Saving…' : 'Save preferences'}
        </Button>
        {saved ? <span className="text-sm text-steel-600">Saved.</span> : null}
      </div>
    </section>
  )
}
