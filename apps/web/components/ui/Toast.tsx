'use client'

import { AnimatePresence, motion } from 'framer-motion'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { toast as toastVariants, useMotionSafe } from '@/lib/motion'

/**
 * Transient confirmation.
 *
 * ## Why this exists
 *
 * `/settings` has three separate save buttons and `/work` has eight record
 * forms. The audit pressed them and could not tell whether anything had
 * happened: there was no confirmation of any kind, so the only evidence a save
 * worked was the row appearing somewhere further down a four-thousand-pixel
 * page. On a request that takes ten seconds that is indistinguishable from a
 * save that silently failed.
 *
 * ## Why a toast rather than inline text
 *
 * Inline is better when the reader is looking at the thing that changed. It is
 * useless when the change is at the top of a long page and the button is at the
 * bottom, which is the case for every save in this product. So: inline for
 * validation, a toast for "that worked".
 *
 * ## The rules it holds
 *
 * - **It never carries the only copy of information.** A toast is gone in five
 *   seconds and cannot be recalled, so nothing that matters lives only here.
 *   An error with a recovery action gets `Failed`, on the page, instead.
 * - **Hovering pauses the dismissal.** A reader whose pointer is on the toast
 *   is reading it, and taking it away mid-sentence is the classic toast
 *   failure. Focus pauses it too, so a keyboard user can reach the close
 *   button before it leaves.
 * - **One live region, announced politely.** `aria-live="polite"` rather than
 *   `assertive`: a save confirmation must not interrupt a screen reader
 *   mid-word. The container is mounted at all times so the region exists before
 *   the first message arrives — a live region created *with* its content is not
 *   reliably announced.
 * - **It never blocks a click.** The stack is `pointer-events-none`; each toast
 *   re-enables them for itself.
 */

type Tone = 'good' | 'warn'

type Toast = {
  id: number
  tone: Tone
  message: string
  /** One optional action, e.g. "Undo" or "View". Never the only way to recover. */
  action?: { label: string; onClick: () => void }
}

type Push = (message: string, options?: { tone?: Tone; action?: Toast['action'] }) => void

const ToastContext = createContext<Push | null>(null)

/** How long a toast stays, unless the pointer or focus is on it. */
const DWELL = 5_000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(0)

  const dismiss = useCallback((id: number) => {
    setToasts((was) => was.filter((t) => t.id !== id))
  }, [])

  const push = useCallback<Push>((message, options) => {
    const id = next.current++
    setToasts((was) => [
      // Newest first, and capped at three. A stack that grows without bound
      // covers the page it is confirming something about.
      { id, message, tone: options?.tone ?? 'good', action: options?.action },
      ...was.slice(0, 2),
    ])
  }, [])

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        // Bottom-centre on a phone, bottom-right on a desktop: on a phone the
        // right corner is the hardest place to reach with a thumb and the most
        // likely to sit under a browser control.
        className="pointer-events-none fixed inset-x-0 bottom-0 z-toast flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end"
        role="region"
        aria-label="Notifications"
      >
        <span aria-live="polite" aria-atomic="false" className="sr-only">
          {toasts.map((t) => (
            <span key={t.id}>{t.message}</span>
          ))}
        </span>
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <ToastRow key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

function ToastRow({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const safe = useMotionSafe()
  const variants = useMemo(() => toastVariants(safe), [safe])
  const [held, setHeld] = useState(false)

  useEffect(() => {
    if (held) return
    const timer = setTimeout(onDismiss, DWELL)
    return () => clearTimeout(timer)
  }, [held, onDismiss])

  return (
    <motion.div
      variants={variants}
      initial="hidden"
      animate="show"
      exit="leave"
      layout={safe}
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocusCapture={() => setHeld(true)}
      onBlurCapture={() => setHeld(false)}
      className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-data border border-ink-700 bg-ink-800 px-4 py-3 text-bone-50 shadow-e3"
    >
      <span
        aria-hidden="true"
        className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
          toast.tone === 'warn' ? 'bg-gold-400' : 'bg-steel-300'
        }`}
      />
      <p className="flex-1 text-meta leading-relaxed">{toast.message}</p>

      {toast.action ? (
        <button
          type="button"
          onClick={() => {
            toast.action?.onClick()
            onDismiss()
          }}
          className="shrink-0 rounded-[0.35rem] text-meta font-medium text-gold-300 underline decoration-gold-300/40 underline-offset-2 transition-colors duration-micro hover:text-gold-200 focus-visible:ring-2 focus-visible:ring-gold-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-800"
        >
          {toast.action.label}
        </button>
      ) : null}

      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-my-1 -mr-1.5 shrink-0 rounded-[0.35rem] p-1.5 text-slate-300 transition-colors duration-micro hover:text-bone-50 focus-visible:ring-2 focus-visible:ring-gold-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-800"
      >
        <svg viewBox="0 0 14 14" fill="none" aria-hidden="true" className="h-3.5 w-3.5">
          <path d="m3.5 3.5 7 7m0-7-7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
    </motion.div>
  )
}

/**
 * Push a toast.
 *
 * Returns a no-op outside a provider rather than throwing. A save confirmation
 * is not worth crashing a page over, and the components that use this are also
 * rendered in unit tests that have no reason to mount the provider.
 */
export function useToast(): Push {
  const push = useContext(ToastContext)
  return push ?? noop
}

const noop: Push = () => {}
