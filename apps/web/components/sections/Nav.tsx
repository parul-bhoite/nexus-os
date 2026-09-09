'use client'

import { AnimatePresence, motion } from 'framer-motion'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Logo } from '@/components/ui/Logo'
import { Button, ArrowRight } from '@/components/ui/Button'
import { nav } from '@/lib/content'
import { useActiveSection, useScrolled } from '@/lib/hooks'

const hrefs = nav.map((n) => n.href)

export function Nav() {
  const scrolled = useScrolled(16)
  const active = useActiveSection(hrefs)
  const [open, setOpen] = useState(false)

  // A locked body while the mobile sheet is open; restored on close.
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <motion.header
        initial={{ y: -80, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
        className="fixed inset-x-0 top-0 z-50"
      >
        <div
          className={`transition-all duration-500 ease-out-expo ${
            scrolled
              ? 'border-b border-bone-300/70 bg-white/85 backdrop-blur-xl'
              : 'border-b border-transparent bg-transparent'
          }`}
        >
          <div className="shell-full flex h-[4.5rem] items-center justify-between gap-6">
            <a href="#top" className="shrink-0" aria-label={`${'NEXUS OS'} home`}>
              <Logo />
            </a>

            <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
              {nav.map((item) => {
                const isActive = active === item.href
                return (
                  <a
                    key={item.href}
                    href={item.href}
                    className={`relative rounded-full px-3.5 py-2 text-sm transition-colors duration-300 ${
                      isActive ? 'text-ink-800' : 'text-ink-500 hover:text-ink-800'
                    }`}
                  >
                    {isActive ? (
                      <motion.span
                        layoutId="nav-pill"
                        className="absolute inset-0 rounded-full bg-bone-200"
                        transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                      />
                    ) : null}
                    <span className="relative z-10">{item.label}</span>
                  </a>
                )
              })}
            </nav>

            <div className="flex items-center gap-2">
              <Link
                href="/login"
                className="hidden rounded-full px-4 py-2 text-sm text-ink-600 transition-colors hover:text-ink-900 sm:inline-block"
              >
                Sign in
              </Link>
              <Button href="/register" size="md" icon={<ArrowRight />} className="hidden sm:inline-flex">
                Start free
              </Button>

              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label={open ? 'Close menu' : 'Open menu'}
                aria-expanded={open}
                className="relative grid h-11 w-11 place-items-center rounded-full border border-bone-300 bg-white lg:hidden"
              >
                <span className="sr-only">Menu</span>
                <span className="flex h-3.5 w-5 flex-col justify-between">
                  <motion.span
                    animate={open ? { rotate: 45, y: 6 } : { rotate: 0, y: 0 }}
                    className="block h-0.5 w-full rounded-full bg-ink-800"
                  />
                  <motion.span
                    animate={open ? { opacity: 0 } : { opacity: 1 }}
                    className="block h-0.5 w-full rounded-full bg-ink-800"
                  />
                  <motion.span
                    animate={open ? { rotate: -45, y: -6 } : { rotate: 0, y: 0 }}
                    className="block h-0.5 w-full rounded-full bg-ink-800"
                  />
                </span>
              </button>
            </div>
          </div>
        </div>
      </motion.header>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-40 bg-white/95 backdrop-blur-xl lg:hidden"
          >
            <div className="shell-full flex h-full flex-col pt-28">
              <nav className="flex flex-col" aria-label="Mobile">
                {nav.map((item, i) => (
                  <motion.a
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    initial={{ opacity: 0, y: 18 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.06 + i * 0.05, ease: [0.16, 1, 0.3, 1] }}
                    className="border-b border-bone-200 py-5 font-display text-3xl text-ink-800"
                  >
                    {item.label}
                  </motion.a>
                ))}
              </nav>
              <div className="mt-auto flex flex-col gap-3 pb-10 pt-8">
                <Button href="/register" size="lg" icon={<ArrowRight />}>
                  Start free
                </Button>
                <Button href="/login" size="lg" variant="secondary">
                  Sign in
                </Button>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  )
}
