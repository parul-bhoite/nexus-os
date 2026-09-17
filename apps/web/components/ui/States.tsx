'use client'

import type { ReactNode } from 'react'
import { Button } from '@/components/ui/Button'

/**
 * Empty, error and success states — the three the audit found either missing or
 * dead-ended.
 *
 * ## Empty states must carry the action that fills them
 *
 * The dashboard's first card read "No audit has run yet — no page has been
 * fetched for this workspace… The audit runs once a website is added and
 * crawled." Every word of that is true and useful, and there was **no way to
 * add a website from it**. An empty state that names its own precondition and
 * then does not offer it makes the reader go and look for the setting, which is
 * the one thing the empty state existed to prevent.
 *
 * So `Empty` takes an `action` and it is not optional by accident: a state with
 * genuinely nothing to do passes `action={null}` explicitly, which is a
 * decision rather than an omission.
 *
 * ## Error states must offer a retry
 *
 * The Company Brain panel ended the dashboard with "Could not load what NEXUS
 * is working from. Nothing above is affected — this panel reads from a separate
 * place, and it is the reading that failed rather than the brain." The copy is
 * excellent: it says what failed, what is unaffected, and where the boundary
 * is. It had no button. A reader who wants to try again has to reload a page
 * that takes sixteen seconds and refetches twenty-five other things.
 *
 * `Failed` therefore requires `onRetry` *or* an explicit `retry={null}` for the
 * cases where retrying cannot help.
 *
 * ## The illustration is a glyph, not a picture
 *
 * The brief warns against large unnecessary illustrations, and an empty state
 * is where they breed. These draw one 40px mark in a tinted tile — enough to
 * make the state feel designed rather than broken, small enough that it never
 * competes with the sentence or the button.
 */

function Frame({
  tone,
  glyph,
  title,
  children,
  actions,
  className = '',
}: {
  tone: 'quiet' | 'warn' | 'good'
  glyph: ReactNode
  title: ReactNode
  children?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  const tile =
    tone === 'warn'
      ? 'bg-clay-100 text-clay-600'
      : tone === 'good'
        ? 'bg-steel-100 text-steel-700'
        : 'bg-bone-200 text-ink-500'

  return (
    <div
      className={`flex flex-col items-start gap-4 rounded-data border border-ink-100 bg-white px-6 py-7 ${className}`}
    >
      <span className={`flex h-10 w-10 items-center justify-center rounded-control ${tile}`}>
        {glyph}
      </span>
      <div className="flex flex-col gap-1.5">
        <h3 className="text-card font-medium text-ink-800">{title}</h3>
        {children ? (
          <div className="max-w-read text-body leading-relaxed text-ink-600">{children}</div>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

const glyphs = {
  empty: (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
      <rect x="2.75" y="4.75" width="14.5" height="11.5" rx="2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M2.75 9.25h14.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M7 13h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
    </svg>
  ),
  failed: (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
      <path
        d="M10 2.75 17.75 16.5H2.25L10 2.75Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M10 7.75v3.5M10 14.1v.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  done: (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
      <circle cx="10" cy="10" r="7.25" stroke="currentColor" strokeWidth="1.4" />
      <path
        d="m6.75 10.25 2.25 2.25 4.25-4.75"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
}

/**
 * Nothing here yet, and the one thing that would change that.
 *
 * `action` is required — pass `null` to state, on purpose, that there is
 * nothing the reader can do. `secondary` is for "learn what this is".
 */
export function Empty({
  title,
  children,
  action,
  secondary,
  className,
}: {
  title: ReactNode
  children?: ReactNode
  action: { label: string; href?: string; onClick?: () => void } | null
  secondary?: { label: string; href?: string; onClick?: () => void }
  className?: string
}) {
  return (
    <Frame
      tone="quiet"
      glyph={glyphs.empty}
      title={title}
      actions={
        action || secondary ? (
          <>
            {action ? (
              <Button size="sm" href={action.href} onClick={action.onClick}>
                {action.label}
              </Button>
            ) : null}
            {secondary ? (
              <Button size="sm" variant="ghost" href={secondary.href} onClick={secondary.onClick}>
                {secondary.label}
              </Button>
            ) : null}
          </>
        ) : null
      }
      className={className}
    >
      {children}
    </Frame>
  )
}

/**
 * Something failed, and what to do about it.
 *
 * The `detail` is shown verbatim and is expected to be the server's own
 * sentence — this codebase already insists that wording lives in one place so a
 * change reaches every surface, and an error is no exception. What is added
 * here is the control.
 */
export function Failed({
  title = 'That did not load',
  children,
  retry,
  retryLabel = 'Try again',
  busy = false,
  secondary,
  className,
}: {
  title?: ReactNode
  children?: ReactNode
  /** `null` when trying again genuinely cannot help. */
  retry: (() => void) | null
  retryLabel?: string
  busy?: boolean
  secondary?: { label: string; href?: string }
  className?: string
}) {
  return (
    <Frame
      tone="warn"
      glyph={glyphs.failed}
      title={title}
      actions={
        retry || secondary ? (
          <>
            {retry ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={retry}
                loading={busy}
                loadingLabel="Trying again…"
              >
                {retryLabel}
              </Button>
            ) : null}
            {secondary ? (
              <Button size="sm" variant="ghost" href={secondary.href}>
                {secondary.label}
              </Button>
            ) : null}
          </>
        ) : null
      }
      className={className}
    >
      {children}
    </Frame>
  )
}

/** A finished, successful state that stays on screen — not a toast. */
export function Done({
  title,
  children,
  action,
  className,
}: {
  title: ReactNode
  children?: ReactNode
  action?: { label: string; href?: string; onClick?: () => void }
  className?: string
}) {
  return (
    <Frame
      tone="good"
      glyph={glyphs.done}
      title={title}
      actions={
        action ? (
          <Button size="sm" href={action.href} onClick={action.onClick}>
            {action.label}
          </Button>
        ) : null
      }
      className={className}
    >
      {children}
    </Frame>
  )
}
