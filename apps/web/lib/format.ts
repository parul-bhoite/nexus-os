/**
 * Formatting — money and dates — in one place.
 *
 * Closes F-06/F-07/F-20/F-21 at the source rather than at each call site:
 *
 * - **An implicit `Intl` locale is an SSR/hydration bug, not a convenience.**
 *   `new Intl.NumberFormat(undefined, …)` reads the runtime's own locale,
 *   which differs between the server (the container's) and the browser (the
 *   visitor's) — and React tears the subtree down the moment the first
 *   client render disagrees with what the server sent. Every formatter here
 *   takes an explicit locale, defaulting to `LOCALE`, never `undefined`.
 * - **A date-only ISO string must never round-trip through `Date`.**
 *   `new Date('2026-09-17')` parses as UTC midnight; formatting that in a
 *   browser west of Greenwich prints the sixteenth. `formatDate` detects the
 *   date-only shape and reads the three numbers directly, with nothing to
 *   convert.
 * - **Nothing here prints the literal string "Invalid Date".** Every
 *   formatter returns `''` for input it cannot parse, so a caller renders
 *   nothing rather than a sentence that reads as a second bug.
 */

/** The one locale every formatter in this app uses. Explicit, never
 *  `undefined` — see the file note above for why that distinction matters. */
export const LOCALE = 'en-GB'

/**
 * Money, from minor units, in the currency the caller supplies.
 *
 * `currency` is never assumed. It is always the workspace's own reporting
 * currency or a figure's own `currency` field, sourced from the API — never a
 * hardcoded guess (F-06's defect was exactly that guess).
 */
export function formatCurrency(
  minorUnits: number,
  currency: string,
  locale: string = LOCALE,
  maximumFractionDigits = 2,
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    maximumFractionDigits,
  }).format(minorUnits / 100)
}

/**
 * A date, from an ISO string that is either date-only (`2026-09-17`) or a
 * full timestamp.
 *
 * The date-only case is read directly out of the string — never through
 * `Date`, which would parse it as UTC midnight and print the wrong day
 * everywhere west of Greenwich. A full timestamp genuinely names one instant,
 * so converting it to the reader's own timezone is correct and is what the
 * second branch does.
 *
 * Returns `''` for `''`, for a date-only string with an impossible month or
 * day, and for anything `Date` cannot parse — so a caller never renders the
 * literal string "Invalid Date" (F-20's other half).
 */
export function formatDate(iso: string, locale: string = LOCALE): string {
  if (!iso) return ''

  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (dateOnly) {
    const year = Number(dateOnly[1])
    const month = Number(dateOnly[2])
    const day = Number(dateOnly[3])
    if (month < 1 || month > 12 || day < 1 || day > 31) return ''
    // Noon UTC, not midnight: a `dateStyle` formatter asked to render in UTC
    // reads back exactly the numbers just given it, with no boundary a
    // half-day's slack cannot protect against.
    const instant = new Date(Date.UTC(year, month - 1, day, 12))
    return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(
      instant,
    )
  }

  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return ''
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(parsed)
}

/**
 * A full timestamp, date and time, in the reader's own timezone.
 *
 * Unlike `formatDate`, there is no date-only branch — a caller reaching for
 * the time as well as the date always has a real instant to convert.
 */
export function formatDateTime(iso: string, locale: string = LOCALE): string {
  if (!iso) return ''
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return ''
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
    parsed,
  )
}
