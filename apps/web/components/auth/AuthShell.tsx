import Link from 'next/link'
import type { ReactNode } from 'react'
import { Logo } from '@/components/ui/Logo'
import { PaperLandscape } from '@/components/art/PaperLandscape'

/**
 * The frame around every auth page.
 *
 * Two columns on desktop: the form on the left, the paper-cut landscape on the
 * right. The landscape is the landing page's own artwork rather than a stock
 * illustration, so signing in does not feel like leaving the product — but it is
 * `aria-hidden` and drops away entirely below `lg`, where a form has better uses
 * for the space.
 *
 * ## The artwork reaches the edge of the glass
 *
 * It did not. The grid was `max-w-6xl mx-auto`, so at 1440 the whole two-column
 * layout was 1152px wide and centred — which left a 144px strip of bone
 * page-background to the right of a full-bleed navy artwork panel. A dark panel
 * that stops 144px short of the window reads as a layout that failed to finish
 * loading, and it was the first thing anybody saw on the sign-in page.
 *
 * The grid is now full width. The *form* is what stays measured: its column
 * centres a `max-w-md` block, so the reading column is unchanged and only the
 * artwork gained the space it should always have had.
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
    <main className="min-h-screen bg-bone-50">
      <div className="grid min-h-screen w-full grid-cols-1 lg:grid-cols-2">
        {/* ── The form ── */}
        <div className="flex flex-col items-center px-6 py-8 sm:px-10 lg:py-12">
          <div className="w-full max-w-md">
            <Link
              href="/"
              className="inline-flex w-fit rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-4 focus-visible:ring-offset-bone-50"
              aria-label="NEXUS OS home"
            >
              <Logo />
            </Link>
          </div>

          {/* `justify-center` with a bounded gap rather than `py-10`: the form
              was pinned to the vertical centre of the column while the logo sat
              at the top, which on a 900px window left ~180px of nothing between
              them and put the heading below the midpoint. */}
          <div className="flex w-full max-w-md flex-1 flex-col justify-center py-8">
            <h1 className="text-page text-ink-900">{title}</h1>
            <p className="mt-3 text-body leading-relaxed text-ink-600">{intro}</p>
            <div className="mt-7">{children}</div>
          </div>

          {footer ? <div className="w-full max-w-md text-meta text-ink-500">{footer}</div> : null}
        </div>

        {/* ── The artwork ──
            A column, not a stack. The caption used to be absolutely positioned
            over the illustration, which worked while the grid was 1152px wide
            and the SVG letterboxed well short of the bottom. Giving the column
            the full half of a 1440px window made the artwork taller than its
            own scrim, and the promise — the one line on this page that states
            what the product is for — printed across a boat.

            The artwork now takes the space that is left after the caption has
            had what it needs, so the two cannot collide at any height. */}
        <div className="hidden flex-col overflow-hidden bg-ink-900 lg:flex" aria-hidden="true">
          {/* No `object-cover`: it has no effect on inline SVG. The viewBox
              letterboxes against `bg-ink-900`, which is the artwork's own
              ground, so the fit is invisible. */}
          <div className="relative min-h-0 flex-1">
            <PaperLandscape className="absolute inset-0 h-full w-full" />
          </div>
          <div className="shrink-0 px-10 pb-10 pt-8">
            <p className="max-w-sm font-display text-xl leading-snug text-bone-50">
              Every number NEXUS shows you is fetched or computed. None of them are
              generated.
            </p>
            <p className="mt-3 text-2xs uppercase tracking-[0.14em] text-slate-300">
              The rule the product is built on
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
