import Link from 'next/link'
import type { ReactNode } from 'react'
import { Logo } from '@/components/ui/Logo'
import { PaperLandscape } from '@/components/art/PaperLandscape'
import { IconSparkle } from '@/components/art/Icons'

/**
 * The frame around every auth page (ADR 0072).
 *
 * A single framed "slide" floating on a soft grey ground: the form on the left,
 * and on the right an image panel whose left edge is an organic S-curve that the
 * white form column flows into, with a floating glass card over it. The image is
 * the landing page's own grayscale artwork rather than stock, so signing in does
 * not feel like leaving the product — it is `aria-hidden` and drops away below
 * `lg`, where a form has better uses for the space.
 *
 * The curve is one objectBoundingBox clip-path, so it scales with the panel at
 * any height without re-measuring.
 */
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
      {/* The clip-path lives once, here; the image panel references it. */}
      <svg aria-hidden="true" className="absolute h-0 w-0">
        <defs>
          <clipPath id="authCurve" clipPathUnits="objectBoundingBox">
            <path d="M0.18,0 C0.02,0.26 0.28,0.46 0.14,0.66 C0.05,0.82 0.2,0.92 0.16,1 L1,1 L1,0 Z" />
          </clipPath>
        </defs>
      </svg>

      <div className="relative w-full overflow-hidden bg-white shadow-e3 lg:max-w-6xl lg:rounded-[2rem]">
        {/* ── The image panel — organic curve, grayscale artwork, floating card ── */}
        <div
          aria-hidden="true"
          className="absolute inset-y-0 right-0 hidden w-[58%] bg-ink-950 lg:block"
          style={{ clipPath: 'url(#authCurve)' }}
        >
          <PaperLandscape className="absolute inset-0 h-full w-full" />
          {/* A faint wash to seat the floating card and the corner label. */}
          <div className="absolute inset-0 bg-gradient-to-t from-ink-950/35 via-transparent to-transparent" />
        </div>

        {/* The floating glass card — a sibling of the clipped panel, so it is not
            clipped. Mirrors the reference card: an accent chip, a title, a line.
            Real content, per the product's own rule. */}
        <div className="pointer-events-none absolute bottom-[16%] left-[44%] z-20 hidden w-72 lg:block">
          <div className="rounded-2xl border border-white/70 bg-white/85 p-5 shadow-e2 backdrop-blur-md">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gold-500 text-white shadow-e1">
              <IconSparkle className="h-4 w-4" />
            </span>
            <h2 className="mt-3.5 font-display text-card font-semibold text-ink-900">
              Never invent a number
            </h2>
            <p className="mt-1 text-meta leading-relaxed text-ink-500">
              Every figure is fetched or computed — and cites where it came from.
            </p>
          </div>
        </div>

        {/* A small corner label, echoing the reference's slide caption. */}
        <span className="absolute bottom-7 right-9 z-20 hidden font-mono text-2xs uppercase tracking-[0.22em] text-slate-300 lg:block">
          NEXUS · built on grounded data
        </span>

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
