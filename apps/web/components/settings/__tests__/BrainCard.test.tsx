import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BrainCard } from '@/components/settings/BrainCard'

/**
 * Panel 10. The assumptions are the point of the panel, not a footer — an
 * assumption presented as a fact is the one failure that would matter here.
 */

const BRAIN = {
  version: 2,
  generated_by: 'answers',
  unavailable_reason: '',
  profile: 'Industrial supplies and distribution in Oman.',
  products_services: 'Valves, fittings, industrial consumables.',
  target_customers: null,
  goals: null,
  assumptions: ['Headcount inferred from the website'],
  provenance: ['onboarding_answer:what_you_sell', 'crawl:home'],
}

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => respond(BRAIN)))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('BrainCard', () => {
  it('shows the assumptions as prominently as the facts, labelled as assumptions', async () => {
    render(<BrainCard />)

    await waitFor(() => expect(screen.getByText(/What it had to assume/)).toBeTruthy())
    expect(screen.getByText(/Assumptions, not findings/)).toBeTruthy()
  })

  it('says a brain built without a model is complete, not a fallback', async () => {
    // ADR 0011. A founder who thinks they are looking at a degraded version
    // will not correct it.
    render(<BrainCard />)

    await waitFor(() => expect(screen.getByText(/invented nothing/)).toBeTruthy())
  })

  it('offers no delete, and says why', async () => {
    // A button that removed the row and left the embeddings would say a fact
    // was gone while it was still retrievable.
    render(<BrainCard />)

    await waitFor(() => expect(screen.getByText(/Read-only here/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()
  })

  it('omits a section it has no content for rather than showing an empty heading', async () => {
    render(<BrainCard />)

    await waitFor(() => expect(screen.getByText('Profile')).toBeTruthy())
    expect(screen.queryByText('Goals')).toBeNull()
  })

  it('says a brain that could not be assembled was not, with the reason', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        respond({ ...BRAIN, generated_by: 'unavailable', unavailable_reason: 'no answers yet' }),
      ),
    )
    render(<BrainCard />)

    await waitFor(() => expect(screen.getByText(/no answers yet/)).toBeTruthy())
    expect(screen.getByText(/Nothing is filled in with a guess/)).toBeTruthy()
  })

  it('treats an absent brain as a stage rather than a fault', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond({ detail: 'Not found' }, 404)))
    render(<BrainCard />)

    await waitFor(() => expect(screen.getByText(/Not built yet/)).toBeTruthy())
  })
})
