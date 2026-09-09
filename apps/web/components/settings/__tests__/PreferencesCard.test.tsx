import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PreferencesCard } from '@/components/settings/PreferencesCard'

/**
 * Panel 2. Every field is a `persona.*` column and none of them authorises
 * anything (`doc/06` §2.6) — so the assertions are about the panel *saying* so,
 * and about the one distinction that would otherwise collapse: this timezone is
 * where you read from, and Reporting's is where a day ends for the company.
 */

const PREFS = {
  language: 'en',
  timezone: 'Asia/Muscat',
  communication_style: 'standard',
  default_landing_screen: null,
  priority_topics: ['cash', 'late deliveries'],
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => json(PREFS)))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('PreferencesCard', () => {
  it('says a preference changes what you are told, never what you may know', async () => {
    // A person who suspects a preference might be a permission will not change
    // it, so the panel has to be explicit.
    render(<PreferencesCard />)

    await waitFor(() => expect(screen.getByText(/never what you are allowed to know/)).toBeTruthy())
  })

  it('distinguishes your timezone from where reports are cut', async () => {
    // Two different facts that would collapse into one field if nobody said so.
    render(<PreferencesCard />)

    await waitFor(() => expect(screen.getByText(/Where you read from/)).toBeTruthy())
  })

  it('shows the inferred topics without offering checkboxes for them', async () => {
    // Taken from what the founder said would go wrong. A checkbox list would
    // turn a considered answer into a shopping basket.
    render(<PreferencesCard />)

    await waitFor(() => expect(screen.getByText(/cash · late deliveries/)).toBeTruthy())
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('needs no owner, so it always offers a save', async () => {
    render(<PreferencesCard />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Save preferences/ })).toBeTruthy(),
    )
  })
})
