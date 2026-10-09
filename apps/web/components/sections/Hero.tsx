'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { Button, ArrowRight } from '@/components/ui/Button'
import { RevealWords } from '@/components/motion/Reveal'
import { IconSparkle, IconCheck } from '@/components/art/Icons'
import { hero } from '@/lib/content'

/* Entrance animations here are CSS classes (`animate-rise`, `animate-rise-scale`,
   `animate-fade-in` in globals.css), not framer-motion.

   Everything in this section is above the fold. A JS-driven entrance writes its
   hidden state into the server HTML, so the hero renders at `opacity: 0` and
   stays there until React hydrates — a blank first paint on a slow connection,
   and a permanently blank one if the bundle fails. CSS keyframes run at first
   paint with no bundle and no hydration, and the global reduced-motion rule
   collapses their duration instead of leaving anything hidden.

   framer-motion is still the right tool below the fold, where reveals need
   viewport detection and the bundle has long since arrived. The one in-view-
   independent exception here is the sparkline/bar growth, which is above the
   fold and short — it is cheap and never gates a click. */

/**
 * The `Illustrative` marker every product mock must carry.
 *
 * CLAUDE.md's content rule is not decoration: the product sells on never
 * inventing a number, and these cards show numbers invented for the page. The
 * label travels with the card because the card is screenshot-shaped — a footnote
 * at the foot of the page does not.
 */
function IllustrativeTag() {
  return (
    <span className="ml-auto shrink-0 rounded-md bg-bone-100 px-1.5 py-0.5 font-mono text-2xs uppercase tracking-[0.14em] text-ink-500">
      Illustrative
    </span>
  )
}

/** A cited source chip — the shape of the product's central promise. */
function Source({ name }: { name: string }) {
  return (
    <span className="rounded-md bg-bone-100 px-1.5 py-0.5 font-mono text-2xs text-ink-500">
      {name}
    </span>
  )
}

/**
 * The hero's proof, as one stacked cluster of product fragments rather than a
 * decorative illustration (ADR 0072). Each card says something true about what
 * NEXUS is: a single brain grounded in cited sources, a number that carries its
 * origin, and one team across every department. Shape, not real data.
 */

/** 1 — the Company Brain, grounded in connected sources. */
function BrainCard() {
  return (
    <div className="surface relative z-20 w-full rounded-card p-5 shadow-e2">
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-gold-400 opacity-75 motion-safe:animate-pulse-ring" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-gold-500" />
        </span>
        <span className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-500">
          Company Brain
        </span>
        <IllustrativeTag />
      </div>
      <p className="mt-3 font-display text-card font-semibold text-ink-900">
        Grounded in 6 connected sources
      </p>
      <p className="mt-1.5 text-meta text-ink-500">
        Every answer cites where it came from — nothing is invented.
      </p>
      <div className="mt-3.5 flex flex-wrap gap-1.5">
        {['Website', 'CRM', 'GA4', 'Docs', 'Xero'].map((s) => (
          <Source key={s} name={s} />
        ))}
      </div>
    </div>
  )
}

/** 2 — a number that carries its source and its direction. */
function MetricCard() {
  const reduced = useReducedMotion()
  // A monochrome sparkline; the only colour is the amber endpoint — the spark.
  const pts = [4, 9, 7, 14, 12, 20, 17, 27, 31]
  const max = 34
  const path = pts
    .map((v, i) => `${(i / (pts.length - 1)) * 200},${48 - (v / max) * 40}`)
    .join(' ')
  const last = { x: 200, y: 48 - (pts[pts.length - 1] / max) * 40 }

  return (
    <div className="surface relative z-10 w-[17rem] max-w-full -rotate-1 rounded-card p-5 shadow-e2">
      <div className="flex items-center gap-2">
        <span className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-500">
          Cash on hand
        </span>
        <IllustrativeTag />
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-display text-figure-sm font-extrabold tabular-nums text-ink-950">
          OMR 48,200
        </span>
        <span className="font-mono text-2xs font-medium text-ink-700">▲ 12.4%</span>
      </div>
      <svg
        viewBox="0 0 200 56"
        preserveAspectRatio="none"
        aria-hidden="true"
        className="mt-3 h-12 w-full overflow-visible"
      >
        <motion.polyline
          points={path}
          fill="none"
          className="stroke-ink-800"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={reduced ? false : { pathLength: 0 }}
          animate={reduced ? undefined : { pathLength: 1 }}
          transition={{ duration: 1.1, delay: 1.1, ease: [0.16, 1, 0.3, 1] }}
        />
        <circle cx={last.x} cy={last.y} r="3.5" className="fill-gold-500" />
      </svg>
      <div className="mt-2.5">
        <Source name="source: Xero" />
      </div>
    </div>
  )
}

