'use client'

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { looksSignedIn } from '@/lib/auth-client'

/** True once the window has scrolled past `threshold` px. */
export function useScrolled(threshold = 12) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [threshold])

  return scrolled
}

/**
 * Normalised pointer position (-1..1 on both axes) relative to the viewport
 * centre, smoothed via rAF. Drives the hero parallax.
 */
export function usePointerParallax(disabled = false) {
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const frame = useRef<number | null>(null)
  const target = useRef({ x: 0, y: 0 })

  useEffect(() => {
    if (disabled) return
    // Pointer parallax is meaningless without a fine pointer.
    if (!window.matchMedia('(pointer: fine)').matches) return

    const onMove = (e: PointerEvent) => {
      target.current = {
        x: (e.clientX / window.innerWidth) * 2 - 1,
        y: (e.clientY / window.innerHeight) * 2 - 1,
      }
      if (frame.current === null) {
        frame.current = requestAnimationFrame(tick)
      }
    }

    const tick = () => {
      setPos((prev) => {
        const next = {
          x: prev.x + (target.current.x - prev.x) * 0.08,
          y: prev.y + (target.current.y - prev.y) * 0.08,
        }
        const settled =
          Math.abs(next.x - target.current.x) < 0.001 && Math.abs(next.y - target.current.y) < 0.001
        frame.current = settled ? null : requestAnimationFrame(tick)
        return next
      })
    }

    window.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      window.removeEventListener('pointermove', onMove)
      if (frame.current !== null) cancelAnimationFrame(frame.current)
    }
  }, [disabled])

  return pos
}

/** Tracks which of the given section ids is currently in view. */
/**
 * Which section the reader is looking at.
 *
 * ## Why this is not an IntersectionObserver any more
 *
 * It was, and it reported the wrong section — reproducibly. Scrolling *down*
 * from Pillars into Moments moved the nav indicator *back* to "Your team", and
 * it stayed on "Pricing" through the whole FAQ.
 *
 * The cause is that the old implementation sorted the intersecting entries by
 * `intersectionRatio` and took the highest. `intersectionRatio` is a fraction
 * of **the observed element's own size**, so it is not comparable between
 * elements of different heights — and these differ by a factor of three.
 * Inside the 10%-of-viewport band the old `rootMargin` left, Pillars (1,898px
 * tall) scores about 0.05 while Moments (732px) scores 0.12. The shorter
 * section wins the sort whenever both are in the band, whichever one the reader
 * is actually in. The second defect compounded it: an observer callback
 * receives only the entries whose intersection *changed* in that batch, so the
 * comparison was frequently between one fresh entry and nothing at all.
 *
 * A position test has neither problem. The active section is the last one whose
 * top has passed a line 40% down the viewport — which is a direct statement of
 * "the section the reader is reading", needs no comparison between elements,
 * and cannot disagree with itself.
 *
 * Read inside `requestAnimationFrame` so a scroll burst costs one layout read
 * per frame rather than one per event, and `passive: true` so the listener can
 * never delay the scroll it is watching.
 */
export function useActiveSection(ids: readonly string[]) {
  const [active, setActive] = useState<string | null>(null)

  useEffect(() => {
    let frame = 0

    function measure() {
      frame = 0
      // 40% rather than 50%: a section's heading is at its top, and a reader
      // who has just brought a heading onto the screen considers themselves in
      // that section before its midpoint reaches the middle of the window.
      const line = window.scrollY + window.innerHeight * 0.4
      let current: string | null = null

      for (const id of ids) {
        const element = document.getElementById(id.replace('#', ''))
        if (!element) continue
        const top = element.getBoundingClientRect().top + window.scrollY
        // `ids` is in document order, so the last one to pass the line is the
        // one being read. No sort, and nothing to compare between elements.
        if (top <= line) current = id
      }

      setActive(current)
    }

    function onScroll() {
      if (frame === 0) frame = requestAnimationFrame(measure)
    }

    measure()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll, { passive: true })
    return () => {
      if (frame !== 0) cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [ids])

  return active
}

/** Fires once when the element enters the viewport. */
export function useInViewOnce<T extends HTMLElement>(amount = 0.4) {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || seen) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true)
          observer.disconnect()
        }
      },
      { threshold: amount },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [amount, seen])

  return { ref, seen }
}

/** No cookie change event exists, so there is nothing to subscribe to. */
const noopSubscribe = () => () => {}

/**
 * `looksSignedIn`, safe to call during render.
 *
 * Finding F5: `AcceptInvitation` read `document.cookie` in its render body, so
 * the server produced the signed-out branch and the client's first render
 * wanted the signed-in one. React reported *"Expected server HTML to contain a
 * matching <button>"*, gave up on the Suspense boundary and switched the whole
 * subtree to client rendering — on the very first page a new teammate ever
 * loads, and at the cost of that page's server rendering entirely.
 *
 * `useSyncExternalStore` rather than a `mounted` flag, because it is the
 * version that cannot be got wrong later: React uses the *server* snapshot for
 * hydration as well, so the first client render matches by construction, and
 * the real value arrives in the pass immediately after.
 *
 * Still only a hint. The cookie is readable and therefore forgeable, and the
 * API answers 401 regardless of what this says.
 */
export function useLooksSignedIn(): boolean {
  return useSyncExternalStore(noopSubscribe, looksSignedIn, () => false)
}
