'use client'

import { useEffect, useState } from 'react'

/**
 * A label for a button that is waiting on something slow.
 *
 * Finding F9's other half. `Waiting` handles a page that is loading; this
 * handles a *submit* — sign in (~15 s), create company (~8 s, occasionally
 * measured as long as ~25 s — R-02), save a department block (~10 s) — where
 * the only place to say anything is the button itself, and each of them said
 * one word for the whole duration.
 *
 * Returns the label to render. `busy` false gives the idle one; otherwise the
 * label advances as the wait goes on, which is the product's own Q57: never one
 * spinner. Nothing here estimates a proportion — every string is simply true
 * when it appears.
 *
 *     const label = useSlowLabel(busy, 'Sign in', 'Signing in…')
 *
 * The escalation is deliberately vague about time rather than counting seconds
 * up at somebody. A counter turns a slow request into a stopwatch to watch,
 * which is worse than a sentence that changes twice.
 *
 * **R-02: a second escalation.** With `registerCompany` now carrying a 30s
 * client-side ceiling rather than none at all, a caller waiting past the
 * first escalation at 6s had nothing further to read for up to twenty-four
 * more seconds — the copy froze exactly when patience is thinnest. A second
 * stage at 16s says the wait is now unusual rather than leaving the first
 * "still going" to speak for the entire remainder.
 */
export function useSlowLabel(
  busy: boolean,
  idle: string,
  working: string,
  stillWorking = `${working} still going`,
  takingLonger = 'This is taking longer than usual…',
): string {
  const [stage, setStage] = useState(0)

  useEffect(() => {
    if (!busy) {
      setStage(0)
      return
    }
    const first = setTimeout(() => setStage(1), 6_000)
    const second = setTimeout(() => setStage(2), 16_000)
    return () => {
      clearTimeout(first)
      clearTimeout(second)
    }
  }, [busy])

  if (!busy) return idle
  if (stage === 0) return working
  if (stage === 1) return stillWorking
  return takingLonger
}
