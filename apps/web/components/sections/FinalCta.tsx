'use client'

import { motion } from 'framer-motion'
import { Reveal } from '@/components/motion/Reveal'
import { Button, ArrowRight } from '@/components/ui/Button'
import { finalCta } from '@/lib/content'

/** A wide, calm reprise of the hero landscape — the same horizon, closer in. */
function HorizonStrip() {
  return (
    <svg
      viewBox="0 0 1200 260"
      preserveAspectRatio="none"
      aria-hidden="true"
      className="absolute inset-x-0 bottom-0 h-44 w-full sm:h-56"
    >
      <defs>
        <linearGradient id="ctaSea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#5F94B8" />
          <stop offset="100%" stopColor="#37729C" />
        </linearGradient>
      </defs>
      <path d="M0 118c180-40 320 10 520 32s400 8 680-40v150H0z" fill="#93B8D1" opacity="0.55" />
      <path d="M0 158c200-36 350 14 540 34s420 4 660-34v102H0z" fill="url(#ctaSea)" opacity="0.75" />
      <g stroke="#FFFFFF" fill="none" opacity="0.3" strokeLinecap="round" strokeWidth="1.5">
        <path d="M140 206a26 14 0 0 1 52 0M154 218a18 10 0 0 1 36 0" />
        <path d="M1010 194a26 14 0 0 1 52 0M1024 206a18 10 0 0 1 36 0" />
        <path d="M600 224a22 12 0 0 1 44 0" />
      </g>
      {/* One small boat, still heading somewhere.

          **Two nested groups, and that is the fix rather than the style.** The
          boat used to carry its `transform` attribute and `animate-sway` on the
          same element. A CSS `transform` property *overrides* the SVG
          `transform` presentation attribute outright — it does not compose with
          it — so the moment the sway keyframe applied, `translate(560 168)
          scale(1.1)` was discarded and the boat rendered at the viewBox origin.
          It sat in the top-left corner of the panel, above the waterline,
          visibly sailing through the sky.

          The outer group owns the position and the inner one owns the
          animation, so the CSS transform has nothing to overwrite. */}
      <g transform="translate(560 168) scale(1.1)">
      <g className="motion-safe:animate-sway" style={{ transformOrigin: '20px 32px' }}>
        <path d="M20 4v26" stroke="#84492A" strokeWidth="2" strokeLinecap="round" />
        <path d="M21 6c8 5 11 10 12 17H21z" fill="#F5F2EF" />
        <path d="M19 10c-6 4-8 8-9 13h9z" fill="#E9E4DE" />
        <path d="M4 30h32l-5 8c-.8 1.3-2.2 2-3.7 2H12.7c-1.5 0-2.9-.7-3.7-2z" fill="#A55D35" />
      </g>
      </g>
    </svg>
  )
}

export function FinalCta() {
  return (
    <section id="cta" className="relative scroll-mt-24 px-[var(--shell-x)] pb-section pt-10">
      <Reveal>
        <div className="relative mx-auto max-w-shell overflow-hidden rounded-panel border border-bone-300/70 bg-gradient-to-b from-bone-50 to-white shadow-paper-xl">
          {/* Warm sun wash */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(34rem_20rem_at_50%_-10%,rgba(239,191,106,0.28),transparent_70%)]"
          />

          <div className="relative px-6 pb-56 pt-20 text-center sm:px-12 sm:pb-64 sm:pt-24">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              whileInView={{ scale: 1, opacity: 1 }}
              viewport={{ once: true, amount: 0.5 }}
              transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
              className="mx-auto mb-9 h-16 w-16"
            >
              <svg viewBox="0 0 64 64" className="h-full w-full" aria-hidden="true">
                <circle
                  cx="32"
                  cy="32"
                  r="29"
                  fill="none"
                  stroke="#DFA542"
                  strokeWidth="1.5"
                  strokeDasharray="3 8"
                  className="motion-safe:animate-spin-slow"
                  style={{ transformOrigin: '32px 32px' }}
                />
                <circle cx="32" cy="32" r="20" fill="#EFBF6A" />
                <path d="M22 22a20 20 0 0 1 17 32 20 20 0 1 0-17-32z" fill="#FFFFFF" opacity="0.25" />
              </svg>
            </motion.div>

            <h2 className="mx-auto max-w-3xl text-headline text-balance">{finalCta.headline}</h2>
            <p className="mx-auto mt-6 max-w-xl text-pretty text-lg text-ink-500">
              {finalCta.sub}
            </p>

            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button href="/register" size="lg" icon={<ArrowRight />}>
                {finalCta.primary}
              </Button>
              <Button href="#loop" size="lg" variant="secondary">
                {finalCta.secondary}
              </Button>
            </div>

            <p className="mt-6 font-mono text-2xs uppercase tracking-[0.16em] text-ink-400">
              {finalCta.reassure}
            </p>
          </div>

          <HorizonStrip />
        </div>
      </Reveal>
    </section>
  )
}
