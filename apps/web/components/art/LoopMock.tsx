'use client'

import { motion } from 'framer-motion'
import { IconCheck, IconDoc, IconChart, IconGlobe, IconTarget } from '@/components/art/Icons'

/**
 * Compact product fragments, one per loop stage. These are UI mocks, not
 * screenshots — every figure is labelled illustrative by the wrapper below,
 * because the product's core promise is that it never shows an invented number.
 */

const row = 'flex items-center gap-3 rounded-xl border border-bone-200 bg-white p-3'

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative">
      <div className="flex items-center gap-1.5 pb-3">
        <span className="h-2 w-2 rounded-full bg-bone-300" />
        <span className="h-2 w-2 rounded-full bg-bone-300" />
        <span className="h-2 w-2 rounded-full bg-bone-300" />
        <span className="ml-auto font-mono text-2xs uppercase tracking-[0.16em] text-ink-400">
          Illustrative
        </span>
      </div>
      {children}
    </div>
  )
}

function Stagger({ children, i }: { children: React.ReactNode; i: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 14 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.18 + i * 0.08, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  )
}

function Connect() {
  const sources = [
    { name: 'Website', detail: 'nexus-demo.om', done: true, Icon: IconGlobe },
    { name: 'Google Analytics 4', detail: 'OAuth connected', done: true, Icon: IconChart },
    { name: 'Documents', detail: '12 files indexed', done: true, Icon: IconDoc },
    { name: 'Search Console', detail: 'Connect to enable SEO', done: false, Icon: IconTarget },
  ]
  return (
    <Frame>
      <div className="space-y-2.5">
        {sources.map((s, i) => (
          <Stagger key={s.name} i={i}>
            <div className={row}>
              <span
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${
                  s.done ? 'bg-steel-100 text-steel-600' : 'bg-bone-100 text-ink-400'
                }`}
              >
                <s.Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink-800">{s.name}</span>
                <span className="block truncate text-xs text-ink-400">{s.detail}</span>
              </span>
              {s.done ? (
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-ink-800 text-bone-50">
                  <IconCheck className="h-3.5 w-3.5" />
                </span>
              ) : (
                <span className="shrink-0 rounded-full border border-bone-300 px-2.5 py-1 text-2xs text-ink-500">
                  Connect
                </span>
              )}
            </div>
          </Stagger>
        ))}
      </div>
    </Frame>
  )
}

function Understand() {
  const facts = [
    { k: 'Primary service', v: 'Fit-out & joinery', src: 'website /services' },
    { k: 'Target customer', v: 'Commercial developers', src: 'onboarding' },
    { k: 'Day rate', v: 'OMR 145', src: 'Rate-Card-2026.pdf p.3' },
    { k: 'Brand voice', v: 'Direct, technical, no hype', src: 'onboarding' },
  ]
  return (
    <Frame>
      <div className="space-y-2.5">
        {facts.map((f, i) => (
          <Stagger key={f.k} i={i}>
            <div className="rounded-xl border border-bone-200 bg-white p-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-xs text-ink-400">{f.k}</span>
                <span className="text-sm font-medium text-ink-800">{f.v}</span>
              </div>
              <div className="mt-2 flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full bg-gold-500" />
                <span className="truncate font-mono text-2xs text-ink-400">source: {f.src}</span>
              </div>
            </div>
          </Stagger>
        ))}
        <Stagger i={4}>
          <div className="rounded-xl border border-dashed border-clay-300 bg-clay-100/50 p-3">
            <span className="font-mono text-2xs uppercase tracking-[0.14em] text-clay-500">
              Needs confirmation
            </span>
            <p className="mt-1 text-xs leading-relaxed text-ink-600">
              Two competitors were detected but not confirmed by you.
            </p>
          </div>
        </Stagger>
      </div>
    </Frame>
  )
}

function Decide() {
  return (
    <Frame>
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-2xl border border-bone-200 bg-white p-5 shadow-paper"
      >
        <div className="flex items-center justify-between">
          <span className="rounded-full bg-gold-200 px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.14em] text-gold-700">
            Decision required
          </span>
          <span className="font-mono text-2xs text-ink-400">Risk: low</span>
        </div>
        <h4 className="mt-4 font-display text-xl leading-snug text-ink-800">
          Three deals worth OMR 24,000 have been idle for 11 days.
        </h4>
        <p className="mt-2.5 text-xs leading-relaxed text-ink-500">
          All three stalled after the proposal stage. Your average close time from this stage is 6
          days.
        </p>

        <div className="mt-4 rounded-lg bg-bone-50 p-3">
          <span className="font-mono text-2xs uppercase tracking-[0.14em] text-ink-400">
            Why you are seeing this
          </span>
          <div className="mt-2 space-y-1">
            {['CRM · deal.last_activity_at', 'CRM · stage_duration_avg'].map((s) => (
              <div key={s} className="font-mono text-2xs text-ink-500">
                → {s}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {['Draft follow-ups', 'Ask why', 'Dismiss'].map((a, i) => (
            <span
              key={a}
              className={`rounded-full px-3 py-1.5 text-xs ${
                i === 0
                  ? 'bg-ink-800 text-bone-50'
                  : 'border border-bone-300 bg-white text-ink-600'
              }`}
            >
              {a}
            </span>
          ))}
        </div>
      </motion.div>
    </Frame>
  )
}

function Execute() {
  return (
    <Frame>
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, duration: 0.5 }}
        className="overflow-hidden rounded-2xl border border-bone-200 bg-white shadow-paper"
      >
        <div className="flex items-center justify-between border-b border-bone-200 px-4 py-3">
          <span className="text-sm font-medium text-ink-800">Proposal — client project</span>
          <span className="font-mono text-2xs text-ink-400">DRAFT</span>
        </div>
        <div className="space-y-3 p-4">
          {[
            { item: 'Design & documentation', price: 'OMR 3,200', cite: 'Rate-Card-2026.pdf p.2' },
            { item: 'Joinery fabrication', price: 'OMR 11,850', cite: 'Rate-Card-2026.pdf p.4' },
          ].map((l, i) => (
            <Stagger key={l.item} i={i}>
              <div className="flex items-start justify-between gap-3 border-b border-bone-100 pb-3">
                <span className="min-w-0">
                  <span className="block text-sm text-ink-700">{l.item}</span>
                  <span className="mt-1 flex items-center gap-1.5">
                    <IconDoc className="h-3 w-3 shrink-0 text-gold-600" />
                    <span className="truncate font-mono text-2xs text-ink-400">{l.cite}</span>
                  </span>
                </span>
                <span className="shrink-0 font-mono text-sm text-ink-800">{l.price}</span>
              </div>
            </Stagger>
          ))}
          <Stagger i={2}>
            <div className="flex items-start justify-between gap-3 rounded-lg border border-dashed border-clay-300 bg-clay-100/40 p-2.5">
              <span className="text-sm text-ink-600">Site supervision</span>
              <span className="shrink-0 font-mono text-2xs text-clay-500">
                price not found — add manually
              </span>
            </div>
          </Stagger>
        </div>
      </motion.div>
    </Frame>
  )
}

function Improve() {
  const weeks = [58, 61, 60, 64, 67, 66, 72]
  const max = 80
  return (
    <Frame>
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, duration: 0.5 }}
        className="rounded-2xl border border-bone-200 bg-white p-5 shadow-paper"
      >
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium text-ink-800">Company Health Score</span>
          <span className="font-mono text-2xs text-steel-600">7 weeks</span>
        </div>

        <div className="mt-5 flex h-28 items-end gap-2">
          {weeks.map((w, i) => (
            <motion.div
              key={i}
              initial={{ height: 0 }}
              animate={{ height: `${(w / max) * 100}%` }}
              transition={{ delay: 0.25 + i * 0.07, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className={`flex-1 rounded-t-md ${
                i === weeks.length - 1 ? 'bg-ink-800' : 'bg-steel-300'
              }`}
            />
          ))}
        </div>

        <div className="mt-4 border-t border-bone-200 pt-4">
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-steel-100 px-2 py-0.5 font-mono text-2xs text-steel-600">
              +6 this week
            </span>
            <span className="text-xs text-ink-400">Marketing 54 → 61</span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-ink-500">
            Organic sessions rose after three SEO briefs were published. Sales was unchanged and is
            reported as unchanged.
          </p>
        </div>
      </motion.div>
    </Frame>
  )
}

const mocks = {
  connect: Connect,
  understand: Understand,
  decide: Decide,
  execute: Execute,
  improve: Improve,
} as const

export function LoopMock({ step }: { step: string }) {
  const Mock = mocks[step as keyof typeof mocks] ?? Connect
  return <Mock />
}
