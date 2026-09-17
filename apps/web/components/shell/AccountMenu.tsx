'use client'

import { AnimatePresence, motion } from 'framer-motion'
import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'
import { popover, useMotionSafe } from '@/lib/motion'
import { fetchSession, logout } from '@/lib/auth-client'

/**
 * Who you are signed in as, and the two things you can do about it.
 *
 * ## Why this replaces a text link
 *
 * The header's only control was the word "Account", underlined, linking to
 * `/account` — a page whose own sidebar entry sat four rows below in the nav
 * panel. So the same destination had two permanent affordances and sign-out had
 * none: to leave, you navigated to a page and found a button on it.
 *
 * A header account control is one of the few places a menu is genuinely the
 * right pattern. It holds two or three rarely-used items that must be reachable
 * from every page, and it is the conventional home for identity — a reader
 * looks top-right to check which account they are in, and that question was
 * unanswerable here without loading a page.
 *
 * ## The avatar is initials, not a picture
 *
 * There is no avatar upload in this product and inventing a coloured gravatar
 * would be an identity the reader never chose. Initials from the email's local
 * part are derived, not decorative, and the full address is in the menu
 * underneath — so the abbreviation is never the only thing available.
 *
 * ## Signing out says so
 *
 * `POST /api/auth/logout` goes through the same proxy as everything else and
 * takes as long as everything else. The button reports that rather than sitting
 * still for ten seconds, and it navigates with `window.location.assign` rather
 * than the router for the reason `WorkspaceMenu` gives: nothing belonging to
 * the session that just ended should survive into the next document.
 */

function initials(email: string): string {
  const local = email.split('@')[0] ?? ''
  const parts = local.split(/[.\-_+]/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return local.slice(0, 2).toUpperCase() || '··'
}

export function AccountMenu() {
  const safe = useMotionSafe()
  const variants = useMemo(() => popover(safe, 'bottom'), [safe])
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState<string | null>(null)
  const [leaving, setLeaving] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let live = true
    fetchSession()
      .then((session) => live && setEmail(session?.email ?? null))
      // A header control must not be able to break a page. Without an address
      // the trigger still works and the menu still holds its links.
      .catch(() => {})
    return () => {
      live = false
    }
  }, [])

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

  async function signOut() {
    setLeaving(true)
    try {
      await logout()
    } catch {
      // Whatever the server said, the intent was to leave. Going to the sign-in
      // page with a stale cookie is recoverable; staying signed in on a shared
      // machine because a request failed is not.
    }
    window.location.assign('/login')
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={email ? `Account — ${email}` : 'Account'}
        className="flex h-9 w-9 items-center justify-center rounded-full border border-ink-200 bg-white text-2xs font-semibold tracking-[0.02em] text-ink-600 transition-[background-color,border-color] duration-micro ease-out hover:border-ink-300 hover:bg-bone-100 hover:text-ink-900"
      >
        {email ? initials(email) : <span aria-hidden="true">··</span>}
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            variants={variants}
            initial="hidden"
            animate="show"
            exit="leave"
            role="menu"
            className="absolute right-0 top-full z-overlay mt-1.5 w-64 rounded-data border border-ink-100 bg-white p-1.5 shadow-e3"
          >
            <div className="border-b border-ink-100 px-2.5 pb-2.5 pt-1.5">
              <p className="text-2xs uppercase tracking-[0.1em] text-ink-400">Signed in as</p>
              <p className="mt-0.5 break-all text-meta font-medium text-ink-700">
                {email ?? 'Checking…'}
              </p>
            </div>

            <Link
              href="/account"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="mt-1 block rounded-control px-2.5 py-2 text-body text-ink-700 transition-colors duration-micro ease-out hover:bg-bone-100 hover:text-ink-900"
            >
              Your account
            </Link>
            <Link
              href="/settings"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="block rounded-control px-2.5 py-2 text-body text-ink-700 transition-colors duration-micro ease-out hover:bg-bone-100 hover:text-ink-900"
            >
              Workspace settings
            </Link>

            <button
              type="button"
              role="menuitem"
              onClick={() => void signOut()}
              disabled={leaving}
              aria-busy={leaving || undefined}
              className="mt-1 block w-full rounded-control border-t border-ink-100 px-2.5 py-2 pt-2.5 text-left text-body text-ink-700 transition-colors duration-micro ease-out hover:bg-bone-100 hover:text-ink-900 disabled:text-ink-400"
            >
              {leaving ? 'Signing out…' : 'Sign out'}
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
