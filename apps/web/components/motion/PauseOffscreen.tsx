'use client'

import { useEffect } from 'react'

/**
 * Stops decorative animation in sections nobody is looking at.
 *
 * ## Why
 *
 * The landing page runs twenty-six infinite CSS animations — eleven
 * `pulse-ring`s, six `dash-flow`s, and the floats, drifts and sways inside the
 * paper-cut illustrations. Each one is individually cheap and defensible: they
 * are what makes the artwork feel drawn rather than printed.
 *
 * The problem is that all of them run all of the time, including in the nine
 * sections that are thousands of pixels off screen. The browser keeps
 * compositing every one, on a 13,000-pixel page, for as long as the tab is
 * open. On a phone that is a measurable, pointless battery cost, and it is the
 * thing the brief means by "no excessive animation loops".
 *
 * ## How
 *
 * One `IntersectionObserver` over the page's sections, toggling the
 * `motion-paused` class from `globals.css` — which sets `animation-play-state:
 * paused` on the section and everything in it. Paused, not cancelled: a
 * `pulse-ring` resumes mid-cycle where it left off, so scrolling back to a
 * section does not restart its artwork.
 *
 * `rootMargin` is generous (half a viewport either side) so a section is
 * already running before it is visible. An animation that starts *as* you
 * arrive is more noticeable than one that was never paused.
 *
 * ## Why this is not in each component
 *
 * Because the components that own these animations are illustrations, and an
 * illustration should not have to know about the viewport. One observer here
 * costs nothing and covers every section, including ones added later.
 *
 * Renders nothing.
 */
export function PauseOffscreen() {
  useEffect(() => {
    // Nothing to pause if the reader has already asked for no motion — the
    // global media query has collapsed every duration to ~0 and the classes
    // would fight over an animation that is not running.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const sections = document.querySelectorAll<HTMLElement>('main > section')
    if (sections.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          entry.target.classList.toggle('motion-paused', !entry.isIntersecting)
        }
      },
      { rootMargin: '50% 0px 50% 0px' },
    )

    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [])

  return null
}
