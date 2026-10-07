import Link from 'next/link'
import type { ReactNode } from 'react'
import { Logo } from '@/components/ui/Logo'
import { IconCheck } from '@/components/art/Icons'

/**
 * The frame around every auth page (ADR 0072).
 *
 * A single framed "slide" floating on a soft grey ground: the form on the left,
 * and on the right a dark branded panel whose left edge is an organic S-curve the
 * white form column flows into. The right panel carries the product's thesis and
 * its grounding promise rather than decorative scenery — it is `aria-hidden` and
 * drops away below `lg`, where a form has better uses for the space and the task
 * lives entirely in the form.
 *
 * The curve is one objectBoundingBox clip-path, so it scales with the panel at
 * any height without re-measuring.
 */

const PROOF = [
  { title: 'Fetched or computed', body: 'Never guessed by a language model.' },
  { title: 'Cited to its source', body: 'Every figure names where it came from.' },
  { title: 'Auditable forever', body: 'Any card can show its working.' },
] as const

export function AuthShell({
  title,
  intro,
  children,
  footer,
}: {
  title: string
  intro: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <main
      id="main"
      tabIndex={-1}
      className="flex min-h-screen justify-center bg-bone-100 lg:items-center lg:p-8"
    >
      {/* The clip-path lives once, here; the right panel references it. */}
      <svg aria-hidden="true" className="absolute h-0 w-0">
        <defs>
          <clipPath id="authCurve" clipPathUnits="objectBoundingBox">
            <path d="M0.14,0 C0.03,0.24 0.18,0.46 0.1,0.66 C0.03,0.82 0.14,0.93 0.12,1 L1,1 L1,0 Z" />
          </clipPath>
        </defs>
      </svg>

      <div className="relative w-full overflow-hidden bg-white shadow-e3 lg:max-w-6xl lg:rounded-[2rem]">
        {/* ── The brand panel — organic curve, value thesis, grounding proof ── */}
        <div
          aria-hidden="true"
          className="absolute inset-y-0 right-0 hidden w-[58%] overflow-hidden bg-ink-950 lg:block"
          style={{ clipPath: 'url(#authCurve)' }}
        >
          {/* The brand X, ghosted large and bled off the top-right corner. */}
          <svg
            viewBox="0 0 100 100"
            aria-hidden="true"
            className="pointer-events-none absolute -right-20 -top-24 h-[34rem] w-[34rem]"
            fill="none"
          >
            <line x1="26" y1="26" x2="74" y2="74" className="stroke-white/[0.05]" strokeWidth="11" strokeLinecap="round" />
            <line x1="26" y1="74" x2="50" y2="50" className="stroke-white/[0.05]" strokeWidth="11" strokeLinecap="round" />
            <line x1="50" y1="50" x2="74" y2="26" className="stroke-gold-500/30" strokeWidth="11" strokeLinecap="round" />
          </svg>

          <div className="relative flex h-full flex-col justify-center py-16 pl-28 pr-14 xl:pl-32">
            <span className="flex items-center gap-2 font-mono text-2xs uppercase tracking-[0.2em] text-slate-300">
              <span className="h-1.5 w-1.5 rounded-full bg-gold-500" />
              AI business operating system
            </span>

            <p className="mt-6 max-w-sm text-balance font-display text-[1.9rem] font-bold leading-[1.15] text-bone-50">
              One Company Brain. Every number traceable to a real source.
            </p>

            <div className="my-9 h-px w-12 bg-white/15" />

            <ul className="space-y-5">
              {PROOF.map((p) => (
                <li key={p.title} className="flex items-start gap-3.5">
                  <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gold-500 text-ink-950">
                    <IconCheck className="h-4 w-4" />
                  </span>
                  <div>
                    <span className="block text-[0.95rem] font-medium text-bone-50">{p.title}</span>
                    <span className="mt-0.5 block text-meta leading-relaxed text-slate-400">
                      {p.body}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* A small corner label. */}
          <span className="absolute bottom-7 right-9 font-mono text-2xs uppercase tracking-[0.22em] text-slate-500">
            NEXUS · built on grounded data
          </span>
        </div>

        {/* ── The form ── */}
        <div className="relative z-10 flex min-h-screen flex-col px-6 py-10 sm:px-10 lg:min-h-[46rem] lg:w-[48%] lg:px-14 lg:py-12">
          <Link
            href="/"
            className="inline-flex w-fit rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 focus-visible:ring-offset-4 focus-visible:ring-offset-white"
            aria-label="NEXUS home"
          >
            <Logo />
          </Link>

          <div className="flex w-full max-w-md flex-1 flex-col justify-center py-10">
            <h1 className="font-display text-page font-bold tracking-tight text-ink-950">
              {title}
              <span className="text-gold-500">.</span>
            </h1>

            {/* The accent dots — amber spark, then two neutral steps. */}
            <div className="mt-5 flex items-center gap-2" aria-hidden="true">
              <span className="h-2 w-2 rounded-full bg-gold-500" />
              <span className="h-2 w-2 rounded-full bg-ink-300" />
              <span className="h-2 w-2 rounded-full bg-ink-200" />
            </div>

            <p className="mt-6 max-w-sm text-body leading-relaxed text-ink-500">{intro}</p>
            <div className="mt-8">{children}</div>
          </div>

          {footer ? <div className="w-full max-w-md text-meta text-ink-500">{footer}</div> : null}
        </div>
      </div>
    </main>
  )
}
