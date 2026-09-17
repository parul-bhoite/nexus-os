'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { useId, useMemo, useState, type ReactNode } from 'react'
import { collapse, useMotionSafe } from '@/lib/motion'

/**
 * A region that opens in place.
 *
 * ## Why the product needs one badly
 *
 * The audit's central finding about the dashboard is that the apparatus around
 * each number is fifteen lines and the number is one. Every block card carried,
 * permanently expanded: what the figure measures, how it was counted, what it
 * excluded, when it was last read, a caveat about completeness, the capability's
 * specification id, and its block kind. All of it is *correct* and most of it is
 * the reason to trust the product — and all of it at once means the reader
 * cannot see the figure.
 *
 * The fix is not to delete any of it. It is to make one consistent gesture
 * reveal it, everywhere, so that "where did this come from?" has a single
 * answer the reader learns once. That is what this is.
 *
 * ## Why not `<details>`
 *
 * `<details>` is the right instinct and the product already used it in one
 * place. Two things stop it being enough here: it cannot animate its own height
 * (so a drawer full of arithmetic snaps open and shifts the page), and its
 * open state cannot be lifted, which the block grid needs — "expand the working
 * on every card" is a single control on the section, not twelve separate ones.
 *
 * What `<details>` gets right and this keeps: the summary is a real button and
 * the control says what it will reveal rather than saying "more".
 *
 * **A closed region renders nothing.** An earlier draft mirrored the closed
 * children into a `hidden` div so browser find-in-page could still reach them.
 * That is a nice property and it is the wrong trade: `BlockCard`'s own test
 * asserts that the nine rows of a calculator's working are *not on the page*
 * until they are asked for, which is the behaviour the drawer exists to
 * provide. Content that is merely visually hidden is still content the reader
 * did not ask for — it is in the DOM, it is in `textContent`, and any tooling
 * that reads the page reads it. So closed means absent.
 *
 * ## Reduced motion
 *
 * `collapse` resolves to a zero-duration height change, so the region still
 * opens and closes — the state change is preserved, only the travel is removed.
 */

export function Disclosure({
  summary,
  children,
  /** Controlled, when a parent offers "expand all". */
  open: controlled,
  onOpenChange,
  defaultOpen = false,
  tone = 'quiet',
  className = '',
}: {
  summary: ReactNode
  children: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  defaultOpen?: boolean
  tone?: 'quiet' | 'bordered'
  className?: string
}) {
  const safe = useMotionSafe()
  const variants = useMemo(() => collapse(safe), [safe])
  const [uncontrolled, setUncontrolled] = useState(defaultOpen)
  const id = useId()

  const open = controlled ?? uncontrolled
  const toggle = () => {
    if (controlled === undefined) setUncontrolled(!open)
    onOpenChange?.(!open)
  }

  return (
    <div className={className}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={id}
        className={`group flex w-full items-center gap-1.5 rounded-[0.35rem] text-meta font-medium transition-colors duration-micro ease-out ${
          tone === 'bordered'
            ? 'justify-between border-b border-ink-100 px-1 py-3 text-ink-700 hover:text-ink-900'
            : 'text-ink-500 hover:text-ink-800'
        }`}
      >
        <span>{summary}</span>
        <svg
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
          className={`h-3.5 w-3.5 shrink-0 transition-transform duration-base ease-out ${
            open ? 'rotate-180' : ''
          }`}
        >
          <path d="m4 6.25 4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* `initial={false}` so a card that mounts already open — the "expand
          all" case — does not animate thirty regions at once on first paint. */}
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={id}
            key="content"
            variants={variants}
            initial="hidden"
            animate="show"
            exit="leave"
            className="overflow-hidden"
          >
            <div className="pt-2.5">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

/**
 * A list of them, where opening one is independent of the others.
 *
 * Deliberately not an accordion that closes its siblings. On an FAQ a reader
 * frequently wants two answers side by side to compare them, and closing the
 * first one as they open the second makes that impossible — the "only one open"
 * rule saves vertical space at the cost of the task the page exists for.
 */
export function DisclosureList({
  items,
  className = '',
}: {
  items: { key: string; summary: ReactNode; content: ReactNode }[]
  className?: string
}) {
  return (
    <div className={`flex flex-col ${className}`}>
      {items.map((item) => (
        <Disclosure key={item.key} summary={item.summary} tone="bordered">
          <div className="pb-4">{item.content}</div>
        </Disclosure>
      ))}
    </div>
  )
}
