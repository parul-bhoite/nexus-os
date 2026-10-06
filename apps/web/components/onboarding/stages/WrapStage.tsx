'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/Button'
import { duration, useMotionSafe } from '@/lib/motion'

/**
 * Part 3 of 3 — the calm arrival.
 *
 * Deliberately not a progress screen: tools, documents and domain verification
 * are not in this flow (they live later, in Settings, per the product's
 * existing "start straight away" copy) so there is nothing left to assemble
 * here beyond handing the founder into their own workspace. The auto-advance
 * is short and always paired with a manual control — someone using a screen
 * reader or who simply reads slower is never raced by a timer with no escape.
 */
export function WrapStage() {
  const router = useRouter()
  const safe = useMotionSafe()

  useEffect(() => {
    const delay = safe ? 1400 : duration.instant * 1000
    const id = setTimeout(() => router.replace('/dashboard'), delay)
    return () => clearTimeout(id)
  }, [router, safe])

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-page text-ink-900">You&rsquo;re all set.</h1>
      <p className="max-w-read text-body text-ink-600">
        Entering your workspace — your directors and dashboards are ready for the areas you chose.
      </p>
      <Button size="lg" className="mt-2 self-start" onClick={() => router.replace('/dashboard')}>
        Enter your workspace
      </Button>
    </div>
  )
}
