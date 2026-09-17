'use client'

import type { ReactNode } from 'react'

/**
 * The pieces a number is made of: the figure itself, the badge beside it, the
 * dot that says what state it is in, and the table it sometimes sits in.
 *
 * ## The inversion this fixes
 *
 * On every block card the audit measured, the figure occupied one line and the
 * apparatus around it fifteen. A reader scanning the dashboard for "what
 * changed" met a wall of methodology with a `1` somewhere inside it. The
 * product's promise is that every number is traceable — not that every number
 * is *preceded* by its trace.
 *
 * `Figure` therefore makes the number the largest thing in its card by a clear
 * margin and puts the unit and the qualifier beside it at reading size. What it
 * measures, what it excluded and where it came from move behind `Disclosure`.
 * Nothing is deleted; the order is reversed.
 *
 * ## Why the state badge became a dot
 *
 * Twelve cards each carried a `LIVE` pill. A badge that is on everything marks
 * nothing, and it was the highest-contrast element on a card whose point is a
 * number. `StateDot` renders 6px of colour with the state as its accessible
 * name, and — the part that matters — **`live` renders nothing at all**. The
 * normal state is the absence of a marker, so the four cards that need
 * attention are the only four wearing one.
 */

/**
 * A figure, at the size a figure deserves.
 *
 * `value` is pre-formatted by the caller — currency and percentages are
 * formatted once, centrally, because two call sites rounding differently is
 * exactly the class of defect this product refuses.
 */
export function Figure({
  value,
  unit,
  qualifier,
  size = 'lg',
  tone = 'ink',
}: {
  value: ReactNode
  /** What the number is in — "points", "deals", "/ 65". Beside, never below. */
  unit?: ReactNode
  /** One short clause. Anything longer belongs in the working. */
  qualifier?: ReactNode
  size?: 'lg' | 'sm'
  tone?: 'ink' | 'muted'
}) {
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span
        className={`tnum font-display leading-none ${
          size === 'lg' ? 'text-figure' : 'text-figure-sm'
        } ${tone === 'muted' ? 'text-ink-400' : 'text-ink-900'}`}
      >
        {value}
      </span>
      {unit ? <span className="text-body text-ink-500">{unit}</span> : null}
      {qualifier ? <span className="text-meta text-ink-500">{qualifier}</span> : null}
    </p>
  )
}

/**
 * A figure that does not exist, said as an absence rather than drawn as a zero.
 *
 * Invariant I10: a number we do not have must never render as `0`. An em dash
 * at figure size holds the same space the number would, so a grid of cards does
 * not go ragged where one of them has nothing to show.
 */
export function NoFigure({ because }: { because: ReactNode }) {
  return (
    // `items-baseline` with `flex-wrap` put the dash alone on the first line
    // whenever the reason ran past one line — which it usually does, because a
    // refusal is a sentence explaining what would make the figure computable.
    // The dash is a fixed-width marker and the reason is a block beside it.
    <p className="flex items-baseline gap-2.5">
      <span
        aria-hidden="true"
        className="shrink-0 font-display text-figure leading-none text-ink-200"
      >
        —
      </span>
      <span className="min-w-0 flex-1 text-meta leading-relaxed text-ink-600">{because}</span>
    </p>
  )
}

const DOT_TONES = {
  attention: 'bg-gold-500',
  warn: 'bg-clay-500',
  quiet: 'bg-ink-200',
  good: 'bg-steel-500',
} as const

/**
 * A state marker. Six pixels, and no *visible* mark when the state is the
 * normal one.
 *
 * The label is always rendered, because removing the dot must not remove the
 * information. `tone: 'none'` drops the colour and keeps an `sr-only` label, so
 * a screen reader still hears "Live" on a tile that draws nothing — which is
 * what `BlockCard`'s state test is actually asserting, and it is right to: the
 * visual language may say "normal is unmarked", but a reader who cannot see the
 * absence of a dot still needs to be told.
 *
 * The label is also the `title` and the accessible name, so the colour is never
 * the only carrier of the meaning — a dot that is only a colour fails for the
 * reader who cannot distinguish gold from clay, which is the pair this palette
 * happens to make hardest.
 */
