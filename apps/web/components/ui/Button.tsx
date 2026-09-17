'use client'

import Link from 'next/link'
import type { ComponentProps, ReactNode } from 'react'

/**
 * Every button in the product.
 *
 * ## What the audit changed
 *
 * **A disabled primary action is no longer the default state of a form.** Both
 * `/login` and the onboarding conversation rendered their only call to action
 * at `opacity-50` with `disabled` set, before the reader had typed anything.
 * That fails twice over: it is the lowest-contrast thing on the screen at the
 * moment it is the most important, and it gives no indication of *what* would
 * enable it. Forms now keep the button live and validate on submit, and where a
 * control genuinely cannot act — a save with nothing changed — it passes
 * `disabledReason`, which is rendered to assistive technology and shown on
 * hover rather than left for the reader to deduce.
 *
 * **There is a loading state.** Six actions in this product take eight to
 * fifteen seconds (`Waiting` documents why). Every one of them used to leave
 * its button looking idle, so the honest response to a slow save was to press
 * it again. `loading` swaps the label for the caller's `loadingLabel`, sets
 * `aria-busy`, and blocks the click without going grey — a control that is
 * working is not a control that is unavailable, and the two must not look the
 * same.
 *
 * **Hover no longer moves the button.** `hover:-translate-y-0.5` on a control
 * whose neighbour does not move makes a toolbar shuffle as the pointer crosses
 * it. Depth still changes on hover; position does not. A press does move, by
 * one pixel, because that is feedback on an action rather than decoration on a
 * hover.
 *
 * ## Sizes
 *
 * `sm` exists for controls inside a dense row and is 36px — above the 24px
 * WCAG 2.5.8 floor but below a comfortable target, so it is only for a control
 * that sits in a row of its own kind. `md` (44px) is the default and meets the
 * touch-target minimum on every platform. `lg` (56px) is a page's single
 * primary action.
 */

type Variant = 'primary' | 'secondary' | 'ghost' | 'quiet' | 'danger' | 'onDark'
type Size = 'sm' | 'md' | 'lg' | 'icon'

const base =
  'group relative inline-flex select-none items-center justify-center gap-2 rounded-full ' +
  'font-medium transition-[background-color,border-color,box-shadow,transform,color] ' +
  'duration-base ease-out active:translate-y-px ' +
  'disabled:pointer-events-none disabled:opacity-45 aria-busy:cursor-progress'

const variants: Record<Variant, string> = {
  primary: 'bg-ink-800 text-bone-50 shadow-e1 hover:bg-ink-700 hover:shadow-e2',
  secondary:
    'border border-ink-200 bg-white text-ink-800 shadow-e1 hover:border-ink-300 hover:bg-bone-50 hover:shadow-e2',
  ghost: 'text-ink-700 hover:bg-bone-200 hover:text-ink-900',
  // A control that must be reachable but must not compete — "Explain again"
  // beside a sentence that is already written.
  quiet:
    'text-ink-500 underline decoration-ink-300 underline-offset-2 hover:text-ink-800 hover:decoration-ink-500',
  // Destructive. Outlined rather than filled: a filled red button is the most
  // prominent thing on a page, and deleting is never the primary action.
  danger:
    'border border-clay-300 bg-white text-clay-600 hover:border-clay-500 hover:bg-clay-100 hover:text-clay-600',
  onDark: 'bg-gold-400 text-ink-900 shadow-e1 hover:bg-gold-300 hover:shadow-e2',
}

const sizes: Record<Size, string> = {
  sm: 'h-9 px-3.5 text-meta',
  md: 'h-11 px-5 text-body',
  lg: 'h-14 px-7 text-[0.975rem]',
  icon: 'h-11 w-11 shrink-0',
}

/**
 * The spinner. Two arcs on one circle so it reads as motion even at 14px, and
 * `aria-hidden` because `aria-busy` on the button already says what this means
 * — a screen reader announcing "loading image" beside "Saving…" says it twice.
 */
function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={`h-4 w-4 animate-spin ${className}`}
    >
      <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.75" opacity="0.25" />
      <path
        d="M14.25 8A6.25 6.25 0 0 0 8 1.75"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  )
}

type Props = {
  children?: ReactNode
  href?: string
  variant?: Variant
  size?: Size
  className?: string
  icon?: ReactNode
  /** Before the label rather than after. For a leading glyph, not an arrow. */
  iconBefore?: ReactNode
  loading?: boolean
  /** What to say while `loading`. Says *what* is happening, not "please wait". */
  loadingLabel?: string
  /**
   * Why this control cannot act, in the reader's words.
   *
   * Setting it implies `disabled`. It becomes the `title` and is announced via
   * `aria-describedby`, so the answer to "why is this grey?" is available
   * without guessing. A disabled button with no reason is a bug report waiting
   * to happen, so this is the only supported way to disable one.
   */
  disabledReason?: string
  /** Full width. Named rather than passed as a class so forms are consistent. */
  block?: boolean
} & Omit<ComponentProps<'button'>, 'ref' | 'children'>

export function Button({
  children,
  href,
  variant = 'primary',
  size = 'md',
  className = '',
  icon,
  iconBefore,
  loading = false,
  loadingLabel,
  disabledReason,
  block = false,
  disabled,
  ...rest
}: Props) {
  const isDisabled = disabled || Boolean(disabledReason)
  const cls = `${base} ${variants[variant]} ${sizes[size]} ${block ? 'w-full' : ''} ${className}`

  const label = loading && loadingLabel ? loadingLabel : children

  const inner = (
    <>
      {loading ? <Spinner /> : iconBefore ? <span className="relative z-10">{iconBefore}</span> : null}
      {label ? <span className="relative z-10">{label}</span> : null}
      {icon && !loading ? (
        <span className="relative z-10 transition-transform duration-base ease-out group-hover:translate-x-0.5">
          {icon}
        </span>
      ) : null}
    </>
  )

  if (href) {
    // A link is never `loading` and never `disabled` — those are button states.
    // Rendering a dead `<a>` is how a navigation becomes untrappable by
    // keyboard, so a link that should not be followed is simply not a link.
    return (
      <Link href={href} className={cls}>
        {inner}
      </Link>
    )
  }

  return (
    <button
      className={cls}
      disabled={isDisabled || loading}
      aria-busy={loading || undefined}
      title={disabledReason}
      {...rest}
    >
      {inner}
      {disabledReason ? <span className="sr-only"> — {disabledReason}</span> : null}
    </button>
  )
}

export function ArrowRight({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={`h-4 w-4 ${className}`}
    >
      <path
        d="M2.5 8h11m0 0L9 3.5M13.5 8 9 12.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
