'use client'

import { motion } from 'framer-motion'
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { spring, useMotionSafe } from '@/lib/motion'

/**
 * A horizontal tab rail with a sliding indicator.
 *
 * ## The keyboard contract
 *
 * The director page's rail was a row of buttons. A row of buttons is not a tab
 * list: every tab is a separate tab stop, so reaching the sixth means six
 * presses, and nothing announces "tab 3 of 6" or that a panel is associated
 * with the selection. The WAI pattern is one tab stop for the whole rail plus
 * arrow keys within it, which is what `onKeyDown` implements here — and it is
 * also simply faster for a mouse user's muscle memory, because Home and End
 * work.
 *
 * ## The indicator
 *
 * `layoutId` lets framer-motion move one element between positions rather than
 * cross-fading two, which is what makes the movement read as the *same*
 * indicator travelling. It is a spring rather than a tween because the target
 * can change mid-flight — clicking two tabs quickly — and a tween restarts
 * where a spring redirects.
 *
 * The indicator is behind the label (`-z-10` on the motion element, label
 * relative) so text never animates; only the shape moves.
 *
 * ## Overflow
 *
 * Six tabs with counts do not fit 390px. The rail scrolls horizontally, with
 * the ends masked so a partially visible tab reads as "there is more" rather
 * than as a clipped one. `scroll-snap` is deliberately absent — snapping fights
 * a reader who is flicking through to see what exists.
 *
 * **The mask is conditional, and that is not a refinement.** Applied
 * unconditionally it fades the first and last 8% of the rail whether or not
 * anything overflows — so on a desktop where all six tabs fit, the selected
 * first tab rendered as a navy pill dissolving into the page at its left edge,
 * which reads as a rendering fault rather than as an affordance. The fade now
 * appears on an edge only when there is scrollable content past it, which is
 * also what makes it mean something: it says "there is more this way".
 */

export type Tab = {
  key: string
  label: ReactNode
  /** Shown as a quiet numeral after the label. Omit rather than pass 0. */
  count?: number
}

export function Tabs({
  tabs,
  active,
  onChange,
  label,
  className = '',
}: {
  tabs: Tab[]
  active: string
  onChange: (key: string) => void
  /** Names the rail for assistive technology — "Operations sections". */
  label: string
  className?: string
}) {
  const safe = useMotionSafe()
  const group = useId()
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  const rail = useRef<HTMLDivElement>(null)
  const [overflow, setOverflow] = useState({ start: false, end: false })

  const measure = useCallback(() => {
    const node = rail.current
    if (!node) return
    // A pixel of tolerance: sub-pixel layout means `scrollLeft` rarely reaches
    // exactly `scrollWidth - clientWidth`, and without it the end fade never
    // turns off when the rail is scrolled fully right.
    const max = node.scrollWidth - node.clientWidth
    setOverflow({ start: node.scrollLeft > 1, end: node.scrollLeft < max - 1 })
  }, [])

  // Layout effect, so the first paint already has the right mask rather than
  // flashing a fade on a rail that does not overflow.
  useLayoutEffect(measure, [measure, tabs.length])

  useEffect(() => {
    const node = rail.current
    if (!node) return
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [measure])

  function onKeyDown(event: React.KeyboardEvent) {
    const order = tabs.map((t) => t.key)
    const at = order.indexOf(active)
    let next: string | undefined

    if (event.key === 'ArrowRight') next = order[(at + 1) % order.length]
    else if (event.key === 'ArrowLeft') next = order[(at - 1 + order.length) % order.length]
    else if (event.key === 'Home') next = order[0]
    else if (event.key === 'End') next = order[order.length - 1]
    else return

    event.preventDefault()
    onChange(next)
    refs.current[next]?.focus()
  }

  return (
    <div
      ref={rail}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      onScroll={measure}
      className={`-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${
        overflow.start && overflow.end
          ? 'mask-fade-x'
          : overflow.start
            ? 'mask-fade-start'
            : overflow.end
              ? 'mask-fade-end'
              : ''
      } ${className}`}
    >
      {tabs.map((tab) => {
        const current = tab.key === active
        return (
          <button
            key={tab.key}
            ref={(node) => {
              refs.current[tab.key] = node
            }}
            type="button"
            role="tab"
            id={`${group}-${tab.key}`}
            aria-selected={current}
            aria-controls={`${group}-${tab.key}-panel`}
            // One tab stop for the rail: only the selected tab is reachable by
            // Tab, and the arrows move within.
            tabIndex={current ? 0 : -1}
            onClick={() => onChange(tab.key)}
            className={`relative shrink-0 rounded-full px-3.5 py-2 text-meta font-medium transition-colors duration-base ease-out focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-2 ${
              current ? 'text-bone-50' : 'text-ink-600 hover:bg-bone-200 hover:text-ink-900'
            }`}
          >
            {current ? (
              <motion.span
                layoutId={`${group}-indicator`}
                transition={safe ? spring.indicator : { duration: 0 }}
                aria-hidden="true"
                className="absolute inset-0 -z-10 rounded-full bg-ink-800"
              />
            ) : null}
            <span className="relative">{tab.label}</span>
            {typeof tab.count === 'number' ? (
              <span
                className={`relative ml-1.5 tnum text-2xs ${current ? 'text-slate-300' : 'text-ink-400'}`}
              >
                {tab.count}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

/** The panel a tab controls. Focusable, so the tab's target can be reached. */
export function TabPanel({
  id,
  tab,
  children,
  className = '',
}: {
  /** The same `useId()` group value the rail was given. */
  id: string
  tab: string
  children: ReactNode
  className?: string
}) {
  return (
    <div
      role="tabpanel"
      id={`${id}-${tab}-panel`}
      aria-labelledby={`${id}-${tab}`}
      tabIndex={0}
      className={`outline-none ${className}`}
    >
      {children}
    </div>
  )
}