export function StateDot({
  tone,
  label,
}: {
  tone: keyof typeof DOT_TONES | 'none'
  label: string
}) {
  if (tone === 'none') return <span className="sr-only">{label}</span>
  return (
    <span
      title={label}
      className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${DOT_TONES[tone]}`}
    >
      <span className="sr-only">{label}</span>
    </span>
  )
}

/**
 * A small label on a thing. Used for a count, a kind, a status in a row.
 *
 * `quiet` is the default and should stay the common case: the audit's rule is
 * that a badge earns its contrast by being rare.
 */
export function Badge({
  children,
  tone = 'quiet',
  className = '',
}: {
  children: ReactNode
  tone?: 'quiet' | 'attention' | 'warn' | 'good' | 'outline'
  className?: string
}) {
  const tones = {
    quiet: 'bg-bone-200 text-ink-600',
    attention: 'bg-gold-200 text-gold-700',
    warn: 'bg-clay-100 text-clay-600',
    good: 'bg-steel-100 text-steel-700',
    outline: 'border border-ink-200 text-ink-500',
  }
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-2xs font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

/**
 * A key/value list — provenance, arithmetic, a record's fields.
 *
 * A real `<dl>`, because that is what this is and because one test asserts it.
 * Two columns on anything but a phone; stacked below, where a 40/60 split
 * leaves neither side enough room to avoid wrapping every value.
 */
export function Facts({
  items,
  className = '',
}: {
  items: { key: string; term: ReactNode; value: ReactNode }[]
  className?: string
}) {
  return (
    <dl className={`grid gap-x-4 gap-y-2 sm:grid-cols-[minmax(0,10rem)_1fr] ${className}`}>
      {items.map((item) => (
        <div key={item.key} className="contents">
          <dt className="text-meta text-ink-500">{item.term}</dt>
          <dd className="text-meta leading-relaxed text-ink-700">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * A table that survives a phone.
 *
 * Below `md` each row becomes a stacked card, using the column headers as
 * labels via the `data-label` attribute — a table that scrolls sideways on a
 * phone is a table nobody reads, and the alternative of hiding columns hides
 * data. Above `md` it is an ordinary table with a sticky header.
 *
 * Numeric columns are right-aligned and tabular, which is the difference
 * between a column of figures and a column of strings that happen to be digits.
 */
export function Table<Row>({
  caption,
  columns,
  rows,
  rowKey,
  empty,
  className = '',
}: {
  /** Describes the table for a screen reader. Visually hidden. */
  caption: string
  columns: {
    key: string
    header: ReactNode
    align?: 'start' | 'end'
    numeric?: boolean
    cell: (row: Row) => ReactNode
    /** Hide on small screens where the value is secondary. */
    minor?: boolean
  }[]
  rows: Row[]
  rowKey: (row: Row) => string
  empty?: ReactNode
  className?: string
}) {
  if (rows.length === 0 && empty) return <>{empty}</>

  return (
    <div className={`surface overflow-hidden ${className}`}>
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">{caption}</caption>
        <thead className="hidden md:table-header-group">
          <tr className="border-b border-ink-100 bg-bone-50">
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={`px-4 py-2.5 text-2xs font-medium uppercase tracking-[0.08em] text-ink-500 ${
                  c.align === 'end' || c.numeric ? 'text-right' : ''
                }`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="flex flex-col md:table-row-group">
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className="flex flex-col gap-1 border-b border-ink-100 px-4 py-3 last:border-0 transition-colors duration-micro ease-out md:table-row md:px-0 md:py-0 md:hover:bg-bone-50"
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  data-label={typeof c.header === 'string' ? c.header : undefined}
                  className={[
                    'text-body text-ink-700 md:px-4 md:py-3',
                    c.numeric ? 'tnum md:text-right' : '',
                    c.align === 'end' ? 'md:text-right' : '',
                    c.minor ? 'hidden md:table-cell' : '',
                    // On a phone the header is printed before the value from
                    // `data-label`, which is what turns the row into a card
                    // without duplicating any markup.
                    "before:mr-2 before:text-2xs before:uppercase before:tracking-[0.08em] before:text-ink-400 before:content-[attr(data-label)] md:before:content-none",
                  ].join(' ')}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
