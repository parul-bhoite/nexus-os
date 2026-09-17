'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useId, useMemo, useRef, type ReactNode } from 'react'
import { dialog, scrim, slideIn, useMotionSafe } from '@/lib/motion'

/**
 * Overlays: the drawer, the sheet and the dialog.
 *
 * ## What was wrong
 *
 * The app shell's mobile navigation was `open ? <div>…</div> : null`. That is
 * an overlay with none of an overlay's obligations:
 *
 * - **It appeared and vanished instantly**, so nothing said where it came from.
 * - **It had no close control.** It covered the header, including the button
 *   that opened it, and the only way out was to guess that the sliver of page
 *   on the right was a scrim.
 * - **It did not trap focus**, so tabbing walked straight out of the open
 *   drawer and into the page behind it, which is still there and still
 *   clickable to a keyboard.
 * - **Escape did nothing.**
 * - **The page behind it still scrolled**, so a touch that missed the panel
 *   scrolled the content underneath.
 * - **It was not a dialog** to assistive technology — no role, no label, no
 *   `aria-modal`.
 *
 * This component is those six obligations, written once. Everything modal in
 * the product goes through it, which is the only way they stay met.
 *
 * ## Focus
 *
 * On open, focus moves to the panel itself rather than to the first control:
 * moving straight to the first link means a screen reader starts reading
 * "Today, link" with no indication that a dialog opened. The panel is
 * `tabIndex={-1}` and labelled, so it announces itself first. On close, focus
 * returns to whatever had it before — which is what makes the drawer usable
 * twice in a row from a keyboard.
 *
 * The trap is a keydown handler on Tab rather than a library: the contents are
 * ordinary DOM, the set of focusable elements is small, and the wrap is four
 * lines. What matters is that it is in one place.
 */

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

function useOverlay(open: boolean, onClose: () => void) {
  const panel = useRef<HTMLDivElement>(null)
  const restoreTo = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return

    restoreTo.current = document.activeElement as HTMLElement | null
    // A frame, so the panel exists and has been laid out before it is focused.
    const raf = requestAnimationFrame(() => panel.current?.focus())

    // The page behind must not scroll. Padding compensates for the scrollbar
    // the lock removes, without which the whole page shifts left as it opens.
    const { body } = document
    const gap = window.innerWidth - document.documentElement.clientWidth
    const overflow = body.style.overflow
    const padding = body.style.paddingRight
    body.style.overflow = 'hidden'
    if (gap > 0) body.style.paddingRight = `${gap}px`

    return () => {
      cancelAnimationFrame(raf)
      body.style.overflow = overflow
      body.style.paddingRight = padding
      restoreTo.current?.focus?.()
    }
  }, [open])

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const nodes = panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE)
      if (!nodes || nodes.length === 0) {
        // Nothing to move to. Keep focus on the panel rather than letting it
        // escape to the page behind.
        event.preventDefault()
        return
      }
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      const active = document.activeElement

      if (event.shiftKey && (active === first || active === panel.current)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    },
    [onClose],
  )

  return { panel, onKeyDown }
}

function Scrim({ onClose }: { onClose: () => void }) {
  const safe = useMotionSafe()
  const variants = useMemo(() => scrim(safe), [safe])
  return (
    <motion.div
      variants={variants}
      initial="hidden"
      animate="show"
      exit="leave"
      onClick={onClose}
      // Dark enough to read as modal. The old drawer used ink-900/30, through
      // which the page stayed fully legible, so the drawer read as a panel
      // that had landed on the page rather than as something covering it.
      className="absolute inset-0 bg-ink-950/45 backdrop-blur-[2px]"
      aria-hidden="true"
    />
  )
}

function CloseButton({ onClose, label = 'Close' }: { onClose: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label={label}
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-ink-500 transition-colors duration-micro ease-out hover:bg-bone-200 hover:text-ink-900"
    >
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="h-4 w-4">
        <path d="m4 4 8 8m0-8-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  )
}

/**
 * A panel from an edge. Left for navigation, right for detail, bottom on a
 * phone — a right-hand sheet on a 390px screen is a full-screen takeover that
 * arrives from the wrong direction for a thumb.
 */
export function Sheet({
  open,
  onClose,
  title,
  description,
  side = 'right',
  children,
  footer,
  width = 'max-w-md',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  side?: 'left' | 'right' | 'bottom'
  children: ReactNode
  footer?: ReactNode
  width?: string
}) {
  const safe = useMotionSafe()
  const { panel, onKeyDown } = useOverlay(open, onClose)
  const titleId = useId()
  const descId = useId()
  const variants = useMemo(() => slideIn(safe, side), [safe, side])

  const place =
    side === 'bottom'
      ? `inset-x-0 bottom-0 max-h-[85vh] rounded-t-panel border-t`
      : side === 'left'
        ? `inset-y-0 left-0 w-full ${width} border-r`
        : `inset-y-0 right-0 w-full ${width} border-l`

  return (
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-overlay" onKeyDown={onKeyDown}>
          <Scrim onClose={onClose} />
          <motion.div
            ref={panel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={description ? descId : undefined}
            variants={variants}
            initial="hidden"
            animate="show"
            exit="leave"
            className={`absolute flex flex-col border-ink-100 bg-bone-50 shadow-e3 outline-none ${place}`}
          >
            <header className="flex items-start gap-3 border-b border-ink-100 bg-white px-5 py-4">
              <div className="min-w-0 flex-1">
                <h2 id={titleId} className="text-title text-ink-900">
                  {title}
                </h2>
                {description ? (
                  <p id={descId} className="mt-1 text-meta leading-relaxed text-ink-500">
                    {description}
                  </p>
                ) : null}
              </div>
              <CloseButton onClose={onClose} />
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>

            {footer ? (
              <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-ink-100 bg-white px-5 py-3.5">
                {footer}
              </footer>
            ) : null}
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}

/**
 * A centred dialog, for a decision rather than a task.
 *
 * Use it for confirmation and nothing else. Anything with a form in it belongs
 * in a `Sheet`, which can be as tall as it needs to be and does not jump when
 * an error message appears.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  const safe = useMotionSafe()
  const { panel, onKeyDown } = useOverlay(open, onClose)
  const titleId = useId()
  const variants = useMemo(() => dialog(safe), [safe])

  return (
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-overlay flex items-end justify-center p-4 sm:items-center" onKeyDown={onKeyDown}>
          <Scrim onClose={onClose} />
          <motion.div
            ref={panel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            variants={variants}
            initial="hidden"
            animate="show"
            exit="leave"
            className="relative flex w-full max-w-md flex-col rounded-panel border border-ink-100 bg-white shadow-e3 outline-none"
          >
            <header className="flex items-start gap-3 px-6 pt-5">
              <h2 id={titleId} className="flex-1 text-title text-ink-900">
                {title}
              </h2>
              <CloseButton onClose={onClose} />
            </header>
            <div className="px-6 pb-2 pt-3 text-body leading-relaxed text-ink-600">{children}</div>
            {footer ? (
              <footer className="flex flex-wrap items-center justify-end gap-2 px-6 pb-5 pt-3">
                {footer}
              </footer>
            ) : null}
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}
