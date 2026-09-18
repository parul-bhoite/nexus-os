'use client'

import { motion, type Variants } from 'framer-motion'
import { Fragment, type ReactNode } from 'react'
import { duration, easing, travel } from '@/lib/motion'

type Direction = 'up' | 'down' | 'left' | 'right' | 'none'

/**
 * How far a revealed element travels.
 *
 * `travel.reveal` is 16px, where this file used 28. At 28px a card looks like
 * it is being thrown into place, and the brief asks for low amplitude — on a
 * page where twelve cards reveal in sequence, twelve things moving a long way
 * is the difference between a page that settles and a page that lurches.
 */
const offset: Record<Direction, { x: number; y: number }> = {
  up: { x: 0, y: travel.reveal },
  down: { x: 0, y: -travel.reveal },
  left: { x: travel.reveal, y: 0 },
  right: { x: -travel.reveal, y: 0 },
  none: { x: 0, y: 0 },
}

/**
 * **No `useReducedMotion()` in this file.**
 *
 * It reads a media query, which does not exist on a server, so branching the
 * *initial style* on it made the server and the client disagree and produced a
 * hydration mismatch on every revealed element. `MotionProvider` sets
 * `reducedMotion="user"` at the root instead, and framer-motion drops the
 * transform at run time on both sides identically. See that file for the full
 * account.
 */

export function Reveal({
  children,
  delay = 0,
  direction = 'up',
  className,
  once = true,
  amount = 0.25,
}: {
  children: ReactNode
  delay?: number
  direction?: Direction
  className?: string
  once?: boolean
  amount?: number
}) {
  const { x, y } = offset[direction]

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, x, y }}
      whileInView={{ opacity: 1, x: 0, y: 0 }}
      viewport={{ once, amount }}
      transition={{ duration: duration.slow, delay, ease: easing.out }}
    >
      {children}
    </motion.div>
  )
}

/** Parent that staggers its `RevealItem` children. */
export function RevealGroup({
  children,
  className,
  stagger = 0.045,
  delay = 0,
  amount = 0.2,
}: {
  children: ReactNode
  className?: string
  stagger?: number
  delay?: number
  amount?: number
}) {
  const variants: Variants = {
    hidden: {},
    show: { transition: { staggerChildren: stagger, delayChildren: delay } },
  }

  return (
    <motion.div
      className={className}
      variants={variants}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount }}
    >
      {children}
    </motion.div>
  )
}

export function RevealItem({
  children,
  className,
  direction = 'up',
}: {
  children: ReactNode
  className?: string
  direction?: Direction
}) {
  const { x, y } = offset[direction]

  const variants: Variants = {
    hidden: { opacity: 0, x, y },
    show: {
      opacity: 1,
      x: 0,
      y: 0,
      transition: { duration: duration.slow, ease: easing.out },
    },
  }

  return (
    <motion.div className={className} variants={variants}>
      {children}
    </motion.div>
  )
}

/**
 * Splits a string into words and reveals them in sequence. Used sparingly —
 * only the hero headline earns this much attention.
 *
 * CSS-animated rather than JavaScript-animated, and that is the whole point.
 * Each word sits inside an `overflow-hidden` mask and starts translated fully
 * out of it, so the hidden state is not a faint word — it is no word at all.
 * Driven from JS that state renders into the server HTML, so the headline is
 * blank until React hydrates; on a slow connection the first paint of the page
 * is an empty hero. A keyframe animation starts at first paint instead, needs
 * no bundle, and degrades to visible rather than absent if scripting fails.
 *
 * Reduced motion is handled globally in `globals.css`, which collapses every
 * animation duration — so the words land immediately rather than staying
 * hidden.
 */
export function RevealWords({
  text,
  className,
  wordClassName,
  delay = 0,
}: {
  text: string
  className?: string
  wordClassName?: string
  delay?: number
}) {
  const words = text.split(' ')

  return (
    <span className={className}>
      {words.map((word, i) => (
        <Fragment key={`${word}-${i}`}>
          {/* The mask has to wrap the word and nothing else. A trailing space
              inside an `inline-block` — worse, inside one with
              `overflow-hidden` — is collapsed away, which ran every word in the
              headline together. The separator therefore sits between the masks
              as an ordinary text node. */}
          <span className="inline-block overflow-hidden align-bottom">
            <span
              className={`animate-word-rise inline-block ${wordClassName ?? ''}`}
              style={{ animationDelay: `${delay + i * 0.06}s` }}
            >
              {word}
            </span>
          </span>
          {i < words.length - 1 ? ' ' : ''}
        </Fragment>
      ))}
    </span>
  )
}
