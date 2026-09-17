'use client'

/**
 * The loading system.
 *
 * ## The problem this replaces
 *
 * Signed in, `/dashboard` showed two lines of plain text on an otherwise empty
 * page — "Reading what changed…", then "Taking longer than usual" — for the
 * twelve to sixteen seconds the API takes against Neon. Three separate failures
 * were stacked in that:
 *
 * 1. **No shape.** Nothing told the reader what was coming or how much of it,
 *    so the wait had no end in sight and the page had no layout to settle into.
 * 2. **A layout jump on arrival.** The nav panel omits its Directors group
 *    while the director list is `null`, so the sidebar grew by seven rows the
 *    moment the fetch landed — and, worse, until then it stated an absence
 *    `AppShell`'s own documentation says it must never state.
 * 3. **Reflow.** Content arriving into an empty region pushes everything below
 *    it, so a reader who started reading the top of the page gets moved.
 *
 * A skeleton fixes all three at once, and only if it is **the same shape as the
 * content**. A generic grey box is a spinner with extra steps: it neither
 * predicts the layout nor prevents the jump. So the skeletons here are built
 * from the same primitives, at the same sizes, as the components they stand in
 * for, and each one lives beside the thing it mimics rather than in a pile.
 *
 * ## Why `opacity` and not a sweep
 *
 * The sweep — a gradient translated across the placeholder — is the familiar
 * choice and the wrong one here. It repaints the full area of every placeholder
 * every frame, and the dashboard shows about thirty of them, on a page that is
 * by definition already waiting on something slow. `animate-breathe` animates
 * opacity, which the compositor handles on its own, and it is slow (1.6s) and
 * shallow (1 → 0.45) enough to read as breathing rather than as a progress
 * indicator with no denominator.
 *
 * ## Announcing it
 *
 * The placeholders themselves are `aria-hidden`; a screen reader reading out
 * eleven blank boxes is worse than silence. The *region* carries one
 * `role="status"` with a sentence, which is what `Loading` is for. One
 * announcement, not thirty.
 */

/** A single placeholder. `w`/`h` are Tailwind classes so the caller sizes it. */
export function Bone({ className = '' }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`block animate-breathe rounded-[0.35rem] bg-ink-100 ${className}`}
    />
  )
}

/**
 * Lines of text. The last line is short, because a paragraph's last line is,
 * and that single detail is most of what makes a text skeleton read as text.
 */
export function BoneText({
  lines = 3,
  className = '',
}: {
  lines?: number
  className?: string
}) {
  return (
    <span aria-hidden="true" className={`flex flex-col gap-2 ${className}`}>
      {Array.from({ length: lines }, (_, i) => (
        <Bone
          key={i}
          className={`h-3 ${i === lines - 1 ? 'w-2/5' : i % 3 === 1 ? 'w-11/12' : 'w-full'}`}
        />
      ))}
    </span>
  )
}

/**
 * One announcement for a loading region, with the skeleton inside it.
 *
 * `aria-busy` on the region is what tells assistive technology that what is
 * inside is provisional. The sentence says what is being read, in the product's
 * own voice — `Waiting` already established that the copy should name the work
 * rather than say "please wait", and it escalates if the wait goes on.
 */
export function Loading({
  label,
  children,
  className = '',
}: {
  label: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  )
}

/**
 * A block card's placeholder. Mirrors `BlockCard`: a title row with a state
 * dot, a figure, two lines of qualifier, and the working row.
 */
export function BlockCardSkeleton() {
  return (
    <li aria-hidden="true" className="surface flex flex-col gap-4 px-5 py-5">
      <div className="flex items-start justify-between gap-3">
        <Bone className="h-4 w-1/2" />
        <Bone className="h-2 w-2 rounded-full" />
      </div>
      <Bone className="h-8 w-24" />
      <BoneText lines={2} />
      <div className="mt-auto flex items-center gap-2 border-t border-ink-100 pt-3">
        <Bone className="h-3 w-28" />
      </div>
    </li>
  )
}

/** A grid of them. `count` matches what the real grid usually holds. */
export function BlockGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <ul className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {Array.from({ length: count }, (_, i) => (
        <BlockCardSkeleton key={i} />
      ))}
    </ul>
  )
}

/** A table's placeholder, with the header row solid and the body breathing. */
export function TableSkeleton({
  rows = 5,
  columns = 4,
}: {
  rows?: number
  columns?: number
}) {
  return (
    <div aria-hidden="true" className="surface overflow-hidden">
      <div className="flex gap-4 border-b border-ink-100 bg-bone-50 px-4 py-2.5">
        {Array.from({ length: columns }, (_, i) => (
          <Bone key={i} className="h-2.5 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex gap-4 border-b border-ink-100 px-4 py-3 last:border-0">
          {Array.from({ length: columns }, (_, c) => (
            <Bone key={c} className={`h-3 flex-1 ${c === 0 ? 'max-w-[40%]' : ''}`} />
          ))}
        </div>
      ))}
    </div>
  )
}

/** The nav panel's placeholder. Holds the height the real panel will need. */
export function NavSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-6">
      <Bone className="h-12 w-full rounded-control" />
      <div className="flex flex-col gap-2">
        <Bone className="ml-3 h-2.5 w-16" />
        {Array.from({ length: 7 }, (_, i) => (
          <Bone key={i} className="h-8 w-full rounded-control" />
        ))}
      </div>
      <div className="flex flex-col gap-2">
        <Bone className="ml-3 h-2.5 w-16" />
        <Bone className="h-8 w-full rounded-control" />
        <Bone className="h-8 w-full rounded-control" />
      </div>
    </div>
  )
}

/** A page's heading placeholder, so the title does not jump in. */
export function PageHeadSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-3">
      <Bone className="h-8 w-56" />
      <Bone className="h-3 w-80" />
    </div>
  )
}
