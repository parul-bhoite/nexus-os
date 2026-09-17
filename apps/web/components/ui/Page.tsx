import Link from 'next/link'
import type { ReactNode } from 'react'

/**
 * A page's heading, and the rhythm every product page hangs off.
 *
 * ## The hierarchy this repairs
 *
 * On `/dashboard` the page title was `text-title` (up to 30px) and so was every
 * section heading beneath it. A reader scanning the page met five headings of
 * the same weight and could not tell which one named the page. Worse, the first
 * two were stacked: "Today / What needs you, and where each number came from."
 * immediately followed by "Morning brief / What was found, ranked by what it
 * cost." — two titles and two subtitles, 240px of a phone screen, before any
 * content at all.
 *
 * So there is now one `h1` per page at `text-page`, one optional sentence, and
 * `Section` for everything below it at a visibly smaller step. The type scale
 * does the work; no page decides its own sizes.
 *
 * ## Breadcrumbs
 *
 * Only where the page is genuinely nested — a director page under Today. The
 * product is two levels deep, so a crumb trail on every page would be
 * decoration. Where it does appear it is a real `nav` with `aria-label`, and
 * the current page is the last item and is not a link.
 */

export function PageHeader({
  title,
  lede,
  crumb,
  actions,
  className = '',
}: {
  title: ReactNode
  /** One sentence. If it needs two, it belongs in the content. */
  lede?: ReactNode
  crumb?: { href: string; label: string }
  actions?: ReactNode
  className?: string
}) {
  return (
    <header className={`flex flex-col gap-3 ${className}`}>
      {crumb ? (
        <nav aria-label="Breadcrumb">
          <Link
            href={crumb.href}
            className="group inline-flex items-center gap-1.5 text-meta text-ink-500 transition-colors duration-micro ease-out hover:text-ink-800"
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="h-3.5 w-3.5 transition-transform duration-base ease-out group-hover:-translate-x-0.5">
              <path d="M10 3.5 5.5 8l4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {crumb.label}
          </Link>
        </nav>
      ) : null}

      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-page text-ink-900">{title}</h1>
          {lede ? (
            <p className="mt-2 max-w-prose text-body leading-relaxed text-ink-500">{lede}</p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  )
}

/**
 * A band of a page. One heading, optionally a sentence and a control, then the
 * content.
 *
 * `gap-stack` between sections rather than a margin on each: a gap belongs to
 * the container, so two adjacent sections cannot disagree about the distance
 * between them, and the last one cannot leave a trailing margin. The audit
 * found ~470px of dead space under the landing page's "Three moments" from
 * exactly that — a section padding that had nothing to push against.
 */
export function Section({
  title,
  lede,
  action,
  children,
  id,
  className = '',
}: {
  title?: ReactNode
  lede?: ReactNode
  action?: ReactNode
  children: ReactNode
  id?: string
  className?: string
}) {
  return (
    <section id={id} className={`flex flex-col gap-4 ${className}`}>
      {title || action ? (
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            {title ? <h2 className="text-section text-ink-900">{title}</h2> : null}
            {lede ? (
              <p className="mt-1 max-w-prose text-meta leading-relaxed text-ink-500">{lede}</p>
            ) : null}
          </div>
          {action ? <div className="shrink-0">{action}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}

/** The vertical rhythm of a page's sections. Used once, by the page. */
export function PageBody({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={`flex flex-col gap-stack ${className}`}>{children}</div>
}
