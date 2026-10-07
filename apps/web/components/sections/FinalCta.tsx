'use client'

import { Reveal } from '@/components/motion/Reveal'
import { Button, ArrowRight } from '@/components/ui/Button'
import { finalCta } from '@/lib/content'

/**
 * The closing CTA. Redesigned to the monochrome editorial system (ADR 0072):
 * the cut-paper sun, horizon and boat are gone. What carries the panel now is a
 * large ghosted X watermark, a bold headline, and the amber spark used once — on
 * the underline beneath the verb.
 */
export function FinalCta() {
  return (
    <section id="cta" className="relative scroll-mt-24 px-[var(--shell-x)] pb-section pt-10">
      <Reveal>
        <div className="relative mx-auto max-w-shell overflow-hidden rounded-panel border border-ink-100 bg-ink-950 shadow-e3">
          {/* The brand X, ghosted large and bled off the right edge. */}
          <svg
            viewBox="0 0 100 100"
            aria-hidden="true"
            className="pointer-events-none absolute -right-16 -top-20 h-[34rem] w-[34rem]"
            fill="none"
          >
            <line x1="26" y1="26" x2="74" y2="74" className="stroke-white/[0.05]" strokeWidth="11" strokeLinecap="round" />
            <line x1="26" y1="74" x2="50" y2="50" className="stroke-white/[0.05]" strokeWidth="11" strokeLinecap="round" />
            <line x1="50" y1="50" x2="74" y2="26" className="stroke-gold-500/25" strokeWidth="11" strokeLinecap="round" />
          </svg>

          <div className="relative px-6 py-24 text-center sm:px-12 sm:py-28">
            <span className="font-mono text-2xs uppercase tracking-[0.2em] text-slate-400">
              Ten minutes to a Company Brain
            </span>

            <h2 className="mx-auto mt-6 max-w-3xl text-balance font-display text-headline font-extrabold text-bone-50">
              {finalCta.headline}
            </h2>
            <p className="mx-auto mt-6 max-w-xl text-pretty text-lg leading-relaxed text-slate-300">
              {finalCta.sub}
            </p>

            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button href="/register" size="lg" variant="onDark" icon={<ArrowRight />}>
                {finalCta.primary}
              </Button>
              <Button href="#loop" size="lg" variant="ghost" className="text-bone-50 hover:bg-white/10">
                {finalCta.secondary}
              </Button>
            </div>

            <p className="mt-7 font-mono text-2xs uppercase tracking-[0.16em] text-slate-400">
              {finalCta.reassure}
            </p>
          </div>
        </div>
      </Reveal>
    </section>
  )
}
