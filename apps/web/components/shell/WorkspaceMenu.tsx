'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import { popover, useMotionSafe } from '@/lib/motion'
import { switchWorkspace, type WorkspaceChoice } from '@/lib/settings-client'

/**
 * Which company you are in, and — when there is more than one — how to leave it.
 *
 * ## Why the name is always on screen now
 *
 * `EntitySwitcher` renders nothing for a single-entity login, which is almost
 * everybody, and that was the right call for a *switcher*: a control with one
 * option implies a second company exists somewhere you cannot see. But the
 * consequence was that the product never named the workspace anywhere in its
 * chrome. The only place the company appeared was a card on `/account`.
 *
 * ADR 0026 calls reading entity A's figures under entity B's name the worst
 * failure this product can have, precisely because it looks entirely normal.
 * The defence against a silent mismatch is that the name is *never* off screen,
 * so this renders it for one company as static text and for several as a menu.
 * The switcher's own argument is preserved: with one company there is no
 * control, no chevron and nothing to press — just the name.
 *
 * ## Switching is still a full page navigation
 *
 * Unchanged from `EntitySwitcher`, and for its reasons: a client-side
 * transition would leave React state, module state and in-flight requests from
 * the previous entity alive in the same document. `switchWorkspace` posts and
 * this reloads. The cost is a visible reload and it is the correct price.
 *
 * The audit's one addition is that the button reports it. A ten-second POST
 * whose only feedback was the word changing inside the pill read as a control
 * that had not registered the click.
 */

export function WorkspaceMenu({
  workspaces,
  className = '',
}: {
  workspaces: WorkspaceChoice[] | null
  className?: string
}) {
  const safe = useMotionSafe()
  const variants = useMemo(() => popover(safe, 'bottom'), [safe])
  const [open, setOpen] = useState(false)
  const [moving, setMoving] = useState('')
  const [problem, setProblem] = useState('')
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function away(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    function key(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', key)
    }
  }, [open])

  // Unknown. A skeleton rather than a guess — the shell's fetch may still be in
  // flight, and an empty header that fills in later is one more thing moving.
  if (workspaces === null) {
    return (
      <span
        aria-hidden="true"
        className={`ml-1 h-4 w-28 animate-breathe rounded-[0.3rem] bg-ink-100 ${className}`}
      />
    )
  }

  const active = workspaces.find((w) => w.active) ?? workspaces[0]
  if (!active) return null

  const others = workspaces.filter((w) => w.workspace_id !== active.workspace_id)

  async function move(to: WorkspaceChoice) {
    setMoving(to.workspace_id)
    setProblem('')
    try {
      await switchWorkspace(to.workspace_id)
      window.location.assign('/dashboard?switched=1')
    } catch {
      setProblem(`Could not switch. You are still in ${active.name}.`)
      setMoving('')
    }
  }

  // One company. The name, and nothing to press.
  if (others.length === 0) {
    return (
      <span className={`ml-1 min-w-0 items-center gap-2 ${className}`}>
        <span aria-hidden="true" className="h-4 w-px shrink-0 bg-ink-200" />
        <span className="truncate text-meta font-medium text-ink-600" title={active.name}>
          {active.name}
        </span>
      </span>
    )
  }

  return (
    <div ref={root} className={`relative ml-1 min-w-0 items-center gap-2 ${className}`}>
      <span aria-hidden="true" className="h-4 w-px shrink-0 bg-ink-200" />
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex min-w-0 items-center gap-1.5 rounded-control px-2 py-1.5 text-meta font-medium text-ink-600 transition-colors duration-micro ease-out hover:bg-bone-200 hover:text-ink-900"
      >
        <span className="truncate">{active.name}</span>
        <svg
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
          className={`h-3.5 w-3.5 shrink-0 text-ink-400 transition-transform duration-base ease-out ${
            open ? 'rotate-180' : ''
          }`}
        >
          <path d="m4 6.25 4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            variants={variants}
            initial="hidden"
            animate="show"
            exit="leave"
            role="menu"
            aria-label="Companies"
            className="absolute left-0 top-full z-overlay mt-1.5 w-64 rounded-data border border-ink-100 bg-white p-1.5 shadow-e3"
          >
            <p className="px-2.5 py-1.5 text-2xs uppercase tracking-[0.1em] text-ink-400">
              Companies
            </p>
            {workspaces.map((entity) => {
              const current = entity.workspace_id === active.workspace_id
              return (
                <button
                  key={entity.workspace_id}
                  type="button"
                  role="menuitem"
                  onClick={() => void move(entity)}
                  disabled={current || moving !== ''}
                  aria-current={current ? 'true' : undefined}
                  className="flex w-full items-center gap-2 rounded-control px-2.5 py-2 text-left text-body text-ink-700 transition-colors duration-micro ease-out hover:bg-bone-100 disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <span className="min-w-0 flex-1 truncate">{entity.name}</span>
                  {moving === entity.workspace_id ? (
                    <span className="shrink-0 text-2xs text-ink-400">Switching…</span>
                  ) : current ? (
                    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-steel-500">
                      <path d="m3.5 8.5 3 3 6-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : null}
                </button>
              )
            })}
            {/* Named, not "switched successfully". The whole risk this control
                carries is reading one company's figures under another's name. */}
            <p className="border-t border-ink-100 px-2.5 pb-1 pt-2 text-2xs leading-relaxed text-ink-400">
              Switching reloads the page so nothing from this company is left on
              screen.
            </p>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {problem ? (
        <p role="alert" className="absolute left-0 top-full mt-1 w-64 text-meta font-medium text-clay-600">
          {problem}
        </p>
      ) : null}
    </div>
  )
}