/** 3 — one brain, every department. */
function DepartmentsCard() {
  const depts = [
    { k: 'S', name: 'Sales' },
    { k: 'M', name: 'Marketing' },
    { k: 'O', name: 'Ops' },
    { k: 'P', name: 'People' },
    { k: 'F', name: 'Finance' },
    { k: '◆', name: 'Chief of Staff' },
  ]
  return (
    <div className="surface relative z-20 ml-auto w-[16rem] max-w-full rotate-1 rounded-card p-5 shadow-e2">
      <span className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-500">
        Every department, one brain
      </span>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {depts.map((d) => (
          <div
            key={d.name}
            className="flex flex-col items-center gap-1 rounded-data bg-bone-50 py-2.5"
          >
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink-950 font-display text-xs font-bold text-bone-50">
              {d.k}
            </span>
            <span className="text-2xs text-ink-500">{d.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** The brand X, ghosted large behind the cluster. */
function XWatermark() {
  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className="pointer-events-none absolute -right-10 -top-12 -z-0 h-[26rem] w-[26rem] opacity-70"
      fill="none"
    >
      <line x1="26" y1="26" x2="74" y2="74" className="stroke-ink-100" strokeWidth="11" strokeLinecap="round" />
      <line x1="26" y1="74" x2="50" y2="50" className="stroke-ink-100" strokeWidth="11" strokeLinecap="round" />
      <line x1="50" y1="50" x2="74" y2="26" className="stroke-gold-200" strokeWidth="11" strokeLinecap="round" />
    </svg>
  )
}

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden pt-32 lg:pt-36">
      {/* Ambient wash — a faint neutral lift plus one breath of amber, keeping the
          page white (ADR 0072). */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[46rem] bg-[radial-gradient(60rem_36rem_at_72%_16%,rgba(11,12,14,0.05),transparent_64%),radial-gradient(34rem_24rem_at_10%_6%,rgba(226,136,31,0.10),transparent_70%)]"
      />

      <div className="shell relative">
        <div className="grid items-center gap-14 lg:grid-cols-[1.05fr_1fr] lg:gap-12">
          {/* ── Copy ─────────────────────────────────────────── */}
          <div className="relative z-10 max-w-2xl">
            <div className="animate-rise inline-flex items-center gap-2 rounded-full border border-bone-300 bg-white/70 py-1.5 pl-2 pr-4 shadow-paper backdrop-blur">
              <span className="grid h-6 w-6 place-items-center rounded-full bg-gold-100 text-gold-700">
                <IconSparkle className="h-3.5 w-3.5" />
              </span>
              <span className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-600">
                {hero.eyebrow}
              </span>
            </div>

            <h1 className="mt-7 text-display text-balance">
              <RevealWords text={hero.headlineTop} delay={0.15} />{' '}
              <span className="relative inline-block">
                <RevealWords text={hero.headlineAccent} delay={0.28} />
                {/* Hand-drawn underline, drawn on after the words land — the spark. */}
                <motion.svg
                  viewBox="0 0 340 18"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                  className="absolute -bottom-[0.12em] left-0 h-[0.16em] w-full text-gold-500"
                >
                  <motion.path
                    d="M3 12C58 5 132 3 190 6c46 2 96 5 147 8"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="5"
                    strokeLinecap="round"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ duration: 1, delay: 0.9, ease: [0.16, 1, 0.3, 1] }}
                  />
                </motion.svg>
              </span>
              <br />
              <RevealWords text={hero.headlineBottom} delay={0.42} wordClassName="text-ink-500" />
            </h1>

            <p
              style={{ animationDelay: '0.72s' }}
              className="animate-rise mt-7 max-w-xl text-pretty text-lg leading-relaxed text-ink-500"
            >
              {hero.sub}
            </p>

            {/* `doc/11` Q1 (D18): one action, and it is sign up. */}
            <div
              style={{ animationDelay: '0.84s' }}
              className="animate-rise mt-9 flex flex-col items-start gap-3 sm:flex-row sm:items-center"
            >
              <Button href="/register" size="lg" icon={<ArrowRight />}>
                {hero.primaryCta}
              </Button>
              <Button href="#loop" size="lg" variant="secondary">
                {hero.secondaryCta}
              </Button>
            </div>

            <p
              style={{ animationDelay: '1s' }}
              className="animate-fade-in mt-6 flex items-start gap-2 text-sm text-ink-400"
            >
              <IconCheck className="mt-0.5 h-4 w-4 shrink-0 text-ink-500" />
              {hero.note}
            </p>

            {/* G10, ADR 0046. A second, quiet door — not a competing CTA. */}
            <div style={{ animationDelay: '1.1s' }} className="animate-fade-in mt-3">
              <Button href="/scan" variant="quiet" size="sm">
                Or see 3 real gaps on your own site first
              </Button>
            </div>
          </div>

          {/* ── Product proof cluster ────────────────────────── */}
          <div
            style={{ animationDelay: '0.25s' }}
            className="animate-rise-scale relative mx-auto w-full max-w-[32rem] lg:max-w-none"
          >
            <XWatermark />
            <div className="relative flex flex-col gap-4">
              <BrainCard />
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                <MetricCard />
                <DepartmentsCard />
              </div>
            </div>
          </div>
        </div>

        {/* ── Value ticker ───────────────────────────────────── */}
        <div
          style={{ animationDelay: '1.2s' }}
          className="animate-fade-in mt-20 border-t border-bone-200 py-6 lg:mt-24"
        >
          <div className="mask-fade-x overflow-hidden pause-on-hover">
            <div className="flex w-max motion-safe:animate-marquee">
              {[0, 1].map((copy) => (
                <div key={copy} className="flex shrink-0 items-center" aria-hidden={copy === 1}>
                  {hero.ticker.map((t) => (
                    <span
                      key={t}
                      className="flex shrink-0 items-center gap-4 px-8 font-display text-lg text-ink-400"
                    >
                      {t}
                      <span className="h-1 w-1 rounded-full bg-gold-400" />
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
