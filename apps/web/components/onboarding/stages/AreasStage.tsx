'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import { fetchDepartments, saveDepartments, type DepartmentState } from '@/lib/settings-client'
import { fetchRateCard, formatMinor, type RateCardDepartment } from '@/lib/billing-client'
import { duration, easing, staggerGroup, useMotionSafe } from '@/lib/motion'

/**
 * Part 2 of 3 — Areas of Interest, the centerpiece of the combined flow.
 *
 * Icon department tiles (Direction B, `onboarding-b-board.html`), inside
 * Direction A's calm one-thing-at-a-time shell (ADR 0067, the product owner's
 * chosen mix). Backed by the real `workspace_department` set via
 * `fetchDepartments`/`saveDepartments` — floor of one, 3–5 recommended, with
 * `executive` (Chief of Staff) filtered out: it is automatic and never a
 * choice, per `services/api/app/domain/departments.py`.
 */

type Stage =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; departments: DepartmentState[] }

/** The accent-per-department mapping already live on the marketing site's
 *  Directors section (`lib/content.ts`), reused here for recognisability
 *  rather than inventing a second colour code for the same six departments. */
const ACCENT: Record<string, { markBg: string; markText: string; icon: ReactNode }> = {
  marketing: {
    markBg: 'bg-steel-100',
    markText: 'text-steel-600',
    icon: (
      <path
        d="M4 18V9l8-5 8 5v9M9 18v-5h6v5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    ),
  },
  sales: {
    markBg: 'bg-clay-100',
    markText: 'text-clay-600',
    icon: (
      <path
        d="M4 14l5-5 4 4 7-7M15 6h5v5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    ),
  },
  finance: {
    markBg: 'bg-ink-100',
    markText: 'text-ink-700',
    icon: (
      <path
        d="M12 3v18M7 7h6.5a2.5 2.5 0 0 1 0 5H8a2.5 2.5 0 0 0 0 5h7"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    ),
  },
  operations: {
    markBg: 'bg-steel-100',
    markText: 'text-steel-600',
    icon: (
      <>
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.6" fill="none" />
        <path
          d="M19 12a7 7 0 0 0-.2-1.6l2-1.4-2-3.4-2.3.6a7 7 0 0 0-2.8-1.6L13 2h-2l-.7 2.6a7 7 0 0 0-2.8 1.6l-2.3-.6-2 3.4 2 1.4A7 7 0 0 0 5 12"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </>
    ),
  },
  hr: {
    markBg: 'bg-slate-100',
    markText: 'text-slate-600',
    icon: (
      <>
        <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.6" fill="none" />
        <path
          d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 5.5a3 3 0 0 1 0 5.9M21 20c0-2.8-2-5.2-4.6-5.8"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          fill="none"
        />
      </>
    ),
  },
  strategy: {
    markBg: 'bg-gold-100',
    markText: 'text-gold-700',
    icon: (
      <path
        d="M3 12h4l3-8 4 16 3-8h4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    ),
  },
}

const RECOMMENDED = { min: 3, max: 5 }

function countNote(count: number): string {
  if (count === 0) return 'Pick at least one to continue'
  if (count < RECOMMENDED.min) return 'A good start — most companies pick a few more'
  if (count <= RECOMMENDED.max) return 'A good range'
  return 'A wide range — you can always narrow this later in Settings'
}

const DESCRIPTIONS: Record<string, string> = {
  marketing: 'Campaigns, SEO, brand positioning, content',
  sales: 'Pipeline, forecasting, proposals, follow-ups',
  finance: 'Revenue, margin, cash-flow signals, pricing',
  operations: 'SOPs, workflows, bottlenecks, task management',
  hr: 'Policies, recruitment, onboarding, training',
  strategy: 'Expansion planning, market entry, risk',
}

export function AreasStage({
  onComplete,
}: {
  /** The non-`executive` department values this founder kept selected. */
  onComplete: (selected: string[]) => void
}) {
  const [stage, setStage] = useState<Stage>({ status: 'loading' })
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [rate, setRate] = useState<{ currency: string; byKey: Record<string, RateCardDepartment> } | null>(
    null,
  )
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const safe = useMotionSafe()

  useEffect(() => {
    let alive = true
    async function load() {
      setStage({ status: 'loading' })
      // The price list is supplementary: a billing hiccup must not stop the
      // founder choosing areas, so it loads in parallel and its failure only
      // drops the price/tool detail from the cards.
      void fetchRateCard()
        .then((card) => {
          if (!alive) return
          const byKey: Record<string, RateCardDepartment> = {}
          for (const dept of card.departments) byKey[dept.key] = dept
          setRate({ currency: card.currency, byKey })
        })
        .catch(() => {
          if (alive) setRate(null)
        })
      try {
        const { departments } = await fetchDepartments()
        if (!alive) return
        const selectable = departments.filter((d) => d.value !== 'executive')
        setSelected(new Set(selectable.filter((d) => d.running).map((d) => d.value)))
        setStage({ status: 'ready', departments: selectable })
      } catch (error) {
        if (!alive) return
        setStage({
          status: 'error',
          message: error instanceof AuthError ? error.message : 'Could not reach the account service.',
        })
      }
    }
    void load()
    return () => {
      alive = false
    }
  }, [])

  function toggle(value: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  async function continueToQuestions() {
    if (selected.size === 0) return
    setSaving(true)
    setSaveError(null)
    try {
      const values = Array.from(selected)
      await saveDepartments(values)
      onComplete(values)
    } catch (error) {
      setSaveError(error instanceof AuthError ? error.message : 'Could not reach the account service.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-page text-ink-900">
        Which parts of the business should NEXUS pay attention to?
      </h1>
      <p className="-mt-2 max-w-read text-body text-ink-600">
        This decides which directors and dashboards you get. Pick what you actually run —{' '}
        {RECOMMENDED.min} to {RECOMMENDED.max} is typical, and you can change this later in Settings.
      </p>

      {stage.status === 'loading' ? (
        <div aria-hidden className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-44 animate-breathe rounded-card bg-bone-200"
              style={{ animationDelay: `${i * 0.08}s` }}
            />
          ))}
        </div>
      ) : stage.status === 'error' ? (
        <div role="alert" className="mt-2 rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
          <h3 className="font-medium text-ink-800">The department list didn&rsquo;t load</h3>
          <p className="mt-2 text-sm text-clay-600">{stage.message}</p>
          <Button variant="danger" size="sm" className="mt-4" onClick={() => setStage({ status: 'loading' })}>
            Retry
          </Button>
        </div>
      ) : stage.departments.length === 0 ? (
        <div role="status" className="mt-2 rounded-data border border-dashed border-bone-400 px-6 py-5">
          <h3 className="font-medium text-ink-800">Nothing to choose from yet</h3>
          <p className="mt-2 text-sm text-ink-600">
            This is unusual. You can still continue — Settings lets you set this any time.
          </p>
          <Button size="sm" className="mt-4" onClick={() => onComplete([])}>
            Continue
          </Button>
        </div>
      ) : (
        <>
          <motion.ul
            variants={staggerGroup(safe)}
            initial="hidden"
            animate="show"
            className="mt-2 grid grid-cols-1 gap-4 sm:auto-rows-fr sm:grid-cols-2 xl:grid-cols-3"
          >
            {stage.departments.map((department) => {
              const accent = ACCENT[department.value] ?? ACCENT.marketing
              const checked = selected.has(department.value)
              const rateInfo = rate?.byKey[department.value]
              const price =
                rateInfo && rateInfo.amount_minor != null && rate
                  ? formatMinor(rateInfo.amount_minor, rate.currency)
                  : null
              return (
                <motion.li key={department.value} className="h-full">
                  <label className="group relative block h-full cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(department.value)}
                      className="peer sr-only"
                    />
                    <motion.span
                      whileTap={safe ? { scale: 0.97 } : undefined}
                      transition={{ duration: duration.micro, ease: easing.out }}
                      className={`relative flex h-full min-h-[11rem] flex-col rounded-card border-[1.5px] bg-white p-5 shadow-e1 transition-[border-color,box-shadow] duration-base ease-out peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-steel-500 sm:hover:shadow-e2 ${
                        checked ? 'border-ink-800 shadow-e2' : 'border-bone-300'
                      }`}
                    >
                      <span
                        className={`mb-3 flex h-11 w-11 items-center justify-center rounded-full ${accent.markBg} ${accent.markText}`}
                      >
                        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
                          {accent.icon}
                        </svg>
                      </span>
                      <h3 className="text-card font-semibold text-ink-800">{department.label}</h3>
                      {price ? (
                        <p className="mt-1 text-card font-semibold tabular-nums text-ink-900">
                          {price} <span className="text-meta font-normal text-ink-400">/ mo</span>
                        </p>
                      ) : null}
                      <p className="mt-1 text-meta text-ink-500">{DESCRIPTIONS[department.value] ?? ''}</p>
                      {rateInfo ? (
                        <div className="mt-auto border-t border-bone-200 pt-3">
                          {rateInfo.tools.length > 0 ? (
                            <>
                              <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
                                Tools included
                              </p>
                              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                                {rateInfo.tools.map((tool) => (
                                  <li
                                    key={tool.key}
                                    className="rounded-full bg-bone-100 px-2 py-0.5 text-2xs text-ink-600"
                                  >
                                    {tool.label}
                                  </li>
                                ))}
                              </ul>
                            </>
                          ) : (
                            <p className="text-2xs text-ink-400">No connected tools yet</p>
                          )}
                        </div>
                      ) : null}
                      <span
                        aria-hidden
                        className={`absolute right-4 top-4 flex h-6 w-6 items-center justify-center rounded-full border-[1.5px] transition-colors duration-micro ease-out ${
                          checked ? 'border-ink-800 bg-ink-800' : 'border-bone-400 bg-white'
                        }`}
                      >
                        <svg
                          viewBox="0 0 16 16"
                          width="12"
                          height="12"
                          fill="none"
                          className={`text-bone-50 ${checked ? 'opacity-100' : 'opacity-0'}`}
                        >
                          <path
                            d="M3 8.5l3 3 7-7"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </span>
                    </motion.span>
                  </label>
                </motion.li>
              )
            })}
          </motion.ul>

          <div aria-live="polite" className="flex items-center justify-between text-meta text-ink-500">
            <span>
              <strong className="tabular-nums text-ink-800">{selected.size}</strong> of{' '}
              {stage.departments.length} selected — {countNote(selected.size)}
            </span>
          </div>

          {saveError ? (
            <p role="alert" className="text-sm text-clay-600">
              {saveError}
            </p>
          ) : null}

          <div className="mt-2">
            <Button
              size="lg"
              disabled={selected.size === 0 || saving}
              loading={saving}
              loadingLabel="Saving…"
              onClick={() => void continueToQuestions()}
              disabledReason={selected.size === 0 ? 'Pick at least one area to continue.' : undefined}
            >
              Continue
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
