'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { PaperLandscape } from '@/components/art/PaperLandscape'
import { Button, ArrowRight } from '@/components/ui/Button'
import { RevealWords } from '@/components/motion/Reveal'
import { IconSparkle, IconCheck } from '@/components/art/Icons'
import { hero } from '@/lib/content'
import { usePointerParallax } from '@/lib/hooks'

/* Entrance animations here are CSS classes (`animate-rise`, `animate-rise-scale`,
   `animate-fade-in` in globals.css), not framer-motion.
 
   Everything in this section is above the fold. A JS-driven entrance writes its
   hidden state into the server HTML, so the hero renders at `opacity: 0` and
   stays there until React hydrates — a blank first paint on a slow connection,
   and a permanently blank one if the bundle fails. CSS keyframes run at first
   paint with no bundle and no hydration, and the global reduced-motion rule
   collapses their duration instead of leaving anything hidden.
 
   framer-motion is still the right tool below the fold, where reveals need
   viewport detection and the bundle has long since arrived. */

/**
 * The `Illustrative` marker every product mock must carry.
 *
 * CLAUDE.md's content rule is not decoration: the product sells on never
 * inventing a number, and these cards show numbers that were invented for the
 * page. Same wording as `LoopMock`'s frame so the label reads as one convention
 * rather than two.
 *
 * A footnote at the bottom of the page is not sufficient — these cards are
 * screenshot-shaped, and the screenshot travels without the footnote.
 */
function IllustrativeTag() {
  return (
    <span className="ml-auto shrink-0 rounded-md bg-bone-200 px-1.5 py-0.5 font-mono text-2xs uppercase tracking-[0.14em] text-ink-500">
      Illustrative
    </span>
  )
}

/** A product fragment that floats over the illustration — shape, not real data. */
function FloatingBrief() {
  return (
    <div
      style={{ animationDelay: '0.85s' }}
      className="animate-rise-scale absolute -left-2 top-[22%] w-[17.5rem] rounded-2xl border border-bone-300/80 bg-white/90 p-4 shadow-paper-lg backdrop-blur-md sm:-left-8"
    >
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-gold-400 opacity-75 motion-safe:animate-pulse-ring" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-gold-500" />
        </span>
        <span className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-400">
          Morning Brief
        </span>
        <IllustrativeTag />
      </div>
      <p className="mt-2.5 text-[0.92rem] font-medium leading-snug text-ink-800">
        Pipeline value rose while three deals went quiet for 11 days.
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {['CRM', 'GA4'].map((s) => (
          <span
            key={s}
            className="rounded-md bg-bone-100 px-1.5 py-0.5 font-mono text-2xs text-ink-500"
          >
            source: {s}
          </span>
        ))}
      </div>
    </div>
  )
}

function FloatingScore() {
  return (
    <div
      style={{ animationDelay: '1.05s' }}
      className="animate-rise-scale absolute -right-1 bottom-[16%] w-[14.5rem] rounded-2xl border border-bone-300/80 bg-white/90 p-4 shadow-paper-lg backdrop-blur-md sm:-right-6"
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-2xs uppercase tracking-[0.18em] text-ink-400">
          Health Score
        </span>
        <IllustrativeTag />
      </div>
      <div className="mt-1 flex items-baseline justify-end">
        <span className="font-mono text-2xs text-clay-500">+4 wk</span>
      </div>
      <div className="mt-2 flex items-end gap-1.5">
        <span className="font-display text-4xl leading-none text-ink-800">72</span>
        <span className="pb-1 text-xs text-ink-400">/ 100</span>
      </div>
      <div className="mt-3 space-y-1.5">
        {[
          { label: 'Sales', v: 84 },
          { label: 'Marketing', v: 61 },
          { label: 'Finance', v: 77 },
        ].map((d, i) => (
          <div key={d.label} className="flex items-center gap-2">
            <span className="w-16 shrink-0 text-2xs text-ink-500">{d.label}</span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-bone-200">
              <motion.span
                initial={{ width: 0 }}
                animate={{ width: `${d.v}%` }}
                transition={{ duration: 1.1, delay: 1.3 + i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                className="block h-full rounded-full bg-steel-500"
              />
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Hero() {
  const reduced = useReducedMotion()
  const parallax = usePointerParallax(!!reduced)

  return (
    <section id="top" className="relative overflow-hidden pt-32 lg:pt-36">
      {/* Ambient wash — very light, keeps the page white while adding depth. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[46rem] bg-[radial-gradient(60rem_36rem_at_72%_18%,rgba(55,114,156,0.10),transparent_65%),radial-gradient(38rem_26rem_at_12%_8%,rgba(239,191,106,0.14),transparent_70%)]"
      />

      <div className="shell relative">
        <div className="grid items-center gap-14 lg:grid-cols-[1.05fr_1fr] lg:gap-10">
          {/* ── Copy ─────────────────────────────────────────── */}
          <div className="relative z-10 max-w-2xl">
            <div
              className="animate-rise inline-flex items-center gap-2 rounded-full border border-bone-300 bg-white/70 py-1.5 pl-2 pr-4 shadow-paper backdrop-blur"
            >
              <span className="grid h-6 w-6 place-items-center rounded-full bg-gold-200 text-gold-600">
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
                {/* Hand-drawn underline, drawn on after the words land. */}
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
              <RevealWords
                text={hero.headlineBottom}
                delay={0.42}
                wordClassName="text-ink-500"
              />
            </h1>

            <p
              style={{ animationDelay: '0.72s' }}
              className="animate-rise mt-7 max-w-xl text-pretty text-lg leading-relaxed text-ink-500"
            >
              {hero.sub}
            </p>

            {/* `doc/11` Q1 (D18): one action, and it is sign up. This was a URL
                field feeding the unauthenticated Preview audit, which Phase 2
                retired — a stranger could type a competitor's address and be
                handed an analysis of a company they do not own. The website is
                asked for at stage 2 instead, once there is an account to attach
                it to, and the crawl starts there. */}
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
              <IconCheck className="mt-0.5 h-4 w-4 shrink-0 text-steel-500" />
              {hero.note}
            </p>
          </div>

          {/* ── Illustration ─────────────────────────────────── */}
          <div
            style={{ animationDelay: '0.25s' }}
            className="animate-rise-scale relative mx-auto w-full max-w-[34rem] lg:max-w-none"
          >
            <div className="relative">
              <PaperLandscape parallax={parallax} className="w-full drop-shadow-[0_40px_80px_rgba(9,31,70,0.16)]" />
              <FloatingBrief />
              <FloatingScore />
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
